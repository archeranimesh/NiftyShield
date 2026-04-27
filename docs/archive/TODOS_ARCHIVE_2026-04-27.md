# NiftyShield — Completed Work Archive

> Archived: 2026-04-27. Contains all completed TODO items and session log through 2026-04-26.
> Active open work lives in [TODOS.md](../../TODOS.md).

---

## Completed Feature TODOs (archived 2026-04-27)

### P1-NEXT — Greeks Capture — DONE 2026-04-25

Story file: `docs/plan/0_2_greeks_capture.md`

Implemented: `src/models/options.py` (OptionLeg, OptionChainStrike, OptionChain), `src/client/upstox_market.py` (parse_upstox_option_chain + _parse_option_leg + _safe_decimal), `src/portfolio/tracker.py` (_extract_greeks_from_chain + real _fetch_greeks), `tests/unit/test_greeks_capture.py` (16 tests, all green). 883 tests total passing.

### P1-NEXT — Paper Trading Module — DONE 2026-04-25

Sprint 0.5 from `BACKTEST_PLAN.md`.

Implemented:
- `src/paper/__init__.py`, `src/paper/CLAUDE.md` — package + module invariants doc
- `src/paper/models.py` — `PaperTrade` (frozen Pydantic, `paper_` prefix validator, `is_paper: Literal[True]`), `PaperPosition` (frozen dataclass, `avg_cost` + `avg_sell_price`), `PaperNavSnapshot` (frozen dataclass)
- `src/paper/store.py` — `PaperStore` with `paper_trades` + `paper_nav_snapshots` tables; UNIQUE idempotency; Decimal-as-TEXT invariant
- `src/paper/tracker.py` — `PaperTracker.compute_pnl()` + `record_daily_snapshot()` + `record_all_strategies()`; correct short P&L via `avg_sell_price`
- `scripts/record_paper_trade.py` — CLI mirroring `record_trade.py`; enforces `paper_` prefix; prints position summary post-insert
- Paper trading is standalone — not wired into `daily_snapshot.py`.
- `tests/unit/paper/` — 65 tests (20 models, 24 store, 18 tracker, 9 CLI). 948 total passing.

Architecture decision recorded in `DECISIONS.md`: shared SQLite DB + `paper_` prefix convention; `avg_sell_price` tracked separately for short positions.

### P1-NEXT — Strategy Spec Validator — DONE 2026-04-25

Sprint 0.7 from `BACKTEST_PLAN.md`.

Implemented:
- `scripts/validate_strategy_spec.py` — reads `docs/strategies/*.md`; skips DEPRECATED files; validates 8 required `##` section headers; exits 1 on any active failure.
- `tests/unit/test_validate_strategy_spec.py` — 28 tests: happy path, case/plural heading variants, deprecated detection (both formats), per-section missing parametrised, multi-missing, directory scan, explicit file path, live smoke-test against `csp_nifty_v1.md`. All green. 952 total passing.
- `csp_nifty_v1.md` confirmed passing. `csp_niftybees_v1.md` correctly skipped as DEPRECATED.

### P5-DEBT — DEBT-1: `@staticmethod` overuse (TD-1) — DONE 2026-04-24

All 8 `@staticmethod` row-mapper / helper methods promoted to module-level `_private_function()`. No logic changes. 868 tests green.

---

## Session Log (2026-04-24 through 2026-04-26)

