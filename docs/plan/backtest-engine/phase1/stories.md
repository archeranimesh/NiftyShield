# Backtest Engine — Phase 1 — Story Index

This story dir tracks status only (see `tasks.md`). **Full implementation spec for every task
below lives in `BACKTEST_PLAN_PHASE1.md` (root)** — that file is referenced directly from
`CLAUDE.md`'s Quick Reference table and `DECISIONS.md`, so duplicating its content here would
create a second source of truth that drifts. Each entry below is a pointer to the exact section
to read before implementing — not a summary to implement from.

Before implementing any task: read `CONTEXT.md`, then read the named section in full in
`BACKTEST_PLAN_PHASE1.md` (it contains the sub-checklist, commit sequencing, and any
code-reviewer/test requirements specific to that task — do not skip straight to `tasks.md`'s
one-line summary).

## 1.1 — STRATEGY — Stockmock calibration backtests
Section: `BACKTEST_PLAN_PHASE1.md` → `## 1.1 — STRATEGY — Stockmock calibration backtests`.
Owner: Animesh, Stockmock UI only — no code. Mirrors the checklist in `TODOS.md`'s
"Animesh-only: Stockmock Calibration Backtests" section; that TODOS.md section is the one to
tick, this task exists so the story has a complete index.

## 1.3a — CODE — Underlying OHLC ingest (Nifty 50, India VIX, NiftyBees)
Section: `BACKTEST_PLAN_PHASE1.md` → `## 1.3a — CODE — Underlying OHLC ingest`.
New module: `src/backtest/ohlc_ingest.py`. Async, resumable, rate-limited separately from the
DhanHQ `rollingoption` budget. Derived fields (ATR-14/20, 50D slope, 10M SMA, VIX 252D rank) are
part of this task, not a follow-up.

## 1.3b — CODE — TrueData 1-min options data ingestion pipeline
Section: `BACKTEST_PLAN_PHASE1.md` → `## 1.3b — CODE — TrueData 1-min options data ingestion pipeline`.
New modules: `src/backtest/lot_sizes.py`, `src/backtest/truedata_parser.py`,
`scripts/truedata_ingest.py`, `scripts/truedata_registry.py`. Column order is vendor-documented,
not inferred from data — read the NOTE 1/NOTE 2 schema block in the source section before writing
the parser.

## 1.4 — CODE — Port quant-4pc backtest engine
Section: `BACKTEST_PLAN_PHASE1.md` → `## 1.4 — CODE — Port quant-4pc backtest engine`.
New modules: `src/backtest/engine.py`, `src/backtest/pricers.py`, `src/backtest/costs.py`.
Real `code-reviewer` gate required — heavy focus on the Decimal invariant (never float) throughout
the cost model, per the source section's explicit note.

## 1.5 — CODE — Backtest results storage
Section: `BACKTEST_PLAN_PHASE1.md` → `## 1.5 — CODE — Backtest results storage`.
New module: `src/backtest/store.py` (`BacktestStore`). **`src/analytics/` is a separate task —
tracked as B2.1/B2.2 in `docs/plan/backtest-eval-core/stories.md`, not here.** Do not build
`src/analytics/` as part of 1.5.

## 1.6 — CODE — Port Iron Condor strategy (reference implementation)
Section: `BACKTEST_PLAN_PHASE1.md` → `## 1.6 — CODE — Port Iron Condor strategy`.
Scaffolding port only — do not deploy anywhere. Second engine-validation exercise after CSP (1.7).

## 1.6a — CODE — Black '76 IV reconstruction + Greeks for backtest
Section: `BACKTEST_PLAN_PHASE1.md` → `## 1.6a — CODE — Black '76 IV reconstruction + Greeks for backtest`.
Prerequisites: 1.3 (done) + 1.3a. Follow the 2026-04-30 council methodology in
`DECISIONS.md → IV Reconstruction Methodology` exactly — Black '76 with futures `settle_price` as
forward price `F`, not spot.

## 1.7 — CODE — Implement CSP strategy in backtest engine
Section: `BACKTEST_PLAN_PHASE1.md` → `## 1.7 — CODE — Implement CSP strategy in backtest engine`.
New module: `src/strategy/csp.py`. `CSPConfig` thresholds come from the Stockmock calibration
results (task 1.1) — do not hardcode placeholder values if 1.1 hasn't landed yet; block on it.

## 1.8 — CODE — Run CSP backtest across full history (three variants)
Section: `BACKTEST_PLAN_PHASE1.md` → `## 1.8 — CODE — Run CSP backtest across full history`.
V1 (baseline), V2 (R5 re-entry, IVR-gated), V3 (always-on roll). Results go into
`docs/strategies/csp_nifty_v1.md` → "Backtest Results" table.

## 1.9 — CODE — Synthetic pricer for deep OTM protective legs
Section: `BACKTEST_PLAN_PHASE1.md` → `## 1.9 — CODE — Synthetic pricer for deep OTM protective legs`.
New modules: `src/backtest/skew.py`, `src/backtest/synthetic_pricer.py`.

## 1.9a — CODE — Integrated strategy backtest (three legs combined)
Section: `BACKTEST_PLAN_PHASE1.md` → `## 1.9a — CODE — Integrated strategy backtest`.
New module: `src/strategy/niftyshield.py`. Full 2016-01–present backtest; results into
`docs/strategies/niftyshield_integrated_v1.md`.

## 1.11 — STRATEGY — Variance check: paper vs backtest
Section: `BACKTEST_PLAN_PHASE1.md` → `## 1.11 — STRATEGY — Variance check`.
Global Z-score **and** regime-matched Z-score, both against `|Z| ≤ 1.5` after bias adjustment.
If it fails: iterate on the backtest, then re-run 1.8 and 1.11 — do not adjust the paper data to
fit.

## 1.12 — GATE — End of Phase 1
Section: `BACKTEST_PLAN_PHASE1.md` → `## 1.12 — GATE — End of Phase 1`.
Not a code task — a checklist gate requiring 1.1–1.11 complete, full test suite green, and
Animesh sign-off recorded in a `TODOS.md` session log entry. Blocks `docs/plan/backtest-eval-core/`
and, transitively, `docs/plan/signals-eval-core/`.

---

**What happens after 1.12:** `BACKTEST_PLAN_PHASE1.md` continues with its own internal Phase
2/3/4 sections (CSP live deployment, IC live/paper, portfolio cap layer, third strategy, basket
maturity) — these are tracked as separate story dirs, not part of this Phase 1 story:
`docs/plan/backtest-engine/phase2/`, `phase3/`, `phase4/`. Note these are distinct from this
repo's own `docs/plan/phase2-integrations/` story (P&L viz/Zerodha/execution layer/Telegram),
which is unrelated content that happens to also be called "Phase 2" — see that story's naming
note.

**Correction (2026-07-27):** an earlier pass through this repo's docs flagged the
`2.S2a/2.S2b/2.S2c` signal-generator tasks inside `BACKTEST_PLAN_PHASE1.md`'s "Parallel Research
Tracks" section as an unresolved duplicate of `docs/plan/signals-eval-core/tasks.md`'s SE3.x
tasks, needing reconciliation. That was wrong — `BACKTEST_PLAN_PHASE1.md` line 678 explicitly
names `docs/plan/signals-eval-core/` as the "full methodology documents" for that section. It's
an intentional two-level cross-reference (phase-sequencing overlay → implementation checklist),
not an accidental duplication. See `docs/plan/backtest-engine/phase2/tasks.md` for the corrected
note.
