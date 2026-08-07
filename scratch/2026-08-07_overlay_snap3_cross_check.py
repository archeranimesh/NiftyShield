"""SNAP-3 cross-check: confirm CC/PP/Collar overlay trade coverage in the live DB.

Run this directly on the host machine (not just inside a mounted/synced copy) to rule out
a stale-mount explanation for "paper_nifty_overlay has zero rows" — see
docs/plan/paper-ic-daily-snapshot/stories.md SNAP-3 findings, DB_REGISTRY.md.

Usage:
    python scratch/2026-08-07_overlay_snap3_cross_check.py
    python scratch/2026-08-07_overlay_snap3_cross_check.py --db-path /custom/path/portfolio.sqlite

Prints:
    - Which DB file it actually opened (absolute path + mtime + size) — so there's no ambiguity
      about which copy answered the query.
    - Every distinct strategy_name in paper_trades, paper_nav_snapshots, paper_leg_snapshots,
      paper_overlay_pnl_snapshots.
    - Row counts for the overlay leg_roles specifically (overlay_cc, overlay_pp,
      overlay_collar_call, overlay_collar_put) across paper_trades.
    - The 5 most recent paper_trades rows overall, so a very recent entry (possibly not yet
      reflected in the strategy_name aggregate view) is still visible.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")

OVERLAY_LEG_ROLES = (
    "overlay_cc",
    "overlay_pp",
    "overlay_collar_call",
    "overlay_collar_put",
)


def _fmt_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    db_path = args.db_path.resolve()
    if not db_path.exists():
        print(f"ERROR: {db_path} does not exist.")
        return

    print(f"Opened DB: {db_path}")
    print(f"  size: {db_path.stat().st_size:,} bytes")
    print(f"  mtime: {_fmt_mtime(db_path)}")
    print()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    for table in (
        "paper_trades",
        "paper_nav_snapshots",
        "paper_leg_snapshots",
        "paper_overlay_pnl_snapshots",
    ):
        if not _table_exists(conn, table):
            print(f"{table}: TABLE DOES NOT EXIST in this DB")
            continue
        rows = conn.execute(
            f"SELECT DISTINCT strategy_name, COUNT(*) as n FROM {table} "
            f"GROUP BY strategy_name ORDER BY strategy_name"
        ).fetchall()
        print(f"{table} — distinct strategy_name (row count):")
        if not rows:
            print("  (empty table)")
        for r in rows:
            print(f"  {r['strategy_name']!r}: {r['n']}")
        print()

    print("paper_trades — overlay leg_role counts (overlay_cc/overlay_pp/overlay_collar_*):")
    for leg_role in OVERLAY_LEG_ROLES:
        n = conn.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE leg_role = ?", (leg_role,)
        ).fetchone()[0]
        print(f"  {leg_role}: {n}")
    print()

    print("paper_trades — 5 most recent rows (by id desc, no created_at column on this table):")
    rows = conn.execute(
        "SELECT id, strategy_name, leg_role, instrument_key, trade_date, action, quantity, price "
        "FROM paper_trades ORDER BY id DESC LIMIT 5"
    ).fetchall()
    for r in rows:
        print(f"  {dict(r)}")

    conn.close()


if __name__ == "__main__":
    main()
