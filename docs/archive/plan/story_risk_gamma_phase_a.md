# Risk Wiring + Gamma Phase A — Implementation Story

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Do not look at any other unchecked item. One task. Complete it fully. Stop.

---

## Task A — Wire `src/risk/` delta gate into `record_paper_trade.py`

**What exists:** `src/risk/` is fully implemented and tested (20 unit tests green).
`PortfolioDeltaTracker` + `check_entry_allowed` are not yet called from any entry script.

**Files to change:**
- `scripts/record_paper_trade.py` — add delta gate check on BUY actions only
- Test file covering `record_paper_trade.py` (find via `search_graph("record_paper_trade")`) — add gate integration tests

**What to implement:**

1. After Nifty spot is fetched (it is already fetched in the script — find it via the graph,
   do not assume the variable name), load all open `PaperPosition` objects across all
   strategies. Use `search_graph("PaperStore")` to find the correct method — do not guess.

2. Instantiate `PortfolioDeltaTracker()` with default thresholds.
   Call `aggregate_delta(positions, nifty_spot, LOT_SIZE)`.
   (`LOT_SIZE` is in `src/paper/constants.py`.)

3. Determine `is_protective`:
   - `True` when `action == "BUY"` and `"PE"` in the resolved instrument key
     (long put = hedge, reduces directional exposure).
   - `False` for all other BUY actions (CE, futures-like positions).

4. For `trade_delta_lots`: pass `Decimal("0")` — the gate decision uses pre-trade state
   only (see `src/risk/entry_gate.py` docstring). The value only appears in the warning
   string; zero is safe and avoids key-resolution complexity at gate-check time.

5. Call `check_entry_allowed(portfolio_delta, Decimal("0"), is_protective)`.
   - `allowed is False` → print the reason to stderr, `sys.exit(1)`.
   - `reason.startswith("WARNING:")` → print warning to stdout, continue with the trade.
   - No breach → continue silently.

6. Gate applies on BUY actions only. The SELL / `--close` path skips the gate entirely.

**Tests (no network, mock everything):**

- Gate blocks when `cap_breached=True`: mock `PortfolioDeltaTracker.aggregate_delta`
  to return a `PortfolioDelta` with `cap_breached=True`; assert script exits 1.
- Gate warns but continues when `warning_breached=True`: assert warning printed, trade proceeds.
- Gate passes silently when no breach.
- Gate is skipped on `--action SELL` / `--close` path.
- `BUY PE` bypasses gate even when `cap_breached=True` (`is_protective=True`).

**Commit:** `feat(scripts): wire portfolio delta gate into record_paper_trade`

- [x] **A** — Wire `src/risk/` delta gate into `record_paper_trade.py` | SHA: b9c00146e2bb268aa0d8449a295e0d92c17cfab1

---

## Task B1 — `src/gamma/` package: models + GammaStore

**Spec:** `docs/strategies/near_expiry_buy_v1.md` §11 — full DDL for `gamma_chain_snapshots`
and `gamma_watchlist`. This task is scaffolding only: package + data models + DB store.
No script logic. No chain fetching.

**Files to change:**
- `src/gamma/__init__.py` — package stub (one comment line, no imports)
- `src/gamma/models.py` — frozen dataclasses for `GammaChainSnapshot` and `GammaWatchlistEntry`
- `src/gamma/store.py` — `GammaStore` class
- `tests/unit/gamma/__init__.py` — test package stub
- `tests/unit/gamma/test_gamma_store.py` — store tests (in-memory SQLite via `src/db.py` pattern)

**Models (`src/gamma/models.py`):**

`GammaChainSnapshot` — one row of `gamma_chain_snapshots`. Field types:
- `snapshot_date: datetime.date`, `snapshot_time: str` (HH:MM), `expiry_date: datetime.date`
- `strike: int`, `option_type: str` (CE|PE), `dte_calendar: int`
- All price/Greek/derived fields: `Decimal | None` (stored as TEXT in DB, same Decimal TEXT invariant as the rest of the codebase)
- `oi: int | None`, `volume_day: int | None`
- `created_at: datetime` (UTC)

