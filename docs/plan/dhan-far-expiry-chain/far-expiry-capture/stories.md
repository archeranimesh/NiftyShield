# Far-Expiry Capture — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` + tick the box,
> update story status, add one line to `TODOS.md`.

---

## FC-1 — Storage decision

**Files to change / create:** `DECISIONS.md` (entry), `DB_REGISTRY.md` (row, only if a table is created), `docs/plan/dhan-far-expiry-chain/far-expiry-capture/schema.md` (only if SQLite).

**Before any code:** read `DB_REGISTRY.md` first; `get_code_snippet("ChainWriter")`, `get_code_snippet("ChainReader")` — can they hold bid, ask, bid/ask size, OI, IV and all four Greeks per strike per
snapshot? Check `src/intraday/market_store.py` as the SQLite prior art for broker-agnostic market data.

**What to implement:** a one-page comparison and a choice. Default recommendation: `ChainWriter` Parquet if it fits (existing chain-history pattern, DuckDB for the report), else one SQLite table with
`Decimal` as `TEXT` and unique key `(snapshot_date, expiry, strike, option_type, source)`.

**Tests:** none (docs-only).

**Commit:** `docs: decide far-expiry chain capture storage`

---

## FC-2 — Writer, reader, reducer

**Files to change / create:** per FC-1 (a `src/` module with `__init__.py`, graph re-index after), `tests/unit/.../test_far_expiry_store.py`.

**Before any code:** `get_code_snippet("OptionChain")`, `get_code_snippet("OptionLeg")`; if SQLite, the `schema.md` from FC-1 and `src/db.py` context manager.

**What to implement:** `record_chain(snapshot_date, source, chain)` idempotent on the unique key; reader returning rows for a date range; pure `chain_to_liquidity_rows(chain)` producing per-strike
quote status, spread %, OI and delta presence.

**Tests:** `test_record_then_read_round_trip`, `test_record_twice_is_idempotent`, `test_zero_delta_rows_flagged`, `test_one_sided_quote_flagged_not_quoted`.

**Commit:** `feat(capture): add far-expiry chain store and reducer`

---

## FC-3 — Capture entrypoint

**Files to change / create:** `scripts/pipeline/capture_far_expiry_chain.py`, `tests/unit/scripts/test_capture_far_expiry_chain.py`.

**Before any code:** read `LOGGING.md`; `get_code_snippet("setup_logging")`; `search_graph("guard_trading_day")`; the heartbeat writer used by another cron.

**What to implement:** `_SCRIPT_NAME = "scripts.pipeline.capture_far_expiry_chain"`; `setup_logging()`; `guard_trading_day`; expiries = nearest yearly (December) plus the next yearly, via
`get_expiry_candidates`; fetch each through the chain-source seam with 4 s spacing; write; record a heartbeat; non-zero exit on total failure, partial failure logged per expiry.

**Tests:** `test_capture_writes_each_expiry`, `test_holiday_exits_cleanly_no_calls`, `test_805_logged_run_continues`, `test_no_get_logger_dunder_name` (pre-commit rule).

**Commit:** `feat(capture): add daily far-expiry chain capture script`

---

## FC-4 — Cron and healthcheck (Animesh)

**Files:** host crontab (after 15:30 IST, Mon-Fri), `scripts/healthcheck.py` registration if not automatic. **Write:** the exact cron line in the story `findings.md`; confirm the first heartbeat
appears. **Tests:** none. **Commit:** `docs(plan): record far-expiry capture cron`

---

## FC-5 — Liquidity report

**Files to change / create:** `scripts/dev/far_expiry_liquidity_report.py`, `tests/unit/scripts/test_far_expiry_liquidity_report.py`.

**Before any code:** `get_code_snippet` for the FC-2 reader; `SCRATCH.md` convergence rule (this is a tested CLI per the repo's no-throwaway-scripts rule).

**What to implement:** for a date range and expiry, print per day the target-delta strikes (calls and puts at the configured deltas), their quote status, spread % of mid, OI, and the count of
non-zero-delta rows; aggregates in the query, a compact table out (Rule 1 output discipline).

**Tests:** `test_report_from_stored_rows_no_network`, `test_report_empty_range_prints_message`.

**Commit:** `feat(dev): add far-expiry liquidity report CLI`
