"""Idempotent migration: add CLOSED to paper_trades state CHECK constraint.

BUG-6: The original CHECK constraint on `paper_trades.state` only permitted
'OPEN', 'DEFENDED', and 'RE_ENTRY_PENDING'. Adding TradeState.CLOSED requires
the constraint to be widened to include 'CLOSED'.

SQLite does not support ALTER TABLE ... MODIFY COLUMN, so the migration
rebuilds the table in-place using the standard CREATE/INSERT/DROP/RENAME pattern.

Safe to run multiple times — checks the current schema before migrating.

Usage:
    python scripts/dev/migrate_add_closed_state.py [--db-path PATH]
"""

import argparse
import sqlite3
from pathlib import Path

_SCRIPT_NAME = "scripts.dev.migrate_add_closed_state"


def migrate(db_path: Path) -> None:
    """Apply BUG-6 migration to the given database.

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

        if "'CLOSED'" in row[0]:
            log.info("migrate.skip", reason="CHECK constraint already includes CLOSED")
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
                                   CHECK(state IN ('OPEN','DEFENDED','RE_ENTRY_PENDING','CLOSED')),
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
        log.info("migrate.complete", db_path=str(db_path))


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/portfolio/portfolio.sqlite"),
        help="Path to portfolio SQLite DB (default: data/portfolio/portfolio.sqlite)",
    )
    args = parser.parse_args()
    migrate(args.db_path)


if __name__ == "__main__":
    main()
