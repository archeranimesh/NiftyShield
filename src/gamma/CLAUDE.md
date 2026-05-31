# src/gamma/ — Module Context

## Purpose

Near-Expiry Gamma Buy strategy scaffolding. Tracks option contracts with
elevated gamma gearing as candidates for directional gamma plays near expiry.

## Models (`models.py`)

Two frozen dataclasses — never mutate after construction:

- **`GammaChainSnapshot`** — one row per option contract per snapshot tick.
  Fields: `snapshot_date`, `snapshot_time` (HH:MM IST), `expiry_date`,
  `strike`, `option_type` (CE|PE), `dte_calendar`, `nifty_spot`,
  `nifty_futures`, `india_vix`, full Greeks (`delta_val`, `gamma_val`,
  `vega_val`, `theta_val`, `iv_val`), derived fields (`gamma_gearing`,
  `distance_pct`), quote (`best_bid`, `best_ask`, `bid_ask_spread`),
  OI/volume, computed percentiles (`strike_iv_pctile_20d`,
  `gamma_gearing_pctile_dte`), and `created_at` (UTC, timezone-aware).

- **`GammaWatchlistEntry`** — one row per (expiry, strike, option_type)
  watchlist candidate. Tracks `added_date`, `last_seen_date`,
  `removed_date`, `removal_reason`, `elevated`, `elevation_reason`.

## Decimal invariant

All monetary, Greek, and derived numeric values use `Decimal`, stored as
TEXT in SQLite. Never use `float` for these fields. Read back with
`Decimal(row["col"])`. Greeks from the Upstox chain parser arrive as
`float` — convert at the boundary: `Decimal(str(greek_float))`.

## Store (`store.py`) — `GammaStore`

Table: **`gamma_chain_snapshots`**
Primary key: `AUTOINCREMENT id`
Uniqueness: `UNIQUE(snapshot_date, snapshot_time, expiry_date, strike, option_type)` — upsert semantics via `INSERT OR REPLACE`.

Table: **`gamma_watchlist`**
Primary key: `(expiry_date, strike, option_type)` — natural composite key.

Constructor: `GammaStore(db_path)` — calls `_ensure_tables()` on init
(idempotent `CREATE TABLE IF NOT EXISTS`).

## What does NOT yet exist

- `gamma_daily_watch.py` script — planned for Phase A. Will consume
  `GammaStore` to emit daily watchlist updates via Telegram.
- Calibration update path for `strike_iv_pctile_20d` and
  `gamma_gearing_pctile_dte` percentile columns — schema present,
  population logic not yet implemented.
