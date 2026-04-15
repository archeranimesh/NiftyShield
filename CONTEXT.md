# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase.
> Read this before writing any code. Do not rely on session summaries or chat history.
> Repo: https://github.com/archeranimesh/NiftyShield

**Related files:** [DECISIONS.md](DECISIONS.md) — architecture rationale | [REFERENCES.md](REFERENCES.md) — instrument keys, AMFI codes, API quirks | [TODOS.md](TODOS.md) — open work + session log | [PLANNER.md](PLANNER.md) — multi-sprint roadmap | [INSTRUCTION.md](INSTRUCTION.md) — per-task prompt templates and session workflow

---

## Current State (as of 2026-04-14)

### What Exists (committed and working)

```
src/
├── auth/
│   ├── login.py              # OAuth flow — opens browser, captures code, saves token to .env
│   ├── verify.py             # API connectivity check — fetches user profile
│   ├── nuvama_login.py       # Nuvama request_id flow — opens browser, captures request_id from redirect, initializes APIConnect session, saves NUVAMA_SETTINGS_FILE to .env. APIConnect persists session token in settings_file (no daily re-auth required after first login).
│   └── nuvama_verify.py      # Nuvama connectivity check — loads APIConnect from settings_file, calls Holdings(), prints holding count + ltp. parse_holdings() is a pure function (testable independently).
│   ├── dhan_login.py          # Dhan manual token flow — opens web.dhan.co, prompts for token, validates, saves DHAN_ACCESS_TOKEN to .env via dotenv.set_key(). Pure functions: build_login_url(), validate_token(), save_token(). No SDK dependency.
│   └── dhan_verify.py         # Dhan connectivity check — loads DHAN_CLIENT_ID + DHAN_ACCESS_TOKEN, calls GET /v2/profile + /v2/holdings via raw requests. parse_holdings() pure function. Returns True/False.
├── analytics/                # Exploratory scripts (not production modules)
│   └── verify_analytics.py   # Tests LTP, option chain, Greeks, historical candles via Analytics Token
├── sandbox/                  # Exploratory scripts
│   └── order_lifecycle.py    # Place → Modify → Cancel via V3 Order API (sandbox=True)
├── portfolio/
│   ├── CLAUDE.md             # Module context: Leg/Trade distinction, Decimal invariant, apply_trade_positions() overlay, strategy_name constraint
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
│   ├── CLAUDE.md             # Module context: transaction ledger model, AMFI source, Decimal TEXT invariant, MFHolding location
│   ├── __init__.py           # Package marker
│   ├── models.py             # Pydantic: MFTransaction, MFNavSnapshot, TransactionType enum. Also: MFHolding frozen dataclass.
│   ├── store.py              # SQLite: mf_transactions + mf_nav_snapshots in shared DB. get_holdings() returns dict[str, MFHolding].
│   ├── nav_fetcher.py        # AMFI flat file download + parse → {amfi_code: Decimal}. Injectable source for offline tests.
│   └── tracker.py            # MFTracker: load holdings, fetch NAVs, upsert snapshots, return PortfolioPnL. MFHolding imported from models.
├── dhan/
│   ├── CLAUDE.md             # Module context: classification config, data flow, Dhan API quirks
│   ├── __init__.py           # Package marker
│   ├── models.py             # Frozen dataclasses: DhanHolding (EQUITY/BOND, LTP, cost/pnl properties), DhanPortfolioSummary (split by classification, Decimal fields, day deltas)
│   ├── reader.py             # Pure + HTTP functions. fetch_holdings_raw/fetch_ltp_raw (I/O). classify_holding, build_dhan_holdings (filter+classify), build_security_id_map, enrich_with_ltp (Dhan API — paid tier), enrich_with_upstox_prices (preferred), upstox_keys_for_holdings, build_dhan_summary (pure). fetch_dhan_holdings() + fetch_dhan_portfolio() orchestrators.
│   └── store.py              # DhanStore: dhan_holdings_snapshots table. record_snapshot (upsert), get_snapshot_for_date, get_prev_snapshot (MAX date < d, keyed by ISIN).
├── instruments/
│   └── lookup.py             # Offline BOD search (NSE.json.gz). CLI: --find-legs mode. search() uses ranked exact>prefix>fuzzy scoring via _score_query()/_best_score() (rapidfuzz; difflib fallback). min_score param added.
├── notifications/
│   ├── CLAUDE.md             # Module context: non-fatal contract, build_notifier() → None, HTML parse_mode
│   ├── __init__.py           # Package marker.
│   └── telegram.py           # TelegramNotifier: fire-and-forget sendMessage via raw requests (HTML parse_mode, <pre> block). build_notifier() returns None when env vars absent. send() never raises — catches Exception broadly, logs WARNING, returns False.
├── nuvama/
│   ├── __init__.py           # Package marker
│   ├── models.py             # Frozen dataclasses: NuvamaBondHolding (isin/qty/avg_price/ltp/chg_pct/hair_cut; cost_basis/current_value/pnl/pnl_pct/day_delta properties), NuvamaBondSummary (total_value/basis/pnl/pnl_pct/total_day_delta). All BOND classification.
│   ├── reader.py             # parse_bond_holdings() (pure, joins positions dict for avg_price, skips _EXCLUDE_ISINS + missing positions with WARNING, catches InvalidOperation), build_nuvama_summary() (pure aggregation), fetch_nuvama_portfolio() (I/O orchestrator). _extract_rms_hdg() handles both resp.data.rmsHdg and eq.data.rmsHdg response paths.
│   └── store.py              # NuvamaStore: nuvama_positions (ISIN PK, avg_price TEXT, qty, label — seed once via seed_nuvama_positions.py), nuvama_holdings_snapshots (UNIQUE(isin, snapshot_date) upsert). get_positions() → ISIN→Decimal. get_prev_total_value() calendar-agnostic Python-Decimal sum.
├── db.py                     # Shared SQLite context manager — WAL mode, row_factory, FK enforcement, auto commit/rollback.
└── client/
    ├── CLAUDE.md             # Module context: BrokerClient protocol rule, 4 implementations, active constraints
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
├── record_trade.py           # CLI for recording future trades. Validates via Trade model; inserts; prints updated net position + avg price. --dry-run prints without touching DB. --strategy takes DB strategy name (e.g. finideas_ilts, not ILTS).
├── roll_leg.py               # CLI for atomic option leg rolls. Closes old leg + opens new leg in a single DB transaction. Pure _build_trades() validates both Trade objects before any DB write. --old-*/--new-* flag pairs. --dry-run. Calls store.record_roll().
├── seed_nuvama_positions.py  # One-time seed of Nuvama bond cost-basis. build_positions() pure (6 instruments). seed_positions() I/O wrapper. --write (required to commit), --overwrite, --db. Dry-run by default.
└── probe_nuvama_schema.py    # Diagnostic script (not production). Dumps all rmsHdg fields from live Holdings() response.

.claude/
├── skills/commit/SKILL.md    # NiftyShield commit format (disable-model-invocation: true — manual only)
└── agents/
    ├── code-reviewer.md      # Opus: checks Decimal, BrokerClient protocol, type hints, async correctness
    ├── test-runner.md        # Haiku: runs python -m pytest tests/unit/ and reports
    ├── greeks-analyst.md     # Sonnet: OptionChain model design, _extract_greeks_from_chain(), fixture analysis
    ├── roll-validator.md     # Opus: pre-roll position check, Trade model integrity, DB atomicity — hard deadline 2026-06-30
    └── options-strategist.md # Opus: delta-neutral sizing, IC/strangle design, risk module logic (src/risk/ scope)

docs/archive/
├── CODE_REVIEW_2026-04-04.md        # Full codebase code review from foundation sprint
└── daily_snapshot_old_2026-04-12.py # Pre-factory.py version of daily_snapshot script

tests/
├── unit/
│   ├── portfolio/
│   │   ├── __init__.py
│   │   ├── test_trade_models.py    # 20 tests: TradeAction enum, Trade valid/invalid construction, qty/price validators, frozen=True, Decimal precision
│   │   ├── test_trade_store.py     # 25 tests: record_trade CRUD, idempotency, get_trades filters + ordering, get_position (BUY-only, SELL-only, mixed, weighted avg, ignores SELL price, schema coexistence)
│   │   ├── test_seed_trades.py     # 13 tests: build_trades shape, strategy/leg/key correctness, BUY+SELL actions, idempotency (3×), EBBETF0431 weighted avg, NIFTY_JUN_PE short position
│   └── test_roll_leg.py        # 10 tests: _build_trades happy path (fields, notes, leg independence), validation errors (zero/negative qty, zero price)
│   └── mf/
│       ├── __init__.py       # Package marker
│       ├── test_models.py    # 25 tests: MFTransaction + MFNavSnapshot valid/invalid/edge cases
│       ├── test_store.py     # 33 tests: CRUD, upsert idempotency, date range queries, schema coexistence. get_holdings tests updated for MFHolding return type.
│       ├── test_nav_fetcher.py  # 20 tests: AMFI parse logic, fixture-driven, fully offline. Updated to correct AMFI codes.
│       ├── test_tracker.py   # 27 tests: pure P&L math + mocked store/fetcher orchestration
│       ├── test_seed.py      # 20 tests: seed transaction shape, verified AMFI code set, idempotency, Decimal precision, total_invested sum
│       ├── test_daily_snapshot_mf.py   # 12 tests: MF wire-up path — schema coexistence, full seed→snapshot→aggregate, empty holdings, nav failure
│       └── test_daily_snapshot_helpers.py  # 11 tests: _etf_current_value + _etf_cost_basis pure helpers. No sys.modules stubs needed — daily_snapshot.py has no I/O imports at module level.
└── instruments/
│   ├── __init__.py
│   └── test_lookup.py        # 27 tests: _score_query tiers, _best_score field selection, InstrumentLookup.search ranking/filters/min_score/edge cases
└── auth/
    ├── __init__.py
    ├── test_nuvama_login.py   # 16 tests: build_login_url, extract_request_id (full URL + bare token + whitespace), initialize_session (APIConnect args, parent dir creation, is_production flag), save_settings_path (write + upsert), login flow (missing creds, empty input, full flow). autouse clean_env fixture prevents dotenv leakage.
    ├── test_nuvama_verify.py  # 17 tests: parse_holdings (flat list, whitespace strip, multiple records, empty, invalid JSON, missing key), load_api_connect (missing creds, settings file missing, happy path), verify (true/false on valid/invalid response, config error, api exception, stdout count). autouse clean_env fixture.
    ├── test_dhan_login.py     # 13 tests: build_login_url, validate_token (strip/empty/whitespace), save_token (write/upsert/preserve), login flow (missing client_id, empty input, full flow, whitespace token). autouse clean_env fixture.
    └── test_dhan_verify.py    # 18 tests: _build_headers, load_dhan_credentials (happy/missing_id/missing_token/whitespace), fetch_profile (happy/401), fetch_holdings (list/empty/dict), parse_holdings (multiple/empty/missing/malformed), verify (success/missing_creds/401/stdout). autouse clean_env fixture.
└── fixtures/
    ├── responses/            # 7 JSON fixtures recorded from real APIs (LTP, option chain, Greeks, candles)
    └── amfi/
        └── nav_slice.txt     # Realistic AMFI flat file slice: 11 valid schemes with correct AMFI codes, N.A. line, malformed line
```

