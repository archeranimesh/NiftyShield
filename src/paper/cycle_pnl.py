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
