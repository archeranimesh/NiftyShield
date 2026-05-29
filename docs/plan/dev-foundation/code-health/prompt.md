# code-health — Session Start Protocol

Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/dev-foundation/code-health/health_tasks.md` and find the first unchecked `- [ ]`
line. That is your **only task** for this session.

**Prerequisite:** `dx-foundation` must be complete before CH-6/CH-7/CH-8 (they use
`pyproject.toml` deps). CH-1/CH-2/CH-3/CH-4/CH-5 can start independently.

**Owner split — mandatory:**

| Tasks | Owner | Why |
|-------|-------|-----|
| CH-1, CH-2 | **Claude** | Scan output requires judgment — not mechanical |
| CH-3 | **Claude** | Requires domain knowledge of trading terms |
| CH-4 | **Antigravity** | Mechanical — add `__all__` to N files |
| CH-5 | **Claude** | Requires architectural understanding |
| CH-6, CH-8 | **Antigravity** | Mechanical implementation once spec defined |
| CH-7 | **Claude** defines `Settings` model → **Antigravity** replaces `os.getenv()` calls |
| CH-9 | **Claude** designs edge cases → **Antigravity** implements `@given` tests |
| CH-10 | **Claude** | Docs synthesis |

For Antigravity tasks: Claude invokes `handoff-antigravity` skill with the full spec.

**Graph-before-Read rule applies.** CH-4 and CH-7 span many `src/` files — Antigravity
must use `search_code("os.getenv")` and `search_graph("__init__")` before reading files.

**Test gate:** `python -m pytest tests/unit/ --tb=no -q` after every task.

**Commit:** Execute — do not draft.

**Verify and record:** Tick `health_tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`:
`- [YYYY-MM-DD] CH <task-id> — <description> — <SHA>`

**Stop.** One task per session.
