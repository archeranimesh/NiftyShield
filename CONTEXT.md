# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase.
> Read this before writing any code. Do not rely on session summaries or chat history.
> Repo: https://github.com/archeranimesh/NiftyShield

---

## Current State (as of 2026-04-07)

### What Exists (committed and working)

```
src/
├── auth/
│   ├── login.py              # OAuth flow — opens browser, captures code, saves token to .env
│   └── verify.py             # API connectivity check — fetches user profile
├── analytics/                # Exploratory scripts (not production modules)
│   └── verify_analytics.py   # Tests LTP, option chain, Greeks, historical candles via Analytics Token
├── sandbox/                  # Exploratory scripts
│   └── order_lifecycle.py    # Place → Modify → Cancel via V3 Order API (sandbox=True)
├── portfolio/
│   ├── models.py             # Pydantic: Leg, Strategy, DailySnapshot. Monetary fields (entry_price, ltp, close, underlying_price) are Decimal. P&L methods accept float|Decimal, return Decimal.
│   ├── store.py              # SQLite: strategies, legs, daily_snapshots. entry_price/ltp/close/underlying_price stored as TEXT for Decimal precision. WAL + upsert semantics.
│   ├── tracker.py            # PortfolioTracker: loads strategies, fetches LTPs, records snapshots. compute_pnl() returns StrategyPnL with Decimal total_pnl. Float LTPs from API converted via Decimal(str()) at boundary.
│   └── strategies/
│       ├── __init__.py       # ALL_STRATEGIES registry
│       └── finideas/
│           ├── __init__.py
│           ├── ilts.py       # ILTS: 4 legs (EBBETF0431 + 3 Nifty options)
│           └── finrakshak.py # FinRakshak: 1 leg (protective put)
├── mf/
│   ├── __init__.py           # Package marker
│   ├── models.py             # Pydantic: MFTransaction, MFNavSnapshot, TransactionType enum. Also: MFHolding frozen dataclass.
│   ├── store.py              # SQLite: mf_transactions + mf_nav_snapshots in shared DB. get_holdings() returns dict[str, MFHolding].
│   ├── nav_fetcher.py        # AMFI flat file download + parse → {amfi_code: Decimal}. Injectable source for offline tests.
│   └── tracker.py            # MFTracker: load holdings, fetch NAVs, upsert snapshots, return PortfolioPnL. MFHolding imported from models.
├── instruments/
│   └── lookup.py             # Offline BOD search (NSE.json.gz). CLI: --find-legs mode.
├── notifications/
│   ├── __init__.py           # Package marker.
│   └── telegram.py           # TelegramNotifier: fire-and-forget sendMessage via raw requests (HTML parse_mode, <pre> block). build_notifier() returns None when env vars absent. send() never raises — catches Exception broadly, logs WARNING, returns False.
├── db.py                     # Shared SQLite context manager — WAL mode, row_factory, FK enforcement, auto commit/rollback.
└── client/
    ├── exceptions.py         # Custom exception hierarchy: BrokerError → AuthenticationError, RateLimitError, DataFetchError (→ LTPFetchError), OrderRejectedError (→ InsufficientMarginError), InstrumentNotFoundError.
    └── upstox_market.py      # Sync requests client. V3 LTP endpoint. Pipe→colon key remap. Raises LTPFetchError on HTTP error / empty data.

scripts/
├── daily_snapshot.py         # Two-mode CLI. Live mode: fetches LTPs + Nifty spot, records snapshots, prints P&L, sends Telegram notification (non-fatal). Historical mode (--date YYYY-MM-DD): reads stored snapshots, computes P&L offline — no API call. _format_combined_summary() returns the formatted string; _print_combined_summary() wraps it with print(). Module-level imports stay stdlib + portfolio.models only; all I/O deferred.
├── send_test_telegram.py     # Smoke-test script. Reads TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID from .env, sends a sample P&L message. Exit code 0/1. Run before first cron to verify credentials.
└── seed_mf_holdings.py       # One-time CLI. Inserts 11 INITIAL MF transactions. Idempotent. --dry-run flag.

tests/
├── unit/
│   ├── portfolio/            # 20 tests: Leg P&L, strategy aggregation, store CRUD, upsert, tracker
│   └── mf/
│       ├── __init__.py       # Package marker
│       ├── test_models.py    # 25 tests: MFTransaction + MFNavSnapshot valid/invalid/edge cases
│       ├── test_store.py     # 33 tests: CRUD, upsert idempotency, date range queries, schema coexistence. get_holdings tests updated for MFHolding return type.
│       ├── test_nav_fetcher.py  # 20 tests: AMFI parse logic, fixture-driven, fully offline. Updated to correct AMFI codes.
│       ├── test_tracker.py   # 27 tests: pure P&L math + mocked store/fetcher orchestration
│       ├── test_seed.py      # 20 tests: seed transaction shape, verified AMFI code set, idempotency, Decimal precision, total_invested sum
│       ├── test_daily_snapshot_mf.py   # 12 tests: MF wire-up path — schema coexistence, full seed→snapshot→aggregate, empty holdings, nav failure
│       └── test_daily_snapshot_helpers.py  # 11 tests: _etf_current_value + _etf_cost_basis pure helpers. No sys.modules stubs needed — daily_snapshot.py has no I/O imports at module level.
└── fixtures/
    ├── responses/            # 7 JSON fixtures recorded from real APIs (LTP, option chain, Greeks, candles)
    └── amfi/
        └── nav_slice.txt     # Realistic AMFI flat file slice: 11 valid schemes with correct AMFI codes, N.A. line, malformed line
```

