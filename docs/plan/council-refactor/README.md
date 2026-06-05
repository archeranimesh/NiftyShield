# council-refactor — Story Index

> Stories have been split by domain. Load only the file you need.
> `tasks.md` is the checklist — check it first to find your assigned task, then load the relevant story file.

| File | Covers | Stories |
|---|---|---|
| `stories_infra.md` | Approval flow bug fix | CR0 |
| `stories_csp.md` | CSP roll automation | CR1a, CR1b, CR1c, CR1d |
| `stories_cc.md` | CC signal alignment + automation + ReEntryMixin | CC-1, CC-2, CC-3, CC-4 |
| `stories_overlay.md` | 3-track overlay roll signal | CR2, CR3 |
| `stories_close.md` | Docs close (always last) | CR4 |

## Dependency Order

```
CR0 ✅
  └─► CR1a ──────────────────────────► CR1b ──► CC-1
                                          │         └─► CC-4 (needs CC-1 + CC-2 + CR1d)
  └─► CC-2 ──► CC-3 ──────────────────► CR1d
                          └─► CR1c ──► CR1d
                                          └─► CR2 ──► CR3
                                                         └─► CR4
```

Parallel lanes:
- `CC-2` (ReEntryMixin) is independent — can run any time before `CC-3`
- `CR1c` (CSPRollExecutor) can run in parallel with `CC-1`, `CC-2`, `CC-3`
- `CR2` (evaluate_roll_overlay) can run after `CR1b`, parallel to `CC-4`

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
| 3 | `PROFIT_TARGET` | mark ≤ 30% of entry, entry ≥ ₹15 | CLOSE_CC + re-entry check | ACTION |
| 4 | `TIME_STOP` | days_held ≥ 21 | CLOSE_CC + re-entry check | ACTION |
| 5 | `DELTA_WARN` | delta ≥ 0.45 | — | WARN |
| 6 | `DTE_REVIEW` | DTE ≤ 5 | — | WARN |
| — | `BELOW_FLOOR` | entry < ₹12 | — | INFO |

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

### ReEntryMixin Contract

Three gates — all must pass for ELIGIBLE:
1. DTE of closed contract ≥ 14
2. IVR ≥ 0.25
3. No open position for `reentry_leg_role`

Writes `R5_REENTRY_ELIGIBLE` or `R5_REENTRY_BLOCKED` to `paper_exit_events`.
Sends Telegram with `reentry_script_hint`.

Triggered by: `PROFIT_TARGET` and `TIME_STOP` exits only.
Not triggered by: `LOSS_STOP`, `DELTA_STOP` (market moved against you — reassess first).
