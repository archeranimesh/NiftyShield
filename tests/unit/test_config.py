"""Unit tests for src/config.py Settings model.

All tests are offline — no network, no .env file dependency.
Environment variables are injected via monkeypatch.
"""

import pytest
from pydantic import ValidationError

from src.config import Settings, _DynamicSettings


def test_defaults_with_no_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """All optional fields are None; required defaults are correct."""
    # Ensure nothing leaks from the calling shell environment.
    for key in [
        "UPSTOX_ENV",
        "UPSTOX_ANALYTICS_TOKEN",
        "UPSTOX_ACCESS_TOKEN",
        "UPSTOX_SANDBOX_TOKEN",
        "UPSTOX_DEBUG",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "DHAN_CLIENT_ID",
        "DHAN_ACCESS_TOKEN",
        "NUVAMA_SETTINGS_FILE",
    ]:
        monkeypatch.delenv(key, raising=False)

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.upstox_env == "test"
    assert s.upstox_analytics_token is None
    assert s.upstox_access_token is None
    assert s.upstox_debug is False
    assert s.telegram_bot_token is None
    assert s.telegram_chat_id is None
    assert s.telegram_message_budget == 10
    assert s.dhan_client_id is None
    assert s.dhan_access_token is None
    assert s.nuvama_settings_file == "data/nuvama/settings.json"
    assert s.vix_data_dir == "data/historical/ohlc/india_vix"
    assert s.db_path == "data/portfolio/portfolio.sqlite"
    assert s.log_level == "INFO"


def test_upstox_env_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """UPSTOX_ENV=prod is accepted and stored correctly."""
    monkeypatch.setenv("UPSTOX_ENV", "prod")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.upstox_env == "prod"


def test_invalid_upstox_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unrecognised UPSTOX_ENV value raises ValidationError."""
    monkeypatch.setenv("UPSTOX_ENV", "live")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


# ── _DynamicSettings cache invalidation (BUG-011) ──────────────────


def test_dynamic_settings_rebuilds_on_real_env_change(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity check: changing os.environ between accesses picks up the new value."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    dynamic = _DynamicSettings()
    assert dynamic.telegram_bot_token is None

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "real-token")
    assert dynamic.telegram_bot_token == "real-token"

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert dynamic.telegram_bot_token is None


def test_dynamic_settings_correctness_independent_of_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache-invalidation no longer depends on ``hash()`` at all.

    The old cache-validity check compared ``hash(frozenset(os.environ.items()))``
    across accesses. Hash equality does not imply content equality — two
    different ``os.environ`` snapshots can coincidentally hash to the same
    int, which would let a stale ``Settings`` instance survive a real env
    change undetected. The fix compares the actual environ dict instead.

    This test doesn't reproduce a real hash collision (that's not practical
    to force deterministically) — it monkeypatches ``hash`` inside
    ``src.config`` to a constant to prove the fixed code path no longer calls
    ``hash()`` as part of its cache-validity check at all, so a collision in
    that function literally cannot affect it anymore.
    """
    import src.config as config_module

    monkeypatch.setattr(config_module, "hash", lambda _obj: 42, raising=False)

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    dynamic = _DynamicSettings()
    assert dynamic.telegram_bot_token is None

    # Different os.environ content, but under the old hash-only check this
    # would collide with the previous state (both forced to hash 42) and
    # wrongly reuse the cached Settings built with no token set.
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "leaked-token")
    assert dynamic.telegram_bot_token == "leaked-token"
