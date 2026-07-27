**This story is opportunistic, not sequential — read this before doing anything else.**

Unlike every other story in `docs/plan/`, do **not** pick an item from
`docs/plan/technical-debt/tasks.md` just because it's the next unchecked box. Each item has its
own trigger condition (stated in `tasks.md` and detailed in `stories.md`): you only touch it when
you are *already* editing the same file/module for an unrelated task. **Never a standalone
commit** — the one exception is DEBT-3, which is explicitly allowed to be its own commit once the
license decision is recorded in `DECISIONS.md` (see `stories.md`).

So the actual workflow is: whenever any other session (from any story) is about to touch
`test_bhavcopy_ingest.py`, `write_to_parquet`, `Leg` construction, `market_calendar`,
`src/models/portfolio.py`'s `is_nifty` check, `src/instruments/lot_size.py`'s `is_nifty` check, or
`daily_snapshot.py`'s dynamic dispatch — check this story's `tasks.md` first to see if a matching
DEBT item's trigger has just fired, and fold the fix into that session's commit (with its own
line in the commit message, still following normal commit-message format) rather than treating it
as separate work.

**If you were sent here directly** (i.e. told to "work on technical debt"): that's almost
certainly a mistake for every item except DEBT-3 — ask whether the intent was actually "the file
I'm about to touch for reason X happens to have an open DEBT item" instead. Do not go looking for
an unrelated file to touch just to justify picking one of these up.

**Graph-before-Read rule still applies:** `search_graph`/`get_code_snippet`/`trace_path` before
`Read` on any `src/`/`scripts/` file, same as every other story.

**Test gate — blocking:** `python -m pytest tests/unit/ --tb=no -q`. All green before committing.

**Commit:** Use the format from `.claude/skills/commit/SKILL.md`. If folded into another story's
session, the commit message's `What:` section gets an extra line for the DEBT fix; it does not
need its own separate commit unless the surrounding change is itself docs-only and the DEBT fix
is code (in which case split them per the doc-vs-code commit-scope rule in `CLAUDE.md` Step 5c).

**Verify and record:** Tick the item in `docs/plan/technical-debt/tasks.md`, append
`| SHA: <sha>`, and add one line to `TODOS.md`'s Session Log noting which host session the fix
was folded into.
