"""Centralised application settings via pydantic-settings.

All environment variables used anywhere in src/ or scripts/ are declared here.
Import ``settings`` singleton — never call ``os.getenv()`` directly.

Usage::

    from src.config import settings

    token = settings.upstox_analytics_token
"""

from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from environment / .env file.

    All fields are optional (None by default) so the codebase continues to
    start in test mode without any credentials configured.  Callers that
    require a specific credential must guard against None themselves.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Extra env vars that are not declared here are silently ignored.
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Upstox
    # ------------------------------------------------------------------
    upstox_env: str = Field(
        default="test",
        pattern="^(prod|sandbox|test)$",
        description="Broker environment — selects client implementation.",
    )
    upstox_analytics_token: str | None = Field(
        default=None,
        description="Long-lived Analytics Token for market data.",
    )
    upstox_access_token: str | None = Field(
        default=None,
        description="Daily OAuth access token.",
    )
    upstox_sandbox_token: str | None = Field(
        default=None,
        description="Sandbox access token (opt-in tests only).",
    )
    upstox_api_key: str | None = Field(
        default=None,
        description="OAuth app key (used in login flow).",
    )
    upstox_api_secret: str | None = Field(
        default=None,
        description="OAuth app secret (used in login flow).",
    )
    upstox_redirect_uri: str | None = Field(
        default=None,
        description="OAuth redirect URI.",
    )
    upstox_debug: bool = Field(
        default=False,
        description="Set UPSTOX_DEBUG=1 for verbose request/response logging.",
    )

    # ------------------------------------------------------------------
    # Telegram
    # ------------------------------------------------------------------
    telegram_bot_token: str | None = Field(
        default=None,
        description="Telegram bot token for cron notifications.",
    )
    telegram_chat_id: str | None = Field(
        default=None,
        description="Telegram chat ID for notifications.",
    )
    telegram_message_budget: int = Field(
        default=10,
        description="Max Telegram messages per cron run before suppression.",
    )

    @field_validator("telegram_message_budget", mode="before")
    @classmethod
    def validate_telegram_message_budget(cls, v):
        try:
            return int(v)
        except (ValueError, TypeError):
            return 10

    # ------------------------------------------------------------------
    # Nuvama
    # ------------------------------------------------------------------
    nuvama_api_key: str | None = Field(
        default=None,
        description="Nuvama APIConnect key.",
    )
    nuvama_api_secret: str | None = Field(
        default=None,
        description="Nuvama APIConnect secret.",
    )
    nuvama_settings_file: str = Field(
        default="data/nuvama/settings.json",
        description="Path to Nuvama APIConnect session file.",
    )

    # ------------------------------------------------------------------
    # Dhan
    # ------------------------------------------------------------------
    dhan_client_id: str | None = Field(
        default=None,
        description="Dhan broker client ID.",
    )
    dhan_access_token: str | None = Field(
        default=None,
        description="Dhan broker access token.",
    )

    # ------------------------------------------------------------------
    # Data paths
    # ------------------------------------------------------------------
    db_path: str = Field(
        default="data/portfolio/portfolio.sqlite",
        description="Path to the shared SQLite database.",
    )
    vix_data_dir: str = Field(
        default="data/historical/ohlc/india_vix",
        description="Directory containing India VIX Parquet files.",
    )
    chain_snapshot_dir: str = Field(
        default="data/historical/option_chain/eod",
        description="Base directory for EOD option chain Parquet snapshots.",
    )
    chain_intraday_dir: str = Field(
        default="data/historical/option_chain/intraday",
        description="Base directory for intraday option chain Parquet snapshots.",
    )
    bod_instruments_path: str = Field(
        default="data/instruments/NSE.json",
        description="Path to the Beginning-of-Day instrument JSON from Upstox.",
    )

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    log_level: str = Field(
        default="INFO",
        description="Root log level (DEBUG / INFO / WARNING / ERROR).",
    )
    nse_cookie: str | None = Field(
        default=None,
        description="Akamai bypass cookie required for NSE bhavcopy downloads.",
    )


# ---------------------------------------------------------------------------
# Module-level singleton — ``from src.config import settings``
# ---------------------------------------------------------------------------
class _DynamicSettings:
    """A wrapper around Settings that automatically re-instantiates it if os.environ changes.

    This ensures that mock environments in unit tests and dynamic dotenv loading
    in scripts/ are transparently supported without stale cached values.
    """

    _cached_settings: Settings | None
    _environ_hash: int | None

    def __init__(self) -> None:
        self._cached_settings = None
        self._environ_hash = None

    def _get_settings(self) -> Settings:
        import os
        import sys

        # frozenset of os.environ is stable and hashable since all keys/values are strings.
        current_hash = hash(frozenset(os.environ.items()))
        if self._cached_settings is None or self._environ_hash != current_hash:
            kwargs: dict[str, Any] = {}
            if os.environ.get("UPSTOX_ENV", "test") == "test" or "pytest" in sys.modules:
                kwargs["_env_file"] = None
            self._cached_settings = Settings(**kwargs)
            self._environ_hash = current_hash
        assert self._cached_settings is not None
        return self._cached_settings

    def __getattr__(self, name: str):
        return getattr(self._get_settings(), name)

    def __dir__(self) -> list[str]:
        return dir(self._get_settings())

    def __repr__(self) -> str:
        return repr(self._get_settings())


settings: Any = _DynamicSettings()
