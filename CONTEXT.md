# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase.
> Read this before writing any code. Do not rely on session summaries or chat history.
> Repo: https://github.com/archeranimesh/NiftyShield

---

## Current State (as of 2026-04-04)

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
├── db.py                     # Shared SQLite context manager — WAL mode, row_factory, FK enforcement, auto commit/rollback.
└── client/
    ├── exceptions.py         # Custom exception hierarchy: BrokerError → DataFetchError → LTPFetchError.
    └── upstox_market.py      # Sync requests client. V3 LTP endpoint. Pipe→colon key remap. Raises LTPFetchError on HTTP error / empty data.

scripts/
├── daily_snapshot.py         # Cron-ready CLI. Module-level imports are stdlib + portfolio.models only (no side effects). All I/O deferred into _async_main(). Fetches LTPs + Nifty spot, records snapshots, MF snapshot, prints combined P&L summary.
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
- `PortfolioSummary` type — combined MF + ETF + options totals computed inline in `daily_snapshot.py`; should migrate to a frozen dataclass in `src/portfolio/models.py` before the visualization commit
- Day-change P&L in combined summary — today vs yesterday delta from `mf_nav_snapshots` not yet surfaced in output. Data accumulates automatically via cron; display enhancement deferred until 2+ clean snapshots exist (from 2026-04-07 onwards).

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
- `PortfolioTracker.compute_pnl()` returns `StrategyPnL` with `total_pnl` as `Decimal`. No bridging cast needed when combining with other `Decimal` values in the combined summary.
- **MF snapshot is non-fatal in cron:** the MF block in `daily_snapshot.py` is wrapped in `try/except Exception`. AMFI unreachable at 3:45 PM does not abort the portfolio snapshot — it logs a WARNING and the combined summary prints `[failed]` for the MF line.
- `seed_mf_holdings.py` separates `build_transactions()` (pure, no I/O) from `seed_holdings()` (calls store) — `build_transactions()` is independently testable with no DB.
- **daily_snapshot.py import design:** module-level imports are stdlib + `src.portfolio.models` only. All I/O-triggering imports (`dotenv`, `UpstoxMarketClient`, `PortfolioStore`, `PortfolioTracker`, `MFStore`, `MFTracker`) are deferred inside `_async_main()`. This makes the pure helpers importable in tests with zero side effects — no `.env`, no DB, no network.
- **Combined P&L has two distinct metrics:** (1) inception P&L — current value minus total invested, permanent fixture of the summary; (2) day-change P&L — today's value minus previous snapshot in `mf_nav_snapshots`. Both should be displayed. Day-change requires 2+ clean snapshots — will be meaningful from 2026-04-07 onwards.
- **Shared SQLite connection factory** in `src/db.py`: single `connect()` context manager used by both `PortfolioStore` and `MFStore`. WAL mode, `sqlite3.Row` factory, foreign key enforcement, auto commit/rollback. Any PRAGMA change applies everywhere from one place.
- **Error hierarchy in `src/client/exceptions.py`:** `BrokerError → DataFetchError → LTPFetchError`. `UpstoxMarketClient` raises `LTPFetchError` on HTTP errors, empty API response, and missing instrument tokens. `get_ohlc_sync` and `get_option_chain_sync` raise `DataFetchError` rather than returning empty dicts silently. Callers distinguish retryable vs terminal errors by catching at the appropriate level.
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
| Day-change P&L not yet displayed | Need 2+ clean snapshots; first delta visible 2026-04-07 after Tuesday cron |

---

## Immediate TODOs (in priority order)

1. **Trade history + roll workflow** — `Trade` model, `TradeAction` enum, `trades` table in store, `scripts/roll_leg.py` CLI. Backfill OPEN trades for existing legs as baseline.
2. **Greeks capture** — fix option chain call (`NSE_INDEX|Nifty 50`), define OptionChain Pydantic model, implement `_extract_greeks_from_chain()`
3. **BrokerClient protocol layer** — `protocol.py`, `UpstoxLiveClient`, `MockBrokerClient`, factory — required before any new feature module
4. **Day-change P&L in combined summary** — query `mf_nav_snapshots` for prior date, compute delta, display alongside inception P&L. Unblock after 2026-04-07.
5. **P&L visualization** — matplotlib script or React dashboard from snapshot time series. `PortfolioSummary` frozen dataclass should be extracted from `daily_snapshot.py` into `src/portfolio/models.py` as part of this commit.

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
- 8 unit tests in `tests/unit/test_client.py` — UpstoxMarketClient error propagation: LTPFetchError on connection error, timeout, HTTP 500, empty data, missing instrument_token; empty input returns {}; correct price mapping; LTPFetchError isinstance DataFetchError.
- 11 unit tests in `tests/unit/mf/test_daily_snapshot_helpers.py` — `_etf_current_value` and `_etf_cost_basis` pure helpers; no sys.modules stubs needed — clean direct import since daily_snapshot.py defers all I/O imports.
- **Total: 176 tests** — all offline, no API dependency
- `python -m pytest` is the confirmed invocation convention (adds CWD to sys.path automatically)
- `python -m pytest tests/unit/` = full offline suite