| Date | What Changed |
|---|---|
| 2026-04-24 | **DEBT-1 (`@staticmethod` overuse).** Promoted 8 static methods to module-level `_private_function()` across `src/mf/store.py`, `src/portfolio/store.py`, `src/portfolio/tracker.py`, `src/dhan/store.py`, `src/instruments/lookup.py`, `src/client/upstox_market.py`. Added `import sqlite3` to `dhan/store.py`. 868 tests green. |
| 2026-04-24 | **Root markdown cleanup.** Archived all ✅ DONE items (PKG-1–4, DEBT-2,4,5) + session log to TODOS_ARCHIVE_2026-04-24.md. Moved `python-architecture-review.prompt.md` to `docs/`. Updated README.md project structure to actual src/ layout. Wrote `.claude/skills/md-cleanup/SKILL.md`. |
| 2026-04-24 | **P&L Visualization scoping.** Audited DB for all viable data sources. Expanded P3-DEFER with 4 panels (MF, Dhan ETFs, Nuvama Bonds, Nuvama Options), data availability, P&L formulas, and known gap (Zerodha/FinRakshak not integrated). |
| 2026-04-24 | **Zerodha/Kite feasibility + corrections.** Corrected Panel 4 attribution (Nuvama options ≠ FinRakshak; FinRakshak + ILTS run on Zerodha). Added P3-DEFER entry for Kite Connect integration with free/paid tier analysis, hybrid architecture approach, and Kite MCP note. |
| 2026-04-25 | **NiftyBees collateral leg — docs + design decision.** No code changes. Decision recorded in `DECISIONS.md`: NiftyBees ETF (NSE_EQ|INF204KB14I2) modelled as `long_niftybees` leg in paper P&L; qty = floor(lot_size × nifty_spot / niftybees_ltp); annual reset in January. `docs/strategies/csp_nifty_v1.md` updated with collateral leg setup section + exact `record_paper_trade.py` command (5725 units @ 271.35 on 2026-04-25). `BACKTEST_PLAN.md` 1.7 extended: `CSPConfig.niftybees_instrument_key`, NiftyBees collateral leg required in backtest P&L, historical ETF OHLC needed; Phase 2.2 lot-size note corrected (65, not 35). |
| 2026-04-25 | **Greeks capture implemented (task 0.2).** `src/models/options.py` (OptionLeg, OptionChainStrike, OptionChain frozen Pydantic), `src/client/upstox_market.py` (parse_upstox_option_chain + _parse_option_leg + _safe_decimal helper), `src/portfolio/tracker.py` (_extract_greeks_from_chain + real async _fetch_greeks replacing early-return stub), `tests/unit/test_greeks_capture.py` (16 fixture-driven offline tests). Greeks columns in daily_snapshots now populated. 883 tests green. |
| 2026-04-25 | **Paper trading module (sprint 0.5).** `src/paper/` package: `PaperTrade` (frozen Pydantic, `paper_` prefix validator), `PaperPosition` + `PaperNavSnapshot` (frozen dataclasses), `PaperStore` (paper_trades + paper_nav_snapshots in shared SQLite), `PaperTracker` (compute_pnl + record_daily_snapshot + record_all_strategies). `scripts/record_paper_trade.py` with `--underlying/--strike/--option-type/--expiry` auto-lookup via InstrumentLookup. `scripts/paper_snapshot.py` standalone mark-to-market. `docs/paper_trading.md` end-to-end guide. Not wired into daily_snapshot.py. 65 tests. 948 total passing. |
| 2026-04-25 | **`find_strike_by_delta.py` scoped.** Added P1-NEXT TODO for live option chain strike filter by delta range. No code yet — all dependencies in place. |
| 2026-04-25 | **CSP v1 strategy review.** Underlying switched from NiftyBees options → Nifty 50 index options (liquidity: OI <1000 / spreads >5% on NiftyBees). `docs/strategies/csp_nifty_v1.md` created as successor; `csp_niftybees_v1.md` retained DEPRECATED. Rules revised: R1 time-stop clarified (21 calendar days from entry), R2 loss-stop changed to delta gate −0.45 OR 1.75× mark, R3 IVR filter added (specified, not yet enforced — no VIX ingestion pipeline), R4 event filter added (specified, not yet enforced — pending task 3.3), R5 re-entry revised (IVR-gated after profit exit), R6 kill criterion added (3× avg credit single-cycle stop), R7 slippage model revised (bid-ask based). Lot size documented as 65 (Jan 2026). Paper-trade minimum raised from 2 cycles to 6 cycles. `DECISIONS.md` updated with Strategy Decisions section. `BACKTEST_PLAN.md` updated: tasks 0.4/0.6/0.8/1.1/1.7/1.8/1.11 revised to reflect new underlying and V1/V2/V3 variant backtest structure. |
| 2026-04-26 | **NiftyShield integrated strategy design.** Analysed FinRakshak coverage gap (~15% of ₹80L+ MF portfolio). Designed integrated strategy: CSP income (1 lot, per `csp_nifty_v1.md`) + protective put spread (4 lots, 8–20% OTM monthly) + quarterly tail puts (2 lots, 5-delta). Net annual cost ₹1.5L–₹3.3L (within 3–5% budget). Wrote `docs/strategies/niftyshield_integrated_v1.md` — passes validator. Two-tier backtest methodology: real data for CSP, BS synthetic pricing with vol skew for protective legs. Updated `DECISIONS.md` (3 entries: integrated strategy, static beta, two-tier backtest). Updated `BACKTEST_PLAN.md` (tasks 0.4a, 0.6a, 1.9, 1.9a; gates 0.8 + 1.12 extended). FinRakshak treated as independent — not counted in hedge ratio. |
