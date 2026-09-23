import argparse
import tempfile
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import structlog

from src.backtest.equity_bhavcopy_ingest import (
    download_equity_bhavcopy,
    download_index_bhavcopy,
    parse_equity_bhavcopy,
    parse_index_bhavcopy,
    write_equity_to_parquet,
    write_index_to_parquet,
)
from src.config import settings
from src.mvp.store import MVPStore

try:
    from src.market_calendar.holidays import get_nse_holidays
except ImportError:

    def get_nse_holidays() -> set[date]:
        return set()


_SCRIPT_NAME = "scripts.pipeline.equity_bhavcopy_bootstrap"
logger = structlog.get_logger(_SCRIPT_NAME)


def main(args_list: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap NSE Equity & Index Bhavcopy data for MVP"
    )
    parser.add_argument("--start", default="2016-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=date.today().isoformat(), help="End date (YYYY-MM-DD)")
    parser.add_argument("--dest", default="data/offline", type=Path, help="Destination directory")

    args = parser.parse_args(args_list)

    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()

    holidays = get_nse_holidays()

    store = MVPStore(settings.db_path)
    symbols = store.get_distinct_symbols()
    logger.info("Loaded %d distinct symbols from MVPStore", len(symbols))
    if not symbols:
        logger.warning("No symbols found in MVPStore, but continuing anyway.")

    current_date = start_date

    downloaded_by_month: dict[str, int] = defaultdict(int)
    total_days_by_month: dict[str, int] = defaultdict(int)
    last_month = None

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        while current_date <= end_date:
            month_key = current_date.strftime("%Y-%m")
            if last_month and last_month != month_key:
                logger.info(
                    "[%s] downloaded %s/%s trading days",
                    last_month,
                    downloaded_by_month[last_month],
                    total_days_by_month[last_month],
                )

            last_month = month_key

            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            total_days_by_month[month_key] += 1

            if current_date in holidays:
                logger.info("%s — holiday/no data, skipping", current_date)
                current_date += timedelta(days=1)
                continue

            try:
                # 1. Equity
                eq_zip_path = download_equity_bhavcopy(current_date, dest_dir=tmp_path)
                eq_records = parse_equity_bhavcopy(eq_zip_path, symbols=symbols)
                eq_dest = args.dest / "equity_ohlcv"
                write_equity_to_parquet(eq_records, current_date, dest_dir=eq_dest)

                # 2. Index
                idx_csv_path = download_index_bhavcopy(current_date, dest_dir=tmp_path)
                idx_record = parse_index_bhavcopy(idx_csv_path)
                if idx_record:
                    idx_dest = args.dest / "nifty_index"
                    write_index_to_parquet([idx_record], current_date, dest_dir=idx_dest)
                else:
                    logger.warning(
                        "%s — parsed index bhavcopy but Nifty 50 record missing", current_date
                    )

                downloaded_by_month[month_key] += 1

            except FileNotFoundError:
                logger.info("%s — holiday/no data, skipping", current_date)
            except Exception as e:
                logger.error("%s — %s", current_date, e)

            time.sleep(1.0)
            current_date += timedelta(days=1)

        if last_month:
            logger.info(
                "[%s] downloaded %s/%s trading days",
                last_month,
                downloaded_by_month[last_month],
                total_days_by_month[last_month],
            )


if __name__ == "__main__":
    from src.utils.logging import setup_logging

    setup_logging(json=False, level="INFO")
    main()
