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


def _build_cycle(index: int, segment: list[PaperTrade], *, is_open: bool) -> Cycle:
    entry_date = segment[0].trade_date
    exit_date = None if is_open else segment[-1].trade_date
    days = None if exit_date is None else (exit_date - entry_date).days
    return Cycle(
        index=index,
        entry_date=entry_date,
        exit_date=exit_date,
        days_in_trade=days,
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
