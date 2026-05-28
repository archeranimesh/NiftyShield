# chain-data — Story Specs

> One task per session. Find the first unchecked item in `chain_data_tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: tick `chain_data_tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.

---

## CD1.1 — `src/backtest/chain_writer.py`: Parquet writer + tests

**Files to change:**
- `src/backtest/chain_writer.py` — new file: `ChainWriter` class
- `tests/unit/backtest/test_chain_writer.py` — new test file

**Before any code:**
- `search_graph("ChainWriter")` — confirm it does NOT yet exist (zero results expected)
- `get_code_snippet("parse_upstox_option_chain")` — confirm return type (`OptionChain`)
- `get_code_snippet("OptionChain")` — exact field list (strikes, underlying_spot, expiry)
- `get_code_snippet("OptionLeg")` — exact field list (delta, gamma, theta, vega, iv, ltp, bid, ask, oi, volume)
- `git log --oneline -5 src/backtest/` — check recent backtest module activity

**What to implement:**

`ChainWriter` is a pure Parquet I/O helper — no business logic, no client calls.

```python
class ChainWriter:
    def __init__(self, base_dir: str) -> None:
        """Store base_dir. Create no directories in __init__."""

    def write_eod_snapshot(
        self,
        chain: OptionChain,
        snapshot_ts: datetime,
        underlying: str = "NIFTY_50",
    ) -> Path:
        """Write an EOD chain snapshot to Parquet.

        Path: {base_dir}/{year}/{month}/upstox_{date}.parquet
        Overwrites any existing file for the same date (idempotent).
        Returns the path written.
        """

    def write_intraday_snapshot(
        self,
        chain: OptionChain,
        snapshot_ts: datetime,
        underlying: str = "NIFTY_50",
    ) -> Path:
        """Write a 5-min intraday snapshot to Parquet.

        Path: {base_dir}/{year}/{month}/{day}/upstox_{HHMM}.parquet
        HHMM is IST 24-hour (convert from UTC snapshot_ts internally).
        Overwrites any existing file for the same HHMM (idempotent).
        Returns the path written.
        """
```

Internal `_chain_to_table(chain, snapshot_ts, underlying) → pa.Table` helper decomposes
`OptionChain` into per-strike per-side rows. One row per `(strike, option_type)`.
Use the PyArrow schema from `chain_data_schema.md` exactly — `pa.decimal128(18, 6)` for
all price/Greek/IV fields, `pa.int64()` for oi/volume.

`snapshot_ts` must be timezone-aware UTC. Raise `ValueError` if naive.

Directory creation: `path.parent.mkdir(parents=True, exist_ok=True)` inside each write method.

**Tests (≥8):**
- `test_write_eod_creates_correct_path` — assert returned path matches `{base_dir}/2026/05/upstox_2026-05-27.parquet`
- `test_write_eod_idempotent` — write twice with same date; file count = 1, last write wins
- `test_write_eod_roundtrip` — write then read back with `pd.read_parquet`; assert row count = CE+PE strikes × expiries; spot value correct
- `test_write_intraday_path` — assert `{base_dir}/2026/05/27/upstox_1430.parquet` for 09:00 UTC (= 14:30 IST)
- `test_write_intraday_idempotent` — same 5-min window, second write overwrites
- `test_naive_ts_raises` — `datetime.utcnow()` (naive) → `ValueError`
- `test_empty_chain_writes_zero_rows` — `OptionChain` with no strikes → Parquet with 0 rows, no error
- `test_decimal_precision` — read back a delta field; assert `Decimal(str(val))` matches input to 6 dp

No network. Use `tmp_path` pytest fixture for all file I/O.

**Commit message:**
```
feat(backtest): ChainWriter — Parquet EOD and intraday chain snapshot writer

Why: Forward-looking chain data accumulation cannot be back-filled; writer must
     exist before the snapshot cron (CD1.2) can land.
What:
- src/backtest/chain_writer.py: ChainWriter with write_eod_snapshot + write_intraday_snapshot
- tests/unit/backtest/test_chain_writer.py: 8 tests, all green
Ref: docs/plan/chain-data/chain_data_schema.md — Parquet schema spec
```

