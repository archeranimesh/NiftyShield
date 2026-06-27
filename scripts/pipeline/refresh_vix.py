#!/usr/bin/env python3
"""Refresh India VIX Parquet data from Upstox API.

Fetches the trailing window (default 30 days) of daily VIX candles and
merges them into the canonical Parquet store. Safe to run repeatedly —
ingest_vix_from_api is resumable and skips already-stored dates.

Cron:
    # Weekly VIX refresh — keeps Parquet fresh for IVR computation
    45 15 * * 1 cd /path/to/NiftyShield && python -m scripts.pipeline.refresh_vix
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import structlog
from dotenv import load_dotenv

from src.utils.logging import setup_logging

load_dotenv()

from src.backtest.vix_ingest import ingest_vix_from_api  # noqa: E402
from src.client.exceptions import DataFetchError  # noqa: E402

_SCRIPT_NAME = "scripts.pipeline.refresh_vix"
logger = structlog.get_logger(_SCRIPT_NAME)

_DEFAULT_OUT_DIR = Path("data/historical/ohlc/india_vix")
_DEFAULT_LOOKBACK_DAYS = 30


def main(args_list: list[str] | None = None) -> int:
    """Entry point for VIX refresh.

    Args:
        args_list: CLI argument list (defaults to sys.argv when None).

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    setup_logging()

    parser = argparse.ArgumentParser(description="Refresh India VIX Parquet from Upstox API")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=_DEFAULT_LOOKBACK_DAYS,
        help=f"Days to look back from today (default {_DEFAULT_LOOKBACK_DAYS})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_DEFAULT_OUT_DIR,
        help=f"Parquet output directory (default {_DEFAULT_OUT_DIR})",
    )
    args = parser.parse_args(args_list)

    today = date.today()
    from_date = today - timedelta(days=args.lookback_days)

    logger.info(
        "vix_refresh_start",
        from_date=from_date.isoformat(),
        to_date=today.isoformat(),
        out_dir=str(args.out_dir),
    )

    try:
        rows_written = ingest_vix_from_api(
            from_date=from_date,
            to_date=today,
            out_dir=args.out_dir,
        )
    except DataFetchError as exc:
        logger.error("vix_refresh_failed", error=str(exc))
        return 1
    except ValueError as exc:
        logger.error("vix_refresh_config_error", error=str(exc))
        return 1

    logger.info("vix_refresh_complete", rows_written=rows_written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
