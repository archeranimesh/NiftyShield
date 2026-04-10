# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase.
> Read this before writing any code. Do not rely on session summaries or chat history.
> Repo: https://github.com/archeranimesh/NiftyShield

---

## Current State (as of 2026-04-08)

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
│   ├── models.py             # Pydantic: Leg, Strategy, DailySnapshot, Trade, TradeAction. Monetary fields (entry_price, ltp, close, underlying_price, price) are Decimal. P&L methods accept float|Decimal, return Decimal. Trade is frozen=True with qty > 0 and price > 0 validators.
│   ├── store.py              # SQLite: strategies, legs, daily_snapshots, trades. Trades methods: record_trade (idempotent), get_trades (strategy/leg filter, date ASC), get_position (net qty + weighted avg buy price), get_all_positions_for_strategy (all leg_roles → (net_qty, avg_price, instrument_key)), ensure_leg (auto-persist trade-only legs to get a DB id for snapshot recording; idempotent). entry_price/ltp/close/underlying_price/price stored as TEXT for Decimal precision. WAL + upsert semantics.
│   ├── tracker.py            # PortfolioTracker: loads strategies, fetches LTPs, records snapshots. Trade overlay applied internally via _get_overlaid_strategy()/_get_all_overlaid_strategies() — compute_pnl, record_daily_snapshot, record_all_strategies all use trade-derived qty/entry_price automatically. Trade-only legs (e.g. LIQUIDBEES) with no DB id are auto-persisted via store.ensure_leg(). compute_pnl() returns StrategyPnL with Decimal total_pnl. Float LTPs from API converted via Decimal(str()) at boundary. apply_trade_positions() module-level pure function: overlays trade-derived qty/entry_price onto strategy Leg objects; appends trade-only legs as EQUITY/CNC; drops zero-net-qty legs.
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
    ├── protocol.py           # BrokerClient + MarketStream protocols. Sub-protocols: MarketDataProvider, OrderExecutor, PortfolioReader. Stub type aliases (= Any) for all Pydantic models not yet in src/models/.
    ├── upstox_market.py      # Sync requests client. V3 LTP endpoint. Pipe→colon key remap. Raises LTPFetchError on HTTP error / empty data.
    ├── upstox_live.py        # UpstoxLiveClient: production BrokerClient. Delegates get_ltp + get_option_chain to UpstoxMarketClient (Analytics Token). Order execution raises NotImplementedError (static IP blocked). Portfolio read raises NotImplementedError (Daily OAuth token required). Expired instruments + historical candles raise NotImplementedError.
    └── factory.py            # Composition root. create_client(env) → BrokerClient. env: "prod" → UpstoxLiveClient (UPSTOX_ANALYTICS_TOKEN), "sandbox" → UpstoxLiveClient (UPSTOX_SANDBOX_TOKEN), "test" → MockBrokerClient. ONLY file in src/ that imports concrete clients.

scripts/
├── daily_snapshot.py         # Two-mode CLI. Live mode: fetches LTPs via await client.get_ltp() + Nifty spot, records snapshots, prints P&L, sends Telegram notification (non-fatal). Historical mode (--date YYYY-MM-DD): reads stored snapshots, computes P&L offline — no API call. _format_combined_summary() returns the formatted string; _print_combined_summary() wraps it with print(). Module-level imports stay stdlib + portfolio.models only; all I/O deferred. Live mode uses create_client(os.getenv("UPSTOX_ENV", "prod")) — UPSTOX_ENV=test runs against MockBrokerClient for local smoke-testing without a real token. Both modes apply apply_trade_positions() overlay after get_all_strategies(); PortfolioTracker also applies the overlay internally so compute_pnl and record_daily_snapshot use trade-derived quantities.
├── send_test_telegram.py     # Smoke-test script. Reads TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID from .env, sends a sample P&L message. Exit code 0/1. Run before first cron to verify credentials.
├── seed_mf_holdings.py       # One-time CLI. Inserts 11 INITIAL MF transactions. Idempotent. --dry-run flag.
├── seed_trades.py            # Idempotent backfill of all finideas_ilts + finrakshak executions as Trade rows. build_trades() (pure) + seed_trades() (I/O). --dry-run flag. 7 trades total. strategy_name must match strategies table (finideas_ilts, finrakshak).
└── record_trade.py           # CLI for recording future trades. Validates via Trade model; inserts; prints updated net position + avg price. --dry-run prints without touching DB. --strategy takes DB strategy name (e.g. finideas_ilts, not ILTS).

