"""Reconstruct trade cycles from the append-only ``paper_trades`` ledger.

A *cycle* is one round trip for a set of legs: every leg opened, then every
leg flattened back to net-zero quantity. ``paper_trades`` carries no
``cycle_id``, so boundaries are derived here by walking trades in execution
order and cutting each time all tracked legs are simultaneously flat.

Shared by ``scripts/dev/cycle_pnl_report.py`` and (per BUG-043) the strategy
close-notification "Cycle P&L" line. Kept import-light on purpose — only
``src.models`` and ``src.paper.models`` — so it can be pulled into the
strategy close paths without the ``PaperStore`` / ``profit_lock_engine``
import cycle.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade


@dataclass(frozen=True)
class Cycle:
    """One open→flat round trip for a set of legs.

    Attributes:
        index: 1-based position of this cycle within the reconstructed list.
        entry_date: ``trade_date`` of the first trade in the cycle.
        exit_date: ``trade_date`` of the last trade, or ``None`` while open.
        days_in_trade: Calendar days entry→exit, or ``None`` while open.
        entry_credit_per_unit: Net premium per unit at entry — SELL legs add,
            BUY (hedge) legs subtract. Positive for a credit structure
            (Iron Condor, covered call), negative for a net-debit entry.
            Assumes a uniform lot quantity across the group's legs.
        exit_cost_per_unit: Net premium per unit paid to close — BUY-to-close
            adds, SELL-to-close subtracts. ``None`` while the cycle is open.
        decay_pct: Percentage of the entry credit kept as realized profit,
            ``100 * (entry_credit - exit_cost) / entry_credit``. ``None`` when
            the cycle is open or the entry was not a net credit.
        realized_pnl: Weighted SELL−BUY realized P&L over closed quantity,
            summed across legs. Reflects only closed quantity, so a still-open
            cycle reports the realized portion (usually ``0``).
        is_open: ``True`` when the legs have not all returned to net-zero.
        trades: Trades belonging to this cycle, in execution order.
        short_credit_per_unit: Sum of the per-unit SELL-to-open prices of the
            cycle's short legs only (a leg whose entry trade is a SELL;
            hedges/longs excluded). ``0`` when the cycle has no short leg
            (a pure long PP).
        short_buyback_per_unit: Sum of the per-unit BUY-to-close prices of
            those same short legs. ``None`` while the cycle is open.
        short_decay_pct: ``100 * (short_credit_per_unit - short_buyback_per_unit)
            / short_credit_per_unit`` — the gross-short-premium decay basis.
            ``None`` when the cycle is open or ``short_credit_per_unit <= 0``
            (no short leg). Stable across IC / CSP / CC / Collar; correctly
            absent for a pure-long PP. This is the basis every exit card and
            ``cycle_stats`` uses — the net ``decay_pct`` above stays for the
            report CLI.
    """

    index: int
    entry_date: date
    exit_date: date | None
    days_in_trade: int | None
    entry_credit_per_unit: Decimal
    exit_cost_per_unit: Decimal | None
    decay_pct: Decimal | None
    realized_pnl: Decimal
    is_open: bool
    trades: tuple[PaperTrade, ...]
    short_credit_per_unit: Decimal
    short_buyback_per_unit: Decimal | None
    short_decay_pct: Decimal | None


def _segment_realized_pnl(trades: Sequence[PaperTrade]) -> Decimal:
    """Weighted SELL−BUY realized P&L over closed qty, summed across leg roles.

    Same approximation as ``tracker._compute_realized_pnl_by_leg`` — full
    weighted average rather than strict FIFO for partial closes, which is
    acceptable for paper-trading analysis.

    Args:
        trades: Trades of a single cycle (any mix of leg roles).

    Returns:
        Realized P&L in rupees.
    """
    total = Decimal("0")
    for role in sorted({t.leg_role for t in trades}):
        legs = [t for t in trades if t.leg_role == role]
        buy_qty = sum(t.quantity for t in legs if t.action == TradeAction.BUY)
        sell_qty = sum(t.quantity for t in legs if t.action == TradeAction.SELL)
        closed_qty = min(buy_qty, sell_qty)
        if closed_qty == 0:
            continue
        buy_val = sum(
            (t.price * t.quantity for t in legs if t.action == TradeAction.BUY), Decimal("0")
        )
        sell_val = sum(
            (t.price * t.quantity for t in legs if t.action == TradeAction.SELL), Decimal("0")
        )
        buy_avg = buy_val / buy_qty if buy_qty else Decimal("0")
        sell_avg = sell_val / sell_qty if sell_qty else Decimal("0")
        total += (sell_avg - buy_avg) * Decimal(closed_qty)
    return total


def _signed_premium_per_unit(trades: list[PaperTrade]) -> Decimal:
    """Net premium per unit: SELL adds, BUY subtracts. Assumes uniform lot qty."""
    return sum(
        (t.price if t.action == TradeAction.SELL else -t.price for t in trades),
        Decimal("0"),
    )


def _entry_exit_legs(
    segment: list[PaperTrade],
) -> tuple[list[PaperTrade], list[PaperTrade]]:
    """First and last trade per leg role — the opening and closing fills.

    A role with a single trade (an open leg) contributes only to ``entry``.
    Mid-cycle defend/adjustment fills are not reflected in the entry/exit
    premium figures, only in ``realized_pnl``.
    """
    first: dict[str, PaperTrade] = {}
    last: dict[str, PaperTrade] = {}
    for trade in segment:
        first.setdefault(trade.leg_role, trade)
        last[trade.leg_role] = trade
    entry = list(first.values())
    exit_ = [last[role] for role, t in first.items() if last[role] is not t]
    return entry, exit_


def _build_cycle(index: int, segment: list[PaperTrade], *, is_open: bool) -> Cycle:
    entry_date = segment[0].trade_date
    exit_date = None if is_open else segment[-1].trade_date
    days = None if exit_date is None else (exit_date - entry_date).days

    entry_legs, exit_legs = _entry_exit_legs(segment)
    entry_credit = _signed_premium_per_unit(entry_legs)
    exit_cost: Decimal | None = None
    decay_pct: Decimal | None = None
    if not is_open and exit_legs:
        exit_cost = -_signed_premium_per_unit(exit_legs)
        if entry_credit > 0:
            decay_pct = (entry_credit - exit_cost) / entry_credit * Decimal("100")

    short_roles = {t.leg_role for t in entry_legs if t.action == TradeAction.SELL}
    short_credit = sum((t.price for t in entry_legs if t.leg_role in short_roles), Decimal("0"))
    short_buyback: Decimal | None = None
    short_decay_pct: Decimal | None = None
    if not is_open and short_roles:
        short_buyback = sum((t.price for t in exit_legs if t.leg_role in short_roles), Decimal("0"))
        if short_credit > 0:
            short_decay_pct = (short_credit - short_buyback) / short_credit * Decimal("100")

    return Cycle(
        index=index,
        entry_date=entry_date,
        exit_date=exit_date,
        days_in_trade=days,
        entry_credit_per_unit=entry_credit,
        exit_cost_per_unit=exit_cost,
        decay_pct=decay_pct,
        realized_pnl=_segment_realized_pnl(segment),
        is_open=is_open,
        trades=tuple(segment),
        short_credit_per_unit=short_credit,
        short_buyback_per_unit=short_buyback,
        short_decay_pct=short_decay_pct,
    )


def reconstruct_cycles(trades: Sequence[PaperTrade]) -> list[Cycle]:
    """Split a leg group's trades into open→flat cycles.

    ``trades`` must be pre-filtered to one strategy and one leg group (all IC
    legs, or just ``overlay_cc``, etc.) and sorted in execution order
    (``trade_date ASC, id ASC``). A boundary is cut after any trade that
    leaves every seen ``leg_role`` at net-zero quantity.

    Args:
        trades: Ledger rows in execution order.

    Returns:
        Cycles oldest first. A trailing run of trades that never returns to
        flat becomes a final cycle with ``is_open=True``. Empty input → ``[]``.
    """
    cycles: list[Cycle] = []
    net: dict[str, int] = defaultdict(int)
    segment: list[PaperTrade] = []
    for trade in trades:
        signed_qty = trade.quantity if trade.action == TradeAction.BUY else -trade.quantity
        net[trade.leg_role] += signed_qty
        segment.append(trade)
        if all(qty == 0 for qty in net.values()):
            cycles.append(_build_cycle(len(cycles) + 1, segment, is_open=False))
            segment = []
            net.clear()
    if segment:
        cycles.append(_build_cycle(len(cycles) + 1, segment, is_open=True))
    return cycles


def get_last_cycle_realized_pnl(trades: Sequence[PaperTrade]) -> Decimal | None:
    """Realized P&L of the most recent *closed* cycle.

    Args:
        trades: Ledger rows for one strategy + leg group, execution order.

    Returns:
        The last closed cycle's realized P&L, or ``None`` if no cycle has
        closed yet.
    """
    closed = [c for c in reconstruct_cycles(trades) if not c.is_open]
    return closed[-1].realized_pnl if closed else None


@dataclass(frozen=True)
class CycleStats:
    """Win-rate / P&L / decay stats over a strategy's closed cycles.

    Attributes:
        closed_count: Number of closed cycles.
        wins: Cycles with ``realized_pnl > 0``.
        losses: Cycles with ``realized_pnl <= 0``.
        win_rate: ``wins / closed_count``, or ``None`` when ``closed_count == 0``.
        avg_win: Mean ``realized_pnl`` over winning cycles, ``0`` if none.
        avg_loss: Mean ``realized_pnl`` over losing cycles (signed, ``<= 0``),
            ``0`` if none.
        best: Highest ``realized_pnl`` across closed cycles, ``0`` if none.
        worst: Lowest ``realized_pnl`` across closed cycles, ``0`` if none.
        avg_hold_days: Mean ``days_in_trade`` across closed cycles, ``0`` if none.
        avg_decay_pct: Mean ``short_decay_pct`` over closed cycles that have
            one, or ``None`` when none do.
    """

    closed_count: int
    wins: int
    losses: int
    win_rate: float | None
    avg_win: Decimal
    avg_loss: Decimal
    best: Decimal
    worst: Decimal
    avg_hold_days: float
    avg_decay_pct: Decimal | None


def cycle_stats(trades: Sequence[PaperTrade]) -> CycleStats:
    """Win-rate / P&L / decay stats over a leg group's closed cycles.

    Pure — no I/O. Args mirror ``reconstruct_cycles``: pre-filtered to one
    strategy + leg group, execution order.

    Args:
        trades: Ledger rows for one strategy + leg group, execution order.

    Returns:
        ``CycleStats`` over the closed cycles. All-zero / ``None`` fields when
        there are none.
    """
    closed = [c for c in reconstruct_cycles(trades) if not c.is_open]
    if not closed:
        return CycleStats(
            closed_count=0,
            wins=0,
            losses=0,
            win_rate=None,
            avg_win=Decimal("0"),
            avg_loss=Decimal("0"),
            best=Decimal("0"),
            worst=Decimal("0"),
            avg_hold_days=0.0,
            avg_decay_pct=None,
        )

    wins_list = [c.realized_pnl for c in closed if c.realized_pnl > 0]
    losses_list = [c.realized_pnl for c in closed if c.realized_pnl <= 0]
    decay_values = [c.short_decay_pct for c in closed if c.short_decay_pct is not None]
    all_pnl = [c.realized_pnl for c in closed]
    hold_days = [c.days_in_trade for c in closed if c.days_in_trade is not None]

    return CycleStats(
        closed_count=len(closed),
        wins=len(wins_list),
        losses=len(losses_list),
        win_rate=len(wins_list) / len(closed),
        avg_win=(sum(wins_list, Decimal("0")) / len(wins_list)) if wins_list else Decimal("0"),
        avg_loss=(sum(losses_list, Decimal("0")) / len(losses_list))
        if losses_list
        else Decimal("0"),
        best=max(all_pnl),
        worst=min(all_pnl),
        avg_hold_days=(sum(hold_days) / len(hold_days)) if hold_days else 0.0,
        avg_decay_pct=(sum(decay_values, Decimal("0")) / len(decay_values))
        if decay_values
        else None,
    )


@dataclass(frozen=True)
class LegGroup:
    """One reportable leg group: a label, its strategy, and its leg-role filter."""

    label: str
    strategy_name: str
    leg_roles: tuple[str, ...] | None  # None = every leg of the strategy


_IC_STRATEGIES = {
    "ic-weekly": "paper_ic_nifty_v1_weekly",
    "ic-monthly": "paper_ic_nifty_v1_monthly",
    "ic-leaps": "paper_ic_nifty_v1_leaps",
    "ic-v2": "paper_ic_nifty_v2_monthly",
}
_OVERLAY_STRATEGY = "paper_nifty_overlay"
_OVERLAY_GROUPS = {
    "cc": ("overlay_cc",),
    "pp": ("overlay_pp",),
    "collar": ("overlay_collar_put", "overlay_collar_call"),
}


def resolve_target(target: str) -> list[LegGroup]:
    """Map a CLI target token to the leg groups it selects.

    Args:
        target: One of the alias tokens (``ic-all``, ``cc`` …) or an exact
            ``paper_*`` strategy name.

    Returns:
        Ordered list of groups to report.

    Raises:
        ValueError: If the target is not a known alias or ``paper_*`` name.
    """
    if target in _IC_STRATEGIES:
        name = _IC_STRATEGIES[target]
        return [LegGroup(name, name, None)]
    if target in _OVERLAY_GROUPS:
        return [
            LegGroup(f"{_OVERLAY_STRATEGY}:{target}", _OVERLAY_STRATEGY, _OVERLAY_GROUPS[target])
        ]
    if target == "ic-all":
        return [LegGroup(n, n, None) for n in _IC_STRATEGIES.values()]
    if target == "overlay-all":
        return [
            LegGroup(f"{_OVERLAY_STRATEGY}:{k}", _OVERLAY_STRATEGY, v)
            for k, v in _OVERLAY_GROUPS.items()
        ]
    if target == "all":
        return resolve_target("ic-all") + resolve_target("overlay-all")
    if target.startswith("paper_"):
        return [LegGroup(target, target, None)]
    raise ValueError(
        f"unknown target {target!r} — use an alias "
        f"(ic-all, ic-weekly, cc, pp, collar, overlay-all, all) or a paper_* strategy name"
    )
