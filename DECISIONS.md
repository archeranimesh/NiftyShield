# NiftyShield — Architecture Decisions

> Read this when: adding a new module, changing inter-module dependencies, or making a
> structural choice that affects more than one file. Not needed for routine feature work.

---

## Data Layer

**Shared SQLite connection factory (`src/db.py`):** Single `connect()` context manager used by both `PortfolioStore` and `MFStore`. WAL mode, `sqlite3.Row` factory, FK enforcement, auto commit/rollback. Any PRAGMA change applies everywhere from one place.

**MF holdings use a transaction ledger model:** `mf_transactions` table stores every SIP/redemption as a plain INSERT. Current holdings derived at query time via `SUM(units)`. Never mutate existing rows — new SIP = new INSERT. Enables full history and attribution.

**NAV data source: AMFI official flat file** (`https://www.amfiindia.com/spages/NAVAll.txt`). Semicolon-delimited, 6 fields: `code; ISIN growth; ISIN reinvest; name; NAV; date`. No auth, no rate limits. Preferred over `mfapi.in` (third-party dependency) and Upstox (no MF API exists).

**AMFI flat file parsing gate:** `parts[0].strip().isdigit()` — single check that skips category headers, the column header line, blank lines, and malformed rows without any regex.

**NAV snapshots stored per-scheme** in `mf_nav_snapshots`; portfolio-level aggregation happens at query time. Enables per-fund P&L attribution.

**MF data shares the existing SQLite DB** (`data/portfolio/portfolio.sqlite`) — one file, one WAL, one backup target.

**`amfi_code` typed as `str` (pattern `^\d+$`), not `int`** — used as identifier and join key, never as arithmetic. Matches AMFI flat file representation.

**Monetary values stored as TEXT in SQLite** — preserves exact `Decimal` precision through round-trips. Read back via `Decimal(row["col"])`. Applies to: `units`, `amount`, `nav`, `entry_price`, `ltp`, `close`, `underlying_price`, `price` in all tables.

**`get_holdings()` and `get_position()` aggregate in Python, not SQL** — same rationale: keeps exact `Decimal` arithmetic, avoids CAST rounding.

**`mf_transactions` unique constraint:** `(amfi_code, transaction_date, transaction_type)` — idempotent seed via `ON CONFLICT DO NOTHING`. Assumes one transaction per type per NAV date per scheme.

**`mf_nav_snapshots` conflict policy:** `ON CONFLICT(amfi_code, snapshot_date) DO UPDATE` — last write wins, consistent with `daily_snapshots`.

**`trades` UNIQUE constraint:** `(strategy_name, leg_role, trade_date, action)` — allows one BUY and one SELL for the same leg on the same date (same-day roll), prevents double-seeding.

**Paper trades stored in same SQLite DB as live trades but in separate tables with `paper_` prefix on strategy names (2026-04-25):** `paper_trades` and `paper_nav_snapshots` live in `portfolio.sqlite` alongside the live tables. Rationale: reuse of the existing `src/db.py` connection manager, `PaperStore` → `PaperTracker` → `daily_snapshot.py` wiring, and Telegram notification infrastructure with zero parallel infrastructure. The `paper_` prefix on `strategy_name` is the sole runtime guard against cross-contamination at query time. No foreign-key cross-references to live tables.

**`PaperPosition.avg_sell_price` tracks SELL opening trades separately from `avg_cost` (BUY avg):** Options writing opens a position via SELL, not BUY. Tracking both averages independently in `PaperPosition` keeps unrealized P&L semantically correct for both long (BUY-opened) and short (SELL-opened) positions without requiring a direction flag on the position itself.

**MF store tests use `tmp_path`** (file-based SQLite), not `:memory:` — `_connect()` opens and closes a fresh connection on every call, so `:memory:` would lose state between calls.

---

## Portfolio & Trade Model

**`Leg` vs `Trade` distinction:** `Leg` (in `ilts.py`, `finrakshak.py`) is a conceptual strategy role — instrument + direction + entry price as a definition. `Trade` (in the `trades` table) is a physical execution — what actually transacted, when, at what price. They coexist permanently: `Leg` defines shape; `Trade` drives cost-basis and qty.

**`apply_trade_positions()` bridges Leg and Trade at runtime:** patches Leg qty/entry_price from weighted avg trade data, appends trade-only legs (LIQUIDBEES) as EQUITY/CNC, drops zero-net-qty legs. Returns new Strategy without mutating original.

**Trade overlay internalized in `PortfolioTracker`:** `_get_overlaid_strategy()` / `_get_all_overlaid_strategies()` private helpers apply the overlay before returning. `compute_pnl`, `record_daily_snapshot`, `record_all_strategies` all use overlaid data — no caller manually applies it for these paths.

**Trade-only legs auto-persisted via `store.ensure_leg()`:** When `record_daily_snapshot` encounters a leg with `id is None` (LIQUIDBEES appended by overlay), it calls `ensure_leg(strategy_name, leg)` to upsert and obtain a DB id. Idempotent.

**`trades.strategy_name` must match `strategies.name` exactly:** Canonical names are `finideas_ilts` and `finrakshak`. Mismatch silently disables the overlay — `get_all_positions_for_strategy()` returns empty, no error raised.

**SELL price excluded from weighted average buy price:** Premium received, not capital deployed. `get_position()` only averages BUY prices.

**LIQUIDBEES tracked in `trades` not in strategy `Leg` definitions:** Not a Finideas strategy leg. `apply_trade_positions()` appends it as EQUITY/CNC at runtime so its mark-to-market is included in the ETF component.

**`seed_trades.py` separates `build_trades()` (pure) from `seed_trades()` (I/O):** mirrors `seed_mf_holdings.py` pattern. Tests call `build_trades()` directly with no DB. Dates marked `2026-01-15` are placeholders pending contract note verification.

---

## P&L & Reporting

**`PortfolioSummary` frozen dataclass** in `src/portfolio/models.py`. Carries all combined totals (`mf_value`, `etf_value`, `options_pnl`, `total_value`, `total_pnl`, `total_pnl_pct`) plus four day-delta fields (all `Decimal | None`). `_build_portfolio_summary()` in `daily_snapshot.py` owns all arithmetic.

**Combined portfolio P&L formula:** `total_value = MF current value + ETF mark-to-market + options net P&L`. ETF legs identified by `leg.asset_type == AssetType.EQUITY` (not string prefix).

**Two distinct P&L metrics:** (1) Inception P&L — current value minus total invested; (2) Day-change P&L — today vs previous snapshot via `get_prev_snapshots()` / `get_prev_nav_snapshots()` (MAX date < today, calendar-agnostic). Δday column omitted silently on first run.

**P&L quantization boundary:** `current_value` and `pnl_pct` quantized to 2 dp (ROUND_HALF_UP); `pnl` kept as exact difference so `sum(scheme.pnl) == total_pnl` without rounding drift.

**`PortfolioTracker.compute_pnl()` returns `Decimal`** via `StrategyPnL.total_pnl`. No bridging cast needed when combining with other Decimal values.

**MF snapshot is non-fatal in cron:** the MF block in `daily_snapshot.py` is wrapped in `try/except Exception`. AMFI unreachable at 3:45 PM does not abort the portfolio snapshot.

**AMFI NAV timing:** AMFI publishes after market close (7–9 PM IST). The 3:45 PM cron fetches T-1 NAV for MFs — this is expected and correct. Combined P&L shows mixed-timestamp data by design.

**`FinRakshak protection stats`:** `finrakshak_day_delta` isolated from combined `options_day_delta` in `_build_portfolio_summary`. `_format_protection_stats()` appends hedge verdict (✅/⚠️) to log output and Telegram header.

**Nuvama options: Intelligent EOD Snapshot pattern for cumulative realized P&L.** Nuvama's `NetPosition()` response returns `rlzPL` as a _daily_ realized figure — it resets each session. To get lifetime cumulative realized P&L, the daily snapshot stores each day's `rlzPL` per `trade_symbol` in `nuvama_options_snapshots`, and `get_cumulative_realized_pnl()` uses a single SQL `GROUP BY trade_symbol` query (AR-8, 2026-04-23) with the result mapped through `Decimal(row["cumulative"])` at the boundary to preserve Decimal precision. Flat positions (net_qty == 0) are intentionally included because their `rlzPL` still counts toward cumulative tracking. Alternative of fetching a running total from Nuvama directly is not available via the SDK.

**Nuvama intraday snapshots use DECIMAL column type (not TEXT).** The five-minute intraday table (`nuvama_intraday_snapshots`) stores `ltp`, `unrealized_pnl`, `realized_pnl_today` as `DECIMAL` and `nifty_spot` as `DECIMAL`. This intentionally deviates from the TEXT-for-Decimal rule — the read path in `get_intraday_extremes()` wraps every value in `Decimal(str(row[...]))` at the boundary, which absorbs any SQLite float representation. The deviation is acceptable here because intraday data is purely for graphing (not P&L accounting) and the boundary cast neutralises precision risk.

---

## Nuvama SDK Exit Handling

**`os._exit()` required in any script that initialises `APIConnect`.** The Nuvama SDK (`APIConnect.__init__`) launches a non-daemon background thread (Feed thread). `sys.exit()` blocks on non-daemon threads and hangs the process. `os._exit(exit_code)` terminates immediately. Applies to: `daily_snapshot.py`, `nuvama_login.py`, `nuvama_verify.py`, `nuvama_intraday_tracker.py`. Any new script that calls `load_api_connect()` or instantiates `APIConnect` directly must also terminate via `os._exit()`.

---

## Market Calendar

