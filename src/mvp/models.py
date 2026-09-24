from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class ProviderSource(str, Enum):
    """Source type for the pick provider."""

    TV = "TV"
    TELEGRAM = "TELEGRAM"
    YOUTUBE = "YOUTUBE"
    OTHER = "OTHER"


class PickStatus(str, Enum):
    """Lifecycle status of a pick."""

    PENDING = "PENDING"
    OPEN = "OPEN"
    TARGET_HIT = "TARGET_HIT"
    SL_HIT = "SL_HIT"
    MANUAL_CLOSE = "MANUAL_CLOSE"


class Provider(BaseModel):
    """A tipster or provider of value picks."""

    model_config = ConfigDict(frozen=True)

    provider_id: str
    slug: str
    display_name: str
    source_type: ProviderSource
    notes: str | None = None
    created_at: str


class Category(BaseModel):
    """A thematic category of picks under a specific provider."""

    model_config = ConfigDict(frozen=True)

    category_id: str
    provider_id: str
    slug: str
    display_name: str
    notes: str | None = None
    created_at: str


class Pick(BaseModel):
    """
    MVP Multi-bagger Value Pick.

    Note: Dividends are out of scope for this model.
    """

    model_config = ConfigDict(frozen=True)

    pick_id: str
    category_id: str | None = None
    symbol: str
    instrument_key: str | None = None
    analyst: str | None = None
    entry_price: Decimal | None = None
    reco_price: Decimal | None = None
    pick_date: str
    target_price: Decimal | None = None
    stop_loss: Decimal | None = None
    notes: str | None = None
    status: PickStatus = PickStatus.PENDING
    closed_at: str | None = None
    close_price: Decimal | None = None
    capital_allotted: Decimal = Decimal("100000")
    tranche_step_pct: Decimal = Decimal("6")
    max_drawdown_pct: Decimal = Decimal("30")
    deployed_capital: Decimal = Decimal("0")
    total_qty: int = 0
    avg_cost: Decimal | None = None
    idle_cash: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    benchmark_entry: Decimal | None = None
    created_at: str
    updated_at: str

    @field_validator(
        "entry_price",
        "reco_price",
        "target_price",
        "stop_loss",
        "close_price",
        "capital_allotted",
        "tranche_step_pct",
        "max_drawdown_pct",
        "deployed_capital",
        "avg_cost",
        "idle_cash",
        "realized_pnl",
        "benchmark_entry",
        mode="before",
    )
    @classmethod
    def _parse_decimal(cls, v: Any) -> Decimal | None:
        if v is None:
            return None
        return Decimal(str(v))


class MVPTranche(BaseModel):
    """An execution tranche for a pick."""

    model_config = ConfigDict(frozen=True)

    tranche_id: str
    pick_id: str
    tranche_index: int
    trigger_pct: Decimal
    fill_price: Decimal | None = None
    qty: int | None = None
    cost_bps: Decimal = Decimal("25")
    filled_at: str | None = None

    @field_validator("trigger_pct", "fill_price", "cost_bps", mode="before")
    @classmethod
    def _parse_decimal(cls, v: Any) -> Decimal | None:
        if v is None:
            return None
        return Decimal(str(v))


class MVPSnapshot(BaseModel):
    """Intraday or EOD price snapshot for a pick."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: int | None = None
    pick_id: str
    ltp: Decimal
    captured_at: str
    benchmark_close: Decimal | None = None

    @field_validator("ltp", "benchmark_close", mode="before")
    @classmethod
    def _parse_decimal(cls, v: Any) -> Decimal | None:
        if v is None:
            return None
        return Decimal(str(v))


class ClosePickResult(BaseModel):
    """Values computed by ``MVPStore.close_pick``, returned to the caller so
    it need not re-read the pick row to render a close alert."""

    model_config = ConfigDict(frozen=True)

    realized_pnl: Decimal
    total_qty: int
    deployed_capital: Decimal
    avg_cost: Decimal | None


class CategoryStats(BaseModel):
    """Win-rate / inception P&L stats over a category's picks.

    ``inception_pnl`` sums ``realized_pnl`` across all closed picks in the
    category. ``invested``/``current`` are the mark-to-market sum over the
    category's OPEN picks only (zero when no ``ltp_map`` was supplied or no
    picks are open). ``inception_pct`` is the combined realized + unrealized
    return since the category's first pick, relative to total capital ever
    deployed in the category (``None`` when nothing has been deployed yet).
    """

    model_config = ConfigDict(frozen=True)

    closed_count: int
    wins: int
    losses: int
    win_rate: Decimal | None
    avg_win: Decimal
    avg_loss: Decimal
    inception_pnl: Decimal
    invested: Decimal = Decimal("0")
    current: Decimal = Decimal("0")
    inception_pct: Decimal | None = None
