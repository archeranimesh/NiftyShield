# NSE F&O Bhavcopy Ingestion Pipeline

Implementation plan for Phase 1.3 of the backtest plan.

## Proposed Changes

### backtest

#### [NEW] src/backtest/__init__.py
- Package stub for type checkers and indexing. After creation, we will run `mcp__codebase-memory-mcp__index_repository` to re-index the codebase graph.

#### [NEW] src/backtest/bhavcopy_ingest.py
- **`BhavRecord`**: Frozen Pydantic model. 
  - **Decimal invariant:** All price fields (`open`, `high`, `low`, `close`, `settle_price`) are strictly `Decimal`, never `float`. They will be converted directly from CSV strings via `Decimal(str(x))`.
  - **FUTIDX Field Mapping:** For FUTIDX rows, `strike` defaults to `Decimal("0")` and `option_type` defaults to `"XX"`. The model must explicitly allow `"XX"` as a valid `option_type`.
  - **Volume Mapping:** `volume` is populated from the `CONTRACTS` column (lot count), NOT `VAL_INLAKH`.
- **`parse_option_symbol(symbol: str)`**: Standalone utility for downstream consumers. **Crucially, this is NOT called inside `parse_bhavcopy`** since the CSV has explicit columns for strike/expiry. 
  - Handles monthly formats, zero-padded strikes, and weekly formats. 
  - **Weekly Format Parsing:** Parsed as `YY` + `M` + `DD` where `M` is 1-9 for Jan-Sep, `O` for Oct, `N` for Nov, and `D` for Dec (e.g., `NIFTY2641724000PE` -> `26`=2026, `4`=April, `17`=17th). Raises `ValueError` on garbage strings.
- **`parse_bhavcopy(csv_path: Path, underlying: str = "NIFTY") -> list[BhavRecord]`**: Filters `INSTRUMENT IN ('OPTIDX', 'OPTSTK')` and `SYMBOL == underlying`. 
  - **Corrupted Strikes Rule:** Rows where `STRIKE_PR == 0` AND `OPTION_TYP` is `CE` or `PE` are data errors and skipped with a `WARNING` log.
  - **Date Parsing:** `EXPIRY_DT` in CSV uses `DD-Mon-YYYY` (e.g. `25-APR-2024`). Parsed strictly with `datetime.strptime`.
- **`download_bhavcopy(trade_date: date, dest_dir: Path) -> Path`**: Fetches the zip from NSE CDN using `urllib.request` (stdlib fallback to avoid dependencies unless httpx exists). Raises `FileNotFoundError` on HTTP 404. **No politeness delay inside this function** — the caller manages sleep.
- **`write_to_parquet(...)`**: 
  - **Idempotency Contract:** Reads existing Parquet for that `{YYYY}/{MM}` partition → checks if `trade_date` is already in the `date` column → if yes, returns early; if no, concats and writes.
  - **Parquet Schema:** Explicitly uses `pyarrow.decimal128(18, 4)` for all price columns to prevent silent `float64` inference.

#### [NEW] src/backtest/bhavcopy_loader.py
- **`load_options_ohlcv(underlying: str, start: date, end: date, data_dir: Path) -> pd.DataFrame`**: 
  - **Partition Discovery:** Scans only `{YYYY}/{MM}` dirs that overlap the `[start, end]` window, rather than globbing all years.
  - Uses `pyarrow.parquet.read_table` with optional column pruning, converting to pandas before returning. Returns an empty DataFrame if missing.

### scripts

#### [NEW] scripts/bhavcopy_bootstrap.py
- Resumable bulk download CLI using `argparse`.
- **Execution:** Sequential, not asyncio (NSE CDN rate sensitivity).
- **CLI Args:** `--underlying` (default NIFTY), `--start` (default 2016-01-01), `--end` (default today), `--dest` (default data/offline/), `--include-futures` (default off).
- **Loop:** Iterates dates, skips known NSE holidays using `src.market_calendar.holidays`. Implements the **politeness delay** (`time.sleep(1)`) between requests.
- **Error Handling:** 
  - HTTP 404: Log `INFO: {date} — holiday/no data, skipping` and continue.
  - Other errors: Log `ERROR: {date} — {exception}` and continue without aborting.
- **Progress Log:** After each month completes, emits log: `INFO: [YYYY-MM] downloaded XX/YY trading days`.
- **FUTIDX Open Question Resolution:** Leaves the decision for Task 1.6a. Implements the `--include-futures` flag as opt-in. If enabled, FUTIDX rows are parsed and stored separately at `data/offline/futures_ohlcv/{year}/{month}/`, never folded into the main options Parquet.

### tests

#### [NEW] tests/fixtures/responses/bhavcopy/
- A synthetic fixture CSV to be used by the unit tests.

#### [NEW] tests/unit/backtest/__init__.py
- Test package stub.

#### [NEW] tests/unit/backtest/test_bhavcopy_ingest.py
- Fixture-driven offline tests interleaving with the commits (see Commit Sequence).

## Commit Sequence (Strict Ordering with Interleaved Tests)

Four sequential commits, each executed ONLY after its code is verified green by `pytest` and `code-reviewer`:
1. `feat(backtest): add BhavRecord model and parse_bhavcopy + parse_option_symbol`
   - **Includes:** `tests/unit/backtest/__init__.py`, fixture setup (`tests/fixtures/responses/bhavcopy/`), and unit tests for `parse_option_symbol` (all 4 variants), `parse_bhavcopy` filtering, and Decimal invariant.
2. `feat(backtest): add Parquet write with idempotency + bhavcopy_loader`
   - **Includes:** Unit tests for Parquet idempotency and loader date filtering/empty handling.
3. `feat(scripts): resumable bulk bhavcopy bootstrap (2016-present)`
   - **Includes:** Unit tests for bootstrap CLI argument parsing and error-path execution.
4. `test(backtest): integration tests for bhavcopy pipeline`
   - **Includes:** End-to-end integration tests (bootstrap → load → verify DataFrame types).

## Post-Implementation Checklist

- `Edit` `CONTEXT.md`: Add `src/backtest/` to the module tree.
- `Edit` `TODOS.md`: Add session log entry with date, task 1.3, commit SHAs, and FUTIDX question status.
- `Edit` `BACKTEST_PLAN_PHASE1.md`: Tick `[x]` on completed items in §1.3.
- Run `mcp__codebase-memory-mcp__index_repository` to index the new files.

## Verification Plan

### Automated & Manual Verification
- **Test Suite:** `python -m pytest tests/unit/ --tb=no -q` ensures all 400+ existing tests and the new tests pass.
- **Code Review:** The `code-reviewer` agent will be invoked against `git diff HEAD` before each of the four commits.
- **Smoke Test:** Manually run the bootstrap script for a single month and verify `load_options_ohlcv` successfully returns a non-empty DataFrame with correct types.
