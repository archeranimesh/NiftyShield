"""Backfill the previous trading day's MF NAV snapshots.

AMFI publishes NAVs at ~21:00–23:00 IST.  The afternoon snapshot
(daily_snapshot.py, 15:45) therefore captures T-2 NAV tagged as T-1 date.
This script runs at 09:15 IST — after AMFI has settled — and upserts the
correct NAV for the previous trading day, fixing that stale value.

MFStore.upsert_nav_snapshot is idempotent on (amfi_code, snapshot_date), so
re-running is always safe.

Usage:
    # Backfill previous trading day (normal cron path)
    python -m scripts.morning_nav

    # Manual override for a specific date
    python -m scripts.morning_nav --date 2026-04-21

    # Custom DB path
    python -m scripts.morning_nav --db-path data/portfolio/portfolio.sqlite

Cron (weekdays at 09:15 IST):
    15 9 * * 1-5 cd /path/to/NiftyShield && /path/to/python -m scripts.morning_nav >> logs/snapshot.log 2>&1
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.market_calendar.holidays import prev_trading_day  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_morning_nav(target_date: date, db_path: Path) -> int:
    """Fetch AMFI NAVs and upsert snapshots for target_date.

    Args:
        target_date: The trading day whose NAV snapshot should be updated.
        db_path: Path to the portfolio SQLite database.

    Returns:
        0 on success, 1 on any error.
    """
    from dotenv import load_dotenv

    from src.mf.store import MFStore
    from src.mf.tracker import MFTracker

    load_dotenv()

    if not db_path.exists():
        logger.error("DB not found at %s", db_path)
        return 1

    logger.info("Morning NAV backfill for %s", target_date.isoformat())
    try:
        store = MFStore(db_path)
        pnl = MFTracker(store).record_snapshot(snapshot_date=target_date)
        logger.info(
            "NAV backfill complete — %d schemes updated, portfolio value: %s",
            len(pnl.schemes),
            pnl.total_current_value,
        )
        return 0
    except Exception:
        logger.exception("NAV backfill failed for %s", target_date.isoformat())
        return 1


def main() -> int:
    """Parse args and run the NAV backfill."""
    parser = argparse.ArgumentParser(
        description="Backfill previous trading day MF NAV snapshots from AMFI"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/portfolio/portfolio.sqlite"),
        help="Path to portfolio SQLite DB (default: data/portfolio/portfolio.sqlite)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help=(
            "YYYY-MM-DD: target date to backfill (default: previous trading day). "
            "Use for manual recovery when cron missed a day."
        ),
    )
    args = parser.parse_args()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if args.date:
        target_date = date.fromisoformat(args.date)
        print(f"[{now}] Manual NAV backfill for {target_date.isoformat()}")
    else:
        target_date = prev_trading_day(date.today())
        print(f"[{now}] Morning NAV backfill — target date: {target_date.isoformat()}")

    return run_morning_nav(target_date, args.db_path)


if __name__ == "__main__":
    sys.exit(main())
