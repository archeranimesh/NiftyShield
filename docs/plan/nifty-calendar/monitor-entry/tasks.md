
# Monitor-driven calendar entry — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: ME-1, ME-2, ME-3, ME-4.**

- [ ] **ME-1** — `EntryReporter` Protocol and `CalendarEntryReporter` (margin capture, entry card, payoff chart) extracted from the entry script into `src/strategy/` | Owner: Claude | Model:
  claude-sonnet-5-5 | Review: code-reviewer | SHA: —
- [ ] **ME-2** — Inject the reporter into `NiftyCalendarV1`, call it after a successful `OPEN_STRUCTURE`, wire in `build_calendar_shell`, thin `run_entry` | Owner: Claude | Model: claude-sonnet-5-5 |
  Review: code-reviewer | SHA: —
- [ ] **ME-3** — Per-strategy log routing for the monitor daemon (`logs/strategies/<strategy_name>.log`) | Owner: Claude | Model: claude-sonnet-5-5 | Review: code-reviewer | SHA: —
- [ ] **ME-4** — Cutover: retire calendar entry cron lines, margin-row backfill decision for 2026-10-14, close-out docs | Owner: Claude | Model: claude-sonnet-5-5 | Review: none | SHA: —

## Story done when

- **ME-1** — with fake broker, store and notifier, `report_entry` writes one margin snapshot, sends one card and one chart for a persisted structure, and a failure in any of the three never raises.
- **ME-2** — `apply_action` with `legs_to_open` calls the reporter once when legs were written and zero times when a position already existed; the script no longer duplicates margin or card code.
- **ME-3** — a daemon tick for a registered strategy writes its lines to `logs/strategies/<strategy_name>.log` and still to `monitor_daemon.log`; no file is created for a strategy that logged nothing.
- **ME-4** — cutover note, `src/strategy/CLAUDE.md`, `CONTEXT.md`, `DECISIONS.md` and the epic story list updated; Animesh's crontab step recorded.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status wherever it is summarised (`docs/plan/README.md` for a single story, the epic `README.md` story
list for an epic sub-story) and add one line to `TODOS.md` Session Log. When the whole story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.
