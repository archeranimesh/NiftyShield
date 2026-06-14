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
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.models.portfolio import TradeAction


class TradeState(str, Enum):
    """Lifecycle state of an open paper trade leg.

    OPEN: Normal operation — no defensive action taken yet.
    DEFENDED: A DELTA_BREACH roll was executed; one defensive roll consumed.
    RE_ENTRY_PENDING: Position was closed (HARD_STOP or DELTA_BREACH_FINAL);
        waiting for re-entry conditions (IVR + delta range) to be met.
    CLOSED: Position fully exited (roll close, profit target, or stop).
        Terminal state — set on the opening trade row after the corresponding
        close trade is recorded. Prevents re-signal on already-closed legs.
    """

    OPEN = "OPEN"
    DEFENDED = "DEFENDED"
    RE_ENTRY_PENDING = "RE_ENTRY_PENDING"
    CLOSED = "CLOSED"


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
        ivr_at_entry: India VIX IV Rank at trade entry [0.0, 1.0].
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
    ivr_at_entry: float | None = None
    state: TradeState = TradeState.OPEN
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
            raise ValueError(f"PaperTrade strategy_name must start with 'paper_', got: {v!r}")
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
        entry_date: Date of first SELL trade for the leg. None for purely long
            legs or positions recorded before this field was added.
    """

    strategy_name: str
    leg_role: str
    net_qty: int
    avg_cost: Decimal
    avg_sell_price: Decimal
    instrument_key: str
    entry_date: date | None = None


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


@dataclass(frozen=True)
class PaperLegSnapshot:
    """Per-leg daily P&L snapshot for a paper strategy.

    One row per (strategy_name, leg_role, snapshot_date) in
    ``paper_leg_snapshots``. Enables delta-from-yesterday tracking per
    individual overlay or base leg without polluting the strategy-total
    ``paper_nav_snapshots`` table.

    Attributes:
        strategy_name: Paper strategy this snapshot belongs to.
        leg_role: Leg identifier within the strategy, e.g. ``overlay_pp``.
        snapshot_date: Date of this snapshot.
        unrealized_pnl: Mark-to-market P&L for the open position on this leg.
        realized_pnl: Cumulative realized P&L from closed trades on this leg.
        total_pnl: unrealized_pnl + realized_pnl. Must satisfy
            ``total_pnl == unrealized_pnl + realized_pnl`` — enforced by
            ``PaperStore.record_leg_snapshot`` at write time.
        ltp: Last traded price at snapshot time (optional context).
    """

    strategy_name: str
    leg_role: str
    snapshot_date: date
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    ltp: Decimal | None = None


class ExitSignal(str, Enum):
    PROFIT_TARGET = "PROFIT_TARGET"
    TIME_STOP = "TIME_STOP"
    DTE_FORCED = "DTE_FORCED"
    DTE_REVIEW = "DTE_REVIEW"
    LOSS_STOP = "LOSS_STOP"
    DELTA_STOP = "DELTA_STOP"
    DELTA_WARN = "DELTA_WARN"
    BELOW_FLOOR = "BELOW_FLOOR"
    CRASH_MONETIZE = "CRASH_MONETIZE"
    COLLAR_CALL_DECAY = "COLLAR_CALL_DECAY"
    COLLAR_CALL_WARN = "COLLAR_CALL_WARN"
    COLLAR_PUT_CRASH = "COLLAR_PUT_CRASH"
    COLLAR_CLOSE_ALL = "COLLAR_CLOSE_ALL"
    COLLAR_REBALANCE = "COLLAR_REBALANCE"
    R5_REENTRY_ELIGIBLE = "R5_REENTRY_ELIGIBLE"
    R5_REENTRY_BLOCKED = "R5_REENTRY_BLOCKED"
    BASE_EXPIRY_ALERT = "BASE_EXPIRY_ALERT"
    MANUAL = "MANUAL"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    NONE = "NONE"


class PaperExitEvent(BaseModel):
    id: int | None = None
    strategy_name: str = Field(..., min_length=1)
    leg_name: str = Field(..., min_length=1)
    trade_id: str = Field(..., min_length=1)
    snapshot_id: int | None = None
    event_time: datetime
    detected_by: Literal["EOD", "INTRADAY", "MANUAL"]
    exit_signal: ExitSignal
    severity: Literal["INFO", "WARNING", "ACTION"]
    ltp: Decimal | None = None
    mid: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    delta: float | None = None
    dte: int | None = None
    entry_price: Decimal
    threshold_value: Decimal | None = None
    delta_stop_would_fire: Literal[0, 1] | None = None
    premium_stop_would_fire: Literal[0, 1] | None = None
    actual_rule_used: str | None = None
    status: Literal["OPEN", "ACKNOWLEDGED", "ACTED", "DISMISSED"] = "OPEN"
    notes: str | None = None
    created_at: str | None = None

    model_config = {"frozen": True}
