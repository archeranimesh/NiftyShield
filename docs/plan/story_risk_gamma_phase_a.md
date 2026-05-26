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

- [x] **B1** — `src/gamma/` package scaffolding: models + GammaStore | SHA: d785b9e

---

## Task B2 — `scripts/gamma_daily_watch.py`

**Spec:** `docs/strategies/near_expiry_buy_v1.md` §5 (Phase A logic) and §12 (responsibilities 1–8).
This task is the EOD cron script. Depends on B1 (GammaStore) being green first.

**Files to change:**
- `scripts/gamma_daily_watch.py` — the full Phase A script
- `tests/unit/scripts/test_gamma_daily_watch.py` — unit tests with mocked chain + mocked GammaStore

**What the script does (from §12):**

1. Determine expiry dates: current-week expiry (next or current Thursday) + the following
   Thursday. Use `src/market_calendar` — verify API via `search_graph("market_calendar")`
   before writing. Do not hardcode dates.

2. Fetch Upstox option chain for both expiries via `BrokerClient` (obtained from `factory.py`
   — verify factory API via `search_graph("factory")`). Use `parse_upstox_option_chain`
   from `src/client/upstox_market.py`.

3. For each strike within ±10% of spot on both expiries, compute:
   - `gamma_gearing = gamma × nifty_spot² / ask_price`  (see §4)
   - `distance_pct = |nifty_spot − strike| / nifty_spot`
   - `oi_change_1d` = fractional change vs yesterday's `gamma_chain_snapshots` row for
     the same `(expiry_date, strike, option_type)` (use `GammaStore.get_yesterday_snapshot`)
   - `bid_ask_spread = best_ask − best_bid`

4. Upsert all computed rows into `gamma_chain_snapshots` via `GammaStore.insert_chain_snapshot`.

5. Update `gamma_watchlist` for the current-week expiry:
   - Add qualifying strikes (all five criteria from §5b).
   - Update `last_seen_date` + current state for already-listed strikes.
   - Mark removals for strikes that no longer qualify (two removal criteria from §5b).
   - Set `elevated = True` for priority candidates (three elevation criteria from §5b).

6. Percentile calibration (§5c): recompute `strike_iv_pctile_20d` and `gamma_gearing_p75`
   by DTE bucket only when ≥ 20 days of snapshots exist for the expiry; otherwise log
   `WARNING: insufficient history for percentile calibration (N days)` and skip.
   Store results back into the relevant `gamma_chain_snapshots` rows.

7. Telegram summary via `build_notifier()` from `src/notifications/`:
   `"Gamma watch: {N} strikes captured, {N} on watchlist, {N} elevated, {N} added, {N} removed"`
   Non-fatal — log warning on failure, do not abort.

8. Support `--morning` flag: when passed, run steps 1–4 only (snapshot, no watchlist update).
   Used for the optional 10:30 IST baseline cron.

9. Support `--dry-run` flag: fetch + compute + log, but do not write to DB or send Telegram.

**Tests (no network, mock all I/O):**
- Happy path: mocked chain with 3 strikes → `GammaStore.insert_chain_snapshot` called 3×,
  watchlist updated, Telegram summary sent.
- `--morning` flag: `upsert_watchlist` is NOT called.
- `--dry-run`: store methods not called, no Telegram.
- Empty chain (market closed): script exits cleanly with a WARNING log, no exception.
- Insufficient history (< 20 days): percentile step skipped, warning logged.

**Commit:** `feat(gamma): implement gamma_daily_watch.py Phase A chain capture`

- [ ] **B2** — `scripts/gamma_daily_watch.py`: Phase A chain capture + watchlist update

---

*Phase B (`gamma_scan.py`) is a separate story. Do not start it here.*