**Holiday data source: static YAML, updated annually.** `src/market_calendar/data/nse_{year}.yaml` — a list of `{date, name}` entries seeded from NSE's published equity holiday calendar. Stored under `src/` (not `data/`) because `data/` is gitignored to protect the live SQLite DB; the YAML is config and must be version-controlled. No live API query at cron time. Rationale: a network failure at 3:45 PM should not determine whether the snapshot runs. NSE's holiday list for the year is deterministic; there is no operational benefit from runtime resolution.

**`src/market_calendar/holidays.py` is the sole consumer of the YAML.** Three public functions: `load_holidays(year)` → `frozenset[date]`, `is_trading_day(d)` → `bool` (weekday AND not in holiday set), `prev_trading_day(d)` → `date` (walk backwards). Cache in module-level `_CACHE` dict to avoid re-parsing on repeat calls within the same process.

**Fail-open on missing YAML.** If `nse_{year}.yaml` does not exist (e.g. January 1st before the annual refresh), `is_trading_day()` logs a WARNING and returns `True`. Safer than blocking a valid trading day due to a missing file. The WARNING is surfaced in cron logs so the gap is visible.

**Data gap on holidays: no rows written, no backfill.** When a script skips due to a holiday, no `daily_snapshots`, `mf_nav_snapshots`, or `nuvama_options_snapshots` rows are written. Gaps are intentional and honest. `get_prev_snapshots()` uses `MAX(snapshot_date) < d` (calendar-agnostic) so day-delta P&L on the next trading day is correct with zero additional code.

**Annual maintenance ritual:** Each January, fetch the NSE equity holiday list for the new year, create `src/market_calendar/data/nse_{year}.yaml`, and commit. The refresh is manual; automating it adds a web-scraping dependency with no operational upside for a once-a-year task.

---

## daily_snapshot.py Design

**Deferred I/O imports:** Module-level imports are stdlib + `src.portfolio.models` only. All I/O-triggering imports (`dotenv`, `UpstoxMarketClient`, `PortfolioStore`, etc.) deferred inside `_async_main()`. Pure helpers importable in tests with zero side effects.

**Single `asyncio.run()` entry point:** entire live-mode logic runs inside `_async_main()`. Historical mode (`--date`) runs in `_historical_main()` — no async needed (DB only).

**`_format_combined_summary()` produces text; `_print_combined_summary()` wraps with print.** Both terminal and Telegram receive identical strings without double-computing or stdout capture.

**`PortfolioTracker.record_daily_snapshot` and `record_all_strategies` return computed P&L alongside counts (AR-11, 2026-04-23).** Both methods previously returned `int` / `dict[str, int]` (snapshot counts only). They now return `tuple[int, StrategyPnL | None]` and `tuple[dict[str, int], dict[str, StrategyPnL | None]]` respectively. The change eliminates the redundant `compute_pnl()` call in `daily_snapshot._async_main` — P&L is computed from the prices dict already fetched during snapshot recording. Any caller that unpacks the old single-value return (`count = await tracker.record_daily_snapshot(...)`) must be updated to `count, pnl = ...`. `compute_pnl()` is retained for ad-hoc single-strategy queries.

---

## Client Layer & BrokerClient Protocol

**BrokerClient protocol design (`src/client/protocol.py`):** Three narrow sub-protocols (ISP) — `MarketDataProvider` (tracker/signal), `OrderExecutor` (execution), `PortfolioReader` (monitoring). `BrokerClient` kept flat (not inheriting from sub-protocols) so its full method list is readable. Python structural typing — any class satisfying all 10 `BrokerClient` methods automatically satisfies all three sub-protocols. Stub type aliases (`X = Any`) with `# TODO` comments stand in for Pydantic models not yet in `src/models/`. `from __future__ import annotations` means zero import-time dependency on `src/models/`.

**Composition root pattern (`src/client/factory.py`):** `create_client(env)` is the only `src/` function that imports `UpstoxLiveClient` or `MockBrokerClient` directly. All other modules receive a `BrokerClient` via constructor injection — they import only `src.client.protocol.BrokerClient`. `VALID_ENVS: Final = ("prod", "sandbox", "test")`.

**`UpstoxLiveClient` delegation pattern:** holds `self._market: UpstoxMarketClient` (Analytics Token). `get_ltp` and `get_option_chain` are pure async pass-throughs to `_market`. No inheritance — protocol conformance is structural.

**Two-token constraint:** Analytics Token (long-lived, `UPSTOX_ANALYTICS_TOKEN`) powers market data. Daily OAuth token (`UPSTOX_ACCESS_TOKEN`) required for positions, holdings, margins. `UpstoxLiveClient` currently holds only the Analytics Token; portfolio-read methods raise `NotImplementedError`.

**`NotImplementedError` policy for blocked methods:** Three categories: (1) Order execution — `_raise_order_blocked()` centralises the message; (2) Portfolio read — Daily OAuth token required; (3) Data constraints — historical candles (not wired), expired contracts (paid subscription). Callers see a clear error rather than silent wrong behaviour.

**`MockBrokerClient` design:** Stateful offline broker client. Margin tracked as `Decimal`; order notional deducts `price * quantity * 0.1` as NRML proxy. `simulate_error(method, exc)` is one-shot: fires once on next call, then removed. `reset()` clears orders/positions/error queue, restores default margin; preserves `_price_map` and `fixtures_dir`. Missing fixtures log WARNING, return `None`/`[]`/`{}` — never raises.

**`upstox_market.py` is a pre-protocol legacy module:** Built before the BrokerClient abstraction. Sync `requests` client. Violates DI rule. Wrapped inside `UpstoxLiveClient` — no consumer outside `src/client/` imports it. Do not add new dependents on it directly.

**Error hierarchy (`src/client/exceptions.py`):** Full tree rooted at `BrokerError`: `AuthenticationError`, `RateLimitError`, `DataFetchError` → `LTPFetchError`, `OrderRejectedError` → `InsufficientMarginError`, `InstrumentNotFoundError`. `get_ohlc_sync` and `get_option_chain_sync` raise `DataFetchError` rather than returning empty dicts silently.

---

## Notifications

**Telegram notifier is optional and non-fatal:** `build_notifier()` returns `None` when env vars absent. `send()` catches all `Exception` broadly, returns `False` with WARNING log. The cron never aborts due to Telegram failure.

**Message format:** HTML parse_mode, `<pre>` block for monospace alignment on mobile.

---

## Models & Types

**`frozen=True` for computed types:** `SchemePnL`, `PortfolioPnL`, `StrategyPnL`, `LegPnL`, `PortfolioSummary`, `MFNavSnapshot`, `MFTransaction`, `Trade` — all immutable.

**Enum compatibility:** `Direction`, `ProductType`, `AssetType` use `(str, Enum)` — not `StrEnum` (3.11+ only; project targets 3.10+).

**`nav_fetcher` injected as `NavFetcherFn = Callable[[set[str]], dict[str, Decimal]]`** — tests pass a lambda, production gets the real AMFI fetcher. Missing NAV codes skipped with WARNING, not raised.

**`MFHolding` defined in `src/mf/models.py`**, not `tracker.py` — avoids the circular import that would result from `store.py` importing a type defined in `tracker.py`.

**`src/models/` migration complete (2026-04-16):** `portfolio/models.py` and `mf/models.py` moved to `src/models/portfolio.py` and `src/models/mf.py`. All consumers in `src/`, `scripts/`, and `tests/` updated. Old files deleted. `src/models/__init__.py` re-exports everything for convenience. Canonical import paths: `from src.models.portfolio import Leg` and `from src.models.mf import MFTransaction`. `src/strategy/`, `src/execution/`, `src/backtest/` can now import shared types without coupling through `src/portfolio/`.

---

## Dhan Portfolio Integration

**Scope: read-only equity and bond holdings.** `GET /v2/holdings` for demat positions; `POST /v2/marketfeed/ltp` for current prices. No F&O, no intraday.

**ISIN → Upstox key derivation:** For NSE equities, Upstox instrument key = `NSE_EQ|{ISIN}`. Derived directly from the Dhan `isin` field — no lookup file, no config.

**Classification is config-driven, not automatic.** Dhan API returns all demat holdings as exchange-traded securities with no bond/equity distinction. `_BOND_SYMBOLS: frozenset[str]` in `reader.py` maps known liquid/bond ETF symbols (LIQUIDCASE, LIQUIDBEES, LIQUIDIETF, CASHIETF, LIQUIDADD, LIQUIDSHRI) to `"BOND"`. Everything else is `"EQUITY"`. Adding a new bond instrument requires one line in this frozenset.

**Double-count prevention:** Dhan `GET /v2/holdings` returns all demat holdings, including instruments already tracked by strategies (EBBETF0431, LIQUIDBEES). `build_dhan_holdings()` accepts an `exclude_isins: set[str]` parameter — `_async_main` extracts ISINs from `NSE_EQ|{ISIN}` strategy leg keys before calling. Filtered holdings are never persisted or included in totals.

**Non-fatal design:** Dhan fetch block in `_async_main` is wrapped in `try/except`. `ValueError` (missing credentials) silently skips with an info print; network errors log WARNING. If Dhan is unavailable, `dhan_summary=None` is passed down — all Dhan fields in `PortfolioSummary` default to `Decimal("0")` and `dhan_available=False`. Formatter shows `[unavailable]` in Bonds section and a NOTE in Total section.

**24h token expiry by design.** Dhan access tokens expire daily. Users refresh via `python -m src.auth.dhan_login`. No auto-refresh implemented.

**`PortfolioSummary` Dhan fields default to zero.** All nine new Dhan fields (`dhan_equity_value`, `dhan_equity_basis`, `dhan_equity_pnl`, `dhan_equity_pnl_pct`, `dhan_equity_day_delta`, and bond equivalents + `dhan_available: bool`) have safe defaults — all existing tests and callers are unaffected.

**SQLite table:** `dhan_holdings_snapshots` shares `data/portfolio/portfolio.sqlite`. `UNIQUE(isin, snapshot_date)` with upsert semantics — re-runs on same day are idempotent, last write wins.

