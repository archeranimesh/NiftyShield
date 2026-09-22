# Technical Debt — prompt

> Track opportunistic technical-debt fixes and standalone-actionable verification items; fold each into an unrelated session once its trigger condition fires, rather than scheduling it.

**This story is opportunistic, not sequential — read this before doing anything else.**

Unlike every other story in `docs/plan/`, do **not** pick an item from `docs/plan/technical-debt/tasks.md` just because it's the next unchecked box. Each item has its own trigger condition (stated in
`tasks.md` and detailed in `stories.md`): you only touch it when you are *already* editing the same file/module for an unrelated task. **Never a standalone commit** — the exceptions are DEBT-3 (its
own commit once the license decision is recorded in `DECISIONS.md`, see `stories.md`) and the `DEBT-8`+ `standalone-actionable` block (proactive verification work, not opportunistic cleanup — also
allowed its own commit).

So the actual workflow is: whenever any other session (from any story) is about to touch `test_bhavcopy_ingest.py`, `write_to_parquet`, `Leg` construction, `market_calendar`,
`src/models/portfolio.py`'s `is_nifty` check, `src/instruments/lot_size.py`'s `is_nifty` check, or `daily_snapshot.py`'s dynamic dispatch — check this story's `tasks.md` first to see if a matching
DEBT item's trigger has just fired, and fold the fix into that session's commit (with its own line in the commit message, still following normal commit-message format) rather than treating it as
separate work.

**If you were sent here directly** (i.e. told to "work on technical debt"): that's almost certainly a mistake for every item except DEBT-3 or an open `standalone-actionable` item — ask whether the
intent was actually "the file I'm about to touch for reason X happens to have an open DEBT item" instead. Do not go looking for an unrelated file to touch just to justify picking one of these up.

**Graph-before-Read rule still applies:** `search_graph`/`get_code_snippet`/`trace_path` before `Read` on any `src/`/`scripts/` file, same as every other story.

**Test gate — blocking:** `python -m pytest tests/unit/ --tb=no -q`. All green before committing.

**Commit:** Use the format from `.claude/skills/commit/SKILL.md`. If folded into another story's session, the commit message's `What:` section gets an extra line for the DEBT fix; it does not need its
own separate commit unless the surrounding change is itself docs-only and the DEBT fix is code (in which case split them per the doc-vs-code commit-scope rule in `CLAUDE.md` Step 5c).

**Verify and record:** Tick the item in `docs/plan/technical-debt/tasks.md`, append `| SHA: <sha>`, and add one line to `TODOS.md`'s Session Log noting which host session the fix was folded into.

## Why this story exists

This folder is a holding pen for technical debt discovered mid-session on unrelated work, plus (from `session-close` Step 4b) `suggestions.md` slugs that cross Count 5 and get escalated into a
one-time verification item. Filing debt here instead of fixing it inline keeps the discovering session's diff scoped to its own task, while still guaranteeing the debt gets picked up the next time the
same file/module is touched — rather than being fixed ad hoc (bloating an unrelated commit) or forgotten entirely.

## Scope guard

Docs/tooling-only by itself: this folder never gets a standalone `src/`/`scripts/` change except DEBT-3 (once unblocked) and open `standalone-actionable` items (`DEBT-14`, `DEBT-16`, `DEBT-17`,
`DEBT-18`), which may touch `.claude/hooks/` or `scripts/dev/`. Every other item's actual code fix (in `test_bhavcopy_ingest.py`, `write_to_parquet`, `Leg`/`market_calendar`, `is_nifty` call sites, or
`daily_snapshot.py`) happens inside another story's session, not this one — this story only tracks the trigger and records the resulting SHA.

## Session-start load hints

`DECISIONS.md` — required reading before touching DEBT-3 (license decision) or recording the outcome of any `standalone-actionable` verification. No module `CLAUDE.md`, `REFERENCES.md`, or
`BACKTEST_PLAN.md` load applies to this folder itself; the *fix* session for a given DEBT item loads whatever its own file/module normally requires.

## Task overview

- **DEBT-3** — license header sweep, blocked on Animesh's license decision.
- **DEBT-5** — add append-path test coverage for `write_to_parquet`'s merge branch.
- **DEBT-6a** — move hardcoded expiry whitelist from `Leg` to `market_calendar` YAML.
- **DEBT-6b** — backfill missing 2017–2025 holiday YAML datasets.
- **DEBT-6c** — consolidate the two ad-hoc `is_nifty` denylist checks into one predicate.
- **DEBT-7** — replace `daily_snapshot.py` dynamic dispatch with an explicit registry.
- **DEBT-8..DEBT-18** — `standalone-actionable` verification of escalated `suggestions.md` hook remediations (see `stories.md` for per-item detail and current status).

## Definition of done

This story has no closing state — it is an actively-fed opportunistic backlog, not a sequence with a completion bar. Each item is "done" independently when its trigger fires, the fix lands in the host
session's commit (or its own commit for DEBT-3 / `standalone-actionable` items), and `tasks.md` + `TODOS.md`'s Session Log are updated per "Verify and record" above.

## Perspectives not covered

Whether items sitting unfixed for a long time (e.g. DEBT-6b, blocking `backtest-engine/phase1` pre-2026 `Leg` construction) should be promoted out of "opportunistic" into a scheduled story once a real
blocking dependency appears, rather than waiting indefinitely for their trigger.
