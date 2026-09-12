# Signals Entrypoint Consolidation — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: SEC-5.**

> **Routing:** SEC-1 / SEC-2 / SEC-3 are `Owner: Antigravity` — mechanical, airtight specs, TDD-shaped (SEC-3 is regression-fixture-gated on a byte-identical `SignalOutcome` row). Each `code-reviewer`
> gate is a **real Claude subagent run**, not Antigravity's persona approximation — SEC-2 and SEC-3 touch signal / P&L-adjacent paths (CLAUDE.md §AutoTrigger). SEC-4 (discretionary), SEC-5 (a
> keep/delete decision) and SEC-6 (docs close) stay `Owner: Claude`.

- [x] **SEC-1** — `src/market_calendar.guard_trading_day(logger, script_name) -> bool` (guard-log-return in one call) + `is_market_session_now() -> bool` (09:15–15:30 IST on a trading day); adopt in
  `morning_signal`, `record_signal_outcome`, `signal_report`, `signal_paper_entry`, and `StrategyMonitor`'s session check. | Owner: Antigravity | Model: gemini-2.5-pro | Review: code-reviewer | SHA:
  1ef2974
- [x] **SEC-2** — `DailySignal.is_actionable` property on `src/signals/models.py` (`return self.trade_action is not TradeAction.NO_TRADE`); refactor the four call sites (`morning_signal`,
  `record_signal_outcome`, `signal_report`, `signal_track_v1`). | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: 0202291 (`819306b` — follow-up fix for escaping-guard baseline
  line-number drift caused by the unused-import removal). `signal_report`'s two `NO_TRADE` checks operate on `SignalOutcome`, not `DailySignal` — left untouched (out of this task's authorized scope:
  `DailySignal.is_actionable` property only); only three of the four named call sites (`morning_signal`, `record_signal_outcome`, `signal_track_v1`) were refactored.
- [x] **SEC-3** — merge `scripts/record_signal_outcome.py` + `scripts/signal_report.py` → `scripts/signal_eod.py` (phase 1 = write the `SignalOutcome` row via the current `--auto` logic, unchanged;
  phase 2 = the report), one 16:00 cron, one `guard_trading_day`. Retire the two old crontab lines, add the one new line. Keep `--auto` / report-only flags for manual use. | Owner: Antigravity |
  Model: n/a | Review: code-reviewer | SHA: 928cb22 (merge) / `b297734` (retire old scripts + docs) / `6b6177b` (follow-up fix — escaping-guard baseline entries for `signal_eod.py`, restored
  `send_test_telegram.py:65` entry dropped in the retire commit, cleaned up a misattributed noqa comment on the report-phase exception handler). Real `code-reviewer` run flagged 2 CRITICAL / 2 ERROR /
  5 WARNING on the first pass; all CRITICAL/ERROR resolved in the follow-up; targeted test set (`tests/unit/scripts/`, `tests/unit/signals/`, `tests/unit/notifications/test_escaping_guard.py`) green —
  527 passed.
- [x] **SEC-4** — extract `morning_signal.run()`'s pipeline body into `src/signals/pipeline.py::run_morning_signal_pipeline(...)` so `scripts/morning_signal.py` is orchestration + Telegram only.
  Discretionary — if the body does not cleanly separate from the cron-boundary I/O, record why in the commit and tick with that note. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer |
  SHA: 85b4744. Separated cleanly per spec — `MorningSignalResult` frozen dataclass carries `signal`/`snapshot`/`n_providers`/`day_cost_usd`/`n_priced` back to the script for the Telegram
  notification. `code-reviewer` found 0 CRITICAL/ERROR, 2 WARNING (deferred, documented in the commit body): `morning_signal_complete` now logs before the Telegram send instead of after (a boundary
  consequence, not a data change), and the new `src/signals/pipeline.py` keeps the `"scripts.morning_signal"` logger name for log-output continuity rather than switching to `__name__`.
  Pipeline-behaviour tests moved to `tests/unit/signals/test_pipeline.py`; `tests/unit/scripts/test_morning_signal.py` now tests `run()` as pure orchestration. Fixed a stale escaping-guard baseline
  entry (`tests/unit/notifications/test_escaping_guard.py`) whose line number moved with the extraction. Targeted set (`tests/unit/scripts/`, `tests/unit/signals/`, `tests/unit/strategy/`,
  `tests/unit/notifications/`) green — 1342 passed.
- [ ] **SEC-5** — review `scripts/signal_paper_entry.py` against the `morning_signal` tail-call's track record: keep it as the documented backfill tool, or delete it and fold re-entry into a
  `--replay-date` flag on `signal_eod` / a dev script. Act on the decision; update the runbook. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SEC-6** — docs close: `CONTEXT.md` `src/signals/` entrypoint list + the final crontab, `DECISIONS.md` §P&L & Reporting note on the `signal_eod` merge, `TODOS.md` session log + delete the
  backlog pointer, `docs/plan/README.md` status → ✅ Archived; archive per §Conventions. | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>

## Story done when

- **SEC-1** — one `guard_trading_day` helper is the only holiday guard at every signal entrypoint; `record_signal_outcome` (via `signal_eod`) now has the guard it lacked; happy-path + edge tests pass,
  no network.
- **SEC-2** — `is_actionable` is the only expression of the NO_TRADE check; all four call sites use it; a `NO_TRADE` and a directional `DailySignal` test the property both ways.
- **SEC-3** — `scripts/signal_eod.py` writes the identical `SignalOutcome` row the old `record_signal_outcome --auto` did (regression fixture), then renders the report; the crontab has one EOD signal
  line, not two; the idealized baseline stays distinct from the paper track.
- **SEC-4** — `scripts/morning_signal.py` is orchestration-only, or the commit records why the extraction was not worth it; the 09:30 pipeline behaviour is unchanged either way.
- **SEC-5** — `signal_paper_entry.py` is either a documented backfill tool or gone with its re-entry path relocated; the runbook matches reality.
- **SEC-6** — `CONTEXT.md` and `DECISIONS.md` record the final entrypoint map and crontab; the folder is archived.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in `docs/plan/README.md` (single story) and add one line to `TODOS.md` Session Log. When the whole
story is done, follow `docs/plan/README.md` §Conventions *Completion → archive*.
