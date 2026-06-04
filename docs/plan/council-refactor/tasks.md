# council-refactor — Task Checklist

> Find the first unchecked item **assigned to you**. That is your only task for this session.
> Each task is tagged `[Claude]` or `[Antigravity]` — only pick up tasks tagged for you.
> If the next unchecked task is tagged for the other agent, stop and hand off.
> After completing: tick the box, append `| SHA: <sha>`, add one line to TODOS.md.

**Prerequisite gate (run before CR0):**
- [x] `search_graph("ExitSignalEngine")` returns results (ES1 committed)
- [x] `search_graph("StrategyMonitor")` returns results (PB1.2 committed)
- [x] `search_code("send_approval_request")` in `monitor.py` — confirm mismatch

---

## Phase CR0 — Bug Fix: Approval Flow Signature

- [x] **CR0** `[Claude]` — Fix `send_approval_request` signature mismatch; remove `CouncilOutput` requirement from daemon approval path | SHA: 4ce6d99

## Phase CR1 — CSP Roll: Extract + Signal + Executor + Automation

- [ ] **CR1a** `[Antigravity]` — Extract `filter_strikes_by_delta`, `_apply_liquidity_gate`, `rank_strikes` from `find_strike_by_delta.py` → `src/instruments/strike_selector.py`; update imports in `find_strike_by_delta.py` and `paper_csp_roll.py`; tests in `test_strike_selector.py`
- [ ] **CR1b** `[Claude]` — `ExitSignalEngine.evaluate_roll_csp(dte)` returns `list[ExitSignalResult]`; `src/strategy/csp_roll_executor.py` (extract `close_csp_leg` + `open_new_csp_leg` from `paper_csp_roll.py`); store `self._broker = broker` in `CSPNiftyV1.__init__`; wire `CLOSE_AND_ROLL` into `check_signals` + `apply_action`; tests
- [ ] **CR1c** `[Antigravity]` — Refactor `paper_csp_roll.py` to thin CLI wrapper around `csp_roll_executor.py`; existing tests must stay green

## Phase CR2 — Overlay Roll Signal

- [ ] **CR2** `[Antigravity]` — Add `evaluate_roll_overlay(leg_role, dte, base_dte, atm_strike)` to `ExitSignalEngine` returning `list[ExitSignalResult]`; no `RollSignalResult`; base-DTE guard → `ROLL_BASE_FIRST` WARN; tests extend `test_exit_signals.py`

## Phase CR3 — Wire Overlay Roll Into 3-Track Strategy

- [ ] **CR3** `[Claude]` — Wire `evaluate_roll_overlay` into `NiftyTrackComparisonV1.check_signals`; promote DTE ≤ 5 WARN to ACTION for `ROLL_ELIGIBLE`; keep `ROLL_BASE_FIRST` as WARN; tests

## Phase CR4 — Docs Close (MUST BE LAST)

- [ ] **CR4** `[Claude]` — `DECISIONS.md`, `CONTEXT.md`, `TODOS.md`; update `ExitSignalEngine` description; update `CSPNiftyV1` and `NiftyTrackComparisonV1` descriptions

---

## Implementation Order

| Priority | Task | Owner | Rationale |
|---|---|---|---|
| P0 | CR0 | Claude | ✅ Done — fixes live runtime TypeError |
| P1 | CR1a | Antigravity | `strike_selector.py` unblocks CR1b |
| P2 | CR1b | Claude | Core roll signal + executor — needed before 2026-06-23 roll week |
| P3 | CR1c | Antigravity | Thin wrapper cleanup — can run in parallel with CR2 |
| P4 | CR2 | Antigravity | Overlay roll signal — same roll week deadline |
| P5 | CR3 | Claude | Wire overlay roll into 3-track — needs CR2 |
| P6 | CR4 | Claude | Always last |

---

## Definition of Done

All tasks above checked. Then verify:

```bash
python -m pytest tests/unit/ --tb=no -q          # all green
search_code("RapidCouncil")                       # zero results in monitor_daemon.py
search_graph("evaluate_roll_csp")                 # exists in ExitSignalEngine
search_graph("evaluate_roll_overlay")             # exists in ExitSignalEngine
search_graph("CSPRollExecutor")                   # not needed — functions, not class
search_graph("close_csp_leg")                     # exists in csp_roll_executor
search_graph("filter_strikes_by_delta")           # exists in strike_selector
```

## Regression Gate

Must remain green after each commit:

```bash
python -m pytest tests/unit/strategy/ --tb=short -q
python -m pytest tests/unit/paper/ --tb=short -q
```

## Environment Variables

No new env vars. `MONITOR_OVERLAYS` behaviour unchanged.
