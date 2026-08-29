<!-- Copy the whole `epic/` folder to docs/plan/<epic-slug>/, then copy
docs/plan/_TEMPLATE/story/ into it once per story. Delete these HTML comments. -->

# <Epic title> — prompt (router)

Central entry point for this epic. `/work` loads this file, **not** a sub-story `prompt.md`.
Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else, then follow the steps below
to find and run exactly one task.

**Origin:** `README.md` in this folder — the epic index. Read it if you have not this
session; it carries the scope decisions, the ordered story list, and the cross-cutting
constraints this router's logic depends on.

---

## Step 1 — find the next task

Story order is fixed:

1. `<story-a>/` — <one line>
2. `<story-b>/` — <one line>   (blocked by: `<story-a>` complete)
3. `<story-c>/` — <one line>   (blocked by: `<story-b>` complete)

Do not jump ahead even if a later story looks more urgent.

Open `<story-a>/tasks.md`. If it has any unchecked `- [ ]` line, the first one (top to
bottom) is your task — stop searching, go to Step 2.
Only if every box in `<story-a>/tasks.md` is checked: open `<story-b>/tasks.md`, first
unchecked line is your task. And so on.
If every sub-story `tasks.md` is fully checked, the epic is complete — say so and stop; do
not invent new work.

## Step 2 — confirm you are the right owner

The task line carries `| Owner: … | Model: … | Review: … | SHA: …`. Read it before doing
anything.

- If `Owner` does not match the agent running this session, **stop** and report: which task
  you found, what it is routed to, and that this session should not implement it.
- If `Model` names a model this session is not running, say so before proceeding.
- Note the `Review` gate now — if it names a sub-agent (`code-reviewer` / `greeks-analyst` /
  `roll-validator`), that gate is mandatory before commit per `CLAUDE.md` Agent AutoTrigger
  Rules.

## Step 3 — load the sub-story context

Read that story's own `prompt.md` for its hard constraints (test-gate command, non-fatal
contracts, coordination checks) and its `stories.md` for the task's full spec.
If the story has a `schema.md`, read it before any Store work.

## Step 4 — implement, verify, record

Follow the sub-story `prompt.md`'s protocol: implement, run the test gate, run the `Review`
gate if flagged, commit via `.claude/skills/commit/SKILL.md` (execute it, do not draft it),
set `SHA:` on the task line + tick the box, update this epic's `README.md` story-list status
column, add one line to `TODOS.md`.

**Stop.** One task per session — do not proceed to the next unchecked item in any story.
