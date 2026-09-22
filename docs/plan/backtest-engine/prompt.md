# Backtest engine — prompt (router)

Central entry point for this epic. `/work` loads this file, **not** a sub-story `prompt.md`. Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else, then follow the steps below to find and
run exactly one task.

**Origin:** `README.md` in this folder — the epic index. Read it if you have not this session; it carries the scope decisions, the ordered story list, and the cross-cutting constraints this router's
logic depends on.

---

## Step 1 — find the next task

Story order is fixed — it is the row order of the **Stories** table in this folder's `README.md`. Keep this list identical to that table:

1. `phase1/` — Phase 0.8 variance-gate CSP v1 paper-trading buildout
2. `phase2/` — CSP-live / IC-paper pipeline (blocked by: `phase1` task 1.12, the Phase 1 gate)
3. `phase3/` — post-Phase-2 strategy expansion (blocked by: `phase2` task 2.7, the Phase 2 gate)
4. `phase4/` — long-horizon capital allocation + ML overlays (blocked by: `phase3` task 3.6, the Phase 3 gate)

Do not jump ahead even if a later phase looks more urgent.

Open `phase1/tasks.md`. If it has any unchecked `- [ ]` line, the first one (top to bottom) is your task — stop searching, go to Step 2. Only if every box in `phase1/tasks.md` is checked: open
`phase2/tasks.md`, first unchecked line is your task. And so on. If every sub-story `tasks.md` is fully checked, the epic is complete — say so and stop; do not invent new work.

## Step 2 — confirm you are the right owner

The task line carries `| Owner: … | Model: … | Review: … | SHA: …`. Read it before doing anything.

- If `Owner` does not match the agent running this session, **stop** and report: which task you found, what it is routed to, and that this session should not implement it.
- If `Model` names a model this session is not running, say so before proceeding.
- Note the `Review` gate now — if it names a sub-agent (`code-reviewer` / `greeks-analyst` / `roll-validator`), that gate is mandatory before commit per `CLAUDE.md` Agent AutoTrigger Rules.
- `phase2`/`phase3`/`phase4` carry several tasks marked "Owner: Animesh" — capital-allocation or spec-authoring decisions, not implementation tasks. If the first unchecked box in that phase's
  `tasks.md` is one of these, stop and flag it rather than implementing it.

## Step 3 — load the sub-story context

Read that phase's own `prompt.md` for its gate checks (Phase 0.8 variance gate, prior-phase GATE task, owner checks) and its `stories.md` for the task's full spec — each entry points to the exact
section in `BACKTEST_PLAN_PHASE1.md` (root), which is the canonical spec; the phase dir's `tasks.md`/`stories.md` are a thin index only.

## Step 4 — implement, verify, record

Follow the sub-story `prompt.md`'s protocol: implement, run the test gate, run the `Review` gate if flagged, commit via `.claude/skills/commit/SKILL.md` (execute it, do not draft it), set `SHA:` on
the task line + tick the box, update this epic's `README.md` story-list status column, add one line to `TODOS.md`.

**Stop.** One task per session — do not proceed to the next unchecked item in any phase.
