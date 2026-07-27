# Backtest Engine — Phase 3 (IC Live + Third Strategy + Portfolio Construction) — Tasks

**Status:** Not started. Gated on `docs/plan/backtest-engine/phase2/` task **2.7** (Phase 2 gate).
Objective: CSP and IC running live, add a third strategy (event-driven), introduce
portfolio-level thinking (correlations, regime-aware sizing). Duration target ~12 months.

Canonical spec: `BACKTEST_PLAN_PHASE1.md` → `# Phase 3 — IC Live + Third Strategy + Portfolio
Construction` (lines 836–915). Thin status index only — do not fork detail into both places.

- [ ] **3.1** — STRATEGY — Deploy IC v1 live. Owner: Animesh. 1 lot, no scaling for 3 months
  minimum, separate capital bucket from CSP until 3.4 lands.
- [ ] **3.2** — STRATEGY — Third strategy specification. Owner: Animesh. Choose Jade Lizard
  (preferred) or Event-Driven Calendar Spread — decision + rationale recorded in `DECISIONS.md`
  before writing the spec.
- [ ] **3.3** — CODE — Event calendar + calendar spread strategy (`src/market_calendar/events.py`,
  `src/strategy/calendar_spread.py`). Only needed if Candidate B (Calendar Spread) was chosen in
  3.2 — if Candidate A (Jade Lizard) was chosen, this task's calendar-spread half is moot; confirm
  the 3.2 decision before starting.
- [ ] **3.4** — CODE — Portfolio-level attribution (`src/portfolio/correlation.py`,
  `strategy_daily_pnl` table). Pairwise 90-day rolling correlation across active strategies;
  alert on any pair >0.8 for 4 consecutive weeks.
- [ ] **3.5** — CODE — Regime classifier (rule-based, not ML) (`src/regime/`). **Read the
  consolidation note in `stories.md` before starting** — this may extend
  `src/strategy/regime.py` (built in Track A / `signals-eval-core` SE2.2) rather than creating a
  parallel module.
- [ ] **3.6** — GATE — End of Phase 3. Blocks `docs/plan/backtest-engine/phase4/`.
