# Signals Evaluation Core — prompt

> Build the regime engine, swing/investment signal generators, backtesters, and the validation pipeline that gates every strategy before real capital.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

**⛔ Blocked.** This story cannot start until both prerequisite blocks land: tasks 1.3 (Bhavcopy ingest) and 1.3a (Nifty OHLC Parquet) in `BACKTEST_PLAN_PHASE1.md`, and `backtest-eval-core` tasks
B1.1–B2.9 (`BacktestStore` + analytics layer). `docs/plan/README.md` "Blocked / Later Stories" lists this story as blocked by `backtest-eval-core` + the Phase 1.12 gate. Check both before picking up
SE1.1 — do not resolve the blocker, just confirm it has cleared.

## Why this story exists

Phase 2 (`BACKTEST_PLAN_PHASE1.md`) needs a signal-generation and validation layer before any swing (Donchian/ORB/Gap Fade) or investment (SMA/Dual Momentum/PE Band) strategy can be paper-traded or
deployed with real capital. This story builds that layer: a regime tagger that classifies every historical trading day, per-strategy signal generators that emit `SwingSignal` / `AllocationDecision`
records, two backtesters (points-based and allocation-based), and a validation pipeline (walk-forward, Monte Carlo, sensitivity, reports) that produces the pass/kill gate each strategy must clear
before going live. It exists because Council-level strategy decisions (`docs/archive/council/strategy/`) require this evaluation infrastructure as a precondition, not an afterthought.

## Scope guard

In bounds: `src/strategy/` (regime tagger, signal generators, execution/spread selection), `src/backtest/` additions (points/allocation/spread backtesters, walk-forward, Monte Carlo, sensitivity,
reports, `SignalEvalStore`), `src/instruments/` additions (PE loader, risk-free rate), and the `regime_tags` / `swing_signals` / `allocation_decisions` tables in `portfolio.sqlite` (see `schema.md`).
Out of bounds: the existing `BacktestStore` schema (`src/backtest/store.py`, owned by `backtest-eval-core`) — this story writes trade results into it but does not change its tables; live/paper order
execution and broker wiring; any change to `docs/plan/README.md` or `TODOS.md` beyond the pointer updates each task's own commit makes. This story changes `src/` behaviour — it is not
docs/tooling-only.

## Session-start load hints

- `schema.md` (this folder) — read before any `SignalEvalStore` or DB-touching task; new tables `regime_tags`, `swing_signals`, `allocation_decisions` plus the `DB_REGISTRY.md` row to add.
- `BACKTEST_PLAN_PHASE1.md` §Phase 2 — the task checklist (2.S0–2.S3b, 2.I0–2.I2) this story's tasks map onto; SE8 ticks those boxes on close.
- `docs/archive/council/strategy/` — binding council decisions on strategy parameters and validation thresholds; read before implementing any signal generator or gate.
- `src/strategy/CLAUDE.md` (created in SE2.1) — module invariants for everything under `src/strategy/` once it exists.
- `REFERENCES.md` — instrument keys and expiry/DTE conventions for ORB/Gap Fade expiry selection (Thursday→Tuesday expiry-day change, April 2026).

## Task overview

- **SE1.1** — Verify Nifty OHLC data coverage and derived fields; integrity report.
- **SE1.2** — PE data loader (NSE PE CSV → Parquet).
- **SE1.3** — Risk-free rate series (AMFI liquid fund NAV → Parquet).
- **SE2.1** — `src/strategy/` package scaffold.
- **SE2.2** — Regime tagger (`RegimeTagger`/`RegimeTag`) + `SignalEvalStore` regime CRUD.
- **SE2.3** — Regime distribution report script (no tests).
- **SE3.1** — Donchian swing signal generator + shared `SwingSignal` model.
- **SE3.2** — ORB swing signal generator + calendar exclusions + DTE expiry selection.
- **SE3.3** — Gap Fade swing signal generator + VIX-IVP filter.
- **SE4.1** — SMA filter investment signal generator + shared `AllocationDecision` model.
- **SE4.2** — Dual Momentum investment signal generator.
- **SE4.3** — PE Band investment signal generator.
- **SE4.4** — Covered Call Overlay paper-trading setup (docs + broker pledge confirmation).
- **SE5.1** — Points backtester (swing strategies).
- **SE5.2** — Allocation backtester (investment strategies).
- **SE5.3** — Spread selector / execution module.
- **SE6.1** — Walk-forward validation engine.
- **SE6.2** — Monte Carlo trade-sequence simulator.
- **SE6.3** — Sensitivity analyser.
- **SE6.4** — Validation report generators.
- **SE6.5** — Portfolio construction analysis (conditional).
- **SE7.1** — Spread backtester, Tier 2 (conditional on SE5.1 passing Tier 1).
- **SE8** — Docs close.

## Definition of done

Every task in `tasks.md` is ticked with a real closing SHA. Every swing strategy (Donchian/ORB/Gap Fade) and every investment strategy (SMA/Dual Momentum/PE Band) has a generator, a backtest, and a
walk-forward + Monte Carlo + sensitivity validation report on file. At least one swing strategy clears all 6 failure conditions before Tier 2 (SE7.1) starts. `CONTEXT.md`, `DECISIONS.md`, and
`BACKTEST_PLAN_PHASE1.md` Phase 2 checkboxes are updated (SE8). `docs/strategies/covered_call_overlay_v1.md` exists with broker compatibility status recorded.

## Perspectives not covered

This story specs the evaluation pipeline but not the go-live decision criteria beyond the 6 failure-condition gate already defined in `BACKTEST_PLAN_PHASE1.md` — position sizing, capital allocation
across strategies once multiple pass, and real-money rollout sequencing are left to a separate council decision at that point, not assumed here.