---

## CD1.2 — `scripts/upstox_chain_snapshot.py`: EOD snapshot cron + tests

**Files to change:**
- `scripts/upstox_chain_snapshot.py` — new script
- `tests/unit/test_upstox_chain_snapshot.py` — new test file

**Before any code:**
- `get_code_snippet("is_trading_day")` — confirm signature (`src/market_calendar/`)
- `get_code_snippet("get_option_chain_sync")` — confirm signature + return type on `UpstoxLiveClient`
- `get_code_snippet("parse_upstox_option_chain")` — confirm it accepts the `get_option_chain_sync` return
- `get_code_snippet("get_expiry_candidates")` — confirm `src/instruments/lookup.py` signature
- `get_code_snippet("ChainWriter")` — confirm CD1.1 is committed before starting this task

**What to implement:**

Single-file script. Entry point: `if __name__ == "__main__": sys.exit(main())`.

```python
def main() -> int:
    """Fetch EOD option chain for 3 Nifty expiries and persist to Parquet.

    Returns 0 on success, 1 on any error.
    Designed to run as: 30 15 * * 1-5 (3:30 PM IST, Mon–Fri).
    """
```

Logic:
1. `is_trading_day(today)` guard — log "not a trading day, exiting" and return 0 if false.
2. Resolve 3 expiries via `get_expiry_candidates(underlying="NIFTY", today=today, preference=["weekly", "monthly_current", "monthly_next"])`. If fewer than 3 candidates, log warning but continue with what's available.
3. For each expiry: call `UpstoxLiveClient.get_option_chain_sync(instrument, expiry_str)` → `parse_upstox_option_chain(raw)` → `ChainWriter.write_eod_snapshot(chain, snapshot_ts, underlying)`.
4. Log: expiry, strike count, rows written, path.
5. On any single-expiry failure: log error, continue. If all three fail: return 1.
6. `snapshot_ts`: `datetime.now(timezone.utc)` at script start (not per-expiry).

`base_dir` from env var `CHAIN_SNAPSHOT_DIR` (default: `data/offline/chain_snapshots`).

**Cron entry (add to README.md):**
```
# EOD option chain snapshot — 3:30 PM IST, Mon–Fri
30 15 * * 1-5  cd /path/to/NiftyShield && python -m scripts.upstox_chain_snapshot >> logs/chain_snapshot.log 2>&1
```

**Tests (≥8):**
- `test_holiday_guard_exits_clean` — mock `is_trading_day` → False; assert main() == 0, no chain fetch called
- `test_happy_path_three_expiries` — mock client + parser + writer; assert write called 3×, returns 0
- `test_single_expiry_failure_continues` — first expiry raises `DataFetchError`; assert write called for remaining 2, returns 0
- `test_all_expiries_fail_returns_one` — all three raise; assert main() == 1
- `test_fewer_than_three_expiries_ok` — `get_expiry_candidates` returns 2; assert write called 2×, returns 0
- `test_snapshot_ts_is_utc_aware` — capture `snapshot_ts` passed to writer; assert `tzinfo is not None`
- `test_base_dir_from_env` — set `CHAIN_SNAPSHOT_DIR=/tmp/test_chain`; assert writer initialised with that path
- `test_log_output_includes_expiry_and_rows` — assert structured log entry emitted per expiry

No network. Mock `UpstoxLiveClient`, `parse_upstox_option_chain`, `ChainWriter`, `is_trading_day`, `get_expiry_candidates`.

**Commit message:**
```
feat(scripts): upstox_chain_snapshot — EOD option chain snapshot cron

Why: Forward data accumulation starts now; cannot be back-filled; feeds
     slippage model (1.4), delta drift calibration (1.6a), and Phase 3 signals.
What:
- scripts/upstox_chain_snapshot.py: cron-ready EOD snapshot for 3 Nifty expiries
- tests/unit/test_upstox_chain_snapshot.py: 8 tests, all green
- README.md: cron entry 30 15 * * 1-5
Ref: docs/plan/chain-data/chain_data_stories.md CD1.2
```

