# NiftyShield — TODOs & Session Log

---

## Open TODOs (priority order)

### 0. Tests for Nuvama options + intraday features (protocol debt)

Both features implemented outside Claude have no unit tests — violates the "every public function needs happy-path + edge-case test" protocol.

Missing test coverage (add to `tests/unit/nuvama/`):

- `test_models.py` — `NuvamaOptionPosition` construction/frozen, `NuvamaOptionsSummary` construction/frozen, `net_pnl` property (unrealized + cumulative_realized)
- `test_options_reader.py` (new file) — `parse_options_positions()`: happy path (OPTIDX + OPTSTK), skips non-option rows, handles flat positions (net_qty=0), handles missing `resp.data.pos`, handles malformed record (KeyError/ValueError/InvalidOperation); `build_options_summary()`: aggregation math, intraday high/low propagation, empty positions list
- `test_store.py` additions — `record_options_snapshot` upsert + idempotency, `get_cumulative_realized_pnl` cross-symbol aggregation, `get_options_snapshot_for_date` retrieval, `record_intraday_positions` inserts + purge-on-call, `get_intraday_extremes` max/min/nifty aggregation, empty-date returns `(None, None, None, None)`

### ~~NEW~~. Market holiday guard for cron scripts — **DONE 2026-04-17**

NSE equity holidays (beyond weekends) cause `daily_snapshot.py` and `nuvama_intraday_tracker.py` to run and produce empty/stale snapshots. Fix: introduce a `src/market_calendar/` module and guard both scripts.

**Phase 1 — `src/market_calendar/` module:**
- `holidays.py`: `load_holidays(year)`, `is_trading_day(d)`, `prev_trading_day(d)`
- `src/market_calendar/data/nse_2026.yaml`: NSE 2026 holiday list (seeded from NSE calendar; in src/ not data/ because data/ is gitignored)
- Tests: `tests/unit/market_calendar/test_holidays.py`

**Phase 2 — Script guards:**
- `scripts/daily_snapshot.py`: early exit if `not is_trading_day(today)`
- `scripts/nuvama_intraday_tracker.py`: same guard
- Fail-open design: if YAML missing for the year, `is_trading_day()` returns `True` (safer than blocking)

**Data gap consequence (already correct):**
- No rows written on holidays — gaps are intentional, not filled
- `get_prev_snapshots()` already uses `MAX(snapshot_date) < d` (calendar-agnostic) — day-delta on the next trading day is correct with no code change needed

**Annual maintenance:** Update `src/market_calendar/data/nse_{year}.yaml` each January from NSE's published holiday calendar.

### 1. Greeks capture
Fix option chain call (`NSE_INDEX|Nifty 50`), define `OptionChain` Pydantic model, implement `_extract_greeks_from_chain()`.
Fixture `nifty_chain_2026-04-07.json` already recorded in `tests/fixtures/responses/` — use it to drive model definition.
Blocked by: nothing. Next after Nuvama integration.

### 3. P&L visualization
Matplotlib script or React dashboard from `daily_snapshots` time series.
Deferred until several weeks of snapshot history exist.
`PortfolioSummary` dataclass already extracted — ready to query.

