# Paper Exit Codification — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Council ruling q11: `docs/archive/council/strategy/2026-06-26_paper-trade-exit-philosophy.md` Stage 3.
> Council ruling q12: `docs/archive/council/data_architecture/2026-06-26_strategy-monitor-watchlist-design.md` Stage 3.

---

## EC-1 — TIME_STOP / DTE_REVIEW Priority Fix in `evaluate_cc`

**Context:** The q11 council confirmed that `exit_signals.py` already implements all canonical exit rules. The one open gap: in `evaluate_cc`, both `TIME_STOP` (days_held ≥ 21) and `DTE_REVIEW` (DTE ≤ 5) may fire simultaneously. The council ruling implies `DTE_REVIEW` should take precedence because it is a forward-looking structural signal, while `TIME_STOP` is a backstop discipline gate. If DTE ≤ 5 fires, emitting an additional `TIME_STOP` signal is redundant and may confuse downstream P&L attribution.

**Files to change:**
- `src/strategy/exit_signals.py` — update `evaluate_cc` priority check
- `tests/unit/strategy/test_exit_signals.py` — add / update tests

**Before any code:**
```
get_code_snippet("ExitSignalEngine.evaluate_cc")    # see exact current implementation
search_code("TIME_STOP")                             # all sites
search_code("DTE_REVIEW")                           # all sites
git log --oneline -10 src/strategy/exit_signals.py  # recent history
```

**What to verify first:** Read `evaluate_cc` and check:
- Does it already have an `if DTE_REVIEW: return early` before checking `TIME_STOP`?
- If yes: no code change needed — story is a verification + test coverage task only.
- If no: add early return: `if dte ≤ 5: emit DTE_REVIEW; return` before TIME_STOP check.

**Required evaluation order in `evaluate_cc` (canonical after this story):**
1. Profit target (PROFIT_TARGET) — check first; if fired, return
2. Delta stop (DELTA_STOP at δ ≥ 0.55) — check; if fired, return
3. Premium backstop (LOSS_STOP at LTP ≥ 2.5× entry) — check; if fired, return
4. DTE_REVIEW (DTE ≤ 5) — check; if fired, return (do NOT also fire TIME_STOP)
5. TIME_STOP (days_held ≥ 21 AND DTE > 5) — backstop only when DTE still has runway

**Tests:**
- `test_dte_review_supersedes_time_stop` — days_held=25, dte=4 → only DTE_REVIEW signal, not TIME_STOP
- `test_time_stop_fires_when_dte_above_threshold` — days_held=22, dte=10 → TIME_STOP fires (DTE_REVIEW suppressed)
- `test_neither_stop_when_fresh` — days_held=5, dte=15 → neither TIME_STOP nor DTE_REVIEW
- `test_profit_target_supersedes_dte_review` — profit target fires at dte=3 → only PROFIT_TARGET returned

**Commit:** `fix(strategy): evaluate_cc — DTE_REVIEW takes priority over TIME_STOP when DTE≤5`

---

## EC-2 — StrategyMonitor Observability Log Lines

**Context:** The q12 council confirmed no architecture change to `StrategyMonitor`. The only required change: add two structured log lines per tick to enable latency profiling and signal auditing. These are the Phase 1 trigger signals (>20 legs OR >1.5s/tick OR rate limits). Without these logs, the Phase 1 scaling trigger has no data.

**Files to change:**
- `src/paper/strategy_monitor.py` — add two `structlog` log calls
- `tests/unit/paper/test_strategy_monitor.py` — add / update tests

**Before any code:**
```
get_code_snippet("StrategyMonitor")              # class structure
get_code_snippet("StrategyMonitor._run_tick")    # or equivalent tick loop method
search_code("strategy_monitor")                  # existing log call sites
git log --oneline -10 src/paper/strategy_monitor.py
```

**Two log lines to add:**

**Log 1 — after chain fetch completes, before signal evaluation:**
```python
logger.info(
    "strategy_monitor.chain_fetch_complete",
    strategy_name=strategy.strategy_name,
    strike_count=len(chain.strikes),
    fetch_latency_ms=round((time.monotonic() - t0) * 1000),
)
```

**Log 2 — after all strategies evaluated per tick:**
```python
logger.info(
    "strategy_monitor.tick_summary",
    strategies_evaluated=len(strategies),
    signals_emitted=total_signals,
    tick_duration_ms=round((time.monotonic() - tick_start) * 1000),
)
```

Both use `structlog` (existing logger in the module — do not introduce new imports beyond what's already there). `t0` and `tick_start` are monotonic timestamps inserted just before the fetch and tick loop respectively.

**TODOS.md addition (do this in EC-2, not EC-3):**
Add one line to `TODOS.md` under a `## Backlog` section or equivalent:
```
- [PERF-1] StrategyMonitor Phase 1 scaling: trigger hybrid split-fetch (LTP per tick, Greeks periodic)
  when: legs > 20 OR tick_duration_ms > 1500 OR rate limit errors. Baseline data from
  strategy_monitor.tick_summary log (added 2026-06-26, EC-2).
```

**Tests:**
- `test_chain_fetch_complete_logged` — after a tick, `strategy_monitor.chain_fetch_complete` log event is captured with `strategy_name`, `strike_count`, `fetch_latency_ms`
- `test_tick_summary_logged` — after a tick, `strategy_monitor.tick_summary` log event is captured with `strategies_evaluated`, `signals_emitted`, `tick_duration_ms`
- `test_tick_summary_signal_count_matches` — emit 2 strategies, 3 signals total → `signals_emitted=3`

**Commit:** `feat(paper): StrategyMonitor — chain_fetch_complete + tick_summary observability logs`

---

## EC-3 — Docs Close

**Goal:** Confirm docs updated, add TODOS.md session log line. No code changes.

**Verify:**
- `DECISIONS.md` — already updated in session with q11 and q12 council rulings ✓
- `TODOS.md` — add one line confirming paper-exit-codification complete
- No new files in `src/` → no CONTEXT.md or CONTEXT_TREE.md changes needed

**Commit:** `docs: paper-exit-codification EC-1/EC-2 session close`
