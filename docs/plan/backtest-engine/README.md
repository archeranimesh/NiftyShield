# Backtest engine — epic index

> Builds the Phase 0→1+ systematic options backtest/paper-trading pipeline in four chained phases — CSP v1 variance-gate buildout, CSP-live/IC-paper expansion, post-gate strategy expansion, and
> long-horizon capital allocation — each phase gated on the previous phase's closing GATE task.

## Why this epic exists

`BACKTEST_PLAN_PHASE1.md` (root) is the canonical multi-year spec for taking the options strategies from Phase 0 paper-trading through live capital deployment. This epic is the implementation index
into that spec: four phase folders, each a thin `tasks.md`/`stories.md` pointer into the matching root-doc section, chained so a phase cannot start before its predecessor's gate task lands.

## Scope decisions

- **The root doc is canonical, not this folder.** `tasks.md`/`stories.md` in each phase dir index task IDs into `BACKTEST_PLAN_PHASE1.md` sections — they never restate the full spec. A task must be
  implemented from the root-doc section, not the one-line `tasks.md` summary.
- **Phase gates are hard blockers.** `phase2` cannot start before `phase1` task **1.12** (Phase 1 gate) is ticked; `phase3` before `phase2` task **2.7**; `phase4` before `phase3` task **3.6**. The
  router (`prompt.md`) enforces this walk order.
- **Signal research tracks live elsewhere.** Swing/investment signal research (Track A/B, `2.S*`/`2.I*` in the root doc) is tracked under `docs/plan/signals-eval-core/`, not here — `phase2/` only
  covers the CSP-live/IC-paper pipeline (2.1–2.7).
- **`phase4` is 2028+ live-capital territory.** Most of its tasks are marked "Owner: Animesh" — capital-allocation and strategic decisions, not implementation tasks.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `phase1/` | Phase 0.8 variance-gate CSP v1 paper-trading buildout | 🔄 In progress — next 1.3a/1.4 | — | — |
| `phase2/` | CSP-live / IC-paper pipeline (2.1–2.7) | ⬜ Not started | `phase1` task 1.12 | — |
| `phase3/` | Post-Phase-2 strategy expansion | ⬜ Not started | `phase2` task 2.7 | — |
| `phase4/` | Long-horizon capital allocation + ML overlays | ⬜ Not started | `phase3` task 3.6 | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view — per-task checkboxes live only in each sub-story's `tasks.md`.

## Cross-cutting constraints

- Every phase's `prompt.md` opens with a gate check against the previous phase's closing GATE task (or, for `phase1`, the Phase 0.8 variance gate itself — see `TODOS.md` §Feature Backlog,
  `variance-gate/` story) — never skip it even if a task looks self-contained.
- Tasks marked "Owner: Animesh" in a phase's `tasks.md`/`stories.md` are capital-allocation or spec-authoring decisions. If one is the first unchecked box, stop and flag it — do not implement it as a
  normal task.
- `phase3` task **3.3** is conditional on the `DECISIONS.md` record of task 3.2's Candidate A (Jade Lizard) vs. Candidate B (Calendar Spread) choice — read that decision before treating 3.3 as next.

## Supersession / coordination

- Blocks `backtest-eval-core/` (task **B1.1** waits on `phase1` tasks 1.3 + 1.4) and `signals-eval-core/` (waits on `backtest-eval-core` + `phase1` task 1.12) — see `TODOS.md` §Feature Backlog items
  7/9/10.
- Feeds `variance-gate/` (Phase 0.8 gate result gates `phase1` start) and is fed by `docs/plan/mvp/` (task **1.1**, which also feeds `phase1` task **1.7**'s `CSPConfig`).

## Epic done when

- **`phase1`** — every task in `phase1/tasks.md` through **1.12** (Phase 1 gate) is ticked with a real SHA.
- **`phase2`** — every task in `phase2/tasks.md` through **2.7** (Phase 2 gate) is ticked, Owner-Animesh tasks resolved by Animesh directly.
- **`phase3`** — every task in `phase3/tasks.md` through **3.6** (Phase 3 gate) is ticked, the 3.2 Candidate A/B decision recorded in `DECISIONS.md` before 3.3 is attempted.
- **`phase4`** — task **4.3** (ML overlays, only if a narrow problem has emerged) and the mechanical-documentation sub-items of **4.4** are ticked; 4.1/4.2/the strategic parts of 4.4 are resolved by
  Animesh directly, not implemented as normal tasks.
