#!/usr/bin/env python3
"""One-time backfill: apply ``mark_trade_closed()`` to already-flat legs.

BUG-035: ``PaperStore.mark_trade_closed()`` existed but had zero callers
graph-wide until this session's fix wired it into every overlay close path
(``CCOverlayV1._record_close_trade``, ``PPOverlayV1._record_close_trade``,
``OverlayCloser.close_single_leg``/``close_collar_all``/``monetize_collar_put``).
Any leg that was already fully closed *before* that fix landed still has its
``paper_trades`` rows stuck at ``state IN ('OPEN', 'DEFENDED')`` — the fix only
prevents the problem going forward, it doesn't repair history.

This script finds every ``(strategy_name, leg_role, instrument_key)`` whose
rows sum to a flat position (``net_qty == 0``, BUY quantity minus SELL
quantity) but still carry a non-CLOSED state, and calls the real
``PaperStore.mark_trade_closed()`` for each — never raw SQL — so the
state-machine's own guard (``WHERE state IN ('OPEN', 'DEFENDED')``) stays the
single source of truth for what's a legal transition, per BUG-035's suggested
fix.

Idempotent: a tuple already fully CLOSED is not flat-but-open, so re-running
is always a no-op for it. ``--dry-run`` prints what would change without
writing.

Known instances at time of writing (BUG-035, 2026-08-24): overlay_pp legs
NSE_FO|61604 and NSE_FO|74009 — but this scans the whole table rather than
hardcoding those two, in case other legs were closed before the fix too.

Usage:
    python -m scripts.dev.backfill_mark_trade_closed_overlay
    python -m scripts.dev.backfill_mark_trade_closed_overlay --db-path /path/to/db.sqlite
    python -m scripts.dev.backfill_mark_trade_closed_overlay --dry-run
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import structlog

from src.utils.logging import setup_logging

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.paper.constants import DEFAULT_DB_PATH
from src.paper.store import PaperStore

_SCRIPT_NAME = "scripts.dev.backfill_mark_trade_closed_overlay"
logger = structlog.get_logger(_SCRIPT_NAME)


def _find_stale_flat_legs(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Return every (strategy_name, leg_role, instrument_key) that is flat
    (net BUY-SELL quantity == 0) but still has at least one row in
    state IN ('OPEN', 'DEFENDED').

    Pulled as grouped sums only, never a raw row dump, per Rule 1
    (aggregate at the source).
    """
    rows = conn.execute(
        """
        SELECT strategy_name, leg_role, instrument_key,
               SUM(CASE WHEN action = 'BUY' THEN quantity ELSE -quantity END) AS net_qty,
               SUM(CASE WHEN state IN ('OPEN', 'DEFENDED') THEN 1 ELSE 0 END) AS open_rows
        FROM paper_trades
        GROUP BY strategy_name, leg_role, instrument_key
        HAVING net_qty = 0 AND open_rows > 0
        """
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def backfill(db_path: Path, dry_run: bool) -> None:
    """Apply mark_trade_closed() to every stale-but-flat leg found.

    The discovery SQL nets quantity across a tuple's *entire* trade history,
    which is a candidate scan, not a final answer: if an instrument_key were
    ever reused across two separate open/close cycles (re-entry, or a roll
    where a new leg posts under the same key before the old one's close
    settles), the all-time sum could land on zero while a specific cycle is
    still genuinely open. Each candidate is re-verified against
    ``PaperStore.get_position()`` — the canonical, already-tested net_qty
    calculation — immediately before writing, so a false-positive candidate
    is skipped rather than incorrectly marked CLOSED.

    Args:
        db_path: Path to the portfolio SQLite database.
        dry_run: If True, only print what would change — no writes.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        stale = _find_stale_flat_legs(conn)
    finally:
        conn.close()

    if not stale:
        print(f"[{_SCRIPT_NAME}] No stale flat legs found — nothing to do.")
        return

    print(f"[{_SCRIPT_NAME}] Found {len(stale)} candidate stale flat leg(s):")
    for strategy_name, leg_role, instrument_key in stale:
        print(f"  - {strategy_name} / {leg_role} / {instrument_key}")

    if dry_run:
        print(f"[{_SCRIPT_NAME}] --dry-run: no changes written.")
        return

    store = PaperStore(db_path)
    applied = 0
    skipped: list[tuple[str, str, str]] = []
    failed: list[tuple[str, str, str, str]] = []
    for strategy_name, leg_role, instrument_key in stale:
        try:
            pos = store.get_position(strategy_name, leg_role, instrument_key)
            if pos.net_qty != 0:
                logger.warning(
                    "backfill_mark_trade_closed_overlay.skipped_not_flat",
                    strategy_name=strategy_name,
                    leg_role=leg_role,
                    instrument_key=instrument_key,
                    net_qty=pos.net_qty,
                )
                skipped.append((strategy_name, leg_role, instrument_key))
                continue
            store.mark_trade_closed(strategy_name, leg_role, instrument_key)
            logger.info(
                "backfill_mark_trade_closed_overlay.marked_closed",
                strategy_name=strategy_name,
                leg_role=leg_role,
                instrument_key=instrument_key,
            )
            applied += 1
        except Exception as exc:
            logger.error(
                "backfill_mark_trade_closed_overlay.failed",
                strategy_name=strategy_name,
                leg_role=leg_role,
                instrument_key=instrument_key,
                error=str(exc),
            )
            failed.append((strategy_name, leg_role, instrument_key, str(exc)))

    print(f"[{_SCRIPT_NAME}] mark_trade_closed() applied to {applied} leg(s).")
    if skipped:
        print(
            f"[{_SCRIPT_NAME}] Skipped {len(skipped)} candidate(s) — "
            "get_position() found a non-zero net_qty (stale all-time sum, not "
            "actually flat right now):"
        )
        for strategy_name, leg_role, instrument_key in skipped:
            print(f"  - {strategy_name} / {leg_role} / {instrument_key}")
    if failed:
        print(f"[{_SCRIPT_NAME}] {len(failed)} tuple(s) raised an error and were NOT applied:")
        for strategy_name, leg_role, instrument_key, error in failed:
            print(f"  - {strategy_name} / {leg_role} / {instrument_key}: {error}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite DB (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without writing.",
    )
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: DB not found at {args.db_path}", file=sys.stderr)
        sys.exit(1)

    backfill(args.db_path, args.dry_run)


if __name__ == "__main__":
    setup_logging()
    main()