tests/
├── unit/
│   ├── portfolio/
│   │   ├── __init__.py
│   │   ├── test_trade_models.py    # 20 tests: TradeAction enum, Trade valid/invalid construction, qty/price validators, frozen=True, Decimal precision
│   │   ├── test_trade_store.py     # 25 tests: record_trade CRUD, idempotency, get_trades filters + ordering, get_position (BUY-only, SELL-only, mixed, weighted avg, ignores SELL price, schema coexistence)
│   │   └── test_seed_trades.py     # 13 tests: build_trades shape, strategy/leg/key correctness, BUY+SELL actions, idempotency (3×), EBBETF0431 weighted avg, NIFTY_JUN_PE short position
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

- ~~`src/client/protocol.py`~~ — **DONE (2026-04-08)**: BrokerClient + MarketStream protocols, sub-protocols (MarketDataProvider, OrderExecutor, PortfolioReader), stub type aliases. MarketDataProvider migrated out of tracker.py.
- ~~`src/client/upstox_live.py`~~ — **DONE (2026-04-08)**: UpstoxLiveClient wrapping UpstoxMarketClient. get_ltp + get_option_chain delegate to _market. Order/portfolio/expired methods raise NotImplementedError with documented reasons. 14 tests in test_upstox_live.py.
- ~~`src/client/mock_client.py`~~ — **DONE (2026-04-08)**: MockBrokerClient (stateful, offline). Internal state: `_margin_available` (Decimal), `_orders`, `_positions`, `_price_map`, `_error_queue`. Test-setup API: `set_price`, `set_margin`, `simulate_error` (one-shot), `reset`. All 10 BrokerClient methods implemented; fixture loading graceful (WARNING + empty return on miss). 38 tests in `test_mock_client.py`.
- ~~`src/client/factory.py`~~ — **DONE (2026-04-08)**: `create_client(env)` composition root. Sole importer of `UpstoxLiveClient` + `MockBrokerClient`. `env` → `"prod"` / `"sandbox"` / `"test"`. `sandbox` falls back to `UPSTOX_SANDBOX_TOKEN` env var when `token=` kwarg absent. `ValueError` on unknown env. 10 tests in `tests/unit/test_factory.py`; all green.
- `src/models/` — shared Pydantic models (not written; models are local to portfolio/ and mf/ — both will migrate here in a future refactor commit)
- `src/strategy/`, `src/execution/`, `src/backtest/`, `src/risk/`, `src/streaming/` — all empty
- OptionChain Pydantic model — not defined
- Greeks capture — `_fetch_greeks()` returns `{}` immediately (explicit TODO)
- `scripts/roll_leg.py` — CLI to close an old leg and open a replacement in one atomic transaction (not written)
- ~~Trade history model~~ — **DONE (2026-04-08)**: `Trade` + `TradeAction` in `src/portfolio/models.py`. `trades` table in `PortfolioStore` with `record_trade`, `get_trades`, `get_position`. `scripts/seed_trades.py` (backfill) + `scripts/record_trade.py` (ongoing capture). Live DB seeded with 7 trades. 58 new tests.
- ~~`PortfolioSummary` type~~ — **DONE (2026-04-08)**: `PortfolioSummary` frozen dataclass added to `src/portfolio/models.py`. `_build_portfolio_summary()` extracted from `_format_combined_summary()` in `daily_snapshot.py`. Both callers (`_async_main`, `_historical_main`) thread `snap_date` through. 10 new tests, 246 total.
- ~~Day-change P&L in combined summary~~ — **DONE (2026-04-07)**: `PortfolioStore.get_prev_snapshots()`, `MFStore.get_prev_nav_snapshots()`, `_build_prev_prices()`, `_compute_prev_mf_pnl()` helpers added. Combined summary now shows `Δday` for MF, ETF, and options when prev data exists; column omitted silently on first run.
- ~~FinRakshak protection effectiveness stats~~ — **DONE (2026-04-10)**: `finrakshak_day_delta` field added to `PortfolioSummary`. Computed in `_build_portfolio_summary` by isolating finrakshak's contribution from combined `options_day_delta`. `_format_protection_stats()` pure helper appends a protection section to the log output (MF Δday / FinRakshak Δday / Net + ✅/⚠️ verdict). Telegram header line now includes hedge verdict and net amount. 10 new tests (31 total in test_daily_snapshot_helpers.py). Omitted silently on first run.

