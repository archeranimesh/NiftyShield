Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/full-repo-review-followups/logging-migration-completion/tasks.md` and find the first unchecked box.
That is the only task for this session.

**This story is routed to Antigravity (see "Surface & Model" below for why).** Per CLAUDE.md
Step 3b: do not write any code yourself. Invoke the `handoff-antigravity` skill now and
produce the structured handoff prompt containing the four mandatory elements
(`ai_collaboration_plan.md` §4):
1. **Reading list** — explicit `view_file` paths, `CONTEXT.md` mandatory plus this story's
   `stories.md`.
2. **Objective** — one sentence, drawn from the first unchecked box in `tasks.md`.
3. **Pointers** — explicit file paths / graph queries from this story's `stories.md`. Do not
   rely on Antigravity to discover scope on its own.
4. **Boundaries** — Only the `logging.getLogger(__name__)` → `structlog.get_logger(__name__)` substitution and the missing `setup_logging()` calls — do not refactor surrounding logic, do not change log message content or event names, do not touch files outside the listed 21 `src/` + 24 `scripts/` files.

Then stop. Do not proceed to implementation.

**When Antigravity returns its Phase Completion Output:** verify `files_changed` against
`git diff --name-only HEAD~1`, `tests_passing` against `pytest --tb=no -q`'s summary line, and
— the load-bearing check — that `commit_sha` matches `git log --oneline -1`. If all three
check out, tick `tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`, stop. If
verification fails, open a fix session with the failure details per Step 3b — if the fix
needs the `code-reviewer`/`test-runner` AutoTrigger gates, run those yourself in Claude Code
rather than re-handing to Antigravity (FR-1 F-C1: Antigravity cannot spawn those subagents).

**Origin:** Spawned from `docs/plan/full-repo-review/findings/FR-7_synthesis.md` (Chairman
Synthesis), FR-7 row 7 (CRITICAL) — FR-4 §1. Independently re-verified against the live repo before this story was
created — see FR-9's commit message for the verification method.

Confirmed: 21 files under `src/` use bare `logging.getLogger(__name__)` instead of `structlog.get_logger(__name__)` (`src/paper/track_snapshot.py`, `src/paper/overlay_selector.py`, `src/paper/tracker.py`, `src/mf/nav_fetcher.py`, `src/mf/tracker.py`, `src/models/portfolio.py`, `src/backtest/bhavcopy_ingest.py`, `src/backtest/bhavcopy_loader.py`, `src/backtest/vix_ingest.py`, `src/portfolio/service.py`, `src/portfolio/tracker.py`, `src/nuvama/store.py`, `src/nuvama/reader.py`, `src/nuvama/options_reader.py`, `src/dhan/reader.py`, `src/risk/delta_tracker.py`, `src/client/mock_client.py`, `src/market_calendar/holidays.py`, `src/notifications/telegram.py`, `src/notifications/telegram_gateway.py`, `src/strategy/exit_signals.py`), and 24 of 55 `scripts/` entrypoints never call `setup_logging()`. LOGGING.md's mandatory rules were elevated to canonical by CLAUDE.md precisely because of the BUG-010 failure class (six incompatible log formats found in `logs/` before the standard was written down) — this is that same failure class, uncorrected, at scale.

**Surface & Model: Antigravity (handoff via `handoff-antigravity`); Claude Code / Sonnet for the review half.** FR-7's own sequencing already named this the Antigravity candidate: many files (21 `src/` + 24 `scripts/`), zero design ambiguity, and a pre-commit hook (`no-script-main-logger`, to be extended) gives a hard machine-checkable verification signal — exactly the shape Step 3b describes.

**Story spec:** Read the matching story in `docs/plan/full-repo-review-followups/logging-migration-completion/stories.md` for the full spec.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing.

**Financial logic commit — real `@code-reviewer` subagent mandatory** per CLAUDE.md's Agent AutoTrigger Rules (this touches P&L / Decimal / broker-adjacent paths). Resolve any CRITICAL/ERROR finding before committing.

**Commit:** Antigravity executes the commit as part of its own protocol (per
`ai_collaboration_plan.md`) — Claude does not draft or run a separate commit for this story.

**Stop.** Do not proceed to the next unchecked item.
