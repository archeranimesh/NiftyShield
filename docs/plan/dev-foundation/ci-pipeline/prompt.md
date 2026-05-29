# ci-pipeline — Session Start Protocol

Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/dev-foundation/ci-pipeline/ci_tasks.md` and find the first unchecked `- [ ]`
line. That is your **only task** for this session.

**Prerequisite:** `dx-foundation` must be fully complete (all DX tasks checked off and
`pyproject.toml` + `Makefile` committed) before starting any CI task. If `make ci` does
not exist yet, stop and complete `dx-foundation` first.

**Owner:** All tasks in this story → **Antigravity**.
Claude invokes `handoff-antigravity` skill for each task. Do not implement directly.

**Story spec:** Read `ci_stories.md` (same task ID) for full spec.

**Pre-implementation gate (for Antigravity):** State task ID + files that change before
writing any file.

**No production logic changes.** If a task requires touching `src/` business logic, stop.

**Test gate:** After each task, run `python -m pytest tests/unit/ --tb=no -q`.
All existing tests must stay green.

**Commit:** Execute — do not draft.
```
git add <files>
git commit -m '<message>'
git log --oneline -1
```

**Verify and record:** Tick `ci_tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`:
`- [YYYY-MM-DD] CI <task-id> — <description> — <SHA>`

**Stop.** One task per session.
