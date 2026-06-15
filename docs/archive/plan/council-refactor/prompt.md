# council-refactor — Continuation Prompt

> **Status as of 2026-06-15.** Original design rationale archived at the bottom.
> Most of the story is shipped. This prompt covers only the remaining pending tasks.
>
> **How to find your next task:**
> Open `docs/plan/council-refactor/tasks.md` and find the **first unchecked `[ ]` item
> assigned to you** (`[Claude]` or `[Antigravity]`). That is the only task for this session.
> If the first unchecked item belongs to the other agent, stop and hand off.
> Complete in checklist order — do not skip ahead.

---

## What Is Already Shipped

| Task | SHA | Summary |
|---|---|---|
| CR0 | 4ce6d99 | Fix `send_approval_request` signature mismatch; remove CouncilOutput from approval path |
| CR1a | 0a6b3bd | Extract `strike_selector.py` from `find_strike_by_delta.py` |
| CR1b | 8fd58d4 | TradeState enum; 5 independent CSP classmethods; DTE≤7 roll eligible |
| CR1c | 154a64c | Refactor `paper_csp_roll.py` to thin CLI wrapper around `csp_roll_executor.py` |
| CR1d | e62aee9 | CSPNiftyV1 full automation: auto_execute, state machine, CLOSE_AND_ROLL |
| CC-1→CC-5 | various | CCOverlayV1 full automation; ReEntryMixin; paper_cc_roll.py |
| PP-1, PP-2 | various | PPOverlayV1 updates; always-reprotect design |
| COLLAR-1 | various | CollarOverlayV1 + Addition A+B |
| DAEMON-FIX, BF-1, DAEMON-S1 | various | Daemon crash guards; chain-leg fallback fix |
| P0/P1/P2 bug fixes | various | DBI-1→3, BUG-1/4, FR-1→10, SIG-1/2, SM-1/2, LOG-1 |
| RPT-1, RPT-2 | various | Track report; daily P&L delta mode |
| CR2 | 689662f + | `evaluate_roll_overlay()` added to ExitSignalEngine; base-DTE guard; tests |
| CR3 | 5ac623f | Wire `evaluate_roll_overlay` into `NiftyTrackComparisonV1`; DTE ≤ 5 → ACTION |

**Invariants established by shipped code — do not re-derive, just use:**
- `evaluate_roll_overlay(leg_role, dte, base_dte, atm_strike)` lives in `ExitSignalEngine`.
  Returns `list[ExitSignalResult]`. `ROLL_ELIGIBLE` ACTION at DTE ≤ 5 (when base_dte > 10);
  `ROLL_BASE_FIRST` WARN when base_dte ≤ 10. Raises `ValueError` for unknown leg roles.
- `NiftyTrackComparisonV1.check_signals`: DTE ≤ 5 → `evaluate_roll_overlay`; DTE 6–10 → `ROLL_DUE_DTE` WARN.
  `_get_base_dte(positions, strategy_name, today)` returns base leg DTE or 999 (ETF/no base).
- `csp_roll_executor.py` is in `src/strategy/`. `paper_csp_roll.py` is a thin wrapper.
- `strike_selector.py` is in `src/instruments/`. Used by executor and lookup scripts.
- `TelegramGateway.send_approval_request(event, context_str)` — no CouncilOutput anywhere.
- `NotifierProtocol` in `src/notifications/protocol.py` — `_notifier` typed against it in monitor.
- `RapidCouncil` in `src/council/rapid.py` — retained, not wired anywhere.

---

## Pending Tasks — Complete In This Order

> **Agent assignments:** `[Claude]` = you. `[Antigravity]` = other agent — do NOT implement,
> hand off when you reach one. Resume from the next `[Claude]` task after Antigravity returns.
>
> **Source of truth:** `docs/plan/council-refactor/tasks.md` — find the first unchecked `[ ]`
> item for your agent tag. The task specs below match that checklist order.

---

### NT-1 `[Antigravity]` — `evaluate_proxy_delta()` + consecutive-day state

> **Hand off to Antigravity.** Full spec in `stories_overlay.md` under NT-1.
> Resume from NT-2 after Antigravity returns the NT-1 SHA.

---

### NT-2 `[Claude]` — Futures + standalone CC block guard

**Files:** `src/strategy/nifty_track_comparison_v1.py`, `tests/unit/strategy/test_nifty_track_comparison_v1.py`

**Prerequisite:** CR3 committed. NT-1 committed (Antigravity).

