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

---

## Strategy & Research Decisions

> Full rationale for each decision lives in the referenced council file or strategy doc.
> This section is an index — one line per decision. Read the source file for reasoning.

| Date | Decision | Source |
|---|---|---|
| 2026-04-25 | CSP underlying → Nifty 50 index options (NiftyBees rejected: OI <1,000, spread >5% of mid) | `docs/strategies/csp_nifty_v1.md` |
| 2026-04-25 | NiftyBees collateral modelled as `long_niftybees` leg in paper P&L; annual reset in January | `docs/strategies/csp_nifty_v1.md` |
| 2026-04-26 | NiftyShield integrated: CSP Leg 1 + put spread 4 lots (8–20% OTM) + tail puts 2 lots (5-delta quarterly) | `docs/strategies/niftyshield_integrated_v1.md` |
| 2026-04-26 | Static beta 1.25 for MF hedge ratio; switch to rolling 60d beta after 12+ months NAV history | `docs/strategies/niftyshield_integrated_v1.md` |
| 2026-04-26 | Two-tier backtest: Tier 1 = Bhavcopy + Black '76 IV; Tier 2 = synthetic pricer for deep OTM protective legs | `BACKTEST_PLAN_PHASE1.md §1.9a` |
| 2026-04-27 | Data stack: TrueData + DhanHQ rejected; Stockmock (calibration) + NSE Bhavcopy (programmatic) adopted | `BACKTEST_PLAN_PHASE1.md §1.1, §1.3` |
| 2026-04-27 | TimescaleDB deferred indefinitely (Bhavcopy EOD ~4M rows fits Parquet + SQLite) | `BACKTEST_PLAN_PHASE1.md §1.2` |
| 2026-04-30 | IV reconstruction: Black '76 with Nifty Futures forward; stepped RBI repo rate; quadratic smile fit for delta | `BACKTEST_PLAN_PHASE1.md §1.6a` |
| 2026-04-30 | Slippage: absolute INR, VIX-regime-aware + OI liquidity multiplier; base at 60–70th percentile | `BACKTEST_PLAN_PHASE1.md §1.4` |
| 2026-05-01 | Donchian: signal-in-only (ATR trailing stop → flat, not always-in); credit spreads uniform; ATR-proportional spread width | `docs/council/2026-05-01_donchian-roll-mechanics.md` |
| 2026-05-01 | ORB: ATR primary filter + VIX-IVP 90th-pct structural exclusion; event-day calendar exclusion mandatory; DTE ≤ 2 → skip to next weekly | `docs/council/2026-05-01_orb-volatility-filter-design.md` |
| 2026-05-02 | CSP delta: 22-delta default (85% of 25d credit, ~half stop-out rate); 25-delta when IVR 25–40; parameterised in scripts | `docs/council/2026-05-02_csp-entry-delta-v2.md` |
| 2026-05-02 | Gap Fade VIX-IVP filter: 75th percentile (vs ORB 90th); asymmetry is structural and binding | `docs/council/2026-05-02_gap-fade-vix-filter-threshold.md` |
| 2026-05-02 | IC v1: mild put-side asymmetry (short put 16Δ / short call 14Δ normal; 18Δ/12Δ high-IVR); symmetric deltas rejected | `docs/council/2026-05-02_iron-condor-v1-core-design.md` |
| 2026-05-02 | 3-track comparison: Track C = Deep ITM Call (delta ≈ 0.90); Track B + Covered Call / CSP programmatically blocked | `docs/council/2026-05-02_nifty-long-instrument-comparison-protection.md` |
| 2026-05-02 | Near-expiry buy research (Phase 3): Gamma Gearing primary; Speed secondary; OI velocity confirmation only | `docs/council/2026-05-02_gamma-acceleration-mispricing-option-buying.md` |
| 2026-05-02 | Live monitoring: CUSUM lower-sided (k=0.50, h_warn=3.0, h_reduce=4.0, h_halt=5.0) replaces weekly Z-score | `docs/council/2026-05-02_continuous-revalidation-statistical-power.md` |
| 2026-05-02 | Phase 0.8 gate: 4 criteria (A–D); Z-score is smoke test only; graduated deployment tiers 0 → 0.5 → 1 → 2 → 3 | `docs/council/2026-05-02_variance-gate-regime-completeness.md`, `docs/plan/variance_gate.md` |

