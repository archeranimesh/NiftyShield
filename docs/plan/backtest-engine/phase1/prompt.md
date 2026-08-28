Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else.

**Gate check first — this is not a normal story:** confirm the Phase 0.8 variance gate has
passed (`BACKTEST_PLAN.md` — CSP v1 paper-trading gate, criteria A–D) before picking up any task
below. If the gate has not passed, stop here — do not start any 1.x task. Check `TODOS.md`'s
`## Feature Backlog` (variance-gate story) for current gate status.

Once the gate has passed: read `docs/plan/backtest-engine/phase1/tasks.md` and find the first
unchecked box. That is your **only task** for this session. Do not look at any other unchecked
item. Do not batch or combine tasks. One task. Complete it fully. Stop.

**Story spec:** Read the matching entry in `docs/plan/backtest-engine/phase1/stories.md` (same
task ID) — it points you to the exact section in `BACKTEST_PLAN_PHASE1.md` (root) to read in
full. **`BACKTEST_PLAN_PHASE1.md` is the canonical spec** — `tasks.md`/`stories.md` here are a
thin index only. Do not implement from the one-line summary in `tasks.md` alone.

**Pre-implementation gate:** State in one sentence: which task you are implementing (ID +
one-line description), which files will change, and which test file covers it. Do not write any
code until this plan is stated.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first trying the
graph. Order: `git log --oneline -10 <file>` for intent → `search_graph`/`get_code_snippet` for
symbols → `trace_path` for callers → `search_code` for grep → `bash sed -n 'N,Mp' <file>` for a
specific block → `Read` only if all of the above are insufficient, and state why.

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first — never write model constructors from memory.

**Financial logic note:** several tasks in this story (1.4 cost model, 1.7 CSP strategy, 1.9a
integrated backtest) are financial-logic paths — the real `@code-reviewer` gate is mandatory,
even if this surface can't spawn it (state the substitution used, per prior sessions in this
repo).

**Antigravity routing (Step 3b gate):** After stating the plan, check: does this task span 3+
files with a clear non-ambiguous spec (e.g. 1.4, 1.6a, 1.9)? If yes → invoke the
`handoff-antigravity` skill and produce the structured handoff prompt. Stop — do not write any
code. If no (single/2-file, exploratory, or inline judgment required) → implement directly.

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
`docs/plan/backtest-engine/phase1/tasks.md`, change `- [ ]` to `- [x]` on the completed line, and
append `| SHA: <sha>`. **Also tick the matching task in `BACKTEST_PLAN_PHASE1.md` itself** — that
file's own checkboxes are what `1.12`'s gate checklist reads, and this story's `tasks.md` must not
be the only place the tick is recorded. Then add one line to `TODOS.md` under the Session Log:
`| <YYYY-MM-DD> | backtest-engine/phase1 <task-id> — <one-line description> — <SHA> |`

**Stop.** Do not proceed to the next unchecked item. The next session picks up from the next
unchecked box.
