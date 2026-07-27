Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else.

**Gate check first:** confirm `docs/plan/backtest-engine/phase1/tasks.md` task **1.12** (Phase 1
gate) is ticked before picking up any 2.x task below. If it isn't, stop — do not start.

**Scope check second:** if you were sent here to work on swing/investment signal research (Track
A/Track B, `2.S*`/`2.I*` in the root doc), stop — that work is tracked under
`docs/plan/signals-eval-core/tasks.md`, not here. This story dir only covers the CSP-live/IC-paper
pipeline (2.1–2.7). See `tasks.md`'s "Parallel Research Tracks" note for why.

Once both checks pass: read `docs/plan/backtest-engine/phase2/tasks.md` and find the first
unchecked box among 2.1–2.7. That is your **only task** for this session. Do not batch or combine
tasks. One task. Complete it fully. Stop.

**Story spec:** Read the matching entry in `stories.md` (same task ID) — it points you to the
exact section in `BACKTEST_PLAN_PHASE1.md` (root) to read in full. That file is the canonical
spec; `tasks.md`/`stories.md` here are a thin index only.

**Owner check:** 2.2, 2.3, and 2.6 are marked "Owner: Animesh" in the source spec — these are
live-capital or spec-authoring decisions, not implementation tasks. If you land on one of these
as the first unchecked box, stop and flag it for Animesh rather than attempting it.

**Pre-implementation gate:** State in one sentence: which task you are implementing (ID +
one-line description), which files will change, and which test file covers it. Do not write any
code until this plan is stated.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first trying the
graph. Order: `git log --oneline -10 <file>` → `search_graph`/`get_code_snippet` → `trace_path` →
`search_code` → `bash sed -n 'N,Mp' <file>` → `Read` only if insufficient, and state why.

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first — never write model constructors from memory.

**Financial logic note — this entire story is live-capital-adjacent.** 2.1 (CUSUM monitoring
guarding real money), 2.4 (IC strategy execution), and 2.7's portfolio_sim (cap-aware backtester
gating Phase 3 live deployment) are all financial-logic paths. The real `@code-reviewer` gate is
mandatory for every code task in this story — state the substitution used if this surface can't
spawn it, per prior sessions in this repo.

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

**Verify and record:** Copy the SHA from `git log --oneline -1`. Tick the box in
`docs/plan/backtest-engine/phase2/tasks.md`, append `| SHA: <sha>`. **Also tick the matching task
in `BACKTEST_PLAN_PHASE1.md` itself** — that file's own checkboxes are what `2.7`'s gate reads.
Then add one line to `TODOS.md`'s Session Log:
`| <YYYY-MM-DD> | backtest-engine/phase2 <task-id> — <one-line description> — <SHA> |`

**Stop.** Do not proceed to the next unchecked item.
