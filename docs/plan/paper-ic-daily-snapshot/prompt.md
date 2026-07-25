Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/paper-ic-daily-snapshot/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task. Complete it
fully. Stop.

**Story spec:** Read the matching story in `docs/plan/paper-ic-daily-snapshot/stories.md` for the
full spec — problem, fix, tests required, files touched, and why this task is routed to Claude
rather than Antigravity.

**Background:** User asked for a daily P&L graph, realized P&L since inception, realized P&L for
the current calendar month, and unrealized P&L since inception, for paper-trading strategies
(triggered by a question about IC V2, `paper_ic_nifty_v2_monthly`). Investigation found
`paper_leg_snapshots` — the table designed for exactly this — has zero rows for every IC variant
and every CSP/overlay strategy. Only the three-track strategies (`paper_nifty_futures`,
`paper_nifty_proxy`, `paper_nifty_spot`) have daily history, because `paper_3track_snapshot.py` is
the only caller of `PaperStore.record_leg_snapshot()` in the codebase. `paper_ic_snapshot.py`
computes the same P&L for its Telegram report but never persists it. Backfill is explicitly out
of scope — this story is about getting clean daily data from today forward.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph. Order: `git log` → graph query (`search_graph`/`get_code_snippet`/`trace_path`) →
`search_code` → `sed -n` → `Read` (state why the graph was insufficient).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first — do not write fixtures from memory. This bit the
project before (`Direction.SHORT` / missing `entry_date` — see `CLAUDE.md` Step 4).

**Bash Output Discipline (Rule 1):** Any query against `portfolio.sqlite` must pre-aggregate —
`GROUP BY`/`SUM`/`LIMIT`, never `SELECT *` or a full-table dump. This applies to SNAP-1's
three-track data pull and to every query SNAP-4 writes.

**SNAP-1 and SNAP-3 are read-only.** Do not edit any file for either — output is a findings
section appended to `stories.md` under the heading named in the task, using `Edit`, not `Write`.

**Financial-logic gate (SNAP-2, SNAP-4):** Both persist or report real P&L. Per `CLAUDE.md`'s
AutoTrigger table, the real `@code-reviewer` subagent is mandatory before committing. Cowork
cannot spawn this project's local `.claude/agents/code-reviewer` — per the project's documented
substitution pattern (used for BUG-014, `CLAUDE.md`), apply `REVIEW.md`'s checklist directly and
state explicitly in the commit message that this is a substitution, not an equivalent automated
gate. Resolve any CRITICAL/ERROR-equivalent finding before committing.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing (SNAP-1/SNAP-3 have no tests to run — audit-only).

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it
and stop.

**Verify and record:** Tick the box in `tasks.md`, append `| SHA: <sha>` (or
`| no commit — read-only` for SNAP-1/SNAP-3). Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item, even if it looks like a natural continuation.
