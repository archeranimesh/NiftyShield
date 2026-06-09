#!/usr/bin/env python3
"""One-shot data correction for spurious Jun8 overlay_cc trades on instrument 71474.

BUG-7 fix (see docs/plan/council-refactor/stories_bugs_overlay_state.md):

  Problem 1 — SELL 65 @ 12.60 on 2026-06-08 (instrument 71474):
    Spurious new open on a 22-DTE near-worthless expiring instrument written during roll.
    Should not exist. Deleted.

  Problem 2 — BUY 130 @ 12.60 on 2026-06-08 (instrument 71474):
    Close qty must match the original SELL qty (65), not 130.
    Updated: quantity 130 → 65.

  After these two corrections, per-track net on 71474 = -65 + 65 = 0 (correctly closed).

Usage:
    python scripts/dev/fix_overlay_cc_jun8.py                    # dry-run (safe, shows changes)
    python scripts/dev/fix_overlay_cc_jun8.py --execute          # apply changes
    python scripts/dev/fix_overlay_cc_jun8.py --db path/to/db    # custom DB path

IMPORTANT: Run this BEFORE deploying the BUG-6 migration (migrate_add_closed_state.py).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "portfolio" / "portfolio.sqlite"

_INSTRUMENT_PATTERN = "%71474%"
_CLOSE_DATE = "2026-06-08"
_LEG_ROLE = "overlay_cc"
_PRICE = "12.6"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _show_current(conn: sqlite3.Connection) -> None:
    print("\n── Current overlay_cc rows (all dates) ──")
    rows = conn.execute(
        "SELECT id, strategy_name, instrument_key, trade_date, action, quantity, price, state"
        " FROM paper_trades"
        " WHERE leg_role = ?"
        " ORDER BY strategy_name, trade_date, id",
        (_LEG_ROLE,),
    ).fetchall()
    for r in rows:
        print(
            f"  id={r['id']:4d} | {r['strategy_name']:<22} | {r['instrument_key']}"
            f" | {r['trade_date']} | {r['action']:<4} | qty={r['quantity']:4d}"
            f" | price={r['price']:<8} | {r['state']}"
        )

    print("\n── Net qty on 71474 per strategy (before fix) ──")
    rows = conn.execute(
        "SELECT strategy_name,"
        "  SUM(CASE WHEN action='SELL' THEN -quantity ELSE quantity END) AS net_qty"
        " FROM paper_trades"
        " WHERE leg_role = ? AND instrument_key LIKE ?"
        " GROUP BY strategy_name",
        (_LEG_ROLE, _INSTRUMENT_PATTERN),
    ).fetchall()
    for r in rows:
        print(f"  {r['strategy_name']:<22}: net_qty = {r['net_qty']}")


def _rows_to_delete(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """SELL 65 @ 12.6 on Jun8 — spurious open on expiring instrument."""
    return conn.execute(
        "SELECT id, strategy_name, instrument_key, trade_date, action, quantity, price"
        " FROM paper_trades"
        " WHERE leg_role = ?"
        "   AND instrument_key LIKE ?"
        "   AND trade_date = ?"
        "   AND action = 'SELL'"
        "   AND CAST(price AS REAL) = CAST(? AS REAL)",
        (_LEG_ROLE, _INSTRUMENT_PATTERN, _CLOSE_DATE, _PRICE),
    ).fetchall()


def _rows_to_update(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """BUY 130 @ 12.6 on Jun8 — qty should be 65."""
    return conn.execute(
        "SELECT id, strategy_name, instrument_key, trade_date, action, quantity, price"
        " FROM paper_trades"
        " WHERE leg_role = ?"
        "   AND instrument_key LIKE ?"
        "   AND trade_date = ?"
        "   AND action = 'BUY'"
        "   AND quantity = 130"
        "   AND CAST(price AS REAL) = CAST(? AS REAL)",
        (_LEG_ROLE, _INSTRUMENT_PATTERN, _CLOSE_DATE, _PRICE),
    ).fetchall()


def _dry_run(conn: sqlite3.Connection) -> None:
    _show_current(conn)

    to_delete = _rows_to_delete(conn)
    to_update = _rows_to_update(conn)

    print(f"\n── DRY RUN — {len(to_delete)} row(s) to DELETE ──")
    for r in to_delete:
        print(
            f"  DELETE id={r['id']} | {r['strategy_name']} | {r['instrument_key']}"
            f" | {r['trade_date']} | {r['action']} qty={r['quantity']} @ {r['price']}"
        )

    print(f"\n── DRY RUN — {len(to_update)} row(s) to UPDATE (qty 130 → 65) ──")
    for r in to_update:
        print(
            f"  UPDATE id={r['id']} | {r['strategy_name']} | {r['instrument_key']}"
            f" | {r['trade_date']} | {r['action']} qty={r['quantity']} → 65 @ {r['price']}"
        )

    if not to_delete and not to_update:
        print("\n  Nothing to do — DB may already be clean.")
    else:
        print("\nRe-run with --execute to apply.")


def _execute(conn: sqlite3.Connection) -> None:
    _show_current(conn)

    to_delete = _rows_to_delete(conn)
    to_update = _rows_to_update(conn)

    if not to_delete and not to_update:
        print("\nNothing to do — DB already clean.")
        return

    with conn:
        # Step 1: delete spurious SELL rows
        for r in to_delete:
            conn.execute("DELETE FROM paper_trades WHERE id = ?", (r["id"],))
            print(
                f"  DELETED id={r['id']} | {r['strategy_name']} | {r['action']} qty={r['quantity']}"
            )

        # Step 2: fix BUY 130 → BUY 65
        for r in to_update:
            conn.execute("UPDATE paper_trades SET quantity = 65 WHERE id = ?", (r["id"],))
            print(f"  UPDATED id={r['id']} | {r['strategy_name']} | qty 130 → 65")

    # Step 3: verify net qty on 71474 is now 0
    print("\n── Net qty on 71474 per strategy (after fix) ──")
    rows = conn.execute(
        "SELECT strategy_name,"
        "  SUM(CASE WHEN action='SELL' THEN -quantity ELSE quantity END) AS net_qty"
        " FROM paper_trades"
        " WHERE leg_role = ? AND instrument_key LIKE ?"
        " GROUP BY strategy_name",
        (_LEG_ROLE, _INSTRUMENT_PATTERN),
    ).fetchall()
    ok = True
    for r in rows:
        status = "✓" if r["net_qty"] == 0 else "✗ UNEXPECTED"
        print(f"  {r['strategy_name']:<22}: net_qty = {r['net_qty']}  {status}")
        if r["net_qty"] != 0:
            ok = False

    # Step 4: show remaining overlay_cc rows
    print("\n── Remaining overlay_cc rows ──")
    rows = conn.execute(
        "SELECT id, strategy_name, instrument_key, trade_date, action, quantity, price, state"
        " FROM paper_trades"
        " WHERE leg_role = ?"
        " ORDER BY strategy_name, trade_date, id",
        (_LEG_ROLE,),
    ).fetchall()
    for r in rows:
        print(
            f"  id={r['id']:4d} | {r['strategy_name']:<22} | {r['instrument_key']}"
            f" | {r['trade_date']} | {r['action']:<4} | qty={r['quantity']:4d}"
            f" | price={r['price']:<8} | {r['state']}"
        )

    if not ok:
        print("\n⚠ Net qty check FAILED — investigate before proceeding.", file=sys.stderr)
        sys.exit(1)
    else:
        print("\n✓ Data correction complete.")
        print(
            "  Next step: run migrate_add_closed_state.py, then manually mark 71474 rows as CLOSED."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--execute", action="store_true", help="Apply changes (default: dry-run)")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to SQLite DB")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: DB not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = _connect(db_path)

    if args.execute:
        print(f"EXECUTE mode — writing to {db_path}")
        _execute(conn)
    else:
        print(f"DRY RUN mode — reading from {db_path}")
        _dry_run(conn)


if __name__ == "__main__":
    main()
