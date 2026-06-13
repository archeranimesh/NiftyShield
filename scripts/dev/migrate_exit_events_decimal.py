"""Migrate paper_exit_events monetary columns from REAL to TEXT.

Affected columns: ltp, mid, bid, ask, entry_price, threshold_value.

SQLite does not support ALTER COLUMN, so this migration uses the
rename-recreate pattern:
  1. Rename paper_exit_events → paper_exit_events_old
  2. Create paper_exit_events with TEXT columns (matches current _SCHEMA)
  3. INSERT ... SELECT with CAST(col AS TEXT) from old table
  4. Rebuild indexes
  5. DROP paper_exit_events_old

Idempotent: re-running after completion is a no-op (old table absent).

Usage:
    python -m scripts.dev.migrate_exit_events_decimal [--db PATH]
    python -m scripts.dev.migrate_exit_events_decimal --dry-run
"""

import argparse
import sys
from pathlib import Path

import structlog

from src.db import connect as _connect
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.dev.migrate_exit_events_decimal"
logger = structlog.get_logger(_SCRIPT_NAME)

_DEFAULT_DB = Path("data/portfolio/portfolio.sqlite")


def _run(db_path: Path, *, dry_run: bool) -> None:
    """Execute the migration.

    Args:
        db_path: Path to the SQLite database file.
        dry_run: If True, print the SQL without executing.
    """
    statements = [
        # Step 1 – rename old table
        "ALTER TABLE paper_exit_events RENAME TO paper_exit_events_old;",
        # Step 2 – create new table with TEXT monetary columns
        """CREATE TABLE paper_exit_events (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name           TEXT    NOT NULL,
    leg_name                TEXT    NOT NULL,
    trade_id                TEXT    NOT NULL,
    snapshot_id             INTEGER,
    event_time              TEXT    NOT NULL,
    detected_by             TEXT    NOT NULL,
    exit_signal             TEXT    NOT NULL,
    severity                TEXT    NOT NULL,
    ltp                     TEXT,
    mid                     TEXT,
    bid                     TEXT,
    ask                     TEXT,
    delta                   REAL,
    dte                     INTEGER,
    entry_price             TEXT    NOT NULL,
    threshold_value         TEXT,
    delta_stop_would_fire   INTEGER,
    premium_stop_would_fire INTEGER,
    actual_rule_used        TEXT,
    status                  TEXT    NOT NULL DEFAULT 'OPEN',
    notes                   TEXT,
    created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);""",
        # Step 3 – copy data, casting REAL columns to TEXT
        """INSERT INTO paper_exit_events
    SELECT
        id, strategy_name, leg_name, trade_id, snapshot_id,
        event_time, detected_by, exit_signal, severity,
        CAST(ltp AS TEXT),
        CAST(mid AS TEXT),
        CAST(bid AS TEXT),
        CAST(ask AS TEXT),
        delta, dte,
        CAST(entry_price AS TEXT),
        CAST(threshold_value AS TEXT),
        delta_stop_would_fire, premium_stop_would_fire, actual_rule_used,
        status, notes, created_at
    FROM paper_exit_events_old;""",
        # Step 4 – recreate indexes
        "CREATE INDEX IF NOT EXISTS idx_exit_events_strategy_leg ON paper_exit_events (strategy_name, leg_name, status);",
        "CREATE INDEX IF NOT EXISTS idx_exit_events_trade ON paper_exit_events (trade_id, exit_signal);",
        "CREATE INDEX IF NOT EXISTS idx_exit_events_open ON paper_exit_events (status, event_time) WHERE status = 'OPEN';",
        # Step 5 – drop old table
        "DROP TABLE paper_exit_events_old;",
    ]

    if dry_run:
        for stmt in statements:
            print(stmt)
            print()
        return

    with _connect(db_path) as conn:
        # Check whether migration has already been applied (old table absent)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='paper_exit_events_old'"
        ).fetchone()
        if row is not None:
            logger.warning(
                "migrate.already_in_progress",
                hint="paper_exit_events_old exists — previous run may have failed. "
                "Inspect the DB before re-running.",
            )
            sys.exit(1)

        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='paper_exit_events'"
        ).fetchone()
        if row is None:
            logger.info("migrate.no_table", msg="paper_exit_events not found — nothing to migrate")
            return

        old_count = conn.execute("SELECT COUNT(*) FROM paper_exit_events").fetchone()[0]
        logger.info("migrate.start", rows=old_count)

        for stmt in statements:
            conn.execute(stmt)

        new_count = conn.execute("SELECT COUNT(*) FROM paper_exit_events").fetchone()[0]
        if new_count != old_count:
            raise RuntimeError(
                f"Row count mismatch after migration: old={old_count} new={new_count}"
            )

        logger.info("migrate.complete", rows_migrated=new_count)


def main() -> None:
    """CLI entry point."""
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=_DEFAULT_DB, help="Path to portfolio.sqlite")
    parser.add_argument("--dry-run", action="store_true", help="Print SQL without executing")
    args = parser.parse_args()

    _run(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
