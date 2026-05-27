# 1.5b — Evaluation & analytics module (`src/analytics/`)

**Status:** NOT STARTED
**Owner:** Cowork
**Phase:** 1
**Blocks:** 1.11 (variance check uses `compare_reports`), 2.1 (continuous re-validation loop uses `rolling_zscore`), all downstream strategy evaluation
**Blocked by:** 1.5 (`backtest_runs` tables needed for metrics storage integration)
**Estimated effort:** XL (1-2 weeks)
**Literature:** LIT-02, LIT-03, LIT-04, LIT-05, LIT-06, LIT-07, LIT-08, LIT-09

## Problem statement

Every strategy-evaluation decision from Phase 1 onward depends on a consistent set of metrics. Without a central analytics layer, each phase reimplements ratios, each backtest run computes Sharpe differently, and comparisons across strategies or between backtest and live become impossible.

This module is the "build once, use forever" evaluation substrate. It operates identically on live trades (`trades` table), paper trades (`paper_trades` table), and backtest trades (`backtest_trades` table) because it takes trade-like records as pure function input with no I/O concerns.

The scope is deliberately wide because the cost of omitting a metric now is that it silently never gets implemented — most retail traders who skip probabilistic Sharpe never come back to add it. By packaging the full suite in one module, every future strategy gets proper evaluation for free.

## Acceptance criteria

### Structural

