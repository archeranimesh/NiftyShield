# variance-gate — Session Orientation

> **What this story covers:** CSP v1 deployment gate — the criteria that must be satisfied
> before any live capital is committed to the Cash-Secured Put strategy on Nifty 50.
>
> This is a **decision + observation story**, not a pure implementation story.
> Most tasks are human checkpoints (Animesh reviews accumulated evidence) rather than
> Cowork build tasks. The one pure implementation task is VG0 (spec reconciliation).

---

## Context

The CSP v1 Nifty strategy is in paper trading. The Phase 0.8 gate defines what must be
true before live capital is deployed. The gate was council-approved on 2026-05-02.

Full gate specification: `docs/plan/variance-gate/variance_gate_spec.md`
Council decision: `docs/council/2026-05-02_variance-gate-regime-completeness.md`
Canonical strategy spec (to be reconciled in VG0): `docs/strategies/csp_nifty_v1.md`

---

## Session start protocol

1. Read this file + `CONTEXT.md` + `docs/plan/variance-gate/variance_gate_spec.md`.
2. Check `variance_gate_tasks.md` — find the first unchecked item.
3. For VG0 (Cowork task): follow implementation rules in root `CLAUDE.md`.
4. For VG1–VG4 (Animesh checkpoints): Cowork helps review evidence and tick criteria.
5. After each task: tick `variance_gate_tasks.md`, append `| SHA: <sha>` or `| Date: YYYY-MM-DD`,
   add one line to `TODOS.md` session log.

---

## Task overview

| Task | Owner | Type | Blocked by |
|------|-------|------|------------|
| VG0 — CSP v1 spec reconciliation | Animesh + Cowork | Doc fix | Nothing |
| VG1 — Tier 0.5 two-cycle review | Animesh | Checkpoint | 2 executed cycles |
| VG2 — Gate A + B: sample + exit validation | Animesh | Observation | ≥6 cycles + exit events |
| VG3 — Gate C: regime completeness | Animesh | Observation/Replay | ≥1 stress event or replay harness |
| VG4 — Gate D: regime-matched Z-score | Cowork | Computation | Phase 1 task 1.11 + ≥6 cycles |

**Critical path:** VG0 → (parallel observation: VG1, VG2, VG3) → VG4 → Phase 1 pilot eligibility.
VG0 is the only task that can be actioned right now.
