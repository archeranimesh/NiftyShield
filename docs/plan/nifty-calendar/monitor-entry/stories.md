
# Monitor-driven calendar entry — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

Evidence for the story: `logs/monitor_daemon.log` 2026-10-14 10:31:21 (`auto_execute_dispatched ... NC_ENTRY ... OPEN_STRUCTURE`); `paper_trades` ids 501-504; no `paper_margin_snapshots` row.

---

## ME-1 — EntryReporter Protocol and CalendarEntryReporter

**Files to change / create:**
- `src/strategy/nifty_calendar_entry_report.py` — new: `EntryReporter` Protocol and `CalendarEntryReporter`.
- `tests/unit/strategy/test_nifty_calendar_entry_report.py`
- `scripts/strategies/nifty_calendar/paper_calendar_entry.py` — unchanged in this task (the script keeps working; ME-2 removes its copy).

**Before any code:** `get_code_snippet("_send_entry_card")` and `get_code_snippet("capture_entry_margin")`; `get_code_snippet("send_close_message")` for the notifier precedent;
`trace_path("build_view")` and `trace_path("send_payoff_chart")`; `get_code_snippet("MarginSnapshot")`. Run the design-principles SOLID triggers and the prior-art audit and record the outcome in
`prompt.md` Design review.

**What to implement:**

1. `EntryReporter(Protocol)`: `async def report_entry(self, strategy_name: str, entry_date: date) -> None`. It reads the just-persisted open legs from the store, so the caller passes no chain or
   margin.
2. `CalendarEntryReporter`: constructor-injected `broker`, `store`, `lookup`, `notifier`, `config`. `report_entry` (a) calls `capture_entry_margin` for the short legs, (b) fetches the near-expiry
   chain itself with the script's `_fetch_chain` logic (move that helper here or into a shared function; the script then imports it), (c) builds the view, the `build_calendar_entry_message` card and
   the payoff chart exactly as `_send_entry_card` does today, passing the captured `final_margin` to the chart.
3. Every step is independently non-fatal: a margin failure still sends the card, a card failure still sends the chart, nothing raises (log `calendar_entry.report_failed` with `step=`). Preserve the
   `ensure_registered()` call for payoff registrations.
4. Note in the module docstring that `notifier=None` still captures margin and skips messages, matching the script's current behaviour.

**Tests (`tests/unit/strategy/`, no network, no real DB):**
- `test_report_entry_writes_margin_card_and_chart_once` — fakes record one margin write, one `send_notification`, one `send_photo`.
- `test_margin_failure_still_sends_card` and `test_card_failure_still_sends_chart`.
- `test_no_notifier_captures_margin_only`.
- `test_report_entry_never_raises_on_broker_error`.

**Commit:** `feat(strategy): add calendar entry reporter`

---

## ME-2 — Wire the reporter into the shell and thin the script

**Files to change / create:**
- `src/strategy/nifty_calendar_v1.py` — optional `entry_reporter: EntryReporter | None = None` constructor argument; `apply_action` awaits it after `_open_structure` when legs were written.
- `src/strategy/nifty_calendar_factory.py` — `build_calendar_shell` constructs `CalendarEntryReporter` from the broker, store, lookup, notifier and config it already receives.
- `scripts/strategies/nifty_calendar/paper_calendar_entry.py` — remove the post-`apply_action` margin and `_send_entry_card` block; keep `INCOMPLETE` detection and alerts.
- `tests/unit/strategy/test_nifty_calendar_v1.py`, `tests/unit/scripts/test_paper_calendar_entry.py` — extend.

**Before any code:** `trace_path("apply_action")` and `trace_path("build_calendar_shell")` for every caller (daemon, entry script, snapshot script, tests); `get_code_snippet("_open_structure")`.

**What to implement:**

1. `_open_structure` must tell `apply_action` whether it wrote legs (return a bool, or compare positions before and after). A call that hits `nifty_calendar.open_skipped_position_exists` or recorded
   no new row must not report, so a second process or a re-run never sends a duplicate card.
2. `apply_action` awaits `self._entry_reporter.report_entry(...)` after a successful open, inside `try/except Exception` that logs and swallows (a message failure never undoes an entry, as today). Do
   not report when the structure is `INCOMPLETE` (missing roles); leave that alert in the script and add the equivalent `nifty_calendar.legs_not_persisted` error log in the shell.
3. `build_calendar_shell` passes the reporter; with no reporter (older tests) behaviour is unchanged.
4. `run_entry`: after `shell.apply_action`, keep the `missing roles` check and return `ENTERED`; delete the margin and card code and the now-unused imports. `--no-dry-run` output is otherwise
   identical.