**Day-change delta computation:** `DhanStore.get_prev_snapshot()` uses `MAX(snapshot_date) < today` — calendar-agnostic, handles weekends/holidays without explicit market-calendar dependency.

**LTP source: Upstox batch fetch, not Dhan market API.** Dhan's `POST /v2/marketfeed/ltp` requires the paid Data API (₹499/month) and returns 401 on free tier. Instead, `_async_main` pre-fetches Dhan holdings before the Upstox LTP batch, derives Upstox keys via `NSE_EQ|{ISIN}` using `upstox_keys_for_holdings()`, adds them to `all_keys`, then calls `enrich_with_upstox_prices()` after the single Upstox batch LTP call. Single batch, zero extra API cost. `enrich_with_ltp()` (Dhan API path) is retained in `reader.py` for completeness but not used in production.

---

## Nuvama Integration

**Scope: read-only.** Bonds/holdings for margin tracking + EOD positions. Order execution NOT wired for Nuvama.

**Session persistence:** `APIConnect` persists session token in `NUVAMA_SETTINGS_FILE` (path in `.env`). No daily re-auth after first login via `python -m src.auth.nuvama_login`. Unlike Upstox daily OAuth, session survives until explicitly invalidated.

**`parse_holdings()` is a pure function** — maps `eq.data.rmsHdg` response to a flat list. Independently testable without a live session.

**`src/nuvama/` module architecture (added 2026-04-15):**

**Cost basis stored in `nuvama_positions` table, not derived from API.** Nuvama's `Holdings()` response has no `avgPrice` field — current value only (`totalVal = ltp × qty`). Cost basis seeded once via `scripts/seed_nuvama_positions.py` into `nuvama_positions(isin TEXT PRIMARY KEY, avg_price TEXT, qty INT, label TEXT)` in `portfolio.sqlite`. `reader.py` joins positions at parse time. New purchases require re-running the seed or a future `record_nuvama_trade.py` CLI.

**Day-change delta derived from `chgP` field.** The API returns `chgP` as a string percentage (e.g. `'-1.28'`). `day_delta = current_value × Decimal(chgP) / 100`. This avoids a prior-snapshot dependency and is accurate enough for bonds (low intraday volatility). Snapshots are still stored in `nuvama_holdings_snapshots` for historical tracking.

**All Nuvama holdings classified as BOND.** Nuvama account holds only debt instruments. `asTyp` field is always `'EQUITY'` in the API (Nuvama makes no bond/equity distinction in their response schema). Classification is not API-driven. `_EXCLUDE_ISINS: frozenset[str]` in `reader.py` excludes instruments already tracked elsewhere (initially: LIQUIDBEES `INF732E01037`).

**LTP sourced directly from Holdings() response — no Upstox enrichment.** Unlike Dhan (which requires a separate LTP call), Nuvama's Holdings() includes current LTP inline. No secondary API call needed.

**`nuvama_holdings_snapshots` table.** `UNIQUE(isin, snapshot_date)` with upsert — same pattern as `dhan_holdings_snapshots`. Stores `isin, snapshot_date, qty, ltp, current_value` for historical trend tracking. Shares `portfolio.sqlite`.

**Non-fatal design.** Nuvama fetch block in `_async_main` is wrapped in `try/except`. `ValueError` (missing credentials/settings) skips with info print; network/API errors log WARNING. `nuvama_summary=None` passed down — `PortfolioSummary.nuvama_*` fields default to zero, `nuvama_available=False`. Formatter shows `[unavailable]` in Bonds section.

---

## Dhan Integration

**Two API tiers:** Trading APIs (free — portfolio, positions, funds, orders) vs Data APIs (₹499/month or ₹4,788/year — option chain, historical data, expired options, market depth). Current integration uses free tier only.

**Scope: read-only.** Holdings, positions, fund limits for after-market P&L review. No order execution wired for Dhan.

**Raw `requests` client (no `dhanhq` SDK):** All Dhan APIs are plain REST with `access-token` header auth. The `dhanhq` package is a thin wrapper that adds no value for read-only calls. Raw requests give us full control over request/response shapes — essential for building Pydantic models for the backtesting engine later. Migration cost to SDK is near-zero if ever needed.

**Manual 24-hour token from `web.dhan.co`:** Token generation requires Application Name (e.g. `NiftyShield`), optional Postback URL, Token validity (default 24h). No OAuth flow — simpler than both Upstox and Nuvama.

**Data Source for Backtesting Engine — SUPERSEDED (2026-04-27):** See "Backtest Data Source Decision (2026-04-27)" section below. DhanHQ was the original choice; it has been rejected after evaluation. NSE F&O Bhavcopy (free, from exchange) is now the programmatic data source for options OHLCV backtesting.

**Local Storage Architecture for Historical Chains — REVISED (2026-04-27):** TimescaleDB was originally selected to handle the volume of DhanHQ's 1-minute data (~500M rows). DhanHQ has been rejected; the NSE F&O Bhavcopy pipeline produces EOD data (~4M rows for 8 years across all NIFTY strikes) — well within Parquet + SQLite capacity. TimescaleDB is **deferred indefinitely** — revisit only if a future paid minute-level data source is adopted. All new backtest storage uses Parquet (`data/offline/`) + existing `portfolio.sqlite`.

**Parquet partition scheme designed for DuckDB glob-query compatibility (2026-04-27):** All Parquet outputs under `data/offline/` use the partition path `{year}/{month}/` (EOD data) or `{year}/{month}/{day}/` (intraday data). This is intentional: DuckDB can glob-query the full dataset without any schema migration via `read_parquet('data/offline/<series>/**/*.parquet')`. Do not install DuckDB yet — Parquet + pyarrow/pandas is sufficient for Phase 1 volumes. If complex multi-file range queries become slow in Phase 2 (e.g., querying 16M-row intraday chain sets), introduce DuckDB as a zero-migration query layer on top of the existing files. The partition scheme is the only forward-compatibility requirement.

**Task 1.10 chain snapshot storage revised from TimescaleDB to Parquet (2026-04-27):** Task 1.10 in BACKTEST_PLAN.md originally specified a Timescale hypertable `option_chain_snapshots` with a 7-day chunk interval. Since TimescaleDB is deferred, the storage target is Parquet at `data/offline/chain_snapshots/{year}/{month}/upstox_{date}.parquet`. Schema is identical to the original hypertable spec: `snapshot_ts, underlying, expiry_date, strike, option_type, spot, ltp, bid, ask, oi, volume, iv, delta, gamma, theta, vega`. One file per EOD capture (3:30 PM cron). Query pattern — time-range + strike filter — is columnar-friendly and maps naturally to Parquet partition scans.

**Intraday live option chain snapshots at 5-min cadence (proposed task 1.10a, 2026-04-27):** In addition to the EOD chain snapshot (task 1.10), a 5-min intraday chain snapshot cron (`*/5 9-15 * * 1-5`) accumulates real bid/ask and Greeks throughout the trading day. Storage: `data/offline/chain_snapshots_5min/{year}/{month}/{day}/upstox_{timestamp}.parquet`. Volume: ~67K rows/day, ~16M rows/year, ~2–3 GB/year compressed. Rationale: (1) real intraday bid/ask spread distribution is the empirical input for the slippage model in task 1.4 — without it, slippage parameters are guesses; (2) intraday delta drift from real Upstox Greeks against BS-reconstructed Greeks quantifies the structural bias in task 1.6a; (3) cannot be back-filled — capture must start in Phase 1 to have 6+ months of data by the task 1.11 variance check. Operational cost: 3 API calls per 5-min interval (one per expiry), 225 calls/day, well within Upstox Analytics Token rate limits.

---

## Development Tooling

**`__init__.py` required in every package directory:** `scripts/` was missing `__init__.py`, which caused `codebase-memory-mcp` to silently skip the entire directory — all 12 functions in `daily_snapshot.py` were invisible to the graph despite the repo being indexed. Adding `scripts/__init__.py` brought the node count from 1048 → 1684 and edge count from 3544 → 6077 in one re-index. Rule: every new `src/<module>/`, `scripts/`, and test subdirectory must include `__init__.py`. Re-index after adding any new package.

**codebase-memory-mcp as primary code understanding tool:** Use `search_graph`, `get_code_snippet`, and `trace_path` before opening source files with `Read`. The graph resolves function signatures, call chains, and callers/callees without consuming tokens on file content. `Read` is the fallback for markdown, config, and fixtures not in the graph. This is especially important for large files like `daily_snapshot.py` (~600 lines) where only one or two functions are relevant to any given task.

**git log as primary intent discovery tool:** Every commit in this repo follows the structured format in `.claude/skills/commit/SKILL.md` with an explicit `Why:` line. Before inferring intent from code, run `git log --oneline -15 <file>` to see the change sequence, then `git show <sha>` for the diff and rationale. This is faster and more accurate than reverse-engineering intent from code alone.

---

## OptionChain Model

**Source-agnostic `OptionChain` Pydantic model (decided 2026-04-24, implemented 2026-04-25):** `OptionLeg`, `OptionChainStrike`, `OptionChain` defined in `src/models/options.py`. Field names are source-agnostic (`delta`, not `greeks_delta`). Translation from Upstox/Dhan response shapes happens in each client's parser, not in the model. `OptionLeg` carries no `instrument_key` — lookup is by strike price + asset_type (both on the `Leg` model), so the OptionChain model stays vendor-neutral.

**Upstox-first for live chain, Dhan from Phase 1.10:** Upstox Analytics Token is already active — zero marginal cost. Dhan Data API (₹400/month) is not yet subscribed. When it is activated for the backtesting engine, Phase 1.10 switches live chain to Dhan so that backtest Greeks (historical Dhan data) and live Greeks come from the same vendor. Without consistent source, IV percentile rules used in strategy entry logic would have systematic bias between backtest and live.

