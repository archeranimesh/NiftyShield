"""Data models for portfolio strategy tracking.

Covers strategy definitions, individual legs, and daily price/greeks snapshots.
All timestamps are UTC internally; IST conversion happens at display layer only.

Monetary fields (entry_price, ltp, close, underlying_price) use Decimal to
preserve sub-rupee precision through P&L calculations and SQLite round-trips.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, computed_field, field_validator


class TradeAction(str, Enum):
    """Direction of a physical trade execution — BUY or SELL."""

    BUY = "BUY"
    SELL = "SELL"


class Trade(BaseModel):
    """A single physical trade execution — one row in the trades ledger.

    Immutable after construction (frozen=True). Monetary fields use Decimal
    stored as TEXT in SQLite, same convention as Leg.entry_price and MFTransaction.

    Attributes:
        strategy_name: Strategy this trade belongs to, e.g. "ILTS" or "FinRakshak".
        leg_role: Human label identifying the position, e.g. "EBBETF0431".
        instrument_key: Upstox instrument key, e.g. "NSE_EQ|INF754K01LE1".
        trade_date: Actual execution date.
        action: BUY or SELL.
        quantity: Units transacted. Always positive — direction is in action.
        price: Execution price per unit. Always positive.
        notes: Optional free-text annotation (contract note ref, reason, etc.).
    """

    strategy_name: str = Field(..., min_length=1)
    leg_role: str = Field(..., min_length=1)
    instrument_key: str = Field(..., min_length=1)
    trade_date: date
    action: TradeAction
    quantity: int = Field(..., gt=0)
    price: Decimal = Field(..., gt=0)
    notes: str = ""

    model_config = {"frozen": True}

    @field_validator("price", mode="before")
    @classmethod
    def price_must_be_positive(cls, v: object) -> object:
        """Coerce str/float inputs and guard against zero/negative values."""
        if isinstance(v, float):
            v = Decimal(str(v))
        return v


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ProductType(str, Enum):
    CNC = "CNC"
    NRML = "NRML"
    MIS = "MIS"


class AssetType(str, Enum):
    EQUITY = "EQUITY"
    CE = "CE"
    PE = "PE"
    FUTURES = "FUTURES"


class Leg(BaseModel):
    """A single leg of a multi-leg strategy."""

    id: int | None = None
    strategy_id: int | None = None
    instrument_key: str = Field(description="Upstox instrument key for API lookups")
    display_name: str = Field(description="Human-readable name, e.g. 'NIFTY DEC 23000 PE'")
    asset_type: AssetType
    direction: Direction
    quantity: int
    lot_size: int = Field(default=1, description="Lot size — 1 for ETFs, 75 for Nifty options")
    entry_price: Decimal
    entry_date: date
    expiry: date | None = Field(default=None, description="Expiry date for F&O legs, None for equity")
    strike: float | None = Field(default=None, description="Strike price for options")
    product_type: ProductType

    @computed_field
    @property
    def total_lots(self) -> int:
        """Number of lots (quantity / lot_size)."""
        return self.quantity // self.lot_size if self.lot_size > 0 else self.quantity

    @computed_field
    @property
    def entry_value(self) -> Decimal:
        """Total capital deployed at entry."""
        return self.entry_price * self.quantity

    def pnl(self, current_price: float | Decimal) -> Decimal:
        """Compute unrealized P&L for this leg at a given price.

        Accepts float (from broker API) or Decimal. Float inputs are
        converted via str() to avoid binary representation errors.

        For BUY legs:  (current - entry) * quantity
        For SELL legs: (entry - current) * quantity
        """
        cp = current_price if isinstance(current_price, Decimal) else Decimal(str(current_price))
        if self.direction == Direction.BUY:
            return (cp - self.entry_price) * self.quantity
        return (self.entry_price - cp) * self.quantity

    def pnl_percent(self, current_price: float | Decimal) -> Decimal:
        """P&L as percentage of entry value."""
        if self.entry_value == 0:
            return Decimal("0")
        return (self.pnl(current_price) / abs(self.entry_value)) * 100


class Strategy(BaseModel):
    """A named strategy comprising one or more legs."""

    id: int | None = None
    name: str
    description: str = ""
    legs: list[Leg] = Field(default_factory=list)
    created_at: datetime | None = None

    @computed_field
    @property
    def total_entry_value(self) -> Decimal:
        """Net capital deployed across all legs (buys positive, sells negative)."""
        total = Decimal("0")
        for leg in self.legs:
            if leg.direction == Direction.BUY:
                total += leg.entry_value
            else:
                total -= leg.entry_value
        return total

    def total_pnl(self, prices: dict[int, float | Decimal]) -> Decimal:
        """Compute strategy-level P&L given current prices keyed by leg ID.

        Args:
            prices: Mapping of leg.id -> current LTP (float or Decimal).
        """
        return sum(
            (leg.pnl(prices[leg.id])
             for leg in self.legs
             if leg.id is not None and leg.id in prices),
            Decimal("0"),
        )


class DailySnapshot(BaseModel):
    """A single day's closing data for one leg."""

    id: int | None = None
    leg_id: int
    snapshot_date: date
    ltp: Decimal
    close: Decimal | None = None
    iv: float | None = Field(default=None, description="Implied volatility")
    delta: float | None = None
    theta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    oi: int | None = Field(default=None, description="Open interest")
    volume: int | None = None
    underlying_price: Decimal | None = Field(
        default=None, description="Nifty spot at snapshot time"
    )

    def leg_pnl(self, entry_price: Decimal, quantity: int, direction: Direction) -> Decimal:
        """Compute P&L using this snapshot's LTP."""
        if direction == Direction.BUY:
            return (self.ltp - entry_price) * quantity
        return (entry_price - self.ltp) * quantity


