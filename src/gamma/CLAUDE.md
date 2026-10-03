# src/gamma/ — Module Context

## Purpose

Near-Expiry Gamma Buy strategy scaffolding. Tracks option contracts with elevated gamma gearing as candidates for directional gamma plays near expiry.

## Models (`models.py`)

Two frozen dataclasses — never mutate after construction:

- **`GammaChainSnapshot`** — one row per option contract per snapshot tick. Fields: `snapshot_date`, `snapshot_time` (HH:MM IST), `expiry_date`, `strike`, `option_type` (CE|PE), `dte_calendar`,
  `nifty_spot`, `nifty_futures`, `india_vix`, full Greeks (`delta_val`, `gamma_val`, `vega_val`, `theta_val`, `iv_val`), derived fields (`gamma_gearing`, `distance_pct`), quote (`best_bid`,
  `best_ask`, `bid_ask_spread`), OI/volume, computed percentiles (`strike_iv_pctile_20d`, `gamma_gearing_pctile_dte`), and `created_at` (UTC, timezone-aware).

- **`GammaWatchlistEntry`** — one row per (expiry, strike, option_type) watchlist candidate. Tracks `added_date`, `last_seen_date`, `removed_date`, `removal_reason`, `elevated`, `elevation_reason`.

## Decimal invariant

All monetary, Greek, and derived numeric values use `Decimal`, stored as TEXT in SQLite. Never use `float` for these fields. Read back with `Decimal(row["col"])`. Greeks from the Upstox chain parser
arrive as `float` — convert at the boundary: `Decimal(str(greek_float))`.

## Store (`store.py`) — `GammaStore`

Table: **`gamma_chain_snapshots`** Primary key: `AUTOINCREMENT id` Uniqueness: `UNIQUE(snapshot_date, snapshot_time, expiry_date, strike, option_type)` — upsert semantics via `INSERT OR REPLACE`.

Table: **`gamma_watchlist`** Primary key: `(expiry_date, strike, option_type)` — natural composite key.

Constructor: `GammaStore()` — stateless; every method takes an open `sqlite3.Connection`. Create tables explicitly via `create_tables(conn)` (idempotent `CREATE TABLE IF NOT EXISTS`).

`get_prior_oi(conn, expiry_date, today)` — one batched query returning the latest pre-today OI per `(strike, option_type)`; feeds `derive_snapshots` (never call `get_yesterday_snapshot` in a
per-strike loop).

`get_prior_snapshots(conn, expiry_date, today, days)` — one query: the latest snapshot per `(strike, option_type)` for each of the last `days` distinct snapshot dates strictly before `today` (D3;
same-day re-runs collapse to the latest `snapshot_time`). `get_all_active_watchlist(conn)` — active entries across all expiries; needed because `get_active_watchlist` takes one expiry and misses last
week's entries once `current_week_expiry` has rolled (D4).

`update_percentiles(conn, *, snapshot_date, snapshot_time, expiry_date, strike, option_type, iv_pctile, gearing_pctile)` — targeted UPDATE of the two percentile columns for one snapshot key (`None`
keeps the column; returns False for an unknown key). Calibration reads are day-based (D5): `get_iv_history(..., before=today)` returns one value per prior date (latest snapshot_time), so its `len` is
a day count; `get_gearing_by_dte(..., before=today)` excludes today; `count_prior_gearing_days(conn, dte, before)` is the distinct-day count the 20-day gate uses (the gearing list length counts
strikes, not days). Without `before`, both getters keep their legacy every-row behaviour.

## Derived fields (`derive.py`)

Pure, zero-I/O `derive_snapshots(chain, expiry_date, today, snapshot_time, prior_oi)` builds `GammaChainSnapshot` rows for strikes within ±10% of spot (`gamma_gearing` = gamma × spot² / ask, `None`
when ask <= 0.50 or gamma missing; `distance_pct`; `oi_change_1d`; `bid_ask_spread`; `dte_calendar`). Shared by `scripts/pipeline/gamma_daily_watch.py` and Phase B `gamma_scan.py`. Strike keys are
`int`, matching `GammaChainSnapshot.strike`.

## Watchlist rules (`watchlist.py`)

Pure `evaluate_watchlist(today_snaps, history, active, today) -> WatchlistDecision` (frozen: `add`, `retain`, `remove` carrying `removal_reason`, `elevate`); thresholds are module constants, no rule
registry. Add criteria (§5b) gate new entries only; an active entry that stops qualifying is retained (state refreshed) unless a removal rule fires (D4). `None` gearing/OI blocks adding; `None`
`oi_change_1d` passes inclusion but blocks elevation. Elevation is recomputed every run, needs inclusion, and needs 3 prior snapshot dates (average excludes today). "Yesterday" is the most recent
prior snapshot *date*; a strike missing from it never triggers removal. `expired` covers every active entry. Feed it current-week-expiry snapshots only. The script applies the decision.

## Dependency rule

`src/gamma/` never imports from `scripts/`. Scripts are thin orchestration; rules live here.

## Daily watch script (`scripts/pipeline/gamma_daily_watch.py`)

Runs end to end: expiry resolution, chain fetch + `derive_snapshots`, snapshot persistence, `_update_watchlist`, `_run_calibration`, Telegram summary. `--morning` stops after persistence (D6);
`--dry-run` reads the store but never writes and sends nothing (D9). `_run_calibration` ranks today's IV and DTE-bucket gearing against prior days only, gated on 20 distinct prior days, and writes via
`update_percentiles`; the percentile maths is a script-local helper (no `calibration.py`). The Telegram send is non-fatal (`asyncio.wait_for` timeout, WARNING on failure, skipped when
`build_notifier()` is None). Percentile columns are read-only for Phase B.

## What does NOT yet exist

- Phase B (`gamma_scan.py`, `gamma_signal_log`) — sibling story `docs/plan/gamma-near-expiry/gamma-scan-phase-b/`.
