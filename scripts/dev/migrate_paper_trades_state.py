#!/usr/bin/env python3
"""One-time DB migration: add ``state`` column to ``paper_trades``.

Idempotent — safe to run multiple times. Checks for column existence before
altering; prints a summary of what was done.

Usage:
    python -m scripts.dev.migrate_paper_trades_state
    python -m scripts.dev.migrate_paper_trades_state --db-path /path/to/db.sqlite
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

_SCRIPT_NAME = "scripts.dev.migrate_paper_trades_state"
logger = structlog.get_logger(_SCRIPT_NAME)


_SCRIPT_NAME = "scripts.dev.migrate_paper_trades_state"


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Return True if *column* exists in *table*."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def migrate(db_path: Path) -> None:
    """Add ``state`` column to ``paper_trades`` if not already present.

    The column is TEXT NOT NULL with a DEFAULT of 'OPEN' and a CHECK constraint
    that restricts values to the TradeState enum members.

    Args:
        db_path: Path to the portfolio SQLite database.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        if _column_exists(conn, "paper_trades", "state"):
            print(f"[{_SCRIPT_NAME}] 'state' column already exists — nothing to do.")
            return

        conn.execute(
            "ALTER TABLE paper_trades ADD COLUMN state TEXT NOT NULL DEFAULT 'OPEN'"
            " CHECK(state IN ('OPEN','DEFENDED','RE_ENTRY_PENDING'))"
        )
        conn.execute("UPDATE paper_trades SET state = 'OPEN'")
        conn.commit()

        count = conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
        print(f"[{_SCRIPT_NAME}] Added 'state' column; set {count} existing row(s) to 'OPEN'.")
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
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: DB not found at {args.db_path}", file=sys.stderr)
        sys.exit(1)

    migrate(args.db_path)


if __name__ == "__main__":
    setup_logging()
    main()
