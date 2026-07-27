# Backtest Engine — Phase 2 — Story Index

Full spec for every task below lives in `BACKTEST_PLAN_PHASE1.md` (root), lines 568–668. Read the
named section in full before implementing — do not implement from `tasks.md`'s one-line summary.

## 2.1 — CODE — Continuous re-validation loop
Section: `## 2.1 — CODE — Continuous re-validation loop`. **Council decision 2026-05-02:** weekly
Z-score replaced by per-cycle lower-sided CUSUM — see
`docs/council/2026-05-02_continuous-revalidation-statistical-power.md` and
`DECISIONS.md → Live Strategy Monitoring`. Three new modules
(`src/risk/monitoring.py`, `src/risk/cusum_config.py`, `src/risk/early_guards.py`), 7 guards,
Telegram alerting gated by cycle count N. This is financial-logic code guarding a live strategy —
real `@code-reviewer` gate mandatory, no substitution.

## 2.2 — STRATEGY — Deploy CSP live (1 lot)
Section: `## 2.2 — STRATEGY — Deploy CSP live (1 lot)`. Owner: Animesh. Depends on static-IP
provisioning for automated order placement (see `docs/plan/phase2-integrations/` OE-1) — if not
provisioned, CSP goes live via manual order placement with trades still recorded via
`record_trade.py`. Confirm current lot size before entry (65 as of Jan 2026 — lot sizes change
annually, per `REFERENCES.md`).

## 2.3 — STRATEGY — Iron Condor v1 specification
Section: `## 2.3 — STRATEGY — Iron Condor v1 specification`. Owner: Animesh. New spec doc
`docs/strategies/ic_nifty_monthly_v1.md`, same required sections as the CSP spec. Includes the
regime-conditional Iron Butterfly variant (IVR < 25th pctile AND |50D slope z| < 0.5 → shift to
ATM-centred Iron Butterfly). Must pass the strategy-spec validator and get an `options-strategist`
agent review on the sizing/risk section before committing.

## 2.4 — CODE — IC strategy to match spec
Section: `## 2.4 — CODE — IC strategy to match spec`. Extends `src/strategy/iron_condor.py`
(scaffolding port already exists from `docs/plan/backtest-engine/phase1/` task 1.6) — diff against
that scaffolding rather than rewriting from scratch.

## 2.5 — CODE — IC backtest
Section: `## 2.5 — CODE — IC backtest`. Run across 2020–present, extract metrics per task 1.8's
methodology, results into `ic_nifty_monthly_v1.md`.

## 2.6 — STRATEGY — Paper trade IC v1 (parallel to CSP live)
Section: `## 2.6 — STRATEGY — Paper trade IC v1`. Owner: Animesh. Minimum 12 weeks +
`docs/plan/backtest-engine/phase1/` task 1.11-style variance check passing before considering live.

## 2.7 — GATE — End of Phase 2
Section: `## 2.7 — GATE — End of Phase 2`. Requires: CSP live ≥3 months with no CUSUM
halt/reduce, no CSP kill criterion triggered, IC paper ≥12 weeks with variance check passed,
re-validation loop running weekly with zero missed runs, and `src/backtest/portfolio_sim.py`
(cap-aware Layer 2 portfolio backtester) complete with Sharpe ≥0.8 and max DD <₹6L over
2016–present — **if that threshold isn't met, Phase 3 live deployment is blocked regardless of
per-strategy metrics.** Blocks `docs/plan/backtest-engine/phase3/`.

---

**Parallel Research Tracks — do not implement from this story.** Track A (`2.S0`–`2.S7`) and
Track B (`2.I0`–`2.I5`) run in parallel with 2.1–2.7, gated only on Phase 1.12. Their actual
implementation checklist is `docs/plan/signals-eval-core/tasks.md` (SE3.x for Track A, SE4.x for
Track B, SE5–SE6 shared validation) — per `BACKTEST_PLAN_PHASE1.md` line 678's explicit
cross-reference. Pick up that story's tasks, not a parallel list here.

**Cross-story overlap flagged for later, not resolved now:** `BACKTEST_PLAN_PHASE1.md`'s own
3.5 section notes that Track A's regime engine (`src/strategy/regime.py`, task 2.S1) and Phase
3's regime classifier (`src/regime/`) may need consolidating into one module rather than two
independent classifiers with overlapping VIX logic — read that note (`3.5`'s "Overlap with Track
A" paragraph) before building either if both are in flight at once.