### Live Data

- SQLite DB path confirmed: `data/portfolio/portfolio.sqlite`
- DB wiped clean on 2026-04-04 (`daily_snapshots`, `mf_transactions`, `mf_nav_snapshots` all cleared)
- `mf_transactions` re-seeded with all 11 schemes using correct AMFI codes
- `mf_nav_snapshots` empty — first clean snapshot on Monday 2026-04-06 (pre-market run)
- `daily_snapshots` empty — first clean baseline on Monday 2026-04-06 (pre-market run)
- `underlying_price` will populate from 2026-04-06 onwards
- Greeks columns are null across all snapshots
- `trades` table seeded 2026-04-08 — 7 rows: finideas_ilts (6 legs including LIQUIDBEES) + finrakshak (1). EBBETF0431 net=465 @ avg ₹1388.01. **strategy_name migrated 2026-04-08:** `ILTS` → `finideas_ilts`, `FinRakshak` → `finrakshak` to match strategies table. Must use DB strategy names in all future `record_trade.py` calls.
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
| LIQUIDBEES ETF | `NSE_EQ\|INF732E01037` | Verified 2026-04-08 via InstrumentLookup.search_equity('LIQUIDBEES') on NSE.json.gz BOD file |
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
- **BrokerClient protocol design (`src/client/protocol.py`):** Three narrow sub-protocols (ISP) — `MarketDataProvider` (tracker/signal), `OrderExecutor` (execution), `PortfolioReader` (monitoring). `BrokerClient` is kept flat (not inheriting from sub-protocols) so its full method list is readable in one place. Python structural typing means any class satisfying all 10 `BrokerClient` methods automatically satisfies all three sub-protocols. Stub type aliases (`X = Any`) with `# TODO` comments stand in for the 11 Pydantic models that will live in `src/models/`. All method signatures use `from __future__ import annotations` so protocol.py has zero import-time dependency on `src/models/`. `MarketDataProvider` was previously defined inline in `tracker.py`; it now lives in `protocol.py` and is re-exported through `tracker.py`'s namespace for backward compatibility.
- **UpstoxLiveClient delegation pattern (`src/client/upstox_live.py`):** `UpstoxLiveClient` holds `self._market: UpstoxMarketClient` (Analytics Token). `get_ltp` and `get_option_chain` are pure async pass-throughs to `_market`; they propagate all exceptions unmodified (LTPFetchError, DataFetchError). No inheritance — protocol conformance is structural. `isinstance(client, BrokerClient)` and `isinstance(client, MarketDataProvider)` both return True.
- **Two-token constraint:** Analytics Token (long-lived, env var `UPSTOX_ANALYTICS_TOKEN`) powers market data — LTP, option chain, candles. Daily OAuth token (Algo Trading app) is required for positions, holdings, and margins. `UpstoxLiveClient` currently holds only the Analytics Token. `get_positions`, `get_holdings`, and `get_margins` raise `NotImplementedError("Requires Daily OAuth token")` until the client is extended to accept a second token.
- **NotImplementedError policy for blocked methods:** Methods blocked by infrastructure constraints raise `NotImplementedError` with a message that names the constraint and points to CONTEXT.md. Three categories: (1) Order execution — `_raise_order_blocked()` centralises the message for `place_order`, `modify_order`, `cancel_order`; (2) Portfolio read — individual `NotImplementedError` in each method citing Daily OAuth token; (3) Data constraints — `get_historical_candles` (not yet wired in UpstoxMarketClient), `get_expired_option_contracts` (paid subscription). This policy means callers see a clear error rather than silent wrong behaviour when a constraint is not yet resolved.
- **Composition root pattern (`src/client/factory.py`):** `create_client(env)` is the only function in `src/` that imports `UpstoxLiveClient` or `MockBrokerClient` directly. All other modules receive a `BrokerClient` via constructor injection — they import only `src.client.protocol.BrokerClient`. This keeps the dependency graph clean and makes swapping implementations (e.g., test → prod) a one-line change at the call site. `VALID_ENVS: Final = ("prod", "sandbox", "test")` is the canonical list of valid environments. `sandbox` falls back to `UPSTOX_SANDBOX_TOKEN` env var when `token=` kwarg is absent, consistent with 12-factor config.
- **Consumer migration to factory pattern (2026-04-08):** `daily_snapshot.py` is the sole external consumer of market data. It now calls `create_client(os.getenv("UPSTOX_ENV", "prod"))` inside `_async_main()` — `"prod"` is the default, preserving live cron behaviour unchanged. Setting `UPSTOX_ENV=test` in the environment routes the snapshot logic through `MockBrokerClient` for local smoke-testing without a real token. `src/portfolio/tracker.py` was already importing `MarketDataProvider` from `src.client.protocol` (done in 5.b). `UpstoxMarketClient` remains as an internal implementation detail of `UpstoxLiveClient`; it is no longer imported by any module outside `src/client/`.
- **MockBrokerClient design (`src/client/mock_client.py`):** Stateful offline broker client — the only implementation to use for order-execution tests until static IP is provisioned. Margin is tracked as `Decimal`; order notional deducts `price * quantity * 0.1` as a NRML proxy. `simulate_error(method_name, exc)` is one-shot: the queued exception fires once on the next call and is then removed — second call succeeds normally. Fixture loading convention: `option_chain/{instrument}_{expiry}.json` where pipe (`|`) and spaces become underscores; `historical_candles/{instrument}_{interval}.json`. Missing fixtures log WARNING and return `None`/`[]`/`{}` — never raises. `reset()` clears orders, positions, and error queue; restores default margin (500 000); preserves `_price_map` and `fixtures_dir`. `get_expired_option_contracts` always returns `[]` (paid API blocked).
- **Error hierarchy in `src/client/exceptions.py`:** Full tree rooted at `BrokerError`: `AuthenticationError` (token/OAuth failure), `RateLimitError` (429, retryable), `DataFetchError` (retryable) → `LTPFetchError`, `OrderRejectedError` (terminal) → `InsufficientMarginError`, `InstrumentNotFoundError` (terminal). `UpstoxMarketClient` raises `LTPFetchError` on HTTP errors, empty API response, and missing instrument tokens. `get_ohlc_sync` and `get_option_chain_sync` raise `DataFetchError` rather than returning empty dicts silently. Callers distinguish retryable vs terminal errors by catching at the appropriate level.
- **Monetary field types:** `Leg.entry_price`, `DailySnapshot.ltp`, `.close`, `.underlying_price` are `Decimal`. SQLite stores them as `TEXT` columns to preserve precision through round-trips. `Leg.pnl()` and `pnl_percent()` accept `float | Decimal` — float inputs go through `Decimal(str())` inside the method. Float LTPs from the broker API are converted via `Decimal(str(ltp))` at the tracker boundary before entering any model or P&L calculation.
- **Enum compatibility:** `Direction`, `ProductType`, `AssetType` use `(str, Enum)` pattern (not `StrEnum`) — `StrEnum` was introduced in Python 3.11; the project targets Python 3.10+.

