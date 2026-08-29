Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read `docs/plan/options_income/options_income_tasks.md`
and find the first unchecked box — the first `- [ ]` line. That is your **only task** for this session. Do not look at any other unchecked item. One task. Complete it fully. Stop.

**Strategy spec:** `docs/plan/options_income/options_income_strategy.md` — canonical rules. All implementation must trace back to a rule there.

**Story spec:** Read the matching story in `docs/plan/options_income/options_income_stories.md` (same task ID) for the full implementation spec,
"Before any code" graph queries, test list, and commit message. Follow it exactly.

**Pre-implementation gate:** State in one sentence: which task you are implementing (ID + one-line description), which files will change,
and which test file covers it. Do not write any code until this plan is stated.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first trying the graph. Order:
`git log --oneline -10 <file>` for intent → `search_graph` / `get_code_snippet` for symbols → `trace_path` for callers →
`search_code` for grep → `bash sed -n 'N,Mp' <file>` for a specific block → `Read` only if all of the above are insufficient, and state why.

**Before writing any test helper that constructs a domain model:** run `get_code_snippet('<ModelClassName>')` to get the exact current field list. Never write model constructors from memory.

**Implementation:** Follow all rules in `CLAUDE.md` and `REVIEW.md`. Every public function needs one happy-path test and one edge/error test.
No network calls in tests. Monetary fields always `Decimal`, stored as TEXT in SQLite — never float. Every new package dir needs `__init__.py`.

**greeks-analyst gate (mandatory for S2, S3, S6):** After implementation, before code-reviewer, spawn the `greeks-analyst` agent against the changed files.
Any CRITICAL finding must be resolved before proceeding.

**Test gate — blocking:** After implementation, run:
`python -m pytest tests/unit/ --tb=no -q`
All tests must be green. Fix failures before proceeding. Do not skip.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it:
```
git add <files>
git commit -m '<message>'
git log --oneline -1
```

**Verify and record:** Copy SHA from `git log --oneline -1`. Open `docs/plan/options_income/options_income_tasks.md`, change `- [ ]` to `- [x]`, append `| SHA: <sha>`. Add one line to `TODOS.md`:
`- [YYYY-MM-DD] options_income <task-id> — <one-line description> — <SHA>`

**Stop.** Do not proceed to the next unchecked item.
