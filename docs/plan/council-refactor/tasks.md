# council-refactor — Task Checklist

> Find the first unchecked item **assigned to you**. That is your only task for this session.
> Each task is tagged `[Claude]` or `[Antigravity]` — only pick up tasks tagged for you.
> If the next unchecked task is tagged for the other agent, stop and hand off.
> After completing: tick the box, append `| SHA: <sha>`, add one line to TODOS.md.
>
> **Story file to load based on task prefix:**
> | Task prefix | Story file |
> |---|---|
> | CR0 | `stories_infra.md` |
> | CR1a, CR1b, CR1c, CR1d | `stories_csp.md` |
> | CC-1, CC-2, CC-3, CC-4, CC-5 | `stories_cc.md` |
> | PP-1, PP-2, PP-3 | `stories_pp.md` |
> | COLLAR-1 | `stories_collar.md` |
| CR2, CR3 | `stories_overlay.md` |
> | CR4 | `stories_close.md` |
>
> Also load `README.md` for shared context (signal tables, state machine, dependency order).
> Do NOT load `stories.md` — it is a historical archive.

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

## Phase CC — CC Signal Alignment + Automation

- [ ] **CC-1** `[Antigravity]` — Align `evaluate_cc()` to CSP structure: add `days_held` param, `TIME_STOP` signal, replace `DTE_FORCED` with `DTE_REVIEW` WARN, use `_PROFIT_TARGET_RETENTION` constant, add `_CC_MIN_ENTRY_CREDIT`; update `CCOverlayV1` caller; tests
- [ ] **CC-2** `[Antigravity]` — `ReEntryMixin` in `src/strategy/reentry_mixin.py`: three-gate check (DTE ≥ 14, IVR ≥ 0.25, no open position); `reentry_leg_role` + `reentry_script_hint` class attrs; writes paper_exit_events; Telegram notification
- [ ] **CC-3** `[Claude]` — Migrate `CSPNiftyV1` to `ReEntryMixin`: inherit mixin, add class attrs, remove `_check_r5_reentry`, call `_check_reentry` on PROFIT_TARGET **and** TIME_STOP in `apply_action` (TIME_STOP was missing — regression fix)
- [ ] **CC-4** `[Antigravity]` — `CCOverlayV1` full automation: `auto_execute=True`, inherit `ReEntryMixin`, add `__init__` with store/notifier/vix_data_dir, handle `CLOSE_CC` in `apply_action`, `_send_close_notification` via `send_notification`; re-entry check on PROFIT_TARGET + TIME_STOP only
- [ ] **CC-5** `[Antigravity]` — `scripts/paper_cc_roll.py`: manual override exit handler with four triggers (loss_stop 2.5×, delta_stop 0.55, profit_target 30%, time_stop 21d) matching `evaluate_cc()` thresholds; dry-run mode; tests in `tests/unit/paper/test_cc_roll.py`

## Phase PP — PP Automation

- [ ] **PP-1** `[Antigravity]` — Update `evaluate_pp()`: remove bid/ask spread guard from CRASH_MONETIZE; promote DTE_REVIEW INFO → ROLL_ELIGIBLE ACTION; remove bid/ask params from signature; update PPOverlayV1 caller; tests
- [ ] **PP-2** `[Antigravity]` — `PPOverlayV1` full automation: `auto_execute=True`, inject store/broker/lookup/notifier, OPEN ↔ RE_ENTRY_PENDING state machine, three action types (MONETIZE_PP / ROLL_PP / OPEN_NEW_PP), IVR ≤ 0.60 re-entry gate, Telegram notifications; tests

## Phase COLLAR — Collar Automation

- [ ] **COLLAR-1** `[Antigravity]` — `CollarOverlayV1` full automation: `auto_execute=True`, inherit `ReEntryMixin`, add `__init__` with store/notifier/vix_data_dir, remove `evaluate_collar` from `exit_signals.py` (call `evaluate_cc` directly), handle `CLOSE_COLLAR` in `apply_action` (both legs via `OverlayCloser.close_collar`), `_send_close_notification` showing call + put; re-entry check on PROFIT_TARGET + TIME_STOP only

## Phase CR2 — Overlay Roll Signal

