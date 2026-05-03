# NSE F&O Bhavcopy Ingestion Pipeline

Implementation plan for Phase 1.3 of the backtest plan.

## Proposed Changes

### backtest

#### [NEW] src/backtest/__init__.py
- Package stub for type checkers and indexing.

#### [NEW] src/backtest/bhavcopy_ingest.py
- Define `BhavRecord` frozen Pydantic model with fields mapping to the Parquet schema (`trade_date`, `symbol`, `underlying`, `instrument`, `expiry`, `strike`, `option_type`, `open`, `high`, `low`, `close`, `settle_price`, `volume`, `oi`).
- `parse_option_symbol(symbol: str)`: Parses NSE option symbols into expiry, strike, and option_type, handling standard monthly, zero-padded strikes, and post-2019 weekly expiries.
- `parse_bhavcopy(csv_path: Path, underlying: str = "NIFTY") -> list[BhavRecord]`: Filters for `OPTIDX` and `OPTSTK` matching the underlying, skipping corrupted strikes.
- `download_bhavcopy(trade_date: date, dest_dir: Path) -> Path`: Fetches from NSE CDN. Returns the local zip path, or raises `FileNotFoundError` on HTTP 404.
- `write_to_parquet(records: list[BhavRecord], ...)`: Idempotently appends to Parquet files grouped by YYYY/MM using `pyarrow.parquet`.

#### [NEW] src/backtest/bhavcopy_loader.py
- `load_options_ohlcv(underlying: str, start: date, end: date, data_dir: Path) -> pd.DataFrame`: Reads overlapping partitions using `pyarrow.parquet`, filters by exact date range, and returns a DataFrame.

### scripts

#### [NEW] scripts/bhavcopy_bootstrap.py
- Resumable CLI script using `argparse`.
- Iterates dates, checks existing Parquet data to skip downloads, respects holidays via `src.market_calendar.holidays`.
- Downloads, parses, and writes data with a politeness delay (`>= 1.0` second sleep).
- Supports `--include-futures` flag to optionally save FUTIDX data to a separate path (`data/offline/futures_ohlcv/{year}/{month}/`).

### tests

#### [NEW] tests/unit/backtest/__init__.py
- Test package stub.

#### [NEW] tests/unit/backtest/test_bhavcopy_ingest.py
- Includes 11 offline fixture-driven test cases covering filtering, Decimal invariants, corrupted zip, symbol parser variants, idempotency, and loader filtering.

## Verification Plan

### Automated Tests
- Run `python -m pytest tests/unit/ --tb=no -q`
