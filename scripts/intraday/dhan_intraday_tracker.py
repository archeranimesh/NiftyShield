"""Dhan intraday options tracker — records positions every 15 minutes.

Standalone Dhan-only tracker. Can be run directly for manual invocation
or debugging. Also importable by scripts/intraday/intraday_tracker.py (combined
orchestrator) which replaces the individual cron entries.

Time window: 09:15–15:29. Before 09:15 Dhan position data is unreliable
during the opening auction. After 15:29 the market is closed; the final
EOD snapshot is recorded by daily_snapshot.py at 3:45 PM.

Standalone cron (if running without combined orchestrator):
    */15 9-15 * * 1-5  cd /path && python -m scripts.intraday.dhan_intraday_tracker >> logs/intraday.log 2>&1

No os._exit() needed here — no Nuvama SDK thread is involved.
"""

from __future__ import annotations

import sys
from datetime import date, datetime

import requests.exceptions
import structlog

# Pure-computation helper only — no I/O on import.
from src.market_calendar.holidays import is_trading_day
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.intraday.dhan_intraday_tracker"
logger = structlog.get_logger(_SCRIPT_NAME)


def main(nifty_spot: float = 0.0, india_vix: float = 0.0) -> int:
    """Run one Dhan intraday options snapshot tick.

    Args:
        nifty_spot: Nifty 50 level fetched by the combined orchestrator.
            Accepted for API symmetry with nuvama_intraday_tracker; not yet
            stored or logged here (market context lives in intraday_market_snapshots).
        india_vix: India VIX level — same note as nifty_spot.

    Returns:
        0 on success or deliberate skip, 1 on unrecoverable error.
    """
    # All I/O-triggering imports deferred so this module is importable
    # without a live .env. Follows the daily_snapshot.py pattern.
    from datetime import timezone
    from pathlib import Path

    from dotenv import load_dotenv

    from src.dhan.positions import (
        build_options_summary,
        fetch_fund_limit_raw,
        fetch_positions_raw,
        filter_intraday_options,
        parse_fund_limit,
        parse_option_positions,
    )
    from src.dhan.store import DhanStore

    load_dotenv()
    pass

    now = datetime.now()
    logger.info("dhan_intraday_tracker starting time=%s", now.strftime("%H:%M"))

    # ── Market calendar guard ─────────────────────────────────────
    if not is_trading_day(date.today()):
        logger.info("market_holiday date=%s — skipping", date.today())
        return 0

    # ── Time window guards ────────────────────────────────────────
    if now.hour < 9 or (now.hour == 9 and now.minute < 15):
        logger.info(
            "before_market_open time=%s — skipping (tracker starts at 09:15)",
            now.strftime("%H:%M"),
        )
        return 0

    if now.hour > 15 or (now.hour == 15 and now.minute >= 30):
        logger.info(
            "market_closed time=%s — skipping (EOD handled by daily_snapshot.py at 15:45)",
            now.strftime("%H:%M"),
        )
        return 0

    from src.config import settings

    if not settings.dhan_client_id or not settings.dhan_access_token:
        raise KeyError("DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN must be set")
    client_id = settings.dhan_client_id
    access_token = settings.dhan_access_token
    db_path = Path(settings.db_path)
    ts = datetime.now(tz=timezone.utc)

    try:
        # ── Positions ─────────────────────────────────────────────
        raw = fetch_positions_raw(client_id, access_token)
        positions = filter_intraday_options(parse_option_positions(raw))
        summary = build_options_summary(positions, ts)

        # ── Fund limit (margin) ───────────────────────────────────
        raw_fl = fetch_fund_limit_raw(client_id, access_token)
        fund_limit = parse_fund_limit(raw_fl, ts)

        # ── Persist ───────────────────────────────────────────────
        store = DhanStore(db_path)
        store.record_options_snapshot(ts, summary, positions, is_eod=False)
        store.record_margin_snapshot(ts, fund_limit)
        purged = store.purge_old_intraday(days=30)

        total_pnl = summary.unrealized_pnl + summary.realized_pnl
        logger.info(
            f"Total: {total_pnl:+,.0f} | Unreal: {summary.unrealized_pnl:+,.0f} | "
            f"RealToday: {summary.realized_pnl:+,.0f} | AvailMgn: {fund_limit.available_balance:+,.0f} | "
            f"Pos: {summary.position_count}"
        )
        if purged:
            logger.info("purged %d old intraday row(s)", purged)

    except requests.exceptions.ConnectionError as e:
        logger.warning("Network unavailable — skipping Dhan snapshot: %s", e)
        return 0
    except Exception:
        logger.exception("Dhan intraday tracker failed")
        return 1

    return 0


if __name__ == "__main__":
    setup_logging()
    sys.exit(main())
