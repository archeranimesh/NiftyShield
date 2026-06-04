# council-refactor — Task Checklist

> Find the first unchecked item **assigned to you**. That is your only task for this session.
> Each task is tagged `[Claude]` or `[Antigravity]` — only pick up tasks tagged for you.
> If the next unchecked task is tagged for the other agent, stop and hand off.
> After completing: tick the box, append `| SHA: <sha>`, add one line to TODOS.md.

**Prerequisite gate (run before CR0):**
- [ ] `search_graph("ExitSignalEngine")` returns results (ES1 committed)
- [ ] `search_graph("StrategyMonitor")` returns results (PB1.2 committed)
- [ ] `search_code("send_approval_request")` in `monitor.py` — confirm mismatch

---

## Phase CR0 — Bug Fix: Approval Flow Signature

- [ ] **CR0** `[Claude]` — Fix `send_approval_request` signature mismatch; remove `CouncilOutput` requirement from daemon approval path

## Phase CR1 — Deterministic CSP Roll Rules

- [ ] **CR1** `[Claude]` — Add `evaluate_roll_csp()` to `ExitSignalEngine` + `RollSignalResult` model + tests

## Phase CR2 — Deterministic Overlay Roll Rules

- [ ] **CR2** `[Antigravity]` — Add `evaluate_roll_overlay()` to `ExitSignalEngine` + tests

## Phase CR3 — Wire Roll Signals Into Strategies

- [ ] **CR3** `[Claude]` — Wire `ROLL_ELIGIBLE` into `CSPNiftyV1` + promote `ROLL_DUE_DTE` to ACTION at DTE ≤ 5 in `NiftyTrackComparisonV1` + update tests

## Phase CR4 — Docs Close (MUST BE LAST)

- [ ] **CR4** `[Claude]` — `DECISIONS.md`, `CONTEXT.md`, `TODOS.md`; update `DECISIONS.md` entry on paper-backbone council wiring

---

## Implementation Order

| Priority | Task | Rationale |
|---|---|---|
| P0 | CR0 | Fixes live runtime bug — unblocks any daemon run |
| P1 | CR1 | CSP roll rules — needed before next CSP cycle roll (2026-06-23) |
| P2 | CR2 | Overlay roll rules — same roll week deadline |
| P3 | CR3 | Wire signals into strategies — needs CR1 + CR2 |
| P4 | CR4 | Always last |

---

## Definition of Done

All tasks above checked. Then verify:

```bash
python -m pytest tests/unit/ --tb=no -q     # all green
search_code("RapidCouncil")                 # zero results in monitor_daemon.py
search_graph("evaluate_roll_csp")           # exists in ExitSignalEngine
search_graph("evaluate_roll_overlay")       # exists in ExitSignalEngine
```

## Regression Gate

Must remain green after each commit:

```bash
python -m pytest tests/unit/strategy/ --tb=short -q
python -m pytest tests/unit/paper/ --tb=short -q
```

## Environment Variables

No new env vars. `MONITOR_OVERLAYS` behaviour unchanged.
