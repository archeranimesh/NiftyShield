# risk-gamma-phase-a — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: tick `tasks.md`, append the
> completion tail `| Owner: <Claude|Antigravity|Animesh> | Model: <model-id|n/a> | SHA: <sha>`, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## Task A — Wire `src/risk/` delta gate into `record_paper_trade.py`  ✅ DONE (b9c00146)

**What exists:** `src/risk/` is fully implemented and tested (20 unit tests green). `PortfolioDeltaTracker` + `check_entry_allowed` are not yet called from any entry script.

**Files changed:**
- `scripts/record_paper_trade.py` — delta gate check on BUY actions only
- Test file covering `record_paper_trade.py` — gate integration tests

**Implementation:**

1. After Nifty spot is fetched, load all open `PaperPosition` objects across all strategies.
2. Instantiate `PortfolioDeltaTracker()` with default thresholds. Call `aggregate_delta(positions, nifty_spot, LOT_SIZE)`. (`LOT_SIZE` in `src/paper/constants.py`.)
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

**Spec:** `docs/strategies/near_expiry_buy_v1.md` §11 — DDL for `gamma_chain_snapshots` and `gamma_watchlist`. Scaffolding only: package + data models + DB store. No script logic. No chain fetching.

**Files created:**
- `src/gamma/__init__.py`, `src/gamma/models.py`, `src/gamma/store.py`
- `tests/unit/gamma/__init__.py`, `tests/unit/gamma/test_gamma_store.py`

**Commit:** `feat(gamma): add GammaChainSnapshot models and GammaStore`

---

## Task B2.1 — Script scaffold: CLI flags + expiry resolution  ✅ DONE (b68bb3d)

**Files created:**
- `scripts/pipeline/gamma_daily_watch.py` — runnable skeleton
- `tests/unit/scripts/test_gamma_daily_watch.py`

**What was built:**
1. `argparse`: `--morning`, `--dry-run`, `--date` flags.
2. Logging: INFO default; DEBUG on `UPSTOX_DEBUG=1`.
3. `resolve_expiries(today) -> tuple[date, date]` via `src/market_calendar`.
4. `main()`: parse → resolve → stub `_fetch_and_snapshot` + `_update_watchlist` → exit 0.

**Commit:** `feat(gamma): scaffold gamma_daily_watch with CLI flags and expiry resolution`

---

## Task B2.2 — Chain fetch + field computation  ✅ DONE

> Built deviations: added `GammaStore.get_prior_oi` (batched prior-day OI); `prior_oi` keys are `(int strike, option_type)` to match `GammaChainSnapshot.strike`; `bid_ask_spread` is `None` when bid or
> ask is 0 (`OptionLeg` encodes a missing price as 0); client is `UpstoxMarketClient` (sync `get_option_chain_sync`, as in the other pipeline scripts) — `BrokerClient` only exposes the async variant.

**Files to change:**
- `src/gamma/derive.py` — **new**: pure `derive_snapshots` (shared with Phase B `gamma_scan.py`; no store access, no I/O)
- `tests/unit/gamma/test_derive.py` — **new**
- `scripts/pipeline/gamma_daily_watch.py` — replace B2.1 stubs: thin `_fetch_chain` adapter + `_fetch_and_snapshot` orchestration
- `tests/unit/scripts/test_gamma_daily_watch.py` — add new tests
- `src/gamma/CLAUDE.md` — document `derive.py` and the one-way rule (`src/gamma/` never imports from `scripts/`)

**Design (refactor review):** the derived-field maths is mechanism logic that Phase B also needs (`gamma-scan-phase-b` B-2 step 5a), so it lives in `src/gamma/`, not in the script. The prior-day OI is
fetched once per expiry by the script and passed in as a mapping — this replaces a per-strike `get_yesterday_snapshot` call (N+1 queries over ~100+ strikes × 2 expiries).

**Before any code:**
- `search_graph("get_option_chain")` or `trace_path("parse_upstox_option_chain")` — confirm `BrokerClient` method signature
- `get_code_snippet("OptionChain")` — field list
- `get_code_snippet("GammaChainSnapshot")` — field list before constructing instances

**What to implement:**

1. `_fetch_chain(client: BrokerClient, expiry_date: date) -> OptionChain | None` Returns `None` on empty/market-closed response; logs WARNING, does not raise.

