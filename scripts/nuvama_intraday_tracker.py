"""Background script to track Nuvama Options PnL at 5-minute intervals.

Intended to run via cron:
*/5 9-15 * * 1-5 python -m scripts.nuvama_intraday_tracker

The cron fires from 9:00 but the script exits early for ticks before 9:15
(Nuvama NetPosition data is stale / unreliable during the opening auction window).
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import date, datetime
from decimal import Decimal

from dotenv import load_dotenv

from src.auth.nuvama_verify import load_api_connect
from src.client.exceptions import LTPFetchError
from src.client.factory import create_client
from src.market_calendar.holidays import is_trading_day
from src.nuvama.options_reader import parse_options_positions
from src.nuvama.store import NuvamaStore

logger = logging.getLogger(__name__)


async def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, force=True, format="%(levelname)s: %(message)s")
    run_id = uuid.uuid4().hex[:8]
    now = datetime.now()
    logger.info("run_id=%s starting intraday tracker", run_id)

    if not is_trading_day(date.today()):
        logger.info("market_holiday date=%s — skipping intraday tracker", date.today())
        return 0

    if now.hour == 9 and now.minute < 15:
        logger.info("before_market_open time=%s — skipping (tracker starts at 09:15)", now.strftime("%H:%M"))
        return 0

    store = NuvamaStore()

    # 1. Fetch Nuvama options positions
    try:
        api = load_api_connect()
        # Nuvama SDK removes all standard logging handlers on __init__. We must restore it.
        logging.basicConfig(
            level=logging.INFO, 
            force=True, 
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        logger.info("Starting intraday nuvama options tracking loop...")
        
        logger.info("Fetching NetPosition()...")
        response = api.NetPosition()

        positions = parse_options_positions(response)
        if not positions:
            logger.info("No Nuvama options positions found.")
            return 0

    except Exception:  # Intentional: isolate all upstream Nuvama failures
        logger.exception("run_id=%s failed to fetch Nuvama positions", run_id)
        return 1

    # 2. Fetch Nifty Spot from Upstox
    nifty_spot = 0.0
    try:
        logger.info("Fetching Nifty LTP from Upstox...")
        env = os.getenv("UPSTOX_ENV", "prod")
        client = create_client(env)
        NIFTY_INDEX_KEY = "NSE_INDEX|Nifty 50"
        prices = await client.get_ltp([NIFTY_INDEX_KEY])
        nifty_spot = prices.get(NIFTY_INDEX_KEY, 0.0)
    except LTPFetchError:
        logger.exception("run_id=%s Upstox LTP fetch failed", run_id)
    except Exception:  # Intentional: isolate all upstream Upstox failures
        logger.exception("run_id=%s failed to fetch Nifty spot", run_id)

    # 3. Save to database
    try:
        store.record_intraday_positions(now, float(nifty_spot), positions)
        
        # Calculate PnL Breakdown
        unrealized = sum((p.unrealized_pnl for p in positions), Decimal("0"))
        realized_today = sum((p.realized_pnl_today for p in positions), Decimal("0"))
        historical_map = store.get_cumulative_realized_pnl(before_date=now.date())
        historical_total = sum(historical_map.values(), Decimal("0"))
        
        total_pnl = unrealized + realized_today

        logger.info(
            "Total PnL: {:+,.0f} | Unrealized: {:+,.0f} | Realized Today: {:+,.0f} | Ledger: {:+,.0f} | "
            "Positions: {:d} | Nifty: {:,.2f}".format(
                total_pnl, unrealized, realized_today, historical_total, len(positions), nifty_spot
            )
        )
    except Exception:  # Intentional: isolate db failure
        logger.exception("run_id=%s failed to record intraday positions", run_id)
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    # os._exit is absolutely required because the Nuvama APIConnect SDK
    # launches a non-daemon background thread that will indefinitely hang standard exits.
    os._exit(exit_code)