### What Does NOT Exist Yet

- `src/client/protocol.py` — BrokerClient & MarketStream protocols (not written)
- `src/client/upstox_live.py` — UpstoxLiveClient (not written)
- `src/client/mock_client.py` — MockBrokerClient (not written)
- `src/client/factory.py` — client factory (not written)
- `src/models/` — shared Pydantic models (not written; models are local to portfolio/ and mf/ — both will migrate here in a future refactor commit)
- `src/strategy/`, `src/execution/`, `src/backtest/`, `src/risk/`, `src/streaming/` — all empty
- OptionChain Pydantic model — not defined
- Greeks capture — `_fetch_greeks()` returns `{}` immediately (explicit TODO)
- `scripts/roll_leg.py` — CLI to close an old leg and open a replacement in one atomic transaction (not written)
- Trade history model — `Trade`, `TradeAction` not yet defined; no audit trail for rolls/adjustments
- ~~`PortfolioSummary` type~~ — **DONE (2026-04-08)**: `PortfolioSummary` frozen dataclass added to `src/portfolio/models.py`. `_build_portfolio_summary()` extracted from `_format_combined_summary()` in `daily_snapshot.py`. Both callers (`_async_main`, `_historical_main`) thread `snap_date` through. 10 new tests, 246 total.
- ~~Day-change P&L in combined summary~~ — **DONE (2026-04-07)**: `PortfolioStore.get_prev_snapshots()`, `MFStore.get_prev_nav_snapshots()`, `_build_prev_prices()`, `_compute_prev_mf_pnl()` helpers added. Combined summary now shows `Δday` for MF, ETF, and options when prev data exists; column omitted silently on first run.

### Live Data

- SQLite DB path confirmed: `data/portfolio/portfolio.sqlite`
- DB wiped clean on 2026-04-04 (`daily_snapshots`, `mf_transactions`, `mf_nav_snapshots` all cleared)
- `mf_transactions` re-seeded with all 11 schemes using correct AMFI codes
- `mf_nav_snapshots` empty — first clean snapshot on Monday 2026-04-06 (pre-market run)
- `daily_snapshots` empty — first clean baseline on Monday 2026-04-06 (pre-market run)
- `underlying_price` will populate from 2026-04-06 onwards
- Greeks columns are null across all snapshots
- Cron job set up: `45 15 * * 1-5` — snapshots accumulate automatically from Monday

---

## Key Decisions

### Tokens & Auth
- **Analytics Token** is the primary working token (read-side: quotes, option chain, Greeks, candles, websocket). Lasts 1 year, no OAuth required.
- **Daily OAuth token** (Algo Trading app) needed only for portfolio/positions read and order execution.
- Both tokens stored in `.env`.

