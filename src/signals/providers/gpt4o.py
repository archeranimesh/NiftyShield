"""OpenRouter-backed :class:`SignalProvider` for GPT-4o (Phase 1)."""

import asyncio
import json
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

from src.client.exceptions import DataFetchError

from ..models import Direction, MarketSnapshot, SignalResponse
from ..prompt import build_prompt

_PROVIDER = "gpt4o"


class GPT4oSignalProvider:
    """Call GPT-4o via OpenRouter chat completions and parse a structured signal.

    Phase 1 POC: all providers route through a single ``OPENROUTER_API_KEY``.
    GPT-4o stays on OpenRouter in Phase 2 (no direct-API upgrade planned).
    """

    provider_name: str = _PROVIDER

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-4o",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 60.0,
    ) -> None:
        """Configure the provider.

        Args:
            api_key: OpenRouter API key.
            model: OpenRouter model string.
            base_url: OpenRouter API base URL (no trailing slash).
            timeout: Total request timeout in seconds.
        """
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def get_signal(self, snapshot: MarketSnapshot) -> SignalResponse:
        """POST the snapshot prompt to OpenRouter and parse the JSON reply.

        Args:
            snapshot: Market snapshot to reason over.

        Returns:
            The parsed :class:`SignalResponse`.

        Raises:
            DataFetchError: On HTTP error, malformed envelope, or a
                ``message.content`` body that is not valid signal JSON.
        """
        messages = build_prompt(snapshot, _PROVIDER)
        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base_url}/chat/completions"

        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    resp.raise_for_status()
                    envelope = await resp.json()
        except aiohttp.ClientResponseError as e:
            raise DataFetchError(f"{_PROVIDER}: OpenRouter HTTP {e.status}: {e}") from e
        except aiohttp.ClientError as e:
            raise DataFetchError(f"{_PROVIDER}: OpenRouter request failed: {e}") from e
        except asyncio.TimeoutError as e:
            raise DataFetchError(
                f"{_PROVIDER}: request timed out after {self._timeout.total}s"
            ) from e

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
