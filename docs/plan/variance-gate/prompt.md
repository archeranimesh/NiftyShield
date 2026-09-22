# variance-gate — prompt

> CSP v1 Phase 0.8 deployment gate — the criteria that must be satisfied before any live capital is committed to the Cash-Secured Put strategy on Nifty 50.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The CSP v1 Nifty strategy is in paper trading. The Phase 0.8 gate defines what must be true before live capital is deployed — the gate was council-approved on 2026-05-02
(`docs/archive/council/risk/2026-05-02_variance-gate-regime-completeness.md`). This is a **decision + observation story**, not a pure implementation story. Most tasks are human checkpoints (Animesh
reviews accumulated evidence) rather than Cowork build tasks. The one pure implementation task is VG0 (spec reconciliation); VG1–VG4 are Animesh checkpoints where Cowork helps review evidence and tick
criteria.

## Scope guard

Touches `docs/strategies/csp_nifty_v1.md` (spec reconciliation + evidence sections) and this folder's own files. VG0 is docs-only — no Python changes. VG1–VG4 are observation/checkpoint tasks: they
read `paper_trades` / `paper_leg_snapshots` / `nuvama_intraday_snapshots` and record findings — they do not change strategy parameters, entry/exit rules, or `src/` code. Replay-harness build-out is
explicitly out of scope here (Phase 1, `docs/plan/replay_harness.md`).

## Session-start load hints

Full gate specification: `docs/plan/variance-gate/spec.md`. Canonical strategy spec (to be reconciled in VG0): `docs/strategies/csp_nifty_v1.md`. Council decision:
`docs/archive/council/risk/2026-05-02_variance-gate-regime-completeness.md`. Gate D (VG4) is blocked by `BACKTEST_PLAN_PHASE1.md` task 1.11 (Z-score methodology) — read that section before actioning
VG4.

## Task overview

- **VG0** — CSP v1 spec reconciliation: resolve 4 open mismatches in `csp_nifty_v1.md` (lot size, time stop, R-number naming, R4 definition). Owner: Animesh + Cowork.
- **VG1** — Tier 0.5 two-cycle operational review (strike selection, bid/ask recording, P&L reconciliation, NiftyBees collateral, R3/R4 skip logic). Owner: Animesh.
- **VG2** — Gate A (sample size) + Gate B (exit-path validation: profit-target, time-stop, delta/mark-stop). Owner: Animesh + Cowork (replay support).
- **VG3** — Gate C: regime completeness (one of high-IVR / drawdown / delta-pressure). Owner: Animesh + Cowork.
- **VG4** — Gate D: regime-matched Z-score. Owner: Cowork (computation) + Animesh (sign-off).

**Critical path:** VG0 → (parallel observation: VG1, VG2, VG3) → VG4 → Phase 1 pilot eligibility. VG0 is the only task that can be actioned right now.

## Definition of done

All of VG0–VG4 ticked in `tasks.md` with evidence references (SHA or date), the Gate Summary table in `tasks.md` shows all six criteria green, no unresolved accounting defects across the paper cycles
used as evidence, and Animesh sign-off recorded in `DECISIONS.md`.

## Perspectives not covered

This story treats the gate criteria (A–D) as fixed — it does not re-litigate whether the thresholds themselves (≥6 cycles, `|Z| ≤ 1.5`, the regime-completeness definitions) are the right bar; that was
settled at council on 2026-05-02. A statistician's perspective on the gate's actual power at small N (noted inline in VG4 as a known limitation) is not independently re-verified here.