- [ ] `src/analytics/` package with `__init__.py` and `CLAUDE.md` (module invariants: pure functions, Decimal-in/Decimal-out, accepts list of Trade-like records, never touches DB directly, citations to `LITERATURE.md` in every public function's docstring).
- [ ] Five submodules: `trade_metrics.py`, `ratios.py`, `drawdown.py`, `sizing.py`, `spc.py`.
- [ ] Reporting module `report.py` that composes the above into a single `StrategyReport` dataclass.
- [ ] Integration with `src/backtest/store.py`: after every backtest run, `backtest_metrics` table automatically populated from `StrategyReport`.
- [ ] CLI `scripts/analyze_strategy.py` with mutually-exclusive modes `--backtest-run <id>`, `--live --strategy <name>`, `--paper --strategy <name>`. Prints full report.

### Functional (per submodule)

**`trade_metrics.py`**
- [ ] `profit_factor(trades)` — gross wins / gross losses as Decimal. Edge case: zero losses → `Decimal('Infinity')` (not error, not None). Test: 3 wins of 100 + 2 losses of 50 → 3.0 exactly.
- [ ] `expectancy(trades)` — `(win% * avg_win) - (loss% * avg_loss)`. Rupee value.
- [ ] `win_rate`, `avg_win`, `avg_loss`, `max_win`, `max_loss`, `total_pnl` — basics.
- [ ] `trade_duration_stats(trades)` — returns dict with `{"winners": {"mean": ..., "median": ..., "p25": ..., "p75": ...}, "losers": {...}}`. Answers "are we holding winners longer than losers?"
- [ ] `r_multiple_distribution(trades)` — uses `trade.intended_risk` if present. Returns `{"bin_edges": [...], "counts": [...], "mean": ..., "std": ..., "pct_above_1r": ..., "pct_below_neg_1r": ...}`. LIT-09.

**`ratios.py`** (citations per LIT-04 through LIT-08)
- [ ] `sharpe_ratio(returns, risk_free_rate, periods_per_year)` — LIT-04. Annualised. Decimal.
- [ ] `sortino_ratio(returns, target_return, periods_per_year)` — LIT-05. Downside-deviation denominator.
- [ ] `calmar_ratio(returns, periods_per_year)` — LIT-06. Returns `None` if no drawdown observed.
- [ ] `ulcer_index(returns)` — LIT-06.
- [ ] `probabilistic_sharpe_ratio(returns, benchmark_sharpe, periods_per_year)` — LIT-07. Returns probability in [0, 1].
- [ ] `deflated_sharpe_ratio(returns, num_trials, periods_per_year)` — LIT-08. Multiple-testing correction.

**`drawdown.py`**
- [ ] `drawdown_series(equity_curve)` — running drawdown at each point.
- [ ] `max_drawdown(equity_curve)` — `(max_dd_pct, peak_date, trough_date, recovery_date_or_None)`.
- [ ] `drawdown_duration_distribution(equity_curve)` — stats on drawdown durations.
- [ ] `conditional_drawdown_at_risk(equity_curve, confidence=0.95)` — expected DD in worst `1-confidence` fraction of periods.

**`sizing.py`** (LIT-02, LIT-03)
- [ ] `kelly_fraction(win_rate, win_loss_ratio)` — classical. LIT-02.
- [ ] `fractional_kelly(win_rate, win_loss_ratio, fraction=Decimal('0.25'))` — practitioner-standard.
- [ ] `optimal_f(trades)` — LIT-03. Numerical search over f ∈ [0.01, 0.99].
- [ ] `risk_of_ruin(win_rate, win_loss_ratio, fraction_risked_per_trade, ruin_threshold=Decimal('0.3'))` — LIT-03. Probability of losing `ruin_threshold` fraction of capital.
- [ ] `probability_of_drawdown(returns, threshold_pct, num_periods, seed=42)` — Monte Carlo. Documented seed for reproducibility.

**`spc.py`** (statistical process control)
- [ ] `rolling_zscore(realized_returns, backtest_mean, backtest_std, window=3)` — drift detection.
- [ ] `cusum(realized_returns, expected_mean)` — cumulative sum of deviations.
- [ ] `runs_test(win_loss_sequence)` — Wald-Wolfowitz. Returns `(z_statistic, p_value)`.

**`report.py`**
- [ ] `StrategyReport` frozen dataclass with fields for every metric above plus narrative markdown string.
- [ ] `generate_strategy_report(trades, returns, config)` — produces a `StrategyReport`.
- [ ] `compare_reports(report_a, report_b)` — side-by-side diff for backtest-vs-paper variance checks. Returns a `ComparisonReport` dataclass.
- [ ] Markdown rendering: `StrategyReport.to_markdown()` produces a shareable report.

### Test coverage

- [ ] Minimum 100 new tests across all submodules.
- [ ] Every metric has: happy-path test, edge case (empty input, zero losses, flat returns), boundary (minimum sample size).
- [ ] Pinned known-values for LIT-07 (PSR) and LIT-08 (DSR) from López de Prado's published examples in *Advances in Financial Machine Learning*. These are non-negotiable — if the formula is implemented incorrectly, the DSR specifically will silently give wrong answers.
- [ ] Pinned known-values for Kelly and Optimal f from Thorp / Vince examples.

## Definition of Done

- [ ] `python -m pytest tests/unit/analytics/` green (all new tests)
- [ ] `python -m pytest tests/unit/` full suite green
- [ ] `code-reviewer` agent clean on each commit (7 commits — one per submodule + integration)
- [ ] `src/analytics/CLAUDE.md` documents invariants and cites `LITERATURE.md` as the source-of-record for metric definitions
- [ ] `CONTEXT.md` "What Exists" tree updated with new module
- [ ] `DECISIONS.md` updated with "Analytics module: pure-function layer operating on trade-record input" entry
- [ ] `LITERATURE.md` — verify each cited LIT entry is linked from the relevant function docstring
- [ ] `TODOS.md` session log entry added
- [ ] `BACKTEST_PLAN.md` task 1.5b checkbox ticked
- [ ] Commit sequence: 7 commits as outlined in "Commit sequence" below

## Technical notes

**Commit sequence** (enforce one commit per submodule for easier review):

1. `feat(analytics): trade-level metrics`
2. `feat(analytics): strategy-level ratios (Sharpe/Sortino/Calmar/Ulcer/PSR/DSR)`
3. `feat(analytics): drawdown analytics`
4. `feat(analytics): position sizing (Kelly/OptimalF/risk-of-ruin)`
5. `feat(analytics): statistical process control (Z-score/CUSUM/runs-test)`
6. `feat(analytics): strategy report composition`
7. `feat(analytics): backtest integration + analyze_strategy CLI`

**Decimal arithmetic invariant:** Every monetary quantity in and out is `Decimal`. Never cast to float inside the module. Use `Decimal` context with `ROUND_HALF_UP` where quantization is needed.

**Numpy/scipy usage:** Acceptable for vectorised operations on return series and the normal CDF in PSR/DSR. But Decimal → float → Decimal at the boundary must be documented. For simple statistics (mean, std on small lists of Decimals), use pure Python — avoids the boundary entirely.

**Pinned test values for PSR/DSR:** López de Prado publishes numerical examples in Chapter 14 of *Advances in Financial Machine Learning*. Replicate at least 3 examples per function as pinned tests. If the published values cannot be replicated to within 1e-4, the formula is implemented incorrectly.

**Pinned test values for Kelly:** Thorp's Kelly example with a biased coin (60% win, even money payoff) gives `f* = 0.20`. Use this as a pinned test.

**Pinned test values for Optimal f:** Vince's examples in *The Mathematics of Money Management* Chapter 1 have specific trade sequences with known Optimal f. Use those.

**`compare_reports(a, b)` output shape:** returns a `ComparisonReport` with fields for each metric showing `(a_value, b_value, delta, delta_pct)`. Used by Phase 1.11 variance check to detect which specific metrics have diverged between backtest and paper.

## Non-goals

- Does NOT include ML (meta-labeling, purged CV). That's Phase 4.3.
- Does NOT visualise — matplotlib/React dashboard is separate.
- Does NOT include behavioral metrics (adherence rate, override outcome). Those come later (LIT-25) after 30+ live trades exist.
- Does NOT change any existing code outside `src/analytics/` and `src/backtest/store.py` integration point.

## Follow-up work

- Phase 1.11 variance check uses `compare_reports`.
- Phase 2.1 continuous re-validation loop uses `rolling_zscore`.
- Phase 3.5b regime conditioning experiment uses `deflated_sharpe_ratio` for evaluation.
- Future: behavioral metrics addition (LIT-25) as new submodule `src/analytics/process.py` after live trading data accumulates.

---

## Session log

_(append-only, dated entries)_