5. The monitor path needs no edit: `StrategyMonitor` already calls `apply_action`. Add a test that drives the dispatch with a stub reporter to prove it.

**Tests:**
- `test_apply_action_open_reports_once`
- `test_apply_action_open_skipped_when_position_exists_does_not_report`
- `test_reporter_exception_does_not_undo_entry`
- `test_script_entry_no_longer_sends_card_directly` — script path still yields exactly one card via the shell.
- `test_monitor_dispatch_of_nc_entry_triggers_reporter`

**Commit:** `feat(strategy): report calendar entries from the shell`

---

## ME-3 — Per-strategy log routing

**Files to change / create:**
- `src/utils/logging.py` — opt-in per-strategy file sink keyed on the `strategy` event field.
- `scripts/monitor_daemon.py` — enable it for the daemon only.
- `LOGGING.md` — document the layout.
- `tests/unit/utils/test_logging_strategy_routing.py`

**Before any code:** read `LOGGING.md` and `src/utils/logging.py` in full (BUG-010 covers why formats must not diverge); `search_code("strategy=")` over `src/strategy/monitor.py` to see which events
carry the field; confirm the daemon is the only long-lived multi-strategy process.

**What to implement:**

1. A structlog processor (or stdlib handler filter) that, when enabled, appends each event whose `strategy` field is set to `logs/strategies/<strategy_name>.log` in the standard line shape, in
   addition to the existing file. Create the file lazily on first event.
2. Opt-in via a `setup_logging(strategy_log_dir=...)` argument; default `None` keeps every existing script unchanged.
3. Reject path traversal: the strategy name is sanitised to `[A-Za-z0-9_.-]`.
4. Open file handles are bounded (small LRU or one handle per name, 13 strategies today); rotation follows the same policy as the main log.
5. Events from `NiftyCalendarV1.apply_action` and the reporter carry `strategy=` so entry and report lines land in the calendar's own file; add the field where missing (ME-1/ME-2 use it already).

**Tests:** `test_event_with_strategy_field_written_to_strategy_file_and_main` · `test_event_without_field_goes_to_main_only` · `test_default_setup_creates_no_strategy_dir` ·
`test_unsafe_strategy_name_is_sanitised`.

**Commit:** `feat(logging): route daemon logs per strategy`

---

## ME-4 — Cutover, backfill decision and close-out

**Files to change / create:**
- `docs/plan/nifty-calendar/monitor-entry/stories.md` (this file) — append a "Cutover note" section with the crontab step.
- `src/strategy/nifty_calendar_v1.py` — update `reentry_script_hint` text if the script is now manual-only.
- `CONTEXT.md`, `src/strategy/CLAUDE.md`, `DECISIONS.md`, `docs/plan/nifty-calendar/README.md`, `docs/plan/README.md`, `TODOS.md`.

**What to do:**

1. Cutover note for Animesh: remove the two `paper_calendar_entry` lines (monthly and biweekly) from the crontab and keep the two `paper_calendar_snapshot` lines. The script stays as a manual or
   recovery tool; its `ALREADY_OPEN` and `OTHER_VARIANT_OPEN` guards make a late manual run safe. Record the trade-off: with cron gone, a daemon outage in the entry window means no entry that day.
2. Decide with Animesh whether to keep one entry cron line as a safety net. If kept, note that it races the daemon and that `_open_structure`'s position check is the only guard; if dropped, add a
   daemon-down alert only if one already exists elsewhere (do not build one here).
3. Backfill decision for `paper_nifty_calendar_biweekly` entry on 2026-10-14: no `paper_margin_snapshots` row exists. Offer a one-off `capture_entry_margin` call through a tested `scripts/dev/` CLI
   (not a scratchpad script) or leave the gap; Animesh decides. Default: record the gap in `DB_REGISTRY.md` and do nothing.
4. `DECISIONS.md`: record that calendar entries are monitor-driven and shell-reported, that CC/PP/IC/collar entries remain cron-driven, and that moving them is an open council question.
5. Close the story per `docs/plan/README.md` §Conventions: epic `README.md` story list, the epic row in `docs/plan/README.md` (both pointers), `TODOS.md` Session Log, and archive when complete.

**Tests:** none beyond the green suite (docs and a hint string). Run `python -m pytest tests/unit/ --tb=no -q`.

**Commit:** `docs(nifty-calendar): close monitor-entry story`