- **Trade ledger design:** `Leg` (in `ilts.py` / `finrakshak.py`) is a conceptual role — instrument + direction + entry price as a strategy definition. `Trade` (in the `trades` table) is a physical execution — what actually transacted, when, at what price. The two coexist permanently: `Leg` defines the strategy shape; `Trade` drives cost-basis and qty. `apply_trade_positions()` bridges them at runtime — `daily_snapshot.py` P&L now uses trade-derived qty and weighted avg price for any leg that has trades, and appends trade-only legs (LIQUIDBEES) as EQUITY/CNC legs.
- **`trades` UNIQUE constraint is `(strategy_name, leg_role, trade_date, action)`** — allows one BUY and one SELL for the same leg on the same date (e.g., a same-day roll), but prevents double-seeding or duplicate CLI calls. Idempotent via `ON CONFLICT DO NOTHING`.
- **`get_position` aggregates in Python, not SQL** — same rationale as `get_holdings()` in `MFStore`. `Decimal(row["price"])` read back from TEXT column; all arithmetic in Python preserves exact precision. SELL price is deliberately excluded from the average — it is premium received, not capital deployed.
- **LIQUIDBEES is tracked in `trades` and flows into `daily_snapshot.py` via the trade overlay** — it is not a `Leg` in `ilts.py` (not a strategy leg in the Finideas sense), but `apply_trade_positions()` appends it as an `EQUITY/CNC` leg at runtime so its mark-to-market value is included in the ETF component of the combined summary.
- **`seed_trades.py` separates `build_trades()` (pure) from `seed_trades()` (I/O)** — mirrors `seed_mf_holdings.py` pattern. Tests call `build_trades()` directly with no DB. Dates marked `2026-01-15` are placeholders pending contract note verification.
- **Trade overlay internalized in PortfolioTracker (2026-04-08):** `_get_overlaid_strategy()` / `_get_all_overlaid_strategies()` private helpers load a strategy from the store and apply `apply_trade_positions()` before returning. `compute_pnl`, `record_daily_snapshot`, and `record_all_strategies` all use overlaid strategies — no caller needs to manually apply the overlay for these paths. `daily_snapshot.py` still applies the overlay for `_format_combined_summary` and `_etf_current_value` (these use the local `strategies` list, not the tracker).
- **Trade-only legs auto-persisted via `ensure_leg()` (2026-04-08):** When `record_daily_snapshot` encounters a leg with `id is None` (e.g. LIQUIDBEES appended by the overlay), it calls `store.ensure_leg(strategy_name, leg)` to upsert the leg into the `legs` table and obtain a DB id. Idempotent — returns existing id on subsequent runs. Without this, trade-only legs would be silently skipped in snapshot recording.
- **`trades.strategy_name` must match `strategies.name` exactly (2026-04-08):** Original seed used informal names (`ILTS`, `FinRakshak`) while strategies table had `finideas_ilts`, `finrakshak`. The mismatch caused `get_all_positions_for_strategy()` to return empty results, silently disabling the trade overlay. Migrated existing rows and fixed `seed_trades.py` + `record_trade.py`. Canonical names: `finideas_ilts`, `finrakshak`.

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