---

## §7.3 — Multi-Strategy Portfolio Risk Caps (implementation reference)

**All binding rules — apply from Phase 0.6c onwards:**

| # | Rule |
|---|------|
| 1 | All Nifty option strategies are ONE portfolio risk unit |
| 2 | Options-only bullish delta cap: **+1.0 lot** (warning at +0.75) |
| 3 | Options + NiftyBees bullish delta cap: **+2.0 lots** (warning at +1.5) |
| 4 | −10% Nifty / IV+10–15 vol stress loss: ≤ ₹3L options-only, ≤ ₹4L with NiftyBees |
| 5 | Absolute portfolio drawdown kill zone: **₹6L** |
| 6 | Far OTM long puts (>15% OTM) receive no stress-loss credit; 8–15% OTM receives 50–70% credit |
| 7 | Size from internal stress-loss budget — never from broker SPAN margin |
| 8 | Shadow Gross Margin: must survive simultaneous removal of ALL SPAN offsets without exceeding 80% of ₹45L post-haircut collateral pool |
| 9 | Maximum short-put lots across all concurrent strategies: **2** |
| 10 | Protective hedge entries (Legs 2 and 3) are **never** blocked by the delta cap |
| 11 | Log every skipped signal: `DELTA_CAP \| STRESS_LOSS_CAP \| MARGIN_CAP \| DUPLICATE_EXPOSURE \| EVENT_FILTER \| TREND_FILTER \| LIQUIDITY_FILTER \| MANUAL_BLOCK` |

**Trade priority when delta cap binding:** Risk-reducing exits → Protective hedges (Legs 2/3) → Integrated CSP (Leg 1) → Standalone CSP v2 → Bearish swing spreads → (covered call blocked)

**Source:** `docs/council/2026-05-02_multi-strategy-portfolio-risk-allocation.md`

---

## Backtest Data Source Decision (2026-04-27)

| Tool | Status | Reason |
|---|---|---|
| TrueData | Rejected | 1-min: 6 months depth; tick: 5 days; no historical Greeks |
| DhanHQ Data API | Rejected | 1-min: ~5 days depth (not 5 years); EOD misses COVID Mar 2020 + IL&FS Sep 2018 |
| Stockmock | Adopted — calibration backtests | Already subscribed; covers all critical stress windows; UI-only |
| NSE F&O Bhavcopy | Adopted — programmatic pipeline | Free; exchange-authoritative; 2016–present; see `BACKTEST_PLAN_PHASE1.md §1.3` |
| Upstox Analytics API | Confirmed — forward testing + production | Already integrated; live Greeks at zero additional cost |

---

## IV Reconstruction Methodology (2026-04-30)

**Key choices (full rationale: `docs/council/2026-05-02_*`):**
- Pricing model: **Black '76** (Nifty Futures `settle_price` as forward `F` — eliminates dividend yield + carry adjustment)
- Risk-free rate: **Stepped RBI Repo Rate** (~20 entries, 2016–2024) in `src/backtest/repo_rates.py`
- Option price: **Guarded blend** — `close` if volume >0 and `|close − settle| / settle < 0.50`; else `settle_price`; mark unusable rows
- IV inversion: **`scipy.optimize.brentq`** per strike, bounds σ ∈ [0.01, 3.0]; exclude DTE <5, price <₹1, extrinsic <₹0.50
- Delta: **Quadratic smile fit** in log-moneyness (`np.polyfit`), then Black '76 delta from smoothed IV

**Module shape:**

