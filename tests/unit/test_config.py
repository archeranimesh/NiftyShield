"""Unit tests for src/config.py Settings model.

All tests are offline — no network, no .env file dependency.
Environment variables are injected via monkeypatch.
"""

from pathlib import Path

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
        "MARKET_DATA__CHAIN__SOURCES",
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
    assert s.vix_data_dir == Path("data/historical/ohlc/india_vix")
    assert isinstance(s.vix_data_dir, Path)
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


# ── vix_data_dir Path typing (BUG-026) ──────────────────────────────
#
# vix_data_dir was declared `str`, so `load_vix_series(settings.vix_data_dir)`
# call sites that skipped their own `Path(...)` wrap crashed with
# `AttributeError: 'str' object has no attribute 'glob'` — the three
# --auto-cc/--auto-pp/--auto-collar bootstrap functions in
# paper_3track_overlay_entry.py did exactly this on every cron run. Every
# existing test for those functions mocks `load_vix_series` directly, so
# the wrong type never reached `.glob()` in the suite — these tests close
# that gap at the settings layer.


def test_vix_data_dir_is_path_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """vix_data_dir is a real Path, not str — callers can .glob() it directly."""
    monkeypatch.delenv("VIX_DATA_DIR", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert isinstance(s.vix_data_dir, Path)
    # The exact call BUG-026's crash site made — must not raise AttributeError.
    list(s.vix_data_dir.glob("**/*.parquet"))


def test_vix_data_dir_env_override_coerces_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """A string env var value still coerces cleanly into a Path field."""
    monkeypatch.setenv("VIX_DATA_DIR", "/tmp/custom_vix_dir")
    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.vix_data_dir == Path("/tmp/custom_vix_dir")
    assert isinstance(s.vix_data_dir, Path)


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


# ── market_data routing config (DSC-4) ──────────────────────────────


def _clean_market_data_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "MARKET_DATA__CHAIN__SOURCES",
        "MARKET_DATA__CHAIN__DHAN_MIN_INTERVAL_S",
        "MARKET_DATA__QUOTE__SOURCES",
        "MARKET_DATA__CANDLES__SOURCES",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_market_data_defaults_are_upstox_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression pin: with no env, every capability routes to Upstox alone, 4 s floor."""
    _clean_market_data_env(monkeypatch)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert [x.value for x in s.market_data.chain.sources] == ["upstox"]
    assert [x.value for x in s.market_data.quote.sources] == ["upstox"]
    assert [x.value for x in s.market_data.candles.sources] == ["upstox"]
    assert s.market_data.chain.dhan_min_interval_s == 4.0


def test_market_data_chain_sources_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """The yearly setting parses from a nested env var, order preserved."""
    _clean_market_data_env(monkeypatch)
    monkeypatch.setenv("MARKET_DATA__CHAIN__SOURCES", '["upstox", "dhan"]')
    monkeypatch.setenv("MARKET_DATA__CHAIN__DHAN_MIN_INTERVAL_S", "6")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert [x.value for x in s.market_data.chain.sources] == ["upstox", "dhan"]
    assert s.market_data.chain.dhan_min_interval_s == 6.0


@pytest.mark.parametrize("raw", ['["kite"]', "[]", '["dhan", "dhan"]'])
def test_market_data_invalid_sources_rejected(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    """Unknown, empty and duplicate source lists fail at Settings construction."""
    _clean_market_data_env(monkeypatch)
    monkeypatch.setenv("MARKET_DATA__CHAIN__SOURCES", raw)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_market_data_quote_unknown_source_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Quote and candle entries are validated even though they are not wired yet."""
    _clean_market_data_env(monkeypatch)
    monkeypatch.setenv("MARKET_DATA__QUOTE__SOURCES", '["kite"]')
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_market_data_non_positive_floor_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_market_data_env(monkeypatch)
    monkeypatch.setenv("MARKET_DATA__CHAIN__DHAN_MIN_INTERVAL_S", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
