#!/usr/bin/env python3
"""One-time cleanup: remove overlay_cc rows that duplicate overlay_collar_call.

Background
----------
Before the dedup guard was added to paper_3track_overlay_entry.py, entering a
collar also entered an overlay_cc SELL on the same instrument key.  This caused
the short call to appear under two leg_roles, double-counting it in P&L snapshots.

What this script does
---------------------
For every (strategy_name, instrument_key, trade_date) tuple where both
overlay_cc and overlay_collar_call exist with the same action:

  Case A — identical prices (exact duplicate, e.g. Jun-9 cycle, NSE_FO|65900):
    DELETE the overlay_cc rows.

  Case B — different prices (entered in separate runs, e.g. May-11 cycle,
    NSE_FO|71474 @ 221.38 for cc vs 220.62 for collar_call):
    UPDATE overlay_cc.state → 'DEDUP_CLOSED' and overlay_cc.notes to record
    the dedup reason.  Keeps the historical record intact while excluding these
    rows from active position calculations (which filter on state='OPEN').

Run
---
    python scripts/dev/cleanup_cc_collar_dedup.py [--dry-run] [--db-path PATH]

Always run with --dry-run first to review what will change.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import structlog

from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.dev.cleanup_cc_collar_dedup"
logger = structlog.get_logger(_SCRIPT_NAME)


sys.path.insert(0, str(Path(__file__).parent.parent.parent))

DEFAULT_DB = Path("data/portfolio/portfolio.sqlite")


def _find_duplicates(conn: sqlite3.Connection) -> list[dict]:
    """Return rows where overlay_cc and overlay_collar_call share the same key+date+action."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            cc.rowid        AS cc_rowid,
            cc.strategy_name,
            cc.instrument_key,
            cc.trade_date,
            cc.action,
            cc.quantity     AS cc_qty,
            cc.price        AS cc_price,
            cc.state        AS cc_state,
            col.rowid       AS collar_rowid,
            col.price       AS collar_price,
            col.state       AS collar_state
        FROM paper_trades cc
        JOIN paper_trades col
          ON  cc.strategy_name   = col.strategy_name
          AND cc.instrument_key  = col.instrument_key
          AND cc.trade_date      = col.trade_date
          AND cc.action          = col.action
        WHERE cc.leg_role  = 'overlay_cc'
          AND cc.state    != 'CLOSED'
          AND col.leg_role = 'overlay_collar_call'
        ORDER BY cc.strategy_name, cc.instrument_key, cc.trade_date
        """
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def run(db_path: Path, dry_run: bool) -> None:
    """Execute the cleanup.

    Args:
        db_path: Path to portfolio.sqlite.
        dry_run: If True, print what would happen without modifying anything.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    dupes = _find_duplicates(conn)

    if not dupes:
        print("No duplicate overlay_cc / overlay_collar_call rows found. Nothing to do.")
        conn.close()
        return

    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"\n[{mode}] Found {len(dupes)} duplicate row(s):\n")
    print(
        f"  {'rowid':>6}  {'strategy':28}  {'key':20}  {'date':10}  "
        f"{'cc_px':>8}  {'col_px':>8}  action"
    )
    print("  " + "─" * 92)
    for d in dupes:
        print(
            f"  {d['cc_rowid']:>6}  {d['strategy_name']:28}  {d['instrument_key']:20}  "
            f"{d['trade_date']:10}  {d['cc_price']:>8}  {d['collar_price']:>8}  {d['action']}"
        )

    if dry_run:
        print("\n  Re-run without --dry-run to apply changes.")
        conn.close()
        return

    cur = conn.cursor()
    deleted = 0
    dedup_closed = 0

    for d in dupes:
        same_price = abs(float(d["cc_price"]) - float(d["collar_price"])) < 0.01

        if same_price:
            # Exact duplicate — safe to delete
            cur.execute("DELETE FROM paper_trades WHERE rowid = ?", (d["cc_rowid"],))
            deleted += 1
            print(
                f"  DELETED  rowid={d['cc_rowid']}  {d['strategy_name']}  "
                f"{d['instrument_key']}  {d['trade_date']}  overlay_cc @ {d['cc_price']}"
            )
        else:
            # Different prices — mark CLOSED and record reason in notes.
            # state='CLOSED' removes it from active position queries; the
            # original price is preserved in the row for audit purposes.
            note = (
                f"DEDUP: overlay_collar_call @ {d['collar_price']} is canonical. "
                f"This overlay_cc entry @ {d['cc_price']} was entered in a separate "
                "run and is a historical duplicate. Marked CLOSED to exclude from "
                "active position calculations."
            )
            cur.execute(
                "UPDATE paper_trades SET state = 'CLOSED', notes = ? WHERE rowid = ?",
                (note, d["cc_rowid"]),
            )
            dedup_closed += 1
            print(
                f"  CLOSED(dedup)  rowid={d['cc_rowid']}  {d['strategy_name']}  "
                f"{d['instrument_key']}  {d['trade_date']}  "
                f"overlay_cc @ {d['cc_price']} (collar_call @ {d['collar_price']})"
            )

    conn.commit()
    conn.close()
    print(f"\nDone. {deleted} row(s) deleted, {dedup_closed} row(s) marked DEDUP_CLOSED.")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB,
        help=f"Path to SQLite DB (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying the DB.",
    )
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: DB not found at {args.db_path}", file=sys.stderr)
        sys.exit(1)

    run(args.db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    setup_logging()
    main()
