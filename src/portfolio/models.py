"""Data models for portfolio strategy tracking.

Covers strategy definitions, individual legs, and daily price/greeks snapshots.
All timestamps are UTC internally; IST conversion happens at display layer only.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field


class Direction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class ProductType(StrEnum):
    CNC = "CNC"
    NRML = "NRML"
    MIS = "MIS"


class AssetType(StrEnum):
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
    entry_price: float
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
    def entry_value(self) -> float:
        """Total capital deployed at entry."""
        return self.entry_price * self.quantity

    def pnl(self, current_price: float) -> float:
        """Compute unrealized P&L for this leg at a given price.

        For BUY legs:  (current - entry) * quantity
        For SELL legs: (entry - current) * quantity
        """
        if self.direction == Direction.BUY:
            return (current_price - self.entry_price) * self.quantity
        return (self.entry_price - current_price) * self.quantity

    def pnl_percent(self, current_price: float) -> float:
        """P&L as percentage of entry value."""
        if self.entry_value == 0:
            return 0.0
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
    def total_entry_value(self) -> float:
        """Net capital deployed across all legs (buys positive, sells negative)."""
        total = 0.0
        for leg in self.legs:
            if leg.direction == Direction.BUY:
                total += leg.entry_value
            else:
                total -= leg.entry_value
        return total

    def total_pnl(self, prices: dict[int, float]) -> float:
        """Compute strategy-level P&L given current prices keyed by leg ID.

        Args:
            prices: Mapping of leg.id -> current LTP.
        """
        return sum(
            leg.pnl(prices[leg.id])
            for leg in self.legs
            if leg.id is not None and leg.id in prices
        )


class DailySnapshot(BaseModel):
    """A single day's closing data for one leg."""

    id: int | None = None
    leg_id: int
    snapshot_date: date
    ltp: float
    close: float | None = None
    iv: float | None = Field(default=None, description="Implied volatility")
    delta: float | None = None
    theta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    oi: int | None = Field(default=None, description="Open interest")
    volume: int | None = None
    underlying_price: float | None = Field(
        default=None, description="Nifty spot at snapshot time"
    )

    def leg_pnl(self, entry_price: float, quantity: int, direction: Direction) -> float:
        """Compute P&L using this snapshot's LTP."""
        if direction == Direction.BUY:
            return (self.ltp - entry_price) * quantity
        return (entry_price - self.ltp) * quantity
