Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/telegram-ic-comparison-formatting/tasks.md` and find the first unchecked box. That is
your **only task** for this session. Do not look at any other unchecked item. One task. Complete
it fully. Stop.

**Origin:** 2026-08-07 Cowork session. The "IC Monthly Comparison" Telegram message
(`build_comparison_report()`, `scripts/strategies/ic/paper_ic_monthly_comparison.py`) rendered
misaligned in the real Telegram app — confirmed live via
`scratch/2026-08-07_telegram_ic_comparison_format_repro.py` (real sends to the configured chat).
Root cause: hand-counted literal-space column widths that break silently once a label grows past
what was counted by hand at write time (reproduced with `"Realized (inception)"` /
`"Unrealized(inception)"` colliding into the value column). TGFMT-1..3 fix that report directly
and add new fields (approved format is in `stories.md`'s header). **TGFMT-3 was revised same-day**
after the story was first drafted: it now adds both `Bkd (M)`/`Bkd (I)` (realized) and `Flt (M)`/
`Flt (I)` (unrealized) splits — `Flt (M)` requires a real new month-start-delta calculation
(`_get_unrealized_pnl_month_change()`), it is not a relabeled copy of `Flt (I)`. Read TGFMT-3's
full spec in `stories.md` before starting it; do not implement from the task-list one-liner alone.
TGFMT-4 onward extend the fix repo-wide: a survey of every `notifier.send(...)` call site found
the same hand-counted-width bug independently reproduced in 6 other message builders — TGFMT-4
extracts a shared `format_table()` helper, TGFMT-5/6/7 retrofit it to those sites, TGFMT-8/9 close
docs.

**Story spec:** Read the matching story in `docs/plan/telegram-ic-comparison-formatting/stories.md`
for the full spec, including the survey table under "Scope extension" if you're on TGFMT-4 or later.

**Hard sequencing constraint — do not violate:** TGFMT-4 (shared helper extraction) must not start
until TGFMT-1, TGFMT-2, and TGFMT-3 are all checked off. TGFMT-4 refactors TGFMT-1's already-landed
fix into a reusable helper — running it earlier means implementing the same logic twice and
reconciling them later. If you land on TGFMT-4's task and TGFMT-1..3 aren't all checked, stop and
say so instead of proceeding out of order.

**Scope boundary — do not touch prose-only messages:** the survey explicitly found these sites
are plain prose (no column alignment attempted) and are out of scope — do not "fix" them, there
is nothing broken there: `src/strategy/collar_overlay_v1.py`, `cc_overlay_v1.py`, `pp_overlay_v1.py`
(`_send_close_notification`), `scripts/strategies/three_track/paper_3track_roll.py`,
`src/strategy/overlay_closer.py`, `scripts/position_health_check.py`, `scripts/healthcheck.py`,
`scripts/strategies/ic/paper_ic_entry_v2.py`.

**Financial-logic gate:** TGFMT-3 and TGFMT-6 touch real P&L reporting / a capital-affecting close
notification. Per root `CLAUDE.md`'s AutoTrigger table, the real `@code-reviewer` gate is
mandatory before commit. Cowork cannot spawn the local `.claude/agents/code-reviewer` subagent —
apply `REVIEW.md`'s checklist directly instead, and state explicitly in the commit message that
this is a documented substitution, not an equivalent automated gate (same pattern used for
BUG-014 and the `paper-ic-daily-snapshot` story). TGFMT-1, TGFMT-2, TGFMT-4, TGFMT-5, TGFMT-7 are
formatting-only (no financial calculation changes) — no gate.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph. Order: `git log` → `search_graph`/`get_code_snippet` → `search_code` → `sed -n` → `Read`
(state why the graph was insufficient).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first — do not write `ICMonthlyStats` or
`paper_nav_snapshots` row fixtures from memory; confirm current field names against the actual
dataclass/query functions first.

**Bash output discipline:** any diagnostic query against `paper_nav_snapshots` or similar tables
(e.g. while building TGFMT-3's inception-P&L test fixtures) must pre-aggregate — named columns +
`LIMIT`, never `SELECT *` on a full table dump. See root `CLAUDE.md` Rule 1.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft
it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
