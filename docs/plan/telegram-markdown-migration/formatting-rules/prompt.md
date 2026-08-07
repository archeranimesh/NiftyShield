Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/telegram-markdown-migration/formatting-rules/tasks.md` and find the first unchecked
box. That is your **only task** for this session. Do not look at any other unchecked item. One
task. Complete it fully. Stop.

**Depends on:** `docs/plan/telegram-markdown-migration/backbone/` must be fully complete
(all of MD-1..MD-5 checked) before starting FMT-2 — the table helpers interpolate dynamic
values and need `mdcode()`/`escape_markdown()` from `src/notifications/markdown.py`. FMT-1
(the spec doc) has no code dependency and can start earlier if useful.

**Origin:** `docs/plan/telegram-markdown-migration/README.md` — epic index. The table-builder
logic being promoted here started as `_kv_table` / `_side_by_side_kv` / `_leg_table` in
`scratch/2026-08-07_ic_eod_audit_telegram_format.py` — read that script's final version for
working reference implementations before writing the real ones; do not redesign from scratch.

**Story spec:** Read the matching task in
`docs/plan/telegram-markdown-migration/formatting-rules/stories.md` for the full spec.

**Known past bug this must not repeat:** `build_comparison_report()`
(`scripts/strategies/ic/paper_ic_monthly_comparison.py`) hand-counts a fixed 20-char label
budget for column alignment, which silently broke the first time a label
("Realized (inception)") was longer than what was counted by hand. Every width in the new
helpers must be computed from actual content (`max(len(...) for ...)`), never a literal
hand-counted constant.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft
it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
