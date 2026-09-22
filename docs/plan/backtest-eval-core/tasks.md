# backtest-eval-core — Task Checklist

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation spec.

**Open: B1.1, B1.2, B2.1, B2.2, B2.3, B2.4, B2.5, B2.6, B2.7, B2.8, B2.9.**

**Prerequisite check before B1.1:** confirm tasks 1.3 (Bhavcopy ingest) and 1.4 (BacktestEngine) are committed. If not, stop — this plan cannot start until those are green.

## Phase 1.5 — BacktestStore (results persistence)

- [ ] **B1.1** — `src/backtest/store.py`: `BacktestStore` scaffold + `init_db` + `backtest_runs` CRUD + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **B1.2** — `src/backtest/store.py`: `backtest_daily_pnl` + `backtest_trades` + `backtest_metrics` tables + CRUD + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —

## Phase 1.5b — Analytics module (pure-function evaluation layer)

- [ ] **B2.1** — `src/analytics/` package setup: proper `__init__.py`, `CLAUDE.md`; relocate `test_analytics_apis.py` to `scripts/` | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer |
  SHA: —
- [ ] **B2.2** — `src/analytics/trade_metrics.py`: trade-level metrics + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **B2.3** — `src/analytics/ratios.py`: Sharpe / Sortino / Calmar / Ulcer / PSR / DSR + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **B2.4** — `src/analytics/drawdown.py`: drawdown series + max DD + duration distribution + CDaR + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **B2.5** — `src/analytics/sizing.py`: Kelly / fractional Kelly / Optimal f / risk-of-ruin / Monte Carlo DD + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **B2.6** — `src/analytics/spc.py`: rolling Z-score / CUSUM / runs test + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **B2.7** — `src/analytics/report.py`: `StrategyReport` + `generate_strategy_report` + `compare_reports` + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **B2.8** — Backtest integration: `BacktestStore.record_metrics_from_report` + `scripts/analyze_strategy.py` CLI + tests | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **B2.9** — Docs close: `CONTEXT.md`, `DECISIONS.md`, `TODOS.md`, `BACKTEST_PLAN_PHASE1.md` checkboxes 1.5 + 1.5b | Owner: Claude | Model: n/a | Review: none | SHA: —

## Story done when

- **B1.1** — `BacktestStore` exists with `init_db` and `backtest_runs` CRUD, covered by tests.
- **B1.2** — `backtest_daily_pnl`, `backtest_trades`, `backtest_metrics` tables have CRUD and tests.
- **B2.1** — `src/analytics/` is a proper package with a `CLAUDE.md`; the API-connectivity script lives in `scripts/`.
- **B2.2** — trade-level metrics (`total_pnl`, `win_rate`, `profit_factor`, `expectancy`, …) exist and are tested.
- **B2.3** — Sharpe / Sortino / Calmar / Ulcer / PSR / DSR ratios exist, with PSR/DSR pinned to the López de Prado Ch. 14 examples.
- **B2.4** — drawdown series, max drawdown, duration distribution, and CDaR exist and are tested.
- **B2.5** — Kelly, fractional Kelly, Optimal f, risk-of-ruin, and Monte Carlo drawdown probability exist, with Kelly pinned to Thorp's example.
- **B2.6** — rolling Z-score, CUSUM, and runs test exist and are tested.
- **B2.7** — `StrategyReport` and `compare_reports` compose all analytics submodules and are tested.
- **B2.8** — `BacktestStore.record_metrics_from_report` and `scripts/analyze_strategy.py` persist and print a full report.
- **B2.9** — `CONTEXT.md`, `DECISIONS.md`, `TODOS.md`, and `BACKTEST_PLAN_PHASE1.md` reflect the completed 1.5 + 1.5b work.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in `docs/plan/README.md` and add one line to `TODOS.md` Session Log. When the whole story is done,
follow §Conventions *Completion → archive*.
