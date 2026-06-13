"""Idempotent migration: add instrument_key to paper_trades UNIQUE constraint.

BUG-4: The old constraint was (strategy_name, leg_role, trade_date, action).
A same-day close of a rolled leg (different instrument_key) silently no-oped,
causing _close_leg to think the trade was already recorded and triggering
_reentry_notification on every daemon tick.

New constraint: (strategy_name, leg_role, instrument_key, trade_date, action).

Safe to run multiple times — checks current constraint before migrating.

Usage:
    python scripts/dev/migrate_paper_trades_unique.py [--db-path PATH]
"""

import argparse
import sqlite3
from pathlib import Path

_SCRIPT_NAME = "scripts.dev.migrate_paper_trades_unique"


def migrate(db_path: Path) -> None:
    """Apply BUG-4 migration to the given database.

    Args:
        db_path: Path to the portfolio SQLite database.
    """
    import structlog

    from src.utils.logging import setup_logging

    setup_logging()
    log = structlog.get_logger(_SCRIPT_NAME)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='paper_trades'"
        ).fetchone()

        if row is None:
            log.info("migrate.skip", reason="paper_trades table does not exist")
            return

        if "instrument_key, trade_date" in row[0]:
            log.info("migrate.skip", reason="constraint already includes instrument_key")
            return

        log.info("migrate.start", db_path=str(db_path))
        conn.executescript(
            """
            PRAGMA foreign_keys = OFF;
            BEGIN;
            CREATE TABLE paper_trades_new (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name  TEXT NOT NULL,
                leg_role       TEXT NOT NULL,
                instrument_key TEXT NOT NULL,
                trade_date     TEXT NOT NULL,
                action         TEXT NOT NULL,
                quantity       INTEGER NOT NULL,
                price          TEXT NOT NULL,
                notes          TEXT NOT NULL DEFAULT '',
                ivr_at_entry   REAL DEFAULT NULL,
                state          TEXT NOT NULL DEFAULT 'OPEN'
                                   CHECK(state IN ('OPEN','DEFENDED','RE_ENTRY_PENDING')),
                UNIQUE(strategy_name, leg_role, instrument_key, trade_date, action)
            );
            INSERT OR IGNORE INTO paper_trades_new
                SELECT id, strategy_name, leg_role, instrument_key, trade_date,
                       action, quantity, price, notes, ivr_at_entry, state
                FROM paper_trades;
            DROP TABLE paper_trades;
            ALTER TABLE paper_trades_new RENAME TO paper_trades;
            CREATE INDEX IF NOT EXISTS idx_paper_trades_strategy_leg
                ON paper_trades(strategy_name, leg_role, trade_date);
            COMMIT;
            PRAGMA foreign_keys = ON;
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
        log.info("migrate.done", rows_preserved=count)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/portfolio/portfolio.sqlite"),
        help="Path to SQLite DB (default: data/portfolio/portfolio.sqlite)",
    )
    args = parser.parse_args()
    migrate(args.db_path)


if __name__ == "__main__":
    main()
