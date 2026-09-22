# variance-gate — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session. Tick the box and append `| SHA: <sha>` (code changes) or `| Date: YYYY-MM-DD` (observation gates) when done. Add one
> line to `TODOS.md` session log. Full story spec for each task: `docs/plan/variance-gate/stories.md`.

---

## Phase VG0 — Spec Reconciliation (prerequisite — unblocks everything)

- [ ] **VG0** — Resolve 4 mismatches in `csp_nifty_v1.md` (lot size, time stop, R-number naming, R4 def); align with `BACKTEST_PLAN.md`. | Owner: Animesh | Model: n/a | Review: none | SHA: —

---

## Phase VG1 — Tier 0.5 Operational Review

- [ ] **VG1** — Tier 0.5 two-cycle checklist: strike selection, bid/ask recording, P&L reconciliation, NiftyBees collateral, R3/R4 skip logic. | Owner: Animesh | Model: n/a | Review: none | SHA: —

---

## Phase VG2 — Gate A + B: Sample Size + Exit-Path Validation

- [ ] **VG2.A** — Gate A: ≥6 executed paper CSP cycles and ≥9 calendar months of entry-decision observation. Record count and start date. | Owner: Animesh | Model: n/a | Review: none | SHA: —
- [ ] **VG2.B1** — Gate B: profit-target (50%) exit validated — live paper occurrence or historical replay. | Owner: Animesh | Model: n/a | Review: none | SHA: —
- [ ] **VG2.B2** — Gate B: time-stop (21-day) exit validated — live paper or replay. | Owner: Animesh | Model: n/a | Review: none | SHA: —
- [ ] **VG2.B3** — Gate B: delta/mark-stop exit validated — **live paper required before Tier 2**; replay acceptable for Tier 1. | Owner: Animesh | Model: n/a | Review: none | SHA: —

---

## Phase VG3 — Gate C: Regime Completeness

*At least ONE of the three criteria must be satisfied (live or replay). Replay requires the Phase 1 harness — do not build until task 1.3a data pipeline is live.*

- [ ] **VG3.C** — Gate C: one of (a) IVR>50 at entry, (b) ≥5% Nifty intraday drawdown, (c) short-put delta ≤−0.35 pre-exit. | Owner: Animesh | Model: n/a | Review: none | SHA: —

---

## Phase VG4 — Gate D: Regime-Matched Z-Score

*Blocked by Phase 1 task 1.11 (Z-score computation) + ≥6 executed cycles.*

- [ ] **VG4.D** — Gate D: `|Z| ≤ 1.5` on both full 8-year backtest and regime-matched subset. Record Z-scores and methodology. | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

---

## Gate Summary (fill in as each criterion passes)

| Criterion | Status | Evidence | Date |
|-----------|--------|----------|------|
| Gate A — min sample | ⬜ | — | — |
| Gate B1 — profit-target exit | ⬜ | — | — |
| Gate B2 — time-stop exit | ⬜ | — | — |
| Gate B3 — delta/mark-stop exit | ⬜ | — | — |
| Gate C — regime completeness | ⬜ | — | — |
| Gate D — Z-score | ⬜ | — | — |

**Tier 1 pilot eligible:** All A–D green + no unresolved accounting defects.