### Instrument Keys (verified against live API)
| Instrument | Key | Notes |
|---|---|---|
| EBBETF0431 (ETF) | `NSE_EQ\|INF754K01LE1` | ISIN starts with INF (ETF), not INE |
| NiftyBees ETF | `NSE_EQ\|INF204KB14I2` | Discovered Day 1 |
| NIFTY DEC 23000 PE | `NSE_FO\|37810` | Monthly expiry: 2026-12-29 (Tue) |
| NIFTY JUN 23000 CE | `NSE_FO\|37799` | Monthly expiry: 2026-06-30 (Tue) |
| NIFTY JUN 23000 PE | `NSE_FO\|37805` | Monthly expiry: 2026-06-30 (Tue) |
| Nifty Index | `NSE_INDEX\|Nifty 50` | For option chain API and spot price — NOT `"NIFTY"` |

### AMFI Codes (verified against live AMFI flat file on 2026-04-04)
All 11 codes were wrong in the original `_HOLDINGS` — they resolved to completely unrelated schemes,
not even plan-variant mismatches. Root cause unknown (likely copied from a stale or incorrect source).
Every code was replaced by grepping the live AMFI flat file.

| Scheme | Correct AMFI Code |
|---|---|
| Parag Parikh Flexi Cap Fund - Regular Plan - Growth | 122640 |
| DSP Midcap Fund - Regular Plan - Growth | 104481 |
| HDFC Focused Fund - Growth | 102760 |
| Mahindra Manulife Mid Cap Fund - Regular Plan - Growth | 142109 |
| Edelweiss Small Cap Fund - Regular Plan - Growth | 146193 |
| Tata Value Fund - Regular Plan - Growth | 101672 |
| quant Small Cap Fund - Growth - Regular Plan | 100177 |
| Kotak Flexicap Fund - Growth | 112090 |
| HDFC BSE Sensex Index Fund - Growth Plan | 101281 |
| Tata Nifty 50 Index Fund - Regular Plan | 101659 |
| WhiteOak Capital Large Cap Fund - Regular Plan Growth | 150799 |

**Verification method:** `grep -i "<scheme name>" <(curl AMFI flat file)` — match on scheme name, pick Regular Plan Growth variant. Do NOT trust codes from any other source without verifying against the live flat file.

### API Quirks
- V3 Market Quote: send keys with pipe (`NSE_FO|37810`), response comes back with colon (`NSE_FO:NIFTY...`). Map back via `instrument_token` field.
- Option chain instrument key must be `NSE_INDEX|Nifty 50` — any other format returns empty/error.
- Monthly expiry epoch must use `datetime.fromtimestamp(epoch/1000, tz=timezone.utc)` — local timezone causes IST offset bug (date shifts by one day).
- Monthly NSE options expire last **Tuesday** of the month. Monthly symbols show only month name; weeklies show full date.
- `NSE_INDEX|Nifty 50` can be included in the standard V3 LTP batch call alongside equity and F&O keys — no separate endpoint needed for spot price.
- **Upstox has no mutual fund API.** No MF holdings, NAV, or transaction endpoints exist in V2 or V3. Community requests confirmed unanswered as of Feb 2026.
- **AMFI NAV timing:** AMFI publishes NAVs after market close, typically 7–9 PM IST. The cron at 3:45 PM fetches intraday option LTPs (live) but the MF NAV at that time is T-1. This is expected and correct for MFs — the combined P&L summary shows mixed-timestamp data at 3:45 PM by design.

