# Signals LLM cost tracking — database schema

No new table. **Three columns added** to the existing `signal_responses` table in `data/portfolio/portfolio.sqlite` (single shared DB via `src/db.py`). The `cost_usd` field is a Decimal stored as
`TEXT`, read back via `Decimal(row["cost_usd"])`. Token counts are exact integers → `INTEGER`. All three columns are nullable: `NULL` for the `mock` provider and for Gemini's Phase-2 Google-SDK path,
both of which return no OpenRouter `usage` object.

Applied by `SignalStore.init_db()` using the same idempotent `try/except sqlite3.OperationalError` "duplicate column name" `ALTER TABLE` pattern already present in that method for
`daily_signals.entry_premium` — there is no migration-file mechanism. `CREATE TABLE IF NOT EXISTS` in `_SCHEMA` gains the columns too, so a fresh DB is created with them directly.

---

```sql
-- Added to the existing signal_responses table. Written by SignalStore.record_response()
-- from the SignalUsage object parsed off the OpenRouter response envelope in each provider.
-- Read back by _response_from_row() and aggregated by SignalStore.get_signal_cost().
ALTER TABLE signal_responses ADD COLUMN prompt_tokens     INTEGER;   -- OpenRouter usage.prompt_tokens; NULL when no usage object
ALTER TABLE signal_responses ADD COLUMN completion_tokens INTEGER;   -- OpenRouter usage.completion_tokens; NULL when no usage object
ALTER TABLE signal_responses ADD COLUMN cost_usd          TEXT;      -- Decimal as TEXT — OpenRouter usage.cost (USD credits); NULL when no usage object
```

No new index. `get_signal_cost()` filters on `trade_date` (already covered by `idx_signal_responses_date`) and groups by `provider` — a full-scan `GROUP BY` over a table that grows ~3 rows/trading-day
needs no dedicated index.

## DB_REGISTRY.md row to edit

`signal_responses` already has a row in `DB_REGISTRY.md`. **Edit** it (do not add a second row) so the Purpose / columns note reflects that each row now also carries per-call token counts and USD cost
from OpenRouter inline usage accounting. Keep the Writer / Cadence / Grain cells as they are (`SignalStore.record_response()` → `scripts/morning_signal.py`, per trading day, `(trade_date, provider)`).

Add a lettered note below the table if the cell will not hold it:

> Note: `prompt_tokens` / `completion_tokens` / `cost_usd` added by `signals-cost-tracking/` SCT-2 (<closing SHA>). `NULL` on rows written by the `mock` provider or Gemini's Google-SDK path, and on
> every row written before that SHA landed — cost aggregates are only complete from the first trading day after it.

## Existing tables reused (no shape change)

- `daily_signals`, `signal_inputs`, `signal_outcomes` — untouched by this story.
