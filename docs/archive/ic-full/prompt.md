Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read `docs/plan/ic-full/ic_full_tasks.md` and find the first unchecked box assigned to you — the first `- [ ]` tagged `[Claude]` or `[Antigravity]`. That is your **only task** for this session.

**Story spec:** Read `docs/plan/ic-full/stories/<TASK_ID>.md` for the full spec, pre-baked context, test list, and commit message.
Pre-baked context contains pre-run graph results — **skip graph calls listed in the story and use those results directly**.

**Supersedes:** This plan replaces both `docs/plan/ic-e2e` (remaining stories IC-E2, IC-E3, IC-E4) and `docs/plan/ic-multi-expiry` entirely. Do not pick up tasks from those plans.

**Already completed (do not re-implement):**
- ic-e2e IC-E1 — `auto_execute: bool = False` attribute + `STRATEGY_IC` constant (SHA: 17a9744).
  Note: IC-F3 will change `auto_execute` to `True` — the attribute exists, the value changes.

**Pre-implementation gate:** State in one sentence: task ID + description, files changing, test file. No code before this.

**Graph-before-Read rule:** `git log` → `search_graph` → `trace_path` → `search_code` → `sed -n` → `Read` only if all prior steps insufficient. State why if you reach `Read`.

**Before any test helper that constructs a domain model:** `get_code_snippet('<ClassName>')` first. Never from memory.

**Agent routing:**
- Story opens with `> Assigned to: Claude` or `> Assigned to: Antigravity`
- Wrong assignment → stop and hand off. Do not write any code.

**Test gate — blocking:** `python -m pytest tests/unit/ --tb=no -q` must be green before proceeding.

**Code-reviewer gate — blocking:** Run `code-reviewer` agent on `git diff HEAD`. Resolve all CRITICAL/ERROR before committing.

**Commit and verify:**
```
git add <files>
git commit -m '<message>'
git log --oneline -1
```
Tick `- [ ]` → `- [x]` in `ic_full_tasks.md`, append `| SHA: <sha>`.
Add one line to `TODOS.md`: `| <YYYY-MM-DD> | ic-full <task-id> — <description> — <SHA> |`

**Stop.** One task per session.
