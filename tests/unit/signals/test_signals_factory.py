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


def test_unknown_provider_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        providers = build_providers(
            {**_OPENROUTER, "SIGNAL_PROVIDERS": "gpt4o,bogus"},
        )
    assert [p.provider_name for p in providers] == ["gpt4o"]
    assert "signal_provider_unknown" in caplog.text
