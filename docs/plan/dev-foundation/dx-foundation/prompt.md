# dx-foundation — Session Start Protocol

Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/dev-foundation/dx-foundation/dx_tasks.md` and find the first unchecked `- [ ]`
line. That is your **only task** for this session. Do not batch. One task. Complete it fully.

**Story spec:** Read the matching story in `dx_stories.md` (same task ID) for the full
spec, files changed, and commit message. Follow it exactly.

**Pre-implementation gate:** State: task ID + one-line description + files that change.
Do not write any file until this is stated.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first trying
the graph. These tasks are config files — `Read` is permitted for existing config and
markdown files without a graph query.

**No production logic changes in this story.** If a task seems to require touching
`src/` business logic, stop and flag it.

**Owner split — mandatory:**

| Tasks | Owner | Why |
|-------|-------|-----|
| DX-1, DX-2, DX-4, DX-5, DX-6 | **Antigravity** | Mechanical config — TDD loop, multi-file, clear spec |
| DX-3 | **Claude** | Requires judgment: which modules get `--strict` first |

If you are Claude and the next unchecked task is DX-1/2/4/5/6 → invoke `handoff-antigravity`
skill and produce the structured handoff prompt. Do not write the config files yourself.

**Test gate:** Config-only tasks (DX-1/2/3/4/5/6) do not add tests. After each task, run
`python -m pytest tests/unit/ --tb=no -q` to confirm existing tests still pass (nothing broken).

**Commit:** Use format in `.claude/skills/commit/SKILL.md`. Execute — do not draft.

```
git add <files>
git commit -m '<message>'
git log --oneline -1
```

**Verify and record:** Tick `dx_tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`:
`- [YYYY-MM-DD] DX <task-id> — <description> — <SHA>`

**Stop.** One task per session.