2. `derive_snapshots(chain, expiry_date, today, snapshot_time, prior_oi: Mapping[tuple[Decimal, str], int]) -> list[GammaChainSnapshot]` in `src/gamma/derive.py` — pure; `prior_oi` is keyed by
   `(strike, option_type)` and holds yesterday's OI (the script builds it from one batched store lookup per expiry). Iterates all strikes within ±10% of spot. Computes:
   - `gamma_gearing = gamma × nifty_spot² / ask_price` Guard: if `ask_price is None` or `ask_price <= Decimal("0.50")` → `gamma_gearing = None`, log `WARNING: ask_price too low for gearing computation
     (strike=X, ask=Y)`.
   - `distance_pct = abs(nifty_spot − strike) / nifty_spot`
   - `oi_change_1d`: look up `prior_oi[(strike, option_type)]`. Missing or zero → `None`. Otherwise `(today_oi − prior_oi) / prior_oi`.
   - `bid_ask_spread = best_ask − best_bid` (both non-None; else `None`)
   - `dte_calendar = (expiry_date − today).days`

3. `_fetch_and_snapshot(client, expiries, today, snapshot_time, store, conn, dry_run) -> list[GammaChainSnapshot]` Calls `_fetch_chain` for each expiry, builds `prior_oi` from one store lookup, calls
   `derive_snapshots`, collects results. `dry_run=True`: logs but does NOT call any store method (persistence is B2.3's job).

**Tests (no network, no SQLite; `derive_snapshots` tests need no mocks at all):**
- `test_derive_snapshots_normal` (`test_derive.py`): 2 strikes, `prior_oi` mapping → assert correct `oi_change_1d`, `gamma_gearing`, `distance_pct`, `bid_ask_spread`.
- `test_derive_snapshots_ask_guard`: `ask_price = Decimal("0.10")` → `gamma_gearing` is `None`, warning logged, row still in output.
- `test_derive_snapshots_no_prior_oi`: strike absent from `prior_oi` (or prior OI zero) → `oi_change_1d` is `None`.
- `test_fetch_chain_empty_response` (script test, mock `BrokerClient`): empty chain → `_fetch_chain` returns `None`, warning logged.
- `test_fetch_and_snapshot_batches_prior_oi` (script test, mock `GammaStore`): the prior-OI store lookup runs once per expiry, not once per strike.

**Commit:** `feat(gamma): add derive_snapshots and chain fetch to daily watch`

---

## Task B2.3 — Snapshot persistence

**Files to change:**
- `scripts/pipeline/gamma_daily_watch.py` — add persistence inside `_fetch_and_snapshot`
- `tests/unit/scripts/test_gamma_daily_watch.py` — add new tests

**What to implement:**

1. After `derive_snapshots` returns the list, iterate and call `store.insert_chain_snapshot(conn, snap)` for each (unless `dry_run=True`).
2. Log at INFO: `"Snapshot: {N} rows written for expiry {expiry_date}"` after each batch. `"dry-run: skipping {N} snapshot writes"` on dry run.
3. Wrap the per-expiry fetch+persist step in `try/except DataFetchError` (and the store's own error type, if `GammaStore` raises one — check before coding) — failure on one expiry does not abort the
   other. Log ERROR and continue. Do **not** use a bare `except Exception`: it would swallow programming errors; per the code-review checklist, wrap only the fetch/store boundary exceptions.

**Tests:**
- `test_persistence_called_per_snapshot`: assert `insert_chain_snapshot` called once per snapshot (3 strikes × 2 option types = 6 calls).
- `test_dry_run_skips_persistence`: `insert_chain_snapshot` NOT called when `dry_run=True`.
- `test_single_expiry_failure_does_not_abort`: mock first expiry to raise `DataFetchError`; assert second expiry is still processed.

**Commit:** `feat(gamma): wire snapshot persistence into gamma_daily_watch`

---

## Task B2.4 — Watchlist maintenance

**Files to change:**
- `src/gamma/watchlist.py` — **new**: pure `evaluate_watchlist` holding the §5b add / elevate / remove rules (no store access)
- `tests/unit/gamma/test_watchlist.py` — **new**: the rule tests below
- `scripts/pipeline/gamma_daily_watch.py` — replace B2.1 stub: `_update_watchlist` gathers history from the store, calls `evaluate_watchlist`, applies the decision
- `tests/unit/scripts/test_gamma_daily_watch.py` — add the orchestration tests
- `src/gamma/CLAUDE.md` — document `watchlist.py`

**Design (refactor review):** the rules are fixed by §5b with a single caller, so keep them as plain code with thresholds as module constants — no rule registry. Extracting them as a pure function is
for testability and single responsibility (the script is the most logic-dense file in the story), not for Phase B reuse: Phase B only *reads* `get_active_watchlist` to tag `watchlist_hit`. Leaving the
rules in the script is defensible; if so, drop the `watchlist.py` file lines above.

**What to implement:**

`evaluate_watchlist(today_snaps, history, today) -> WatchlistDecision` (frozen dataclass: `add`, `elevate`, `remove` lists, where each removal carries its `removal_reason`; `history` holds the
yesterday / 3-day-gearing / consecutive-day inputs gathered by the script). `_update_watchlist(today_snaps, current_week_expiry, today, store, conn, dry_run) -> dict` in the script applies the
decision through the store and returns `{"added": int, "retained": int, "removed": int, "elevated": int}`.

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
If yesterday's snapshot is missing for consecutive checks: do not remove. `dry_run=True`: compute stats dict, log what would happen, call no store methods.

**Tests:** the first six are pure `evaluate_watchlist` tests in `test_watchlist.py` (no mocks); the last two are script tests with a mock `GammaStore`.
- `test_watchlist_add_qualifying_strike`: all 5 criteria pass → strike in `decision.add`.
- `test_watchlist_skip_low_gearing`: `gamma_gearing = Decimal("2.5")` → not added.
- `test_watchlist_removal_spot_moved_two_days`: both days `distance_pct > 0.05` → removed with `"spot_moved_away"`.
- `test_watchlist_no_removal_on_single_day_breach`: only today breaches → NOT removed.
- `test_watchlist_elevation`: all three elevation criteria pass → strike in `decision.elevate`.
- `test_watchlist_expired_removal`: `expiry_date < today` → removed with `"expired"`.
- `test_morning_flag_skips_watchlist`: `_update_watchlist` not called with `--morning`.
- `test_dry_run_no_store_calls`: no store write methods called when `dry_run=True`.

**Commit:** `feat(gamma): add watchlist maintenance to daily watch`

---

## Task B2.5 — Percentile calibration + Telegram summary

**Files to change:**
- `src/gamma/store.py` — add `GammaStore.update_percentiles` (writes only the two percentile columns for one snapshot key)
- `tests/unit/gamma/test_gamma_store.py` — test `update_percentiles` (happy path + unknown-key no-op)
- `scripts/pipeline/gamma_daily_watch.py` — add `_run_calibration()` and Telegram wire-up
- `tests/unit/scripts/test_gamma_daily_watch.py` — add new tests

**Design (refactor review):** calibration re-upserting whole snapshot rows through `insert_chain_snapshot` just to set one column is wrong-shaped, so the percentile writes go through a targeted
`update_percentiles`. The percentile maths is ~10 lines used once — keep it as a pure helper in the script; do not create `src/gamma/calibration.py`. Phase B Layer 3 only *reads* these columns.

**What to implement:**

1. `_run_calibration(today_snaps, today, store, conn, dry_run) -> None`

Per unique `(strike, option_type)` in `today_snaps`:
   - `store.get_iv_history(conn, strike, option_type, limit_days=20)`.
   - `len(history) < 20`: log `WARNING: insufficient history for IV percentile (strike=X, opt=Y, days=N)` and skip.
   - Else: `strike_iv_pctile_20d = sum(1 for v in history if v <= today_iv) / len(history)`.
   - Update via `store.update_percentiles` (sets `strike_iv_pctile_20d` only).

DTE-bucket gearing percentile (`gamma_gearing_pctile_dte`):
   - Per DTE value in `today_snaps`: `store.get_gearing_by_dte(conn, target_dte, limit_days=60)`.
   - `len < 20`: log warning, skip bucket.
   - Else: compute percentile, update affected rows via `store.update_percentiles`.
   - `dry_run=True`: compute but do not write.

2. Telegram: after all stages, `build_notifier()` and send: `"Gamma watch: {captured} strikes captured, {watchlist} on watchlist, {elevated} elevated, {added} added, {removed} removed"` Non-fatal:
   `try/except`, log WARNING on failure. Skip entirely on `dry_run=True`.

**Tests:**
- `test_calibration_skipped_insufficient_history`: 15 values → `update_percentiles` NOT called, warning logged.
- `test_calibration_writes_percentile`: 20 values → percentile correct, `update_percentiles` called.
- `test_calibration_dry_run`: `update_percentiles` NOT called when `dry_run=True`.
- `test_telegram_summary_sent`: mock `build_notifier`; assert correct message template.
- `test_telegram_failure_non_fatal`: notifier raises → no reraise, WARNING logged.
- `test_full_pipeline_integration`: end-to-end with all mocks — assert all stages run in order.

**Commit:** `feat(gamma): add percentile calibration and Telegram summary`

---

*Phase B (`gamma_scan.py`) is the sibling story `../gamma-scan-phase-b/` in this epic. Do not start it here.*
