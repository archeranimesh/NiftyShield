"""Composition root for signal providers.

``build_providers`` is the sole place where concrete provider classes are
instantiated. Everything downstream depends only on the
:class:`~src.signals.protocol.SignalProvider` contract.
"""

from __future__ import annotations

import os

import structlog

from .aggregator import SignalAggregator
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
        SIGNAL_MODEL_GROK / SIGNAL_MODEL_GPT4O / SIGNAL_MODEL_GEMINI: optional
            per-provider OpenRouter model-slug overrides; each defaults to that
            provider's built-in constant.
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
        providers.append(_construct(name, openrouter_key, env))

    unknown = requested - set(_KNOWN_PROVIDERS)
    for name in sorted(unknown):
        logger.warning("signal_provider_unknown", provider=name)

    if not providers:
        logger.warning("signal_providers_empty", fallback="mock")
        return [MockSignalProvider()]

    return providers


_MODEL_ENV_VAR = {
    "grok": "SIGNAL_MODEL_GROK",
    "gpt4o": "SIGNAL_MODEL_GPT4O",
    "gemini": "SIGNAL_MODEL_GEMINI",
}


def _construct(name: str, openrouter_key: str, env: dict) -> SignalProvider:
    """Instantiate one Phase 1 provider by name.

    Reads ``SIGNAL_MODEL_<NAME>`` from ``env`` for an optional slug override;
    an empty or missing value leaves the provider on its built-in default.
    """
    model = env.get(_MODEL_ENV_VAR[name], "").strip() or None
    if name == "gpt4o":
        kwargs = {"model": model} if model else {}
        return GPT4oSignalProvider(api_key=openrouter_key, **kwargs)
    if name == "grok":
        return GrokSignalProvider(api_key=openrouter_key, use_openrouter=True, model=model)
    if name == "gemini":
        return GeminiSignalProvider(api_key=openrouter_key, use_openrouter=True, model=model)
    raise ValueError(f"Unknown provider: {name}")


def _int_env(env: dict, key: str, default: int) -> int:
    """Read a positive int from ``env``.

    Falls back to ``default`` on a blank, non-integer, or sub-1 value.
    """
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("signal_env_not_int", key=key, value=raw, fallback=default)
        return default
    if value < 1:
        logger.warning("signal_env_out_of_range", key=key, value=value, fallback=default)
        return default
    return value


def build_aggregator(env: dict | None = None) -> SignalAggregator:
    """Build the consensus aggregator from environment variables.

    Args:
        env: Environment mapping. Defaults to ``os.environ``; pass a dict in
            tests to avoid touching real env vars.

    Reads:
        SIGNAL_MIN_CONFIDENCE: mean confidence of agreeing models required for
            a directional trade (default 3).
        SIGNAL_CONSENSUS_REQUIRED: number of validated models that must agree
            on a direction (default 2).

    Blank, non-integer, or sub-1 values fall back to the default with a warning.
    """
    env = os.environ if env is None else env
    return SignalAggregator(
        min_confidence=_int_env(env, "SIGNAL_MIN_CONFIDENCE", 3),
        consensus_required=_int_env(env, "SIGNAL_CONSENSUS_REQUIRED", 2),
    )
