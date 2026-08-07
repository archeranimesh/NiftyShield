#!/usr/bin/env python3
"""One-time backfill: correct drifted ``total_pnl`` in ``paper_nav_snapshots``.

SNAP-1's audit found 42 of 267 rows where ``total_pnl != unrealized_pnl +
realized_pnl`` (exact Decimal arithmetic, not a rounding artifact). Root
cause (SNAP-5): ``generate_track_snapshot`` (src/paper/track_snapshot.py)
wrote ``net_pnl`` — a display figure that dedupes overlay_cc against
overlay_collar_call — as ``total_pnl``, while ``unrealized_pnl``/
``realized_pnl`` were accumulated undeduped. Fixed at the source in
src/paper/track_snapshot.py and enforced at write time in
PaperStore.record_nav_snapshot(); this script only repairs the 42 rows that
predate both fixes.

Decision (2026-08-07, Animesh): Option A — backfill in place. Since
unrealized_pnl/realized_pnl are themselves correct on every row (only the
stored total_pnl drifted), this is a direct
``Decimal(realized_pnl) + Decimal(unrealized_pnl)`` rewrite of total_pnl per
bad row — no trade replay or LTP refetch. All arithmetic is Decimal, per
CLAUDE.md's Decimal-as-TEXT convention; no raw-SQL arithmetic.

Idempotent: only touches rows where the invariant currently fails; running
twice is a no-op the second time.

Usage:
    python -m scripts.dev.backfill_nav_total_pnl
    python -m scripts.dev.backfill_nav_total_pnl --db-path /path/to/db.sqlite
    python -m scripts.dev.backfill_nav_total_pnl --dry-run
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path

import structlog

from src.utils.logging import setup_logging

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.paper.constants import DEFAULT_DB_PATH

_SCRIPT_NAME = "scripts.dev.backfill_nav_total_pnl"
logger = structlog.get_logger(_SCRIPT_NAME)


def _find_bad_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return every paper_nav_snapshots row failing the total_pnl invariant.

    Pulled as (strategy_name, snapshot_date, unrealized_pnl, realized_pnl,
    total_pnl) only — no SELECT * — the Decimal comparison happens in
    Python since SQLite has no native Decimal type and these columns are
    TEXT-stored.
    """
    rows = conn.execute(
        "SELECT strategy_name, snapshot_date, unrealized_pnl, realized_pnl, total_pnl "
        "FROM paper_nav_snapshots"
    ).fetchall()
    bad = []
    for row in rows:
        expected = Decimal(row["unrealized_pnl"]) + Decimal(row["realized_pnl"])
        if Decimal(row["total_pnl"]) != expected:
            bad.append(row)
    return bad


def backfill(db_path: Path, dry_run: bool = False) -> int:
    """Recompute and overwrite total_pnl for every row failing the invariant.

    Args:
        db_path: Path to the portfolio SQLite database.
        dry_run: If True, report what would change without writing.

    Returns:
        Number of rows corrected (or that would be corrected, in dry-run mode).
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        bad_rows = _find_bad_rows(conn)

        if not bad_rows:
            print(f"[{_SCRIPT_NAME}] No invariant-violating rows found — nothing to do.")
            return 0

        print(f"[{_SCRIPT_NAME}] Found {len(bad_rows)} row(s) with total_pnl drift.")

        for row in bad_rows:
            corrected = Decimal(row["unrealized_pnl"]) + Decimal(row["realized_pnl"])
            print(
                f"  {row['strategy_name']} / {row['snapshot_date']}: "
                f"total_pnl {row['total_pnl']} -> {corrected}"
            )
            if not dry_run:
                conn.execute(
                    "UPDATE paper_nav_snapshots SET total_pnl = ? "
                    "WHERE strategy_name = ? AND snapshot_date = ?",
                    (str(corrected), row["strategy_name"], row["snapshot_date"]),
                )

        if dry_run:
            print(f"[{_SCRIPT_NAME}] Dry run — no rows written.")
        else:
            conn.commit()
            print(f"[{_SCRIPT_NAME}] Corrected {len(bad_rows)} row(s).")

        return len(bad_rows)
    finally:
        conn.close()


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
        help="Report what would change without writing.",
    )
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: DB not found at {args.db_path}", file=sys.stderr)
        sys.exit(1)

    backfill(args.db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    setup_logging()
    main()
