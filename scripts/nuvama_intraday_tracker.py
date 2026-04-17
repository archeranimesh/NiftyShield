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
    logging.basicConfig(level=logging.INFO, force=True, format="%(levelname)s: %(message)s")
    logger.info("Starting intraday nuvama options tracking loop...")

    now = datetime.now()
    store = NuvamaStore()

    # 1. Fetch Nuvama options positions
    try:
        api = load_api_connect()
        # Nuvama SDK removes all standard logging handlers on __init__. We must restore it.
        logging.basicConfig(level=logging.INFO, force=True, format="%(levelname)s: %(message)s")
        
        logger.info("Fetching NetPosition()...")
        response = api.NetPosition()

        positions = parse_options_positions(response)
        if not positions:
            logger.info("No Nuvama options positions found.")
            return 0

    except Exception as e:  # Intentional: isolate all upstream Nuvama failures
        logger.error("Failed to fetch Nuvama positions: %s", e)
        import traceback
        traceback.print_exc()
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
    exit_code = asyncio.run(main())
    # os._exit is absolutely required because the Nuvama APIConnect SDK
    # launches a non-daemon background thread that will indefinitely hang standard exits.
    os._exit(exit_code)
