Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/phase2-integrations/tasks.md` and find the first unchecked box that is not gated. That
is your **only task** for this session. Do not batch or combine tasks. One task. Complete it
fully. Stop.

**Gate check first:** PV-1 is the only ungated item — it can be picked up any time. ZK-1/OE-1/PT-1
are each gated for their own stated reason (see `stories.md`), not on Phase 1.12 itself. Confirm
the specific gate for the task you're about to pick up has actually cleared before starting —
do not assume Phase 1.12 passing unblocks all four.

**Story spec:** Read the matching entry in `docs/plan/phase2-integrations/stories.md` (same task
ID) for the full spec, prerequisites, and test requirements. Follow it exactly.

**Pre-implementation gate:** State in one sentence: which task you are implementing (ID +
one-line description), which files will change, and which test file covers it (if any — PV-1 may
not need new `src/` tests if it's a pure Cowork artifact). Do not write any code until this plan
is stated.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first trying the
graph. Order: `git log --oneline -10 <file>` for intent → `search_graph`/`get_code_snippet` for
symbols → `trace_path` for callers → `search_code` for grep → `bash sed -n 'N,Mp' <file>` for a
specific block → `Read` only if all of the above are insufficient, and state why.

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first — never write model constructors from memory.

**Implementation:** Follow all rules in `CLAUDE.md` and `REVIEW.md`. Every public function needs
one happy-path test and one edge/error test. No network calls in tests. Monetary fields are
always `Decimal`, stored as TEXT in SQLite — never float.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All tests must be green before committing. No network in tests.

**Commit:** Use the format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not
draft it and hand it to the user:
```
git add <files>
git commit -m '<message>'
git log --oneline -1
```

**Verify and record:** Copy the SHA from `git log --oneline -1`. Open
`docs/plan/phase2-integrations/tasks.md`, change `- [ ]` to `- [x]` on the completed line, and
append `| SHA: <sha>`. Then add one line to `TODOS.md` under the Session Log:
`| <YYYY-MM-DD> | phase2-integrations <task-id> — <one-line description> — <SHA> |`

**Stop.** Do not proceed to the next unchecked item. The next session picks up from the next
unchecked box.
