"""Gemini :class:`SignalProvider` — Phase 1 OpenRouter shim, Phase 2 Google AI SDK."""

import asyncio
import json
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

from src.client.exceptions import DataFetchError

from ..models import Direction, MarketSnapshot, SignalResponse
from ..prompt import build_prompt

try:  # Phase 2 dependency — optional until a Google AI key is acquired.
    import google.generativeai as genai
except ImportError:  # pragma: no cover - exercised via patched import in tests
    genai = None

_PROVIDER = "gemini"

_OPENROUTER = ("https://openrouter.ai/api/v1", "google/gemini-2.0-flash")
_GOOGLE_MODEL = "gemini-2.0-flash"

_MISSING_SDK = "google-generativeai not installed; run: pip install google-generativeai"


class GeminiSignalProvider:
    """Call Gemini and parse a structured signal.

    Two operating modes selected by ``use_openrouter``:

    - Phase 1 (``use_openrouter=True``, default): route through OpenRouter with
      ``google/gemini-2.0-flash``. No search grounding.
    - Phase 2 (``use_openrouter=False``): Google AI SDK with ``gemini-2.0-flash``
      and Google Search grounding enabled.
    """

    provider_name: str = _PROVIDER

    def __init__(
        self,
        api_key: str,
        use_openrouter: bool = True,
        timeout: float = 30.0,
        model: str | None = None,
    ) -> None:
        """Configure the provider.

        Args:
            api_key: OpenRouter key (Phase 1) or ``GOOGLE_AI_API_KEY`` (Phase 2).
            use_openrouter: Route via OpenRouter when True, else Google AI SDK.
            timeout: Total request timeout in seconds (Phase 1 only).
            model: Override the OpenRouter model slug. Defaults to
                ``google/gemini-2.0-flash``.

        Raises:
            ImportError: When ``use_openrouter=False`` and ``google-generativeai``
                is not installed.
        """
        if not use_openrouter and genai is None:
            raise ImportError(_MISSING_SDK)
        self._api_key = api_key
        self._use_openrouter = use_openrouter
        self._base_url, default_model = _OPENROUTER
        self._model = model or default_model
        self._timeout_s = timeout
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        if not use_openrouter:
            genai.configure(api_key=api_key)

    async def get_signal(self, snapshot: MarketSnapshot) -> SignalResponse:
        """Fetch the snapshot prompt's structured reply from the configured backend.

        Args:
            snapshot: Market snapshot to reason over.

        Returns:
            The parsed :class:`SignalResponse`.

        Raises:
            DataFetchError: On HTTP error, timeout, malformed envelope, or a
                response body that is not valid signal JSON.
        """
        messages = build_prompt(snapshot, _PROVIDER)
        if not self._use_openrouter:
            content = await self._call_google_sdk(messages)
            return _build_signal(snapshot, content)
        return await self._call_openrouter(snapshot, messages)

    async def _call_openrouter(
        self, snapshot: MarketSnapshot, messages: list[dict[str, str]]
    ) -> SignalResponse:
        """POST to OpenRouter chat completions and parse the reply."""
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": 512,
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
            raise DataFetchError(f"{_PROVIDER}: HTTP {e.status}: {e}") from e
        except aiohttp.ClientError as e:
            raise DataFetchError(f"{_PROVIDER}: request failed: {e}") from e
        except asyncio.TimeoutError as e:
            raise DataFetchError(
                f"{_PROVIDER}: request timed out after {self._timeout.total}s"
            ) from e

        try:
            content = envelope["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise DataFetchError(f"{_PROVIDER}: unexpected response envelope: {e}") from e
        return _build_signal(snapshot, content)

    async def _call_google_sdk(self, messages: list[dict[str, str]]) -> str:
        """Run the Google AI SDK call (with search grounding) off the event loop."""
        prompt = "\n\n".join(m["content"] for m in messages)

        def _generate() -> str:
            model = genai.GenerativeModel(_GOOGLE_MODEL)
            result = model.generate_content(prompt, tools=["google_search_retrieval"])
            return result.text

        try:
            return await asyncio.wait_for(asyncio.to_thread(_generate), timeout=self._timeout_s)
        except asyncio.TimeoutError as e:
            raise DataFetchError(f"{_PROVIDER}: request timed out after {self._timeout_s}s") from e
        except Exception as e:  # Intentional: isolate all upstream SDK failures here
            raise DataFetchError(f"{_PROVIDER}: Google AI SDK call failed: {e}") from e


def _build_signal(snapshot: MarketSnapshot, content: Any) -> SignalResponse:
    """Parse an LLM ``message.content`` body into a :class:`SignalResponse`."""
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
