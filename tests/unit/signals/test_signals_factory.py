"""Tests for src.signals.factory.build_providers."""

from __future__ import annotations

import logging

import pytest

from src.signals.factory import build_providers
from src.signals.providers.mock import MockSignalProvider

_OPENROUTER = {"OPENROUTER_API_KEY": "or-key"}  # pragma: allowlist secret


def test_test_env_returns_mock_only() -> None:
    providers = build_providers(
        {"UPSTOX_ENV": "test", "SIGNAL_PROVIDERS": "grok,gpt4o"},
    )
    assert len(providers) == 1
    assert isinstance(providers[0], MockSignalProvider)


def test_single_provider_configured() -> None:
    providers = build_providers({**_OPENROUTER, "SIGNAL_PROVIDERS": "gpt4o"})
    assert [p.provider_name for p in providers] == ["gpt4o"]


def test_default_is_gpt4o() -> None:
    providers = build_providers(dict(_OPENROUTER))
    assert [p.provider_name for p in providers] == ["gpt4o"]


def test_missing_key_skips_provider_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        providers = build_providers({"SIGNAL_PROVIDERS": "gpt4o"})
    assert len(providers) == 1
    assert isinstance(providers[0], MockSignalProvider)
    assert "signal_provider_skipped" in caplog.text


def test_empty_result_falls_back_to_mock(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        providers = build_providers(
            {**_OPENROUTER, "SIGNAL_PROVIDERS": ""},
        )
    assert len(providers) == 1
    assert isinstance(providers[0], MockSignalProvider)
    assert "signal_providers_empty" in caplog.text


def test_all_three_configured_in_canonical_order() -> None:
    providers = build_providers(
        {**_OPENROUTER, "SIGNAL_PROVIDERS": "gpt4o,gemini,grok"},
    )
    assert [p.provider_name for p in providers] == ["grok", "gpt4o", "gemini"]


def test_model_slug_overrides_applied_per_provider() -> None:
    providers = build_providers(
        {
            **_OPENROUTER,
            "SIGNAL_PROVIDERS": "grok,gpt4o,gemini",
            "SIGNAL_MODEL_GROK": "x-ai/grok-4.1-fast",
            "SIGNAL_MODEL_GPT4O": "openai/gpt-4.1",
            "SIGNAL_MODEL_GEMINI": "google/gemini-3.7-flash",
        },
    )
    by_name = {p.provider_name: p for p in providers}
    assert by_name["grok"]._model == "x-ai/grok-4.1-fast"
    assert by_name["gpt4o"]._model == "openai/gpt-4.1"
    assert by_name["gemini"]._model == "google/gemini-3.7-flash"


def test_blank_or_missing_slug_keeps_provider_default() -> None:
    providers = build_providers(
        {
            **_OPENROUTER,
            "SIGNAL_PROVIDERS": "grok,gpt4o,gemini",
            "SIGNAL_MODEL_GROK": "   ",
        },
    )
    by_name = {p.provider_name: p for p in providers}
    assert by_name["grok"]._model == "x-ai/grok-3"
    assert by_name["gpt4o"]._model == "openai/gpt-4o"
    assert by_name["gemini"]._model == "google/gemini-2.0-flash"


def test_unknown_provider_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        providers = build_providers(
            {**_OPENROUTER, "SIGNAL_PROVIDERS": "gpt4o,bogus"},
        )
    assert [p.provider_name for p in providers] == ["gpt4o"]
    assert "signal_provider_unknown" in caplog.text