**Strike lookup: `Decimal(str(leg.strike))` dict key.** `OptionChain.strikes` is keyed by `Decimal`. Nifty strikes are always integers. `Decimal("22250.0") == Decimal("22250")` is True in Python (value equality governs dict lookup), so float-origin strikes round-trip correctly.

**`_parse_option_leg` coerces null/non-numeric Greeks to `Decimal("0")` with WARNING.** Best-effort contract — a bad Greek field never aborts the snapshot.

**`get_option_chain_sync` pre-existing return-type bug:** Returns `resp.json().get("data", {})` — the data field is a list, not a dict; default `{}` is wrong; return annotation `dict[str, Any]` is wrong. Deferred fix — absorb in `parse_upstox_option_chain` by accepting `list[dict]`. Do not fix the bug in this task.

---

## Strategy Decisions

**2026-04-25 — CSP v1 underlying switched from NiftyBees options to Nifty 50 index options.**
Rationale: NiftyBees options have insufficient liquidity (OI typically < 1,000 on monthlies,
bid/ask spreads > 5% of mid) to trade with confidence or backtest reliably. NiftyBees ETF
tracking error vs Nifty 50 is ≤0.02% annually, making Nifty index options a near-perfect
proxy for premium exposure. The NiftyBees holding is retained as pledged collateral; only the
option leg is switched. Reviewed 2026-04-25 with strategy-stress-test pass; no margin concern
given the ₹1.2 cr+ collateral pool (₹75L MF + ₹30L bonds + ₹15.5L NiftyBees ETF). Rules
R1–R7 also revised in the same review session — see `docs/strategies/csp_nifty_v1.md`.

**2026-04-26 — NiftyShield Integrated Strategy: CSP income + layered MF protection.**
Design decision: integrate the CSP income engine (`csp_nifty_v1.md`) with protective
put spreads (4 lots, 8–20% OTM) and quarterly tail puts (2 lots, ~30% OTM, 5-delta)
into a single tracked strategy (`paper_niftyshield_v1`). Rationale: FinRakshak covers
~15% of the ₹80L+ MF portfolio (1 lot, ₹15.6L notional). The remaining ~85% is
unhedged against >8% corrections. CSP income subsidises ~20–30% of the protection
cost; the remainder is an explicit 3–5% annual insurance budget. FinRakshak is NOT
counted in NiftyShield's hedge ratio — treated as independent and managed by Finideas.

**2026-04-26 — Static beta 1.25 for hedge ratio (initial; switch to rolling planned).**
The MF portfolio's weighted-average beta to Nifty is estimated at ~1.25 (mid/small
cap heavy). Nifty-equivalent exposure: ₹80L × 1.25 = ₹100L. Put spread lot count
(4 lots) sized to cover ~65% of remaining unhedged exposure. Static beta avoids
complexity while NAV history is short (<1 month clean data post-DB-wipe). Switch to
rolling 60-day beta once 12+ months of `mf_nav_snapshots` exist and the delta from
static exceeds 0.1.

**2026-04-26 — Two-tier backtest methodology for integrated strategy.**
Tier 1 (CSP leg): real Dhan expired options data — same as standalone CSP backtest.
Tier 2 (protective legs): Black-Scholes synthetic pricing with fixed skew markup
(+2% IV per 5% OTM, initial). Rationale: Dhan `rollingoption` coverage (ATM±3 to
ATM±10) does not extend to 8–30% OTM strikes. Synthetic pricing has known optimistic
biases (underprices deep OTM puts, overestimates crisis fills). These biases are
acknowledged and documented in the strategy spec. Paper-trading phase with real Dhan
live chain prices (`/v2/optionchain` — full strike range) provides the true
validation. Variance threshold for protective legs widened to |Z| ≤ 2.0 (vs 1.5 for
CSP) to accommodate the structural pricing error.

**2026-04-25 — NiftyBees collateral modelled as a `long_niftybees` leg in paper P&L.**
The CSP strategy's true economics include both the short put premium and the mark-to-market
of the pledged NiftyBees ETF collateral. Modelling only the option leg understates both the
return (ETF appreciates in uptrends) and the drawdown (ETF declines alongside a falling put).
Decision: record a BUY of NiftyBees equivalent to 1 Nifty lot as `leg_role=long_niftybees`
in `paper_csp_nifty_v1` at strategy inception. Qty formula: `floor(lot_size × nifty_spot /
niftybees_ltp)`. Reset annually (January, post-expiry): SELL old qty at current LTP to
realise P&L, BUY new qty at recomputed size. `PaperTracker.compute_pnl` requires zero changes
— it is instrument-key agnostic and batches all open legs into a single LTP fetch.
Instrument key: `NSE_EQ|INF204KB14I2`. This decision carries forward to Phase 1 backtest:
the backtest engine must include the NiftyBees collateral leg in all CSP strategy P&L
calculations. See `docs/strategies/csp_nifty_v1.md` for the exact `record_paper_trade.py`
command and annual reset procedure.

**2026-05-01 — Donchian strategy: signal-in-only architecture (council ruling).**
Source: `docs/council/2026-05-01_donchian-roll-mechanics.md`. Always-in architecture rejected.
When the ATR trailing stop fires, close the spread and go flat — do not open a new spread
until the next fresh Donchian channel breakout fires. Cost analysis is unambiguous: a
mid-contract roll (4 legs on NSE, no native multi-leg order type) incurs ₹1,100–1,900 in
slippage + brokerage + STT per event — 28–76% of a single cycle's gross premium at 20 DTE.
Additionally, holding a spread during consolidation periods bleeds ₹800–2,160/lot per
inter-signal period in uncompensated theta. The only "roll" permitted is signal-driven:
when an opposite-direction breakout fires, close the current spread and immediately enter the
new direction at fresh 30–45 DTE timing. Three exit triggers in priority order: (1) ATR
trailing stop → flat; (2) ≥50% max profit captured AND ≤21 DTE → close; (3) opposite
breakout → close and enter new direction. Confidence: High.