| Module | Contents |
|---|---|
| `src/backtest/repo_rates.py` | `get_repo_rate(date) → float` |
| `src/backtest/greeks.py` | `black76_price`, `black76_iv`, `black76_delta`, `black76_gamma`, `black76_theta`, `black76_vega` |
| `src/backtest/iv_reconstruction.py` | `select_price_for_entry`, `fit_smile_and_get_delta`, `compute_30dte_atm_iv`, `iv_percentile`, `process_daily_chain` → `DailyChainResult` |
| `src/backtest/strike_selector.py` | `select_strike_by_delta(smile_df, target_delta, option_type)` |

---

## Slippage Model (2026-04-30)

**Absolute INR, VIX-regime-aware. Fill: SELL at `settle − s`, BUY at `settle + s`.**

| India VIX | Base slippage `s` |
|---|---|
| ≤ 20 | ₹1.0 |
| 20–25 | ₹1.5 |
| 25–30 | ₹3.0 |
| > 30 | ₹4.0 |

**OI liquidity multiplier applied to base `s`:**

| Strike OI | Multiplier |
|---|---|
| ≥ 50,000 | 1.0× |
| 20,000–49,999 | 1.5× |
| 5,000–19,999 | 2.0× |
| < 5,000 | 2.5× (flag as potentially unexecutable) |

Stop-loss exit multiplier: 1.5× (spreads widest during crashes). All backtest reports must include optimistic / base / conservative scenario table. **Source:** `docs/council/2026-05-02_continuous-revalidation-statistical-power.md`

---

## Live Strategy Monitoring (2026-05-02)

**CUSUM replaces weekly Z-score for N < 24 live cycles.**

```
C_t = max(0, C_{t-1} − z_t − k)
z_t = (cycle_pnl_t − μ_backtest) / σ_backtest
k = 0.50  |  h_warning = 3.0  |  h_reduce = 4.0  |  h_halt = 5.0
```

Update monthly at cycle close only. Two versions: (a) combined strategy P&L, (b) option-leg-only.

| Live closed cycles N | Active monitoring regime |
|---|---|
| N < 6 | Hard risk guards only |
| 6 ≤ N < 12 | CUSUM warning (h=3.0) triggers manual review |
| 12 ≤ N < 24 | CUSUM reduce/halt thresholds active; Z-score advisory |
| N ≥ 24 | Full: CUSUM + Z-score + guards |

**Early guards (active from first live trade):** R6 single-cycle catastrophic loss; 3-cycle rolling drawdown > 4× credit → paper-only; 3 consecutive losses → halt; open MTM > 3× credit → close + pause; regime-divergence flag (VIX >95th pct, IVR <25, R4 event); slippage > 2× modeled for 2 cycles → paper-only. **Implementation:** `src/risk/monitoring.py` (Phase 2). **Source:** `docs/council/2026-05-02_continuous-revalidation-statistical-power.md`

---

## Variance Gate — Phase 0.8 Deployment Tiers (2026-05-02)

| Tier | Requirements | Constraints |
|---|---|---|
| 0 — Paper only | Recording works, P&L reconciles | No live capital |
| 0.5 — Two-cycle review | After 2 paper cycles: strike/fill/P&L reconcile sanity | Operational only, not statistical |
| 1 — Limited live pilot | All Phase 0.8 criteria A–D met; `\|Z\| ≤ 1.5` regime-matched; all exit paths validated | 1 lot max; manual approval per entry |
| 2 — Normal v1 live | N ≥ 12 cycles OR N ≥ 6 + ≥1 genuine stressed episode; ≥1 delta-stop live | Runs as designed at conservative size |
| 3 — Overlay integration | N ≥ 18–24; full regime coverage; hedge-overlay interaction verified | Prerequisite for NiftyShield integrated |

Full gate specification: `docs/plan/variance_gate.md`. **Source:** `docs/council/2026-05-02_variance-gate-regime-completeness.md`

---

## Deferred / Not Yet Built

- `src/strategy/`, `src/execution/`, `src/backtest/`, `src/risk/` (except 0.6c), `src/streaming/` — all empty
- Expired instruments via Upstox — blocked (paid). NSE F&O Bhavcopy is the adopted alternative (free)
- Liquidity buffer rule + OI-based margin haircut — deferred to Phase 2 `src/risk/` expansion
