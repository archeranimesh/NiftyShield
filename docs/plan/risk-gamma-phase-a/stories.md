# risk-gamma-phase-a — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: tick `tasks.md`, append the completion tail
> `| Owner: <Claude|Antigravity|Animesh> | Model: <model-id|n/a> | SHA: <sha>`, add one line to
> `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## Task A — Wire `src/risk/` delta gate into `record_paper_trade.py`  ✅ DONE (b9c00146)

**What exists:** `src/risk/` is fully implemented and tested (20 unit tests green).
`PortfolioDeltaTracker` + `check_entry_allowed` are not yet called from any entry script.

**Files changed:**
- `scripts/record_paper_trade.py` — delta gate check on BUY actions only
- Test file covering `record_paper_trade.py` — gate integration tests

**Implementation:**

1. After Nifty spot is fetched, load all open `PaperPosition` objects across all strategies.
2. Instantiate `PortfolioDeltaTracker()` with default thresholds.
   Call `aggregate_delta(positions, nifty_spot, LOT_SIZE)`.
   (`LOT_SIZE` in `src/paper/constants.py`.)
3. `is_protective = True` when `action == "BUY"` and `"PE"` in the resolved instrument key.
4. `trade_delta_lots = Decimal("0")` — gate uses pre-trade state only.
5. `check_entry_allowed(portfolio_delta, Decimal("0"), is_protective)`:
   - `allowed is False` → print reason to stderr, `sys.exit(1)`.
   - `reason.startswith("WARNING:")` → print warning to stdout, continue.
   - No breach → continue silently.
6. Gate applies on BUY only. SELL / `--close` path skips entirely.

**Commit:** `feat(scripts): wire portfolio delta gate into record_paper_trade`

---

## Task B1 — `src/gamma/` package: models + GammaStore  ✅ DONE (d8c2e69)

**Spec:** `docs/strategies/near_expiry_buy_v1.md` §11 — DDL for `gamma_chain_snapshots` and `gamma_watchlist`.
Scaffolding only: package + data models + DB store. No script logic. No chain fetching.

**Files created:**
- `src/gamma/__init__.py`, `src/gamma/models.py`, `src/gamma/store.py`
- `tests/unit/gamma/__init__.py`, `tests/unit/gamma/test_gamma_store.py`

**Commit:** `feat(gamma): add GammaChainSnapshot models and GammaStore`

---

## Task B2.1 — Script scaffold: CLI flags + expiry resolution  ✅ DONE (b68bb3d)

**Files created:**
- `scripts/gamma_daily_watch.py` — runnable skeleton
- `tests/unit/scripts/test_gamma_daily_watch.py`

**What was built:**
1. `argparse`: `--morning`, `--dry-run`, `--date` flags.
2. Logging: INFO default; DEBUG on `UPSTOX_DEBUG=1`.
3. `resolve_expiries(today) -> tuple[date, date]` via `src/market_calendar`.
4. `main()`: parse → resolve → stub `_fetch_and_snapshot` + `_update_watchlist` → exit 0.

**Commit:** `feat(gamma): scaffold gamma_daily_watch with CLI flags and expiry resolution`

---

## Task B2.2 — Chain fetch + field computation

**Files to change:**
- `scripts/gamma_daily_watch.py` — replace B2.1 stubs with real implementation
- `tests/unit/scripts/test_gamma_daily_watch.py` — add new tests

**Before any code:**
- `search_graph("get_option_chain")` or `trace_path("parse_upstox_option_chain")` — confirm `BrokerClient` method signature
- `get_code_snippet("OptionChain")` — field list
- `get_code_snippet("GammaChainSnapshot")` — field list before constructing instances

**What to implement:**

1. `_fetch_chain(client: BrokerClient, expiry_date: date) -> OptionChain | None`
   Returns `None` on empty/market-closed response; logs WARNING, does not raise.

2. `_compute_snapshots(chain, expiry_date, today, snapshot_time, store, conn) -> list[GammaChainSnapshot]`
   Iterates all strikes within ±10% of spot. Computes:
   - `gamma_gearing = gamma × nifty_spot² / ask_price`
     Guard: if `ask_price is None` or `ask_price <= Decimal("0.50")` → `gamma_gearing = None`,
     log `WARNING: ask_price too low for gearing computation (strike=X, ask=Y)`.
   - `distance_pct = abs(nifty_spot − strike) / nifty_spot`
   - `oi_change_1d`: call `store.get_yesterday_snapshot(...)`. `None` or prior `oi` zero → `None`.
     Otherwise `(today_oi − prior_oi) / prior_oi`.
   - `bid_ask_spread = best_ask − best_bid` (both non-None; else `None`)
   - `dte_calendar = (expiry_date − today).days`

3. `_fetch_and_snapshot(client, expiries, today, snapshot_time, store, conn, dry_run) -> list[GammaChainSnapshot]`
   Calls `_fetch_chain` for each expiry, calls `_compute_snapshots`, collects results.
   `dry_run=True`: logs but does NOT call any store method (persistence is B2.3's job).

**Tests (mock BrokerClient and GammaStore, no network, no SQLite):**
- `test_compute_snapshots_normal`: 2 strikes, mocked yesterday OI → assert correct `oi_change_1d`, `gamma_gearing`, `distance_pct`, `bid_ask_spread`.
- `test_compute_snapshots_ask_guard`: `ask_price = Decimal("0.10")` → `gamma_gearing` is `None`, warning logged, row still in output.
- `test_compute_snapshots_no_prior_oi`: `get_yesterday_snapshot` returns `None` → `oi_change_1d` is `None`.
- `test_fetch_chain_empty_response`: empty chain → `_fetch_chain` returns `None`, warning logged.

**Commit:** `feat(gamma): add chain fetch and field computation to gamma_daily_watch`

---

## Task B2.3 — Snapshot persistence

**Files to change:**
- `scripts/gamma_daily_watch.py` — add persistence inside `_fetch_and_snapshot`
- `tests/unit/scripts/test_gamma_daily_watch.py` — add new tests

**What to implement:**

1. After `_compute_snapshots` returns the list, iterate and call
   `store.insert_chain_snapshot(conn, snap)` for each (unless `dry_run=True`).
2. Log at INFO: `"Snapshot: {N} rows written for expiry {expiry_date}"` after each batch.
   `"dry-run: skipping {N} snapshot writes"` on dry run.
3. Wrap entire fetch+persist loop in `try/except Exception` per expiry — failure on one
   expiry does not abort the other. Log ERROR and continue.

**Tests:**
- `test_persistence_called_per_snapshot`: assert `insert_chain_snapshot` called once per snapshot (3 strikes × 2 option types = 6 calls).
- `test_dry_run_skips_persistence`: `insert_chain_snapshot` NOT called when `dry_run=True`.
- `test_single_expiry_failure_does_not_abort`: mock first expiry to raise `DataFetchError`; assert second expiry is still processed.

**Commit:** `feat(gamma): wire snapshot persistence into gamma_daily_watch`

---

## Task B2.4 — Watchlist maintenance

**Files to change:**
- `scripts/gamma_daily_watch.py` — replace B2.1 stub with real implementation
- `tests/unit/scripts/test_gamma_daily_watch.py` — add new tests

**What to implement:**

`_update_watchlist(today_snaps, current_week_expiry, today, store, conn, dry_run) -> dict`
Returns `{"added": int, "retained": int, "removed": int, "elevated": int}`.

**Inclusion criteria (all five — §5b):**
```
dte_calendar BETWEEN 2 AND 6
distance_pct <= Decimal("0.04")
gamma_gearing >= Decimal("3.0")   (skip if None)
oi >= 1000                         (skip if None)
oi_change_1d >= 0                  (skip if None — treat as neutral pass)
```

**Elevation criteria (all three simultaneously):**
```
distance_pct <= Decimal("0.03")
distance_pct < yesterday's distance_pct
gamma_gearing > 3-day moving average of gamma_gearing for this strike
oi_change_1d >= Decimal("0.10")
```

**Removal criteria (either triggers removal — §5b):**
```
distance_pct > Decimal("0.05") for 2 consecutive days  → removal_reason = "spot_moved_away"
oi_change_1d < Decimal("-0.20") for 2 consecutive days  → removal_reason = "oi_unwinding"
expiry_date < today                                      → removal_reason = "expired"
```
If yesterday's snapshot is missing for consecutive checks: do not remove.
`dry_run=True`: compute stats dict, log what would happen, call no store methods.

**Tests:**
- `test_watchlist_add_qualifying_strike`: all 5 criteria pass → `upsert_watchlist` called, `added = 1`.
- `test_watchlist_skip_low_gearing`: `gamma_gearing = Decimal("2.5")` → not added.
- `test_watchlist_removal_spot_moved_two_days`: both days `distance_pct > 0.05` → removed with `"spot_moved_away"`.
- `test_watchlist_no_removal_on_single_day_breach`: only today breaches → NOT removed.
- `test_watchlist_elevation`: all three elevation criteria pass → `elevated=True` in upserted entry.
- `test_watchlist_expired_removal`: `expiry_date < today` → removed with `"expired"`.
- `test_morning_flag_skips_watchlist`: `_update_watchlist` not called with `--morning`.
- `test_dry_run_no_store_calls`: no store methods called when `dry_run=True`.

**Commit:** `feat(gamma): implement watchlist maintenance in gamma_daily_watch`

---

## Task B2.5 — Percentile calibration + Telegram summary

**Files to change:**
- `scripts/gamma_daily_watch.py` — add `_run_calibration()` and Telegram wire-up
- `tests/unit/scripts/test_gamma_daily_watch.py` — add new tests

**What to implement:**

1. `_run_calibration(today_snaps, today, store, conn, dry_run) -> None`

   Per unique `(strike, option_type)` in `today_snaps`:
   - `store.get_iv_history(conn, strike, option_type, limit_days=20)`.
   - `len(history) < 20`: log `WARNING: insufficient history for IV percentile (strike=X, opt=Y, days=N)` and skip.
   - Else: `strike_iv_pctile_20d = sum(1 for v in history if v <= today_iv) / len(history)`.
   - Update via `store.insert_chain_snapshot` (upsert overwrites `strike_iv_pctile_20d`).

   DTE-bucket gearing percentile (`gamma_gearing_pctile_dte`):
   - Per DTE value in `today_snaps`: `store.get_gearing_by_dte(conn, target_dte, limit_days=60)`.
   - `len < 20`: log warning, skip bucket.
   - Else: compute percentile, update affected rows via upsert.
   - `dry_run=True`: compute but do not write.

2. Telegram: after all stages, `build_notifier()` and send:
   `"Gamma watch: {captured} strikes captured, {watchlist} on watchlist, {elevated} elevated, {added} added, {removed} removed"`
   Non-fatal: `try/except`, log WARNING on failure. Skip entirely on `dry_run=True`.

**Tests:**
- `test_calibration_skipped_insufficient_history`: 15 values → `insert_chain_snapshot` NOT called, warning logged.
- `test_calibration_writes_percentile`: 20 values → percentile correct, `insert_chain_snapshot` called.
- `test_calibration_dry_run`: `insert_chain_snapshot` NOT called when `dry_run=True`.
- `test_telegram_summary_sent`: mock `build_notifier`; assert correct message template.
- `test_telegram_failure_non_fatal`: notifier raises → no reraise, WARNING logged.
- `test_full_pipeline_integration`: end-to-end with all mocks — assert all stages run in order.

**Commit:** `feat(gamma): add percentile calibration and Telegram summary to gamma_daily_watch`

---

*Phase B (`gamma_scan.py`) is a separate story. Do not start it here.*
