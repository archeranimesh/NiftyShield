# P2 — Architecture Implementation Plan

This plan outlines the steps to resolve the P2 architecture issues (AR-4, AR-5, AR-6, AR-7) to prepare the NiftyShield codebase for Phase 0 CSP expansion.

## User Review Required

- **AR-4 (`PortfolioSummary` Refactoring):** We will remove all source-specific flattened fields (e.g., `dhan_equity_value`, `nuvama_bond_basis`) from `PortfolioSummary`. Instead, it will contain references to the source summaries (`dhan`, `nuvama_bonds`, `nuvama_options`, `mf_pnl`). This requires cascading changes to `_build_portfolio_summary`, `_format_combined_summary`, and all related tests.
- **AR-6 (`NuvamaBondHolding` Historical Hack):** The database table `nuvama_holdings_snapshots` already stores `ltp` and `qty`. We will update `NuvamaStore.get_snapshot_for_date` to return these fields instead of just `current_value`, and use them to construct completely accurate `NuvamaBondHolding` objects in `_historical_main()`. 

## Open Questions

None currently.

## Proposed Changes

---

### `src/models/`

#### [MODIFY] [portfolio.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/models/portfolio.py)
- Import `TYPE_CHECKING` and add conditional imports for `PortfolioPnL`, `DhanPortfolioSummary`, `NuvamaBondSummary`, and `NuvamaOptionsSummary`.
- Refactor `PortfolioSummary` dataclass:
  - Remove all flat `mf_*`, `dhan_*`, and `nuvama_*` properties (e.g., `dhan_equity_value`, `nuvama_options_pnl`, etc.).
  - Add optional typed references: `mf_pnl: PortfolioPnL | None`, `dhan: DhanPortfolioSummary | None`, `nuvama_bonds: NuvamaBondSummary | None`, `nuvama_options: NuvamaOptionsSummary | None`.
  - Keep combined aggregate fields: `total_value`, `total_invested`, `total_pnl`, `total_pnl_pct`, `total_day_delta`, `etf_value`, `etf_basis`, `etf_day_delta`, `options_pnl`, `options_day_delta`, `finrakshak_day_delta`.

---

### `src/portfolio/`

#### [MODIFY] [summary.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/portfolio/summary.py)
- Import `TYPE_CHECKING` and correctly type the parameters in `_build_portfolio_summary` (replacing `object | None`).
- Remove the 14 `# type: ignore[union-attr]` suppressions.
- Update `_build_portfolio_summary` logic to compute the cross-source aggregates (e.g., `total_value`) directly from the passed source summaries, and store the source summaries inside the returned `PortfolioSummary` rather than unpacking all their fields.

#### [MODIFY] [formatting.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/portfolio/formatting.py)
- Import `TYPE_CHECKING` and correctly type parameters where appropriate.
- Update `_format_combined_summary` and `_format_protection_stats` to access source-specific data via the typed optional references in `PortfolioSummary` (e.g., `summary.dhan.equity_value` instead of `summary.dhan_equity_value`). Add appropriate `None` checks.

---

### `src/nuvama/`

#### [MODIFY] [store.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/nuvama/store.py)
- Update `get_snapshot_for_date` to return a list of dicts including `isin`, `qty`, `ltp`, and `current_value` instead of just mapping ISIN to `current_value`.
- Make `record_all_snapshots` atomic by using a single `with connect(self._db_path) as conn:` block and `conn.executemany` with the `INSERT ... ON CONFLICT ...` query.
- Make `record_all_options_snapshots` atomic in the exact same manner.

---

### `scripts/`

#### [MODIFY] [daily_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/daily_snapshot.py)
- Update `_historical_main` to accommodate the change in `NuvamaStore.get_snapshot_for_date`'s return type.
- Remove the `qty=1` stub hack in `_historical_main`. Pass the true `qty` and `ltp` returned from the database to reconstruct accurate `NuvamaBondHolding` instances.

---

### `tests/`

#### [MODIFY] test files (multiple)
- Update all tests that instantiate or assert against `PortfolioSummary` to align with the new schema (e.g., `tests/unit/portfolio/test_summary.py`, `tests/unit/test_daily_snapshot_historical.py`, `tests/unit/dhan/test_daily_snapshot_dhan.py`, etc.).
- Add atomic tests for `record_all_snapshots` and `record_all_options_snapshots` in `tests/unit/nuvama/test_store.py` (verifying partial write rollback).

## Verification Plan

### Automated Tests
- Run `python -m pytest tests/unit/` to ensure all 859+ tests pass.

### Manual Verification
- Run `python -m scripts.daily_snapshot --date <recent_snapshot_date>` to verify historical reconstruction works exactly as before.
- Run `python -m scripts.daily_snapshot` locally (dry run / test DB) to ensure live snapshot and formatting still works correctly.
