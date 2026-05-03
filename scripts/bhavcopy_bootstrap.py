import argparse
import logging
import time
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv()

from src.backtest.bhavcopy_ingest import download_bhavcopy, parse_bhavcopy, write_to_parquet

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Try importing holidays; fallback to empty set if not found
try:
    from src.market_calendar.holidays import get_nse_holidays
except ImportError:
    def get_nse_holidays() -> set[date]:
        return set()

def main(args_list=None):
    parser = argparse.ArgumentParser(description="Bootstrap NSE F&O Bhavcopy data")
    parser.add_argument("--underlying", default="NIFTY", help="Underlying symbol (default NIFTY)")
    parser.add_argument("--start", default="2016-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=date.today().isoformat(), help="End date (YYYY-MM-DD)")
    parser.add_argument("--dest", default="data/offline", type=Path, help="Destination directory")
    parser.add_argument("--include-futures", action="store_true", help="Include FUTIDX data")
    
    args = parser.parse_args(args_list)
    
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    
    holidays = get_nse_holidays()
    
    current_date = start_date
    
    downloaded_by_month = defaultdict(int)
    total_days_by_month = defaultdict(int)
    last_month = None
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        while current_date <= end_date:
            month_key = current_date.strftime("%Y-%m")
            if last_month and last_month != month_key:
                logger.info("[%s] downloaded %s/%s trading days", last_month, downloaded_by_month[last_month], total_days_by_month[last_month])
                
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
                zip_path = download_bhavcopy(current_date, dest_dir=tmp_path)
                
                records = parse_bhavcopy(zip_path, underlying=args.underlying, include_futures=args.include_futures)
                
                options_records = [r for r in records if r.instrument in ("OPTIDX", "OPTSTK")]
                options_dest = args.dest / "options_ohlcv"
                write_to_parquet(options_records, current_date, dest_dir=options_dest)
                
                if args.include_futures:
                    futures_records = [r for r in records if r.instrument in ("FUTIDX", "FUTSTK")]
                    futures_dest = args.dest / "futures_ohlcv"
                    write_to_parquet(futures_records, current_date, dest_dir=futures_dest)
                    
                downloaded_by_month[month_key] += 1
                
            except FileNotFoundError:
                logger.info("%s — holiday/no data, skipping", current_date)
            except Exception as e:
                logger.error("%s — %s", current_date, e)
                
            time.sleep(1.0)
            current_date += timedelta(days=1)
            
        if last_month:
            logger.info("[%s] downloaded %s/%s trading days", last_month, downloaded_by_month[last_month], total_days_by_month[last_month])

if __name__ == "__main__":
    main()