3. ~~**Trade history + roll workflow**~~ — **DONE (2026-04-08)**: `Trade` + `TradeAction` models, `trades` table in `PortfolioStore`, `seed_trades.py`, `record_trade.py`. Live DB seeded. `scripts/roll_leg.py` (atomic close + open) still outstanding — required before JUN 2026 expiry roll (2026-06-30).

4. **Greeks capture** — fix option chain call (`NSE_INDEX|Nifty 50`), define `OptionChain` Pydantic model, implement `_extract_greeks_from_chain()`. Fixture `nifty_chain_2026-04-07.json` already recorded — use it to drive the model definition.

5. ~~**BrokerClient protocol layer**~~ — **ALL DONE (2026-04-08)**. Full dependency-inversion layer in place. `UpstoxMarketClient` wrapped inside `UpstoxLiveClient`; no consumer outside `src/client/` imports it directly. Sub-tasks in order:
   - ~~**5.a** — Expand `src/client/exceptions.py`: add `AuthenticationError`, `RateLimitError`, `OrderRejectedError`, `InsufficientMarginError`, `InstrumentNotFoundError`. Tests in `tests/unit/test_exceptions.py` (8 tests).~~ **DONE (2026-04-08)**
   - ~~**5.b**~~ — **DONE (2026-04-08)**: `src/client/protocol.py` created with full `BrokerClient` + `MarketStream` protocols, sub-protocols (`MarketDataProvider`, `OrderExecutor`, `PortfolioReader`), stub type aliases. `MarketDataProvider` migrated from inline `tracker.py` definition to `protocol.py` import. 11 tests in `tests/unit/test_protocol.py`. 265 total tests, all green.
   - ~~**5.c**~~ — **DONE (2026-04-08)**: `src/client/upstox_live.py` created. `UpstoxLiveClient` wraps `UpstoxMarketClient` for `get_ltp` + `get_option_chain`. All blocked methods raise `NotImplementedError` with documented reasons. 14 tests in `tests/unit/test_upstox_live.py`. 279 total, all green.
   - ~~**5.d**~~ — **DONE (2026-04-08)**: `src/client/mock_client.py` created. Stateful `MockBrokerClient` — in-memory `_price_map`, `_orders`, `_positions`, `_margin_available` (Decimal), `_error_queue`. Setup API: `set_price`, `set_margin`, `simulate_error` (one-shot), `reset`. All 10 `BrokerClient` methods implemented; fixture loading graceful (WARNING + empty return on miss). `price*qty*0.1` NRML margin proxy. 38 tests in `tests/unit/test_mock_client.py`; all green.
   - ~~**5.e**~~ — **DONE (2026-04-08)**: `src/client/factory.py` created. `create_client(env)` is the sole composition root and the only `src/` importer of `UpstoxLiveClient` + `MockBrokerClient`. 10 tests in `tests/unit/test_factory.py`; all green.
   - ~~**5.f**~~ — **DONE (2026-04-08)**: `daily_snapshot.py` migrated from direct `UpstoxMarketClient` import to `create_client(os.getenv("UPSTOX_ENV", "prod"))`. `tracker.py` confirmed already using `from src.client.protocol import MarketDataProvider`. `UpstoxMarketClient` no longer imported by any consumer outside `src/client/`. No new tests — pure refactor. 327 tests total, all green.

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
- 11 unit tests in `tests/unit/test_protocol.py` — `UpstoxMarketClient` satisfies `MarketDataProvider` (True) and NOT `BrokerClient` (False, intentional gap); `DummyBrokerClient` (all 10 methods) satisfies all four protocols; `DummyMarketStream` satisfies `MarketStream`; `BrokerClient` does not satisfy `MarketStream`; both `from src.client.protocol import MarketDataProvider` and `from src.portfolio.tracker import MarketDataProvider` resolve to the same object.
- 9 unit tests in `tests/unit/test_exceptions.py` — full exception hierarchy: all 9 isinstance relationships verified (AuthenticationError→BrokerError, RateLimitError→BrokerError, DataFetchError→BrokerError, LTPFetchError→DataFetchError+BrokerError, OrderRejectedError→BrokerError, InsufficientMarginError→OrderRejectedError+BrokerError, InstrumentNotFoundError→BrokerError).
- 11 unit tests in `tests/unit/mf/test_daily_snapshot_helpers.py` — `_etf_current_value` and `_etf_cost_basis` pure helpers; no sys.modules stubs needed — clean direct import since daily_snapshot.py defers all I/O imports.
- 23 unit tests in `tests/unit/test_daily_snapshot_historical.py` — `_compute_strategy_pnl_from_prices` pure helper (6 tests) + `_historical_main` DB-only path (9 tests): success/error exits, output content, MF absent/present paths.
- 4 tests added to `tests/unit/test_portfolio.py` — `PortfolioStore.get_snapshots_for_date`: returns correct snapshots, excludes other dates, empty dict when no data, underlying_price preserved.
- 4 tests added to `tests/unit/mf/test_store.py` — `MFStore.get_nav_snapshots_for_date`: all schemes returned, other dates excluded, empty list, ordered by amfi_code.
- 12 new tests (2026-04-07): `PortfolioStore.get_prev_snapshots` (4 tests in test_portfolio.py), `MFStore.get_prev_nav_snapshots` (4 tests in mf/test_store.py), day-change delta in summary output (2 tests), `_build_prev_prices` helper (2 tests) — both in test_daily_snapshot_historical.py.
- 25 new tests (2026-04-08): `tests/unit/test_notifications.py` — `_html_escape` (5), `escape_mdv2` (3), `TelegramNotifier.send` happy path (6) + error paths (5 including bare Exception), `build_notifier` (6 tests: missing token, missing chat_id, both missing, both set, whitespace stripping, blank token).
- 10 new tests (2026-04-08): `tests/unit/mf/test_daily_snapshot_helpers.py` — `TestBuildPortfolioSummary` (10): isinstance check, date propagation, mf_available flag (True/False), total_value computation, total_pnl computation, total_pnl_pct quantization, all deltas None without prev data, mf_day_delta, total_day_delta absent when only prev_mf absent.
- 20 unit tests in `tests/unit/portfolio/test_trade_models.py` — `TradeAction` enum coercion/rejection, `Trade` BUY+SELL construction, qty/price > 0 validation, `frozen=True` enforcement, `Decimal` precision round-trip, float coercion via `str()`.
- 25 unit tests in `tests/unit/portfolio/test_trade_store.py` — `record_trade` insert + idempotency, `get_trades` strategy/leg filters + date ASC ordering, `get_position` net qty (BUY-only, SELL-only, mixed), weighted avg price, SELL price ignored, schema coexistence with existing tables.
- 13 unit tests in `tests/unit/portfolio/test_seed_trades.py` — `build_trades` count/shape/keys, ILTS BUY+SELL mix, FinRakshak all-BUY, idempotency (3×), `get_position` weighted avg for EBBETF0431, short net qty for NIFTY_JUN_PE.
- 6 unit tests added to `tests/unit/portfolio/test_trade_store.py` — `get_all_positions_for_strategy`: empty, single-leg, multi-leg, weighted-avg accumulation, instrument_key provenance, strategy isolation. 26 total in this file.
- 9 unit tests in `tests/unit/portfolio/test_apply_trade_positions.py` — `apply_trade_positions`: passthrough (no positions), known-leg qty+price update, instrument_key preserved, options legs passthrough, zero-qty leg dropped, unknown leg_role appended as EQUITY/CNC, zero unknown not appended, original not mutated, name/description preserved.
- 2 unit tests added to `tests/unit/test_daily_snapshot_historical.py` — `TestTradeOverlayInHistoricalMain`: overlay updates qty in P&L, LIQUIDBEES appended to ETF value.
- **Total: 400 tests** — all offline, no API dependency
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
| 2026-04-08 | **BrokerClient protocol layer (5.b).** `src/client/protocol.py`: `BrokerClient` + `MarketStream` full protocols; sub-protocols `MarketDataProvider`, `OrderExecutor`, `PortfolioReader`; 11 stub type aliases (= Any) with TODO comments. `tracker.py` migrated from local `MarketDataProvider` class definition to `from src.client.protocol import MarketDataProvider`. 11 new tests in `tests/unit/test_protocol.py`; 265 total, all green. |
| 2026-04-08 | **PortfolioSummary extraction.** `PortfolioSummary` frozen dataclass added to `src/portfolio/models.py` (snapshot_date, MF/ETF/options components, combined totals, 4 day-delta fields). `_build_portfolio_summary()` extracted into `daily_snapshot.py` — owns all arithmetic previously inline in `_format_combined_summary()`. `_format_combined_summary()` and `_print_combined_summary()` gain optional `snap_date` kwarg (backward compat). Both `_async_main` and `_historical_main` thread `snap_date` through. 10 new tests, 246 total, all green. |
| 2026-04-08 | **UpstoxLiveClient (5.c).** `src/client/upstox_live.py`: production `BrokerClient` implementation. `get_ltp` and `get_option_chain` delegate to `UpstoxMarketClient` (Analytics Token) via `self._market`. `place_order`/`modify_order`/`cancel_order` raise `NotImplementedError` via `_raise_order_blocked()` (static IP constraint). `get_positions`/`get_holdings`/`get_margins` raise `NotImplementedError` (Daily OAuth token required). `get_historical_candles` and `get_expired_option_contracts` raise `NotImplementedError` (not yet wired / paid subscription). Satisfies `BrokerClient` and `MarketDataProvider` via structural typing — no inheritance. 14 tests in `tests/unit/test_upstox_live.py`; 279 total, all green. |
| 2026-04-08 | **MockBrokerClient (5.d).** `src/client/mock_client.py`: stateful offline broker client. `_margin_available` (Decimal), `_orders`, `_positions`, `_price_map`, `_error_queue`. Setup API: `set_price`, `set_margin`, `simulate_error` (one-shot), `reset`. All 10 `BrokerClient` methods; fixture loading graceful (WARNING + empty on miss); `price*qty*0.1` NRML margin proxy; `place_order` / `modify_order` / `cancel_order` raise correct exception types. 38 tests in `tests/unit/test_mock_client.py`; all green. |
| 2026-04-08 | **Composition root factory (5.e).** `src/client/factory.py`: `create_client(env, **kwargs)` is the sole `src/` importer of `UpstoxLiveClient` and `MockBrokerClient`. `env="prod"` → `UpstoxLiveClient` (UPSTOX_ANALYTICS_TOKEN); `env="sandbox"` → `UpstoxLiveClient` (UPSTOX_SANDBOX_TOKEN, with kwarg fallback); `env="test"` → `MockBrokerClient` (offline). `ValueError` on unknown env with hint message. `VALID_ENVS: Final = ("prod", "sandbox", "test")`. 10 tests in `tests/unit/test_factory.py` (all env branches, kwargs forwarding, margin propagation, BrokerClient isinstance, env-var sandbox fallback); all green. |
| 2026-04-08 | **Consumer migration to factory (5.f — final).** `daily_snapshot.py` switched from direct `UpstoxMarketClient` import to `create_client(os.getenv("UPSTOX_ENV", "prod"))` inside `_async_main()`. `import os` added at module level (stdlib). `tracker.py` confirmed already using `from src.client.protocol import MarketDataProvider`. `test_client.py` confirmed clean — no hierarchy tests (those were removed in 5.a). `UpstoxMarketClient` no longer imported by any consumer outside `src/client/`. `UPSTOX_ENV=test` enables `MockBrokerClient`-backed smoke-test without a real token. Pure refactor — no new tests. 327 tests, all green. **TODO #5 complete.** |
| 2026-04-08 | **Trade ledger.** `TradeAction` + `Trade` (frozen Pydantic, qty/price > 0) added to `src/portfolio/models.py`. `trades` table added to `PortfolioStore` (additive, `CREATE IF NOT EXISTS`): `record_trade` (idempotent), `get_trades` (strategy/leg filter, date ASC), `get_position` (net qty + weighted avg buy price in Python). `scripts/seed_trades.py` backfills all ILTS + FinRakshak positions (7 trades). `scripts/record_trade.py` CLI for future captures — validates via model, inserts, prints position summary. LIQUIDBEES key verified against `NSE.json.gz` BOD: `NSE_EQ\|INF732E01037`. Live DB seeded; existing tables untouched (20 snapshots, 11 MF transactions confirmed). 58 new tests in `tests/unit/portfolio/`. 385 total, all green. |
| 2026-04-08 | **Trade overlay into P&L pipeline.** `get_all_positions_for_strategy()` added to `PortfolioStore` — returns all leg_roles with (net_qty, avg_price, instrument_key) for a strategy. `apply_trade_positions()` pure function added to `src/portfolio/tracker.py` — patches Leg qty/entry_price from trades, appends trade-only legs (LIQUIDBEES) as EQUITY/CNC, drops zero-net-qty legs, returns new Strategy without mutating original. Wired into both `_async_main` and `_historical_main` in `daily_snapshot.py` immediately after `get_all_strategies()`. P&L now reflects actual traded qty and weighted avg cost basis. 17 new tests (6 store + 9 apply_trade_positions + 2 integration). 400 total, all green. |
| 2026-04-08 | **Trade overlay internalized + strategy name fix.** Three bugs fixed: (1) `daily_snapshot.py` called `client.get_ltp_sync()` which doesn't exist on `UpstoxLiveClient` — changed to `await client.get_ltp()`. (2) `PortfolioTracker.compute_pnl`, `record_daily_snapshot`, `record_all_strategies` re-loaded raw DB legs, bypassing the trade overlay — added `_get_overlaid_strategy()` / `_get_all_overlaid_strategies()` private helpers so the overlay is applied internally. Trade-only legs (LIQUIDBEES) with no DB id are auto-persisted via new `store.ensure_leg()`. (3) `trades.strategy_name` used `ILTS`/`FinRakshak` but `strategies.name` had `finideas_ilts`/`finrakshak` — overlay returned empty and was silently a no-op. Migrated DB rows + fixed `seed_trades.py`, `record_trade.py`, and test assertions. 240 portfolio+MF tests green. |