### What Does NOT Exist Yet

- `src/nuvama/CLAUDE.md` — module context file not yet written
- `src/models/` — shared Pydantic models (deferred; portfolio/ and mf/ models migrate here together — see PLANNER.md)
- `src/strategy/`, `src/execution/`, `src/backtest/`, `src/risk/`, `src/streaming/` — all empty
- `OptionChain` Pydantic model — not defined; `_fetch_greeks()` returns `{}` immediately

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

Architecture decisions, rationale, and deferred items: **[DECISIONS.md](DECISIONS.md)**
Instrument keys, AMFI codes, API quirks, auth tokens: **[REFERENCES.md](REFERENCES.md)**

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

Before writing any code: read `CONTEXT.md`, state `CONTEXT.md ✓`, confirm scope, state plan. See `CLAUDE.md` for full protocol.
- Architecture decisions or new modules: also read `DECISIONS.md`
- Instrument keys, market data, AMFI codes: also read `REFERENCES.md`
- Starting new feature work: also read `TODOS.md` + `PLANNER.md`
- Working in a `src/` module: that module's `CLAUDE.md` loads automatically

## Immediate TODOs

Open work and priority order have moved to **[TODOS.md](TODOS.md)**.
   - ~~**5.c**~~ — **DONE (2026-04-08)**: `src/client/upstox_live.py` created. `UpstoxLiveClient` wraps `UpstoxMarketClient` for `get_ltp` + `get_option_chain`. All blocked methods raise `NotImplementedError` with documented reasons. 14 tests in `tests/unit/test_upstox_live.py`. 279 total, all green.
   - ~~**5.d**~~ — **DONE (2026-04-08)**: `src/client/mock_client.py` created. Stateful `MockBrokerClient` — in-memory `_price_map`, `_orders`, `_positions`, `_margin_available` (Decimal), `_error_queue`. Setup API: `set_price`, `set_margin`, `simulate_error` (one-shot), `reset`. All 10 `BrokerClient` methods implemented; fixture loading graceful (WARNING + empty return on miss). `price*qty*0.1` NRML margin proxy. 38 tests in `tests/unit/test_mock_client.py`; all green.
   - ~~**5.e**~~ — **DONE (2026-04-08)**: `src/client/factory.py` created. `create_client(env)` is the sole composition root and the only `src/` importer of `UpstoxLiveClient` + `MockBrokerClient`. 10 tests in `tests/unit/test_factory.py`; all green.
   - ~~**5.f**~~ — **DONE (2026-04-08)**: `daily_snapshot.py` migrated from direct `UpstoxMarketClient` import to `create_client(os.getenv("UPSTOX_ENV", "prod"))`. `tracker.py` confirmed already using `from src.client.protocol import MarketDataProvider`. `UpstoxMarketClient` no longer imported by any consumer outside `src/client/`. No new tests — pure refactor. 327 tests total, all green.

