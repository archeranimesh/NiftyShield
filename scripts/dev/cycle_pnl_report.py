#!/usr/bin/env python3
"""Per-cycle P&L / exit-reason / days-in-trade report for paper strategies.

Reconstructs each round-trip cycle from ``paper_trades`` (see
``src/paper/cycle_pnl.py`` — a cycle boundary is every point where all legs of
the group return to net-zero), then prints per cycle: entry date, exit date,
days in trade, realized cycle P&L, and the exit reason (from
``paper_exit_events`` where recorded, else the closing trade's note). Ends each
strategy block with the total realized across closed cycles.

Read-only. No network, no writes.

Usage:
    python -m scripts.dev.cycle_pnl_report ic-weekly
    python -m scripts.dev.cycle_pnl_report ic-all
    python -m scripts.dev.cycle_pnl_report cc
    python -m scripts.dev.cycle_pnl_report collar
    python -m scripts.dev.cycle_pnl_report all
    python -m scripts.dev.cycle_pnl_report paper_ic_nifty_v2_monthly
    python -m scripts.dev.cycle_pnl_report ic-all --db-path /path/to/db.sqlite

Targets:
    ic-weekly / ic-monthly / ic-leaps / ic-v2   single IC strategy
    ic-all                                       all four IC strategies
    cc / pp / collar                             overlay group in paper_nifty_overlay
    overlay-all                                  cc + pp + collar
    all                                          ic-all + overlay-all
    <exact paper_* strategy name>                that strategy, all legs as one group
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import structlog

from src.notifications.formatting import format_money
from src.paper.constants import DEFAULT_DB_PATH
from src.paper.cycle_pnl import Cycle, reconstruct_cycles, resolve_target
from src.paper.cycle_pnl import LegGroup as _Group
from src.paper.store import PaperStore
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.dev.cycle_pnl_report"
logger = structlog.get_logger(_SCRIPT_NAME)


def _load_exit_signals(conn: sqlite3.Connection, strategy_name: str) -> list[tuple[date, str]]:
    """Combined-signal exit events for a strategy, oldest first.

    Only ``leg_name = 'ALL'`` rows — those are the whole-position exit signals
    (PROFIT_TARGET / LOSS_STOP / TIME_STOP); per-leg rows are entry annotations.
    All statuses are included: the acted rows are not reliably flipped to
    ``ACTED`` in the live DB.
    """
    rows = conn.execute(
        "SELECT event_time, exit_signal FROM paper_exit_events "
        "WHERE strategy_name = ? AND leg_name = 'ALL' "
        "ORDER BY event_time ASC, id ASC",
        (strategy_name,),
    ).fetchall()
    out: list[tuple[date, str]] = []
    for event_time, exit_signal in rows:
        signal = str(exit_signal or "").strip()
        if not signal or signal == "NONE":
            continue
        out.append((date.fromisoformat(str(event_time)[:10]), signal))
    return out


def _exit_reason(cycle: Cycle, exit_signals: list[tuple[date, str]]) -> str:
    """Best available exit reason for a closed cycle.

    Prefers a ``paper_exit_events`` signal dated within the cycle window;
    falls back to the closing trade's note, then a generic label.
    """
    if cycle.is_open or cycle.exit_date is None:
        return "—"
    matches = [sig for dt, sig in exit_signals if cycle.entry_date <= dt <= cycle.exit_date]
    if matches:
        return matches[-1]
    note = cycle.trades[-1].notes.strip()
    if note:
        # e.g. "ic_nifty_v1 auto-close: CLOSE_FULL" -> "CLOSE_FULL (auto-close)"
        if "auto-close:" in note:
            return f"{note.split('auto-close:')[-1].strip()} (auto-close)"
        return note
    return "flat close (no signal recorded)"


def _print_group(group: _Group, store: PaperStore, conn: sqlite3.Connection) -> None:
    trades = store.get_trades(group.strategy_name)
    if group.leg_roles is not None:
        wanted = set(group.leg_roles)
        trades = [t for t in trades if t.leg_role in wanted]
    if not trades:
        print(f"\n{group.label}: no trades found.")
        logger.warning("no_trades", group=group.label)
        return

    cycles = reconstruct_cycles(trades)
    exit_signals = _load_exit_signals(conn, group.strategy_name)
    closed = [c for c in cycles if not c.is_open]
    open_count = len(cycles) - len(closed)

    print(f"\n{group.label} — {len(closed)} closed cycle(s), {open_count} open")
    print(
        f"  {'#':>2}  {'Entry':<10}  {'Exit':<10}  {'Days':>4}  {'Credit/u':>9}  "
        f"{'Cost/u':>8}  {'Decay%':>7}  {'Cycle P&L':>14}  Exit reason"
    )
    for cycle in cycles:
        exit_str = cycle.exit_date.isoformat() if cycle.exit_date else "(open)"
        days_str = "—" if cycle.days_in_trade is None else str(cycle.days_in_trade)
        pnl_str = "(unrealized)" if cycle.is_open else format_money(cycle.realized_pnl, signed=True)
        credit_str = f"{cycle.entry_credit_per_unit:.2f}"
        cost_str = "—" if cycle.exit_cost_per_unit is None else f"{cycle.exit_cost_per_unit:.2f}"
        decay_str = "—" if cycle.decay_pct is None else f"{cycle.decay_pct:.1f}%"
        print(
            f"  {cycle.index:>2}  {cycle.entry_date.isoformat():<10}  {exit_str:<10}  "
            f"{days_str:>4}  {credit_str:>9}  {cost_str:>8}  {decay_str:>7}  "
            f"{pnl_str:>14}  {_exit_reason(cycle, exit_signals)}"
        )
    total = sum((c.realized_pnl for c in closed), Decimal("0"))
    print(f"  {'-' * 60}")
    print(f"  Total realized ({len(closed)} closed cycle(s)): {format_money(total, signed=True)}")


def main() -> None:
    """CLI entry point."""
    setup_logging(json=False, level="INFO")
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("target", help="alias (ic-all, cc, …) or an exact paper_* strategy name")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: DB not found at {args.db_path}", file=sys.stderr)
        raise SystemExit(1)

    try:
        groups = resolve_target(args.target)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    store = PaperStore(args.db_path)
    with sqlite3.connect(args.db_path) as conn:
        for group in groups:
            _print_group(group, store, conn)


if __name__ == "__main__":
    main()
