"""Tests for OpenRouter native model-fallback wiring.

All tests are fully offline — no network calls.  httpx.AsyncClient is mocked
at the ``backend.openrouter`` namespace level.

The llm-council package lives in ``tools/llm-council/`` with its own venv and
relative imports, so we prepend its root to sys.path here rather than relying
on the project-root discovery that works for ``src/``.

Functions covered
-----------------
query_model:
  1  no_fallbacks_payload_uses_model_key      — singular ``model`` str in payload
  2  fallbacks_payload_uses_models_array      — ``models`` list: [primary, fb]
  3  model_used_extracted_from_response       — taken from data["model"], not slug
  4  model_used_defaults_to_primary           — when data["model"] is absent
  5  returns_none_on_http_exception           — any exception → None
  6  402_with_fallback_retries_client_side    — 402 bypasses server failover; client retries
  7  402_without_fallback_returns_none        — 402 + no fallbacks → None (credit exhaustion)
  8  402_cascades_through_all_fallbacks       — each fallback also 402s → None
  9  transport_error_with_fallback_retries    — disconnect retries client-side with fallback
 10  transport_error_without_fallback_is_none — disconnect + no fallbacks → None

query_models_parallel:
  6  dispatches_fallback_per_model         — each member gets its fb from dict
  7  no_fallback_when_key_absent           — missing key → singular model payload
  8  result_keyed_by_primary_slug          — dict keys are original primaries

council.stage1_collect_responses:
  9  records_model_used_in_result          — model_used from response propagated
 10  fallback_from_set_when_fallback_fired — primary ≠ model_used → fallback_from key
 11  no_fallback_from_on_primary_success   — primary == model_used → key absent

council.stage3_synthesize_final:
 12  chairman_called_with_chairman_fallback — CHAIRMAN_FALLBACK passed as fallbacks arg
 13  chairman_fallback_from_in_result       — fallback_from present when chairman fell back
"""

from __future__ import annotations

import sys
import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import httpx
import pytest

# ── path setup ────────────────────────────────────────────────────────────────
_COUNCIL_ROOT = Path(__file__).parents[2] / "tools" / "llm-council"
if str(_COUNCIL_ROOT) not in sys.path:
    sys.path.insert(0, str(_COUNCIL_ROOT))

from backend.openrouter import query_model, query_models_parallel  # noqa: E402
from backend.config import CHAIRMAN_FALLBACK  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_http_mock(content: str = "ok", model_slug: str = "openai/gpt-4.1") -> tuple:
    """Return (mock_AsyncClient_cls, mock_post) for patching httpx.AsyncClient.

    The mock_post captures all call_args so tests can inspect the JSON payload.
    """
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": content, "reasoning_details": None}}],
        "model": model_slug,
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_cls = MagicMock(return_value=mock_cm)
    return mock_cls, mock_client.post


def _make_parallel_mock(
    responses: dict[str, dict[str, Any]],
) -> AsyncMock:
    """Return an AsyncMock for query_models_parallel returning ``responses``."""
    return AsyncMock(return_value=responses)


# ── query_model ───────────────────────────────────────────────────────────────

class TestQueryModelPayload:
    """Verify the JSON payload shape sent to OpenRouter."""

    async def test_no_fallbacks_payload_uses_model_key(self) -> None:
        mock_cls, mock_post = _make_http_mock()
        with patch("backend.openrouter.httpx.AsyncClient", mock_cls):
            await query_model("openai/gpt-4.1", [{"role": "user", "content": "hi"}])

        payload = mock_post.call_args.kwargs["json"]
        assert payload["model"] == "openai/gpt-4.1"
        assert "models" not in payload

    async def test_fallbacks_payload_uses_models_array(self) -> None:
        mock_cls, mock_post = _make_http_mock()
        with patch("backend.openrouter.httpx.AsyncClient", mock_cls):
            await query_model(
                "openai/gpt-5.5",
                [{"role": "user", "content": "hi"}],
                fallbacks=["openai/gpt-4.1"],
            )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["models"] == ["openai/gpt-5.5", "openai/gpt-4.1"]
        assert "model" not in payload

    async def test_model_used_extracted_from_response(self) -> None:
        # OpenRouter returns the fallback slug in data["model"] when it falls back.
        mock_cls, _ = _make_http_mock(content="answer", model_slug="openai/gpt-4.1")
        with patch("backend.openrouter.httpx.AsyncClient", mock_cls):
            result = await query_model(
                "openai/gpt-5.5",
                [{"role": "user", "content": "q"}],
                fallbacks=["openai/gpt-4.1"],
            )

        assert result is not None
        assert result["model_used"] == "openai/gpt-4.1"
        assert result["content"] == "answer"

    async def test_model_used_defaults_to_primary_when_absent(self) -> None:
        # Older OpenRouter responses may omit the top-level "model" field.
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "x", "reasoning_details": None}}],
            # "model" key deliberately absent
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.openrouter.httpx.AsyncClient", MagicMock(return_value=mock_cm)):
            result = await query_model("openai/gpt-4.1", [{"role": "user", "content": "q"}])

        assert result is not None
        assert result["model_used"] == "openai/gpt-4.1"

    async def test_returns_none_on_http_exception(self) -> None:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("network error"))
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.openrouter.httpx.AsyncClient", MagicMock(return_value=mock_cm)):
            result = await query_model("openai/gpt-4.1", [{"role": "user", "content": "q"}])

        assert result is None