`GammaWatchlistEntry` — one row of `gamma_watchlist`. Field types follow §11 schema.
`elevated: bool`, `removed_date: datetime.date | None`, `removal_reason: str | None`.
`days_on_watchlist: int`.

**`GammaStore` public methods:**
- `create_tables(conn) → None` — DDL from §11, `CREATE TABLE IF NOT EXISTS`
- `insert_chain_snapshot(conn, snap: GammaChainSnapshot) → None` — upsert on
  `(snapshot_date, snapshot_time, expiry_date, strike, option_type)`
- `get_chain_snapshots(conn, expiry_date: datetime.date, snapshot_date: datetime.date) → list[GammaChainSnapshot]`
- `get_yesterday_snapshot(conn, expiry_date: datetime.date, strike: int, option_type: str, today: datetime.date) → GammaChainSnapshot | None`
  (used to compute `oi_change_1d` — returns the most recent snapshot for that strike before today)
- `upsert_watchlist(conn, entry: GammaWatchlistEntry) → None`
  — INSERT on first add, UPDATE `last_seen_date` + current state fields on subsequent calls;
  UNIQUE constraint is `(expiry_date, strike, option_type)`
- `get_active_watchlist(conn, expiry_date: datetime.date) → list[GammaWatchlistEntry]`
  — WHERE `removed_date IS NULL`
- `remove_from_watchlist(conn, expiry_date: datetime.date, strike: int, option_type: str, reason: str, removed_date: datetime.date) → None`
  — sets `removed_date` + `removal_reason`; does NOT delete the row

Use the `src/db.py` shared connection pattern. Pass `conn` as a parameter — `GammaStore`
holds no state (same pattern as `PaperStore` — verify with `search_graph("PaperStore")`
before writing). Use `get_code_snippet("GammaChainSnapshot")` after writing to verify
field names before constructing instances in tests.

**Tests:** in-memory SQLite for all. Happy path + edge case per public method.
Round-trip test: insert → retrieve → assert fields match including Decimal precision.

**Commit:** `feat(gamma): add GammaChainSnapshot models and GammaStore`

After commit: re-index codebase — run `mcp__codebase-memory-mcp__index_repository` with
project ID `Users-abhadra-myWork-myCode-python-NiftyShield`.

- [x] **B1** — `src/gamma/` package scaffolding: models + GammaStore | SHA: d8c2e69

---

## Task B2 — `scripts/gamma_daily_watch.py` (split into 5 sub-tasks)

> Each sub-task is one Antigravity session, one commit. Do not combine. The next sub-task
> may not start until the prior SHA is confirmed and all tests are green.

---

### Task B2.1 — Script scaffold: CLI flags + expiry resolution

**What to build:** The runnable skeleton of `gamma_daily_watch.py`. No chain fetch, no DB
writes. Just argument parsing, logging setup, expiry resolution, and the main entry point
that calls (stubbed) stage functions.

**Files to create/change:**
- `scripts/gamma_daily_watch.py` — new file
- `tests/unit/scripts/__init__.py` — new stub (only if it does not already exist)
- `tests/unit/scripts/test_gamma_daily_watch.py` — new file

**What to implement:**

1. `argparse` setup: `--morning` (bool flag), `--dry-run` (bool flag), `--date` (optional
   override, format `YYYY-MM-DD`, defaults to today — useful for manual backfill runs).

2. Logging: structured output via standard `logging`. INFO level default; `DEBUG` when
   `UPSTOX_DEBUG=1`. Log format: `%(asctime)s %(levelname)s %(message)s`.

3. `resolve_expiries(today: datetime.date) -> tuple[datetime.date, datetime.date]` —
   returns `(current_week_expiry, next_week_expiry)` both as `datetime.date`.
   Use `src/market_calendar` — verify API via `search_graph("market_calendar")` before
   writing. Do not hardcode. Current-week = next or current Thursday (if today is Thursday
   and market is open, use today). Next-week = the Thursday after that.