### Architecture Decisions
- `src/client/upstox_market.py` was built outside the intended BrokerClient protocol abstraction. Works fine for the batch snapshot script, but violates the dependency-inversion rule in the project instructions. Needs wrapping before the next feature module is added.
- Strategy definitions (leg structure, instrument keys) stay in code (`ilts.py`, `finrakshak.py`), not in DB. What goes in DB is trade history — physical executions, rolls, and adjustments under each leg. A `Leg` is a conceptual role; a `Trade` is a physical execution.
- `src/mf/` is a separate module from `src/portfolio/` — different data source (AMFI vs Upstox), different asset class, different lifecycle (SIP cadence vs trade events). P&L is combined at query time, not at model level.
- MF holdings use a **transaction ledger** model (`mf_transactions`) rather than a static holdings snapshot — supports SIP additions each month as plain INSERTs with no mutation of existing rows. Current holdings derived at query time via `SUM(units)`.
- NAV data source: **AMFI official flat file** (`https://www.amfiindia.com/spages/NAVAll.txt`). Published nightly, no auth, no rate limits, **semicolon-delimited** (6 fields: code; ISIN growth; ISIN reinvest; name; NAV; date). Preferred over `mfapi.in` (third-party dependency) and Upstox (no MF API).
- AMFI flat file parsing gate: `parts[0].strip().isdigit()` — single check that skips all category headers, the column header line, blank lines, and malformed rows without any regex.
- NAV snapshots stored **per-scheme** in `mf_nav_snapshots`; portfolio-level aggregation happens at query time. Enables per-fund attribution.
- MF data shares the **existing SQLite DB** (`data/portfolio/portfolio.sqlite`) — one file, one WAL, one backup.
- `amfi_code` typed as `str` (pattern `^\d+$`), not `int` — used as identifier and join key, never as arithmetic. Matches AMFI flat file representation.
- `units`, `amount`, and `nav` stored as `TEXT` in SQLite (not `REAL`) — preserves exact `Decimal` precision through the round-trip. Read back via `Decimal(row["..."])`.
- `get_holdings()` aggregates units, invested amount, and scheme_name in Python, not SQL `CAST` — keeps exact `Decimal` arithmetic for INITIAL + SIP accumulation and REDEMPTION subtraction.
- `MFHolding` is defined in `src/mf/models.py`, **not** `tracker.py` — avoids the circular import that would result from `store.py` importing a type defined in `tracker.py`. `store.get_holdings()` returns `dict[str, MFHolding]`; `tracker.py` imports `MFHolding` from `models`.
- `get_holdings()` returns `dict[str, MFHolding]` where `MFHolding` carries `amfi_code`, `scheme_name`, `total_units`, `total_invested`. `scheme_name` is taken from the most recent transaction for each scheme (all transactions carry the same name in practice).
- `mf_transactions` unique constraint is `(amfi_code, transaction_date, transaction_type)` — ensures seed script idempotency via `ON CONFLICT DO NOTHING`. Assumes one transaction per type per NAV date per scheme, which AMFI's one-NAV-per-day rule makes practical.
- `mf_nav_snapshots` uses `ON CONFLICT(amfi_code, snapshot_date) DO UPDATE` — last write wins, consistent with `daily_snapshots` in `PortfolioStore`.
- MF store tests use `tmp_path` (ephemeral file-based SQLite), not `:memory:` — `_connect()` opens and closes a fresh connection on every call, so `:memory:` would lose state between method calls.
- `frozen=True` on MFTransaction and MFNavSnapshot — immutable records; mutation goes through the store.
- `MFNavSnapshot` has a `scheme_name` field (denormalised) — required at construction time. The tracker pulls it from `MFHolding.scheme_name` which originates from `mf_transactions`.
- Both `portfolio/models.py` and `mf/models.py` are module-local for now, consistent with each other. Migration to `src/models/` deferred until BrokerClient protocol layer is built — both move together in one refactor commit.
- `SchemePnL` and `PortfolioPnL` are frozen dataclasses defined in `tracker.py` — computed types, not persisted records. `MFHolding` was originally also in `tracker.py` but moved to `models.py` to break the store→tracker circular import. All three migrate to `src/models/` in the same refactor commit as the Pydantic models.
- P&L quantization boundary: `current_value` and `pnl_pct` quantized to 2 dp (ROUND_HALF_UP); `pnl` kept as exact difference so `sum(scheme.pnl) == total_pnl` without rounding drift.
- `nav_fetcher` is injected into `MFTracker` via `NavFetcherFn = Callable[[set[str]], dict[str, Decimal]]` — tests pass a plain lambda, production defaults to `fetch_navs`. Missing NAV codes are skipped with a WARNING log, not raised — the tracker does not know which codes are critical.
- `fetch_navs` missing-code behaviour: absent from result dict, logged at WARNING. Caller decides whether a missing code is fatal. The tracker skips; `seed_mf_holdings.py` is the right place to treat a missing code as an error (not yet implemented — currently silently skips).
- **Combined portfolio summary** in `daily_snapshot.py`: `total_value = MF current value + ETF mark-to-market + options net P&L`. ETF legs identified by `leg.asset_type == AssetType.EQUITY`. `_etf_current_value` and `_etf_cost_basis` are pure helper functions at module level, directly importable in tests with no stubs required.
- **`PortfolioSummary`** is a `frozen=True` dataclass in `src/portfolio/models.py`. Carries all combined totals (`mf_value`, `etf_value`, `options_pnl`, `total_value`, `total_pnl`, `total_pnl_pct`) plus four day-delta fields (all `Decimal | None`). `_build_portfolio_summary()` in `daily_snapshot.py` owns the computation; `_format_combined_summary()` delegates to it. `snapshot_date: date` field included for the upcoming visualization commit.
- `PortfolioTracker.compute_pnl()` returns `StrategyPnL` with `total_pnl` as `Decimal`. No bridging cast needed when combining with other `Decimal` values in the combined summary.
- **MF snapshot is non-fatal in cron:** the MF block in `daily_snapshot.py` is wrapped in `try/except Exception`. AMFI unreachable at 3:45 PM does not abort the portfolio snapshot — it logs a WARNING and the combined summary prints `[failed]` for the MF line.
- `seed_mf_holdings.py` separates `build_transactions()` (pure, no I/O) from `seed_holdings()` (calls store) — `build_transactions()` is independently testable with no DB.
- **daily_snapshot.py import design:** module-level imports are stdlib + `src.portfolio.models` only. All I/O-triggering imports (`dotenv`, `UpstoxMarketClient`, `PortfolioStore`, `PortfolioTracker`, `MFStore`, `MFTracker`) are deferred inside `_async_main()`. This makes the pure helpers importable in tests with zero side effects — no `.env`, no DB, no network.
- **Combined P&L has two distinct metrics:** (1) inception P&L — current value minus total invested, permanent fixture of the summary; (2) day-change P&L — today's value minus previous snapshot via `get_prev_snapshots()` / `get_prev_nav_snapshots()` (MAX date < today, calendar-agnostic). Δday column is silently omitted on first run when no prior snapshot exists.
- **Telegram notifier is optional and non-fatal:** `build_notifier()` returns `None` when `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` are absent — caller guards with `if notifier:`. `send()` catches all `Exception` broadly (not just `requests.RequestException`) and returns `False` with a WARNING log. The cron never aborts due to Telegram failure. Message is sent in HTML `<pre>` block so monospace P&L alignment renders on mobile. `_format_combined_summary()` was extracted from `_print_combined_summary()` so both the terminal and Telegram receive identical text without double-computing or stdout capture hacks.
- **Shared SQLite connection factory** in `src/db.py`: single `connect()` context manager used by both `PortfolioStore` and `MFStore`. WAL mode, `sqlite3.Row` factory, foreign key enforcement, auto commit/rollback. Any PRAGMA change applies everywhere from one place.
- **Error hierarchy in `src/client/exceptions.py`:** Full tree rooted at `BrokerError`: `AuthenticationError` (token/OAuth failure), `RateLimitError` (429, retryable), `DataFetchError` (retryable) → `LTPFetchError`, `OrderRejectedError` (terminal) → `InsufficientMarginError`, `InstrumentNotFoundError` (terminal). `UpstoxMarketClient` raises `LTPFetchError` on HTTP errors, empty API response, and missing instrument tokens. `get_ohlc_sync` and `get_option_chain_sync` raise `DataFetchError` rather than returning empty dicts silently. Callers distinguish retryable vs terminal errors by catching at the appropriate level.
- **Monetary field types:** `Leg.entry_price`, `DailySnapshot.ltp`, `.close`, `.underlying_price` are `Decimal`. SQLite stores them as `TEXT` columns to preserve precision through round-trips. `Leg.pnl()` and `pnl_percent()` accept `float | Decimal` — float inputs go through `Decimal(str())` inside the method. Float LTPs from the broker API are converted via `Decimal(str(ltp))` at the tracker boundary before entering any model or P&L calculation.
- **Enum compatibility:** `Direction`, `ProductType`, `AssetType` use `(str, Enum)` pattern (not `StrEnum`) — `StrEnum` was introduced in Python 3.11; the project targets Python 3.10+.

