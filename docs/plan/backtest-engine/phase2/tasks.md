# Backtest Engine — Phase 2 (CSP Live + Iron Condor Paper) — Tasks

**Naming note:** this is `BACKTEST_PLAN_PHASE1.md`'s internal "Phase 2 — CSP Live + Iron Condor
Paper" section — **not** the same as `docs/plan/phase2-integrations/` (P&L viz / Zerodha /
execution layer / Telegram), which is this repo's own separate "Phase 2" naming. Do not confuse
the two.

**Status:** Not started. Gated on `docs/plan/backtest-engine/phase1/` task **1.12** (Phase 1 gate).
Objective: deploy CSP live (1 lot) with continuous backtest/paper re-validation, and start
paper-trading Iron Condor. Duration target ~6 months. **Key rule: do not scale CSP beyond 1 lot
for the first 3 months even if profitable** — first 3 months of any new live strategy is
regime-dependent data, not proof of edge.

Canonical spec: `BACKTEST_PLAN_PHASE1.md` → `# Phase 2 — CSP Live + Iron Condor Paper` (lines
568–668). This `tasks.md`/`stories.md` is a thin status index — do not fork detail into both
places.

## Tasks (CSP live + IC paper pipeline)

- [ ] **2.1** — CODE — Continuous re-validation loop (`src/risk/monitoring.py`,
  `src/risk/cusum_config.py`, `src/risk/early_guards.py`). **The most important piece of code in
  this plan** — per-cycle CUSUM drift detection + 7-guard early-deployment stack.
- [ ] **2.2** — STRATEGY — Deploy CSP live (1 lot). Owner: Animesh.
- [ ] **2.3** — STRATEGY — Iron Condor v1 specification (`docs/strategies/ic_nifty_monthly_v1.md`).
  Owner: Animesh. Includes the regime-conditional Iron Butterfly variant.
- [ ] **2.4** — CODE — Extend `src/strategy/iron_condor.py` to match the IC v1 spec exactly.
- [ ] **2.5** — CODE — IC backtest across 2020–present.
- [ ] **2.6** — STRATEGY — Paper trade IC v1 in parallel with CSP live. Owner: Animesh.
- [ ] **2.7** — GATE — End of Phase 2. Blocks Phase 3.

## Parallel Research Tracks (not duplicate work — see note)

`BACKTEST_PLAN_PHASE1.md` also has a "Phase 2 — Parallel Research Tracks" section (Track A:
`2.S0`–`2.S7` swing pipeline; Track B: `2.I0`–`2.I5` investment pipeline) that runs in parallel
with 2.1–2.7 above, gated only on Phase 1.12 (not on 2.1–2.7 closing). **This is not a duplicate
of `docs/plan/signals-eval-core/` needing reconciliation** — the root doc explicitly names
`docs/plan/signals-eval-core/` as "Full methodology documents" for this section (line 678):
Track A → `signals-eval-core` stories SE3.x, Track B → SE4.x, shared validation → SE5–SE6. The
`2.S*`/`2.I*` codes here are a phase-sequencing overlay; the actual implementation checklist is
`signals-eval-core/tasks.md`'s SE-prefixed codes. **Do not build a separate task list for
2.S0–2.S7/2.I0–2.I5** — track progress via `docs/plan/signals-eval-core/tasks.md` (already item
17 in `TODOS.md`'s Priority-Ordered Open Work) instead.

*(Correction: an earlier pass through this repo's docs flagged this as an "unresolved duplicate
needing reconciliation" — that was wrong. Re-reading `BACKTEST_PLAN_PHASE1.md` line 678 directly
shows it's an intentional two-level cross-reference, not an accidental duplication.)*