4. `main()` entry point: parse args → resolve expiries → log resolved dates → call stub
   functions `_fetch_and_snapshot(...)` and `_update_watchlist(...)` (both `pass` for now)
   → exit 0. Respects `--morning` (skip `_update_watchlist` call).

**Tests:**
- `test_resolve_expiries_mid_week`: Monday input → correct Thu + following Thu returned.
- `test_resolve_expiries_on_thursday`: Thursday input → same Thursday as current-week expiry.
- `test_morning_flag_skips_watchlist`: mock `_update_watchlist`; assert it is NOT called
  when `--morning` is passed.
- `test_dry_run_flag_propagates`: assert `dry_run=True` flows into `_fetch_and_snapshot`.

**Commit:** `feat(gamma): scaffold gamma_daily_watch with CLI flags and expiry resolution`

- [x] **B2.1** — Script scaffold: CLI + expiry resolution | SHA: b68bb3d

---

### Task B2.2 — Chain fetch + field computation

**What to build:** The `_fetch_and_snapshot()` function and all pure computation helpers.
No DB writes yet — function returns a `list[GammaChainSnapshot]`.

**Files to change:**
- `scripts/gamma_daily_watch.py` — replace the B2.1 stub with the real implementation
- `tests/unit/scripts/test_gamma_daily_watch.py` — add new tests

**What to implement:**

1. `_fetch_chain(client: BrokerClient, expiry_date: datetime.date) -> OptionChain | None` —
   fetches option chain via `BrokerClient`. Returns `None` on empty/market-closed response;
   logs WARNING and returns early (do not raise).
   Verify `BrokerClient` method signature via `search_graph("get_option_chain")` or
   `trace_path("parse_upstox_option_chain")` before writing.

2. `_compute_snapshots(chain: OptionChain, expiry_date: datetime.date, today: datetime.date,
   snapshot_time: str, store: GammaStore, conn: sqlite3.Connection) -> list[GammaChainSnapshot]` —
   iterates all strikes within ±10% of spot and computes:
   - `gamma_gearing = gamma × nifty_spot² / ask_price`
     Guard: if `ask_price` is `None` or `ask_price <= Decimal("0.50")` → set `gamma_gearing = None`,
     log `WARNING: ask_price too low for gearing computation (strike=X, ask=Y)`.
   - `distance_pct = abs(nifty_spot − strike) / nifty_spot`
   - `oi_change_1d`: call `store.get_yesterday_snapshot(...)`. If `None` or prior `oi` is
     `None` or zero → set `oi_change_1d = None`. Otherwise
     `(today_oi − prior_oi) / prior_oi`.
   - `bid_ask_spread = best_ask − best_bid` (both must be non-None; else `None`)
   - `dte_calendar = (expiry_date − today).days`
   Returns the constructed `list[GammaChainSnapshot]`.

