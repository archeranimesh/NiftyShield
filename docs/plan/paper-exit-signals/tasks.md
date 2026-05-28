# paper-exit-signals — Task Checklist

> Find the first unchecked item. That is your only task for this session.
> After completing: tick the box, append `| SHA: <sha>`, add one line to TODOS.md.

**Prerequisite gate (check before ES0):**
- [ ] `search_graph("StrategyMonitor")` returns results (PB1.2 committed)
- [ ] `search_graph("PaperExecutor")` returns results (PB1.3 committed)
- [ ] `search_graph("CCOverlayV1")` returns zero results (not yet built)

---

## Phase ES0 — Schema

- [ ] ES0 — `paper_exit_events` table + PaperStore methods + tests | SHA: ___

## Phase ES1 — Rule Engine

- [ ] ES1 — `ExitSignalEngine` (CSP, CC, PP, Collar rules) + tests | SHA: ___

## Phase ES2 — CSP Fix

- [ ] ES2 — Fix `CSPNiftyV1` thresholds (delta 0.45, loss 1.75×) + re-test | SHA: ___

## Phase ES3–ES5 — Strategy Classes

- [ ] ES3 — `CCOverlayV1` + tests | SHA: ___
- [ ] ES4 — `PPOverlayV1` + tests | SHA: ___
- [ ] ES5 — `CollarOverlayV1` + tests | SHA: ___

## Phase ES6 — Closure

- [ ] ES6 — `OverlayCloser` (atomic Collar close + rollback) + tests | SHA: ___

## Phase ES7 — EOD Integration

- [ ] ES7 — Tier 1 EOD signal write in `paper_3track_snapshot.py` + tests | SHA: ___

## Phase ES8 — Daemon Integration

- [ ] ES8 — Register overlay strategies in daemon; `MONITOR_OVERLAYS` gate | SHA: ___

## Phase ES10 — CSP Lifecycle: R5 Re-entry

- [ ] ES10 — R5 re-entry eligibility check in `CSPNiftyV1.apply_action(PROFIT_TARGET)` + Telegram alert + tests | SHA: ___

## Phase ES11 — Base Expiry Roll Detection

- [ ] ES11 — Base expiry detection in `paper_3track_snapshot.py`; `get_next_contract()` in `InstrumentLookup`; Telegram alert with roll commands + tests | SHA: ___

## Phase ES12 — Entry Discipline

- [ ] ES12 — Liquidity gate enforcement in `find_strike_by_delta.py`; R3 hard block + `--force-entry` in `record_paper_trade.py` + tests | SHA: ___

## Phase ES9 — Docs Close + Archive (MUST BE LAST)

- [ ] ES9 — DECISIONS.md (10 rows), CONTEXT.md, TODOS.md; archive council + csp_nifty_v1 spec | SHA: ___

---

---

## Implementation Priority

Run stories in this order — later stories depend on earlier ones:

| Priority | Stories | Rationale |
|---|---|---|
| **P0 — Gate** | Prerequisite check | `StrategyMonitor` + `PaperExecutor` must exist (PB1.2, PB1.3) |
| **P1 — Foundation** | ES0 → ES1 → ES2 | Schema, rule engine, CSP threshold fix — everything else depends on these |
| **P2 — CSP lifecycle** | ES10 → ES12 | R5 re-entry + entry discipline — directly impacts open Cycle 2 position |
| **P3 — Overlays** | ES3 → ES4 → ES5 → ES6 | CC, PP, Collar strategy classes + OverlayCloser |
| **P4 — Integration** | ES7 → ES8 | EOD + daemon wiring — needs P1 + P3 complete |
| **P5 — Base lifecycle** | ES11 | Base expiry roll alert — monthly cadence; next event 2026-06-30 |
| **P6 — Docs** | ES9 | Always last — archives spec only when all code is committed |

**Out-of-scope gaps** (need separate story files, not blocked on this story):
- R4 event filter (Budget, RBI MPC, elections) — requires `src/market_calendar/events.yaml` design
- Collateral leg tracking (`long_niftybees` per cycle) — lifecycle story needed
- Transaction cost model application to paper P&L — analytics story needed

---

## Definition of Done

All items above checked. Then verify:

```bash
python -m pytest tests/unit/ --tb=no -q   # all green
git log --oneline -10                      # 10 commits, one per ES task
search_graph("CCOverlayV1")                # exists
search_graph("ExitSignalEngine")           # exists
search_graph("OverlayCloser")              # exists
ls docs/council/archive/strategy/ | grep exit-philosophy   # archived
ls docs/strategies/archive/ | grep csp_nifty               # archived
```

## Regression Gate

The following must remain unchanged after each commit:

```bash
# paper-backbone tests (do not break these)
python -m pytest tests/unit/strategy/ --tb=short -q
python -m pytest tests/unit/paper/ --tb=short -q
```

## Environment Variables Added

| Variable | Default | Effect |
|---|---|---|
| `MONITOR_OVERLAYS` | `0` | `1` = enable intraday overlay monitoring in daemon |