---

## Session Log

| Date | What Changed |
|---|---|
| 2026-04-01 | Project setup, OAuth flow, API verified, README, project instructions |
| 2026-04-02 | Upstox ecosystem mapped, sandbox scripts, Analytics Token verified, 7 fixtures recorded, instrument keys discovered |
| 2026-04-02 | `src/portfolio/` built end-to-end. 20 tests. First live snapshot run. |
| 2026-04-03 | Added Nifty spot price to batch LTP fetch in `daily_snapshot.py`; `underlying_price` now populated in snapshots; cron job configured; trade history model and roll workflow scoped as next priority. |
| 2026-04-03 | Started `src/mf/` module: MFTransaction, MFNavSnapshot, TransactionType models with 25 unit tests (Commit 1). Established AMFI flat file as NAV source, transaction ledger design for SIP support, shared SQLite DB decision. Confirmed Upstox has no MF API. |
| 2026-04-03 | `src/mf/store.py` (Commit 2): MFStore with mf_transactions + mf_nav_snapshots tables, upsert semantics, get_holdings. 33 tests. DB path confirmed as `data/portfolio/portfolio.sqlite`. MF tables manually initialised in live DB; becomes automatic in Commit 6. |
| 2026-04-03 | `src/mf/nav_fetcher.py` (Commit 3): AMFI flat file fetch + semicolon parse, injectable source for offline tests, missing-code WARNING. 20 tests. Corrected AMFI format: semicolon-delimited, not pipe. |
| 2026-04-03 | `src/mf/tracker.py` (Commit 4): MFTracker, MFHolding (with scheme_name), SchemePnL, PortfolioPnL. Injected nav_fetcher. Discovered MFNavSnapshot requires scheme_name — MFHolding updated accordingly. 27 tests. Total offline suite now 125 tests. |
| 2026-04-03 | Interface fix: MFHolding moved to `models.py` (circular import fix); `store.get_holdings()` rewritten to return `dict[str, MFHolding]` with `total_invested` aggregated alongside units. `seed_mf_holdings.py` (Commit 5, 20 tests) and `daily_snapshot.py` MF wire-up + combined portfolio summary (Commit 6, 23 tests) built and verified on live DB. First live combined snapshot run: 10 of 11 schemes (Tata Nifty 50 AMFI code 148495 unverified). Total offline suite: 168 tests. |
| 2026-04-04 | Discovered all 11 AMFI codes in `seed_mf_holdings.py` were wrong (resolving to completely unrelated schemes). Verified correct codes against live AMFI flat file, updated `_HOLDINGS`, wiped and re-seeded DB. Fixed `sys.modules` stub leak in `test_daily_snapshot_helpers.py` that poisoned `PortfolioTracker` across the full pytest session. Updated `test_nav_fetcher.py` and `test_store.py` to use correct codes. All 168 tests green. DB clean; first correct baseline snapshot Monday 2026-04-06. |
| 2026-04-04 | Code review (8 fixes): (1) StrEnum → (str, Enum) for Python 3.10 compat; (2) Extracted shared `src/db.py` connection factory; (3) Emptied `portfolio/__init__.py` (circular import hazard); (4) Decimal migration for all monetary fields — models, store schema (REAL→TEXT), tracker boundary conversion; (5) AssetType.EQUITY replaces string prefix check for ETF leg identification; (6) Single asyncio.run() in daily_snapshot main(); (7) All I/O imports deferred into _async_main() — sys.modules stubs eliminated from tests; (8) Custom exception hierarchy (BrokerError→DataFetchError→LTPFetchError), UpstoxMarketClient raises instead of silently returning {}. 176 tests green. |
