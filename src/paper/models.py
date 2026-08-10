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
        option_type: Instrument classification resolved lazily at read time by
            ``PaperStore.get_position``/``get_positions`` via ``InstrumentLookup``.
            ``"EQ"`` for the NiftyBees equity leg, ``"CE"``/``"PE"`` for options,
            ``"FUT"`` for futures contracts. ``None`` if the instrument_key could
            not be resolved (unrecognised/legacy key), the resolved instrument
            is none of CE/PE/FUT (e.g. an equity/index key other than
            NiftyBees), the BOD JSON file itself could not be loaded
            (missing/corrupt) — all logged as a warning and never raise — or
            (BUG-014) the leg is flat (``net_qty == 0``): resolution is skipped
            entirely for closed legs, silently, since a settled/delisted
            contract's instrument_key can never resolve again once it drops
            out of the BOD file, and attempting it every read would produce a
            permanent, unactionable warning for every closed leg forever.
    """

    strategy_name: str
    leg_role: str
    net_qty: int
    avg_cost: Decimal
    avg_sell_price: Decimal
    instrument_key: str
    entry_date: date | None = None
    option_type: Literal["PE", "CE", "FUT", "EQ"] | None = None


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
class MarginSnapshot:
    """Margin captured once, at the entry of a strategy's open position cycle.

    One row per (strategy_name, entry_date) in ``paper_margin_snapshots``.
    Captured from ``BrokerClient.get_order_margin()`` immediately after a
    strategy's entry trades are recorded — not refreshed daily. ROI-on-margin
    reporting divides P&L by ``final_margin`` (the post-netting-benefit
    figure — what the broker actually blocks), never ``required_margin``.

    Attributes:
        strategy_name: Paper strategy this snapshot belongs to.
        entry_date: Date the position cycle opened — matches
            ``PaperPosition.entry_date`` for the same cycle.
        required_margin: Pre-netting-benefit basket margin (each leg priced
            independently). Kept for reference/audit, not used in ROI.
        final_margin: Post-netting-benefit margin — actual capital blocked.
            ROI-on-margin denominator.
        captured_at: UTC timestamp of the margin-calculator call.
    """

    strategy_name: str
    entry_date: date
    required_margin: Decimal
    final_margin: Decimal
    captured_at: datetime


@dataclass(frozen=True)
class OverlayCoverage:
    """Query-time overlay coverage ratio for one 3-track base (S3r, 2026-07-29).

    Never persisted — overlay legs live in a single track-independent copy
    (``STRATEGY_OVERLAY = "paper_nifty_overlay"``, S1r); this is a read-time
    join answering "how much protection does the current overlay give this
    track right now", recomputed on every call rather than duplicated per
    track (that duplication was RQ2's original, retired mistake).

    Attributes:
        track_name: One of the three base strategy_names (Spot/Futures/Proxy).
        track_effective_units: Base leg's effective Nifty-point exposure —
            ``qty * delta`` (NiftyBees beta for Spot, 1.0 for Futures, live
            chain delta for the Proxy DITM call). Zero if the track has no
            open base position.
        overlay_effective_units: Sum of ``qty * delta`` across all open legs
            in the shared overlay namespace — independent of which track this
            coverage row is being computed for.
        coverage_pct: ``overlay_effective_units / track_effective_units *
            100``. ``None`` when ``track_effective_units`` is zero (no open
            base position — coverage is undefined, not zero). Can be
            negative — not a bug: a directionally-correlated overlay leg
            (e.g. a protective put attributed to a short base) reduces net
            exposure rather than hedging it, and that should read as
            negative coverage, not be clamped to zero.
        as_of: Date this ratio was computed for (chain/Greeks are always
            fetched live; this is a label, not a persistence key).
    """

    track_name: str
    track_effective_units: Decimal
    overlay_effective_units: Decimal
    coverage_pct: Decimal | None
    as_of: date


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


@dataclass(frozen=True)
class TrackComparisonSnapshot:
    """Daily base-instrument-only P&L snapshot for the 3-track RQ1 comparison.

    One row per (strategy_name, snapshot_date) in
    ``paper_track_comparison_snapshots``. Computed strictly from the base leg
    (``base_etf`` / ``base_futures`` / ``base_ditm_call``) mark price — overlay
    legs (CC/PP/Collar) never enter this table, by design (see
    docs/plan/3track-consolidation/stories.md S3). Nifty spot is persisted as
    a 4th synthetic series under ``strategy_name="nifty_index"`` so all four
    series share one schema and one query path.

    Attributes:
        strategy_name: One of the three 3-track strategy names, or the
            synthetic ``"nifty_index"`` value for the Nifty spot series.
        snapshot_date: Date of this snapshot.
        pnl_1d_abs: Today's base-leg mark value minus yesterday's base-leg
            mark value (absolute Rupees).
        pnl_1d_pct: ``pnl_1d_abs / yesterday's mark value`` — standard daily
            return. Denominator is yesterday's closing mark, never entry cost
            basis and never NEE/spot notional.
        pnl_inception_abs: Today's base-leg mark value minus entry cost basis
            (absolute Rupees, cumulative since the track's original entry).
        pnl_inception_pct: ``pnl_inception_abs / entry_cost_basis``.
            Deliberately a *different* denominator than ``pnl_1d_pct`` — the
            two percentage fields are never computed off the same base and
            must not be treated as directly subtractable/addable.
        tracking_error_pct: Secondary/bonus field — this track's cumulative
            return % minus Nifty spot's cumulative return % over the same
            window since entry. ``None`` for the ``"nifty_index"`` row itself
            (tracking error against itself is meaningless) and until entry
            data is available to compute it.
    """

    strategy_name: str
    snapshot_date: date
    pnl_1d_abs: Decimal
    pnl_1d_pct: Decimal
    pnl_inception_abs: Decimal
    pnl_inception_pct: Decimal
    tracking_error_pct: Decimal | None = None


@dataclass(frozen=True)
class OverlayPnLSnapshot:
    """Daily per-overlay P&L snapshot, mirroring ``TrackComparisonSnapshot``'s

    Level-1 fields for CC/PP/Collar instead of the base tracks.

    One row per ``(strategy_name, overlay_type, snapshot_date)`` in
    ``paper_overlay_pnl_snapshots``. ``strategy_name`` is
    ``STRATEGY_OVERLAY`` (the standalone overlay book, since BUG-028's
    2026-08-10 fix) for every row written going forward — a pre-fix row may
    still carry a 3-track strategy_name until BUG-028 Phase 3's historical
    repair runs. Computed from the real-leg-role ``paper_leg_snapshots`` rows
    (``overlay_cc``/``overlay_pp``/``overlay_collar_call``/
    ``overlay_collar_put``) — Collar's call+put merge into a single
    ``"collar"`` row, matching the display convention
    ``_overlay_type_groups`` (``scripts/strategies/three_track/paper_3track_snapshot.py``)
    establishes for the printed summary.
    See docs/plan/3track-consolidation/stories.md S8,
    docs/council/2026-08-10_overlay-pnl-reporting-track-independence.md.

    Attributes:
        strategy_name: Strategy this overlay P&L is attributed to
            (``STRATEGY_OVERLAY`` post-BUG-028).
        overlay_type: One of ``"cc"``, ``"pp"``, ``"collar"``.
        snapshot_date: Date of this snapshot.
        pnl_1d_abs: Today's overlay total P&L minus yesterday's overlay total
            P&L (absolute Rupees).
        pnl_1d_pct: ``pnl_1d_abs / yesterday's mark value``. Denominator is
            yesterday's closing mark, never entry cost/credit basis.
        pnl_inception_abs: Today's overlay total P&L minus zero (P&L is
            already cumulative since entry) — kept as its own field for
            symmetry with S3's shape and to allow the two pct fields to use
            independent denominators.
        pnl_inception_pct: ``pnl_inception_abs / abs(entry_basis)``, where
            entry_basis is the credit received (CC) or debit paid (PP) at
            entry, or the sum of both legs' absolute basis for Collar. Same
            unsigned-denominator convention as S3 — P&L direction is already
            correctly signed via mark-to-market, so no overlay-specific sign
            inversion is applied (confirmed with operator, 2026-08-01).
    """

    strategy_name: str
    overlay_type: str
    snapshot_date: date
    pnl_1d_abs: Decimal
    pnl_1d_pct: Decimal
    pnl_inception_abs: Decimal
    pnl_inception_pct: Decimal


@dataclass(frozen=True)
class ProtectionRecoverySnapshot:
    """Daily NiftyBees-vs-overlay recovery comparison row.

    One row per ``snapshot_date`` in ``paper_protection_recovery_snapshots``.
    Reads S3's ``TrackComparisonSnapshot`` (NiftyBees base leg) and S8's
    ``OverlayPnLSnapshot`` (cc/pp/collar) for the same date — computes
    nothing from raw legs itself. See
    docs/plan/3track-consolidation/stories.md S9.

    Attributes:
        snapshot_date: Date of this snapshot.
        niftybees_pnl_1d: NiftyBees base-leg 1-day P&L (S3, ``strategy_name
            == STRATEGY_SPOT``).
        cc_pnl_1d: CC overlay 1-day P&L (S8, ``overlay_type == "cc"``).
        pp_pnl_1d: PP overlay 1-day P&L (S8, ``overlay_type == "pp"``).
        collar_pnl_1d: Collar overlay 1-day P&L (S8, ``overlay_type ==
            "collar"``).
        niftybees_pnl_inception: NiftyBees base-leg inception P&L.
        cc_pnl_inception: CC overlay inception P&L.
        pp_pnl_inception: PP overlay inception P&L.
        collar_pnl_inception: Collar overlay inception P&L.
        best_overlay: Which of cc/pp/collar recovered the largest share of
            a red NiftyBees day, by ``recovery_pct``. ``None`` when
            ``niftybees_pnl_1d >= 0`` — a green/flat day has nothing to
            recover, so there is no meaningful "best" overlay, not a
            zero-anchored one.
        best_recovery_pct: ``overlay_pnl_1d / abs(niftybees_pnl_1d)`` for
            ``best_overlay``. ``None`` under the same green/flat-day rule
            as ``best_overlay`` — always both-None or both-set together.
        best_overlay_inception: Same rule as ``best_overlay`` but computed
            from the inception fields, independently of the daily pair —
            not a running sum of daily recovery, since inception P&L uses
            entry cost/credit basis per S3/S8 and legitimately drifts from
            a naive cumulative sum of the daily column.
        best_recovery_pct_inception: Inception-basis counterpart to
            ``best_recovery_pct``, same None-pairing rule.
    """

    snapshot_date: date
    niftybees_pnl_1d: Decimal
    cc_pnl_1d: Decimal
    pp_pnl_1d: Decimal
    collar_pnl_1d: Decimal
    niftybees_pnl_inception: Decimal
    cc_pnl_inception: Decimal
    pp_pnl_inception: Decimal
    collar_pnl_inception: Decimal
    best_overlay: str | None = None
    best_recovery_pct: Decimal | None = None
    best_overlay_inception: str | None = None
    best_recovery_pct_inception: Decimal | None = None


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
    ROLL_ELIGIBLE = "ROLL_ELIGIBLE"
    ROLL_BASE_FIRST = "ROLL_BASE_FIRST"
    ROLL_DUE_DTE = "ROLL_DUE_DTE"
    ROLL_DUE_DECAY = "ROLL_DUE_DECAY"
    OVERLAY_EXPIRED = "OVERLAY_EXPIRED"
    PROXY_DELTA_CRITICAL = "PROXY_DELTA_CRITICAL"
    PROXY_PREMIUM_DECAY = "PROXY_PREMIUM_DECAY"
    PROXY_DELTA_WARN = "PROXY_DELTA_WARN"
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
    counterfactual_dte_marks: str | None = None
    status: Literal["OPEN", "ACKNOWLEDGED", "ACTED", "DISMISSED"] = "OPEN"
    notes: str | None = None
    created_at: str | None = None

    model_config = {"frozen": True}


class GateViolation(BaseModel):
    """Structured record of a threshold gate that would have blocked entry.

    Written under ``--log-only-gates`` mode: a threshold/discretionary IC
    entry gate (IVR floor, DTE window, liquidity floor, portfolio-delta cap)
    fails, but instead of aborting the entry the failure is persisted here
    and the trade proceeds. Structural/data-integrity gates (duplicate
    position, post-expiry guard, unresolved instrument keys, stale/missing
    chain data) never produce a ``GateViolation`` — they always hard-block
    regardless of the flag.
    """

    id: int | None = None
    gate_name: str = Field(..., min_length=1)
    threshold: str
    actual: str
    strategy_name: str = Field(..., min_length=1)
    logged_at: datetime

    model_config = {"frozen": True}
