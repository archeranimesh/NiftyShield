"""Background script to track Nuvama Options PnL at 5-minute intervals.

Intended to run via cron:
*/5 9-15 * * 1-5 python -m scripts.nuvama_intraday_tracker

The cron fires from 9:00 but the script exits early for ticks before 9:15
(Nuvama NetPosition data is stale / unreliable during the opening auction window).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date, datetime
from decimal import Decimal

import structlog

# Pure-computation helper only — no I/O on import.
from src.market_calendar.holidays import is_trading_day
from src.utils.logging import setup_logging

logger = structlog.get_logger(__name__)


async def main(nifty_spot: float = 0.0, india_vix: float = 0.0) -> int:
    # All I/O-triggering imports deferred here so the module is importable
    # without a live .env or Nuvama SDK. Follows daily_snapshot.py pattern.
    from dotenv import load_dotenv

    from src.auth.nuvama_verify import load_api_connect
    from src.nuvama.options_reader import parse_options_positions
    from src.nuvama.protocol import NuvamaClient
    from src.nuvama.store import NuvamaStore

    load_dotenv()
    pass
    run_id = uuid.uuid4().hex[:8]
    now = datetime.now()
    logger.info("run_id=%s starting intraday tracker", run_id)

    if not is_trading_day(date.today()):
        logger.info("market_holiday date=%s — skipping intraday tracker", date.today())
        return 0

    if now.hour == 9 and now.minute < 15:
        logger.info(
            "before_market_open time=%s — skipping (tracker starts at 09:15)", now.strftime("%H:%M")
        )
        return 0

    store = NuvamaStore()

    # 1. Fetch Nuvama options positions
    from src.client.exceptions import DataFetchError

    try:
        api: NuvamaClient = load_api_connect()
        # Nuvama SDK removes all standard logging handlers on __init__. We must restore it.
        pass
        logger.info("Starting intraday nuvama options tracking loop...")

        logger.info("Fetching NetPosition()...")
        response = api.NetPosition()

        positions = parse_options_positions(response)
        if not positions:
            logger.info("No Nuvama options positions found.")
            return 0

    except DataFetchError as exc:
        # Known transient: SDK init hit a network failure (DNS not ready after
        # sleep, firewall, etc.). Single-line warning — no traceback needed.
        logger.warning("run_id=%s skipped — %s", run_id, exc)
        return 1
    except Exception:
        # Unexpected failure: preserve full traceback for debugging.
        logger.exception("run_id=%s failed to fetch Nuvama positions", run_id)
        return 1

    # 2. (Removed) Fetch Nifty Spot from Upstox - now passed as argument

    # 3. Save to database
    try:
        store.record_intraday_positions(now, positions)

        # Calculate PnL Breakdown
        unrealized = sum((p.unrealized_pnl for p in positions), Decimal("0"))
        realized_today = sum((p.realized_pnl_today for p in positions), Decimal("0"))
        historical_map = store.get_cumulative_realized_pnl(before_date=now.date())
        historical_total = sum(historical_map.values(), Decimal("0"))

        total_pnl = unrealized + realized_today

        logger.info(
            f"Total: {total_pnl:+,.0f} | Unreal: {unrealized:+,.0f} | "
            f"RealToday: {realized_today:+,.0f} | CumReal: {historical_total:+,.0f} | "
            f"Pos: {len(positions)}"
        )
    except Exception:  # Intentional: isolate db failure
        logger.exception("run_id=%s failed to record intraday positions", run_id)
        return 1

    return 0


if __name__ == "__main__":
    setup_logging()
    from dotenv import load_dotenv

    from src.client.factory import create_client

    async def run_standalone():
        load_dotenv()
        env = os.getenv("UPSTOX_ENV", "prod")
        client = create_client(env)
        try:
            prices = await client.get_ltp(["NSE_INDEX|Nifty 50", "NSE_INDEX|India VIX"])
            nifty = float(prices.get("NSE_INDEX|Nifty 50", 0.0))
            vix = float(prices.get("NSE_INDEX|India VIX", 0.0))
        except Exception:
            nifty, vix = 0.0, 0.0
        return await main(nifty_spot=nifty, india_vix=vix)

    exit_code = asyncio.run(run_standalone())
    # os._exit is absolutely required because the Nuvama APIConnect SDK
    # launches a non-daemon background thread that will indefinitely hang standard exits.
    os._exit(exit_code)
