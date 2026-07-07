#!/usr/bin/env python3
"""One-time DB migration: create ``paper_strategies`` table.

Idempotent — safe to run multiple times. Checks for table existence before
creating; prints a summary of what was done.

Usage:
    python -m scripts.dev.migrate_paper_strategies
    python -m scripts.dev.migrate_paper_strategies --db-path /path/to/db.sqlite
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

_SCRIPT_NAME = "scripts.dev.migrate_paper_strategies"
logger = structlog.get_logger(_SCRIPT_NAME)


_SCRIPT_NAME = "scripts.dev.migrate_paper_strategies"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Return True if *table* exists."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def migrate(db_path: Path) -> None:
    """Create the ``paper_strategies`` table if not already present.

    Args:
        db_path: Path to the portfolio SQLite database.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        if _table_exists(conn, "paper_strategies"):
            print(f"[{_SCRIPT_NAME}] 'paper_strategies' table already exists — nothing to do.")
            return

        conn.execute(
            """
            CREATE TABLE paper_strategies (
                strategy_name TEXT PRIMARY KEY,
                proxy_delta_breach_count INTEGER NOT NULL DEFAULT 0
            ) STRICT;
            """
        )
        conn.commit()
        print(f"[{_SCRIPT_NAME}] Created 'paper_strategies' table.")
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