### Deferred
- Greeks fetch: option chain call was failing during portfolio build; deferred until `OptionChain` Pydantic model is defined.
- Expired instruments API: blocked (paid subscription not active). Backtesting uses NSE CSV dumps as interim.
- Order execution: blocked (static IP not provisioned). All order logic via MockBrokerClient.

---

## Current Constraints

| Constraint | Workaround |
|---|---|
| Order execution blocked (static IP required) | MockBrokerClient for all order dev/testing |
| Expired Instruments API blocked (paid tier) | NSE option chain CSV dumps as interim backtest source |
| Greeks columns null in DB | `_fetch_greeks()` early return — fix after OptionChain model is defined |
| `underlying_price` null for pre-2026-04-06 snapshots | DB wiped; clean baseline starts Monday |
| Upstox has no MF API | AMFI flat file as sole NAV source; MF holdings managed via seed script + monthly SIP inserts |
| MF NAV at 3:45 PM cron is T-1 | Expected for MFs — AMFI publishes after market close. Combined summary shows mixed-timestamp data by design. |
| Day-change P&L | **Implemented** — Δday shown in combined summary from 2026-04-07 |

---

## Pre-Task Protocol (for AI assistants)

Before writing any code: read `CONTEXT.md`, state `CONTEXT.md ✓`, confirm file scope, state a one-sentence plan. See `CLAUDE.md` for the full protocol.

