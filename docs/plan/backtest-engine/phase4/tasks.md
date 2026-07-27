# Backtest Engine — Phase 4 (Basket Maturity + Finideas Evaluation) — Tasks

**Status:** Not started. Gated on `docs/plan/backtest-engine/phase3/` task **3.6** (Phase 3 gate).
Objective: basket of 3–5 validated strategies; explicit keep-or-exit decision on Finideas backed
by ≥2 years of tracked realised data; optional ML overlays for narrow problems only. Duration
target 2028–2030.

Canonical spec: `BACKTEST_PLAN_PHASE1.md` → `# Phase 4 — Basket Maturity + Finideas Evaluation`
(lines 917–967). Thin status index only — do not fork detail into both places.

- [ ] **4.1** — STRATEGY — Finideas evaluation. Owner: Animesh. **The big delayed decision.**
  Requires ≥24 months of Finideas tracked realised P&L. Decision framework: within ±2% of best
  alternative → exit; +3% or more above → stay; between +2–3% → stay 6 more months, re-evaluate.
- [ ] **4.2** — STRATEGY — Fourth / fifth strategies (as maturity allows). Owner: Animesh. One
  per year maximum. Candidates: short strangle (HIGH_IV regime only), ratio spread.
- [ ] **4.3** — CODE — ML overlays (narrow scope only). Optional — build only if a specific
  narrow problem emerges. Explicitly out of scope: direction prediction, strategy generation,
  regime prediction.
- [ ] **4.4** — GATE — Plan closure. Requires 3–5 live strategies each ≥1 year within envelope,
  Finideas decision documented, honestly-measured basket return shared with no adjustments, and
  at least one kill criterion having actually triggered and been handled cleanly somewhere in the
  plan's history.
