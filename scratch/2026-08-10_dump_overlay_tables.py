"""Full raw dump of paper_overlay_pnl_snapshots, paper_leg_snapshots, and
paper_exit_events — every row, every column, no filtering, no aggregation.

Purpose: manual eyeball verification before running
scratch/2026-08-10_overlay_full_cleanup.py --execute. That script's DELETE
filters are scoped to overlay leg_role/leg_name patterns; this script instead
prints everything so Animesh can independently confirm the filters aren't
missing anything (or over-matching something they shouldn't), rather than
trusting the filter logic alone.

Read-only. No writes, no filtering — deliberately dumps ALL rows in each
table (including non-overlay/base-leg rows), not just the overlay-scoped
subset, so nothing is hidden from the review.

Usage:
    python3 scratch/2026-08-10_dump_overlay_tables.py > scratch/2026-08-10_overlay_tables_dump.txt
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_DB_PATH = Path("data/portfolio/portfolio.sqlite")

_TABLES = (
    "paper_overlay_pnl_snapshots",
    "paper_leg_snapshots",
    "paper_exit_events",
)


def dump_table(conn: sqlite3.Connection, table: str) -> None:
    """Print every column, every row of *table*, tab-separated with a header."""
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    rows = conn.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY rowid").fetchall()

    print(f"\n{'=' * 80}")
    print(f"TABLE: {table}  ({len(rows)} row(s) total, ALL rows — not overlay-filtered)")
    print(f"{'=' * 80}")
    print("\t".join(cols))
    for row in rows:
        print("\t".join("" if v is None else str(v) for v in row))


def main() -> None:
    conn = sqlite3.connect(_DB_PATH)
    for table in _TABLES:
        dump_table(conn, table)
    conn.close()


if __name__ == "__main__":
    main()
