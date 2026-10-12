# src/gamma/ — Module Context

## Purpose

Near-Expiry Gamma Buy strategy scaffolding. Tracks option contracts with elevated gamma gearing as candidates for directional gamma plays near expiry.

## Models (`models.py`)

Two frozen dataclasses — never mutate after construction:

- **`GammaChainSnapshot`** — one row per option contract per snapshot tick. Fields: `snapshot_date`, `snapshot_time` (HH:MM IST), `expiry_date`, `strike`, `option_type` (CE|PE), `dte_calendar`,
  `nifty_spot`, `nifty_futures`, `india_vix`, full Greeks (`delta_val`, `gamma_val`, `vega_val`, `theta_val`, `iv_val`), derived fields (`gamma_gearing`, `distance_pct`), quote (`best_bid`,
  `best_ask`, `bid_ask_spread`), OI/volume, computed percentiles (`strike_iv_pctile_20d`, `gamma_gearing_pctile_dte`), and `created_at` (UTC, timezone-aware).

- **`GammaWatchlistEntry`** — one row per (expiry, strike, option_type) watchlist candidate. Tracks `added_date`, `last_seen_date`, `removed_date`, `removal_reason`, `elevated`, `elevation_reason`.

- **`GammaSignalLogEntry`** — one row per evaluated strike in 5-minute intraday scans (Phase B). Tracks underlying context, L2 depth, Greeks, derived fields, tri-state filter passes (`f0`–`f4`),
  signal trigger, paper-trade execution status, and exit tracking. Timestamps are timezone-aware UTC.

## Decimal invariant

All monetary, Greek, and derived numeric values use `Decimal`, stored as TEXT in SQLite. Never use `float` for these fields. Read back with `Decimal(row["col"])`. Greeks from the Upstox chain parser
arrive as `float` — convert at the boundary: `Decimal(str(greek_float))`.

## Store (`store.py`) — `GammaStore`

Table: **`gamma_chain_snapshots`** Primary key: `AUTOINCREMENT id` Uniqueness: `UNIQUE(snapshot_date, snapshot_time, expiry_date, strike, option_type)` — upsert semantics via `INSERT OR REPLACE`.

Table: **`gamma_watchlist`** Primary key: `(expiry_date, strike, option_type)` — natural composite key.

Table: **`gamma_signal_log`** Primary key: `signal_id` — plain `INSERT` (no `OR REPLACE`), duplicates raise `IntegrityError`. Open positions defined as `paper_trade_filled = 1 AND exit_timestamp IS
NULL`.

Constructor: `GammaStore()` — stateless; every method takes an open `sqlite3.Connection`. Create tables explicitly via `create_tables(conn)` (idempotent `CREATE TABLE IF NOT EXISTS`).

`insert_signal_log(conn, entry)` — plain INSERT of `GammaSignalLogEntry`. Does not commit (supports outer transactions). Rejects naive timestamps with `ValueError`. Tri-state boolean filters store
`None` as `NULL`.

`update_signal_exit(conn, signal_id, *, exit_price, exit_timestamp, exit_reason, mfe=None, mae=None, realised_r_multiple=None)` — updates unexited rows (`exit_timestamp IS NULL`). Returns `False` on
unknown ID or already-exited row.

`get_open_signal_positions(conn, option_type=None)` — returns list of `GammaSignalLogEntry` for all unexited filled trades (`paper_trade_filled = 1 AND exit_timestamp IS NULL`), optionally filtered by
option type.

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

## Signal stack (`signals.py`)

Pure `SignalStack(config).evaluate(Candidate) -> StackResult` over ordered `Layer`s of predicates `(Candidate, SignalConfig) -> ReasonCode | None`; first failing predicate stops the stack. Every
threshold is a `SignalConfig` field (frozen); `min_ask_qty` is required with no default (the scan fills it from `DateAwareLotSizeResolver`; lot size is 65). `gearing_threshold` is injected (Stage 1
default 5.0; Stage 2/3 selection is the caller's job). Live `gamma_gearing` is gamma × spot² / ask, ~5e3–5e4, so the Stage-1 floor of 5.0 is non-binding in practice. Fail closed: `india_vix` or quote
age `None` fails with a distinct `*_UNAVAILABLE` code (Phase A stores `india_vix` NULL); only `ask_qty_l1 is None` (reduced mode) passes on `None`. Layer 3: `strike_iv_pctile_20d` is a 0–1 fraction
(`iv_pctile_max=0.30`); with no history condition B is unavailable (`L3_B_UNAVAILABLE`), never a pass. `StackResult` carries tri-state `f0`–`f4` (None = not reached), `quality_method`, and
`watchlist_hit` (never alters the outcome). The "no open position in same direction" check is NOT here; GS-5 owns it in the atomic entry transaction.

## Ranking and exits (`ranking.py`, `exits.py`)

Pure, zero-I/O. `rank_candidates(candidates) -> list[Candidate]` sorts best-first by the section 6 score `gearing * 0.7 + hit * 0.3 * gearing` (Decimal); ties break on watchlist hit, lower ask,
smaller `distance_pct`, option type, then input order (`Candidate` has no strike, so GS-5 must pass candidates in a stable order). `evaluate_exit(position, tick, config) -> ExitDecision | None` walks
an ordered rule tuple (`e1_profit_target`, `e2_stop_loss`, `e2_liquidity`, `e3_time_stop`); thresholds are `ExitConfig` fields. "Mark" is the tick **bid** (a `None` bid never fires price rules); E1 is
`bid >= 5 x entry_ask`, E2 stop `bid <= 0.25`, E2 liquidity is `ask_qty == 0` for 2 consecutive scans (GS-5 keeps the streak in `ExitPosition.prior_zero_ask_scans` and must reset it to 0 on any
non-zero ask qty), E3 is keyed on the tick's calendar DTE and IST time (DTE 0 at 14:30; DTE 1 at 15:00 unless bid >= 1.5 x entry ask). `ExitDecision` carries `ExitReason`, the bid exit price and
`realised_r`; `mfe`/`mae` tracking is GS-5's job. `exit_price`/`realised_r` can be None (no bid), so metrics must filter NULLs.

## Dependency rule

`src/gamma/` never imports from `scripts/`. Scripts are thin orchestration; rules live here.

## Daily watch script (`scripts/pipeline/gamma_daily_watch.py`)

Runs end to end: expiry resolution, chain fetch + `derive_snapshots`, snapshot persistence, `_update_watchlist`, `_run_calibration`, Telegram summary. `--morning` stops after persistence (D6);
`--dry-run` reads the store but never writes and sends nothing (D9). `_run_calibration` ranks today's IV and DTE-bucket gearing against prior days only, gated on 20 distinct prior days, and writes via
`update_percentiles`; the percentile maths is a script-local helper (no `calibration.py`). The Telegram send is non-fatal (`asyncio.wait_for` timeout, WARNING on failure, skipped when
`build_notifier()` is None). Percentile columns are read-only for Phase B.

## What does NOT yet exist

- Phase B orchestration (`scripts/gamma_scan.py`, GS-5) — sibling story `docs/plan/gamma-near-expiry/gamma-scan-phase-b/`.