@dataclass(frozen=True)
class PortfolioSummary:
    """Combined portfolio value snapshot across MF, ETF, and options.

    Computed once per snapshot run and consumed by both the formatted output
    path and the upcoming visualization layer.  All monetary fields are
    Decimal.  Day-change fields are None on the first ever run when no
    prior-day snapshot exists.
    """

    snapshot_date: date

    # MF component — zeroed when mf_available is False (fetch failed)
    mf_value: Decimal
    mf_invested: Decimal
    mf_pnl: Decimal
    mf_pnl_pct: Decimal | None  # None when MF fetch failed
    mf_available: bool

    # ETF component
    etf_value: Decimal
    etf_basis: Decimal

    # Options net P&L (sign-corrected for short legs)
    options_pnl: Decimal

    # Combined totals
    total_value: Decimal
    total_invested: Decimal
    total_pnl: Decimal
    total_pnl_pct: Decimal  # quantized to 2 dp

    # Day-change deltas — None when prior-day data is unavailable
    mf_day_delta: Decimal | None = None
    etf_day_delta: Decimal | None = None
    options_day_delta: Decimal | None = None
    total_day_delta: Decimal | None = None

    # FinRakshak-specific day delta — isolated from combined options_day_delta
    # Enables hedge effectiveness reporting: MF Δday + FinRakshak Δday = net protection
    finrakshak_day_delta: Decimal | None = None

    # Dhan equity component (defaults to 0 when Dhan unavailable)
    dhan_equity_value: Decimal = Decimal("0")
    dhan_equity_basis: Decimal = Decimal("0")
    dhan_equity_pnl: Decimal = Decimal("0")
    dhan_equity_pnl_pct: Decimal | None = None
    dhan_equity_day_delta: Decimal | None = None

    # Dhan bond component
    dhan_bond_value: Decimal = Decimal("0")
    dhan_bond_basis: Decimal = Decimal("0")
    dhan_bond_pnl: Decimal = Decimal("0")
    dhan_bond_pnl_pct: Decimal | None = None
    dhan_bond_day_delta: Decimal | None = None

    # Whether Dhan data was available this run
    dhan_available: bool = False

    # Nuvama bond component (defaults to 0 when Nuvama unavailable)
    # Cost basis from seeded nuvama_positions table; LTP inline from Holdings().
    nuvama_bond_value: Decimal = Decimal("0")
    nuvama_bond_basis: Decimal = Decimal("0")
    nuvama_bond_pnl: Decimal = Decimal("0")
    nuvama_bond_pnl_pct: Decimal | None = None
    nuvama_bond_day_delta: Decimal | None = None

    # Whether Nuvama data was available this run
    nuvama_available: bool = False
