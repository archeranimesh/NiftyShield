#!/usr/bin/env python3
"""System healthcheck script for NiftyShield.

Validates:
1. Trading day guard (exits early silently on holidays).
2. Database accessibility.
3. Snapshot recency in daily_snapshots (for today).
4. Paper snapshot recency in paper_nav_snapshots (for today).
5. India VIX data recency (warns if > 2 days stale).
6. Disk space (warns if < 500 MB free).

Fires a Telegram alert if any check fails or warns, and exits 1.
Runs silently and exits 0 on success.
"""

import argparse
import asyncio
import shutil
import sys
from datetime import date
from pathlib import Path

import structlog

from src.backtest.vix_ingest import load_vix_series
from src.config import settings
from src.db import connect
from src.market_calendar.holidays import is_trading_day
from src.notifications.telegram import build_notifier
from src.utils.logging import setup_logging

logger = structlog.get_logger()


def run_checks(target_date: date, db_path: Path, vix_dir: Path) -> tuple[bool, list[str]]:
    """Execute all system health checks.

    Args:
        target_date: Date to check snapshots against.
        db_path: Path to SQLite database.
        vix_dir: Path to VIX data directory.

    Returns:
        Tuple of (has_failure_or_warning, list_of_status_messages).
    """
    has_issue = False
    messages = []

    # Check 1: DB Accessibility
    db_ok = False
    try:
        with connect(db_path) as conn:
            conn.execute("SELECT 1").fetchone()
            db_ok = True
            messages.append("✅ DB: accessible")
    except Exception as e:
        db_ok = False
        has_issue = True
        logger.error("Database connection failed", error=str(e), db_path=str(db_path))
        messages.append("❌ DB: inaccessible")

    # Check 2: Snapshot recency (daily_snapshots)
    if not db_ok:
        messages.append("❌ daily_snapshots: skip (DB inaccessible)")
        has_issue = True
    else:
        try:
            with connect(db_path) as conn:
                row = conn.execute(
                    "SELECT 1 FROM daily_snapshots WHERE snapshot_date = ? LIMIT 1",
                    (target_date.isoformat(),),
                ).fetchone()
                if row:
                    messages.append("✅ daily_snapshots: ok")
                else:
                    messages.append("❌ daily_snapshots: no row for today")
                    has_issue = True
        except Exception as e:
            logger.exception("Failed to query daily_snapshots", error=str(e))
            messages.append("❌ daily_snapshots: error")
            has_issue = True

    # Check 3: Paper snapshot recency (paper_nav_snapshots)
    if not db_ok:
        messages.append("⚠️ paper_nav_snapshots: skip (DB inaccessible)")
        has_issue = True
    else:
        try:
            with connect(db_path) as conn:
                row = conn.execute(
                    "SELECT 1 FROM paper_nav_snapshots WHERE snapshot_date = ? LIMIT 1",
                    (target_date.isoformat(),),
                ).fetchone()
                if row:
                    messages.append("✅ paper_nav_snapshots: ok")
                else:
                    messages.append("⚠️ paper_nav_snapshots: no row for today")
                    has_issue = True
        except Exception as e:
            logger.exception("Failed to query paper_nav_snapshots", error=str(e))
            messages.append("⚠️ paper_nav_snapshots: error")
            has_issue = True

    # Check 4: VIX data recency
    try:
        vix_series = load_vix_series(vix_dir)
        if vix_series.empty:
            messages.append("⚠️ VIX data: missing")
            has_issue = True
        else:
            latest_vix_date = vix_series.index[-1]
            stale_days = (target_date - latest_vix_date).days
            if stale_days > 2:
                messages.append(f"⚠️ VIX data: {stale_days} days stale")
                has_issue = True
            else:
                messages.append("✅ VIX data: ok")
    except Exception as e:
        logger.exception("Failed to check VIX data recency", error=str(e))
        messages.append(f"⚠️ VIX data: error ({str(e)})")
        has_issue = True

    # Check 5: Disk space
    try:
        target_dir = db_path.parent if db_path.parent.exists() else Path(".")
        total, used, free = shutil.disk_usage(str(target_dir))
        free_mb = free / (1024 * 1024)
        if free_mb < 500:
            messages.append(f"⚠️ Disk space: {free_mb:.1f} MB free")
            has_issue = True
        else:
            messages.append("✅ Disk space: ok")
    except Exception as e:
        logger.exception("Failed to check disk space", error=str(e))
        messages.append(f"⚠️ Disk space: error ({str(e)})")
        has_issue = True

    return has_issue, messages


async def main() -> int:
    """Run the healthcheck script.

    Returns:
        0 on success, 1 on any check failure or warning.
    """
    parser = argparse.ArgumentParser(description="Validate NiftyShield system health")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(settings.db_path),
        help="Path to portfolio SQLite DB",
    )
    parser.add_argument(
        "--vix-dir",
        type=Path,
        default=Path(settings.vix_data_dir),
        help="Path to India VIX data directory",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date to check health for (YYYY-MM-DD). Defaults to today.",
    )
    args = parser.parse_args()

    # Configure logging
    setup_logging(json=(settings.upstox_env == "prod"))

    # Resolve date
    if args.date:
        today = date.fromisoformat(args.date)
    else:
        today = date.today()

    # Check 1: Trading day guard (holiday check)
    if not is_trading_day(today):
        logger.info("Non-trading day. Skipping health checks.", date=today.isoformat())
        return 0

    logger.info("Running system health check", date=today.isoformat())
    has_issue, messages = run_checks(today, args.db_path, args.vix_dir)

    if has_issue:
        # Build status alert message
        alert_body = "\n".join(messages)
        alert_msg = f"⚠️ NiftyShield Healthcheck — {today.isoformat()} 16:30 IST\n{alert_body}"

        logger.warning("System healthcheck failed or warned", alert=alert_msg)

        # Send Telegram alert
        notifier = build_notifier()
        if notifier:
            success = await notifier.send(alert_msg)
            if success:
                logger.info("Telegram healthcheck alert sent successfully")
            else:
                logger.error("Failed to send Telegram healthcheck alert")
        else:
            logger.info("Telegram notifier not configured. Skipping alert.")

        return 1

    logger.info("System healthcheck passed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
