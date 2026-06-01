#!/usr/bin/env python3
"""EOD option chain snapshot cron for NiftyShield.

Fetches Nifty option chains for up to 3 expiries (monthly / quarterly / yearly)
and writes each to Parquet via ChainWriter.

Designed to run daily at 3:30 PM IST (Mon–Fri):
    30 15 * * 1-5  cd /path/to/NiftyShield && \
        python -m scripts.pipeline.upstox_chain_snapshot >> logs/chain_snapshot.log 2>&1

Environment variables:
    CHAIN_SNAPSHOT_DIR      — Parquet output root (default: data/offline/chain_snapshots)
    BOD_INSTRUMENTS_PATH    — Path to NSE.json.gz BOD file (default: data/instruments/NSE.json.gz)
    UPSTOX_ANALYTICS_TOKEN  — Required for live fetch (loaded from .env)
    LOG_LEVEL               — Logging verbosity (default: INFO)
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import structlog

from src.config import settings
from src.utils.logging import setup_logging

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.backtest.chain_writer import ChainWriter  # noqa: E402
from src.client.exceptions import DataFetchError  # noqa: E402
from src.client.upstox_market import UpstoxMarketClient, parse_upstox_option_chain  # noqa: E402
from src.instruments.lookup import InstrumentLookup  # noqa: E402
from src.market_calendar.holidays import is_trading_day  # noqa: E402

_SCRIPT_NAME = "scripts.pipeline.upstox_chain_snapshot"
logger = structlog.get_logger(_SCRIPT_NAME)

_NIFTY_INSTRUMENT = "NSE_INDEX|Nifty 50"
_DEFAULT_SNAPSHOT_DIR = "data/offline/chain_snapshots"
_DEFAULT_BOD_PATH = Path("data/instruments/NSE.json.gz")
_PREFERENCE = ["monthly", "quarterly", "yearly"]
_NIFTY_UNDERLYING = "NIFTY_50"


def main() -> int:
    """Fetch EOD option chain for 3 Nifty expiries and persist to Parquet.

    Returns 0 on success, 1 on any error.
    Designed to run as: 30 15 * * 1-5 (3:30 PM IST, Mon–Fri).
    """
    pass

    today = date.today()

    if not is_trading_day(today):
        logger.info("not a trading day (%s), exiting", today)
        return 0

    snapshot_ts = datetime.now(timezone.utc)

    base_dir = settings.chain_snapshot_dir
    writer = ChainWriter(base_dir)

    bod_path = Path(settings.bod_instruments_path)
    try:
        lookup = InstrumentLookup.from_file(bod_path)
    except (FileNotFoundError, OSError) as exc:
        logger.error("Failed to load BOD instruments file %s: %s", bod_path, exc)
        return 1

    expiries = lookup.get_expiry_candidates("NIFTY", today, _PREFERENCE)

    if len(expiries) < 3:
        logger.warning(
            "only %d expiry candidates found (expected 3): %s",
            len(expiries),
            [exp for _, exp in expiries],
        )

    if not expiries:
        logger.error("no expiry candidates available — cannot fetch chains")
        return 1

    client = UpstoxMarketClient()

    fail_count = 0
    for label, expiry_str in expiries:
        try:
            raw = client.get_option_chain_sync(_NIFTY_INSTRUMENT, expiry_str)
            chain = parse_upstox_option_chain(raw)
            path = writer.write_eod_snapshot(chain, snapshot_ts, _NIFTY_UNDERLYING)
            row_count = len(chain.strikes) * 2
            logger.info(
                "snapshot written: expiry=%s label=%s strikes=%d rows=%d path=%s",
                expiry_str,
                label,
                len(chain.strikes),
                row_count,
                path,
            )
        except DataFetchError as exc:
            logger.error("DataFetchError for expiry=%s: %s", expiry_str, exc)
            fail_count += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("unexpected error for expiry=%s: %s", expiry_str, exc)
            fail_count += 1

    if fail_count == len(expiries):
        logger.error("all %d expiry fetches failed — returning 1", len(expiries))
        return 1

    return 0


if __name__ == "__main__":
    setup_logging()
    sys.exit(main())