**2026-05-01 — Donchian strategy: uniform credit spreads; VIX regime switching deferred (council ruling).**
Source: `docs/council/2026-05-01_donchian-roll-mechanics.md`. Credit/debit VIX regime
switching removed from the Tier 2 backtest scope. Sample size argument is decisive: only
8–12 low-VIX debit trades expected over 5 years — no performance metric has a meaningful
confidence interval at that count. Additional disqualifiers: VIX boundary noise (~1 point
daily std dev) affects ~20–30% of entry days around any fixed threshold; layering a vol-regime
decision on a directional signal confounds attribution (can't isolate which edge is working).
Use **credit spreads uniformly** for both bullish and bearish signals during all backtest and
paper-trade phases. Post-validation contingency (if directional edge confirmed): regime
switching may be added if it improves Sharpe by > 0.15. If implemented, mandatory hysteresis:
enter credit regime at VIX > 19, enter debit regime at VIX < 14, hold previous state in the
14–19 dead zone. Confidence: High.

**2026-05-01 — Donchian strategy: ATR-proportional spread width; fixed 200 points rejected (council ruling).**
Source: `docs/council/2026-05-01_donchian-roll-mechanics.md`. Fixed 200-point spread
width creates a regime-dependent strategy that fails in high-volatility environments —
exactly where larger trends and more signal opportunities arise. At ATR 500, a 200-point
spread is breached by a single average adverse day's move, producing risk:reward > 1:6.
Mandated formula: `spread_width = min(round_to_50(k × ATR_40d), 500)` with k = 0.8
(walk-forward sweep [0.6, 0.7, 0.8, 0.9, 1.0]), floor 150 points (minimum 3 strikes for
meaningful premium), cap 500 points (NSE monthly OI thins beyond ±500 from ATM). This
maintains ~10% breach probability across all vol regimes. `k` is the 4th optimisable
parameter (added to the sweep table in `docs/plan/SWING_STRATEGY_RESEARCH.md`). Position
sizing with variable width: `lots = max(1, floor(₹7,500 / (spread_width × 75)))`. At 300pt
width (ATR ~375), 1 lot = ₹22,500 max loss — accept 1-lot minimum in paper phase; track
% of capital at risk per trade and flag any > 2%. Lot size = 75 (post-Nov 2024). Confidence: High.
Noted, deferred: ATR-based short strike selection (spot ± 1.0×ATR) instead of delta-based,
to eliminate model dependency on the IV surface. First candidate for post-validation testing.

**2026-05-01 — ORB strategy: volatility filter — ATR primary + VIX-IVP 90th-percentile structural exclusion (council ruling).**
Source: `docs/council/2026-05-01_orb-volatility-filter-design.md`. ATR (14-day) is the
theoretically correct primary filter: OR width / ATR directly measures compression relative
to recent realised price action. VIX is added as a **structural binary exclusion** (not a
swept parameter): exclude entry days where India VIX IVP (63-day trailing rank) ≥ 90th
percentile. Rationale: on pre-event consolidation days (e.g., day before RBI MPC at 10:00
AM), realised vol is low (ATR qualifies), but VIX is elevated (forward-looking pricing of
the announcement). On these days the ORB hypothesis is structurally degraded — the OR
compression represents *waiting*, not *indecision resolving into conviction*. The 90th
percentile framing is self-calibrating (adapts to the prevailing vol regime) and is not
subject to the fixed-threshold boundary noise rejected in the Donchian ruling (~5 affected
days/year vs. 20–30% for a fixed VIX level). VIX exclusion is a configurable flag
(`vix_exclusion_enabled: bool = True`, `vix_ivp_threshold: float = 0.90`,
`vix_lookback_days: int = 63`). **Ablation is mandatory**: the backtest must report Sharpe
with and without the VIX exclusion. If the delta is < 0.1 Sharpe, the flag is set to
`False` and the filter is dropped entirely — simpler architecture wins. Confidence: High.

**2026-05-01 — ORB strategy: event day treatment — structural calendar exclusion mandatory (council ruling).**
Source: `docs/council/2026-05-01_orb-volatility-filter-design.md`. Pre-scheduled macro
event dates are a structural exclusion from the ORB signal universe, conceptually identical
to the existing Thursday expiry exclusion. On RBI MPC announcement day (10:00 AM IST),
Union Budget day (11:00 AM IST), and FOMC+1 IST day (next NSE session after US
announcement), the ORB hypothesis is structurally inapplicable — the opening range
represents pre-announcement positioning, not overnight information resolution into
directional conviction. Pre-published calendars do not introduce look-ahead bias: RBI MPC
dates are published 12+ months ahead, Budget and FOMC dates are known months in advance.
Exclusion list: (1) RBI MPC announcement day — ~6/year; (2) Union Budget day — 1/year;
(3) FOMC+1 IST trading day — ~8/year; (4) Weekly expiry Thursday — ~52/year (already in
spec). Total: ~67 structural exclusions/year. **Surprise events (unscheduled geopolitical
shocks, flash crashes) are NOT excluded** — they belong to the true tail-risk distribution.
Post-event days (day after RBI/Budget) remain in-universe — these are the strategy's best
setup days. Backtest must report count and hypothetical P&L of excluded-day signals that
would have fired but were not taken. Calendar lives in `src/market_calendar/`; method:
`is_event_exclusion_date(date) -> tuple[bool, str | None]`. Confidence: High.

**2026-05-01 — ORB strategy: near-expiry contract selection — DTE ≤ 2 → skip to next weekly (council ruling).**
Source: `docs/council/2026-05-01_orb-volatility-filter-design.md`. Minimum DTE for any
new spread entry is 3. When a signal fires on a day where the nearest weekly expiry is
≤ 2 DTE away, skip to the following weekly expiry (+7 days). Day-of-week mapping:
Monday (3 DTE) → use current Thursday ✓; Tuesday (2 DTE) → skip to next Thursday (9 DTE);
Wednesday (1 DTE) → skip to next Thursday (8 DTE); Thursday → excluded (expiry day);
Friday (6 DTE) → use next Thursday ✓. Constraint is **backtest fidelity, not live
liquidity**: Nifty weekly options at 2 DTE are highly liquid (ATM±5 bid-ask 1–3 pts,
OI 5–20 lakh). The constraint is that 15-min discrete-bar backtesting cannot model 2-DTE
gamma path-dependency accurately — a 100-point intraday Nifty move changes delta by 0.40
at 2 DTE (gamma ~0.004/pt), and intra-bar spike → recovery creates ~70% P&L underestimation
in the backtest vs. the true path-dependent loss. At 3+ DTE the error drops to 25–35%
(acceptable for research-grade Phase 1 validation). Implementation stub: `select_expiry()`
in `src/instruments/`. Confidence: High.
Noted, deferred: ORB same-day-close architecture (hard exit at 15:15) means profit is
~95% delta-driven, not theta-driven. This raises whether debit spreads (profit scales
with directional move, no cap until spread width) are superior to credit spreads (profit
capped at premium collected, holding period mismatch) for this strategy. Test credit vs.
debit P&L on the same signals in Phase 1 walk-forward; if debit shows > 0.15 Sharpe
improvement, a separate council is warranted.

**2026-05-02 — 3-track Nifty long instrument comparison: Deep ITM Call selected for Track C (council ruling).**
Source: `docs/council/2026-05-02_nifty-long-instrument-comparison-protection.md`. Track C base instrument is a single-leg Deep ITM Call (delta ≈ 0.90, strike 2000–2500 below spot, monthly expiry). Synthetic long (ATM call + ATM put) rejected: adding a CSP overlay creates double short-put exposure (ATM embedded + CSP OTM), violating risk segregation and expanding downside convexity beyond the max drawdown tolerance. Near-ATM ITM call (delta ~0.70) rejected: higher theta, lower delta fidelity, increased vega/gamma diverge from the true "long Nifty" comparator role. Deep ITM call: defined max loss = premium paid, minimal extrinsic value, overlay compatibility — CSP and protective puts sit cleanly on top with no unintended replication. Monthly roll at expiry; select lowest strike with delta ≈ 0.90 at entry; treat option premium paid as "capital at risk" for normalization. Confidence: High.

**2026-05-02 — 3-track overlay interaction matrix: dangerous combos must be programmatically blocked (council ruling).**
Source: `docs/council/2026-05-02_nifty-long-instrument-comparison-protection.md`. Mandatory block list: (1) Track B (Futures) + Covered Call → synthetic short put (unlimited downside, mission-violating); (2) Track B (Futures) + CSP → double short-put exposure (amplified tail risk in drawdowns). Noted redundancies (not blocked, but auto-converted for reporting simplicity): Track B + Protective Put ≡ long call at higher strike (enter as spread directly); Track C + Protective Put ≡ bull call spread. Implementation requirement: the paper-trade recording layer or reporting layer must detect when net Greeks or position equivalents create unintentional mission-violating structures and warn/block before committing the record. Confidence: High.

**2026-05-02 — 3-track additional protection structures: collars and put spreads approved; ratio spreads rejected (council ruling).**
Source: `docs/council/2026-05-02_nifty-long-instrument-comparison-protection.md`. Approved for backtesting: (a) **Collars** (buy OTM put 8–10% below spot, sell OTM call 3–5% above spot, same expiry) — capital-efficient, align with protection-first mission, exploit Nifty's negative skew (OTM puts structurally more expensive than equidistant OTM calls); (b) **Vertical put spreads** (buy higher-strike put, sell lower-strike put) — cheaper than pure protective put, capped insurance at lower carry cost. Rejected: **ratio spreads / backspreads** — Nifty's negative skew means the second short put creates catastrophic tail risk exactly when it is least wanted (crashes), directly violating "protect before you earn" (Mission Principle I). Rejected: **jade lizards, iron condors, strangles** — introduce undefined downside or are capital-inefficient at 1-lot retail scale with Nifty bid/ask structure. Noted, deferred: ratio spreads retained as an academic tail-risk experiment only (not paper-traded, not allocated capital). Confidence: High.

**2026-05-02 — 3-track daily P&L reporting: NEE normalization + component attribution + minimum Greek set (council ruling).**
Source: `docs/council/2026-05-02_nifty-long-instrument-comparison-protection.md`. (1) **Component attribution mandatory**: report base P&L and each overlay P&L separately per track, plus net combined — reveals whether the overlay hedged a loss or was dead weight. (2) **Notional Equivalent Exposure (NEE)** normalization: all tracks sized to 1 Nifty lot equivalent (~₹15.5–16L). Track A = cash deployed; Track B = notional value (not margin alone), with "surplus" capital in liquid funds tracked separately; Track C = premium paid + overlay margin. (3) **Daily Greek set**: Delta (directional equivalence — alert if Track C drifts below 0.80 as expiry nears), Theta (true carry cost of overlays), Vega (IV sensitivity). Gamma optional but advisable for options-heavy overlay combos. (4) **Metrics per track**: absolute and % P&L, run/max drawdown in absolute and % of NEE, Return on Notional (RoN), tracking error (delta drift) between tracks over time, cumulative premium paid/received per overlay. Confidence: High.

**2026-05-02 — 3-track paper-trade namespaces: paper_track_a / _b / _c with overlay legs recorded independently (council ruling).**
Source: `docs/council/2026-05-02_nifty-long-instrument-comparison-protection.md`. All three tracks recorded via existing `record_paper_trade.py` and `PaperTracker` infrastructure. Strategy name convention: `paper_track_a` (NiftyBees ETF base), `paper_track_b` (Nifty Futures base), `paper_track_c` (Deep ITM Call base). Each overlay is a distinct leg within the track's strategy namespace — base and overlay legs are aggregable via `PaperTracker.compute_pnl()` while remaining individually queryable for attribution. No new paper trading infrastructure required. Spec document required (task 0.4b) before paper trading begins (task 0.6b). Confidence: High.

**2026-05-02 — CSP entry delta: 22-delta adopted as default for Nifty 50 monthly puts; 25-delta superseded (council ruling).**
Source: `docs/council/2026-05-02_csp-entry-delta-v2.md`. Chairman synthesis (GPT-4.1, Grok-4-fast, DeepSeek-R1). Analytical optimum for the 21-day hold / −0.45 delta-stop / 50% profit-target system is ~22-delta: captures ~85% of 25-delta credit, approximately halves stop-out frequency, and produces the highest Sharpe (~1.4 vs ~1.1–1.3 at 25-delta) in skew-adjusted Black-Scholes modelling of the Nifty vol surface. 20-delta further reduces tail risk but costs meaningful EV via thinner premium and wider relative slippage; 25-delta yields best fills but stop-out frequency is approximately 2× that of 22-delta. Strategy doc updated: `docs/strategies/csp_nifty_v1.md`. Implementation requirements: (1) delta is a parameterised input in scripts — candidate values 20, 22, 25 selectable at entry; (2) liquidity gate: skip cycle if bid/ask spread > 5% of premium at the target delta strike; (3) regime-adaptive delta in future IVR-aware versions — 20–22-delta when IVR > 40 (high vol expansion), 25-delta when IVR 25–40 (normal). Do NOT base the v2 delta policy on N=6–8 paper cycles — sample is too small to capture stop-out or tail-event statistics. Maintain 12-month parameter discipline before re-tuning. Confidence: High.
Noted, deferred: ATR-based short strike selection as an alternative to delta-based, to eliminate IV surface model dependency — first candidate for post-validation testing.

**2026-05-02 — Gap Fade VIX-IVP filter: 75th percentile confirmed; asymmetry with ORB 90th is binding (council ruling).**
Source: `docs/council/2026-05-02_gap-fade-vix-filter-threshold.md`. Council (GPT-4.1 +
DeepSeek-R1 joint top-ranked at 1.5; Grok-4-fast at 3.0; chairman synthesis reconstructed
after Stage 3 failure). Asymmetric thresholds confirmed binding: Gap Fade (S3) = IVP_63d ≥
0.75 → skip; ORB (S2) = IVP_63d ≥ 0.90 → skip. Structural rationale: Gap Fade failure is
continuous/gradient (GIFT→NSE correlation breaks from IVP ~65–70 onward, below r ≈ 0.40 by
IVP 75); ORB failure is binary/tail-driven (hypothesis intact across normal-to-moderate IV,
degrades only at extreme pre-event anticipation IVP ≥ 90). A unified threshold at 75th
over-filters ORB; at 90th it retains ~35–40% structurally impaired Gap Fade trades. Both
measured as 63-day trailing percentile rank (`vix_lookback_days = 63`), self-calibrating.
Statistical risk of trade-count shortfall at 75th is acceptable (~15–20% insufficient
windows vs. 25% kill condition). Contingency protocol: (1) primary — expand gap range
0.3–1.0% → 0.25–1.2%; (2) secondary — raise threshold by 0.05 steps up to 0.85 maximum.
Mandatory ablation: report Gap Fade Sharpe at IVP thresholds [0.70, 0.75, 0.80, 0.85] in
Phase 1 walk-forward. Config: `vix_ivp_threshold = 0.75`, `vix_lookback_days = 63` (S3).
Confidence: High.
Noted, deferred: Grok-4-fast recommended 80th as safer default — ablation in Phase 1.8
will resolve empirically whether the 75th vs 80th delta exceeds 0.10 Sharpe.

**2026-05-02 — IC v1 delta targets: mild asymmetry; aggressive put-skew harvesting and symmetric deltas both rejected (council ruling).**
Source: `docs/council/2026-05-02_iron-condor-v1-core-design.md`. Chairman synthesis unanimous on rejecting symmetric deltas. Nifty's put skew (3–6 IV points richer at equivalent deltas) makes a 15-delta put and 15-delta call fundamentally different risk objects; symmetric IC is economically naive. Aggressive asymmetry (20Δ/10Δ) rejected because CSP already owns the left-tail premium trade — stacking a 20-delta IC short put on a 22-delta CSP short put creates correlated double exposure that destroys Calmar in sharp selloffs.

Adopted defaults:

| Mode | Short Put Target Δ | Short Call Target Δ |
|------|-----------------:|------------------:|
| Standalone IC (no CSP open) | ~15Δ | ~10Δ |
| Concurrent with CSP open | ~8–10Δ | ~12–15Δ |

Delta targets are parameterised inputs (candidates: put 10/12/15/18/20; call 8/10/12/15) for regime-adaptive operation once IVR ingestion is live. Tie-breaker: if two strikes straddle the target delta, choose the farther OTM strike — consistent with CSP v1's rule. Confidence: High.

**2026-05-02 — IC v1 adjustment rule: no intra-trade rolls or adjustments; exit-only (council ruling).**
Source: `docs/council/2026-05-02_iron-condor-v1-core-design.md`. Near-unanimous (3 of 4 council members). Rolling introduces path-dependency, partial-fill assumptions, bid/ask widening during stress, and re-entry credit modelling — multiplies Phase 2 complexity by 3–5×. The spread structure caps maximum loss by design; if the trade is wrong, accept the defined loss and re-enter next cycle. Single retail operator managing intraday rolling under stress is a recipe for discretionary errors that invalidate the systematic edge.

IC v1 exit stack (first trigger wins):

| # | Trigger | Action |
|---|---------|--------|
| 1 | Profit target | Close full IC when mark ≤ 50% of opening credit |
| 2 | Loss stop | Close full IC when mark ≥ 2.0× opening credit |
| 3 | Delta stop | Close full IC if either short leg reaches absolute delta ≥ 0.35 |
| 4 | Time stop | Close full IC at 14 DTE if still open |
| 5 | Expiry rule | Never hold IC to expiry in v1 |

Delta stop is an *exit* trigger, not a roll trigger. Backtest both 0.30 and 0.35; default 0.35 for paper v1 (0.30 may over-exit on call side in normal noise). Adjustments deferred to IC v2, informed by v1 paper and backtest results. Confidence: High.
Noted, deferred: if Calmar fails without adjustments, tighten entry filters (higher IVR threshold, add 200-DMA trend filter) or reduce wing width — do not add adjustment complexity as a first response.

**2026-05-02 — IC v1 portfolio interaction with CSP: portfolio-aware caps; neither strict delta neutrality nor pure independence (council ruling).**
Source: `docs/council/2026-05-02_iron-condor-v1-core-design.md`. Two responses argued independence (trust SPAN), one for delta neutrality, one for portfolio-aware caps; chairman adopted portfolio-aware caps. SPAN is a margin system, not a risk manager or Calmar optimizer — running CSP (short 22Δ put) + IC (short 15–20Δ put spread) independently creates combined net delta of approximately −0.30 to −0.40, amplifying downside beta above the portfolio's 1.25 target. Strict delta neutrality rejected because forcing the book to zero delta requires selling uncomfortably close calls (20–25Δ), which generates frequent false stop-outs in Nifty's persistent upward-drift regime.

Portfolio-aware rule: when CSP is open, IC entry is permitted only if the combined book satisfies:
- Combined option delta (lot-equivalent): −0.05 to +0.25
- Combined downside max loss (CSP stop + IC put-side max): ≤ monthly risk budget (₹6L)

If these limits cannot be satisfied at 1 lot, skip the IC cycle. Each strategy retains its own `strategy_name` in the trades table. Sizing is fixed at 1 lot (verify current NSE lot-size before each cycle — do not hardcode 65). The control levers are strike selection, wing width, and cycle-skipping — not fractional sizing. Confidence: High.

**2026-05-02 — Leg 2 strike selection: fixed %OTM maintained; delta-based rejected as primary (council ruling).**
Source: `docs/council/2026-05-02_integrated-leg2-strike-methodology.md`. Unanimous council (GPT-4.1 chairman, Grok-4-fast, DeepSeek-R1; Grok ranked #1 in peer review). Fixed %OTM strikes (long put at 8% below spot, short put at 20% below spot) retained as the sole primary methodology for Leg 2. Delta-based selection (long put at 15-delta, short put at 5-delta) rejected as primary on three grounds: (1) the dead zone widens to 10–12% in low-vol regimes — exactly the regime where moderate corrections are most common (~70% of historical moderates); (2) cost spikes sharply in high-IV periods (can double or triple at VIX=22), risking budget overruns precisely when protection demand is highest; (3) empirical Monte Carlo modelling shows %OTM at 92% reliability vs 85% for delta-based for payoff >50% of MF loss in 8–15% correction scenarios. Liquidity filter added: if 8% OTM OI < 500 contracts at entry, step one strike inward (7% OTM; if still < 500, use 6% OTM). Log any deviation from 8% base in trade metadata. Delta-based reserved as a conditional overlay for future consideration at IVR > 70% in Phase 2 research. Confidence: High.
Noted, deferred: delta-based as a hybrid/conditional overlay in extraordinary volatility events (IVR > 70%) — first candidate for Phase 2 enhancement after paper-trade validation confirms %OTM reliability.

---

## §7.3 — Multi-Strategy Portfolio Risk (Phase 3)

**2026-05-02 — All Nifty options strategies governed as a single portfolio risk unit (council ruling).**
Source: `docs/council/2026-05-02_multi-strategy-portfolio-risk-allocation.md`. Chairman: Claude Opus 4.6. Council: GPT-5.5, Gemini 3.1 Pro, Grok-4, DeepSeek-R1. GPT-5.5 ranked #1 in peer review; chairman synthesis draws heavily from it.

**Architectural note:** `niftyshield_integrated_v1.md` explicitly states that its Leg 1 *is* the CSP — "Entry, exit, and adjustment rules for Leg 1 are governed entirely by `csp_nifty_v1.md`." Running standalone CSP v2 (A) concurrently with Integrated (B) creates **2 lots of short-put exposure**, not 1. This doubled exposure must be explicitly sized within the portfolio risk budget.

**Binding rules for Phase 3 (all 13 are mandatory):**

| # | Rule |
|---|------|
| 1 | All Nifty option strategies are ONE portfolio risk unit |
| 2 | Options-only bullish delta cap: +1.0 Nifty futures-equivalent lot (warning at +0.75) |
| 3 | Options + NiftyBees bullish delta cap: +2.0 lots (warning at +1.5) |
| 4 | −10% Nifty / IV+10–15 vol stress loss: ≤ ₹3L options-only, ≤ ₹4L with NiftyBees |
| 5 | Absolute portfolio drawdown kill zone: ₹6L |
| 6 | Far OTM long puts (>15% OTM) receive no risk-reduction credit in −10% scenario; 8–15% OTM receives 50–70% credit |
| 7 | Size from internal stress-loss budget, never from broker SPAN margin |
| 8 | SPAN offsets reduce required cash only — they do not permit larger short-premium size |
| 9 | Shadow Gross Margin: portfolio must survive simultaneous removal of ALL SPAN offsets without exceeding 80% of ₹45L post-haircut collateral pool (~₹36L) |
| 10 | Maximum short-put lots across all concurrent strategies: 2 |
| 11 | Validate paper/live results only against the **cap-aware portfolio backtest** (Layer 2), not standalone per-strategy backtests |
| 12 | Log every skipped signal with explicit risk-cap reason: `DELTA_CAP \| STRESS_LOSS_CAP \| MARGIN_CAP \| DUPLICATE_EXPOSURE \| EVENT_FILTER \| TREND_FILTER \| LIQUIDITY_FILTER \| MANUAL_BLOCK` |
| 13 | Protective hedge entries (Integrated Legs 2 and 3) are **never** blocked by the delta cap |

**Trade priority order when delta cap is binding:**
1. Risk-reducing exits (always allowed)
2. Protective hedge entries (Legs 2, 3) — unconditional
3. Integrated CSP (Leg 1) — priority over standalone (hedged structure)
4. Standalone CSP v2 — only if residual stress budget remains
5. Swing strategies — bearish spreads may pass if they reduce stress; bullish blocked first
6. Covered call overlay — must not be used as a loophole for more short puts

**Scenario stress table (reprice full book before any new bullish entry):**

| Scenario | Spot Move | IV Shock |
|----------|-----------|----------|
| Moderate | −5% | +5 vol points |
| Significant | −10% | +10–15 vol points |
| Severe | −15% | +15–20 vol points |
| Tail | −20% | +20 vol points |

**Three-layer variance validation framework:**
- Layer 1 — Standalone per-strategy backtest (uncapped): validates raw edge in isolation.
- Layer 2 — Cap-aware portfolio backtest (primary benchmark): simulates real Phase 3 deployment; includes shared margin, delta cap, stress-loss cap, signal-skipping, position netting, and broker cost model.
- Layer 3 — Paper/live variance check: compare against Layer 2 only. Gate: |paper PnL − cap-aware backtest PnL| / backtest PnL < **15%** tracking error.

**Implementation sequence:**
- Phase 0.6c: `PortfolioDeltaTracker` in `src/risk/` — daily delta aggregation across paper positions
- Phase 1: Scenario repricing engine (stress-loss guard) in `src/risk/`
- Phase 2: `src/backtest/portfolio_sim.py` — cap-aware portfolio backtester with signal-skipping
- Phase 3 gate: Cap-aware backtest Sharpe ≥ 0.8 and max DD < ₹6L across 6+ years before live deployment

**Noted, deferred:** Liquidity buffer rule (free cash ≥ 1.5× current margin) and OI-based liquidity multiplier on the conservative offset haircut (credit only 70% of SPAN offset for spreads wider than 10%) — first candidates for Phase 2 `src/risk/` expansion. Confidence: High.

---

## Backtest Data Source Decision (2026-04-27)

Evaluated TrueData and DhanHQ for NSE Nifty options backtesting. Primary use case: insurance calibration backtest for the NiftyShield short put strategy, targeting delta-based strike selection with a max drawdown of ~₹6L on a ₹1 crore portfolio.

**TrueData — Rejected:**
- 1-min bar data: 6 months depth only — useless for stress event backtesting
- Tick data: 5 days depth
- `getTickHistorywithGreeks` is under development — unavailable
- Historical Greeks do not exist; Greeks are live-only and a paid add-on
- EOD data: 10+ years, but freely available from NSE directly
- No justifiable cost given free alternatives

**DhanHQ Data API — Rejected for backtesting:**
- 1-min intraday: ~5 days depth only (previously believed to be 5 years — confirmed wrong after evaluation)
- EOD: 5 years depth — misses COVID Mar 2020 and IL&FS Sep–Oct 2018, the two most important stress windows for NiftyShield's drawdown methodology
- No historical Greeks
- Previously adopted as the primary backtesting source in this file; that decision is superseded. DhanHQ Data API subscription will NOT be pursued.

**Stockmock ([stockmock.in](https://stockmock.in)) — Adopted for calibration backtest phase:**
- Already subscribed, no additional cost
- UI-based NSE F&O options backtester with historical data
- Covers key stress windows: COVID Mar 2020, IL&FS Sep–Oct 2018, 2022 rate-hike selloff — exactly the windows DhanHQ cannot provide
- Purpose-built for the insurance calibration objective: finding the right delta strike, breach frequency across market regimes, premium behaviour across IV environments
- Limitation: no Python API, output is UI reports only — cannot integrate directly with NiftyShield codebase
- Action: run stress scenario backtests manually across COVID, IL&FS, 2022 windows; document delta sweet spot findings; use results to set initial hardcoded thresholds in `csp_nifty_v1.md`

**NSE F&O Bhavcopy (free, direct from exchange) — Adopted for programmatic pipeline:**
- NSE publishes daily F&O bhavcopy CSV files going back to 2016+ at zero cost
- Each file contains every active option strike: symbol, expiry, strike, option type, OHLCV, OI, settlement price
- Authoritative source (exchange itself), no vendor dependency, no API subscription
- No Greeks — IV must be reconstructed via Black-Scholes inverse from settlement price and spot (spot from Upstox OHLC via task 1.3a)
- Data depth: 2016–present, covering COVID Mar 2020, IL&FS Sep–Oct 2018, 2022 rate hike — all critical stress windows
- Storage: Parquet, partitioned by expiry month, under `data/offline/`
- Schema: `date, symbol, expiry, strike, option_type, open, high, low, close, volume, oi, settle_price`
- Implementation: `src/backtest/bhavcopy_ingest.py` — download, parse option symbol string (e.g. `NIFTY26APR24000PE`), normalise, store. See BACKTEST_PLAN.md task 1.3.

**Upstox API — Confirmed for forward testing and production:**
- Already integrated in NiftyShield codebase (`src/client/upstox_market.py`, `UpstoxLiveClient`)
- Provides live option chain with real-time Greeks (delta, IV, theta, vega) at 1-min cadence via the Analytics Token — zero additional cost
- Forward testing phase after calibration backtest is complete
- Production delta monitoring for monthly CSP strike selection
- `UPSTOX_ANALYTICS_TOKEN` already active; no new subscription required

**Final stack:**

| Phase | Tool | Cost |
|---|---|---|
| Calibration backtest (historical) | Stockmock UI | Already subscribed |
| Programmatic data pipeline | NSE F&O Bhavcopy ingestion | Free |
| Forward testing + production | Upstox API (existing) | Already integrated |

**Implication for two-tier backtest methodology (2026-04-26 decision):** The original Tier 1 rationale ("real Dhan expired options data") is updated — Tier 1 now uses NSE F&O Bhavcopy for OHLCV + Black '76 IV reconstruction (see IV Reconstruction Methodology 2026-04-30 below). Tier 2 (deep OTM synthetic pricing for protective legs) is unchanged — still Black-Scholes with parametric skew (`src/backtest/synthetic_pricer.py`), since NSE Bhavcopy covers all strikes at EOD.

---

## IV Reconstruction Methodology (2026-04-30)

Decision reached via multi-model council (GPT-5.4, Gemini 3.1 Pro, Claude Opus 4.6, Grok-4). Supersedes the 2026-04-27 placeholder in task 1.6a which assumed Black-Scholes with spot + fixed risk-free rate.

**Pricing model: Black '76 (not Black-Scholes with spot).** Nifty Futures `settle_price` (same expiry as the option) is used as the forward price `F`. This eliminates both dividend yield estimation (`q`) and carry-adjusted spot forward estimation simultaneously — the market's own consensus is embedded in the futures price. For the rare case where the exact-expiry future is unavailable in the Bhavcopy, fall back to `F ≈ S × exp(r × T)` using Nifty spot from task 1.3a.

**Risk-free rate: stepped RBI Repo Rate, not a constant.** RBI changed the repo rate ~20 times between 2016 and 2024 (notably: 4.0% May 2020, 6.5% from Feb 2023). A constant 7% understates the discount factor during the 2020 low-rate period. Impact on IV is small (~0.1–0.3 IV points on 30-DTE options) but directionally systematic. Implement as a hardcoded stepped table in `src/backtest/repo_rates.py` — ~20 entries, zero ongoing cost. Even with Black '76, `r` is still needed for the `exp(−rT)` discount factor.

**Option price field: guarded blend per job, not uniform `settle_price`.** Two separate jobs have different requirements:
- *Entry pricing / strike selection* (needs execution realism): use `close` if volume > 0 AND `|close − settle_price| / max(settle_price, 0.5) < 0.50`. Fall back to `settle_price` when `close` is stale or zero. Mark rows where neither is usable as `unusable`.
- *IV percentile time series* (needs cross-year consistency): use `settle_price` uniformly for the ATM IV series. Consistency across 8 years matters more than per-day accuracy on any single date.

**IV inversion: per-strike Black '76 inverse via `scipy.optimize.brentq`.** Standard method; recovers the market's strike-specific implied vol. The volatility smile/skew is what you discover through inversion — it does not invalidate the method. Bounds: `σ ∈ [0.01, 3.0]`. Returns `None` + WARNING on non-convergence. Exclusion gates applied before inversion: DTE < 5 calendar days, price < ₹1.0, extrinsic value < ₹0.50, `settle_price ≤ 0`. Extreme IV results (> 150%) during crash regimes are valid — keep but flag; do not cap.

**Delta computation: quadratic smile fit in log-moneyness before computing delta.** Raw per-strike IV inversion is noisy for illiquid strikes. For delta-based strike selection, fit a quadratic `IV = a + b·log(K/F) + c·log(K/F)²` weighted by ATM proximity, then compute Black '76 delta from the smoothed IV at each strike. This handles the Nifty skew correctly (deep OTM puts carry a skew premium vs ATM) and produces stable 25-delta strike selection even when some individual strikes have bad data. Implemented via `np.polyfit` — computationally trivial.

**IV percentile: 30-DTE constant-maturity ATM IV, variance-space interpolation.** A single daily number comparable across all 8 years. Interpolate to 30 DTE in total-variance space (`σ²T` is additive) using the two nearest available expiries in the 7–90 DTE range. 252-day rolling lookback for percentile rank. Use `settle_price`-based ATM IV uniformly for this series (consistency over execution realism).

**Daily validation: ATM straddle + put-call parity sanity check.** Run before computing the IV surface each day. Checks: (1) put-call parity error < 0.5% of spot — detects spot/futures data misalignment or corrupt Bhavcopy rows; (2) Brenner-Subrahmanyam ATM IV approximation (`straddle / (0.8 × F × √T)`) provides a fast independent sanity check on the inversion pipeline. Days with parity error > 0.5% are flagged `suspect` but retained — do not silently drop.

**Module shape:**

| Module | Contents |
|---|---|
| `src/backtest/repo_rates.py` | `get_repo_rate(date) → float` — stepped RBI repo table, no I/O |
| `src/backtest/greeks.py` | `black76_price`, `black76_iv`, `black76_delta`, `black76_gamma`, `black76_theta`, `black76_vega` — all parameterised on `F` (futures forward), not `S` (spot) |
| `src/backtest/iv_reconstruction.py` | `select_price_for_entry`, `atm_sanity_check`, `fit_smile_and_get_delta`, `compute_30dte_atm_iv`, `iv_percentile`, `process_daily_chain` — full daily pipeline; `DailyChainResult` frozen dataclass as output |
| `src/backtest/strike_selector.py` | `select_strike_by_delta(smile_df, target_delta, option_type)` — consumes smoothed delta output from `iv_reconstruction`; not raw per-strike IV inversion |

**Open question (unresolved, 2026-04-30):** Should `bhavcopy_ingest.py` (task 1.3) also parse `FUTIDX NIFTY` rows from the same daily Bhavcopy CSV and store them in a separate Parquet, or should task 1.6a derive futures prices at query time? Parsing futures in task 1.3 is cleaner (single download, single parse pass, no repeated I/O); storing them in a separate Parquet avoids coupling the ingestion schema to the IV pipeline's needs. Resolve this before starting task 1.6a implementation.

**Known biases remaining after Black '76 switch (must be called out in 1.11 variance check):**
- `settle_price` is not an executable fill — entry price is structurally mid-market-optimistic. Absorbed by the slippage model (task 1.4); quantify the gap in 1.11.
- Black '76 delta from EOD settlement vs Upstox live chain delta (which uses a proprietary intraday surface fit): ~0.5–2 delta points structural mismatch expected at 25-delta. Compute RMS delta error against task 1.10 snapshots in 1.11 to establish the structural variance floor before applying the |Z| ≤ 1.5 gate.
- Weekly vs monthly expiry confusion post-2019: filter explicitly for monthly expiry (last Thursday, or Wednesday if Thursday is a NSE holiday) in `process_daily_chain`. Mixing weekly/monthly strikes distorts the smile fit.

**Biases eliminated vs original Black-Scholes + spot plan:** Dividend yield / carry adjustment (now implicit in futures price). Seasonal IV bias from ex-dividend periods. Dependency on Upstox spot as the sole forward price source.

---

## Slippage Model for Historical Bhavcopy Backtest (2026-04-30)

Decision reached via multi-model council (GPT-5.4, Gemini 3.1 Pro, Claude Opus 4.6, Grok-4). Supersedes the placeholder in task 1.4 which assumed a flat 0.5–1 INR band. High consensus across all four models on the core architecture; minor divergence on exact parameter values and failure-mode philosophy.

**Primary model: absolute INR, VIX-regime-aware (not percentage of premium).** Unanimous. Option spreads in Nifty options are far more stable in absolute rupee terms than as a percentage of premium — the minimum tick (₹0.05) and order book depth create an absolute floor that percentage models cannot replicate. A ₹90 put and a ₹200 put at similar OI and delta will have spreads within ~1.5× of each other, not 2.2× as a percentage model implies.

**Fill model:** `entry SELL fill = settle_price − s`; `exit BUY fill = settle_price + s`, where `s` (one-sided slippage, INR) is:

| India VIX | Base slippage (`s`) |
|---|---|
| VIX ≤ 20 | ₹1.0 |
| 20 < VIX ≤ 25 | ₹1.5 |
| 25 < VIX ≤ 30 | ₹3.0 |
| VIX > 30 (crisis) | ₹4.0 |

**Secondary adjustment: OI-based liquidity multiplier.** Multiplier applied to base `s`:

| Strike OI | Multiplier |
|---|---|
| ≥ 50,000 | 1.0× |
| 20,000 – 49,999 | 1.5× |
| 5,000 – 19,999 | 2.0× |
| < 5,000 | 2.5× (flag as potentially unexecutable) |

Final slippage: `s_final = base_slippage(vix) × liquidity_multiplier(oi)`. The base values are anchored at the 60th–70th percentile of estimated spreads — modestly conservative, not worst-case.

**`SlippageModel` dataclass fields (for `src/backtest/costs.py`):**

```python
@dataclass(frozen=True)
class SlippageModel:
    # VIX tier thresholds and base slippage values (INR, one-sided)
    vix_tiers: tuple[tuple[float, float], ...] = (
        (20.0, 1.0), (25.0, 1.5), (30.0, 3.0), (float('inf'), 4.0)
    )
    # OI tier thresholds and multipliers
    oi_tiers: tuple[tuple[int, float], ...] = (
        (50_000, 1.0), (20_000, 1.5), (5_000, 2.0), (0, 2.5)
    )
    # Asymmetric stop-loss exit multiplier (optional; applied to 2× stop exits only)
    stop_loss_exit_multiplier: float = 1.5
```

**Critical: slippage must propagate into exit trigger logic.** Exit rules (50% profit, 2× credit stop, 21 DTE) are calculated from realized fills, not settle prices. If the opening SELL filled at ₹98.5 (settle ₹100 − ₹1.5 slippage), the actual credit is ₹98.5. The 50% profit target is ₹49.25; the 2× stop is ₹197. Exit BUY fill also includes slippage: `exit_fill = settle + s`. Failing to propagate slippage through trigger logic systematically overstates profitability — a common backtest error.

**Asymmetric exit slippage (optional enhancement).** Stop-loss exits occur during crashes when VIX has already spiked and the 25-delta put is now 50–60 delta — spreads are widest exactly when losses are largest. Apply `stop_loss_exit_multiplier = 1.5–2.0×` to the 2× stop-loss BUY fill. Profit-target and time-stop exits use standard slippage. Implement if the base model's stop-loss bias turns out to be material in the variance check.

**Three-scenario sensitivity (mandatory in all backtest reports):**

| Scenario | VIX ≤ 25 | VIX > 25 |
|---|---|---|
| Optimistic | ₹0.75/side | ₹1.5/side |
| Base (primary) | ₹1.0–1.5/side | ₹3.0/side |
| Conservative | ₹2.5/side | ₹5.0/side |

Decision rule applied at reporting time: profitable at zero slippage only → reject; profitable at base, marginal at conservative → paper trade small; profitable at conservative → strong deployment candidate.

**Forward calibration plan.** Once 3–6 months of Upstox 5-min bid/ask snapshots accumulate (task 1.10a, already running): segment realized half-spreads by delta bucket, DTE bucket, VIX regime, OI level, time of day. Fit a regression `expected_half_spread = f(log(OI), VIX, DTE, premium, moneyness)`. If within ±30% of the tiered model, historical backtest conclusions hold. If materially different, retrofit and re-evaluate. This plan does not delay running the backtest — use the tiered model now, calibrate later.

**Materiality.** Typical net credit: ₹80–150/unit → ₹4,000–7,500/lot (50 units). Round-trip slippage at base case: ~₹100–150/lot. Annual drag on 12 round-trips: ₹1,200–1,800/lot. Meaningful but not strategy-killing for a CSP with genuine edge; will reduce returns but should not transform a profitable strategy into a losing one unless the edge is razor-thin — in which case slippage is doing the right diagnostic work.

**Failure-mode verdict: optimistic bias (underestimating slippage) is the worse failure.** Three of four models agreed unambiguously; one dissented on grounds that for a low-frequency strategy with fast feedback loops and a forward data collection plan, the cost of false negatives (rejecting a viable strategy) could outweigh false positives. The dissent has merit in the abstract but is outweighed by: (1) asymmetric real-world consequences — underestimating slippage leads to committing real capital to a strategy with an illusory edge, while overestimating leads to opportunity cost only; (2) psychological anchoring — live positions are harder to exit than abandoned backtests; (3) slippage is highest exactly when losses are largest (stop exits during volatility spikes), so underestimating it understates the worst drawdowns. Err modestly conservative at the 60th–70th percentile, not the 95th.

**Methodology statement (ready for strategy spec documentation):** "Historical NSE Bhavcopy settle prices are treated as mid-market proxies. Executable fills for short options occur at bid on entry and ask on exit; we adjust by a modeled half-spread. In the absence of historical bid/ask data, we employ an absolute slippage model in INR premium points, conditioned on India VIX regime and strike-level open interest as a liquidity proxy. Results are presented across optimistic, base, and conservative slippage scenarios. The base case is anchored to the 60th–70th percentile of estimated spreads. Forward calibration using real-time 5-minute bid/ask snapshots (task 1.10a) will validate and, if necessary, retrofit the historical model."

---

## Deferred / Not Yet Built

- `src/strategy/`, `src/execution/`, `src/backtest/`, `src/risk/`, `src/streaming/` — all empty
- Expired instruments API (Upstox) — blocked (paid subscription). NSE F&O Bhavcopy is the adopted alternative for historical options OHLCV — no Upstox paid tier needed for backtesting
- TimescaleDB — deferred indefinitely (original justification was DhanHQ 1-min volume; DhanHQ rejected 2026-04-27; NSE Bhavcopy EOD data fits in Parquet + SQLite)
- DhanHQ Data API subscription — rejected 2026-04-27 (insufficient historical depth for stress testing; no historical Greeks)
- Order execution — blocked (static IP not provisioned). `MockBrokerClient` for all development
- P&L visualization — matplotlib or React dashboard; deferred until several weeks of snapshot history
- `ReplayMarketStream` + `StreamRecorder` — not yet built
- Rate limiter + retry middleware — token bucket decorator; not yet built