**Prerequisite graph checks:**
```python
get_code_snippet("NiftyTrackComparisonV1.check_signals")  # post-CR3+NT-1 structure
search_graph("SHORT_CALL_ROLES")                           # existing short call role constants
search_code("paper_nifty_futures")                         # confirm strategy namespace string
```

**What to implement:**

Add module-level constant:
```python
_FUTURES_BLOCKED_ROLES: frozenset[str] = frozenset({
    "overlay_cc",
    "overlay_collar_call",  # blocked when no paired long put; collar with put IS allowed
})
```

Add private helper `_check_futures_cc_block(self, positions, strategy_name) -> list[SignalEvent]`:
1. If `strategy_name != "paper_nifty_futures"`: return `[]`
2. Find short call positions: `leg_role in _FUTURES_BLOCKED_ROLES`
3. If none: return `[]`
4. Check for paired long put: `any(p.leg_role in {"overlay_collar_put", "overlay_pp"} for p in positions)`
5. If short call exists AND no paired long put → emit `SignalEvent(severity="ERROR", event_type="BLOCKED_COMBINATION", payload={"message": "...", "violating_roles": [...], "action_required": "CLOSE_LEG"})`

Call `_check_futures_cc_block` at the top of `check_signals()` — prepend its events, then
continue with remaining signal evaluation (do not short-circuit on block).

**Tests:**
- Futures + `overlay_cc`, no long put → `BLOCKED_COMBINATION` ERROR
- Futures + `overlay_cc` + `overlay_collar_put` → no block (collar allowed)
- Futures + `overlay_collar_call` + `overlay_collar_put` → no block
- Futures + `overlay_collar_call`, no put (degenerate collar) → `BLOCKED_COMBINATION`
- Spot + `overlay_cc` → no block (Futures namespace only)
- Proxy + `overlay_cc` → no block
- Futures, no overlays → no block

**Commit:** `feat(strategy): NiftyTrackComparisonV1 — Futures+CC block guard with collar exemption`

---

### AUTO-1 `[Antigravity]` — EOD snapshot auto-close for all overlays

> **Hand off to Antigravity.** Full spec in `stories_auto.md`.
> Prerequisites: FR-1 + CC-4 + PP-2 + COLLAR-1 + DAEMON-FIX (all shipped).
> Resume from OPS-1 after Antigravity returns the AUTO-1 SHA.

---

### OPS-1 `[Claude]` — Insert/skip logging in `paper_3track_overlay_entry.py`

**Files:** `scripts/strategies/three_track/paper_3track_overlay_entry.py`

**Prerequisite graph checks:**
```python
search_code("record_trade", file_pattern="paper_3track_overlay_entry.py")  # find all call sites
```

`store.record_trade()` returns `bool` but the return value is currently discarded. After
each call, log at INFO:
- `True` → `"trade.INSERTED strategy=%s leg=%s"` (structlog key-value)
- `False` → `"trade.SKIPPED conflict on strategy/leg/date/action strategy=%s leg=%s"`

Use the module-level logger (already present). Do not change any logic — logging only.

**Tests:** mock `record_trade` returning `True` → assert INFO log contains `INSERTED`;
returning `False` → assert INFO log contains `SKIPPED`.

**Commit:** `feat(strategies): OPS-1 insert/skip logging in paper_3track_overlay_entry`

---

### OPS-2 `[Claude]` — Atomic collar open/close in `paper_3track_overlay_entry.py`

**Files:** `scripts/strategies/three_track/paper_3track_overlay_entry.py`

**Two sub-tasks:**

**(a) Open:** replace per-leg `store.record_trade()` loop for collar legs with a single
`store.record_trades([put_trade, call_trade])` call (already exists — atomic multi-insert).
If any leg conflicts, the whole collar open is rolled back. Currently the put can succeed
while the call silently conflicts, leaving a half-open collar.

**(b) Close:** validate that any script invocation targeting `overlay_collar_call` also
closes `overlay_collar_put` in the same transaction (and vice versa). Raise `SystemExit`
with an error message if only one collar leg is requested — partial collar close is not
permitted at the CLI level.

**Tests:**
- Open path: second leg raises `IntegrityError` → first leg rolled back; no record in DB
- Close path: requesting `overlay_collar_call` without `overlay_collar_put` → `SystemExit`
- Close path: requesting both → succeeds

**Commit:** `fix(strategies): OPS-2 atomic collar open/close in paper_3track_overlay_entry`

---

### RPT-3 `[Claude]` — Monthly mode in track snapshot

