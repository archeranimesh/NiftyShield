"""Combined intraday tracker — Dhan options + Nuvama options.

Replaces the previous Nuvama-only */5 cron with a single combined entry:
    */15 9-15 * * 1-5  cd /path/to/NiftyShield && python -m scripts.intraday.intraday_tracker >> logs/intraday.log 2>&1

Execution order:
    1. Dhan  — sync, no SDK side-effects, safe to run first.
    2. Nuvama — async; SDK launches a non-daemon background thread on init.
    3. os._exit() — terminates the Nuvama SDK background thread, which would
       otherwise block process exit indefinitely.

Both individual scripts retain their own __main__ guards for standalone use.

Frequency note: changed from */5 (Nuvama-only) to */15 (combined). Dhan option
positions change on trade events, not tick-by-tick; 15-min granularity is adequate
for the intraday P&L curve. Revert to two separate cron entries if the trackers
need different frequencies in future — that is a one-line cron change.
"""

from __future__ import annotations

import asyncio
import os

import structlog

from src.config import settings
from src.utils.logging import setup_logging

setup_logging()

_SCRIPT_NAME = "scripts.intraday.intraday_tracker"
logger = structlog.get_logger(_SCRIPT_NAME)


async def main() -> int:
    """Run Dhan tracker then Nuvama tracker in sequence.

    Returns:
        max(dhan_exit, nuvama_exit) — non-zero if either tracker failed.
    """
    from datetime import datetime, timezone

    from dotenv import load_dotenv

    from scripts.intraday.dhan_intraday_tracker import main as dhan_main
    from scripts.intraday.nuvama_intraday_tracker import main as nuvama_main
    from src.client.exceptions import DataFetchError
    from src.client.factory import create_client
    from src.intraday.market_store import IntradayMarketStore

    load_dotenv()

    nifty_spot = 0.0
    india_vix = 0.0
    try:
        env = settings.upstox_env
        client = create_client(env)
        NIFTY_KEY = "NSE_INDEX|Nifty 50"
        VIX_KEY = "NSE_INDEX|India VIX"
        prices = await client.get_ltp([NIFTY_KEY, VIX_KEY])
        nifty_spot = float(prices.get(NIFTY_KEY, 0.0))
        india_vix = float(prices.get(VIX_KEY, 0.0))

        logger.info(f"Nifty: {nifty_spot:,.2f} | VIX: {india_vix:.2f}")

        store = IntradayMarketStore()
        now = datetime.now(timezone.utc)
        store.record_market_snapshot(now, nifty_spot, india_vix)
        store.purge_old(days=30)
    except DataFetchError as e:
        logger.warning("Network unavailable — skipping market context fetch: %s", e)
    except Exception:
        logger.exception("Failed to fetch or store market context (Nifty/VIX)")

    # Dhan first — sync, no SDK thread pollution.
    dhan_exit = dhan_main(nifty_spot=nifty_spot, india_vix=india_vix)

    # Nuvama second — SDK launches background thread after this returns.
    nuvama_exit = await nuvama_main(nifty_spot=nifty_spot, india_vix=india_vix)

    return max(dhan_exit, nuvama_exit)


if __name__ == "__main__":
    code = asyncio.run(main())
    # os._exit is required: kills the Nuvama SDK non-daemon background thread
    # that would otherwise block process exit indefinitely.
    os._exit(code)
