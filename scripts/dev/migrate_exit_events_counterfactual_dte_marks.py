"""Migration script to add counterfactual_dte_marks to paper_exit_events."""

import argparse
from pathlib import Path

import structlog

from src.db import connect as _connect
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.dev.migrate_exit_events_counterfactual_dte_marks"
logger = structlog.get_logger(_SCRIPT_NAME)

_DEFAULT_DB = Path("data/portfolio/portfolio.sqlite")


def _run(db_path: Path, *, dry_run: bool) -> None:
    """Execute the migration."""
    statement = (
        "ALTER TABLE paper_exit_events "
        "ADD COLUMN counterfactual_dte_marks TEXT;"
    )

    if dry_run:
        print(statement)
        print()
        return

    with _connect(db_path) as conn:
        # Check if column already exists
        columns = conn.execute("PRAGMA table_info(paper_exit_events)").fetchall()
        column_names = [col["name"] for col in columns]
        
        if "counterfactual_dte_marks" in column_names:
            logger.info("migrate.skip", msg="Column counterfactual_dte_marks already exists")
            return
            
        logger.info("migrate.start")
        conn.execute(statement)
        logger.info("migrate.complete", msg="Added counterfactual_dte_marks column")


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