class TestQueryModel402Fallback:
    """Verify client-side fallback fires on 402 (billing rejection).

    OpenRouter's server-side ``models[]`` array failover does NOT trigger on
    402 — the request is rejected before model dispatch.  These tests confirm
    that ``query_model`` handles 402 client-side by recursing with the fallback.
    """

    def _make_402_error(self) -> httpx.HTTPStatusError:
        req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        resp = httpx.Response(402, request=req)
        return httpx.HTTPStatusError("402 Payment Required", request=req, response=resp)

    def _make_http_mock_raising(self, exc: Exception):
        """Return an httpx.AsyncClient mock whose .post raises ``exc``."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=exc)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        return MagicMock(return_value=mock_cm)

    async def test_402_with_fallback_retries_client_side(self) -> None:
        """Primary returns 402 → client retries with fallback; fallback succeeds."""
        err_cls = self._make_http_mock_raising(self._make_402_error())
        ok_cls, _ = _make_http_mock(content="fallback answer", model_slug="openai/gpt-4.1")

        call_count = 0

        def client_factory(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First call (primary) → 402; second call (fallback) → success
            return err_cls(*args, **kwargs) if call_count == 1 else ok_cls(*args, **kwargs)

        with patch("backend.openrouter.httpx.AsyncClient", side_effect=client_factory):
            result = await query_model(
                "openai/gpt-5.5",
                [{"role": "user", "content": "q"}],
                fallbacks=["openai/gpt-4.1"],
            )

        assert result is not None
        assert result["content"] == "fallback answer"
        assert result["model_used"] == "openai/gpt-4.1"

    async def test_402_without_fallback_returns_none(self) -> None:
        """Primary returns 402 with no fallbacks configured → None."""
        err_cls = self._make_http_mock_raising(self._make_402_error())

        with patch("backend.openrouter.httpx.AsyncClient", err_cls):
            result = await query_model(
                "openai/gpt-5.5",
                [{"role": "user", "content": "q"}],
                fallbacks=None,
            )

        assert result is None

    async def test_402_cascades_through_all_fallbacks(self) -> None:
        """Every attempt returns 402 (credit exhaustion) → final result is None."""
        err_cls = self._make_http_mock_raising(self._make_402_error())

        with patch("backend.openrouter.httpx.AsyncClient", err_cls):
            result = await query_model(
                "openai/gpt-5.5",
                [{"role": "user", "content": "q"}],
                fallbacks=["openai/gpt-4.1", "anthropic/claude-3-5-haiku"],
            )

        assert result is None


class TestQueryModelTransportFallback:
    """Verify client-side fallback fires on connection-level errors.

    'Server disconnected without sending a response' is an
    httpx.RemoteProtocolError, a subclass of httpx.TransportError.
    OpenRouter's server-side models[] array failover cannot fire because
    the HTTP round-trip never completed — so we must retry client-side.
    """

    def _make_transport_mock_raising(self, exc: Exception):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=exc)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        return MagicMock(return_value=mock_cm)

    async def test_transport_error_with_fallback_retries_client_side(self) -> None:
        """RemoteProtocolError on primary → client retries with fallback."""
        disconnect = httpx.RemoteProtocolError("Server disconnected without sending a response")
        err_cls = self._make_transport_mock_raising(disconnect)
        ok_cls, _ = _make_http_mock(content="fallback ok", model_slug="openai/gpt-4.1")

        call_count = 0

        def client_factory(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return err_cls(*args, **kwargs) if call_count == 1 else ok_cls(*args, **kwargs)

        with patch("backend.openrouter.httpx.AsyncClient", side_effect=client_factory):
            result = await query_model(
                "anthropic/claude-opus-4.6",
                [{"role": "user", "content": "q"}],
                fallbacks=["openai/gpt-4.1"],
            )

        assert result is not None
        assert result["content"] == "fallback ok"
        assert result["model_used"] == "openai/gpt-4.1"

    async def test_transport_error_without_fallback_returns_none(self) -> None:
        """Transport error with no fallbacks → None."""
        disconnect = httpx.RemoteProtocolError("Server disconnected without sending a response")
        err_cls = self._make_transport_mock_raising(disconnect)

        with patch("backend.openrouter.httpx.AsyncClient", err_cls):
            result = await query_model(
                "anthropic/claude-opus-4.6",
                [{"role": "user", "content": "q"}],
                fallbacks=None,
            )

        assert result is None


# ── query_models_parallel ─────────────────────────────────────────────────────

class TestQueryModelsParallel:
    """Verify parallel dispatch with per-model fallback routing."""

    async def test_dispatches_fallback_per_model(self) -> None:
        captured_payloads: list[dict] = []

        async def fake_query_model(
            model: str,
            messages: list,
            fallbacks: list | None = None,
            timeout: float = 120.0,
        ) -> dict:
            captured_payloads.append({"model": model, "fallbacks": fallbacks})
            return {"content": "ok", "reasoning_details": None, "model_used": model}

        with patch("backend.openrouter.query_model", side_effect=fake_query_model):
            await query_models_parallel(
                ["openai/gpt-5.5", "x-ai/grok-4"],
                [{"role": "user", "content": "q"}],
                fallbacks={"openai/gpt-5.5": "openai/gpt-4.1", "x-ai/grok-4": "x-ai/grok-4-fast"},
            )

        assert captured_payloads[0] == {"model": "openai/gpt-5.5", "fallbacks": ["openai/gpt-4.1"]}
        assert captured_payloads[1] == {"model": "x-ai/grok-4", "fallbacks": ["x-ai/grok-4-fast"]}

    async def test_no_fallback_when_key_absent_from_dict(self) -> None:
        captured: list[dict] = []

        async def fake_query_model(
            model: str,
            messages: list,
            fallbacks: list | None = None,
            timeout: float = 120.0,
        ) -> dict:
            captured.append({"model": model, "fallbacks": fallbacks})
            return {"content": "ok", "reasoning_details": None, "model_used": model}

        with patch("backend.openrouter.query_model", side_effect=fake_query_model):
            await query_models_parallel(
                ["openai/gpt-5.5"],
                [{"role": "user", "content": "q"}],
                fallbacks={},  # empty — no fallback for this model
            )

        assert captured[0]["fallbacks"] is None

    async def test_result_keyed_by_primary_slug(self) -> None:
        async def fake_query_model(
            model: str,
            messages: list,
            fallbacks: list | None = None,
            timeout: float = 120.0,
        ) -> dict:
            # Simulate fallback firing: model_used differs from primary
            return {"content": "ok", "reasoning_details": None, "model_used": "openai/gpt-4.1"}

        with patch("backend.openrouter.query_model", side_effect=fake_query_model):
            result = await query_models_parallel(
                ["openai/gpt-5.5"],
                [{"role": "user", "content": "q"}],
                fallbacks={"openai/gpt-5.5": "openai/gpt-4.1"},
            )

        # Key must be the original primary slug, not the fallback
        assert "openai/gpt-5.5" in result
        assert result["openai/gpt-5.5"]["model_used"] == "openai/gpt-4.1"

    async def test_backward_compat_no_fallbacks_arg(self) -> None:
        """Calling without fallbacks kwarg must not error (old call sites)."""
        async def fake_query_model(
            model: str,
            messages: list,
            fallbacks: list | None = None,
            timeout: float = 120.0,
        ) -> dict:
            return {"content": "ok", "reasoning_details": None, "model_used": model}

        with patch("backend.openrouter.query_model", side_effect=fake_query_model):
            result = await query_models_parallel(
                ["openai/gpt-4.1"],
                [{"role": "user", "content": "q"}],
                # no fallbacks kwarg
            )

        assert "openai/gpt-4.1" in result


# ── council stage1 integration ────────────────────────────────────────────────

class TestStage1FallbackRecording:
    """stage1_collect_responses should record model_used and fallback_from."""

    async def test_records_model_used_in_result(self) -> None:
        from backend.council import stage1_collect_responses

        mock_responses = {
            "openai/gpt-5.5": {
                "content": "answer",
                "reasoning_details": None,
                "model_used": "openai/gpt-5.5",  # primary answered
            }
        }
        with patch("backend.council.COUNCIL_MODELS", ["openai/gpt-5.5"]):
            with patch("backend.council.query_models_parallel", _make_parallel_mock(mock_responses)):
                results = await stage1_collect_responses("What is X?")

        assert len(results) == 1
        assert results[0]["model"] == "openai/gpt-5.5"
        assert results[0]["response"] == "answer"

    async def test_fallback_from_set_when_fallback_fired(self) -> None:
        from backend.council import stage1_collect_responses

        mock_responses = {
            "openai/gpt-5.5": {
                "content": "fallback answer",
                "reasoning_details": None,
                "model_used": "openai/gpt-4.1",  # fallback answered
            }
        }
        with patch("backend.council.COUNCIL_MODELS", ["openai/gpt-5.5"]):
            with patch("backend.council.query_models_parallel", _make_parallel_mock(mock_responses)):
                results = await stage1_collect_responses("What is X?")

        assert results[0]["model"] == "openai/gpt-4.1"
        assert results[0]["fallback_from"] == "openai/gpt-5.5"

    async def test_no_fallback_from_on_primary_success(self) -> None:
        from backend.council import stage1_collect_responses

        mock_responses = {
            "openai/gpt-5.5": {
                "content": "primary answer",
                "reasoning_details": None,
                "model_used": "openai/gpt-5.5",
            }
        }
        with patch("backend.council.COUNCIL_MODELS", ["openai/gpt-5.5"]):
            with patch("backend.council.query_models_parallel", _make_parallel_mock(mock_responses)):
                results = await stage1_collect_responses("What is X?")

        assert "fallback_from" not in results[0]


# ── council stage3 — chairman fallback ───────────────────────────────────────

class TestChairmanFallback:
    """stage3_synthesize_final should pass CHAIRMAN_FALLBACK to query_model."""

    async def test_chairman_called_with_chairman_fallback(self) -> None:
        from backend.council import stage3_synthesize_final

        mock_qm = AsyncMock(return_value={
            "content": "synthesis",
            "reasoning_details": None,
            "model_used": "anthropic/claude-opus-4.6",
        })

        with patch("backend.council.query_model", mock_qm):
            await stage3_synthesize_final(
                "q",
                [{"model": "openai/gpt-5.5", "response": "r1"}],
                [{"model": "openai/gpt-5.5", "ranking": "FINAL RANKING:\n1. Response A", "parsed_ranking": ["Response A"]}],
            )

        _, kwargs = mock_qm.call_args
        assert kwargs.get("fallbacks") == [CHAIRMAN_FALLBACK]

    async def test_chairman_fallback_from_in_result_when_fell_back(self) -> None:
        from backend.council import stage3_synthesize_final

        # model_used differs from CHAIRMAN_MODEL → fallback fired
        mock_qm = AsyncMock(return_value={
            "content": "fallback synthesis",
            "reasoning_details": None,
            "model_used": "openai/gpt-4.1",  # fallback answered
        })

        with patch("backend.council.query_model", mock_qm):
            result = await stage3_synthesize_final(
                "q",
                [{"model": "openai/gpt-5.5", "response": "r1"}],
                [{"model": "openai/gpt-5.5", "ranking": "FINAL RANKING:\n1. Response A", "parsed_ranking": ["Response A"]}],
            )

        assert result["model"] == "openai/gpt-4.1"
        assert result["fallback_from"] == "anthropic/claude-opus-4.6"
        assert result["response"] == "fallback synthesis"
