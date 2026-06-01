from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Callable
from typing import Any

import aiohttp
import structlog

from src.client.exceptions import BrokerError, DataFetchError
from src.council.models import CouncilOutput, PersonaResponse
from src.strategy.protocol import ApprovedAction, LegSpec, SignalEvent

logger = structlog.get_logger(__name__)


class CouncilTimeoutError(BrokerError):
    """Raised when the council chairman times out or fails to respond."""

    pass


class RapidCouncil:
    """Orchestrates parallel Stage 1 advisor calls and a sequential Stage 2 synthesis by the Chairman."""

    def __init__(
        self,
        spec_doc: str,
        openrouter_api_key: str,
        anthropic_api_key: str,
        xai_api_key: str,
    ) -> None:
        self.spec_doc = spec_doc
        self.openrouter_api_key = openrouter_api_key
        self.anthropic_api_key = anthropic_api_key
        self.xai_api_key = xai_api_key

    async def _post_request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        parser_fn: Callable[[dict[str, Any]], str],
    ) -> tuple[str, int, str | None]:
        async with session.post(url, json=payload, headers=headers) as resp:
            status_code = resp.status
            request_id = resp.headers.get("x-request-id") or resp.headers.get("request-id")
            resp.raise_for_status()
            data = await resp.json()
            return parser_fn(data), status_code, request_id

    async def _call_persona(
        self,
        session: aiohttp.ClientSession,
        persona: str,
        model: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        parser_fn: Callable[[dict[str, Any]], str],
        timeout: float = 25.0,
    ) -> PersonaResponse:
        start_time = time.perf_counter()
        status_code = None
        request_id = None
        try:
            response_text, status_code, request_id = await asyncio.wait_for(
                self._post_request(session, url, payload, headers, parser_fn),
                timeout=timeout,
            )
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.info(
                "Council Stage 1 persona call completed",
                persona=persona,
                model=model,
                url=url,
                status_code=status_code,
                request_id=request_id,
                latency_ms=latency_ms,
            )
            return PersonaResponse(
                persona=persona,
                model=model,
                response=response_text,
                latency_ms=latency_ms,
                timed_out=False,
            )
        except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError) as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            is_timeout = isinstance(e, (asyncio.TimeoutError, TimeoutError))
            err_status = getattr(e, "status", None) or status_code
            logger.warning(
                "Council Stage 1 persona call failed",
                persona=persona,
                model=model,
                url=url,
                status_code=err_status,
                latency_ms=latency_ms,
                error=str(e),
                timed_out=is_timeout,
            )
            return PersonaResponse(
                persona=persona,
                model=model,
                response="",
                latency_ms=latency_ms,
                timed_out=is_timeout,
            )

    def _parse_chairman_response(
        self, response_text: str
    ) -> tuple[list[ApprovedAction], str, str | None]:
        # Search for JSON block
        json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response_text

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            brace_match = re.search(r"(\{.*\}|\[.*\])", json_str, re.DOTALL)
            if brace_match:
                try:
                    data = json.loads(brace_match.group(1))
                except json.JSONDecodeError:
                    data = None
            else:
                data = None

        actions: list[ApprovedAction] = []
        rationale = response_text
        dissenting: str | None = None

        if isinstance(data, dict):
            raw_actions = data.get("actions", [])
            rationale = data.get("chairman_rationale", response_text)
            dissenting = data.get("dissenting_notes")
        elif isinstance(data, list):
            raw_actions = data
        else:
            raw_actions = []

        if isinstance(raw_actions, list):
            for idx, item in enumerate(raw_actions):
                if not isinstance(item, dict):
                    continue
                try:
                    legs_open = []
                    for leg in item.get("legs_to_open", []):
                        legs_open.append(
                            LegSpec(
                                instrument_key=leg.get("instrument_key", ""),
                                action=leg.get("action", "BUY"),
                                quantity=int(leg.get("quantity", 0)),
                                leg_role=leg.get("leg_role", ""),
                                notes=leg.get("notes", ""),
                            )
                        )
                    actions.append(
                        ApprovedAction(
                            action_type=item.get("action_type", ""),
                            legs_to_close=item.get("legs_to_close", []),
                            legs_to_open=legs_open,
                            rationale=item.get("rationale", ""),
                            council_rank=int(item.get("council_rank", idx + 1)),
                        )
                    )
                except Exception:
                    continue

        return actions, rationale, dissenting

    async def consult(
        self,
        event: SignalEvent,
        context: str,
    ) -> CouncilOutput:
        """Consult Stage 1 personas in parallel, then synthesize via Chairman in Stage 2."""
        start_time = time.perf_counter()

        openrouter_headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        anthropic_headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        xai_headers = {
            "Authorization": f"Bearer {self.xai_api_key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            # Stage 1: Setup tasks
            tasks = []

            # 1. QuantAnalyst (DeepSeek via OpenRouter)
            quant_prompt = (
                f"You are the QuantAnalyst. Analyze the following context and signal event.\n"
                f"Context: {context}\n"
                f"Event: {event}\n"
                f"Focus on statistical edge, historical context, and mathematical soundness."
            )
            tasks.append(
                self._call_persona(
                    session=session,
                    persona="QuantAnalyst",
                    model="deepseek/deepseek-r1-0528",
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers=openrouter_headers,
                    payload={
                        "model": "deepseek/deepseek-r1-0528",
                        "messages": [{"role": "user", "content": quant_prompt}],
                    },
                    parser_fn=lambda d: d["choices"][0]["message"]["content"],
                    timeout=25.0,
                )
            )

            # 2. SpecGuardian (Claude Haiku direct)
            spec_prompt = (
                f"You are the SpecGuardian. Read the strategy specification document:\n{self.spec_doc}\n"
                f"Analyze the current context and signal event.\n"
                f"Context: {context}\n"
                f"Event: {event}\n"
                f"You MUST evaluate each proposed action against the strategy specification and "
                f"output 'COMPLIANT' or 'NON-COMPLIANT' for each, citing the relevant clause."
            )
            tasks.append(
                self._call_persona(
                    session=session,
                    persona="SpecGuardian",
                    model="claude-haiku-4-5-20251001",
                    url="https://api.anthropic.com/v1/messages",
                    headers=anthropic_headers,
                    payload={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 4096,
                        "messages": [{"role": "user", "content": spec_prompt}],
                    },
                    parser_fn=lambda d: d["content"][0]["text"],
                    timeout=25.0,
                )
            )

            # 3. RiskManager (o3-mini via OpenRouter)
            risk_prompt = (
                f"You are the RiskManager. Analyze the following context and signal event.\n"
                f"Context: {context}\n"
                f"Event: {event}\n"
                f"Focus on portfolio-level risk, margin requirements, drawdown control, and worst-case scenarios."
            )
            tasks.append(
                self._call_persona(
                    session=session,
                    persona="RiskManager",
                    model="openai/o3-mini",
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers=openrouter_headers,
                    payload={
                        "model": "openai/o3-mini",
                        "messages": [{"role": "user", "content": risk_prompt}],
                    },
                    parser_fn=lambda d: d["choices"][0]["message"]["content"],
                    timeout=25.0,
                )
            )

            # 4. OptionsStrategist (Grok 4 Fast direct)
            options_prompt = (
                f"You are the OptionsStrategist. Analyze the following context and signal event.\n"
                f"Context: {context}\n"
                f"Event: {event}\n"
                f"Focus on trade structure, delta adjustments, rolling opportunities, and volatility dynamics."
            )
            tasks.append(
                self._call_persona(
                    session=session,
                    persona="OptionsStrategist",
                    model="x-ai/grok-4-fast",
                    url="https://api.x.ai/v1/chat/completions",
                    headers=xai_headers,
                    payload={
                        "model": "grok-4-fast",
                        "messages": [{"role": "user", "content": options_prompt}],
                    },
                    parser_fn=lambda d: d["choices"][0]["message"]["content"],
                    timeout=25.0,
                )
            )

            stage1_responses = await asyncio.gather(*tasks)

            # Stage 2: Synthesis by Chairman (Claude Sonnet 4.6 direct)
            stage1_summary = ""
            for resp in stage1_responses:
                status = "TIMED OUT" if resp.timed_out else "SUCCESS"
                stage1_summary += (
                    f"=== {resp.persona} ({resp.model}) - {status} ===\n{resp.response}\n\n"
                )

            chairman_prompt = (
                f"You are the Chairman of the NiftyShield Trading Council.\n"
                f"Synthesize the following reports from the council members:\n"
                f"{stage1_summary}\n"
                f"Context: {context}\n"
                f"Event: {event}\n"
                f"Make the final decision. Output a JSON object containing:\n"
                f"1. 'actions': list of ApprovedAction objects ranked by quality (rank 1 = top pick).\n"
                f"2. 'chairman_rationale': your final synthesis and rationale.\n"
                f"3. 'dissenting_notes': any significant risks, dissenting opinions, or SpecGuardian non-compliance concerns.\n"
                f"Ensure the output JSON is valid."
            )

            chairman_payload = {
                "model": "claude-sonnet-4-6",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": chairman_prompt}],
            }

            try:
                start_time_chairman = time.perf_counter()
                chairman_response_text, status_code, request_id = await asyncio.wait_for(
                    self._post_request(
                        session=session,
                        url="https://api.anthropic.com/v1/messages",
                        payload=chairman_payload,
                        headers=anthropic_headers,
                        parser_fn=lambda d: d["content"][0]["text"],
                    ),
                    timeout=15.0,
                )
                latency_ms_chairman = int((time.perf_counter() - start_time_chairman) * 1000)
                logger.info(
                    "Council Chairman call completed",
                    model="claude-sonnet-4-6",
                    status_code=status_code,
                    request_id=request_id,
                    latency_ms=latency_ms_chairman,
                )
            except (asyncio.TimeoutError, TimeoutError) as e:
                logger.error(
                    "Council Chairman call timed out",
                    model="claude-sonnet-4-6",
                    error=str(e),
                )
                raise CouncilTimeoutError("Chairman request timed out after 15 seconds.") from e
            except aiohttp.ClientResponseError as e:
                logger.error(
                    "Council Chairman HTTP error",
                    model="claude-sonnet-4-6",
                    status_code=e.status,
                    error=str(e),
                )
                raise DataFetchError(f"Chairman request HTTP error ({e.status}): {e}") from e
            except aiohttp.ClientError as e:
                logger.error(
                    "Council Chairman client error",
                    model="claude-sonnet-4-6",
                    error=str(e),
                )
                raise DataFetchError(f"Chairman request client error: {e}") from e

            actions, rationale, dissenting = self._parse_chairman_response(chairman_response_text)

            # Check if SpecGuardian returned NON-COMPLIANT
            # If so, append that to dissenting_notes if not already addressed
            spec_resp = next((r for r in stage1_responses if r.persona == "SpecGuardian"), None)
            if spec_resp and "NON-COMPLIANT" in spec_resp.response:
                guard_note = (
                    f"[SpecGuardian Compliance Alert] NON-COMPLIANT detected:\n{spec_resp.response}"
                )
                if dissenting:
                    dissenting = f"{dissenting}\n\n{guard_note}"
                else:
                    dissenting = guard_note

            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return CouncilOutput(
                actions=actions,
                chairman_rationale=rationale,
                dissenting_notes=dissenting,
                stage1_responses=list(stage1_responses),
                latency_ms=latency_ms,
            )
