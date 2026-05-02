# BACKTEST_PLAN — Completed Phase 0 Tasks

> Archived from `BACKTEST_PLAN.md` on 2026-05-02 to reduce session token load.
> These tasks are fully done. Do not edit. For the active plan see `BACKTEST_PLAN.md`.

---

## 0.1 — DONE — Tests for Nuvama options + intraday ✓ 2026-04-24 (cd3ed6b)

- [x] `tests/unit/nuvama/test_models.py` — `NuvamaOptionPosition`, `NuvamaOptionsSummary.net_pnl`
- [x] `tests/unit/nuvama/test_options_reader.py` — `parse_options_positions()`, `build_options_summary()`
- [x] `tests/unit/nuvama/test_store.py` — `record_options_snapshot`, `get_cumulative_realized_pnl`, `record_intraday_positions`, `get_intraday_extremes`
- [x] Full suite green; `code-reviewer` clean; committed `test(nuvama): add coverage for options + intraday`

---

## 0.2 — DONE — Greeks capture (`OptionChain` model + `_extract_greeks_from_chain`) ✓ 2026-04-25

- [x] `OptionChain` Pydantic model in `src/models/options.py` — source-agnostic field names; Upstox parser in `src/client/upstox_market.py`
- [x] `_extract_greeks_from_chain()` in `tracker.py` — pure function, fixture-tested; uses `NSE_INDEX|Nifty 50` key
- [x] Greeks populate in `daily_snapshots` from 2026-04-25 onwards
- [x] 16 fixture-driven tests in `tests/unit/test_greeks_capture.py`
- [x] Committed `feat(models): add source-agnostic OptionChain model + Upstox Greeks capture`

---

## 0.4 — DONE — Choose first paper-trade strategy ✓ 2026-04-25 (fb69043)

- [x] `docs/strategies/csp_niftybees_v1.md` written (all required sections present)
- [x] 2026-04-25: Underlying switched to Nifty 50 index options → `docs/strategies/csp_nifty_v1.md` (canonical); `csp_niftybees_v1.md` retained DEPRECATED

---

## 0.4a — DONE — NiftyShield Integrated Strategy Specification ✓ 2026-04-26 (88dc95e)

- [x] `docs/strategies/niftyshield_integrated_v1.md` — CSP Leg 1 + put spread (4 lots, 8–20% OTM) + tail puts (2 lots, 5-delta quarterly)
- [x] Passes `validate_strategy_spec.py`

---

## 0.5 — DONE — Paper trading module (`src/paper/`) ✓ 2026-04-25 (5ccfc52)

- [x] `src/paper/` package: `models.py` (`PaperTrade`, `PaperPosition`, `PaperNavSnapshot`), `store.py` (`paper_trades` + `paper_nav_snapshots` tables, Decimal-as-TEXT), `tracker.py` (`compute_pnl`, `record_daily_snapshot`, `record_all_strategies`)
- [x] `scripts/record_paper_trade.py` — enforces `paper_` prefix on strategy names
- [x] 65 tests (20 models, 24 store, 18 tracker, 9 CLI); `code-reviewer` clean
- [x] Paper trading runs standalone (not wired into `daily_snapshot.py`)

---

## 0.7 — DONE — Strategy specification validator ✓ (after 0.5)

- [x] `scripts/validate_strategy_spec.py` — checks required sections (Name, Entry, Exit, Adjustment, Sizing, Kill Criteria, Variance Threshold); non-zero exit on missing sections
- [x] 28 tests in `tests/unit/test_validate_strategy_spec.py` (parametrised, all green)
- [x] Committed `feat(scripts): strategy spec validator`
