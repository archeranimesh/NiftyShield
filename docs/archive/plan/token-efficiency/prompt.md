# Token Efficiency — prompt (router)

Central entry point for this epic. `/work` loads this file, **not** a sub-story `prompt.md`.
Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else, then follow the steps below
to find and run exactly one task.

**Origin:** `README.md` in this folder — the epic index. Read it if you have not this
session; it carries the scope decisions (confirmed with Animesh 2026-09-01), the ordered
story list, and the cross-cutting constraint every task must honour — **each fix quotes a
real before/after token number from `measurement/`'s tool.**

---

## Step 1 — find the next task

Story order:

1. `measurement/` — `token_audit.py` + the baseline. Depends on: nothing.
2. `fixed-overhead/` — resident `CLAUDE.md`, module `CLAUDE.md` files, `session-close`,
   MCP result bloat. Depends on: `measurement/` complete.
3. `suggestions-sweep/` — cluster + fix/enforce/accept every `suggestions.md` row; make
   Step 4b self-draining. Depends on: `measurement/` complete.

`fixed-overhead/` and `suggestions-sweep/` do not depend on each other. Once every
`measurement/tasks.md` box is checked, a session may take the first unchecked task in
**either** of the other two — but coordinate first if parallel sessions are running this
epic, so two do not claim the same task.

Open `measurement/tasks.md`. First unchecked `- [ ]` (top to bottom) is your task — stop
searching, go to Step 2. Only if every box there is checked: `fixed-overhead/tasks.md`, then
`suggestions-sweep/tasks.md`. If all three are fully checked, the epic is complete — say so
and stop; do not invent new work.

## Step 2 — confirm you are the right owner

The task line carries `| Owner: … | Model: … | Review: … | SHA: …`. Read it first.

- If `Owner` does not match the agent running this session, **stop** and report which task
  you found and what it is routed to.
- If `Model` names a model this session is not running, say so before proceeding.
- Note the `Review` gate — where it names `code-reviewer`, that AutoTrigger is mandatory
  before commit per `CLAUDE.md`. The `.py` tasks in this epic (the audit tool, the new
  hooks, `commit_preflight.py`, any MCP wrapper) all carry it; the doc/skill/config-only
  tasks are `Review: none`.

## Step 3 — load the sub-story context

Read that story's own `prompt.md` for its hard constraints (test-gate command, the
measured-delta requirement, which files are in and out of bounds) and its `stories.md` for
the task's full spec. No story in this epic has a `schema.md` — none touch DB schema.

## Step 4 — implement, verify, record

Follow the sub-story `prompt.md`'s protocol: implement, run the test gate, run the `Review`
gate if flagged, commit via `.claude/skills/commit/SKILL.md` (execute it, do not draft it),
set `SHA:` on the task line + tick the box, update this epic's `README.md` **Stories** table
status column, add one line to `TODOS.md` Session Log. For `fixed-overhead/` and
`suggestions-sweep/` tasks, the As-built paragraph in that story's `stories.md` must record
the measured token delta.

**Stop.** One task per session — do not proceed to the next unchecked item in any story.
