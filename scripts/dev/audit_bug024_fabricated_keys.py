"""BUG-024 audit: check for fabricated symbol-style instrument_key rows.

Read-only diagnostic. Confirms whether IronCondorV2.enter()'s fabricated
`f"NSE_FO|NIFTY{strike}{CE|PE}"` instrument_key construction (see
docs/bugs/bugs.md BUG-024) has ever actually been persisted to
`paper_trades`, as opposed to sitting latent in the entry code path.

Usage:
    python -m scripts.dev.audit_bug024_fabricated_keys
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import structlog

from src.db import connect
from src.paper.constants import DEFAULT_DB_PATH
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.dev.audit_bug024_fabricated_keys"
logger = structlog.get_logger(_SCRIPT_NAME)

_QUERY = """
    SELECT
        strategy_name,
        leg_role,
        COUNT(*) AS n_rows,
        MIN(trade_date) AS earliest_trade_date,
        MAX(trade_date) AS latest_trade_date,
        SUM(CASE WHEN state = 'OPEN' THEN 1 ELSE 0 END) AS n_still_open
    FROM paper_trades
    WHERE strategy_name LIKE 'paper_ic_nifty_v2%'
      AND instrument_key GLOB 'NSE_FO|NIFTY*[CP]E'
    GROUP BY strategy_name, leg_role
    ORDER BY strategy_name, leg_role
"""


def run(db_path: str = str(DEFAULT_DB_PATH)) -> list[sqlite3.Row]:
    """Run the BUG-024 fabricated-key audit query.

    Args:
        db_path: Path to the portfolio SQLite DB. Defaults to the shared
            live DB (``DEFAULT_DB_PATH``).

    Returns:
        One aggregated row per (strategy_name, leg_role) that has at least
        one fabricated symbol-style instrument_key. Empty list means clean.
    """
    with connect(Path(db_path)) as conn:
        rows = conn.execute(_QUERY).fetchall()

    logger.info(
        "audit_bug024.completed",
        db_path=db_path,
        n_groups_flagged=len(rows),
    )
    return rows


def _print_report(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print("BUG-024 audit: no fabricated-key rows found for paper_ic_nifty_v2*.")
        return

    header = f"{'strategy_name':<30} {'leg_role':<20} {'n_rows':>7} {'earliest':>12} {'latest':>12} {'open':>6}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['strategy_name']:<30} {r['leg_role']:<20} {r['n_rows']:>7} "
            f"{r['earliest_trade_date']:>12} {r['latest_trade_date']:>12} {r['n_still_open']:>6}"
        )


def main() -> None:
    setup_logging()
    rows = run()
    _print_report(rows)


if __name__ == "__main__":
    main()