---

## CD2.1 — `scripts/upstox_chain_intraday.py`: 5-min intraday snapshot cron + tests

**Files to change:**
- `scripts/upstox_chain_intraday.py` — new script (separate from EOD; cleaner than `--mode` flag)
- `tests/unit/test_upstox_chain_intraday.py` — new test file

**Before any code:**
- `get_code_snippet("ChainWriter")` — confirm `write_intraday_snapshot` signature (CD1.1 must be done)
- `get_code_snippet("is_trading_day")` — confirm signature
- `search_graph("upstox_chain_snapshot")` — confirm CD1.2 is committed

**What to implement:**

Same structure as CD1.2 but for intraday cadence. Key differences:
- `base_dir` from `CHAIN_INTRADAY_DIR` (default: `data/offline/chain_snapshots_5min`).
- Uses `ChainWriter.write_intraday_snapshot` (not `write_eod_snapshot`).
- Cron runs every 5 minutes during market hours: `*/5 9-15 * * 1-5`.
- No 3-expiry resolution via `get_expiry_candidates` — re-use same expiry list from EOD cron
  to keep call pattern consistent. In practice: `get_expiry_candidates` is cheap (BOD JSON read).
- On non-trading-day (is_trading_day=False): exit 0, no fetch.
- Same error-isolation pattern: per-expiry try/except, continue on failure.

**Cron entry (add to README.md):**
```
# Intraday 5-min option chain snapshot — 9:00 AM to 3:55 PM IST, Mon–Fri
*/5 9-15 * * 1-5  cd /path/to/NiftyShield && python -m scripts.upstox_chain_intraday >> logs/chain_intraday.log 2>&1
```

**Tests (≥6):**
- `test_holiday_guard_exits_clean` — same as CD1.2
- `test_happy_path_three_expiries` — assert `write_intraday_snapshot` called 3×
- `test_single_expiry_failure_continues`
- `test_all_expiries_fail_returns_one`
- `test_base_dir_from_env` — `CHAIN_INTRADAY_DIR`
- `test_snapshot_ts_is_utc_aware`

**Commit message:**
```
feat(scripts): upstox_chain_intraday — 5-min intraday option chain snapshot

Why: Intraday bid/ask spread distribution is empirical input for slippage model
     (task 1.4); delta drift measurement (1.6a) requires intraday Greek series.
What:
- scripts/upstox_chain_intraday.py: 5-min cron for 3 Nifty expiries
- tests/unit/test_upstox_chain_intraday.py: 6 tests, all green
- README.md: cron entry */5 9-15 * * 1-5
Ref: docs/plan/chain-data/chain_data_stories.md CD2.1
```

---

## CD3.1 — `src/backtest/chain_reader.py`: DuckDB scan + filter utilities + tests

**Files to change:**
- `src/backtest/chain_reader.py` — new file: `ChainReader` class
- `tests/unit/backtest/test_chain_reader.py` — new test file

**Before any code:**
- `search_graph("ChainWriter")` — confirm CD1.1 is committed; get exact Parquet path convention
- `search_graph("ChainReader")` — confirm does NOT yet exist
- `bash python -c "import duckdb; print(duckdb.__version__)"` — confirm duckdb available in venv
- Review `chain_data_schema.md` — column names and types

**What to implement:**

```python
class ChainReader:
    def __init__(self, eod_dir: str, intraday_dir: str | None = None) -> None:
        """Store paths. DuckDB connection opened lazily on first query."""

    def get_eod_snapshots(
        self,
        start_date: date,
        end_date: date,
        underlying: str = "NIFTY_50",
        expiry_date: date | None = None,
        option_type: str | None = None,
        delta_min: float | None = None,
        delta_max: float | None = None,
    ) -> pd.DataFrame:
        """Scan EOD Parquet files for the given date range and optional filters.

        Globs: {eod_dir}/{year}/{month}/upstox_*.parquet (all files, filter by snapshot_ts).
        Returns empty DataFrame (correct columns) if no files exist.
        """

    def get_intraday_snapshots(
        self,
        trade_date: date,
        underlying: str = "NIFTY_50",
        expiry_date: date | None = None,
        strike: Decimal | None = None,
        option_type: str | None = None,
    ) -> pd.DataFrame:
        """Scan intraday Parquet files for a single trading day.

        Globs: {intraday_dir}/{year}/{month}/{day}/upstox_*.parquet.
        Returns empty DataFrame if no files exist or intraday_dir is None.
        """

    def get_strike_delta_series(
        self,
        start_date: date,
        end_date: date,
        strike: Decimal,
        option_type: str,
        underlying: str = "NIFTY_50",
    ) -> pd.DataFrame:
        """Return daily delta time series for a specific strike.

        Convenience wrapper over get_eod_snapshots. Columns: snapshot_ts, delta, iv, ltp.
        """
```

