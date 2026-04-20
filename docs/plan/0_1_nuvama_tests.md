# 0.1 — Tests for Nuvama options + intraday (protocol debt)

**Status:** NOT STARTED
**Owner:** Cowork
**Phase:** 0
**Blocks:** 0.8 (Phase 0 gate)
**Blocked by:** —
**Estimated effort:** M (1-3 days)
**Literature:** none

## Problem statement

The Nuvama options tracking and intraday monitoring features were built outside the standard protocol and shipped without unit tests. This violates the repo's core rule from `CLAUDE.md` Step 4: every public function needs a happy-path test plus an error/edge-case test. `TODOS.md` item 0 catalogs the specific untested methods.

Untested code in a financial system is a deferred bug. The longer the gap persists, the harder it becomes to safely refactor anything that touches those modules — which matters because several downstream phases (portfolio attribution in 3.4, regime snapshots in 3.5) will extend the Nuvama store. Without tests, those extensions become risky.

This task closes the gap before any further work builds on `src/nuvama/`.

## Acceptance criteria

- [ ] `tests/unit/nuvama/test_models.py` contains tests for `NuvamaOptionPosition` construction (valid + 3 invalid cases), `NuvamaOptionsSummary` construction, and `NuvamaOptionsSummary.net_pnl` property (verifies `unrealized + cumulative_realized` math).
- [ ] `tests/unit/nuvama/test_options_reader.py` (new file) covers `parse_options_positions()`: OPTIDX happy path, OPTSTK happy path, skips non-option rows, handles flat position (`net_qty=0`), handles missing `resp.data.pos`, handles malformed record (KeyError/ValueError/InvalidOperation).
- [ ] `tests/unit/nuvama/test_options_reader.py` covers `build_options_summary()`: aggregation math with known inputs, intraday high/low propagation from input, empty positions list returns summary with zero totals.
- [ ] `tests/unit/nuvama/test_store.py` extended with: `record_options_snapshot` upsert + idempotency (same `(trade_symbol, snapshot_date)` second write updates), `get_cumulative_realized_pnl` SUM across multiple symbols and dates, `get_options_snapshot_for_date` retrieval match and miss, `record_intraday_positions` insert + auto-purge on call (rows older than 30 days deleted), `get_intraday_extremes` max/min/nifty aggregation, empty-date returns `(None, None, None, None)`.
- [ ] All new tests offline — no network calls, no real Nuvama session.
- [ ] New test count: ≥25. (Models: ~6, options_reader: ~10, store additions: ~10.)

## Definition of Done

- [ ] `python -m pytest tests/unit/nuvama/` green
- [ ] `python -m pytest tests/unit/` full suite green
- [ ] `code-reviewer` agent clean on diff
- [ ] `CONTEXT.md` test coverage section updated with new counts
- [ ] `TODOS.md` item 0 marked done, session log entry added
- [ ] `BACKTEST_PLAN.md` task 0.1 checkbox ticked
- [ ] Commit: `test(nuvama): add coverage for options + intraday` in conventional format

## Technical notes

- All tests use `tmp_path` fixture for file-backed SQLite, not `:memory:`, because `NuvamaStore._connect()` opens and closes fresh connections.
- For `build_options_summary()`, construct test input as a list of `NuvamaOptionPosition` instances directly — do not invoke `parse_options_positions` as a dependency; this keeps the two functions' tests independent.
- For `record_intraday_positions` purge test: insert rows dated 31+ days ago, call `record_intraday_positions` with a new row, assert the old rows are gone via `SELECT COUNT(*)`. Cannot rely on `time.time()` for "31 days ago" — use a fixed date in the test and parameterise if needed.
- `get_cumulative_realized_pnl` test: insert 3 rows for same `trade_symbol` across 3 dates with known `realized_pnl_today` values, assert the return equals the Decimal sum.
- Pydantic validation tests for `NuvamaOptionPosition`: verify Decimal precision preserved round-trip, verify frozen (assignment raises), verify required fields reject None/missing.

## Non-goals

- Does NOT add new features to `src/nuvama/`. Test-only.
- Does NOT refactor existing code. If a tested function is obviously broken, file a separate bug-fix story — don't silently fix in a test commit.
- Does NOT touch Nuvama bond code (already tested).

## Follow-up work

None directly. Closes a gap in the existing feature set.

---

## Session log

_(append-only, dated entries)_
