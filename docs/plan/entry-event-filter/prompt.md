Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/entry-event-filter/tasks.md` and find the first unchecked box. That is your **only
task** for this session. Do not look at any other unchecked item. One task. Complete it fully.
Stop.

**EF-0 is already checked off** — this directory's creation satisfies the original TODOS.md
DoD ("story dir + prompt.md + tasks.md, no code"). The next unchecked box (EF-1) is genuinely
new implementation work, gated on ES12 shipping first — verify that dependency before starting.

**Graph-before-Read rule:** Never call `Read` on `src/` without first using the graph. Order:
`git log` → graph query → `search_code` → `sed -n` → `Read` (state why).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
