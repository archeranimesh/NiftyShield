Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read `docs/plan/paper-exit-codification/tasks.md` and find the first unchecked box. That is your **only task** for this session. Do not look at any other unchecked item. One task. Complete it fully. Stop.

**Council rulings:**
- q11 exit philosophy: `docs/archive/council/strategy/2026-06-26_paper-trade-exit-philosophy.md` Stage 3
- q12 monitor observability: `docs/archive/council/data_architecture/2026-06-26_strategy-monitor-watchlist-design.md` Stage 3

**Story spec:** Read the matching story in `docs/plan/paper-exit-codification/stories.md` for the full spec.

**Graph-before-Read rule:** Never call `Read` on `src/` without first using the graph. Order: `git log` → graph query → `search_code` → `sed -n` → `Read` (state why).

**Before writing any test helper that constructs a domain model:** run `get_code_snippet('<ModelClassName>')` first.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
