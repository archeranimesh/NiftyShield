Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else.

**Gate check first:** confirm `docs/plan/backtest-engine/phase3/tasks.md` task **3.6** (Phase 3
gate) is ticked before picking up any 4.x task below. If it isn't, stop — do not start.

**Owner check — this matters more than usual here:** 4.1, 4.2, and (partially) 4.4 are marked
"Owner: Animesh" — these are capital-allocation and strategic decisions, not implementation
tasks, and by the time this story is reachable it's 2028+ with real multi-year live capital on
the line. If you land on 4.1 or 4.2 as the next unchecked box, stop and flag it for Animesh. Only
4.3 (ML overlays, and only if a narrow problem has actually emerged) is a normal Cowork
implementation task.

Once the gate and owner checks pass: read `docs/plan/backtest-engine/phase4/tasks.md` and find
the first unchecked box that is actually yours to do (i.e. 4.3, or a sub-item of 4.4 that's
mechanical documentation rather than a strategic call). That is your **only task** for this
session. Complete it fully. Stop.

**Story spec:** Read the matching entry in `stories.md` (same task ID) — it points you to the
exact section in `BACKTEST_PLAN_PHASE1.md` (root). That file is canonical; this dir is a thin
index only.

**4.3 scope discipline — read before writing any code:** the source spec explicitly rules out
direction prediction, strategy generation, and regime prediction, even here. If the "narrow
problem" someone describes to you sounds like any of those three, stop and say so rather than
implementing it. Each ML feature ships with its own spec, backtest, and kill criteria — same
discipline as a full strategy.

**Pre-implementation gate:** State in one sentence: which task you are implementing (ID +
one-line description), which files will change, and which test file covers it. Do not write any
code until this plan is stated.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first trying the
graph.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All tests must be green before committing. No network in tests.

**Financial logic note:** by this phase there are 3–5 live strategies with real multi-year
capital. Real `@code-reviewer` gate mandatory for any code task, no exceptions.

**Commit:** Use the format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not
draft it and hand it to the user:
```
git add <files>
git commit -m '<message>'
git log --oneline -1
```

**Verify and record:** Copy the SHA from `git log --oneline -1`. Tick the box in
`docs/plan/backtest-engine/phase4/tasks.md`, append `| SHA: <sha>`. **Also tick the matching task
in `BACKTEST_PLAN_PHASE1.md` itself.** Then add one line to `TODOS.md`'s Session Log:
`| <YYYY-MM-DD> | backtest-engine/phase4 <task-id> — <one-line description> — <SHA> |`

**Stop.** Do not proceed to the next unchecked item.
