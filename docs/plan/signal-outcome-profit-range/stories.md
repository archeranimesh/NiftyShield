<!-- This file is the complete per-task implementation spec — a session should not need any
other planning doc to execute a task, only CONTEXT.md + the repo + CLAUDE.md / REVIEW.md. -->

# Signal outcome profit range — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

DDL: use the exact schema in `schema.md`. Do not inline `ALTER TABLE` below.

---

## SOP-1 — `SignalOutcome` fields + `signal_outcomes` migration

**Files to change / create:**
- `src/signals/models.py` — add `high_pnl_per_lot: Decimal | None` and `low_pnl_per_lot: Decimal | None` to `SignalOutcome`, defaulting to `None`.
- `src/signals/store.py` — add the two `ALTER TABLE` statements from `schema.md` to the guarded migration loop in `init_db()`; add the two columns to `record_outcome`'s `INSERT OR REPLACE` and to
  `_outcome_from_row`.
- `tests/unit/signals/test_signals_models.py` — cover the new fields.
- `tests/unit/signals/test_signals_store.py` — cover the migration + round-trip.

**Before any code (graph queries — do not write model constructors from memory):**
- `get_code_snippet("SignalOutcome")` — confirm exact current field list before adding to it.
- `get_code_snippet("SignalStore.record_outcome")` and `get_code_snippet("_outcome_from_row")` — confirm the exact column order / positional params before editing.

**What to implement:**

1. In `SignalOutcome`, add `high_pnl_per_lot: Decimal | None = None` and `low_pnl_per_lot: Decimal | None = None` after `pnl_per_lot`.
2. In `src/signals/store.py`'s `init_db()`, append the two `ALTER TABLE signal_outcomes ADD COLUMN ...` strings (exact DDL in `schema.md`) to the existing guarded-migration tuple.
3. In `record_outcome`, add `high_pnl_per_lot` / `low_pnl_per_lot` to the column list and the `VALUES` tuple, using the existing `_opt_str()` helper (same as `pnl_per_lot`).
4. In `_outcome_from_row`, read both columns back via the existing `_opt_decimal()` helper.

**Tests (`tests/unit/...`, no network, no real DB):**
- `test_signal_outcome_high_low_default_none` — constructing `SignalOutcome` without the new kwargs leaves both `None`.
- `test_signal_outcome_high_low_round_trip` — construct with both fields set, `record_outcome` then `get_outcome`, assert both come back as the same `Decimal`.
- `test_init_db_migration_idempotent_on_existing_columns` — calling `init_db()` twice against the same DB file does not raise (covers the `sqlite3.OperationalError` guard).

**Commit:** `feat(signals): add profit high/low columns to SignalOutcome`

---

## SOP-2 — Compute high/low from `paper_signal_marks` in `run_record_phase`

**Files to change / create:**
- `scripts/signal_eod.py` — in `run_record_phase`, when `live_entries` resolves an executed trade's `trade_id`, fetch its marks and compute both fields; pass them into the `SignalOutcome(...)`
  construction.
- `tests/unit/scripts/test_signal_eod.py` — cover the computed values and the not-executed / no-marks fallback.

**Before any code (graph queries — do not write model constructors from memory):**
- `get_code_snippet("SignalMark")` — exact field names (`mfe_pct`, `mae_pct`) and types.
- `get_code_snippet("PaperStore.get_marks")` — confirm signature (`trade_id: int`) and that it returns rows oldest-first (last element is the most recent / final excursion values).
- `search_graph("SignalPaperEntry")` — confirm `trade_id` field name/type on the entry object returned by `PaperStore.get_entries`.

**What to implement:**

1. In `run_record_phase`, where `live_entries` is already fetched (existing BUG-048 block), keep a reference to `live_entries[0].trade_id` alongside the existing `entry_premium` read.
2. After `executed` and `entry_premium` are resolved, if a `trade_id` was captured, call `PaperStore(settings.db_path).get_marks(trade_id)`. If the list is non-empty, take the last row's `mfe_pct` /
   `mae_pct` and compute: `high_pnl_per_lot = mfe_pct * entry_premium * LOT_SIZE` `low_pnl_per_lot = mae_pct * entry_premium * LOT_SIZE` (mirrors the existing `_pnl_per_lot` shape:
   entry-premium-relative, `LOT_SIZE`-scaled).
3. If no `trade_id` was captured (not executed, or executed via explicit `--entry-premium`/`--exit-premium` CLI flags with no live entry row), leave both `None`.
4. Pass `high_pnl_per_lot=...` / `low_pnl_per_lot=...` into the `SignalOutcome(...)` call.

**Tests (`tests/unit/...`, no network, no real DB):**
- `test_executed_outcome_computes_high_low_from_marks` — a fake `PaperStore` returning marks with known `mfe_pct`/`mae_pct` produces the expected `Decimal` high/low on the outcome.
- `test_not_executed_outcome_leaves_high_low_none` — no live entry / not executed → both `None`.
- `test_executed_with_no_marks_leaves_high_low_none` — live entry resolved but `get_marks` returns `[]` (e.g. exit fired before any tick was recorded) → both `None`, no exception.

**Commit:** `feat(signals): compute profit high/low from mark history`

---

## SOP-3 — Render high/low in the Telegram outcome message

**Files to change / create:**
- `scripts/signal_eod.py` — `_format_outcome_notification`: add a "📈 High / 📉 Low" line in the `executed` branch only, using the same `_E(...)` / `format_money(..., signed=True)` escaping pattern as
  `pnl_line`.
- `tests/unit/scripts/test_signal_eod.py` — cover the new line's presence/absence.

**Before any code (graph queries — do not write model constructors from memory):**
- `get_code_snippet("_format_outcome_notification")` — re-confirm current line order before inserting (this file may have shifted since SOP-1/SOP-2 landed).

**What to implement:**

1. After the existing `pnl_line` construction, when `outcome.executed` and both `outcome.high_pnl_per_lot` and `outcome.low_pnl_per_lot` are not `None`, build: `range_line = _E(f"📈 High
   {format_money(outcome.high_pnl_per_lot, signed=True)} / " f"📉 Low {format_money(outcome.low_pnl_per_lot, signed=True)} / lot")`
2. Insert `range_line` immediately after `pnl_line` in the executed-block return string (before the blank line + `close` line). Omit entirely (no blank placeholder) when either value is `None` —
   matches the "not-taken" / "no marks" cases from SOP-2.
3. Do not touch the not-taken (`NOT TAKEN`) or `NO_TRADE` branches — SOP-2 guarantees both fields are `None` there, so no branch-specific change is needed.

**Tests (`tests/unit/...`, no network, no real DB):**
- `test_executed_outcome_message_includes_high_low_line` — outcome with both fields set renders the "📈 High" / "📉 Low" line with correctly escaped, signed money values.
- `test_executed_outcome_message_omits_high_low_when_none` — outcome with `executed=True` but `high_pnl_per_lot=None` (pre-migration row / no marks) renders the existing message unchanged, no blank
  line artifact.

**Commit:** `feat(signals): show profit high/low in outcome Telegram message`
