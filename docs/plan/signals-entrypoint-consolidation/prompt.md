# Signals Entrypoint Consolidation — prompt

> Collapse the duplicated glue across the four signal entrypoints — one holiday guard, one "did the signal fire" predicate, one EOD script — without touching the signal pipeline or the paper-track
> execution layer.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The `signals/` epic shipped three host crons — `morning_signal` 09:30, `record_signal_outcome --auto` 16:00, `signal_report` 16:35 — and `signals-paper-track/` (SPT) adds a paper-entry tail-call
inside `morning_signal`, a `paper_signal_track_v1` registration in the monitor daemon, and a manual `signal_paper_entry.py`. Across those entrypoints the same glue is re-expressed: the NSE-holiday
guard is one helper (`src/market_calendar.is_trading_day`) wrapped in a copy-pasted guard-log-return block at three sites and **missing** at `record_signal_outcome`; the "did the signal fire today"
predicate (`trade_action is not NO_TRADE`) is hand-written in four places; `record_signal_outcome` and `signal_report` open the same store 35 minutes apart only so the outcome write settles before the
report reads it.

Animesh flagged this while reviewing the SPT plan (2026-09-10): too many overlapping entrypoints to reason about, and the shared logic will drift. A Plan-agent review confirmed the fix is small and
should land **after** SPT ships — the pieces touch files SPT holds out of bounds (`src/signals/models.py`, the two advisory scripts), and keeping SPT's diff minimal was worth more than folding the
cleanup in. This story is that deferred cleanup.

## Scope guard

**In bounds:** `src/market_calendar.py` (a new `guard_trading_day` + `is_market_session_now` helper), `src/signals/models.py` (`DailySignal.is_actionable` property only), the four call sites that
adopt them (`scripts/morning_signal.py`, `scripts/record_signal_outcome.py`, `scripts/signal_report.py`, `src/strategy/signal_track_v1.py`), `src/strategy/monitor.py` (adopt `is_market_session_now`),
and merging `record_signal_outcome.py` + `signal_report.py` into one `scripts/signal_eod.py`. Optionally an orchestration-only extraction of `morning_signal`'s pipeline body into `src/signals/`.

**Out of bounds:** the signal pipeline logic (`aggregator.py`, `snapshot.py`, `providers/`, `option_resolver.py`, `factory.py`), all of the SPT execution layer (`signal_track_v1.py` beyond the one
predicate swap, `signal_exit.py`, `paper_signal_*` tables, the monitor registration), the live portfolio, and the finideas strategies. **No behaviour change** — the idealized `SignalOutcome` baseline
row that `record_signal_outcome --auto` writes today is written byte-for-byte the same after the merge; this story only removes duplication and one cron line.

**Hard precondition:** `docs/plan/signals-paper-track/` is archived (all SPT tasks ticked). Do not start SEC-1 before then — SPT-3 and SPT-6 add the fourth `is_actionable` call site and the
`morning_signal` tail-call this story refactors against.

## Session-start load hints

Beyond `CONTEXT.md`:
- `DECISIONS.md` — the §"Signals Paper Track — Execution Layer" as-built note (names the `morning_signal` tail-call seam this story refactors around) and §P&L & Reporting (why `record_signal_outcome`
  is the idealized baseline, kept distinct from the paper track).
- `LOGGING.md` — the `_SCRIPT_NAME` rule for the merged `scripts/signal_eod.py`.
- `src/signals/` — `models.py` for the `DailySignal` shape; `SignalStore` for the outcome / report reads.
- `src/market_calendar.py` — the existing `is_trading_day` / `market_today` this story wraps.
- No `schema.md` — this story changes no DB schema (reads and writes existing tables only).

## Task overview

- **SEC-1** — `market_calendar.guard_trading_day()` + `is_market_session_now()`; adopt at every signal entrypoint (gives `record_signal_outcome` the guard it lacks) and in `StrategyMonitor`.
- **SEC-2** — `DailySignal.is_actionable` property; refactor the four `trade_action is not NO_TRADE` call sites onto it.
- **SEC-3** — merge `record_signal_outcome.py` + `signal_report.py` → `scripts/signal_eod.py` (record then report, one 16:00 cron, one guard); crontab 2 lines → 1.
- **SEC-4** — extract `morning_signal`'s pipeline body into `src/signals/` so the script is orchestration-only (discretionary — see the spec).
- **SEC-5** — decide `scripts/signal_paper_entry.py` keep-or-delete from the tail-call's track record; act on the decision.
- **SEC-6** — docs close + archive.

## Definition of done

One holiday guard, one fire-check predicate, one EOD script, one fewer cron line — with the signal pipeline, the paper-track execution layer, and the idealized `SignalOutcome` baseline row all
unchanged. Every new public function carries happy-path + edge tests; no network, no real DB in the suite. The final crontab and the entrypoint map are recorded in `CONTEXT.md` and `DECISIONS.md`.
