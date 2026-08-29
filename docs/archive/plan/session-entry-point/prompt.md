# Session entry point — unified `/work` skill

Spun out of the 2026-08-27 workflow-suggestion triage (`root-doc-organization` RDO-12).
Read this, then work `tasks.md` top-down.

## Why this story exists

Task-shaped work in this repo splits into two shapes with separate doc trees and no common
front door:

1. **Feature implementation** — story folders under `docs/plan/<story>/` (`prompt.md` +
   `*_tasks.md` + `*_stories.md`). Next-up order lives in `TODOS.md` "Priority-Ordered
   Open Work".
2. **Bug fixing** — `docs/bugs/` (`prompt.md` + `bugs.md` registry + `task.md` checklist).

Anything else (open-ended discussion) needs no routing — it proceeds as normal conversation,
and its outcomes get filed into one of the two trees above.

Today the routing lives as scattered prose in `CLAUDE.md` Step 1–2 ("starting a new feature →
read `TODOS.md` + `PLANNER.md`", "working a specific story → load ONLY that story file"), it
says nothing about `docs/bugs/`, and it requires the operator to remember which files to
pull. There is no single command that asks "what are we doing?" and loads the right prompt.

## What this story delivers

A **manual** `/work` skill (`.claude/skills/work/SKILL.md`) — the single entry point. No
SessionStart hook (decided 2026-08-27): the operator invokes `/work` when starting a
task-shaped session.

### Skill design

**Step A — detect or ask.** If the operator's message already names a target (`fix BUG-038`,
`continue RDO-4`) → skip straight to the matching branch. Otherwise `AskUserQuestion` with
two options: **Feature** / **Bug**.

**Feature branch:**
1. Read `TODOS.md` "Priority-Ordered Open Work".
2. Present the **first 5** list items verbatim (number, title, next task, story path).
3. Operator picks one.
4. Load `docs/plan/<story>/prompt.md` + `*_tasks.md`; identify the first unchecked task.
5. Also read `CONTEXT.md`.
6. Hand off to `CLAUDE.md` Step 2b (council checkpoint) → Step 3 → normal protocol.

**Bug branch:**
1. Read `docs/bugs/task.md` + `docs/bugs/bugs.md`.
2. Present every open bug (`🔴 Open` / `🟡 Fix in progress`) — id, title, first unchecked
   sub-task.
3. Operator picks one.
4. Load that bug's `bugs.md` entry + its `task.md` lines; identify first unchecked.
5. Also read `CONTEXT.md`.
6. Hand off to `CLAUDE.md` Step 2b onward. AutoTrigger agents (greeks-analyst, roll-validator)
   fire per the table if the fix touches their surfaces.

The skill is a **front-end to the existing protocol, not a replacement** — it composes with
`task_protocol.sh` (UserPromptSubmit) and leads into `CLAUDE.md` Step 2b.

### Protocol reconciliation

`/work` becomes the documented start-of-task entry point, so:
- `CLAUDE.md` Step 1 gains one leading line pointing at `/work`; the per-work-type load hints
  ("starting a new feature → read `TODOS.md` + `PLANNER.md`", "working a specific story → load
  ONLY that story file + `CONTEXT.md` + module `CLAUDE.md`") move into the skill so there is
  one source of truth.
- `AGENTS.md` mirrors the `CLAUDE.md` change (per RDO-2 / RDO-6 re-sync rule), with the
  Antigravity adjustment (no `/work` access — state the manual equivalent).
- RDO-6's `md-organize` re-sync scope must include `.claude/skills/work/SKILL.md`.

## Scope guard

Docs + `.claude/` tooling only. No `src/` or `scripts/` change. The only new executable is
the skill markdown — no hook script this iteration (manual invocation only).

## Definition of done

- `/work` exists, offers Feature / Bug, and the skip-through detection works.
- Feature branch presents exactly the first 5 `TODOS.md` priority items and loads the chosen
  story's prompt + first unchecked task.
- Bug branch lists open `docs/bugs/` entries and loads the chosen bug + first unchecked task.
- `CLAUDE.md` + `AGENTS.md` point at `/work`; the duplicated load hints are removed, not left
  in two places.
- RDO-6 `md-organize` re-sync scope names the skill.
- One real session: `/work` → pick a feature → correct prompt loaded → protocol continues;
  repeated for the Bug branch.
