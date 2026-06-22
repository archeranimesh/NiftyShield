Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read `docs/plan/ic-e2e/ic_e2e_tasks.md` and find the first unchecked box — the first `- [ ]` line. That is your **only task** for this session. Do not look at any other unchecked item. Do not attempt to batch or combine tasks. One task. Complete it fully. Move on to nothing else.

**Story spec:** Read `docs/plan/ic-e2e/stories/<TASK_ID>.md` for the full implementation spec, pre-baked graph context, test list, and commit message. Follow it exactly.
The pre-baked context block at the bottom of each story file contains pre-run graph query results — **skip all "Before any code" graph calls listed in the story and use those results directly** to save tokens.

**Pre-implementation gate:** State in one sentence: which task you are implementing (ID + one-line description), which files will change, and which test file covers it. Do not write any code until this plan is stated.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first trying the graph. Order: `git log --oneline -10 <file>` for intent → `search_graph` / `get_code_snippet` for symbols → `trace_path` for callers → `search_code` for grep → `bash sed -n 'N,Mp' <file>` for a specific block → `Read` only if all of the above are insufficient, and state why.

**Before writing any test helper that constructs a domain model:** run `get_code_snippet('<ModelClassName>')` to get the exact current field list. Never write model constructors from memory.

**Implementation:** Follow all rules in `CLAUDE.md` and `REVIEW.md`. Every public function needs one happy-path test and one edge/error test. No network calls in tests. Monetary fields are always `Decimal`, stored as TEXT in SQLite — never float.

**Agent routing (mandatory check):** The story file opens with `> Assigned to: Claude` or `> Assigned to: Antigravity`.
- If you are **Claude** and the story says `Antigravity` → invoke the `handoff-antigravity` skill and stop. Do not write any code.
- If you are **Antigravity** and the story says `Claude` → stop immediately and notify the user that this task is reserved for Claude.
- If the assignment matches you → proceed to implement.

**Test gate — blocking:** After implementation, before touching anything else, run:
`python -m pytest tests/unit/ --tb=no -q`
All tests must be green. If any fail, fix them before proceeding. Do not skip this step.

**Code-reviewer gate — blocking (before every commit):** Run the `code-reviewer` agent against `git diff HEAD`. Address any `CRITICAL` or `ERROR` findings before committing. `WARNING` may be deferred with a documented reason in the commit message.

**Commit:** Use the commit format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it and hand it to the user to run. The commit must land:
```
git add <files>
git commit -m '<message>'
git log --oneline -1
```

**Verify and record:** Copy the SHA from `git log --oneline -1`. Open `docs/plan/ic-e2e/ic_e2e_tasks.md`, change `- [ ]` to `- [x]` on the completed line, and append `| SHA: <sha>`. Then add one line to `TODOS.md` under the session log:
`| <YYYY-MM-DD> | ic-e2e <task-id> — <one-line description> — <SHA> |`

**Stop.** You are done. Do not proceed to the next unchecked item. The next session will pick up from the next unchecked box.
