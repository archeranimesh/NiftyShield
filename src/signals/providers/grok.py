"""Grok :class:`SignalProvider` — Phase 1 OpenRouter shim, Phase 2 xAI direct."""

import asyncio
import json
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

from src.client.exceptions import DataFetchError

from ..models import Direction, MarketSnapshot, SignalResponse
from ..prompt import build_prompt

_PROVIDER = "grok"

_OPENROUTER = ("https://openrouter.ai/api/v1", "x-ai/grok-3")
_XAI_DIRECT = ("https://api.x.ai/v1", "grok-3")


class GrokSignalProvider:
    """Call Grok and parse a structured signal.

    Two operating modes selected by ``use_openrouter``:

    - Phase 1 (``use_openrouter=True``, default): route through OpenRouter with
      ``x-ai/grok-3``. No search capability — behaves like a plain model.
    - Phase 2 (``use_openrouter=False``): xAI direct API with ``grok-3`` and a
      ``"search": True`` request flag.
    """

    provider_name: str = _PROVIDER

    def __init__(
        self,
        api_key: str,
        use_openrouter: bool = True,
        timeout: float = 60.0,
        model: str | None = None,
    ) -> None:
        """Configure the provider.

        Args:
            api_key: OpenRouter key (Phase 1) or xAI key (Phase 2).
            use_openrouter: Route via OpenRouter when True, else xAI direct.
            timeout: Total request timeout in seconds.
            model: Override the model slug. Defaults to the current mode's
                constant (``x-ai/grok-3`` on OpenRouter, ``grok-3`` direct).
        """
        self._api_key = api_key
        self._use_openrouter = use_openrouter
        self._base_url, default_model = _OPENROUTER if use_openrouter else _XAI_DIRECT
        self._model = model or default_model
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def get_signal(self, snapshot: MarketSnapshot) -> SignalResponse:
        """POST the snapshot prompt to the configured endpoint and parse the reply.

        Args:
            snapshot: Market snapshot to reason over.

        Returns:
            The parsed :class:`SignalResponse`.

        Raises:
            DataFetchError: On HTTP error, timeout, malformed envelope, or a
                ``message.content`` body that is not valid signal JSON.
        """
        messages = build_prompt(snapshot, _PROVIDER)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        if not self._use_openrouter:
            payload["search"] = True
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base_url}/chat/completions"

        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    body_text = await resp.text()
                    status = resp.status
        except aiohttp.ClientError as e:
            raise DataFetchError(f"{_PROVIDER}: request failed: {e}") from e
        except UnicodeDecodeError as e:
            raise DataFetchError(f"{_PROVIDER}: undecodable response body: {e}") from e
        except asyncio.TimeoutError as e:
            raise DataFetchError(
                f"{_PROVIDER}: request timed out after {self._timeout.total}s"
            ) from e

        if status >= 400:
            raise DataFetchError(f"{_PROVIDER}: HTTP {status}: {body_text[:500]}")
        try:
            envelope = json.loads(body_text)
        except json.JSONDecodeError as e:
            raise DataFetchError(f"{_PROVIDER}: non-JSON response body: {body_text[:500]}") from e

        return _parse_response(snapshot, envelope)


def _parse_response(snapshot: MarketSnapshot, envelope: dict[str, Any]) -> SignalResponse:
    """Extract ``choices[0].message.content`` and build a :class:`SignalResponse`."""
    try:
        content = envelope["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise DataFetchError(f"{_PROVIDER}: unexpected response envelope: {e}") from e

    try:
        parsed = json.loads(content)
        return SignalResponse(
            trade_date=snapshot.trade_date,
            provider=_PROVIDER,
            direction=Direction(parsed["direction"]),
            confidence=int(parsed["confidence"]),
            recommended_strike=int(parsed["recommended_strike"]),
            entry_premium_low=Decimal(str(parsed["entry_premium_low"])),
            entry_premium_high=Decimal(str(parsed["entry_premium_high"])),
            key_reason=str(parsed["key_reason"]),
            key_risk=str(parsed["key_risk"]),
            raw_response=content if isinstance(content, str) else json.dumps(content),
        )
    except (json.JSONDecodeError, KeyError, ValueError, TypeError, InvalidOperation) as e:
        raise DataFetchError(f"{_PROVIDER}: could not parse signal JSON: {e}") from e
