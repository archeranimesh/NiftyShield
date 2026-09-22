# Signal outcome profit range — prompt

> Show the profit high and low reached since entry, for executed signal-strategy trades, in the daily SIGNAL OUTCOME Telegram message and the persisted record.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

Animesh runs the signal strategy in paper trade to study a safe profit target over ~6 months. `src/strategy/signal_track_v1.py` already tracks a running max-favourable-excursion (`mfe_pct`) and
max-adverse-excursion (`mae_pct`) per tick since entry, persisted per `trade_id` in `paper_signal_marks` (`PaperStore.record_mark` / `get_marks`). The daily EOD notification built by
`scripts/signal_eod.py` (`_format_outcome_notification`) only shows entry/exit premium and P&L — the profit high/low reached intraday is computed but never surfaced.

`run_record_phase` (`scripts/signal_eod.py`) already resolves the day's `trade_id` via `PaperStore.get_entries(trade_date, trade_date)` when auto-detecting an executed trade (BUG-048, `674ca65`), so
the mark history is one `get_marks(trade_id)` call away — no new tracking logic, only reading and surfacing data that already exists.

## Scope guard

In bounds: `src/signals/models.py` (`SignalOutcome` new fields), `src/signals/store.py` (`signal_outcomes` schema + read/write), `scripts/signal_eod.py` (`run_record_phase` computation +
`_format_outcome_notification` rendering).

Out of bounds: `src/strategy/signal_track_v1.py` (the mark computation itself is correct and unchanged), `ProfitLockEngine` / IC / positional strategies (Animesh confirmed this is signal-track only,
not IC or other positional strategies), and any backfill of historical `signal_outcomes` rows (Animesh confirmed no backfill — new columns populate going forward only, `NULL` for past rows).

This changes `src/` behaviour (a schema addition + a new computed value) and a Telegram message format. Financial-logic-adjacent (touches P&L display) — `code-reviewer` is mandatory before each commit
per CLAUDE.md.

## Session-start load hints

- `src/notifications/CLAUDE.md` §"Instrument Label Formatting" — building/editing Telegram message text.
- `FORMATTING.md` — per-parameter-type formatting standard + escaping-boundary contract; the new high/low line must follow the existing `pnl_line` escaping pattern in `_format_outcome_notification`.
- This story carries a `schema.md` — read it before any `src/signals/store.py` work.

## Task overview

- **SOP-1** — Add `high_pnl_per_lot` / `low_pnl_per_lot` to `SignalOutcome` + `signal_outcomes` schema (idempotent `ALTER TABLE ADD COLUMN` migration) + read/write in `src/signals/store.py`.
- **SOP-2** — `run_record_phase` computes both fields from `PaperStore.get_marks(trade_id)`'s last row (`mfe_pct` / `mae_pct`) for executed trades only; `None` for not-taken / no-trade.
- **SOP-3** — `_format_outcome_notification` renders a "📈 High / 📉 Low" line in the executed block only, following the existing `pnl_line` escaping pattern.

## Definition of done

An executed signal-strategy trade's Telegram SIGNAL OUTCOME message shows the ₹/lot profit high and low reached since entry, sourced from the trade's own `paper_signal_marks` history; the value is
also persisted on `SignalOutcome` for later querying. Not-taken and no-trade outcomes are unaffected. No change to `signal_track_v1.py`'s mark computation, IC/positional strategies, or historical
rows.

## Perspectives not covered

This story assumes the last `paper_signal_marks` row for a `trade_id` holds the trade's lifetime `mfe_pct`/`mae_pct` extremes (true today because both are running max/min since the first tick). If
`signal_track_v1.py`'s mark computation is ever changed to reset or window these values, this story's read-time assumption silently goes stale — not caught by any test added here.
