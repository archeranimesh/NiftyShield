"""Composition root for signal providers.

``build_providers`` is the sole place where concrete provider classes are
instantiated. Everything downstream depends only on the
:class:`~src.signals.protocol.SignalProvider` contract.
"""

from __future__ import annotations

import os

import structlog

from .protocol import SignalProvider
from .providers.gemini import GeminiSignalProvider
from .providers.gpt4o import GPT4oSignalProvider
from .providers.grok import GrokSignalProvider
from .providers.mock import MockSignalProvider

logger = structlog.stdlib.get_logger(__name__)

# Canonical order — returned list follows this, not env var order.
_KNOWN_PROVIDERS = ("grok", "gpt4o", "gemini")
_DEFAULT_PROVIDERS = "gpt4o"


def build_providers(env: dict | None = None) -> list[SignalProvider]:
    """Build the active provider list from environment variables.

    Phase 1 POC: every provider routes through a single ``OPENROUTER_API_KEY``.

    Args:
        env: Environment mapping. Defaults to ``os.environ``; pass a dict in
            tests to avoid touching real env vars.

    Returns:
        Active providers in canonical order. Returns ``[MockSignalProvider()]``
        when ``UPSTOX_ENV=test`` or when no real provider could be configured.

    Reads:
        SIGNAL_PROVIDERS: comma-separated subset of ``"grok,gpt4o,gemini"``
            (default ``"gpt4o"``).
        OPENROUTER_API_KEY: required for every Phase 1 provider.
        UPSTOX_ENV: ``"test"`` short-circuits to ``[MockSignalProvider()]``.
    """
    env = os.environ if env is None else env

    if env.get("UPSTOX_ENV") == "test":
        return [MockSignalProvider()]

    requested = {
        name.strip().lower()
        for name in env.get("SIGNAL_PROVIDERS", _DEFAULT_PROVIDERS).split(",")
        if name.strip()
    }
    openrouter_key = env.get("OPENROUTER_API_KEY", "").strip()

    providers: list[SignalProvider] = []
    for name in _KNOWN_PROVIDERS:
        if name not in requested:
            continue
        if not openrouter_key:
            logger.warning(
                "signal_provider_skipped",
                provider=name,
                reason="OPENROUTER_API_KEY missing",
            )
            continue
        providers.append(_construct(name, openrouter_key))

    unknown = requested - set(_KNOWN_PROVIDERS)
    for name in sorted(unknown):
        logger.warning("signal_provider_unknown", provider=name)

    if not providers:
        logger.warning("signal_providers_empty", fallback="mock")
        return [MockSignalProvider()]

    return providers


def _construct(name: str, openrouter_key: str) -> SignalProvider:
    """Instantiate one Phase 1 provider by name."""
    if name == "gpt4o":
        return GPT4oSignalProvider(api_key=openrouter_key)
    if name == "grok":
        return GrokSignalProvider(api_key=openrouter_key, use_openrouter=True)
    if name == "gemini":
        return GeminiSignalProvider(api_key=openrouter_key, use_openrouter=True)
    raise ValueError(f"Unknown provider: {name}")
