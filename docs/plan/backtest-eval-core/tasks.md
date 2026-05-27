# backtest-eval-core — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md` session log.
> Full story spec for each task: `docs/plan/backtest-eval-core/stories.md`.
>
> **Prerequisite check before B1.1:** Confirm tasks 1.3 (Bhavcopy ingest) and 1.4 (BacktestEngine)
> are committed. If not, stop — this plan cannot start until those are green.

---

## Phase 1.5 — BacktestStore (results persistence)

- [ ] **B1.1** — `src/backtest/store.py`: `BacktestStore` scaffold + `init_db` + `backtest_runs` CRUD + tests
- [ ] **B1.2** — `src/backtest/store.py`: `backtest_daily_pnl` + `backtest_trades` + `backtest_metrics` tables + CRUD + tests

## Phase 1.5b — Analytics module (pure-function evaluation layer)

- [ ] **B2.1** — `src/analytics/` package setup: proper `__init__.py`, `CLAUDE.md`; relocate `test_analytics_apis.py` to `scripts/`
- [ ] **B2.2** — `src/analytics/trade_metrics.py`: trade-level metrics + tests
- [ ] **B2.3** — `src/analytics/ratios.py`: Sharpe / Sortino / Calmar / Ulcer / PSR / DSR + tests
- [ ] **B2.4** — `src/analytics/drawdown.py`: drawdown series + max DD + duration distribution + CDaR + tests
- [ ] **B2.5** — `src/analytics/sizing.py`: Kelly / fractional Kelly / Optimal f / risk-of-ruin / Monte Carlo DD + tests
- [ ] **B2.6** — `src/analytics/spc.py`: rolling Z-score / CUSUM / runs test + tests
- [ ] **B2.7** — `src/analytics/report.py`: `StrategyReport` + `generate_strategy_report` + `compare_reports` + tests
- [ ] **B2.8** — Backtest integration: `BacktestStore.record_metrics_from_report` + `scripts/analyze_strategy.py` CLI + tests
- [ ] **B2.9** — Docs close: `CONTEXT.md`, `DECISIONS.md`, `TODOS.md`, `BACKTEST_PLAN_PHASE1.md` checkboxes 1.5 + 1.5b
