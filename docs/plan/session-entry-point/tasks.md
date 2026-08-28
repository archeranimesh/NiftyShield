# Session entry point — tasks

Work top-down. Docs + `.claude/` only — no code-reviewer, no test-runner.
See `prompt.md` for the skill design.

**Epic complete — all tasks shipped 2026-08-27.**

**Post-epic (2026-08-28, from `root-doc-organization` RDO-14):** `/work` keeps its two
branches. RDO-14 §4 had floated collapsing Feature/Bug into one "top N of a unified queue"
menu; Animesh decided against it — `TODOS.md` now carries two separate lists
(`## Feature Backlog`, `## Open Bugs`) and the Feature/Bug fork stays. No skill change.
This folder is archived to `docs/archive/plan/session-entry-point/` only after RDO-15
finishes using `tasks.md` here as its worked example.

- [x] **SEP-1** — Author `.claude/skills/work/SKILL.md`. | Owner: Claude | Model: claude-sonnet-5 | SHA: 08b74a4
  1. Trigger phrases: "work", "start work", "pick up a task", "/work". Front-matter + a
     one-screen body.
  2. Step A — skip-through detection (message already names a story / bug / RDO id) vs
     `AskUserQuestion` Feature / Bug.
  3. Feature branch — read `TODOS.md` "Priority-Ordered Open Work", present the first 5
     verbatim, load the picked `docs/plan/<story>/prompt.md` + `*_tasks.md` + first unchecked
     task + `CONTEXT.md`, hand to `CLAUDE.md` Step 2b.
  4. Bug branch — read `docs/bugs/task.md` + `bugs.md`, list open entries, load the picked
     entry + `task.md` lines + first unchecked + `CONTEXT.md`, hand to Step 2b.
  5. Explicit "front-end to the existing protocol, not a replacement" note so it composes with
     `task_protocol.sh`.
  Verify: invoke `/work` in a scratch session — both branches reach a loaded prompt.

- [x] **SEP-2** — `CLAUDE.md` reconciliation. | Owner: Claude | Model: claude-sonnet-5 | SHA: 774b8b9
  1. Step 1 — add a leading line: "Task-shaped session: invoke `/work` to route to
     feature / bug and load the right prompt."
  2. Remove the now-duplicated "Starting a new feature → also read `TODOS.md` + `PLANNER.md`"
     and "Working a specific story → load ONLY that story file + `CONTEXT.md` + module
     `CLAUDE.md`" lines (they live in the skill now) — or reduce each to a pointer.
  3. Quick-reference table — add a `/work` row.
  Verify: `grep -n 'work' CLAUDE.md` shows the pointer; no load-hint duplication remains.
  Done: both duplicated load-hint lines collapsed into one `/work` pointer line; leading
  `/work` block added to Step 1; Quick-reference row added.

- [x] **SEP-3** — `AGENTS.md` mirror + `md-organize` scope. | Owner: Claude | Model: claude-sonnet-5 | SHA: 4168b75
  1. Apply the SEP-2 change to `AGENTS.md` with the Antigravity adjustment (no `/work` skill
     access — state the manual equivalent: read `TODOS.md` first-5 or `docs/bugs/`, then
     follow the handoff protocol).
  2. RDO-6 (`root-doc-organization`) — add `.claude/skills/work/SKILL.md` to the `md-organize`
     re-sync scope. If RDO-6 already shipped, edit `md-organize/SKILL.md` directly.
  Verify: `AGENTS.md` and `CLAUDE.md` Step 1 read parallel; RDO-6 names the skill.
  Done: `AGENTS.md` gains a `/work` delta bullet + an Antigravity-adjusted routing block in
  Step 1 (manual `TODOS.md` first-5 / `docs/bugs/` routing → handoff protocol); the old
  "new feature" + "specific story" load-hint lines collapsed into one manual-routing pointer;
  Quick-reference row added. RDO-6 already named `.claude/skills/work/SKILL.md` in its re-sync
  scope (added by the RDO-12 triage) — no edit needed; RDO-6 itself is still unshipped.

- [x] **SEP-4** — End-to-end check + close. | Owner: Claude | Model: claude-sonnet-5 | SHA: 42eabb2
  1. One real session: `/work` → Feature → pick item 1 of the 5 → confirm the correct
     `prompt.md` + first unchecked task load and `CLAUDE.md` Step 2b begins.
  2. Repeat for the Bug branch.
  3. Update `docs/plan/README.md` status, `TODOS.md` session log, tick RDO-12 in
     `root-doc-organization/tasks.md`.
  Verify: both branches demonstrated in one session-log entry.
  Done: this session — invoked as `/work on SEP-4 in session-entry-point`. Feature branch
  demonstrated live (skip-through detection → `session-entry-point` (TODOS item 1) →
  `prompt.md` + `tasks.md` loaded → SEP-4 identified as first unchecked → `CONTEXT.md` read →
  Step 2b). Bug branch demonstrated via routing dry-run: open entries BUG-038 (first unchecked
  B038.1) + BUG-037 (B037.6); BUG-019 listed as diagnostic-only/not-actionable. RDO-12 ticked
  in `root-doc-organization/tasks.md`; `docs/plan/README.md` row flipped to ✅ Done.

## Epic done when

- [x] **SEP-1** — `/work` skill authored, both branches functional, skip-through works.
- [x] **SEP-2** — `CLAUDE.md` points at `/work`; load-hint duplication removed.
- [x] **SEP-3** — `AGENTS.md` mirrors; `md-organize` re-sync scope names the skill.
- [x] **SEP-4** — both branches demonstrated end-to-end in one session.

## After each task
Tick the box, append `| SHA: <sha>`, update `docs/plan/README.md` + `TODOS.md` session log.
