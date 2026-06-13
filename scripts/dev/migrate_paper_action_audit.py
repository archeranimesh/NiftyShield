"""Idempotent migration: create paper_action_audit table.

Adds the paper_action_audit table to the shared SQLite DB if it does not
already exist. Safe to run multiple times.

Usage::

    python -m scripts.dev.migrate_paper_action_audit
    python -m scripts.dev.migrate_paper_action_audit --db-path /path/to/portfolio.sqlite
"""

from __future__ import annotations

import argparse

import structlog

from src.db import connect
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.dev.migrate_paper_action_audit"
logger = structlog.get_logger(_SCRIPT_NAME)

_DDL = """
CREATE TABLE IF NOT EXISTS paper_action_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name   TEXT    NOT NULL,
    action_type     TEXT    NOT NULL,
    leg_role        TEXT    NOT NULL,
    price           TEXT    NOT NULL,
    qty             INTEGER NOT NULL,
    rationale       TEXT,
    executed_at     TEXT    NOT NULL
) STRICT;
"""


def run(db_path: str) -> None:
    """Apply migration against db_path.

    Args:
        db_path: Filesystem path to the SQLite database.
    """
    with connect(db_path) as conn:
        conn.executescript(_DDL)
    logger.info("migration.complete", table="paper_action_audit", db=db_path)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        default="data/portfolio/portfolio.sqlite",
        help="Path to portfolio.sqlite (default: data/portfolio/portfolio.sqlite)",
    )
    args = parser.parse_args()
    run(args.db_path)


if __name__ == "__main__":
    main()
