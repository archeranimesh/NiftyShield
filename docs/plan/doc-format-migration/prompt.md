# Doc format migration — prompt (router)

Central entry point for this epic. `/work` loads this file, **not** a sub-story `prompt.md`. Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else, then follow the steps below to find and
run exactly one task.

**Origin:** `README.md` in this folder — the epic index. Read it if you have not this session; it carries the scope decisions (tiered conversion, archive exclusion, enforcement-last ordering), the
ordered story list, and the cross-cutting constraints this router's logic depends on.

---

## Step 1 — find the next task

Story order is fixed — it is the row order of the **Stories** table in this folder's `README.md`. Keep this list identical to that table:

1. `plan-folders/` — tiered batch conversion of every `docs/plan/` folder to the canonical format
2. `repo-wide-reflow/` — fill-to-≤200 every other `.md` in the repo (independent of `plan-folders`; may run in either order)
3. `enforcement/` — widen the hooks repo-wide + CI `--all` gate + scaffolding (blocked by: `plan-folders` **and** `repo-wide-reflow` both complete)

`plan-folders/` and `repo-wide-reflow/` are independent — if the first has an unchecked box, take it; if it is fully checked, move to the second. Do not start `enforcement/` until both are done.

Open `plan-folders/tasks.md`. If it has any unchecked `- [ ]` line, the first one (top to bottom) is your task — stop searching, go to Step 2. Only if every box in `plan-folders/tasks.md` is checked:
open `repo-wide-reflow/tasks.md`, first unchecked line is your task. And so on. If every sub-story `tasks.md` is fully checked, the epic is complete — say so and stop; do not invent new work.

## Step 2 — confirm you are the right owner

The task line carries `| Owner: … | Model: … | Review: … | SHA: …`. Read it before doing anything.

- If `Owner` does not match the agent running this session, **stop** and report: which task you found, what it is routed to, and that this session should not implement it.
- If `Model` names a model this session is not running, say so before proceeding.
- Note the `Review` gate now — if it names a sub-agent (`code-reviewer` / `greeks-analyst` / `roll-validator`), that gate is mandatory before commit per `CLAUDE.md` Agent AutoTrigger Rules.
  `plan-folders/` and `repo-wide-reflow/` tasks are docs-only (`Review: none`). `enforcement/` tasks touch hook scripts and CI (`Review: code-reviewer`).

## Step 3 — load the sub-story context

Read that story's own `prompt.md` for its hard constraints (the word-diff verification command, the one-commit-per-folder rule, the tier definitions) and its `stories.md` for the task's full spec —
including, for `plan-folders/`, the per-folder progress table.

## Step 4 — implement, verify, record

Follow the sub-story `prompt.md`'s protocol: implement, run the verification (`reflow_md.py --check`, the structure/checkbox hooks, `git diff --word-diff`), run the `Review` gate if flagged, commit
via `.claude/skills/commit/SKILL.md` (execute it, do not draft it), set `SHA:` on the task line + tick the box, update this epic's `README.md` story-list status column, add one line to `TODOS.md`.

**Stop.** One task per session — do not proceed to the next unchecked item in any story.