6. **P&L visualization** — matplotlib script or React dashboard from snapshot time series. Deferred until several weeks of snapshot history exist and `PortfolioSummary` dataclass is extracted (TODO 1).

---

## Strategy Definitions

Strategy leg tables (instrument keys, entry prices, quantities, protected MF portfolio) are in **[REFERENCES.md](REFERENCES.md)**.

---

## Test Coverage

- **Total: 599 + 97 new nuvama tests = 696 tests** (54 pydantic-dependent skipped in sandbox, all pass in Mac venv)
- Run: `python -m pytest tests/unit/`
- Auth tests: `tests/unit/auth/` (64 tests — Nuvama login + verify, Dhan login + verify)
- MF tests: `tests/unit/mf/` (127 tests)
- Portfolio tests: `tests/unit/portfolio/` + `tests/unit/test_portfolio.py` (94+ tests — includes 4 record_roll store tests + 10 _build_trades script tests)
- Client tests: `tests/unit/test_client.py`, `test_protocol.py`, `test_exceptions.py`, `test_factory.py`, `test_mock_client.py`, `test_upstox_live.py` (90+ tests)
- Snapshot tests: `tests/unit/test_daily_snapshot_historical.py`, `test_daily_snapshot_helpers.py`, `test_notifications.py` (50+ tests)
- Dhan tests: `tests/unit/dhan/` (90 tests — models, reader, store, daily_snapshot integration)

---

## Session Log

Full session log has moved to **[TODOS.md](TODOS.md)**.
