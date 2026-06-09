# council-refactor — Story Index

> Stories have been split by domain. Load only the file you need.
> `tasks.md` is the checklist — check it first to find your assigned task, then load the relevant story file.

| File | Covers | Stories |
|---|---|---|
| `stories_infra.md` | Approval flow bug fix | CR0 |
| `stories_csp.md` | CSP roll automation | CR1a, CR1b, CR1c, CR1d |
| `stories_cc.md` | CC signal alignment + automation + ReEntryMixin + manual CLI | CC-1, CC-2, CC-3, CC-4, CC-5 |
| `stories_pp.md` | PP automation + RE_ENTRY_PENDING state machine | PP-1, PP-2, PP-3 |
| `stories_collar.md` | Collar overlay automation + leg role unification + dispatch fix | COLLAR-1 |
| `stories_daemon.md` | Overlay registration + dependency injection fix in daemon | DAEMON-FIX |
| `stories_auto.md` | EOD snapshot auto-execution for all overlays | AUTO-1 |
| `stories_overlay.md` | 3-track overlay roll signal + Proxy delta signals + Futures block | CR2, CR3, NT-1, NT-2 |
| `stories_close.md` | Docs close (always last) | CR4 |

## Dependency Order

```
CR0 ✅
  └─► CR1a ──────────────────────────► CR1b ──► CC-1 ──► CC-4 ──┐
                                          │                        │
                                          └─► PP-1 ──► PP-2 ───────┤ all needed for DAEMON-FIX
  └─► CC-2 ──► CC-3 ──────────────────► CR1d                      │
                          └─► CR1c ──► CR1d ──► COLLAR-1 ──────────┤
                                                                    │
                                                        DAEMON-FIX ─┤
                                                                    │
                                                            AUTO-1 ─┤
                                                                    │
                                                       CR4 + PP-3 ──┘ (always last)
  └─► CR2 ──► CR3 ──► NT-1 / NT-2 (parallel; feeds into CR4)
```

Sequential for automation: **COLLAR-1 → DAEMON-FIX → AUTO-1**

Parallel lanes:
- `CC-2` (ReEntryMixin) is independent — can run any time before `CC-3`
- `CR1c` (CSPRollExecutor) can run in parallel with `CC-1`, `CC-2`, `CC-3`, `PP-1`
- `PP-1` (evaluate_pp update) can run in parallel with `CC-1` after `CR1b`
- `PP-2` (PPOverlayV1 automation) runs parallel with `CC-4` — both need CR1a + CR1b
- `COLLAR-1` runs parallel with `CC-4` and `PP-2` — all three needed before `DAEMON-FIX`
- `CR2` (evaluate_roll_overlay) can run after `CR1b`, parallel to `CC-4` and `PP-2`

## Execution Path Gap (why AUTO-1 exists)

Two signal-detection paths that never share state:

| Path | When | Signal detection | Auto-execute? |
|---|---|---|---|
| `StrategyMonitor` daemon | 09:15–15:30 (live WebSocket ticks) | `strategy.check_signals()` per tick | Yes — if `auto_execute=True` |
| EOD snapshot cron | 15:35 (after daemon is dead) | `_dispatch_evaluate()` per position | **No** — writes event + plain Telegram only |

The daemon stops at 15:30. The EOD snapshot starts at 15:35. They never overlap.

**MONITOR_OVERLAYS=0 (current default):** CC, PP, Collar are never registered in the daemon at
all — signals are only detected and logged at EOD. No auto-execution happens. The "approval
request" Telegram message is dead code for overlays (no monitor_daemon to process it).

**After DAEMON-FIX (MONITOR_OVERLAYS=1):** Overlay strategies register in the daemon with
correct dependency injection. Intraday signals fire `apply_action` automatically.

**After AUTO-1:** EOD snapshot itself calls `OverlayCloser` immediately after recording an
ACTION event. Both paths (intraday daemon + EOD) now auto-execute. Zero manual intervention.

## Two-Phase Execution Design (resolved 2026-06-08)

Overlay auto-execution uses a **daemon-first, EOD-fallback** model:

| Phase | Path | When | Condition |
|---|---|---|---|
| Phase 1 | `StrategyMonitor` daemon (intraday) | Any tick 09:15–15:30 | `auto_execute=True` + signal fires during session |
| Phase 2 | EOD snapshot cron (15:35) | After market close | Signal not yet acted (event status ≠ `ACTED`) |

**How it works:**

- If the daemon catches the signal intraday (e.g. PROFIT_TARGET at 14:22), `apply_action` executes immediately. The exit event is written with status `ACTED`.
- At 15:35, the EOD snapshot checks each ACTION event. If status is already `ACTED`, skip. If `OPEN`, execute via `OverlayCloser` and mark `ACTED`.
- This means EOD is a safety net, not the primary path. Positions exit as soon as the condition is met, not 45 minutes later at 15:35.

**Implementation note for AUTO-1:** `compute_and_record_exit_signals` must check event status before calling `OverlayCloser`. The guard: `if event.status != "ACTED": _auto_close(...)`.

**Implementation note for DAEMON-FIX:** After DAEMON-FIX, `StrategyMonitor` processes overlays intraday. The daemon writes the event + calls `apply_action` in one path. No separate "acted" flag needed in the daemon — `apply_action` is the execution.

## Resolved Decisions

1. **Collar leg roles in DB:** `overlay_collar_call` / `overlay_collar_put` (verified 2026-06-08). No DB migration needed. COLLAR-1 Addition A is a source-only constants rename.

2. **Execution timing:** Daemon-first (intraday) with EOD fallback. Both paths active after DAEMON-FIX + AUTO-1.