**Files:** `scripts/strategies/three_track/paper_3track_snapshot.py`, `src/paper/formatting.py`

**Prerequisite:** RPT-2 committed (✓). Verify `src/market_calendar/` holiday list is stable
before implementing (`search_code("is_trading_day", path_filter="market_calendar")`).

Remove the `--monthly` guard added in RPT-2 (`exits with error — RPT-3 not built yet`).
Resolve the reference date to the first NSE trading day of the current month via
`src/market_calendar/`. Fetch the nearest prior `paper_leg_snapshots` row. Compute
month-to-date delta using the same logic as daily mode (`get_prev_leg_snapshot`). Column
headers: `"MTD Base"` / `"MTD Overlay"`.

**Tests:**
- Monthly mode: reference date resolves to first trading day of month; delta computed vs that snapshot
- Non-trading-day first of month → advances to next trading day
- No prior snapshot for the month → renders `N/A` (not a crash)
- `-m` flag no longer exits with error

**Commit:** `feat(strategies): RPT-3 monthly mode in paper_3track_snapshot`

---

### CR4 `[Claude]` — Docs close (ALWAYS LAST)

**Files:** `DECISIONS.md`, `CONTEXT.md`, `TODOS.md`, `docs/plan/council-refactor/tasks.md`

**No code changes. Run only after all story SHAs are committed and tests are green.**

**Before writing:**
```bash
git log --oneline -20          # verify all story SHAs present
python -m pytest tests/unit/ --tb=no -q   # must be 0 failures
```

Full list of entries to add/update: see `stories_close.md` — it is the canonical spec for
this task. Do not summarise here to avoid drift.

**Commit:** `docs(council-refactor): close CR4 — DECISIONS, CONTEXT, TODOS updated`

---

### PP-3 `[Claude]` — PP docs close (can run in parallel with CR4)

**Files:** `DECISIONS.md`, `CONTEXT.md`, `docs/plan/council-refactor/README.md`, `docs/plan/council-refactor/tasks.md`

Document PP always-reprotect design, IVR re-entry gate, spread guard removal (introduced in PP-1/PP-2).
Full entry list: see `stories_pp.md`.

**Commit:** `docs(council-refactor): PP-3 — PP design decisions and CONTEXT update`

---

## Execution Order Summary

```
CR3  [Claude]      ← start here
  ↓
NT-1 [Antigravity] ← hand off; wait for SHA
  ↓
NT-2 [Claude]
  ↓
AUTO-1 [Antigravity] ← hand off; wait for SHA
  ↓
OPS-1 [Claude]     ← can run in parallel with OPS-2 and RPT-3
OPS-2 [Claude]
RPT-3 [Claude]
  ↓
CR4 + PP-3 [Claude]  ← always last; after all other SHAs confirmed
```

---

## Archived: Original Design Rationale

> The following sections explain WHY this story was structured as it is.
> They remain here for reference. Do not re-implement anything described here —
> it is all shipped. See the SHA table above.

### Why the Council Does Not Belong Here

**Paper trading exits are single-option decisions.** `ExitSignalEngine` already determines
whether to exit and why. Each strategy's `apply_action()` accepts a fixed set of action
types — `CLOSE_FULL` for CSP, `CLOSE_CC` for CC, `MONETIZE_PP` for PP. There is nothing
to deliberate: the action is determined before the council would be asked.

**Roll decisions must be backtestable.** A roll decision driven by `evaluate_roll_csp(dte)`
can be replayed deterministically. An LLM council call cannot — non-deterministic across runs,
model-version-dependent, leaks hindsight when replaying historical data.

**The council belongs in live trading for genuinely ambiguous decisions** — when real
capital is at stake, ≥ 2 defensible options exist, and the strategy spec does not resolve
the choice. None of these hold in Phase 0 paper trading.

### Where RapidCouncil Stays (Future)

`src/council/rapid.py` is retained but unwired. Future use: IC leg-selective exits in live
trading; roll parameter decisions if deterministic rules prove insufficient; novel signals
outside the codified rule set. Wiring criterion: action space ≥ 2 defensible options AND
real capital at stake AND strategy spec does not resolve the choice.

### Approval Flow (shipped)

```
Signal detected → ExitSignalEngine evaluates rules → Telegram message with action keyboard
         ↓
You tap approve → PaperExecutor dispatches action
```

No LLM call in any path. `valid_actions` list embedded in each strategy's signal payload
drives the keyboard. `CouncilOutput` not required anywhere.
