# Signal outcome profit range — database schema

1 table changed in `data/portfolio/portfolio.sqlite` (via `src/signals/store.py`'s `SignalStore`). Decimal fields stored as `TEXT`, read back via `Decimal(row["col"])`. Existing table already has live
rows — this is an `ALTER TABLE ADD COLUMN` migration inside `init_db()`, guarded for idempotent re-run, following the existing pattern at `src/signals/store.py:156-161` (`daily_signals` /
`signal_responses` columns). No CREATE-TABLE change, no new table.

---

```sql
-- Added to signal_outcomes (existing table, src/signals/store.py). Written by
-- run_record_phase (scripts/signal_eod.py); read by _format_outcome_notification and
-- get_outcome/get_all_outcomes.
ALTER TABLE signal_outcomes ADD COLUMN high_pnl_per_lot TEXT;  -- Decimal as TEXT, NULL when
                                                                -- not executed or no marks
ALTER TABLE signal_outcomes ADD COLUMN low_pnl_per_lot  TEXT;  -- Decimal as TEXT, NULL when
                                                                -- not executed or no marks
```

Guard each `ALTER TABLE` in the existing `try/except sqlite3.OperationalError` loop in `init_db()` — re-running against a DB that already has the columns must not raise (matches the "duplicate column
name" check already there).

Existing rows keep `NULL` for both columns — no backfill (Animesh confirmed: study is forward-looking only, historical `signal_outcomes` rows are not reprocessed).

## DB_REGISTRY.md row to add

`signal_outcomes` is not currently listed in `DB_REGISTRY.md`'s daily-write table (it is an event-write table, one row per trading day, written by `scripts/signal_eod.py` at 16:00 IST cron). This
story does not add a new table, so no new registry row — note the two new columns inline if `signal_outcomes` ever gets a registry row in a future pass.

## Existing tables reused (no shape change)

- `paper_signal_marks` (`src/paper/store.py` — `record_mark` / `get_marks`) — read-only source of the `mfe_pct` / `mae_pct` used to compute the two new columns. Not altered by this story.
- `paper_signal_entries` — read-only, already used by `run_record_phase` to resolve `trade_id`.