### 4. Nuvama Session P&L Alignment
Evaluate replacing "All-time Total P&L" in `nuvama_intraday_tracker.py` with "Session Total P&L" (Unrealized + Today's Realized) to strictly match the Nuvama mobile/web UI dashboard. 
Current implementation adds historical ledger (+17k), which differs from Nuvama's -17k session view.

---

## Architecture Review 2026-04-21 — Action Items

Findings from full top-down review using `python-architecture-review.prompt.md` v6.
Items are ordered by priority tier. AR- prefix identifies items from this review.

---

### P0 — Correctness Bugs (fix before next trading day)

These produce wrong numbers silently. No architectural work required — surgical one-line fixes.

#### ~~AR-1~~: Fix `if not raw_ltp:` truthiness check — `src/portfolio/tracker.py:209` — **DONE 2026-04-21**

**Problem:** `prices.get(leg.instrument_key, 0.0)` returns `0.0` when the key is missing. `if not raw_ltp:` catches both `0.0` (missing key) and a legitimately zero LTP (an option expiring worthless). An ITM option that expires at zero is recorded with `entry_price` as its LTP — a materially wrong P&L snapshot.

**Fix:**
```python
# Before
raw_ltp = prices.get(leg.instrument_key, 0.0)
if not raw_ltp:

# After
raw_ltp = prices.get(leg.instrument_key)
if raw_ltp is None:
```

**Tests required:** Add one test case in `tests/unit/portfolio/` asserting that a zero LTP is used as-is (not replaced by entry_price).

#### ~~AR-2~~: Fix `if underlying_price:` truthiness check — `daily_snapshot.py:163, 408` — **DONE 2026-04-21**

Same class of bug. Nifty is never actually zero, so this has no live impact today — but it is semantically wrong and sets a pattern that will eventually catch something.

**Fix:** Both occurrences: `if underlying_price is not None:` instead of `if underlying_price:`.

---

### P1 — Test Coverage Gap (production code with zero tests)

#### ~~AR-3~~: Write tests for all Nuvama options + intraday code paths — **DONE 2026-04-21**

Supersedes and expands TODO-0 above. The options reader and intraday store run every 5 minutes in production with zero unit tests.

Specifically, the `MockNuvamaClient` protocol (AR-9 below) must exist first to make `parse_options_positions` and `build_options_summary` fully testable offline. Until AR-9 is done, write tests that call the pure functions directly with fixture JSON.

**Files:** `tests/unit/nuvama/test_options_reader.py` (new), `tests/unit/nuvama/test_store.py` (additions), `tests/unit/nuvama/test_models.py` (additions). See TODO-0 for the full list of test cases.

**Dependency:** AR-9 (Nuvama protocol) unblocks deeper mock-based tests. Write fixture-driven pure function tests now; extend after AR-9.

---

### P2 — Architecture (complete before Phase 0 CSP expansion)

These must be done before adding a new strategy or data source in Phase 0. Each new integration without these fixes adds another 5–9 fields to `PortfolioSummary` and another non-fatal block in `_async_main`.

#### ~~AR-4~~: Refactor `PortfolioSummary` from flat accumulator to per-source composition — **DONE 2026-04-22**

**Problem:** `PortfolioSummary` (`src/models/portfolio.py:198–277`) has 26 fields, grown by 5–9 per integration (Dhan +10, Nuvama bonds +5, Nuvama options +9). Adding the next source (CSP, Zerodha, anything) requires editing `PortfolioSummary`, `_build_portfolio_summary`, `_format_combined_summary`, `_async_main`, and `_historical_main` — 5 files, 3 layers.

**Fix in three parts:**

*Part 1 — `src/models/portfolio.py`:* Replace the per-source field blocks with typed optional references to the source summaries. Keep only cross-source aggregates as flat fields:
```python
@dataclass(frozen=True)
class PortfolioSummary:
    snapshot_date: date
    total_value: Decimal
    total_invested: Decimal
    total_pnl: Decimal
    total_pnl_pct: Decimal
    total_day_delta: Decimal | None
    etf_value: Decimal
    etf_basis: Decimal
    etf_day_delta: Decimal | None
    options_pnl: Decimal
    options_day_delta: Decimal | None
    finrakshak_day_delta: Decimal | None
    mf_pnl: "PortfolioPnL | None" = None   # TYPE_CHECKING import
    dhan: "DhanPortfolioSummary | None" = None
    nuvama_bonds: "NuvamaBondSummary | None" = None
    nuvama_options: "NuvamaOptionsSummary | None" = None
```
16 fields instead of 26. Adding CSP = one new `Optional[CSPSummary]` field.

*Part 2 — `src/portfolio/summary.py`:* `_build_portfolio_summary` computes only cross-source aggregates from the source totals and stores source summaries as-is. Eliminates the 30+ `field = source.field if source else Decimal("0")` lines and all 14 `# type: ignore[union-attr]` suppressions.

*Part 3 — `src/portfolio/formatting.py`:* `_format_combined_summary` accesses source data via `summary.dhan`, `summary.nuvama_bonds`, etc. (typed) rather than via flat fields copied from the source.

**Files:** `src/models/portfolio.py`, `src/portfolio/summary.py`, `src/portfolio/formatting.py`, test files asserting on `PortfolioSummary` fields.
**Note:** `_async_main` and `_historical_main` do NOT change — they already pass the right objects in.

#### ~~AR-5~~: Type the `object | None` parameters in `_build_portfolio_summary` — **DONE 2026-04-22**

Partially overlaps with AR-4 but has independent value. Even before AR-4 is done, the function can be properly typed using `TYPE_CHECKING`-guarded imports.

**Problem:** `_build_portfolio_summary` has four `object | None` typed parameters and 14 `# type: ignore[union-attr]` suppressions. mypy cannot verify this function.

**Fix:** Add `TYPE_CHECKING` imports at the top of `summary.py` and `formatting.py`:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.mf.tracker import PortfolioPnL
    from src.dhan.models import DhanPortfolioSummary
    from src.nuvama.models import NuvamaBondSummary, NuvamaOptionsSummary
```
Replace `object | None` parameter types with the real types. Remove all 14 `# type: ignore[union-attr]` lines.

**Files:** `src/portfolio/summary.py`, `src/portfolio/formatting.py`, `scripts/daily_snapshot.py`.

#### ~~AR-6~~: Fix `NuvamaBondHolding` historical reconstruction hack — `daily_snapshot.py:231–245` — **DONE 2026-04-22**

**Problem:** `_historical_main` constructs `NuvamaBondHolding` stubs with `qty=1` and `ltp=current_value` to trick the `current_value` property (`ltp × qty`) into returning the stored snapshot value. This is a silent correctness dependency: if `NuvamaBondHolding.current_value` ever gains additional terms (e.g., haircut), the historical path silently diverges.

**Fix:** Store `ltp` and `qty` in `nuvama_holdings_snapshots` (or add a `build_nuvama_summary_from_stored()` that takes `{isin: current_value}` directly and bypasses the holding model). The simplest correct fix is a pure function in `src/nuvama/reader.py` that accepts `{isin: current_value}` and `positions` and builds a `NuvamaBondSummary` without the holding stub trick.

**Files:** `src/nuvama/reader.py`, `src/nuvama/store.py`, `scripts/daily_snapshot.py`.

#### ~~AR-7~~: Make `record_all_snapshots` and `record_all_options_snapshots` atomic — `src/nuvama/store.py` — **DONE 2026-04-22**

**Problem:** Both methods iterate and commit each row in a separate transaction. A mid-iteration crash leaves a partial day's snapshot persisted. Compare with `PortfolioStore.record_snapshots_bulk()` which uses `executemany` in one connection block.

**Fix:** Rewrite both methods to use `executemany` in a single `with connect(...) as conn:` block, matching the `PortfolioStore` pattern.

**Tests required:** Verify idempotency (re-run writes same data) and partial-write rollback (exception mid-batch leaves nothing committed).

---

### P3 — Performance & Structural Correctness

#### AR-8: Replace Python aggregation with SQL GROUP BY in `get_cumulative_realized_pnl` — `src/nuvama/store.py:334`

**Problem:** Fetches all historical `realized_pnl_today` rows with no `GROUP BY` and aggregates by `trade_symbol` in Python. The result set grows unboundedly with every trading day. After one year of daily options recording, this is hundreds of rows fetched on every intraday 5-minute tick.

**Fix:**
```python
# Before
rows = conn.execute(
    "SELECT trade_symbol, realized_pnl_today FROM nuvama_options_snapshots WHERE snapshot_date < ?",
    (before_date.isoformat(),),
).fetchall()
# ... Python loop aggregation

# After
rows = conn.execute(
    """SELECT trade_symbol, SUM(realized_pnl_today) AS cumulative
       FROM nuvama_options_snapshots
       WHERE snapshot_date < ?
       GROUP BY trade_symbol""",
    (before_date.isoformat(),),
).fetchall()
return {row["trade_symbol"]: Decimal(row["cumulative"]) for row in rows}
```

**Tests:** Existing `get_cumulative_realized_pnl` tests will validate the fix with no changes needed.

#### AR-9: Wrap Nuvama APIConnect SDK behind a 2-method protocol — `src/nuvama/`

**Problem:** The Nuvama `apiconnect` SDK is the only external dependency not abstracted behind a protocol. Any SDK upgrade touches `reader.py`, `options_reader.py`, `daily_snapshot.py`, and `nuvama_intraday_tracker.py`. More immediately: it blocks a `MockNuvamaClient` for testing (AR-3).

**Fix:** Add `src/nuvama/protocol.py`:
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class NuvamaClient(Protocol):
    def Holdings(self) -> str: ...
    def NetPosition(self) -> str: ...
```
Update `fetch_nuvama_portfolio()` and `nuvama_intraday_tracker.py` to accept `NuvamaClient` instead of `Any`. Create a `MockNuvamaClient` in `tests/` that returns fixture JSON strings.

**Files:** `src/nuvama/protocol.py` (new), `src/nuvama/reader.py`, `src/nuvama/options_reader.py`, `scripts/nuvama_intraday_tracker.py`, `scripts/daily_snapshot.py`.

#### AR-10: Batch `get_all_positions_for_strategy` to eliminate N+1 DB connections — `src/portfolio/store.py:561`

**Problem:** Opens one connection to get `DISTINCT leg_role, instrument_key`, then calls `get_position()` for each leg — each opens a new connection and fetches all trades. For 7 legs: 8 connections, 7 full `trades` table scans per call. Called twice per snapshot run (`_get_all_overlaid_strategies` + compute loop in `_async_main`).

**Fix:** Replace the loop over `get_position()` with a single SQL aggregate query:
```sql
SELECT leg_role, instrument_key,
       SUM(CASE WHEN action='BUY' THEN quantity ELSE 0 END) AS buy_qty,
       SUM(CASE WHEN action='SELL' THEN quantity ELSE 0 END) AS sell_qty,
       SUM(CASE WHEN action='BUY' THEN quantity * CAST(price AS REAL) ELSE 0 END) AS buy_value
FROM trades
WHERE strategy_name = ?
GROUP BY leg_role, instrument_key
```
Compute `avg_price` from `buy_value / buy_qty` in Python with Decimal (preserving the Decimal invariant). One connection, one query, same result.

**Note:** `price` is TEXT in the DB (Decimal invariant). Fetch raw rows and reconstruct with `Decimal(row["price"])` — do not use `CAST` for the final average.

#### AR-11: Eliminate double LTP fetch in `_async_main` — `scripts/daily_snapshot.py`

**Problem:** `await tracker.record_all_strategies(...)` fetches LTPs internally. Then `_async_main` calls `await tracker.compute_pnl(strategy.name)` for each strategy to get `StrategyPnL` for the summary — a second batch LTP call to Upstox per run.

**Fix:** Have `record_all_strategies` return `dict[str, StrategyPnL]` alongside the snapshot counts, built from the already-fetched prices inside `record_daily_snapshot`. The `compute_pnl` calls in `_async_main` are then replaced by a dict lookup. No API change to the `BrokerClient` protocol required.

#### AR-12: Defer module-level I/O imports in `nuvama_intraday_tracker.py`

**Problem:** `from src.auth.nuvama_verify import load_api_connect` and `from src.nuvama.store import NuvamaStore` are module-level imports. This is inconsistent with `daily_snapshot.py` which explicitly defers all I/O imports into `_async_main`. The intraday tracker cannot be safely imported in tests without the auth chain.

**Fix:** Move `load_api_connect`, `NuvamaStore`, `parse_options_positions`, `create_client`, `LTPFetchError` imports inside `async def main()`, matching the `daily_snapshot.py` pattern.

---

### P4 — Observability & Hygiene — **DONE 2026-04-21**

All 7 items completed in one session. 859 tests pass.

#### ~~AR-13~~: Add `exc_info=True` to `logger.error` in `nuvama_intraday_tracker.py` — **DONE**

Replaced `logger.error("...: %s", e)` + `traceback.print_exc()` with `logger.exception("run_id=%s ...", run_id)` throughout `scripts/nuvama_intraday_tracker.py`.

#### ~~AR-14~~: Add a run/correlation ID to `_async_main` and `nuvama_intraday_tracker.main()` — **DONE**

Added `run_id = uuid.uuid4().hex[:8]` at the top of both entry points. All non-fatal WARNING blocks now include `[{run_id}]`.

#### ~~AR-15~~: Delete TD-6 dead assert — `src/client/upstox_live.py:46` — **DONE (pre-existing)**

Assert was already absent; verified via grep.

#### ~~AR-16~~: Fix `__import__("datetime").date.today()` inline — `src/portfolio/tracker.py:126` — **DONE**

Replaced with `date.today()` — `date` was already imported at line 12.

#### ~~AR-17~~: Fix `classify_holding()` return type — `src/dhan/reader.py` — **DONE**

Added `AssetType.BOND = "BOND"` to the enum in `src/models/portfolio.py`. Changed `DhanHolding.classification: str` → `AssetType`. Updated `classify_holding()`, all string comparisons in `build_dhan_summary()`, and all 4 affected test files (`test_models.py`, `test_reader.py`, `test_store.py`, `test_daily_snapshot_dhan.py`). Test stubs updated: `_Leg.entry_price: float` → `Decimal` (conversion at helper boundary).

#### ~~AR-18~~: Fix unnecessary Decimal round-trip in `_etf_cost_basis` — `src/portfolio/summary.py:60` — **DONE**

Replaced `Decimal(str(leg.entry_price)) * Decimal(str(leg.quantity))` with `leg.entry_price * leg.quantity`. Test stubs in `test_daily_snapshot_helpers.py` and `test_daily_snapshot_dhan.py` updated to use `Decimal(str(float))` at the helper boundary (matching production type).

#### ~~AR-19~~: Fix `nifty_spot DECIMAL` → `REAL` in intraday schema — `src/nuvama/store.py` — **DONE**

Changed DDL to `REAL`. Added `_INTRADAY_SCHEMA_VERSION = 1` guard via `PRAGMA user_version` — drops and recreates the 30-day-retention table on first run after deploy. Simplified `float(str(nifty))` → `float(nifty)` in `get_intraday_extremes()`.

---

### P5 — Packaging Hygiene

#### AR-20: Remove `uuid==1.30` from `requirements.txt`

The PyPI `uuid` package is a deprecated wrapper around stdlib `uuid`. It is almost certainly a transitive dependency that leaked into the top-level requirements. Verify with `pip show uuid --files` and remove if not directly imported anywhere in `src/` or `scripts/`.

#### AR-21: Split `requirements-dev.txt` from `requirements.txt`

Move `pytest`, `pytest-asyncio`, and `RapidFuzz` (test-only) into `requirements-dev.txt`. Production dependencies (broker SDKs, requests, pydantic, dotenv) stay in `requirements.txt`. Standard practice; no code changes required.

---

Identified 2026-04-16 via full audit against the PDF style guide. Existing code is NOT being changed in place — these are tracked for systematic cleanup when refactoring adjacent code.

### TD-1: `@staticmethod` overuse (§2.17 — "Never use `staticmethod`")

The guide says to use module-level `_private_function()` instead. Each `@staticmethod` below should become a standalone `_function(...)` at module scope. Change is mechanical — no logic changes.

| File | Method |
|---|---|
| `src/mf/store.py` | `_row_to_transaction()`, `_row_to_nav_snapshot()` |
| `src/portfolio/store.py` | `_row_to_leg()`, `_row_to_snapshot()` |
| `src/portfolio/tracker.py` | `_extract_greeks_from_chain()` |
| `src/dhan/store.py` | `_row_to_holding()` |
| `src/instruments/lookup.py` | `_score_query()` or similar |
| `src/client/upstox_market.py` | row-mapping helper |

**Approach:** Do one module at a time as part of adjacent refactoring work. Never worth a standalone commit.

### TD-2: Line length violations (§3.2 — 80 char limit)

~44 lines exceed 80 chars; 7 lines exceed 100 chars. The 7 >100 lines are the priority — they are unwrapped f-strings or SQL concatenations and are clearly fixable.

| File | Lines |
|---|---|
| `src/portfolio/store.py` | L129 (116c), L292 (102c), L621 (111c) |
| `src/nuvama/store.py` | L229 (104c) |
| `src/dhan/reader.py` | L167 (101c) |
| `src/portfolio/models.py` | L95 (102c) |
| `src/portfolio/tracker.py` | L126 (102c) |

### TD-3: Vertical token alignment (§3.6 — "Don't use spaces to vertically align")

`src/client/protocol.py` lines 43–53: the `= Any      # TODO:` stub assignments use extra spaces to align the comment column. Strip the padding — 11 lines, 5-minute fix.

### TD-4: Missing license boilerplate (§3.8.2)

Every file should contain a license header. Zero files have one. Decision needed on which license to use before this can be automated.

### ~~TD-5~~: `except Exception` without intent comment (§2.4) — **DONE 2026-04-16**

Intent comments added to all four broad catches (dhan_verify.py:165,184 + nuvama_verify.py:154,177). Each comment names the specific hazard being isolated.

### TD-6: Stale `assert` in production module (§2.4)

`src/client/upstox_live.py:46` has `assert issubclass(type, type)` — reads like a placeholder that was never removed. Investigate and delete or replace with a real check.

### ~~TD-7~~: TODO format missing bug reference (§3.12) — **DONE 2026-04-17**

All `# TODO:` comments updated to `# TODO: TD-7 — description` format per §3.12.
2 in `src/portfolio/tracker.py`, 11 in `src/client/protocol.py`.

---

## Session Log

| Date | What Changed |
|---|---|
| 2026-04-01 — 2026-04-04 | **Foundation sprint.** Auth, portfolio module, full MF stack (models/store/nav_fetcher/tracker), daily snapshot cron, seed scripts. All 11 AMFI codes corrected against live AMFI flat file. 8-point code review applied (Decimal migration, shared db.py, enum compat, exception hierarchy, deferred I/O imports). 176 offline tests green. DB wiped and re-seeded; clean baseline from 2026-04-06. |
| 2026-04-07 | `--date` historical query mode, day-change delta, `_compute_prev_mf_pnl`. 211 tests all green. |
| 2026-04-08 | **Telegram notifications.** `src/notifications/telegram.py`: `TelegramNotifier` + `build_notifier()`. Raw requests, HTML parse_mode, `<pre>` block. Non-fatal. `_format_combined_summary()` extracted. 25 new tests, 236 total. |
| 2026-04-08 | **Exception hierarchy.** `src/client/exceptions.py` expanded: `AuthenticationError`, `RateLimitError`, `OrderRejectedError`, `InsufficientMarginError`, `InstrumentNotFoundError`. 9 new tests in `test_exceptions.py`. 254 total. |
| 2026-04-08 | **BrokerClient protocol layer.** `src/client/protocol.py`: `BrokerClient` + `MarketStream` full protocols; sub-protocols; 11 stub type aliases. `MarketDataProvider` migrated from `tracker.py`. 11 new tests. 265 total. |
| 2026-04-08 | **`PortfolioSummary` extraction.** Frozen dataclass in `src/portfolio/models.py`. `_build_portfolio_summary()` owns all arithmetic. 10 new tests, 246 total. |
| 2026-04-08 | **`UpstoxLiveClient` (5.c).** `src/client/upstox_live.py`. `get_ltp` + `get_option_chain` delegate to `UpstoxMarketClient`. Blocked methods raise `NotImplementedError`. 14 tests. 279 total. |
| 2026-04-08 | **`MockBrokerClient` (5.d).** `src/client/mock_client.py`. Stateful offline broker. `simulate_error` (one-shot). `reset()`. 38 tests. |
| 2026-04-08 | **`factory.py` (5.e).** `create_client(env)` composition root. Sole importer of concrete clients. 10 tests. |
| 2026-04-08 | **Consumer migration (5.f).** `daily_snapshot.py` uses `create_client(UPSTOX_ENV)`. `UpstoxMarketClient` no longer imported outside `src/client/`. 327 tests. |
| 2026-04-08 | **Trade ledger.** `TradeAction` + `Trade` models. `trades` table. `seed_trades.py` + `record_trade.py`. LIQUIDBEES key verified. 58 new tests. 385 total. |
| 2026-04-08 | **Trade overlay.** `get_all_positions_for_strategy()`. `apply_trade_positions()` pure function. Wired into `_async_main` and `_historical_main`. 17 new tests. 400 total. |
| 2026-04-08 | **Trade overlay internalized + strategy name fix.** `_get_overlaid_strategy()` / `_get_all_overlaid_strategies()` added to `PortfolioTracker`. `ensure_leg()` added to `PortfolioStore`. `trades.strategy_name` migrated from `ILTS`/`FinRakshak` to `finideas_ilts`/`finrakshak`. |
| 2026-04-10 | **Nuvama auth layer.** `src/auth/nuvama_login.py` + `nuvama_verify.py`. `APIConnect` session persists in `NUVAMA_SETTINGS_FILE`. 33 offline tests. Read-only scope. |
| 2026-04-10 | **Nuvama verify confirmed live.** 6 holdings: 5 EFSL NCDs + 1 GOI loan bond + 1 Sovereign Gold Bond. LTPs populated. |
| 2026-04-12 | **Context reorganisation (completed).** CONTEXT.md split into CONTEXT.md + DECISIONS.md + REFERENCES.md + TODOS.md. PLANNER.md added. CLAUDE.md tightened. Module CLAUDE.md files created: `src/portfolio/`, `src/mf/`, `src/client/`, `src/notifications/`. `.claude/skills/commit/SKILL.md` (commit format, disable-model-invocation). `.claude/agents/code-reviewer.md` (opus) + `test-runner.md` (haiku). `CODE_REVIEW.md` → `docs/archive/CODE_REVIEW_2026-04-04.md`. `scripts/daily_snapshot_old.py` → `docs/archive/daily_snapshot_old_2026-04-12.py`. `PROJECT_INSTRUCTIONS_DRAFT.md` added for Claude Desktop project settings. |
| 2026-04-13 | **Dhan auth layer.** `src/auth/dhan_login.py` + `dhan_verify.py`. Manual 24h token flow via web.dhan.co. Raw `requests` client (no dhanhq SDK). Pure functions: `build_login_url()`, `validate_token()`, `save_token()`, `load_dhan_credentials()`, `fetch_profile()`, `fetch_holdings()`, `parse_holdings()`. 31 offline tests (13 login + 18 verify). Read-only scope — free Trading APIs only. Data APIs (₹499/month — option chain, historical, expired options) deferred for backtesting sprint. 431 total tests, all green (excluding pre-existing upstox_live failures). |
| 2026-04-14 | **Dhan LTP fix — switch to Upstox batch fetch.** Dhan `POST /v2/marketfeed/ltp` returns 401 on free tier (requires ₹499/month Data API). Added `enrich_with_upstox_prices()` + `upstox_keys_for_holdings()` + `fetch_dhan_holdings()` to `reader.py`. Restructured `_async_main`: Dhan holdings pre-fetched before Upstox LTP batch → keys added to `all_keys` → enriched after single batch call. `fetch_dhan_portfolio()` accepts optional `upstox_prices` param. 9 new tests. 558 total. |
| 2026-04-14 | **Dhan portfolio integration.** `src/dhan/` module: `models.py` (DhanHolding, DhanPortfolioSummary frozen dataclasses), `reader.py` (fetch_holdings_raw, fetch_ltp_raw, classify_holding, build_dhan_holdings, build_security_id_map, enrich_with_ltp, build_dhan_summary, fetch_dhan_portfolio), `store.py` (DhanStore — dhan_holdings_snapshots table, upsert, get_prev_snapshot). `src/portfolio/models.py` extended with 9 Dhan fields on PortfolioSummary (all default-zero — existing tests unaffected). `daily_snapshot.py`: `_async_main` wires Dhan (non-fatal, excludes strategy ISINs), `_historical_main` reads stored Dhan snapshots, `_build_portfolio_summary` includes Dhan in totals, `_format_combined_summary` restructured to Equity/Bonds/Derivatives/Total sections. `test_daily_snapshot_historical.py` updated for new sectioned format. 81 new Dhan tests (57 module + 24 snapshot integration). 549 total, all green (pre-existing upstox_live/nuvama failures unchanged). |
| 2026-04-15 | **Fuzzy instrument search.** `src/instruments/lookup.py`: `_score_query()` + `_best_score()` private helpers implement `exact(1.0) > prefix(0.92) > fuzzy` ranking via rapidfuzz (difflib fallback, no hard dep). `InstrumentLookup.search()` now scores + sorts all candidates; `min_score` param added. Signature of all other methods unchanged. 27 new tests in `tests/unit/instruments/test_lookup.py`. 585 total. |
| 2026-04-15 | **quant-4pc-local analysed.** Prior Dhan-focused research repo reviewed. Reusable components identified: `BacktestEngine` + `Strategy` protocol (port into `src/backtest/`), `IronCondorStrategy` + `IronCondorConfig` (port into `src/strategy/`), `_normalize_df()` data normalisation improvements for `src/dhan/reader.py`, retry/backoff pattern for future rate-limiter. Full porting notes in `PLANNER.md` → "quant-4pc-local Reference" section. Folder gitignored (`quant-4pc-local/`). |
| 2026-04-15 | **Atomic leg roll CLI (TODO 2).** `PortfolioStore.record_roll()` — single `_connect` block, two INSERTs, one transaction. `scripts/roll_leg.py`: `--old-*/--new-*` flag pairs, `_build_trades()` pure function, `--dry-run`. README.md updated with full CLI signature + dry-run example. 14 new tests (4 `test_trade_store.py` + 10 `test_roll_leg.py`). 599 total. |
| 2026-04-15 | **Nuvama bond schema probe.** `scripts/probe_nuvama_schema.py` added. Full `rmsHdg` field set confirmed: `isin`, `ltp`, `totalQty`, `totalVal`, `chgP`, `exc`, `hairCut` — no `avgPrice`. 6 holdings: 4 EFSL NCDs, 1 GOI G-Sec, 1 SGB. Cost basis sourced from Nuvama UI screenshot and will be seeded. LIQUIDBEES excluded by ISIN. Plan finalized — 4-phase implementation begins. |
| 2026-04-15 | **fix(scripts): os._exit() for daily_snapshot.py.** APIConnect `__init__` spawns a non-daemon Feed thread. `sys.exit()` waits for non-daemon threads so the process hung after completing. Replaced with `os._exit(main())` — identical fix to `nuvama_verify.py` and `nuvama_login.py`. Committed separately by Animesh (7a49720). |
| 2026-04-16 | **TD-3 resolved.** Stripped vertical alignment padding from stub type alias block in `src/client/protocol.py` lines 43–53. Normalised to 2-space inline comment style per Google §3.6. No logic change. |
| 2026-04-16 | **rapidfuzz deployment step confirmed done.** `RapidFuzz==3.14.5` already present in `requirements.txt`. TODOS.md updated to reflect closure. |
| 2026-04-16 | **`src/models/` migration (TODO 4) complete.** `src/models/portfolio.py` + `src/models/mf.py` created (prior partial session had created files; import migration completed this session). All 34 import sites in `src/`, `scripts/`, `tests/` updated to new paths. `src/portfolio/models.py` + `src/mf/models.py` deleted. `protocol.py` stub-block comment updated. Zero old-path imports remaining. |
| 2026-04-16 | **Indian number format (TODO 8) complete.** `src/utils/number_formatting.py`: `fmt_inr()` utility with `_group_indian()` helper, 37 tests. `src/portfolio/formatting.py`: all `{:,.0f}` monetary formats replaced. 6 test assertions updated across 3 test files. 774 passing. |
| 2026-04-16 | **daily_snapshot.py split (TODO 5) complete.** `_aggregate`/`_scheme_pnl` made public in `src/mf/tracker.py`. `src/portfolio/summary.py` (6 pure computation fns) + `src/portfolio/formatting.py` (2 pure formatting fns) extracted. `daily_snapshot.py` slimmed to I/O orchestration only (~350 lines). All re-exported for backward compat. 4 commits, 717 tests passing, 20 pre-existing failures unchanged. |
| 2026-04-15 | **Nuvama bond portfolio integration (TODO 0) — all 4 phases complete.** `src/nuvama/` module: `models.py` (NuvamaBondHolding + NuvamaBondSummary frozen dataclasses), `reader.py` (parse_bond_holdings, build_nuvama_summary, fetch_nuvama_portfolio), `store.py` (NuvamaStore — nuvama_positions + nuvama_holdings_snapshots tables). `scripts/seed_nuvama_positions.py` (6 instruments, idempotent, dry-run by default). `PortfolioSummary` extended with 6 nuvama_* fields (all default-zero). `daily_snapshot.py`: Nuvama fetch block in `_async_main` (non-fatal), historical reconstruction in `_historical_main`, Nuvama Bonds line in `_format_combined_summary`, nuvama fields in `_build_portfolio_summary`. 97 new tests (54 pydantic-dependent — all pass in Mac venv). |
| 2026-04-16 | **Nuvama option PnL reporting complete.** Extended `src/nuvama/` to parse `NetPosition()`, fetch legacy cumulative PnL from db, and output realized/unrealized metrics. Added to `daily_snapshot.py` formatting logic to display Nuvama options distinct from tracking. |
| 2026-04-17 | **Intraday tracking for options.** `nuvama_intraday_snapshots` table with 30-day retention loop created. `scripts/nuvama_intraday_tracker.py` fetches 5-minute sampling bounds (both options PnL and Upstox Nifty constraints) allowing native intraday insights. Python `Decimal` used to guard aggregations constraints against Float inaccuracies. Output wired into Telegram formatting properly (`M2M High/Low` and `Nifty High/Low`). |
| 2026-04-17 | **Market holiday guard — complete.** `src/market_calendar/holidays.py`: `load_holidays()`, `is_trading_day()`, `prev_trading_day()` — fail-open on missing YAML, module-level cache. `src/market_calendar/data/nse_2026.yaml`: 17 NSE 2026 holidays. Guards added to `daily_snapshot.py` (live mode only — historical `--date` always runs) and `nuvama_intraday_tracker.py`. `.gitignore` fixed: `data/` → `/data/` (anchored to root). 31 tests green. `get_prev_snapshots()` confirmed calendar-agnostic — no store changes needed. |
| 2026-04-17 | **Doc sync (Claude).** Updated CONTEXT.md: header date, nuvama models entry (NuvamaOptionPosition + NuvamaOptionsSummary), options_reader entry (build_options_summary), store entry (nuvama_options_snapshots table + 6 new methods), portfolio.py PortfolioSummary nuvama_options_* fields, summary.py nuvama_options_summary param, nuvama_intraday_tracker script description, removed duplicate CLAUDE.md entry, test coverage note. Added two DECISIONS.md entries (Intelligent EOD Snapshot pattern + Nuvama SDK os._exit() rule). Added TODO-0 for missing option/intraday tests. |
| 2026-04-21 | **Architecture review (Claude).** Full top-down review using `python-architecture-review.prompt.md` v6. 21 action items added to TODOS.md (AR-1 through AR-21) across 5 priority tiers. P0: two `if not x:` truthiness bugs that corrupt P&L snapshots. P1: Nuvama options + intraday test coverage gap (supersedes TODO-0). P2: `PortfolioSummary` god dataclass refactor, type safety in `_build_portfolio_summary`, Nuvama historical reconstruction hack, atomic record_all_*, Nuvama protocol abstraction. P3: SQL GROUP BY for cumulative PnL, N+1 fix in store, double LTP fetch, deferred imports in intraday tracker. P4: observability (exc_info, run ID, dead assert, classify_holding enum). P5: packaging hygiene. No code changed — review only. |
| 2026-04-21 | **P0 correctness fixes (AR-1, AR-2).** AR-1: `tracker.py` — `prices.get(key, 0.0)` + `if not raw_ltp:` → `prices.get(key)` + `if raw_ltp is None:`. Zero LTP (expiring-worthless option) now used as-is instead of being replaced by entry_price. New test `test_compute_pnl_zero_ltp_used_as_is` in `tests/unit/test_portfolio.py`. AR-2: `daily_snapshot.py` lines 163 + 409 — `if underlying_price:` → `if underlying_price is not None:` at both occurrences. 785 tests passing (1 pre-existing rapidfuzz sandbox delta, unrelated). |
| 2026-04-21 | **P4 hygiene (AR-13 through AR-19, Claude).** AR-13: `logger.exception()` + run_id in `nuvama_intraday_tracker.py`, dropped `traceback.print_exc()`. AR-14: `run_id = uuid.uuid4().hex[:8]` in both cron entry points; run_id threaded into all non-fatal WARNING prints. AR-15: pre-existing — dead assert already absent. AR-16: `__import__("datetime").date.today()` → `date.today()` in `tracker.py`. AR-17: Added `AssetType.BOND` to enum; `DhanHolding.classification: str` → `AssetType`; `classify_holding()` returns `AssetType`; all string comparisons and 4 test files updated; `_Leg` stubs corrected to `Decimal` entry_price. AR-18: Removed redundant `Decimal(str(...))` wrap in `_etf_cost_basis()`; test stubs fixed to convert float→Decimal at helper boundary. AR-19: `nuvama_intraday_snapshots` DDL `DECIMAL`→`REAL`; `PRAGMA user_version` schema guard (drop+recreate, v0→v1); `float(str(nifty))` → `float(nifty)`. 859 tests passing. |
| 2026-04-21 | **P1 test coverage gap (AR-3) — Nuvama options + intraday.** Added 54 new tests across 3 files. `tests/unit/nuvama/test_models.py`: 11 new tests for `NuvamaOptionPosition` (construction, frozen, short/flat qty) and `NuvamaOptionsSummary` (construction, frozen, `net_pnl` property, cumulative exclusion, intraday bounds). `tests/unit/nuvama/test_options_reader.py` (new file): 26 tests for `parse_options_positions` (OPTIDX/OPTSTK happy paths, non-option filtering, flat position, short/long price selection, cfAvg→avg fallbacks, instrument name construction, missing key, malformed record edge cases) and `build_options_summary` (unrealized/realized aggregation, cumulative map, intraday bounds propagation, `net_pnl` correctness). `tests/unit/nuvama/test_store.py`: 13 new tests for `record_all_options_snapshots` (multi-insert, empty list, idempotent upsert) and intraday methods (`record_intraday_positions`, `get_intraday_extremes`: empty/single-timestamp/multi-timestamp/multi-leg summation/date isolation, `purge_old_intraday`: removes old / keeps recent / auto-purge on write). 847 passing, 12 pre-existing upstox_live sandbox failures unchanged. |
| 2026-04-22 | **Morning NAV backfill script.** `scripts/morning_nav.py`: standalone cron script that fetches AMFI NAVs and upserts the previous trading day's MF snapshot. Fixes the stale-NAV problem where the 15:45 snapshot captures T-2 NAV (AMFI hasn't published yet). Runs at 09:15 IST — `prev_trading_day(date.today())` handles Mon→Fri and holiday edge cases. `--date` override for manual recovery. 6 new tests in `tests/unit/test_morning_nav.py`. Cron: `15 9 * * 1-5 cd /path/to/NiftyShield && python -m scripts.morning_nav >> logs/snapshot.log 2>&1`. |
| 2026-04-22 | **P2 architecture refactor (AR-4, AR-5, AR-6, AR-7 — Claude).** AR-7: `record_all_snapshots` + `record_all_options_snapshots` rewritten to use `executemany` inside a single `with connect() as conn:` block — atomicity matches `PortfolioStore.record_snapshots_bulk()`. Rollback tests added. AR-5: `object|None` params replaced with real types via `TYPE_CHECKING` guards in `summary.py` + `formatting.py`; all 14 `# type: ignore[union-attr]` suppressions removed. AR-6: `get_snapshot_for_date` now returns `dict[str,dict]` with `qty/ltp/current_value` keys; `_historical_main` reconstructs true `NuvamaBondHolding` objects from stored `qty`+`ltp` — `qty=1` stub gone. AR-4: `PortfolioSummary` refactored from 26-field flat accumulator to 16-field composed model with four typed `Optional` source references (`mf_pnl`, `dhan`, `nuvama_bonds`, `nuvama_options`); availability exposed as computed `@property`; `_build_portfolio_summary` dead intermediate variables removed; `formatting.py` double-guards inside available-checks eliminated. `test_portfolio_summary_nuvama.py` deleted (superseded). `test_telegram_formatting.py` added (cross-source smoke test with numeric delta assertions). All REVIEW.md G2 violations in new diff lines fixed (long arithmetic lines wrapped). 846 passing; 1 pre-existing rapidfuzz/difflib delta in `test_lookup.py`; 12 pre-existing sandbox skips unchanged. Commit: `4de0ec4`. |