## Immediate TODOs (in priority order)

1. ~~**daily_snapshot.py enhancements**~~ — **ALL DONE**:
   - ~~**Day-change delta in output**~~ — DONE (2026-04-07)
   - ~~**Extract `PortfolioSummary`**~~ — DONE (2026-04-08)
   - ~~**Date parameter** (`--date YYYY-MM-DD`)~~ — DONE (2026-04-07)

2. ~~**Telegram bot notifications**~~ — **DONE (2026-04-08)**: `src/notifications/telegram.py` with `TelegramNotifier` + `build_notifier()`. Raw `requests`, HTML parse_mode, `<pre>` block for monospace alignment. Non-fatal (`Exception` caught broadly, WARNING logged). Injected in `_async_main` — skipped silently when env vars absent. `_format_combined_summary()` extracted from `_print_combined_summary()` so both the terminal and Telegram share the same formatted text. Smoke-test script: `scripts/send_test_telegram.py`. 25 new offline tests. 236 total, all green.

3. **Trade history + roll workflow** — `Trade` model, `TradeAction` enum, `trades` table in store, `scripts/roll_leg.py` CLI. Backfill OPEN trades for existing legs as baseline. Required before JUN 2026 expiry roll (2026-06-30).

4. **Greeks capture** — fix option chain call (`NSE_INDEX|Nifty 50`), define `OptionChain` Pydantic model, implement `_extract_greeks_from_chain()`. Fixture `nifty_chain_2026-04-07.json` already recorded — use it to drive the model definition.

5. **BrokerClient protocol layer** — Required before any new feature module is added. Current `upstox_market.py` violates dependency inversion — do not add further modules against it directly. Sub-tasks in order:
   - **5.a** — Expand `src/client/exceptions.py`: add `AuthenticationError`, `RateLimitError`, `OrderRejectedError`, `InsufficientMarginError`, `InstrumentNotFoundError`. Tests in `tests/unit/test_exceptions.py` (8 tests).
   - **5.b** — Create `src/client/protocol.py`: full `BrokerClient` + `MarketStream` protocols, narrow sub-protocols (`MarketDataProvider`, `OrderExecutor`, `PortfolioReader`), stub type aliases. Migrate `MarketDataProvider` import in `tracker.py` from local definition to `protocol.py`. Tests in `tests/unit/test_protocol.py` (~10 tests).
   - **5.c** — Create `src/client/upstox_live.py`: `UpstoxLiveClient` wrapping `upstox_market.py` for market data; order/portfolio methods raise `NotImplementedError` with constraint reason. Tests in `tests/unit/test_upstox_live.py` (~12 tests).
   - **5.d** — Create `src/client/mock_client.py`: stateful `MockBrokerClient` — in-memory price map, order/position tracking, margin validation, one-shot `simulate_error()`, fixture loading. This is the primary test double for all future modules. Tests in `tests/unit/test_mock_client.py` (~25 tests).
   - **5.e** — Create `src/client/factory.py`: `create_client(env)` composition root (`prod`→`UpstoxLiveClient`, `sandbox`→`UpstoxLiveClient` with sandbox token, `test`→`MockBrokerClient`). Only file that imports concrete clients. Tests in `tests/unit/test_factory.py` (~6 tests).
   - **5.f** — Consumer migration: `daily_snapshot.py` switches from direct `UpstoxMarketClient` import to `create_client(UPSTOX_ENV)` (default `"prod"`). `tracker.py` `MarketDataProvider` import confirmed from `protocol.py`. Full suite (246 + new tests) must be green.

6. **P&L visualization** — matplotlib script or React dashboard from snapshot time series. Deferred until several weeks of snapshot history exist and `PortfolioSummary` dataclass is extracted (TODO 1).

