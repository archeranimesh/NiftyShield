#!/usr/bin/env python3
"""Near-Expiry Gamma Buy Strategy — Daily Watch Script.

This script runs daily to fetch option chains, compute gamma gearing,
manage the watchlist, calibrate percentiles, and send Telegram updates.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any

from src.market_calendar.holidays import is_trading_day

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Configure logging for the script.

    By default, logging is at INFO level. If UPSTOX_DEBUG is set to '1' in the
    environment, the logging level is set to DEBUG.
    """
    level = logging.DEBUG if os.getenv("UPSTOX_DEBUG") == "1" else logging.INFO
    log_format = "%(asctime)s %(levelname)s %(message)s"
    logging.basicConfig(level=level, format=log_format)


def resolve_expiries(today: date) -> tuple[date, date]:
    """Resolve the current-week and next-week expiry dates.

    Current-week expiry is the current week's Thursday (or preceding trading
    day if Thursday is a holiday). If today is Thursday and the market is open,
    today is used. If today is Thursday but the market is closed, or if today is
    after Thursday, current-week expiry shifts to the next week's Thursday.
    Next-week expiry is the Thursday (or preceding trading day) after that.

    Args:
        today: The reference date to resolve expiries for.

    Returns:
        A tuple of (current_week_expiry, next_week_expiry).
    """
    # weekday() is 0 for Monday, ..., 3 for Thursday
    weekday_diff = 3 - today.weekday()
    nominal_thursday = today + timedelta(days=weekday_diff)

    if today.weekday() == 3 and is_trading_day(today):
        current_week_nominal = today
        next_week_nominal = today + timedelta(weeks=1)
    else:
        if today.weekday() < 3:
            current_week_nominal = nominal_thursday
            next_week_nominal = nominal_thursday + timedelta(weeks=1)
        else:
            current_week_nominal = nominal_thursday + timedelta(weeks=1)
            next_week_nominal = nominal_thursday + timedelta(weeks=2)

    def _adjust_expiry(nom_thu: date) -> date:
        curr = nom_thu
        while not is_trading_day(curr):
            curr -= timedelta(days=1)
        return curr

    current_week_expiry = _adjust_expiry(current_week_nominal)
    next_week_expiry = _adjust_expiry(next_week_nominal)

    return current_week_expiry, next_week_expiry


def _fetch_and_snapshot(
    client: Any,
    expiries: tuple[date, date],
    today: date,
    snapshot_time: str,
    store: Any,
    conn: Any,
    dry_run: bool,
) -> list[Any]:
    """Fetch option chains and compute/store snapshots. (Stub)"""
    logger.info(
        "Stub: fetch_and_snapshot for expiries %s, today=%s, dry_run=%s",
        expiries,
        today,
        dry_run,
    )
    return []


def _update_watchlist(
    today_snaps: list[Any],
    current_week_expiry: date,
    today: date,
    store: Any,
    conn: Any,
    dry_run: bool,
) -> dict[str, int]:
    """Update the active watchlist. (Stub)"""
    logger.info(
        "Stub: update_watchlist for current_week_expiry %s, today=%s, dry_run=%s",
        current_week_expiry,
        today,
        dry_run,
    )
    return {"added": 0, "retained": 0, "removed": 0, "elevated": 0}


def main() -> None:
    """Main execution entry point."""
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Near-Expiry Gamma Buy Strategy Daily Watch"
    )
    parser.add_argument(
        "--morning",
        action="store_true",
        help="Skip watchlist update (morning run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip database updates and notifications",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Override reference date (YYYY-MM-DD)",
    )

    args = parser.parse_args()

    if args.date:
        try:
            today = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            logger.error("Invalid date format: %s. Use YYYY-MM-DD.", args.date)
            sys.exit(1)
    else:
        today = date.today()

    logger.info("Running daily watch for date: %s", today)

    current_week_expiry, next_week_expiry = resolve_expiries(today)
    logger.info("Resolved current-week expiry: %s", current_week_expiry)
    logger.info("Resolved next-week expiry: %s", next_week_expiry)

    # Stub instantiation / connection handling
    client = None
    store = None
    conn = None
    snapshot_time = datetime.now().strftime("%H:%M")

    snaps = _fetch_and_snapshot(
        client=client,
        expiries=(current_week_expiry, next_week_expiry),
        today=today,
        snapshot_time=snapshot_time,
        store=store,
        conn=conn,
        dry_run=args.dry_run,
    )

    if not args.morning:
        _update_watchlist(
            today_snaps=snaps,
            current_week_expiry=current_week_expiry,
            today=today,
            store=store,
            conn=conn,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
