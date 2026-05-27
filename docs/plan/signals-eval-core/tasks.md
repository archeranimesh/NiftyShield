# signals-eval-core — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md` session log.
> Full story spec for each task: `docs/plan/signals-eval-core/stories.md`.
>
> **Prerequisite check before SE1.1:**
> - Tasks 1.3 (Bhavcopy ingest) and 1.3a (Nifty OHLC Parquet) in BACKTEST_PLAN_PHASE1.md are committed.
> - `backtest-eval-core` tasks B1.1–B2.9 are committed (BacktestStore + analytics layer).
> If either block is incomplete, stop — this plan cannot start.

---

## Phase SE1 — Data Infrastructure

- [ ] **SE1.1** — Verify Nifty 50 daily + 15-min OHLC Parquet coverage; confirm derived fields (ATR-14, ATR-40, ATR-20, 50D slope); generate data integrity report
- [ ] **SE1.2** — `src/instruments/pe_loader.py`: NSE PE CSV download + Parquet storage + gap fill + tests
- [ ] **SE1.3** — Risk-free rate series: monthly liquid fund NAV from AMFI → Parquet; `get_risk_free_rate(date) → Decimal` helper + tests

## Phase SE2 — Strategy Package + Regime Engine

- [ ] **SE2.1** — `src/strategy/` package setup: `__init__.py`, `CLAUDE.md` with module invariants, `src/strategy/signals/__init__.py` stub
- [ ] **SE2.2** — `src/strategy/regime.py`: `RegimeTagger` + `RegimeTag` frozen dataclass + `tag_date(row) → RegimeTag` + `tag_history(df) → list[RegimeTag]` + tests; init_db + `record_regime_tag` + `get_regime_tag` in `SignalEvalStore` (SE3.1 will extend this store)
- [ ] **SE2.3** — `scripts/regime_distribution_report.py`: load Nifty OHLC Parquet → tag all historical days → print 3×3 cell distribution (% days, % total return); visual sanity check script — no unit tests

## Phase SE3 — Swing Signal Generators

- [ ] **SE3.1** — `src/strategy/signals/donchian.py`: `DonchianConfig` frozen dataclass + `DonchianSignalGenerator.generate(df) → list[SwingSignal]`; `SwingSignal` frozen dataclass (shared with ORB/Gap Fade); `SignalEvalStore.record_swing_signal` + `get_swing_signals`; tests
- [ ] **SE3.2** — `src/strategy/signals/orb.py`: `ORBConfig` + `ORBSignalGenerator.generate(daily_df, intraday_df, vix_df) → list[SwingSignal]`; structural calendar exclusions via `is_event_exclusion_date`; DTE expiry selection via `select_expiry`; tests
- [ ] **SE3.3** — `src/strategy/signals/gap_fade.py`: `GapFadeConfig` + `GapFadeSignalGenerator.generate(daily_df, intraday_df, vix_df) → list[SwingSignal]`; VIX-IVP filter (63D, 75th pctile); tests

## Phase SE4 — Investment Signal Generators

- [ ] **SE4.1** — `src/strategy/signals/sma_filter.py`: `SMAFilterConfig` + `SMASignalGenerator.generate(monthly_df) → list[AllocationDecision]`; `AllocationDecision` frozen dataclass (shared across SE4.x); `SignalEvalStore.record_allocation_decision` + `get_allocation_decisions`; tests
- [ ] **SE4.2** — `src/strategy/signals/dual_mom.py`: `DualMomConfig` + `DualMomSignalGenerator.generate(monthly_df, rf_series) → list[AllocationDecision]`; tests
- [ ] **SE4.3** — `src/strategy/signals/pe_band.py`: `PEBandConfig` + `PEBandSignalGenerator.generate(monthly_pe_df, quarterly_dates) → list[AllocationDecision]`; tests
- [ ] **SE4.4** — Covered Call Overlay paper-trading setup (no backtest engine required): create `docs/strategies/covered_call_overlay_v1.md`; confirm Upstox broker pledge compatibility; paper-trade with prefix `paper_covered_call_v1`; retrospective Bhavcopy cross-check after SE7.1 data available
  *(Prerequisite: Upstox confirms NiftyBees pledge does not conflict with simultaneous covered call margin — do not paper-trade until confirmed)*