3. `_fetch_and_snapshot(client, expiries, today, snapshot_time, store, conn, dry_run) -> list[GammaChainSnapshot]` —
   calls `_fetch_chain` for each expiry, calls `_compute_snapshots`, collects results.
   If `dry_run=True`, logs computed rows but does NOT call any store method here (persistence
   is B2.3's responsibility — this function only returns the list).

**Tests (mock BrokerClient and GammaStore, no network, no SQLite):**
- `test_compute_snapshots_normal`: mocked chain with 2 strikes, mocked
  `get_yesterday_snapshot` returning prior OI → assert correct `oi_change_1d`,
  `gamma_gearing`, `distance_pct`, `bid_ask_spread`.
- `test_compute_snapshots_ask_guard`: strike with `ask_price = Decimal("0.10")` →
  `gamma_gearing` is `None`, warning logged, row still in output.
- `test_compute_snapshots_no_prior_oi`: `get_yesterday_snapshot` returns `None` →
  `oi_change_1d` is `None`.
- `test_fetch_chain_empty_response`: `BrokerClient` returns empty chain → `_fetch_chain`
  returns `None`, warning logged.

**Commit:** `feat(gamma): add chain fetch and field computation to gamma_daily_watch`

- [ ] **B2.2** — Chain fetch + field computation

---

### Task B2.3 — Snapshot persistence

**What to build:** Wire `GammaStore.insert_chain_snapshot` into `_fetch_and_snapshot`.
The script now writes to `gamma_chain_snapshots` after computing. `--dry-run` bypasses
the writes.

**Files to change:**
- `scripts/gamma_daily_watch.py` — add persistence call inside `_fetch_and_snapshot`
- `tests/unit/scripts/test_gamma_daily_watch.py` — add new tests

**What to implement:**

1. After `_compute_snapshots` returns the list, iterate and call
   `store.insert_chain_snapshot(conn, snap)` for each item (unless `dry_run=True`).

2. Log at INFO level: `"Snapshot: {N} rows written for expiry {expiry_date}"` after each
   expiry batch. Log `"dry-run: skipping {N} snapshot writes"` when dry run.

3. Wrap the entire fetch+persist loop in a `try/except Exception` per expiry — a failure
   on one expiry should not abort the other. Log ERROR and continue.

**Tests:**
- `test_persistence_called_per_snapshot`: mock `GammaStore.insert_chain_snapshot`; assert
  it is called once per computed snapshot (3 strikes × 2 option types = 6 calls for a
  chain with 3 strikes).
- `test_dry_run_skips_persistence`: `insert_chain_snapshot` NOT called when
  `dry_run=True`.
- `test_single_expiry_failure_does_not_abort`: mock first expiry fetch to raise
  `DataFetchError`; assert second expiry is still processed.

**Commit:** `feat(gamma): wire snapshot persistence into gamma_daily_watch`

- [ ] **B2.3** — Snapshot persistence

---

### Task B2.4 — Watchlist maintenance

**What to build:** The `_update_watchlist()` function. Implements all §5b add/retain/remove/
elevate logic for the current-week expiry. Skipped when `--morning` is passed.

**Files to change:**
- `scripts/gamma_daily_watch.py` — replace B2.1 stub with real implementation
- `tests/unit/scripts/test_gamma_daily_watch.py` — add new tests

**What to implement:**

`_update_watchlist(today_snaps: list[GammaChainSnapshot], current_week_expiry: datetime.date,
today: datetime.date, store: GammaStore, conn: sqlite3.Connection, dry_run: bool) -> dict` —
returns a stats dict `{"added": int, "retained": int, "removed": int, "elevated": int}`.

Inclusion criteria (all five must hold, §5b):
```
dte_calendar BETWEEN 2 AND 6
distance_pct <= Decimal("0.04")
gamma_gearing >= Decimal("3.0")   (skip if None)
oi >= 1000                         (skip if None)
oi_change_1d >= 0                  (skip if None — treat missing OI change as neutral pass)
```

Elevation criteria (all three must hold simultaneously):
```
distance_pct <= Decimal("0.03")
distance_pct < yesterday's distance_pct   (use get_yesterday_snapshot to get prior distance_pct)
gamma_gearing > 3-day moving average of gamma_gearing for this strike
    (use get_iv_history pattern via direct SQL or a helper — 3 values is sufficient)
oi_change_1d >= Decimal("0.10")
```

Removal criteria (either triggers removal, §5b):
```
distance_pct > Decimal("0.05") for 2 consecutive days
    → check yesterday's snapshot; removal_reason = "spot_moved_away"
oi_change_1d < Decimal("-0.20") for 2 consecutive days
    → check yesterday's snapshot; removal_reason = "oi_unwinding"
expiry_date < today
    → removal_reason = "expired"
```
For the consecutive-day checks: if yesterday's snapshot is missing, do not remove
(insufficient evidence).

If `dry_run=True`: compute the full stats dict, log what would be written, but call no
store methods.

**Tests:**
- `test_watchlist_add_qualifying_strike`: strike passes all 5 criteria →
  `upsert_watchlist` called, `added` count = 1.
- `test_watchlist_skip_low_gearing`: `gamma_gearing = Decimal("2.5")` → not added.
- `test_watchlist_removal_spot_moved_two_days`: yesterday + today both have
  `distance_pct > 0.05` → `remove_from_watchlist` called with `"spot_moved_away"`.
- `test_watchlist_no_removal_on_single_day_breach`: only today breaches distance →
  NOT removed (insufficient consecutive evidence).
- `test_watchlist_elevation`: all three elevation criteria pass →
  `elevated=True` in the upserted entry.
- `test_watchlist_expired_removal`: `expiry_date < today` → removed with `"expired"`.
- `test_morning_flag_skips_watchlist`: `_update_watchlist` not called when
  `--morning` passed (tested at the `main()` level).
- `test_dry_run_no_store_calls`: store methods not called when `dry_run=True`.

**Commit:** `feat(gamma): implement watchlist maintenance in gamma_daily_watch`

- [ ] **B2.4** — Watchlist maintenance

---

### Task B2.5 — Percentile calibration + Telegram summary

**What to build:** The final two pipeline stages: rolling percentile backfill into
`gamma_chain_snapshots` and the Telegram EOD summary. This closes B2.

**Files to change:**
- `scripts/gamma_daily_watch.py` — add `_run_calibration()` and wire Telegram
- `tests/unit/scripts/test_gamma_daily_watch.py` — add new tests

**What to implement:**

1. `_run_calibration(today_snaps: list[GammaChainSnapshot], today: datetime.date,
   store: GammaStore, conn: sqlite3.Connection, dry_run: bool) -> None`

   For each unique `(strike, option_type)` in `today_snaps`:
   - Call `store.get_iv_history(conn, strike, option_type, limit_days=20)`.
   - If `len(history) < 20`: log
     `WARNING: insufficient history for IV percentile (strike=X, opt=Y, days=N)` and skip.
   - Else: compute percentile rank of today's `iv_val` within `history` using
     `sum(1 for v in history if v <= today_iv) / len(history)`.
   - Update the today snap row via `store.insert_chain_snapshot` (upsert will overwrite
     `strike_iv_pctile_20d` in place).

   For DTE-bucket gearing percentile (`gamma_gearing_pctile_dte`):
   - For each DTE value present in `today_snaps` (typically 2–6):
     call `store.get_gearing_by_dte(conn, target_dte=dte, limit_days=60)`.
   - If `len(history) < 20`: log warning and skip the bucket.
   - Else: compute percentile rank of today's `gamma_gearing` against the history.
   - Update affected snap rows via upsert.

   If `dry_run=True`: compute but do not write.

2. Wire Telegram: after all stages complete, call `build_notifier()` and send:
   `"Gamma watch: {captured} strikes captured, {watchlist} on watchlist, {elevated} elevated, {added} added, {removed} removed"`
   where counts come from the stats dict returned by `_update_watchlist`.
   Non-fatal: wrap in `try/except`, log WARNING on failure, do not reraise.
   Skip entirely when `dry_run=True`.

**Tests:**
- `test_calibration_skipped_insufficient_history`: `get_iv_history` returns 15 values →
  `insert_chain_snapshot` NOT called for that strike, warning logged.
- `test_calibration_writes_percentile`: `get_iv_history` returns 20 values → percentile
  computed correctly, `insert_chain_snapshot` called with updated `strike_iv_pctile_20d`.
- `test_calibration_dry_run`: `insert_chain_snapshot` NOT called when `dry_run=True`.
- `test_telegram_summary_sent`: mock `build_notifier`; assert notifier called with the
  correct message template.
- `test_telegram_failure_non_fatal`: notifier raises `Exception` → script does not
  reraise, logs WARNING.
- `test_full_pipeline_integration`: end-to-end with all mocks wired — mocked chain,
  mocked store, mocked notifier — assert all stages run in order and stats are correct.

**Commit:** `feat(gamma): add percentile calibration and Telegram summary to gamma_daily_watch`

- [ ] **B2.5** — Percentile calibration + Telegram summary

---

*Phase B (`gamma_scan.py`) is a separate story. Do not start it here.*
