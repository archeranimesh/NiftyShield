Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/full-repo-review-followups/logging-migration-completion/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task.
Complete it fully. Stop.

**Origin:** Spawned from `docs/plan/full-repo-review/findings/FR-7_synthesis.md` (Chairman
Synthesis), FR-7 row 7 (CRITICAL) — FR-4 §1. Independently re-verified against the live repo before this story was
created — see FR-9's commit message for the verification method.

Confirmed: 21 files under `src/` use bare `logging.getLogger(__name__)` instead of `structlog.get_logger(__name__)` (`src/paper/track_snapshot.py`, `src/paper/overlay_selector.py`, `src/paper/tracker.py`, `src/mf/nav_fetcher.py`, `src/mf/tracker.py`, `src/models/portfolio.py`, `src/backtest/bhavcopy_ingest.py`, `src/backtest/bhavcopy_loader.py`, `src/backtest/vix_ingest.py`, `src/portfolio/service.py`, `src/portfolio/tracker.py`, `src/nuvama/store.py`, `src/nuvama/reader.py`, `src/nuvama/options_reader.py`, `src/dhan/reader.py`, `src/risk/delta_tracker.py`, `src/client/mock_client.py`, `src/market_calendar/holidays.py`, `src/notifications/telegram.py`, `src/notifications/telegram_gateway.py`, `src/strategy/exit_signals.py`), and 24 of 55 `scripts/` entrypoints never call `setup_logging()`. LOGGING.md's mandatory rules were elevated to canonical by CLAUDE.md precisely because of the BUG-010 failure class (six incompatible log formats found in `logs/` before the standard was written down) — this is that same failure class, uncorrected, at scale.

**Pre-implementation gate:** State in one sentence which task, which files, which test file.
Do not write any code until this plan is stated.

**Story spec:** Read the matching story in `docs/plan/full-repo-review-followups/logging-migration-completion/stories.md` for the full spec.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph. Order: `git log --oneline -10 <file>` → `search_graph`/`get_code_snippet` →
`trace_path` → `search_code` → `sed -n` → `Read` (state why the graph was
insufficient).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` and `search_graph('<EnumName>')` first — never write
a `_make_*`/`build_*` fixture helper from memory.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing.

**Financial logic commit — real `@code-reviewer` subagent mandatory** per CLAUDE.md's Agent AutoTrigger Rules (this touches P&L / Decimal / broker-adjacent paths). Resolve any CRITICAL/ERROR finding before committing.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not
draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.