Use DuckDB's `read_parquet(glob, hive_partitioning=false)` with `WHERE` pushdown for efficiency.
Open a single `duckdb.connect()` per `ChainReader` instance (in-memory, not persisted).
Return pandas DataFrames (consistent with vix_ingest.py pattern).
Return empty `pd.DataFrame(columns=[...])` — never raise — when no files match.

**Tests (≥8):**
- `test_get_eod_snapshots_happy_path` — write fixture Parquet files via `ChainWriter`, read back with `ChainReader`; assert row count and column names
- `test_get_eod_snapshots_date_filter` — two files for different dates; filter by range; assert only correct date returned
- `test_get_eod_snapshots_empty_dir` — non-existent dir → empty DataFrame with correct columns
- `test_get_eod_snapshots_delta_filter` — assert only rows with delta in range returned
- `test_get_intraday_snapshots_happy_path` — write intraday Parquet, read back; assert row count
- `test_get_intraday_no_intraday_dir` — `intraday_dir=None` → empty DataFrame, no error
- `test_get_strike_delta_series` — assert columns = `[snapshot_ts, delta, iv, ltp]`; one row per file
- `test_get_strike_delta_series_empty` — no matching strike → empty DataFrame

Use `tmp_path` + `ChainWriter` to create real Parquet fixtures. No mocking of DuckDB.

**Commit message:**
```
feat(backtest): ChainReader — DuckDB-based EOD and intraday chain query utilities

Why: Downstream consumers (1.6a delta drift, 1.4 slippage model, Phase 3 signals)
     need a consistent scan interface over accumulated chain Parquet files.
What:
- src/backtest/chain_reader.py: ChainReader with EOD + intraday + delta series queries
- tests/unit/backtest/test_chain_reader.py: 8 tests using real Parquet fixtures
Ref: docs/plan/chain-data/chain_data_stories.md CD3.1
```

---

## CD4 — Docs close

**Files to change (targeted `Edit` only — never `Write` on these files):**
- `CONTEXT.md` — add `src/backtest/chain_writer.py` and `src/backtest/chain_reader.py` to "What Exists" tree
- `DECISIONS.md` — add: "chain-data story supersedes tasks 1.10 + 1.10a (2026-05-27): both tasks migrated to `docs/plan/chain-data/` story with Parquet storage confirmed. `1_10_dhan_chain_client.md` archived as ABANDONED."
- `BACKTEST_PLAN_PHASE1.md` — tick `[x]` on tasks 1.10 and 1.10a checkboxes; append note "→ migrated to chain-data story (`docs/plan/chain-data/`)"
- `TODOS.md` — session log entry

**No code changes in this task. No tests required. Commit immediately after edits.**

**Commit message:**
```
docs(chain-data): close chain-data story — CONTEXT, DECISIONS, BACKTEST_PLAN updated

Why: Docs must reflect completed chain-data implementation; 1.10 + 1.10a checkboxes
     in BACKTEST_PLAN_PHASE1.md must be ticked to unblock 1.12 gate.
What:
- CONTEXT.md: chain_writer + chain_reader added to What Exists tree
- DECISIONS.md: chain-data supersession note added
- BACKTEST_PLAN_PHASE1.md: 1.10 + 1.10a ticked
- TODOS.md: session log entry
Ref: none
```

---

## Session log

_(append-only, dated entries)_
