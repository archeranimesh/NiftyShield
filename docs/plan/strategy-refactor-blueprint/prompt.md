
# Strategy Module Refactor & AI-Collaboration Blueprint — prompt

> Capture the 2026-09-26 discussion on `src/strategy/`'s size problem and turn it into a durable, multi-session plan for refactoring live-trading strategy code safely, using this repo's existing
> Claude / Antigravity / LLM-council division of labor as the execution model.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

`src/strategy/` is 14,255 LOC across 25 files — larger than `src/paper/` (5,256), `src/portfolio/` (2,315) and `src/signals/` (2,148) combined. Two files dominate: `ic_nifty_v2.py` (2,935 lines) and
`ic_nifty_v1.py` (1,409 lines) — together ~30% of the package, 3–6x the next-largest file (`csp_nifty_v1.py`, 921 lines). No existing `technical-debt/` `DEBT-*` item tracks this — it is a new finding
from a 2026-09-26 discussion session, not a rediscovery of queued work.

This code drives live paper-trading positions on an ongoing basis (`ic_nifty_v1`/`v2` cycles managed by `StrategyMonitor` at 30s cadence). A conventional refactor is unsafe here: there is no room to
"clean up while we're in there" without risking a live position's entry/roll/close decision changing silently. The point of this story is to think through *how* to decompose this safely —
characterize-then-extract, golden-test-gated, one mechanical step per commit — before any code is touched, and to record that thinking so it survives across the several future sessions this will take.

The secondary goal (per Animesh, 2026-09-26): use this as the concrete case study for a broader blueprint on how Claude, Antigravity, and the LLM council should divide labor on this kind of
load-bearing refactor in a long-running production codebase — something to generalize into `protocol-reference` §3 once proven out here, not something invented in the abstract.

## Scope guard

This story is **planning and discussion only** until a task explicitly says otherwise. No `src/strategy/` file is edited under this story. When a task graduates to actual extraction work, it spins off
its own story (or epic sub-story, if `ic_nifty_v1`+`v2` end up needing separately sequenced tracks) — this file only tracks the decision trail and hands off cleanly at that point.

**Standing instruction (Animesh, 2026-09-27):** this story is expected to run across several future sessions as pure discussion — extending `tasks.md`/`stories.md` with new findings, open questions,
and decisions as they come up. Do not implement BP-1..BP-5 (or any task added later) on the strength of a session simply reaching them in sequence; each still needs its own explicit go-ahead. Planning
is not complete — and no task under this story starts real work — until Animesh says so.

## Session-start load hints

- `docs/plan/technical-debt/tasks.md` — confirm no `DEBT-*` has since been filed for this (checked clean on 2026-09-26; recheck if time has passed).
- `docs/archive/plan/full-repo-review-followups/paper-pnl-golden-tests/` — existing P3 story (⬜ not started) that is the direct prerequisite safety net; BP-2 below extends its scope rather than
  duplicating it.
- `docs/council/README.md` + `protocol-reference` §1 — the council protocol this story's BP-3 will invoke.
- `CONTEXT_TREE.md` §`src/strategy/` — current per-file module descriptions, to re-check against `wc -l src/strategy/*.py` for drift before resuming.
- `.claude/skills/md-organize/SKILL.md` — already covers most of the *docs*-side findings from this discussion (TODOS.md archival, DECISIONS.md semantic roll, line-style enforcement); BP-1 is "run
  it," not "design it."

## Task overview

- **BP-1** — Run `/md-organize` to resolve the doc-growth drift flagged in discussion (`TODOS.md` 949 lines, `DECISIONS.md` 1,140 lines regrown since its last split) — confirms whether it's actually
  stale or was a false alarm.
- **BP-2** — Extend `paper-pnl-golden-tests/` scope to cover `ic_nifty_v1`/`v2` entry/roll/close decision points, not just `PaperTracker` P&L math — this is the safety net every later step depends on.
- **BP-3** — Draft and run the council question on the `ic_nifty_v1`/`v2` decomposition boundary (shared helpers vs. shared base class) — this is a genuine three-condition Step 2b trigger
  (load-bearing, two defensible approaches, spans engineering + risk/greeks disciplines).
- **BP-4** — Once BP-3 rules, write the file-by-file decomposition plan (which blocks move where, in what commit order) as this story's `plan.md` — no code yet.
- **BP-5** — Draft the generalized AI-collaboration blueprint section (Claude / Antigravity / council routing for this class of "safe refactor of live-trading code") for `protocol-reference` §3, once
  BP-2–BP-4 have proven the approach out in practice on one file.

BP-5 explicitly waits until there's a real result to generalize from — do not write the blueprint before the case study exists.

## Definition of done

This story's own scope is "the plan exists and is council-ruled and golden-test-backed" — it does **not** include the actual `ic_nifty_v1`/`v2` file split (that ships as a separate story/epic BP-4
hands off to). Done when: BP-1–BP-5 are all ticked, the decomposition `plan.md` is council-approved, and the extraction work has its own `docs/plan/` story/epic scaffolded and linked from here.

## Perspectives not covered

- **Quant/risk sign-off on golden-test tolerance bands** — BP-2's fixture-diff approach needs a numeric tolerance (float rounding, timestamp jitter) that hasn't been decided; likely folds into the
  same council question as `greeks-parity-validation/`'s tolerance-band decision (FR-7 row 6).
- **Live cutover timing** — this story doesn't address *when* in the trading calendar it's safe to land an extraction commit (avoiding DTE/roll windows) beyond naming the constraint; a concrete "safe
  commit windows" calendar check is not designed here.
- **Antigravity's actual capability on this class of task** — BP-5 assumes Antigravity can execute a council-ruled, golden-test-gated mechanical extraction, but that's untested; the routing table in
  `protocol-reference` §3 may need revision based on how BP-4's plan actually executes.
