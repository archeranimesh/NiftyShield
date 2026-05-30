"""Unit tests for src/config.py Settings model.

All tests are offline — no network, no .env file dependency.
Environment variables are injected via monkeypatch.
"""

import pytest
from pydantic import ValidationError

from src.config import Settings


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
