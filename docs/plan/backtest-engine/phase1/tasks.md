# Backtest Engine — Phase 1

**Status:** Not started. Gated on the Phase 0.8 variance-gate (see `BACKTEST_PLAN.md` — CSP v1
paper-trading gate, criteria A–D). This story exists so Phase 1 has a `docs/plan/` entry like
every other story in `TODOS.md`'s Priority-Ordered Open Work list — it is a thin index, **not**
a duplicate of the task detail.

**Canonical spec (edit here, not in this file):** [`BACKTEST_PLAN_PHASE1.md`](../../../BACKTEST_PLAN_PHASE1.md)
(root) — full task bodies, sub-checklists, commit sequencing, and code-reviewer/test requirements
for every task below. This `tasks.md` only tracks top-level status so the priority list has
something concrete to point at; do not fork task detail into both places.

## Tasks (top-level status, detail in BACKTEST_PLAN_PHASE1.md)

- [ ] **1.1** — STRATEGY — Stockmock calibration backtests (COVID/IL&FS/2022 stress windows). Owner: Animesh, no code.
- **1.2** — DEFERRED — TimescaleDB container (not tracked as open work).
- [x] **1.3** — CODE — NSE F&O Bhavcopy ingestion pipeline.
- [ ] **1.3a** — CODE — Underlying OHLC ingest (Nifty 50, India VIX, NiftyBees).
- [ ] **1.3b** — CODE — TrueData 1-min options data ingestion pipeline.
- [ ] **1.4** — CODE — Port quant-4pc backtest engine.
- [ ] **1.5** — CODE — Backtest results storage (`BacktestStore`). `src/analytics/` work is tracked separately under `docs/plan/backtest-eval-core/` (B2.x codes) — do not conflate the two.
- [ ] **1.6** — CODE — Port Iron Condor strategy (reference implementation, scaffolding only).
- [ ] **1.6a** — CODE — Black '76 IV reconstruction + Greeks for backtest.
- [ ] **1.7** — CODE — Implement CSP strategy in backtest engine.
- [ ] **1.8** — CODE — Run CSP backtest across full history (V1/V2/V3 variants).
- [x] **1.10** — CODE — Upstox live option chain snapshot (daily) — shipped via chain-data story.
- [x] **1.10a** — CODE — Intraday live option chain snapshots (5-min) — shipped via chain-data story.
- [ ] **1.9** — CODE — Synthetic pricer for deep OTM protective legs.
- [ ] **1.9a** — CODE — Integrated strategy backtest (three legs combined).
- [ ] **1.11** — STRATEGY — Variance check: paper vs backtest (`|Z| ≤ 1.5`, bias-adjusted).
- [ ] **1.12** — GATE — End of Phase 1 (Animesh sign-off). Blocks `docs/plan/backtest-eval-core/` and, transitively, `docs/plan/signals-eval-core/`.

**Next unchecked (in dependency order):** 1.1 (Animesh, no code) and 1.3a/1.4 (Cowork) can proceed
in parallel — both are prerequisites named by `docs/plan/backtest-eval-core/tasks.md`'s B1.1.

**Note on internal "Phase 2"/"Phase 3" headers inside `BACKTEST_PLAN_PHASE1.md`:** the root file
also contains its own later sections (CSP live deployment, IC live/paper, portfolio cap layer,
signal generators) that are a different "Phase 2/3" numbering than this repo's `TODOS.md`
Phase 2 story (`docs/plan/phase2-integrations/`). Some of that later content (2.S2a/2.S2b/2.S2c
signal generators) appears to duplicate `docs/plan/signals-eval-core/tasks.md`'s SE3.x tasks —
flagged here, not resolved; needs a dedicated reconciliation pass before either doc is treated as
sole source of truth for that content.