---

## Strategy Definitions

### Finideas ILTS
| Leg | Instrument | Key | Entry Price | Qty | Direction |
|---|---|---|---|---|---|
| EBBETF0431 | ETF | `NSE_EQ\|INF754K01LE1` | 1388.12 | 438 | LONG |
| NIFTY DEC 23000 PE | Option | `NSE_FO\|37810` | 975.00 | 65 | LONG |
| NIFTY JUN 23000 CE | Option | `NSE_FO\|37799` | 1082.00 | 65 | LONG |
| NIFTY JUN 23000 PE | Option | `NSE_FO\|37805` | 840.00 | 65 | SHORT |

### Finideas FinRakshak
| Leg | Instrument | Key | Entry Price | Qty | Direction |
|---|---|---|---|---|---|
| NIFTY DEC 23000 PE | Option | `NSE_FO\|37810` | 962.15 | 65 | LONG |

### FinRakshak — Protected MF Portfolio
| Scheme | AMFI Code | Inv. Amt. (₹) | Units |
|---|---|---|---|
| DSP Midcap Fund - Regular Plan - Growth | 104481 | 4,39,978.00 | 4,020.602 |
| Edelweiss Small Cap Fund - Regular Plan - Growth | 146193 | 3,79,981.00 | 8,962.544 |
| HDFC BSE Sensex Index Fund - Growth Plan | 101281 | 1,87,371.53 | 291.628 |
| HDFC Focused Fund - Growth | 102760 | 7,89,960.50 | 3,511.563 |
| Kotak Flexicap Fund - Growth | 112090 | 2,35,105.58 | 5,766.492 |
| Mahindra Manulife Mid Cap Fund - Regular Plan - Growth | 142109 | 4,49,977.50 | 13,962.132 |
| Parag Parikh Flexi Cap Fund - Regular Plan - Growth | 122640 | 17,19,925.75 | 32,424.322 |
| quant Small Cap Fund - Growth - Regular Plan | 100177 | 1,16,321.50 | 714.722 |
| Tata Nifty 50 Index Fund - Regular Plan | 101659 | 5,87,002.67 | 4,506.202 |
| Tata Value Fund - Regular Plan - Growth | 101672 | 9,59,956.25 | 3,726.583 |
| WhiteOak Capital Large Cap Fund - Regular Plan Growth | 150799 | 2,99,985.00 | 20,681.514 |

All 11 codes verified against live AMFI flat file on 2026-04-04.

---

## Test Coverage

