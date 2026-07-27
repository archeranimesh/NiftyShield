Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else.

**Gate check first:** confirm `docs/plan/backtest-engine/phase2/tasks.md` task **2.7** (Phase 2
gate) is ticked before picking up any 3.x task below. If it isn't, stop — do not start.

**Dependency check second:** 3.3 only applies if 3.2 chose Candidate B (Calendar Spread). Check
`DECISIONS.md` for the 3.2 decision before treating 3.3 as the next task — if Candidate A (Jade
Lizard) was chosen, skip 3.3 and go to 3.4 once 3.2's Jade Lizard implementation work (folded
into 3.2 itself, since it reuses IC infrastructure) is done.

Once checks pass: read `docs/plan/backtest-engine/phase3/tasks.md` and find the first unchecked
box. That is your **only task** for this session. Do not batch or combine tasks. One task.
Complete it fully. Stop.

**Story spec:** Read the matching entry in `stories.md` (same task ID) — it points you to the
exact section in `BACKTEST_PLAN_PHASE1.md` (root). That file is canonical; this dir is a thin
index only.

**Owner check:** 3.1 and 3.2 are marked "Owner: Animesh" — live-capital or spec-authoring
decisions, not implementation tasks. If you land on one as the first unchecked box, stop and flag
it for Animesh rather than attempting it.

**Pre-implementation gate:** State in one sentence: which task you are implementing (ID +
one-line description), which files will change, and which test file covers it. Do not write any
code until this plan is stated.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first trying the
graph. Order: `git log` → `search_graph`/`get_code_snippet` → `trace_path` → `search_code` →
`sed -n` → `Read` only if insufficient, and state why.

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first.

**3.5 consolidation check — mandatory before writing code:** run `search_graph("RegimeTagger")`
and `search_graph("regime")` first. If `src/strategy/regime.py` already exists (from Track A /
`signals-eval-core` SE2.2), do not create a parallel `src/regime/` module without first stating
whether you're extending the existing one or explicitly justifying a separate module — see the
consolidation note in `stories.md`.

**Financial logic note:** this entire story is live-capital-adjacent (IC live deployment, third
strategy live path, portfolio drawdown kill zone). Real `@code-reviewer` gate mandatory for every
code task — state the substitution used if this surface can't spawn it.

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
`docs/plan/backtest-engine/phase3/tasks.md`, append `| SHA: <sha>`. **Also tick the matching task
in `BACKTEST_PLAN_PHASE1.md` itself** — that file's own checkboxes are what `3.6`'s gate reads.
Then add one line to `TODOS.md`'s Session Log:
`| <YYYY-MM-DD> | backtest-engine/phase3 <task-id> — <one-line description> — <SHA> |`

**Stop.** Do not proceed to the next unchecked item.
