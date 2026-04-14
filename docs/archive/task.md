# Dhan Portfolio Integration — Task List

## Phase 1: Core Module (`src/dhan/`)
- [ ] `src/dhan/__init__.py` — package marker
- [ ] `src/dhan/models.py` — DhanHolding, DhanPortfolioSummary dataclasses
- [ ] `src/dhan/reader.py` — fetch holdings, fetch LTP via marketfeed/ltp, classify, build summary
- [ ] `src/dhan/store.py` — SQLite persistence (dhan_holdings_snapshots table)
- [ ] `src/dhan/CLAUDE.md` — module context

## Phase 2: Integration
- [ ] `src/portfolio/models.py` — extend PortfolioSummary with Dhan fields
- [ ] `scripts/daily_snapshot.py` — wire Dhan into _async_main + _historical_main
- [ ] `scripts/daily_snapshot.py` — restructure _format_combined_summary (Equity/Bonds/Derivatives)
- [ ] `scripts/daily_snapshot.py` — restructure _build_portfolio_summary to include Dhan

## Phase 3: Tests
- [ ] `tests/unit/dhan/test_models.py`
- [ ] `tests/unit/dhan/test_reader.py`
- [ ] `tests/unit/dhan/test_store.py`
- [ ] `tests/fixtures/responses/dhan_holdings.json`
- [ ] `tests/fixtures/responses/dhan_ltp.json`
- [ ] Run full test suite — no regressions

## Phase 4: Documentation
- [ ] Update CONTEXT.md, DECISIONS.md, REFERENCES.md, TODOS.md
