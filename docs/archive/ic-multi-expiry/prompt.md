Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read `docs/plan/ic-multi-expiry/ic_multi_expiry_tasks.md` and find the first unchecked box assigned to you — the first `- [ ]` line tagged `[Claude]` or `[Antigravity]`. That is your **only task** for this session. Do not look at any other unchecked item. One task. Complete it fully.

**Story spec:** Read `docs/plan/ic-multi-expiry/stories/<TASK_ID>.md` for the full implementation spec, pre-baked graph context, test list, and commit message. Follow it exactly.
The pre-baked context block at the bottom of each story file contains pre-run graph query results — **skip all "Before any code" graph calls listed in the story and use those results directly** to save tokens.

**Relation to ic-e2e:** This plan supersedes the remaining ic-e2e stories (IC-E2 and IC-E4). IC-E3 (`[Claude]`) must be completed first if still unchecked — it touches `ic_nifty_v1.py` and must land before IC-M2 parameterizes that file. Do not start IC-M2 until IC-E3 is committed.

**Pre-implementation gate:** State in one sentence: which task you are implementing (ID + one-line description), which files will change, and which test file covers it. Do not write any code until this plan is stated.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first trying the graph. Order: `git log --oneline -10 <file>` → `search_graph` / `get_code_snippet` → `trace_path` → `search_code` → `bash sed -n 'N,Mp' <file>` → `Read` only if all above insufficient.

**Before writing any test helper that constructs a domain model:** run `get_code_snippet('<ModelClassName>')` to get the exact current field list. Never write model constructors from memory.

**Implementation:** Follow all rules in `CLAUDE.md` and `REVIEW.md`. Every public function needs one happy-path test and one edge/error test. No network calls in tests. Monetary fields are always `Decimal`, stored as TEXT in SQLite — never float.

**Agent routing (mandatory check):** The story file opens with `> Assigned to: Claude` or `> Assigned to: Antigravity`.
- If you are **Claude** and the story says `Antigravity` → invoke the `handoff-antigravity` skill and stop.
- If you are **Antigravity** and the story says `Claude` → stop immediately and notify the user.
- If the assignment matches you → proceed to implement.

**Test gate — blocking:** After implementation, before touching anything else, run:
`python -m pytest tests/unit/ --tb=no -q`
All tests must be green. If any fail, fix them before proceeding.

**Code-reviewer gate — blocking (before every commit):** Run the `code-reviewer` agent against `git diff HEAD`. Address any `CRITICAL` or `ERROR` findings before committing.

**Commit:** Use the commit format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it and hand it to the user to run:
```
git add <files>
git commit -m '<message>'
git log --oneline -1
```

**Verify and record:** Copy the SHA from `git log --oneline -1`. Open `docs/plan/ic-multi-expiry/ic_multi_expiry_tasks.md`, change `- [ ]` to `- [x]` on the completed line, and append `| SHA: <sha>`. Then add one line to `TODOS.md` under the session log:
`| <YYYY-MM-DD> | ic-multi-expiry <task-id> — <one-line description> — <SHA> |`

**Stop.** You are done. Do not proceed to the next unchecked item.