- [ ] **CR2** `[Antigravity]` — Add `evaluate_roll_overlay(leg_role, dte, base_dte, atm_strike)` to `ExitSignalEngine` returning `list[ExitSignalResult]`; no `RollSignalResult`; base-DTE guard → `ROLL_BASE_FIRST` WARN; tests extend `test_exit_signals.py`

## Phase CR3 — Wire Overlay Roll Into 3-Track Strategy

- [ ] **CR3** `[Claude]` — Wire `evaluate_roll_overlay` into `NiftyTrackComparisonV1.check_signals`; promote DTE ≤ 5 WARN to ACTION for `ROLL_ELIGIBLE`; keep `ROLL_BASE_FIRST` as WARN; tests

## Phase CR4 — Docs Close (MUST BE LAST)

- [ ] **CR4** `[Claude]` — `DECISIONS.md`, `CONTEXT.md`, `TODOS.md`; update `ExitSignalEngine` description; update `CSPNiftyV1`, `CCOverlayV1`, `PPOverlayV1`, and `NiftyTrackComparisonV1` descriptions
- [ ] **PP-3** `[Claude]` — `DECISIONS.md`, `CONTEXT.md`, `README.md`, `tasks.md`; document PP always-reprotect design, IVR re-entry gate, spread guard removal

---

## Implementation Order

| Priority | Task | Owner | Rationale |
|---|---|---|---|
| P0 | CR0 | Claude | ✅ Done — fixes live runtime TypeError |
| P1 | CR1a | Antigravity | `strike_selector.py` unblocks CR1b and PP-2 |
| P1 | CC-2 | Antigravity | `ReEntryMixin` — independent, run in parallel with CR1a |
| P2 | CR1b | Claude | DB migration + CSP signals; introduces `_PROFIT_TARGET_RETENTION` + `TradeState` |
| P3 | CC-1 | Antigravity | Align `evaluate_cc()` — needs `_PROFIT_TARGET_RETENTION` from CR1b |
| P3 | PP-1 | Antigravity | Update `evaluate_pp()` — needs CR1b for ExitSignalResult; run parallel with CC-1 |
| P3 | CC-3 | Claude | Migrate CSPNiftyV1 to mixin — needs CC-2; run parallel with CC-1, PP-1 |
| P4 | CR1c | Antigravity | CSPRollExecutor — needs CR1b; run parallel with CC-1, CC-3, PP-1 |
| P5 | CR1d | Claude | CSPNiftyV1 full automation — needs CR1c + CC-3 |
| P6 | CC-4 | Antigravity | CCOverlayV1 automation — needs CC-1 + CC-2 + CR1d |
| P6 | PP-2 | Antigravity | PPOverlayV1 automation — needs CR1a + CR1b + PP-1; parallel with CC-4 |
| P6 | COLLAR-1 | Antigravity | CollarOverlayV1 automation — needs CC-1 + CC-2 + CR1d; parallel with CC-4 and PP-2 |
| P6 | CC-5 | Antigravity | paper_cc_roll.py — needs CC-1 (aligned thresholds); parallel with CC-4 |
| P7 | CR2 | Antigravity | evaluate_roll_overlay — needs CR1b; can run after P4 |
| P8 | CR3 | Claude | Wire overlay roll — needs CR2 |
| P9 | CR4 + PP-3 | Claude | Always last — docs close for all automation stories |

---

## Definition of Done

All tasks above checked. Then verify:

```bash
python -m pytest tests/unit/ --tb=no -q          # all green
search_code("RapidCouncil")                       # zero results in monitor_daemon.py
search_graph("evaluate_profit_target_csp")        # exists in ExitSignalEngine
search_graph("evaluate_roll_overlay")             # exists in ExitSignalEngine
search_graph("close_csp_leg")                     # exists in csp_roll_executor
search_graph("filter_strikes_by_delta")           # exists in strike_selector
search_graph("ReEntryMixin")                      # exists in reentry_mixin
search_graph("CCOverlayV1.auto_execute")          # True
search_graph("PPOverlayV1.auto_execute")          # True
search_graph("_PROFIT_TARGET_RETENTION")          # single constant, used by CSP + CC
search_graph("_evaluate_pp_reentry")             # exists in PPOverlayV1
```

## Regression Gate

Must remain green after each commit:

```bash
python -m pytest tests/unit/strategy/ --tb=short -q
python -m pytest tests/unit/paper/ --tb=short -q
```

## Environment Variables

No new env vars. `MONITOR_OVERLAYS` behaviour unchanged.
