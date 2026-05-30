"""Centralised application settings via pydantic-settings.

All environment variables used anywhere in src/ or scripts/ are declared here.
Import ``settings`` singleton — never call ``os.getenv()`` directly.

Usage::

    from src.config import settings

    token = settings.upstox_analytics_token
"""

from pydantic import Field
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
settings = Settings()
