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

- [ ] **SE1.1** — Verify Nifty OHLC (daily+15min) coverage; confirm ATR/slope fields; integrity report | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **SE1.2** — `src/instruments/pe_loader.py`: NSE PE CSV → Parquet + gap fill + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **SE1.3** — Risk-free rate: AMFI NAV → Parquet; `get_risk_free_rate(date)` helper + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —

## Phase SE2 — Strategy Package + Regime Engine

- [ ] **SE2.1** — `src/strategy/` package setup: `__init__.py`, `CLAUDE.md`, `signals/__init__.py` stub | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **SE2.2** — `src/strategy/regime.py`: `RegimeTagger`/`RegimeTag`; `SignalEvalStore` init_db + regime CRUD; tests | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **SE2.3** — `scripts/regime_distribution_report.py`: tag history → 3x3 cell distribution; no tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —

## Phase SE3 — Swing Signal Generators

- [ ] **SE3.1** — `src/strategy/signals/donchian.py`: `DonchianConfig`/Generator + `SwingSignal` + store CRUD; tests | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **SE3.2** — `src/strategy/signals/orb.py`: `ORBConfig`/Generator + calendar exclusions + DTE expiry; tests | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **SE3.3** — `src/strategy/signals/gap_fade.py`: `GapFadeConfig`/Generator; VIX-IVP filter (63D, p75); tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —

## Phase SE4 — Investment Signal Generators

- [ ] **SE4.1** — `src/strategy/signals/sma_filter.py`: `SMAFilterConfig`/Generator + `AllocationDecision` + store CRUD; tests | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **SE4.2** — `src/strategy/signals/dual_mom.py`: `DualMomConfig`/Generator(monthly_df, rf_series); tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **SE4.3** — `src/strategy/signals/pe_band.py`: `PEBandConfig`/Generator(monthly_pe_df, quarterly_dates); tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **SE4.4** — Covered Call Overlay paper setup: `docs/strategies/covered_call_overlay_v1.md`; Upstox pledge check | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: — *(Prerequisite:
  Upstox confirms NiftyBees pledge does not conflict with simultaneous covered call margin — do not paper-trade until confirmed)*

## Phase SE5 — Backtester Implementations

- [ ] **SE5.1** — `src/backtest/points_bt.py`: `PointsBacktester` — signals+OHLC → P&L/equity curve; cost model; tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **SE5.2** — `src/backtest/allocation_bt.py`: `AllocationBacktester` — decisions+NAV+RF → equity; buy-hold; tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **SE5.3** — `src/strategy/execution.py`: `SpreadSelector.select_spread` + `SpreadSpec`; ATR width formula; tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —

## Phase SE6 — Validation Pipeline

- [ ] **SE6.1** — `src/backtest/walkforward.py`: `WalkForwardEngine` — rolling window sweep, OOS Calmar; tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **SE6.2** — `src/backtest/montecarlo.py`: `MonteCarloSimulator` — 10k-iter bootstrap; `MCResult` p50/95/99; tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **SE6.3** — `src/backtest/sensitivity.py`: `SensitivityAnalyser` — +-2-step grid; plateau/spike detect; tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **SE6.4** — `src/backtest/reports.py`: Swing/Investment validation reports; regime decomp; failure checks; tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **SE6.5** — Portfolio construction (conditional, swing only): ATR-normalised combo; Calmar/corr/MC gates; no tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
  *(Prerequisite: >=2 of SE3.1-SE3.3 strategies pass all 6 failure conditions in SE6.1-SE6.4; if only 1 survives, skip this task)*

## Phase SE7 — Tier 2 (Conditional on SE5.1 Donchian Tier 1 pass)

- [ ] **SE7.1** — `src/backtest/spread_bt.py`: `SpreadBacktester` — settle+BS IV, slippage, exclusion tracker; tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: — *(Start
  only after SE5.1 Donchian passes Tier 1 and Bhavcopy exclusion rate < 20%)*

## SE8 — Docs Close

- [ ] **SE8** — `CONTEXT.md`/`DECISIONS.md`/`TODOS.md`/`BACKTEST_PLAN_PHASE1.md` updates; verify covered call doc | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
