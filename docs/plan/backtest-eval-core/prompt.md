# backtest-eval-core — prompt

> Add `BacktestStore` results persistence and a pure-function `src/analytics/` evaluation layer (trade metrics, ratios, drawdown, sizing, SPC, composed `StrategyReport`).

Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read `docs/plan/backtest-eval-core/tasks.md` and find the first unchecked box — the first `- [ ]` line. That is your **only
task** for this session. Do not look at any other unchecked item. Do not attempt to batch or combine tasks. One task. Complete it fully. Move on to nothing else.

**Story spec:** Read the matching task in `docs/plan/backtest-eval-core/stories.md` (same task ID) for the full implementation spec, "Before any code" graph queries, test list, and commit message.
Follow it exactly.

## Why this story exists

Phase 1 backtesting (task 1.3 Bhavcopy ingest, task 1.4 `BacktestEngine`) produces trade and P&L data but nothing persists backtest runs for comparison, and nothing computes the risk-adjusted metrics
(Sharpe, Sortino, Kelly sizing, drawdown statistics) a strategy needs to be judged tradeable. This story adds that layer: `BacktestStore` (Phase 1.5) gives every backtest run a durable, queryable
record in the shared portfolio SQLite DB; `src/analytics/` (Phase 1.5b) is a pure-function evaluation library that computes the same metrics identically whether the input is live trades, paper trades,
or backtest trades — so a strategy's live performance can later be compared against its backtest with `compare_reports`.

## Scope guard

In scope: `src/backtest/store.py` (new `BacktestStore` class and dataclasses), the new `src/analytics/` package (`trade_metrics.py`, `ratios.py`, `drawdown.py`, `sizing.py`, `spc.py`, `report.py`),
`scripts/analyze_strategy.py`, and the doc updates in B2.9.

Out of scope: this story does not touch `BacktestEngine` itself, the Bhavcopy ingest path, strategy execution logic, or the live/paper trade recording paths — `src/analytics/` functions are pure and
take trade-like records as input, never touching the DB. No changes to `src/paper/` or `src/risk/`.

## Session-start load hints

- `BACKTEST_PLAN_PHASE1.md` — tasks 1.5 and 1.5b live here; this story's `tasks.md` / `stories.md` are a working index, not a replacement.
- `docs/plan/backtest-eval-core/schema.md` — read before any `BacktestStore` work (B1.1, B1.2, B2.8); it is the canonical DDL for all four `backtest_*` tables.
- `LITERATURE.md` — LIT-02 through LIT-09, cited per-function across the analytics tasks (B2.2–B2.6); read the relevant entry before implementing a metric.
- `src/db.py` — shared `db_connection` context manager used by `BacktestStore`.

## Task overview

- **B1.1** — `BacktestStore` scaffold, `init_db`, `backtest_runs` CRUD.
- **B1.2** — `backtest_daily_pnl`, `backtest_trades`, `backtest_metrics` CRUD.
- **B2.1** — `src/analytics/` package scaffold; relocate `test_analytics_apis.py`.
- **B2.2** — trade-level metrics (`total_pnl`, `win_rate`, `profit_factor`, …).
- **B2.3** — risk-adjusted ratios (Sharpe / Sortino / Calmar / Ulcer / PSR / DSR).
- **B2.4** — drawdown series, max drawdown, duration distribution, CDaR.
- **B2.5** — position sizing (Kelly / Optimal f / risk-of-ruin / Monte Carlo DD).
- **B2.6** — statistical process control (rolling Z-score / CUSUM / runs test).
- **B2.7** — `StrategyReport` composition + `compare_reports`.
- **B2.8** — backtest integration (`record_metrics_from_report`) + `analyze_strategy` CLI.
- **B2.9** — docs close (`CONTEXT.md`, `DECISIONS.md`, `TODOS.md`, `BACKTEST_PLAN_PHASE1.md`).

## Definition of done

All four `backtest_*` tables exist with CRUD and tests; every `src/analytics/` submodule is implemented, pure (no I/O), Decimal-in/Decimal-out, and tested, with PSR/DSR pinned to López de Prado's Ch.
14 examples and Kelly pinned to Thorp's biased-coin example; `StrategyReport` composes all submodules and `compare_reports` diffs two reports; `scripts/analyze_strategy.py` runs for `--backtest-run`,
`--live`, and `--paper` modes; `CONTEXT.md`, `DECISIONS.md`, `TODOS.md`, and `BACKTEST_PLAN_PHASE1.md` reflect the completed work. Full per-task criteria: `tasks.md` §Story done when.

## Perspectives not covered

This story treats `src/analytics/` metric formulas as settled (cited to `LITERATURE.md` LIT codes) — it does not include a quant/statistics review of whether these are the *right* metrics for a
delta-neutral options strategy, or whether the PSR/DSR multiple-testing correction is appropriately conservative for this strategy's actual trial count.

**Pre-implementation gate:** State in one sentence: which task you are implementing (ID + one-line description), which files will change, and which test file covers it. Do not write any code until
this plan is stated.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first trying the graph. Order: `git log --oneline -10 <file>` for intent → `search_graph` / `get_code_snippet` for symbols
→ `trace_path` for callers → `search_code` for grep → `bash sed -n 'N,Mp' <file>` for a specific block → `Read` only if all of the above are insufficient, and state why.

**Before writing any test helper that constructs a domain model:** run `get_code_snippet('<ModelClassName>')` to get the exact current field list. Never write model constructors from memory.

**Implementation:** Follow all rules in `CLAUDE.md` and `REVIEW.md`. Every public function needs one happy-path test and one edge/error test. No network calls in tests. Monetary fields are always
`Decimal`, stored as TEXT in SQLite — never float.

**Antigravity routing (Step 3b gate):** After stating the plan, check: does this task span 3+ files with a clear non-ambiguous spec? If yes → invoke the `handoff-antigravity` skill and produce the
structured handoff prompt. Stop — do not write any code. If no (single or 2-file task, exploratory, or inline judgment required) → proceed to implement directly.

**Test gate — blocking:** After implementation, before touching anything else, run: `python -m pytest tests/unit/ --tb=no -q` All tests must be green. If any fail, fix them before proceeding. Do not
skip this step.

**Code-reviewer gate — blocking (before every commit):** Run the `code-reviewer` agent against `git diff HEAD`. Address any `CRITICAL` or `ERROR` findings before committing. `WARNING` may be deferred
with a documented reason in the commit message.

**Commit:** Use the commit format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it and hand it to the user to run. The commit must land:
```
git add <files>
git commit -m '<message>'
git log --oneline -1
```

**Verify and record:** Copy the SHA from `git log --oneline -1`. Open `docs/plan/backtest-eval-core/tasks.md`, change `- [ ]` to `- [x]` on the completed line, and append `| SHA: <sha>`. Then add one
line to `TODOS.md` under the session log: `| <YYYY-MM-DD> | backtest-eval-core <task-id> — <one-line description> — <SHA> |`

**Stop.** You are done. Do not proceed to the next unchecked item. The next session will pick up from the next unchecked box.
