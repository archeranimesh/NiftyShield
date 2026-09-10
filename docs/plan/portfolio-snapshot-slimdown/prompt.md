# Portfolio snapshot slimdown — prompt (router)

Central entry point for this epic. `/work` loads this file, **not** a sub-story `prompt.md`.
Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else, then follow the steps below
to find and run exactly one task.

**Origin:** `README.md` in this folder — the epic index. Read it if you have not this
session; it carries the scope decisions (Finideas full removal + hard delete option A; Dhan
message-only, integration kept wired; fixed order), the ordered story list, and the
cross-cutting constraints (both sub-stories rework the same two functions, snapshot must
render with one source left, both formatter paths change together).

---

## Step 1 — find the next task

Story order is fixed — it is the row order of the **Stories** table in this folder's
`README.md`, and it is a hard dependency (both stories edit `_build_portfolio_summary` +
`_format_combined_summary`, so they must not be interleaved):

1. `finideas-decommission/` — remove the Finideas strategy layer + snapshot terms + DB rows (FD-1..7)
2. `dhan-holdings-removal/` — remove Dhan holdings / P&L / options block from the snapshot (DHR-1..4) (blocked by: `finideas-decommission` complete)

Open `finideas-decommission/tasks.md`. If it has any unchecked `- [ ]` line, the first one
(top to bottom) is your task — stop searching, go to Step 2. Only if every box there is
checked: open `dhan-holdings-removal/tasks.md`, first unchecked line is your task. If every
sub-story `tasks.md` is fully checked, the epic is complete — say so and stop; do not invent
new work.

## Step 2 — confirm you are the right owner

The task line carries `| Owner: … | Model: … | Review: … | SHA: …`. Read it before doing
anything.

- If `Owner` does not match the agent running this session, **stop** and report: which task
  you found, what it is routed to, and that this session should not implement it. (FD-1 is
  `Owner: Animesh` — the pre-delete broker/DB audit.)
- If `Model` names a model this session is not running, say so before proceeding.
- Note the `Review` gate now — the code tasks carry `code-reviewer` (financial-logic paths:
  P&L, Decimal, `total_*` recompute); the docs-close tasks are `Review: none`.

## Step 3 — load the sub-story context

Read that story's own `prompt.md` for its hard constraints (Finideas: the strategy-layer
removal + the option-A delete; Dhan: the scope guard keeping `src/auth/dhan_verify` +
`src/dhan/` out of bounds) and its `stories.md` for the task's full spec. Neither sub-story
has a `schema.md`.

## Step 4 — implement, verify, record

Follow the sub-story `prompt.md`'s protocol: implement, run the test gate, run the `Review`
gate if flagged, commit via `.claude/skills/commit/SKILL.md` (execute it, do not draft it),
set `SHA:` on the task line + tick the box, flip this sub-story's row in this folder's
`README.md` **Stories** table (⬜ → 🔄 → ✅ with the closing SHA), add one line to `TODOS.md`
Session Log.

**Epic close (DHR-4 only):** the last sub-story's docs-close task archives the *whole epic*,
per `docs/plan/README.md` §Conventions *Completion → archive* — `git mv
docs/plan/portfolio-snapshot-slimdown docs/archive/plan/portfolio-snapshot-slimdown`,
collapse the `docs/plan/README.md` epic entry to a one-line pointer, move the `TODOS.md`
Feature Backlog line to `docs/archive/TODOS_ARCHIVE.md`. No earlier task archives anything.

**Stop.** One task per session — do not proceed to the next unchecked item in any story.
