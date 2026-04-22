# P2 — Architecture Implementation Plan

This plan outlines the steps to resolve the P2 architecture issues (AR-4, AR-5, AR-6, AR-7) to prepare the NiftyShield codebase for Phase 0 CSP expansion.

## User Review Required

The plan is divided into three distinct phases. Each phase will be executed and committed separately to isolate changes and minimize the blast radius if test failures occur.

## Proposed Changes

### Phase 1 — AR-7 (Atomicity)
**Target:** `src/nuvama/store.py`, `tests/unit/nuvama/test_store.py`
- Rewrite `record_all_snapshots` and `record_all_options_snapshots` to use `conn.executemany` in a single `with connect(...) as conn:` block.
- **Testing:** Update `tests/unit/nuvama/test_store.py` to include a failure-injection test. We will pass a batch of rows where a middle row is corrupt (e.g., violating a UNIQUE or NOT NULL constraint) to force an exception during `executemany`. The test will assert that the transaction rolls back completely and the table remains empty, proving atomicity.

### Phase 2 — AR-5 (Typing Pass)
**Target:** `src/portfolio/summary.py`, `src/portfolio/formatting.py`
- Add `TYPE_CHECKING` imports for `PortfolioPnL`, `DhanPortfolioSummary`, `NuvamaBondSummary`, and `NuvamaOptionsSummary`.
- Replace all `object | None` parameters with their exact types.
- Remove the `# type: ignore[union-attr]` suppressions.
- **Note:** This is purely a type-annotation pass with no behavioral changes. Tests remain unchanged.

### Phase 3 — AR-4 + AR-6 (Structural Refactor)
**Targets:** `src/models/portfolio.py`, `src/portfolio/summary.py`, `src/portfolio/formatting.py`, `src/nuvama/store.py`, `scripts/daily_snapshot.py`, and test files.

**AR-4 (`PortfolioSummary` Refactoring):**
- In `src/models/portfolio.py`, add `TYPE_CHECKING` imports. To avoid runtime `NameError` during module load, field annotations for the newly added objects must use string literals (or `from __future__ import annotations`). We will use string literals, e.g., `mf_pnl: "PortfolioPnL | None" = None`.
- Remove all flat source-specific properties (e.g., `dhan_equity_value`, `nuvama_bond_basis`) from `PortfolioSummary`.
- Add typed references: `mf_pnl`, `dhan`, `nuvama_bonds`, `nuvama_options`.
- Update `_build_portfolio_summary` to compute aggregates and pass the summary objects directly into `PortfolioSummary`.
- Update `_format_combined_summary` and `_format_protection_stats` to access source-specific data via these objects (e.g., `summary.dhan.equity_value` instead of `summary.dhan_equity_value`), with appropriate `None` checks.

**AR-6 (`NuvamaBondHolding` Historical Hack):**
- **Justification for approach:** Extracting actual `qty` and `ltp` from `nuvama_holdings_snapshots` is the most correct approach because it reconstructs the historical state using actual recorded values rather than reverse-engineering them from a stored aggregate. This eliminates the hacky dummy stubs and doesn't require adding a new factory method that bypasses the model.
- **DDL Verification:** Verified that `_CREATE_SNAPSHOTS` in `store.py` already includes `qty` and `ltp` columns. No schema migration is required.
- Update `NuvamaStore.get_snapshot_for_date` to return `isin`, `qty`, `ltp`, and `current_value` as a dictionary (e.g., list of dicts).
- **Callers to update:** `scripts/daily_snapshot.py` (line 229) and `tests/unit/nuvama/test_store.py` (8 instances).
- In `_historical_main()`, use the returned `qty` and `ltp` to construct completely accurate `NuvamaBondHolding` objects.

**Affected Test Files:**
Based on codebase search, the following test files interact with `PortfolioSummary` and need schema updates:
- `tests/unit/dhan/test_daily_snapshot_dhan.py`
- `tests/unit/dhan/test_models.py`
- `tests/unit/nuvama/test_portfolio_summary_nuvama.py`
- `tests/unit/nuvama/test_daily_snapshot_nuvama.py`
- `tests/unit/mf/test_daily_snapshot_helpers.py`

## Verification Plan

### Automated Tests
1. Run `python -m pytest tests/unit/` to ensure all 859+ tests pass.
2. Add a new test case exercising `_format_combined_summary` with a fully populated `PortfolioSummary` (containing all nested objects) to catch any potential `None`-dereferencing bugs from the AR-4 changes.
3. Run the code-reviewer agent (`.claude/agents/code-reviewer.md`) as mandated by `CLAUDE.md` to verify the architectural integrity of the changes.

### Manual Verification
1. Run `python -m scripts.daily_snapshot --date <recent_snapshot_date>` to verify historical reconstruction works. Specifically verify that the `NuvamaBondSummary` output matches what the live snapshot path would produce for that date.
2. Run `python -m scripts.daily_snapshot` locally with a dry-run or sandbox token to ensure formatting correctly outputs the same visual Telegram-ready message.