- 20 unit tests in `tests/unit/test_portfolio.py`
- 25 unit tests in `tests/unit/mf/test_models.py` — MFTransaction + MFNavSnapshot valid/invalid/edge cases, TransactionType coercion
- 33 unit tests in `tests/unit/mf/test_store.py` — CRUD, upsert idempotency, date range queries, schema coexistence; 5 get_holdings tests updated for `MFHolding` return type including `total_invested` assertions
- 20 unit tests in `tests/unit/mf/test_nav_fetcher.py` — AMFI flat file parse logic, fixture-driven, fully offline. Updated to correct AMFI codes (146193 for Edelweiss replacing 120503).
- 27 unit tests in `tests/unit/mf/test_tracker.py` — pure P&L math (no mocks) + mocked store/fetcher orchestration
- 20 unit tests in `tests/unit/mf/test_seed.py` — transaction shape, verified AMFI code set, idempotency (3 runs), Decimal precision, total_invested sum equality
- 12 unit tests in `tests/unit/mf/test_daily_snapshot_mf.py` — MF wire-up: schema coexistence, full seed→snapshot→aggregate path, empty holdings graceful return, nav_fetcher raise propagation, upsert idempotency
- 7 unit tests in `tests/unit/test_client.py` — UpstoxMarketClient error propagation: LTPFetchError on connection error, timeout, HTTP 500, empty data, missing instrument_token; empty input returns {}; correct price mapping.
- 9 unit tests in `tests/unit/test_exceptions.py` — full exception hierarchy: all 9 isinstance relationships verified (AuthenticationError→BrokerError, RateLimitError→BrokerError, DataFetchError→BrokerError, LTPFetchError→DataFetchError+BrokerError, OrderRejectedError→BrokerError, InsufficientMarginError→OrderRejectedError+BrokerError, InstrumentNotFoundError→BrokerError).
- 11 unit tests in `tests/unit/mf/test_daily_snapshot_helpers.py` — `_etf_current_value` and `_etf_cost_basis` pure helpers; no sys.modules stubs needed — clean direct import since daily_snapshot.py defers all I/O imports.
- 23 unit tests in `tests/unit/test_daily_snapshot_historical.py` — `_compute_strategy_pnl_from_prices` pure helper (6 tests) + `_historical_main` DB-only path (9 tests): success/error exits, output content, MF absent/present paths.
- 4 tests added to `tests/unit/test_portfolio.py` — `PortfolioStore.get_snapshots_for_date`: returns correct snapshots, excludes other dates, empty dict when no data, underlying_price preserved.
- 4 tests added to `tests/unit/mf/test_store.py` — `MFStore.get_nav_snapshots_for_date`: all schemes returned, other dates excluded, empty list, ordered by amfi_code.
- 12 new tests (2026-04-07): `PortfolioStore.get_prev_snapshots` (4 tests in test_portfolio.py), `MFStore.get_prev_nav_snapshots` (4 tests in mf/test_store.py), day-change delta in summary output (2 tests), `_build_prev_prices` helper (2 tests) — both in test_daily_snapshot_historical.py.
- 25 new tests (2026-04-08): `tests/unit/test_notifications.py` — `_html_escape` (5), `escape_mdv2` (3), `TelegramNotifier.send` happy path (6) + error paths (5 including bare Exception), `build_notifier` (6 tests: missing token, missing chat_id, both missing, both set, whitespace stripping, blank token).
- 10 new tests (2026-04-08): `tests/unit/mf/test_daily_snapshot_helpers.py` — `TestBuildPortfolioSummary` (10): isinstance check, date propagation, mf_available flag (True/False), total_value computation, total_pnl computation, total_pnl_pct quantization, all deltas None without prev data, mf_day_delta, total_day_delta absent when only prev_mf absent.
- **Total: 254 tests** — all offline, no API dependency
- `python -m pytest` is the confirmed invocation convention (adds CWD to sys.path automatically)
- `python -m pytest tests/unit/` = full offline suite

---

## Session Log

| Date | What Changed |
|---|---|
| 2026-04-01 — 2026-04-04 | **Foundation sprint.** Auth, portfolio module, full MF stack (models/store/nav_fetcher/tracker), daily snapshot cron, seed scripts. All key decisions now in Architecture Decisions above. All 11 AMFI codes corrected against live AMFI flat file. 8-point code review applied (Decimal migration, shared db.py, enum compat, exception hierarchy, deferred I/O imports). 176 offline tests green. DB wiped and re-seeded; clean baseline from 2026-04-06. |
| 2026-04-07 | --date historical query mode, day-change delta, _compute_prev_mf_pnl. 211 tests all green. |
| 2026-04-08 | **Telegram bot notifications.** `src/notifications/telegram.py`: `TelegramNotifier` + `build_notifier()`. Raw requests, HTML parse_mode, `<pre>` block. Non-fatal (broad Exception catch). `_format_combined_summary()` extracted from `_print_combined_summary()` — both terminal and Telegram share the same formatted text. Injected in `_async_main`, skipped silently when env vars absent. `scripts/send_test_telegram.py` smoke-test script. `.env.example` updated with `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`. 25 new tests, 236 total, all green. |
| 2026-04-08 | **Exception hierarchy expanded.** `src/client/exceptions.py`: added `AuthenticationError`, `RateLimitError`, `OrderRejectedError`, `InsufficientMarginError`, `InstrumentNotFoundError` — all rooted at `BrokerError`. `tests/unit/test_exceptions.py` created with 9 isinstance tests covering every hierarchy relationship. Duplicate isinstance test removed from `test_client.py`. 254 tests total, all green. |
| 2026-04-08 | **PortfolioSummary extraction.** `PortfolioSummary` frozen dataclass added to `src/portfolio/models.py` (snapshot_date, MF/ETF/options components, combined totals, 4 day-delta fields). `_build_portfolio_summary()` extracted into `daily_snapshot.py` — owns all arithmetic previously inline in `_format_combined_summary()`. `_format_combined_summary()` and `_print_combined_summary()` gain optional `snap_date` kwarg (backward compat). Both `_async_main` and `_historical_main` thread `snap_date` through. 10 new tests, 246 total, all green. |
