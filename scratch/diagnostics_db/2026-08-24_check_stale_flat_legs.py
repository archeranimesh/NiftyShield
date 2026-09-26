#!/usr/bin/env python3
"""Read-only diagnostic: report stale flat legs and identify which DB you're
looking at.

BUG-037 follow-up: the discovery scan behind BUG-037 found 54
(strategy_name, leg_role, instrument_key) tuples that are fully flat
(net BUY-SELL quantity == 0) but still carry state IN ('OPEN', 'DEFENDED')
in paper_trades. B037.5's re-run of scripts/dev/backfill_mark_trade_closed_overlay.py
against this session's data/portfolio/portfolio.sqlite found 0 — but that file
only has 134 total trade rows, far too small to be the DB the 54-row scan ran
against. This script exists to settle that "which DB am I even looking at"
question before anyone runs the real (writing) backfill anywhere.

Never writes. Never calls mark_trade_closed(). Pure SELECT + aggregation,
per CLAUDE.md Rule 1 (aggregate at the source, never dump raw rows).

Usage:
    python3 check_stale_flat_legs.py [--db-path PATH] [--verbose]

    --db-path   Defaults to data/portfolio/portfolio.sqlite relative to CWD.
                Point this explicitly at any candidate DB file to compare.
    --verbose   Print every stale tuple found (default: just the count +
                a handful of identifying facts about the DB file itself).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def check(db_path: Path, verbose: bool) -> int:
    """Report DB identity + stale-flat-leg count. Returns process exit code."""
    if not db_path.exists():
        print(f"ERROR: no file at {db_path}")
        return 2

    stat = db_path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

    print(f"DB path        : {db_path.resolve()}")
    print(f"File size      : {_fmt_bytes(stat.st_size)}")
    print(f"Last modified  : {mtime}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row

        total_rows, max_id = conn.execute("SELECT COUNT(*), MAX(id) FROM paper_trades").fetchone()
        print(f"paper_trades   : {total_rows} rows, max id = {max_id}")

        strategies = conn.execute(
            "SELECT strategy_name, COUNT(*) AS n FROM paper_trades "
            "GROUP BY strategy_name ORDER BY n DESC"
        ).fetchall()
        print(f"Strategies     : {len(strategies)} distinct")
        for row in strategies:
            print(f"  - {row['strategy_name']}: {row['n']} rows")

        latest = conn.execute("SELECT MAX(trade_date) FROM paper_trades").fetchone()[0]
        print(f"Latest trade_date: {latest}")

        # Same discovery query as scripts/dev/backfill_mark_trade_closed_overlay.py
        # — grouped sums only, never a raw row dump (Rule 1).
        stale = conn.execute(
            """
            SELECT strategy_name, leg_role, instrument_key,
                   SUM(CASE WHEN action = 'BUY' THEN quantity ELSE -quantity END) AS net_qty,
                   SUM(CASE WHEN state IN ('OPEN', 'DEFENDED') THEN 1 ELSE 0 END) AS open_rows,
                   COUNT(*) AS total_rows
            FROM paper_trades
            GROUP BY strategy_name, leg_role, instrument_key
            HAVING net_qty = 0 AND open_rows > 0
            """
        ).fetchall()
    finally:
        conn.close()

    print()
    print(f"Stale flat legs (net_qty=0, state IN OPEN/DEFENDED): {len(stale)}")
    if stale and verbose:
        for row in stale:
            print(
                f"  - {row['strategy_name']} / {row['leg_role']} / "
                f"{row['instrument_key']} "
                f"(open_rows={row['open_rows']}, total_rows={row['total_rows']})"
            )
    elif stale:
        by_strategy: dict[str, int] = {}
        for row in stale:
            by_strategy[row["strategy_name"]] = by_strategy.get(row["strategy_name"], 0) + 1
        for name, n in sorted(by_strategy.items(), key=lambda kv: -kv[1]):
            print(f"  - {name}: {n}")
        print("  (pass --verbose for the full per-leg list)")

    return 1 if stale else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/portfolio/portfolio.sqlite"),
        help="Path to the paper-trading SQLite DB (default: %(default)s, relative to CWD)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every stale (strategy_name, leg_role, instrument_key) tuple found",
    )
    args = parser.parse_args()

    exit_code = check(args.db_path, args.verbose)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
