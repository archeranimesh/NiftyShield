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

## EC-4 — TIME_STOP Must Gate on DTE-Remaining, Not Days-Held

**Context:** Spawned from TODOS.md (detected 2026-06-30, event 68 fired TIME_STOP on
`paper_nifty_spot / overlay_collar_call`, NSE_FO|65900, September 24000 CE, DTE=91 remaining —
auto-close correctly failed since the chain was absent, but the signal itself was wrong). This
is a distinct bug from EC-1's priority-ordering fix — EC-1 makes DTE_REVIEW suppress a
simultaneously-firing TIME_STOP; EC-4 fixes TIME_STOP's own trigger condition, which is
independently wrong for any quarterly/leaps/yearly entry. `evaluate_cc`, `evaluate_time_stop_csp`,
and any other exit-signal evaluator using `days_held >= N` treat holding period as the exit
trigger — but the intent of TIME_STOP is to exit *before expiry*, not to impose a flat
holding-period limit. A 113-DTE collar call held for 21 days still has 91 DTE left and should
not be closed just because 21 days elapsed.

**Correct semantic:** close when DTE drops below a per-strategy/per-expiry-type floor (e.g. ≤7
for weekly CC, ≤14 for monthly CSP, ≤21 for quarterly collar) — the threshold is a function of
entry DTE or expiry type, not a wall-clock counter.

**Cross-reference (2026-07-28, found while working `docs/plan/3track-consolidation`'s CC
delta-selector sub-thread):** check the chosen floor against `evaluate_cc`'s existing
`DTE_REVIEW` WARN threshold (currently `dte <= 5`) before picking final numbers. The
example monthly floor above (≤14) sits *above* `DTE_REVIEW`'s 5 — if TIME_STOP fires at
14 DTE, `DTE_REVIEW`'s dte≤5 WARN never gets a chance to matter for CC monthly, since
TIME_STOP would always force-close first. Confirm whether that's intended (TIME_STOP
fully subsumes DTE_REVIEW for CC) or whether the floors need reordering so both signals
retain independent meaning. `docs/plan/3track-consolidation/stories.md` CC1/CC2/CC3 are
blocked on this story landing — don't finalize floor values without checking that folder
isn't relying on assumptions this story is about to change.

**Files to change:**
- `src/strategy/exit_signals.py` — `evaluate_time_stop_csp`, `evaluate_cc` (and any other
  evaluator taking `days_held`)
- `tests/unit/strategy/test_exit_signals.py` — add/update tests

**Before any code:**
```
get_code_snippet("ExitSignalEngine.evaluate_time_stop_csp")
get_code_snippet("ExitSignalEngine.evaluate_cc")
search_code("days_held")             # every call site — all must be migrated together
git log --oneline -10 src/strategy/exit_signals.py
```

**Land after EC-1** — EC-1's priority ordering assumes `TIME_STOP`'s trigger condition already
exists; changing the condition itself first would make EC-1's test fixtures (`days_held=22,
dte=10 → TIME_STOP fires`) need rework mid-story. Confirm EC-1 is checked off in `tasks.md`
before starting this one.

**Tests:**
- `test_time_stop_quarterly_not_triggered_by_days_held_alone` — quarterly entry, days_held=21,
  dte_remaining=91 → no TIME_STOP (regression test for the reported event 68 case)
- `test_time_stop_fires_when_dte_floor_breached` — dte_remaining ≤ per-expiry-type floor → fires
- `test_time_stop_floor_is_expiry_type_aware` — weekly floor (7) vs monthly floor (14) vs
  quarterly floor (21) each produce correct fire/no-fire at the boundary

**Commit:** `fix(strategy): TIME_STOP gates on DTE-remaining, not days-held`

---

## EC-3 — Docs Close

**Goal:** Confirm docs updated, add TODOS.md session log line. No code changes.

**Verify:**
- `DECISIONS.md` — already updated in session with q11 and q12 council rulings ✓ (add an entry
  for EC-4's fix once it lands)
- `TODOS.md` — add one line confirming paper-exit-codification complete (EC-1, EC-2, EC-4)
- No new files in `src/` → no CONTEXT.md or CONTEXT_TREE.md changes needed

**Commit:** `docs: paper-exit-codification EC-1/EC-2/EC-4 session close`

**Run this last** — after EC-1, EC-2, and EC-4 are all checked off in `tasks.md`.