## Shared Context

### Signal Priority (CSP, evaluated each EOD)

| Priority | Signal | Trigger | Action | Valid state |
|---|---|---|---|---|
| 1 | `HARD_STOP` | LTP ≥ 2× entry_credit | CLOSE_AND_WAIT | OPEN, DEFENDED |
| 2 | `DELTA_BREACH_FINAL` | \|delta\| ≥ 0.40, state=DEFENDED | CLOSE_AND_WAIT | DEFENDED |
| 3 | `DELTA_BREACH` | \|delta\| ≥ 0.40, state=OPEN | ROLL_DOWN_AND_OUT | OPEN |
| 4 | `PROFIT_TARGET` | LTP ≤ 30% of entry_credit | CLOSE_AND_ROLL | OPEN, DEFENDED |
| 5 | `TIME_STOP` | days_held ≥ 21 | CLOSE_AND_ROLL | OPEN, DEFENDED |
| 6 | `ROLL_ELIGIBLE` | DTE ≤ 7 | CLOSE_AND_ROLL | OPEN, DEFENDED |

### Signal Table (CC, evaluated each EOD)

| Priority | Signal | Trigger | Action | Severity |
|---|---|---|---|---|
| 1 | `LOSS_STOP` | mark ≥ 2.5× entry | CLOSE_CC | ACTION |
| 2 | `DELTA_STOP` | delta ≥ 0.55 | CLOSE_CC | ACTION |
| 3 | `PROFIT_TARGET` | mark ≤ 30% of entry (`_PROFIT_TARGET_RETENTION`), entry ≥ ₹15 (`_CC_MIN_ENTRY_CREDIT`) | CLOSE_CC + re-entry check | ACTION |
| 4 | `TIME_STOP` | days_held ≥ 21 | CLOSE_CC + re-entry check | ACTION |
| 5 | `DELTA_WARN` | delta ≥ 0.45 | — | WARN |
| 6 | `DTE_REVIEW` | DTE ≤ 5 | — | WARN |
| — | `BELOW_FLOOR` | entry < ₹12 | — | INFO |

> **Two distinct thresholds — do not conflate:**
> `BELOW_FLOOR` fires at entry < ₹12 (INFO only — position too cheap to actively manage).
> `PROFIT_TARGET` has a separate minimum floor at ₹15 (`_CC_MIN_ENTRY_CREDIT`): if entry < ₹15,
> PROFIT_TARGET never fires regardless of mark decay — ride to DTE_REVIEW instead.
> Both constants live in `exit_signals.py`; `_CC_MIN_ENTRY_CREDIT` is introduced in CC-1.

### CSP State Machine

```
OPEN ──── |delta| ≥ 0.40 (first breach) ──────► DEFENDED
  │                                                  │
  │  PROFIT_TARGET, TIME_STOP, ROLL_ELIGIBLE fire   │  |delta| ≥ 0.40 (second breach)
  │  → CLOSE_AND_ROLL                               │  OR HARD_STOP fires
  ▼                                                  │  → CLOSE_AND_WAIT
RE_ENTRY_PENDING ◄────────────────────────────────────┘
  │
  │  entry conditions met (IVR ≥ 0.25, delta ∈ [0.20, 0.28])
  ▼
OPEN
```

### Signal Table (PP, evaluated each EOD)

| Priority | Signal | Trigger | Action | Severity | Valid state |
|---|---|---|---|---|---|
| 1 | `CRASH_MONETIZE` | delta ≤ −0.80 OR value ≥ 5× entry debit (no spread guard) | MONETIZE_PP | ACTION | OPEN |
| 2 | `ROLL_ELIGIBLE` | DTE ≤ 5 | ROLL_PP | ACTION | OPEN |
| — | `PP_REENTRY_ELIGIBLE` | IVR ≤ 0.60 AND DTE ≥ 14 | OPEN_NEW_PP | ACTION | RE_ENTRY_PENDING |
| — | `PP_REENTRY_BLOCKED` | any re-entry gate fails | — | INFO | RE_ENTRY_PENDING |

When both CRASH_MONETIZE and ROLL_ELIGIBLE fire (crash at DTE ≤ 5), only CRASH_MONETIZE
is emitted — `check_signals` breaks after first result from `_sort_results` (list order
for equal-severity results preserves CRASH_MONETIZE first by insertion order).

### PP State Machine

```
OPEN ──── CRASH_MONETIZE ──────────────────────────────► RE_ENTRY_PENDING
  │                                                            │
  │  ROLL_ELIGIBLE (DTE ≤ 5)                                  │  IVR ≤ 0.60 AND DTE ≥ 14
  │  close current + open new PP (same delta 0.20–0.30)       │  AND no open position
  │  stays OPEN                                               │
  └────────────────────────────────────────────────────────► OPEN
```

No DEFENDED state — there is no defensive roll for a long put.
Re-entry IVR gate is inverted vs CSP: buy protection when IV is LOW (≤ 0.60),
not high. This prevents buying expensive protection immediately after a crash spike.
Fixed delta range 0.20–0.30 for PP re-entry/roll — coverage depth, not IV-driven.

### ReEntryMixin Contract

Three gates — all must pass for ELIGIBLE:
1. DTE of closed contract ≥ 14
2. IVR ≥ 0.25
3. No open position for `reentry_leg_role`

Writes `R5_REENTRY_ELIGIBLE` or `R5_REENTRY_BLOCKED` to `paper_exit_events`.
Sends Telegram with `reentry_script_hint`.

Triggered by: `PROFIT_TARGET` and `TIME_STOP` exits only.
Not triggered by: `LOSS_STOP`, `DELTA_STOP` (market moved against you — reassess first).
