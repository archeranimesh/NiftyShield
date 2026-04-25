"""Data models for paper trading.

Paper trades are simulated executions recorded for strategy validation before
going live. They mirror the live Trade model but are isolated by:

  1. An explicit ``is_paper = True`` marker field.
  2. A validator that enforces ``strategy_name`` starts with ``paper_``.

This dual guard prevents accidental cross-contamination when querying the
shared ``portfolio.sqlite`` database.

All monetary fields use Decimal (stored as TEXT in SQLite) — same invariant
as the live Trade and MFTransaction models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.models.portfolio import TradeAction


class PaperTrade(BaseModel):
    """A single simulated trade execution for paper trading.

    Immutable after construction (frozen=True). Mirrors ``Trade`` exactly
    except for the ``is_paper`` marker and the ``strategy_name`` validator.

    Attributes:
        strategy_name: Must start with ``paper_``, e.g. ``paper_csp_nifty_v1``.
        leg_role: Human label for the position, e.g. ``short_put``.
        instrument_key: Upstox instrument key, e.g. ``NSE_FO|12345``.
        trade_date: Simulated execution date.
        action: BUY or SELL.
        quantity: Units transacted. Always positive — direction is in action.
        price: Simulated execution price per unit. Always positive.
        notes: Optional annotation (slippage assumption, decision rationale, etc.).
        is_paper: Always True. Explicit marker for defensive query filtering.
    """

    strategy_name: str = Field(..., min_length=1)
    leg_role: str = Field(..., min_length=1)
    instrument_key: str = Field(..., min_length=1)
    trade_date: date
    action: TradeAction
    quantity: int = Field(..., gt=0)
    price: Decimal = Field(..., gt=0)
    notes: str = ""
    is_paper: Literal[True] = True

    model_config = {"frozen": True}

    @field_validator("strategy_name")
    @classmethod
    def strategy_name_must_have_paper_prefix(cls, v: str) -> str:
        """Enforce paper_ prefix to prevent live/paper ledger cross-contamination.

        Args:
            v: Proposed strategy_name value.

        Returns:
            The validated strategy_name.

        Raises:
            ValueError: If the name does not start with ``paper_``.
        """
        if not v.startswith("paper_"):
            raise ValueError(
                f"PaperTrade strategy_name must start with 'paper_', got: {v!r}"
            )
        return v

    @field_validator("price", mode="before")
    @classmethod
    def price_must_be_positive(cls, v: object) -> object:
        """Coerce str/float inputs; float inputs converted via str() to avoid fp errors.

        Args:
            v: Raw price value from caller.

        Returns:
            A Decimal-compatible value.
        """
        if isinstance(v, float):
            v = Decimal(str(v))
        return v


@dataclass(frozen=True)
class PaperPosition:
    """Derived position state for a single leg within a paper strategy.

    Computed from ``paper_trades`` rows by ``PaperStore.get_position``.
    Never stored directly — reconstructed on demand.

    Attributes:
        strategy_name: Parent paper strategy name.
        leg_role: Leg identifier within the strategy.
        net_qty: Net open quantity (positive = long, negative = short).
        avg_cost: Weighted average price of BUY trades. Zero if no BUYs.
        avg_sell_price: Weighted average price of SELL trades. Zero if no SELLs.
        instrument_key: Upstox key for the current open position.
    """

    strategy_name: str
    leg_role: str
    net_qty: int
    avg_cost: Decimal
    avg_sell_price: Decimal
    instrument_key: str


@dataclass(frozen=True)
class PaperNavSnapshot:
    """Daily mark-to-market snapshot for a paper strategy.

    One row per (strategy_name, snapshot_date) in ``paper_nav_snapshots``.

    Attributes:
        strategy_name: Paper strategy this snapshot belongs to.
        snapshot_date: Date of this snapshot.
        unrealized_pnl: Mark-to-market P&L for open positions.
        realized_pnl: Cumulative realized P&L from closed trades up to this date.
        total_pnl: unrealized_pnl + realized_pnl.
        underlying_price: Nifty spot at snapshot time (optional context).
    """

    strategy_name: str
    snapshot_date: date
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    underlying_price: Decimal | None = None