## Phase SE5 — Backtester Implementations

- [ ] **SE5.1** — `src/backtest/points_bt.py`: `PointsBacktester` — converts `list[SwingSignal]` + Nifty daily OHLC into trade P&L records; daily mark-to-market equity curve; cost model (₹40 round-trip + 0.5pt slippage/side); writes to `BacktestStore`; tests
- [ ] **SE5.2** — `src/backtest/allocation_bt.py`: `AllocationBacktester` — converts `list[AllocationDecision]` + NiftyBees NAV + cash rate series into equity curve; buy-and-hold comparison; writes to `BacktestStore`; tests
- [ ] **SE5.3** — `src/strategy/execution.py`: `SpreadSelector` — `select_spread(signal, option_chain) → SpreadSpec`; `SpreadSpec` frozen dataclass; ATR-proportional width formula (`min(round_to_50(k × ATR_40d), 500)`, floor 150); tests

## Phase SE6 — Validation Pipeline

- [ ] **SE6.1** — `src/backtest/walkforward.py`: `WalkForwardEngine` — rolling window (configurable training/step), parameter sweep, per-window OOS Calmar aggregation; uses `PointsBacktester` or `AllocationBacktester` as pluggable runner; tests
- [ ] **SE6.2** — `src/backtest/montecarlo.py`: `MonteCarloSimulator` — 10,000-iteration trade-sequence bootstrap; returns `MCResult` with p50/p95/p99 drawdown percentiles; `numpy` vectorised; tests
- [ ] **SE6.3** — `src/backtest/sensitivity.py`: `SensitivityAnalyser` — local grid over ±2-step neighbourhood; `plateau_width` + `spike_detected` per parameter axis; 60%/80% plateau definition; tests
- [ ] **SE6.4** — `src/backtest/reports.py`: `SwingValidationReport` + `InvestmentValidationReport` dataclasses; `generate_swing_report(run_id) → SwingValidationReport`; `generate_investment_report(run_id) → InvestmentValidationReport`; regime decomposition table; failure condition checks; tests
- [ ] **SE6.5** — Portfolio construction analysis (conditional — swing only): combine ≥2 validated swing strategies with equal-risk ATR-normalised allocation; combined walk-forward median Calmar ≥ 1.0 gate; pairwise daily return correlation < 0.3 check; combined MC 95th pctile < individual worst-case; `scripts/portfolio_construction_report.py`; no unit tests (research script)
  *(Prerequisite: ≥2 of SE3.1–SE3.3 strategies pass all 6 failure conditions in SE6.1–SE6.4; if only 1 survives, skip this task)*

## Phase SE7 — Tier 2 (Conditional on SE5.1 Donchian Tier 1 pass)

- [ ] **SE7.1** — `src/backtest/spread_bt.py`: `SpreadBacktester` — Bhavcopy settle_price + BS IV reconstruction → per-leg mark-to-market; slippage model (2pt/leg); strike exclusion tracker; Tier 1 vs Tier 2 P&L gap report; tests
  *(Start only after SE5.1 Donchian passes Tier 1 and Bhavcopy exclusion rate < 20%)*

## SE8 — Docs Close

- [ ] **SE8** — `CONTEXT.md` module tree (add `src/strategy/`, `src/strategy/signals/`); `DECISIONS.md` entries; `TODOS.md` session log; `BACKTEST_PLAN_PHASE1.md` Phase 2 checkboxes (2.S0–2.S3b, 2.I0–2.I2); verify `docs/strategies/covered_call_overlay_v1.md` exists and broker compatibility status is recorded
