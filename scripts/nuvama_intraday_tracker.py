"""Background script to track Nuvama Options PnL at 5-minute intervals.

Intended to run via cron:
*/5 9-15 * * 1-5 python -m scripts.nuvama_intraday_tracker
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from dotenv import load_dotenv

from src.auth.nuvama_verify import load_api_connect
from src.client.exceptions import LTPFetchError
from src.client.factory import create_client
from src.nuvama.options_reader import parse_options_positions
from src.nuvama.store import NuvamaStore

logger = logging.getLogger(__name__)


async def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    now = datetime.now()

    # 1. Fetch Nuvama options positions
    try:
        api = load_api_connect()
        response = api.NetPosition()
        if response.get("stat") != "Ok":
            logger.error("Nuvama API returned non-Ok stat: %s", response)
            return 1

        store = NuvamaStore()
        cumulative_pnl = store.get_cumulative_realized_pnl()

        positions, _ = parse_options_positions(
            response=response,
            cumulative_realized_pnl=cumulative_pnl,
        )
        if not positions:
            logger.info("No Nuvama options positions found.")
            return 0

    except Exception as e:  # Intentional: isolate all upstream Nuvama failures
        logger.error("Failed to fetch Nuvama positions: %s", e)
        return 1

    # 2. Fetch Nifty Spot from Upstox
    nifty_spot = 0.0
    try:
        env = os.getenv("UPSTOX_ENV", "prod")
        client = create_client(env)
        NIFTY_INDEX_KEY = "NSE_INDEX|Nifty 50"
        prices = await client.get_ltp([NIFTY_INDEX_KEY])
        nifty_spot = prices.get(NIFTY_INDEX_KEY, 0.0)
    except LTPFetchError as e:
        logger.error("Upstox LTP fetch failed: %s", e)
    except Exception as e:  # Intentional: isolate all upstream Upstox failures
        logger.error("Failed to fetch Nifty spot: %s", e)

    # 3. Save to database
    try:
        store.record_intraday_positions(now, float(nifty_spot), positions)
        logger.info("Recorded %d positions for intraday tracking.", len(positions))
    except Exception as e:  # Intentional: isolate db failure
        logger.error("Failed to record intraday positions: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
