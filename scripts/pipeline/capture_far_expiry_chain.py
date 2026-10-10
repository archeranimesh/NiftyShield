#!/usr/bin/env python3
"""Capture option chains for far expiries to track liquidity.

Runs daily to snapshot the nearest and next yearly (December) expiries,
recording them in the FarExpiryStore.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import aiohttp
import structlog
from dotenv import load_dotenv

from src.client.chain_source import DhanChainSource
from src.client.dhan_market import DhanMarketClient, SpacingRateLimiter
from src.client.exceptions import DataFetchError
from src.config import settings
from src.far_expiry.store import FarExpiryStore
from src.instruments.lookup import InstrumentLookup
from src.market_calendar.holidays import guard_trading_day
from src.portfolio.store import PortfolioStore
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.pipeline.capture_far_expiry_chain"
logger = structlog.get_logger(_SCRIPT_NAME)


class RealClock:
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def time(self) -> float:
        return asyncio.get_running_loop().time()


async def main() -> int:
    today = date.today()
    if guard_trading_day(logger, _SCRIPT_NAME, today):
        return 0

    bod_path = Path(settings.bod_instruments_path)
    try:
        lookup = InstrumentLookup.from_file(bod_path)
    except (FileNotFoundError, OSError) as exc:
        logger.error("bod.load_failed", error=str(exc))
        return 1

    candidates = lookup.get_expiry_candidates("NIFTY", today, preference=["yearly"])
    nearest_yearly = dict(candidates).get("yearly")

    expiries_to_fetch = []
    if nearest_yearly:
        expiries_to_fetch.append(nearest_yearly)
        next_candidates = lookup.get_expiry_candidates(
            "NIFTY", today, preference=["yearly"], min_expiry=nearest_yearly
        )
        next_yearly = dict(next_candidates).get("yearly")
        if next_yearly:
            expiries_to_fetch.append(next_yearly)

    if not expiries_to_fetch:
        logger.error("expiries.none_found")
        return 1

    db_path = Path(settings.db_path)
    far_store = FarExpiryStore(db_path)
    portfolio_store = await PortfolioStore.create(db_path)

    dhan_token = settings.dhan_access_token or ""
    dhan_client_id = settings.dhan_client_id or ""

    fail_count = 0
    async with aiohttp.ClientSession() as session:
        dhan_client = DhanMarketClient(
            session=session,
            rate_limiter=SpacingRateLimiter(spacing=0.5, clock=RealClock()),
            clock=RealClock(),
            access_token=dhan_token,
            client_id=dhan_client_id,
        )
        chain_source = DhanChainSource(dhan_client)

        for i, expiry_str in enumerate(expiries_to_fetch):
            if i > 0:
                await asyncio.sleep(4.0)

            try:
                chain = await chain_source.get_chain("NSE_INDEX|Nifty 50", expiry_str)
                captured_at = datetime.now(timezone.utc)
                await asyncio.to_thread(
                    far_store.record_chain,
                    snapshot_date=today,
                    captured_at=captured_at,
                    underlying="NIFTY_50",
                    source="dhan",
                    chain=chain,
                )
                logger.info("far_expiry.captured", expiry=expiry_str)
            except DataFetchError as exc:
                err_msg = str(exc)
                if "805" in err_msg:
                    logger.warning("far_expiry.805_response", expiry=expiry_str, error=err_msg)
                else:
                    logger.error("far_expiry.fetch_error", expiry=expiry_str, error=err_msg)
                fail_count += 1
            except Exception as exc:  # noqa: BLE001
                logger.error("far_expiry.unexpected_error", expiry=expiry_str, error=str(exc))
                fail_count += 1

    if fail_count == len(expiries_to_fetch):
        await asyncio.to_thread(
            portfolio_store.record_heartbeat, "capture_far_expiry", "FAILED", "All fetches failed"
        )
        logger.error("far_expiry.all_failed")
        return 1

    await asyncio.to_thread(portfolio_store.record_heartbeat, "capture_far_expiry", "SUCCESS")
    return 0


if __name__ == "__main__":
    load_dotenv()
    setup_logging()
    sys.exit(asyncio.run(main()))
