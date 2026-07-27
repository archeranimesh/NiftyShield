# NiftyShield — Module Tree

> File-level descriptions for every module in `src/`, `scripts/`, `tests/`, `.claude/`, and `docs/archive/`.
> Load this file when: adding new modules, reviewing full codebase structure, or when the graph cannot answer a structural question.
> For day-to-day task work, the graph (`search_graph`, `get_code_snippet`) is faster and cheaper.

---

```
src/
├── auth/
│   ├── login.py              # OAuth flow — opens browser, captures code, saves token to .env
│   ├── verify.py             # API connectivity check — fetches user profile
│   ├── nuvama_login.py       # Nuvama request_id flow — opens browser, captures request_id from redirect, initializes APIConnect session, saves NUVAMA_SETTINGS_FILE to .env. APIConnect persists session token in settings_file (no daily re-auth required after first login).
│   └── nuvama_verify.py      # Nuvama connectivity check — loads APIConnect from settings_file, calls Holdings(), prints holding count + ltp. parse_holdings() is a pure function (testable independently).
│   ├── dhan_login.py          # Dhan manual token flow — opens web.dhan.co, prompts for token, validates, saves DHAN_ACCESS_TOKEN to .env via dotenv.set_key(). Pure functions: build_login_url(), validate_token(), save_token(). No SDK dependency.
│   └── dhan_verify.py         # Dhan connectivity check — loads DHAN_CLIENT_ID + DHAN_ACCESS_TOKEN, calls GET /v2/profile + /v2/holdings via raw requests. parse_holdings() pure function. Returns True/False.
├── backtest/
│   ├── __init__.py           # Package marker
│   ├── chain_writer.py       # ChainWriter: writes EOD and 5-min intraday option chain snapshots to PyArrow Parquet
│   ├── chain_reader.py       # ChainReader: DuckDB-based scanning and filtering of chain snapshots
│   ├── bhavcopy_ingest.py    # Downloads and parses NSE F&O bhavcopy (both legacy and UDiFF formats) to Parquet
│   ├── bhavcopy_loader.py    # load_options_ohlcv(underlying, start, end, data_dir, columns): reads options OHLCV Parquet partitioned by year/month from DEFAULT_DATA_DIR. Returns pd.DataFrame; empty DataFrame if no data found. Used by backtest engine.
│   ├── constants.py          # DEFAULT_DATA_DIR: Path to data/offline/options_ohlcv/ (repo-root-relative). Imported by bhavcopy_loader.py.
│   ├── vix_ingest.py         # India VIX historical ingestion pipeline (NSE CSV / Upstox API)
│   └── ivr.py                # Trailing 252-day India VIX Implied Volatility Rank (IVR) calculation
├── gamma/
│   ├── __init__.py           # Package marker
│   ├── models.py             # GammaChainSnapshot + GammaWatchlistEntry frozen dataclasses — Near-Expiry Gamma Buy strategy scaffolding
│   └── store.py              # GammaStore: SQLite persistence for gamma chain snapshots + watchlist entries
├── council/
│   ├── __init__.py           # Package marker
│   ├── models.py             # Council request/response Pydantic models (CouncilOutput etc.)
│   └── rapid.py              # RapidCouncil: parallel Stage-1 fan-out (5 heterogeneous personas) + chairman synthesis + timeout handling
├── models/
│   ├── __init__.py           # Re-exports all shared models from portfolio.py + mf.py for convenience.
│   ├── portfolio.py          # Canonical home for all portfolio domain types: Leg, Strategy, DailySnapshot, Trade, TradeAction, Direction, ProductType, AssetType, PortfolioSummary. Monetary fields Decimal; P&L methods accept float|Decimal. PortfolioSummary refactored (AR-4): 16 flat cross-source fields + four typed Optional source references: mf_pnl (PortfolioPnL|None), dhan (DhanPortfolioSummary|None), nuvama_bonds (NuvamaBondSummary|None), nuvama_options (NuvamaOptionsSummary|None). Availability exposed via computed @property (dhan_available, nuvama_available, nuvama_options_available, mf_available). String-literal TYPE_CHECKING annotations on source fields avoid circular imports.
│   ├── mf.py                 # Canonical home for all MF domain types: MFTransaction, MFNavSnapshot, TransactionType, MFHolding. Migrated from src/mf/models.py (TODO 4, 2026-04-16).
│   └── options.py            # OptionLeg, OptionChainStrike, OptionChain (all frozen=True Pydantic). Source-agnostic field names. Upstox parser: parse_upstox_option_chain() in src/client/upstox_market.py. Dhan parser not implemented.
├── portfolio/
│   ├── CLAUDE.md             # Module context: Leg/Trade distinction, Decimal invariant, apply_trade_positions() overlay, strategy_name constraint
│   ├── store.py              # SQLite: strategies, legs, daily_snapshots, trades. Trades methods: record_trade (idempotent), get_trades (strategy/leg filter, date ASC), get_position (net qty + weighted avg buy price), get_all_positions_for_strategy (all leg_roles → (net_qty, avg_price, instrument_key)), ensure_leg (auto-persist trade-only legs to get a DB id for snapshot recording; idempotent). entry_price/ltp/close/underlying_price/price stored as TEXT for Decimal precision. WAL + upsert semantics.
│   ├── tracker.py            # PortfolioTracker: loads strategies, fetches LTPs, records snapshots. Trade overlay applied internally via _get_overlaid_strategy()/_get_all_overlaid_strategies() — compute_pnl, record_daily_snapshot, record_all_strategies all use trade-derived qty/entry_price automatically. Trade-only legs (e.g. LIQUIDBEES) with no DB id are auto-persisted via store.ensure_leg(). compute_pnl() returns StrategyPnL with Decimal total_pnl. Float LTPs from API converted via Decimal(str()) at boundary. apply_trade_positions() module-level pure function: overlays trade-derived qty/entry_price onto strategy Leg objects; appends trade-only legs as EQUITY/CNC; drops zero-net-qty legs.
│   ├── summary.py            # Pure computation (AR-4/5): _etf_current_value, _etf_cost_basis, _build_prev_prices, _compute_prev_mf_pnl, _compute_strategy_pnl_from_prices, _build_portfolio_summary. No I/O. TYPE_CHECKING guards replace object|None params; all 14 # type: ignore[union-attr] suppressions removed (AR-5). _build_portfolio_summary computes only cross-source aggregates (total_value/invested/pnl/day_delta) and passes source summary objects directly into PortfolioSummary — no dead intermediate extraction variables.
│   ├── formatting.py         # Pure formatting (AR-4): _format_protection_stats, _format_combined_summary. Depends on summary.py + PortfolioSummary. No I/O. All double-guards (if summary.dhan else Decimal("0") nested inside if summary.dhan_available blocks) removed — source object guaranteed non-None inside its available check by @property construction. mf_pnl guards retained (mf_available not checked before inline mf_pnl access).
│   ├── service.py            # SnapshotServiceProtocol (Protocol) + SnapshotService (concrete). persist_snapshots(strategy_name, strategy, snap_date, prices, greeks_map, underlying_price) builds DailySnapshot list and calls store.record_snapshots_bulk(). Auto-persists trade-only legs via store.ensure_leg() when leg.id is None. PortfolioTracker accepts SnapshotServiceProtocol for constructor injection.
│   └── strategies/
│       ├── __init__.py       # ALL_STRATEGIES registry
│       └── finideas/
│           ├── __init__.py
│           ├── ilts.py       # ILTS: 4 legs (EBBETF0431 + 3 Nifty options)
│           └── finrakshak.py # FinRakshak: 1 leg (protective put)
├── paper/
│   ├── CLAUDE.md             # Module context: paper_ prefix, Decimal invariant, idempotent record_trade
│   ├── __init__.py           # Package marker. Re-exports formatting helpers.
│   ├── constants.py          # Shared paths (portfolio.sqlite, NSE.json.gz) and risk params (LOT_SIZE=65, OVERLAY_ROLL_DTE=5).
│   ├── models.py             # PaperTrade (trade_date, action, quantity, price, leg_role) and PaperSnapshot.
│   ├── store.py              # PaperStore (SQLite): record_trade (idempotent), get_trades, delete_trade (rollback), get_all_strategy_names, record_daily_snapshot, get_prev_leg_snapshot (delta tracking).
│   ├── formatting.py         # Shared output helpers (fmt_inr, format_pnl_table, format_track_summary). Decimal precision; sign-aware.
│   ├── tracker.py            # PaperTracker: P&L computation and daily snapshot recording. Mirrors PortfolioTracker shape; operates on paper_trades/paper_nav_snapshots only. LTP floats converted at boundary via Decimal(str()).
│   ├── track_snapshot.py     # Core logic for producing the daily structured output for the three tracks. Async; dataclass-based snapshot type per track.
│   ├── metrics.py            # Pure metric functions: compute_nee() (Nifty-equivalent exposure), cost attribution helpers. NIFTYBEES_BETA_TO_NIFTY = 0.92.
│   ├── overlay_selector.py   # Overlay expiry selector — finds most cost-efficient protection leg across candidate expiries. Async; returns ranked candidates.
│   ├── proxy_monitor.py      # Track C delta monitor. ProxyDeltaMonitor tracks DITM call delta drift for the proxy track and flags rebalance triggers.
│   ├── chain_utils.py        # Shared option-chain lookup helpers used across paper entry/roll scripts
│   ├── _display.py           # Legacy labels (BASE_LABELS, OVERLAY_LABELS) and hedge_verdict. Kept for backward compat with older snapshot scripts.
│   └── _utils.py             # Paper-local utilities: safe_float(val, default) — converts any value to float without raising.
├── strategy/
│   ├── CLAUDE.md             # Module context: BrokerClient protocol, factory pattern, action dispatch
│   ├── __init__.py           # Package marker
│   ├── protocol.py           # PaperStrategy protocol, SignalEvent, ApprovedAction, LegSpec models
│   ├── ic_expiry_config.py   # ICExpiryConfig frozen dataclass; CONFIGS dict with 4 presets (weekly/monthly/leaps/yearly)
│   ├── ic_expiry_config_v2.py # IronCondorV2ExpiryConfig frozen dataclass; delta-based config (D1/D2/D3/D4); CONFIGS_V2 dict (monthly only, Phase 1)
│   ├── ic_nifty_v1.py        # IronCondorV1 strategy class: 15Δ/10Δ entry, fixed wing points, roll-wing only adjustment
│   ├── ic_nifty_v2.py        # IronCondorV2 strategy class: 25Δ/22Δ entry, 10Δ wings with floors, partial vertical roll, DTE-tiered exits; council ruling 2026-06-26
│   ├── csp_nifty_v1.py       # CSPNiftyV1 strategy: always-open short call selling with automated roll/re-entry
│   ├── cc_overlay_v1.py      # CCOverlayV1 strategy: covered call protective overlay with delta gates
│   ├── pp_overlay_v1.py      # PPOverlayV1 strategy: protective put rebalance overlay (IVR ≤ 0.60 gate)
│   ├── collar_overlay_v1.py  # CollarOverlayV1 strategy: short call + long put atomic collar
│   ├── nifty_track_comparison_v1.py # NiftyTrackComparisonV1: manual-approval multi-leg comparison strategy
│   ├── exit_signals.py       # ExitSignalEngine: static rule engine for CSP/CC/PP/Collar exit signals (INFO/WARN/ACTION)
│   ├── overlay_closer.py     # OverlayCloser: atomic multi-leg close orchestrator (record_trades via store)
│   ├── monitor.py            # StrategyMonitor daemon: polls registered strategies, routes signals, handles approvals
│   ├── executor.py           # PaperExecutor: action dispatch + PaperFillSimulator (VIX-regime slippage)
│   ├── reentry_mixin.py      # ReEntryMixin: three-gate re-entry check (DTE/IVR/position)
│   ├── auto_close.py         # EOD auto-close orchestrator for overlays via OverlayCloser; status → ACTED
│   ├── roll_utils.py         # Shared helpers: find_strike_by_delta, apply_liquidity_gate
│   ├── csp_roll_executor.py  # Legacy CSP roll executor (retained for compatibility)
│   ├── ic_close_executor.py  # close_ic_legs(): shared auto-close persistence helper for IronCondorV1/V2 — batch LTP fetch + atomic closing-trade writes; settlement-fallback for missing LTP on expiry day
│   ├── _price_utils.py       # Shared price/LTP resolution helpers used by executor.py + ic_close_executor.py
│   └── profit_lock_engine.py # ProfitLockEngine: stateless 3-zone profit-lock evaluator; ProfitLockState + ProfitLockDecision frozen dataclasses; floor formula max(W,W)+D_cum+D_lock+K ≤ 0.75×C₀; Zone 1 log-only, Zone 2 wing contraction to ~19Δ, Zone 3 CLOSE_FULL; council ruling 2026-06-27
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
│   ├── models.py             # Frozen dataclasses: DhanHolding (EQUITY/BOND, LTP, cost/pnl properties), DhanPortfolioSummary (split by classification, Decimal fields, day deltas). Also: DhanOptionPosition (security_id/trading_symbol/exchange_segment/product_type/position_type/buy_qty/sell_qty/net_qty/buy_avg/sell_avg/realized_pnl/unrealized_pnl), DhanOptionsSummary (realized_pnl/unrealized_pnl/total_pnl/charges/brokerage/position_count/snapshot_ts; net_pnl property), DhanFundLimit (available_balance/utilized_amount/collateral_amount/withdrawable_balance/snapshot_ts).
│   ├── reader.py             # Pure + HTTP functions. fetch_holdings_raw/fetch_ltp_raw (I/O). classify_holding, build_dhan_holdings (filter+classify), build_security_id_map, enrich_with_ltp (Dhan API — paid tier), enrich_with_upstox_prices (preferred), upstox_keys_for_holdings, build_dhan_summary (pure). fetch_dhan_holdings() + fetch_dhan_portfolio() orchestrators.
│   ├── positions.py          # Intraday Dhan options position fetching, parsing, and formatting. I/O: fetch_positions_raw, fetch_fund_limit_raw. Pure: parse_option_positions, filter_intraday_options (keeps NSE_FNO INTRADAY+MARGIN), compute_charges (exchange/SEBI/stamp/STT/GST; ITM expiry STT path), build_options_summary, parse_fund_limit, format_options_section (Telegram). Decimal(str(v)) enforced throughout. Maps Dhan's 'availabelBalance' typo explicitly.
│   └── store.py              # DhanStore: dhan_holdings_snapshots table. record_snapshot (upsert), get_snapshot_for_date, get_prev_snapshot (MAX date < d, keyed by ISIN).
├── market_calendar/
│   ├── __init__.py           # Package marker.
│   ├── data/nse_2026.yaml    # NSE 2026 equity holiday list — version-controlled config (src/ not data/ because data/ is gitignored). Update each January.
│   └── holidays.py           # NSE equity holiday detection. load_holidays(year) → frozenset[date] (cached, fail-open on missing YAML). is_trading_day(d) → bool (weekday AND not in holiday set). prev_trading_day(d) → date (walks back to nearest prior trading day).
├── intraday/
│   ├── __init__.py           # Package marker
│   └── market_store.py       # IntradayMarketStore: broker-agnostic SQLite store for intraday_market_snapshots table. record_market_snapshot(timestamp, nifty_spot, india_vix) — one row per tracker tick; timestamp must be timezone-aware. purge_old(days=30). get_latest() → (nifty_spot, india_vix) | None. get_latest_vix_today() → float | None — guards against stale prior-session rows using IST date comparison. Shared by Dhan + Nuvama intraday tracker orchestrator.
├── risk/
│   ├── __init__.py           # Package marker
│   ├── models.py             # PortfolioDelta frozen dataclass: options_delta_lots, niftybees_delta_lots, total_delta_lots, warning_breached, cap_breached, as_of. Computed on demand — never stored in DB.
│   ├── delta_tracker.py      # PortfolioDeltaTracker: aggregate_delta(paper_positions, nifty_spot, lot_size) → PortfolioDelta. Options-only thresholds warning=0.75/cap=1.0 lots; combined thresholds warning=1.5/cap=2.0 lots; parameterised via constructor. CE/futures = net_qty/lot_size; PE = -net_qty/lot_size; NiftyBees = qty×avg_cost/(spot×lot_size).
│   └── entry_gate.py         # check_entry_allowed(delta, action) → (allowed, message). Protective entries always allowed; cap breached → block; warning breached → allow with message.
├── instruments/
│   ├── __init__.py           # Package marker
│   ├── lot_size.py           # DateAwareLotSizeResolver: resolves market lot sizes for underlying symbols (like NIFTY, BANKNIFTY) based on date.
│   ├── strike_selector.py    # Core strike selection logic (filter, gate, rank) extracted from find_strike_by_delta CLI.
│   └── lookup.py             # Offline BOD search (NSE.json.gz). CLI: --find-legs mode. search() uses ranked exact>prefix>fuzzy scoring via _score_query()/_best_score() (rapidfuzz; difflib fallback). min_score param added.
├── notifications/
│   ├── CLAUDE.md             # Module context: non-fatal contract, build_notifier() → None, HTML parse_mode
│   ├── __init__.py           # Package marker.
│   ├── protocol.py           # NotifierProtocol — abstracts the notification sink for testability
│   ├── telegram.py           # TelegramNotifier: fire-and-forget sendMessage via raw requests (HTML parse_mode, <pre> block). build_notifier() returns None when env vars absent. send() never raises — catches Exception broadly, logs WARNING, returns False.
│   └── telegram_gateway.py   # TelegramGateway: council-free approval request dispatch + inbound callback polling + auth guard (chat-ID allowlist) + timeout scan for stale pending approvals
├── nuvama/
│   ├── __init__.py           # Package marker
│   ├── models.py             # Frozen dataclasses: NuvamaBondHolding (isin/qty/avg_price/ltp/chg_pct/hair_cut; cost_basis/current_value/pnl/pnl_pct/day_delta properties), NuvamaBondSummary (total_value/basis/pnl/pnl_pct/total_day_delta). All BOND classification. NuvamaOptionPosition (trade_symbol/instrument_name/net_qty/avg_price/ltp/unrealized_pnl/realized_pnl_today). NuvamaOptionsSummary (snapshot_date/positions tuple/total_unrealized_pnl/total_realized_pnl_today/cumulative_realized_pnl/intraday_high/low/nifty_high/low; net_pnl property = unrealized + cumulative_realized).
│   ├── reader.py             # parse_bond_holdings() (pure, joins positions dict for avg_price, skips _EXCLUDE_ISINS + missing positions with WARNING, catches InvalidOperation), build_nuvama_summary() (pure aggregation), fetch_nuvama_portfolio() (I/O orchestrator). _extract_rms_hdg() handles both resp.data.rmsHdg and eq.data.rmsHdg response paths.
│   ├── options_reader.py     # parse_options_positions() (pure) — filters OPTIDX/OPTSTK from NetPosition() JSON, resolves avg_price from cfAvgSlPrc/cfAvgByPrc, skips non-option rows and malformed records. build_options_summary() (pure) — aggregates positions list + cumulative_realized_pnl_map + optional intraday/nifty bounds → NuvamaOptionsSummary.
│   ├── protocol.py           # NuvamaClient protocol. Abstracts the Nuvama SDK (Holdings, NetPosition) for testability.
│   ├── mock_client.py        # MockNuvamaClient: offline NuvamaClient implementation for unit tests (AR-9). Lives in src/nuvama/ (not tests/) so scripts + integration tests can import without coupling to the test tree. Same convention as src/client/mock_client.py.
│   └── store.py              # NuvamaStore: nuvama_positions (ISIN PK, avg_price TEXT, qty, label — seed once), nuvama_holdings_snapshots (UNIQUE(isin, snapshot_date) upsert; get_snapshot_for_date returns dict[str,dict] with qty/ltp/current_value keys — AR-6; record_all_snapshots uses executemany in single transaction — AR-7; get_prev_total_value() calendar-agnostic), nuvama_options_snapshots (PRIMARY KEY (trade_symbol, snapshot_date) upsert — record_all_options_snapshots atomic via executemany — AR-7; get_cumulative_realized_pnl aggregates realized_pnl_today across all historical rows per symbol via single SQL GROUP BY — AR-8), nuvama_intraday_snapshots (record_intraday_positions/purge_old_intraday 30-day retention/get_intraday_extremes — sums unrealized+realized per timestamp, returns max_pnl/min_pnl/nifty_high/nifty_low).
├── utils/
│   ├── __init__.py           # Package marker.
│   ├── logging.py            # setup_logging(*, json, level): configures structlog with shared processors (contextvars merge, log level, logger name, ISO timestamp). JSON renderer in prod (upstox_env == "prod"); ConsoleRenderer otherwise. Wired at entry point of every script.
│   └── number_formatting.py  # fmt_inr(value, *, decimals, sign, width) — Indian numbering system (Lakhs/Crores). _group_indian() private helper. No I/O or dependencies beyond stdlib.
├── config.py                 # Settings(BaseSettings) singleton (pydantic-settings). Declares every env var across src/ and scripts/: Upstox tokens, Telegram, Nuvama, Dhan, data paths. Loads from .env + environment. Import the settings singleton — never call os.getenv() directly.
├── db.py                     # Shared SQLite context manager — WAL mode, row_factory, FK enforcement, auto commit/rollback.
└── client/
    ├── CLAUDE.md             # Module context: BrokerClient protocol rule, 4 implementations, active constraints
    ├── exceptions.py         # Custom exception hierarchy: BrokerError → AuthenticationError, RateLimitError, DataFetchError (→ LTPFetchError), OrderRejectedError (→ InsufficientMarginError), InstrumentNotFoundError.
    ├── protocol.py           # BrokerClient + MarketStream protocols. Sub-protocols: MarketDataProvider, OrderExecutor, PortfolioReader. Stub type aliases (= Any) for all Pydantic models not yet in src/models/.
    ├── upstox_market.py      # Sync requests client. V3 LTP endpoint. Pipe→colon key remap. Raises LTPFetchError on HTTP error / empty data.
    ├── upstox_live.py        # UpstoxLiveClient: production BrokerClient. Delegates get_ltp + get_option_chain to UpstoxMarketClient (Analytics Token). Order execution raises NotImplementedError (static IP blocked). Portfolio read raises NotImplementedError (Daily OAuth token required). Expired instruments + historical candles raise NotImplementedError. get_order_margin() (2026-07-22): pre-trade margin calculator via POST /v2/charges/margin.
    ├── mock_client.py        # MockBrokerClient: offline BrokerClient implementation — deterministic fakes for all protocol methods, including a netting-benefit factor for get_order_margin() BUY+SELL baskets
    └── factory.py            # Composition root. create_client(env) → BrokerClient. env: "prod" → UpstoxLiveClient (UPSTOX_ANALYTICS_TOKEN), "sandbox" → UpstoxLiveClient (UPSTOX_SANDBOX_TOKEN), "test" → MockBrokerClient. ONLY file in src/ that imports concrete clients.

scripts/
├── __init__.py           # Package marker
├── pipeline/             # cron-driven; produces data or snapshots; shared across strategies
│   ├── __init__.py       # Package marker
│   ├── upstox_chain_snapshot.py # EOD option chain snapshot cron. Writes to PyArrow Parquet.
│   ├── upstox_chain_intraday.py # 5-min intraday option chain snapshot. Writes to Parquet.
│   ├── gamma_daily_watch.py     # Greeks monitoring from chain snapshots.
│   ├── bhavcopy_bootstrap.py    # Resumable bulk NSE bhavcopy download 2016–present.
│   └── refresh_vix.py           # India VIX ingestion refresh cron — wraps src/backtest/vix_ingest.py, resumable gap-fill.
├── lookup/               # on-demand queries; called by humans or entry scripts
│   ├── __init__.py       # Package marker
│   ├── find_strike_by_delta.py  # CLI: live Nifty option chain → filter by |delta| range → strike/IV/key table. Prints ready-to-paste record_paper_trade.py commands. --expiry and --date use type=date.fromisoformat. Added --track shortcut.
│   ├── find_overlay_strikes.py  # overlay-specific strike finder.
│   └── instrument_lookup.py     # Offline BOD search (NSE.json.gz). CLI: --find-legs mode. search() uses ranked exact>prefix>fuzzy scoring.
├── record/               # human-facing write CLIs; one action per invocation
│   ├── __init__.py       # Package marker
│   ├── record_paper_trade.py    # Automated CSP/overlay trade recorder. Resolves instrument keys/prices from live chain or existing DB position. Dry-run by default.
│   └── record_trade.py          # CLI for recording future trades. Validates via Trade model; inserts; prints updated net position + avg price. --dry-run prints without touching DB. --strategy takes DB strategy name (e.g. finideas_ilts, not ILTS).
├── strategies/           # strategy-specific scripts; one subfolder per strategy
│   ├── __init__.py       # Package marker
│   ├── csp/
│   │   └── __init__.py   # Package marker only — paper_csp_roll.py retired 2026-07 (PA2); CSP rolls now backbone-managed via CSPNiftyV1.apply_action + PaperExecutor
│   ├── three_track/
│   │   ├── __init__.py   # Package marker
│   │   ├── paper_3track_entry.py    # Base leg entry for 3-Track comparison. Auto-selects DITM CE proxy + futures + NiftyBees. --confirm required to write.
│   │   ├── paper_3track_overlay.py  # Live-fetch overlay entry for all 3 tracks (spot/futures/proxy). PP/CC/collar types. CC permanently blocked on paper_nifty_futures (synthetic short put). _check_existing_overlay detects open SELL positions correctly. Atomicity: failed writes rolled back via store.delete_trade(). Imports: ALL_TRACKS, _ACTION_FOR_ROLE, _OPTION_TYPE_FOR_ROLE, _build_trade, _collect_expiry_candidates, _fetch_candidates_for_expiries, _select_best_candidate.
│   │   ├── paper_3track_overlay_entry.py # overlay-specific entry script.
│   │   │                                  # (paper_3track_overlay_roll.py retired 2026-07 (PA2) — 3-track overlay rolls now backbone-managed via NiftyTrackComparisonV1.apply_action + PaperExecutor)
│   │   └── paper_3track_snapshot.py      # Canonical EOD cron for 3-track comparison (15:45 IST). Live spot fetch (--spot to override). Per-leg delta-from-yesterday via get_prev_leg_snapshot. Writes paper_nav_snapshots + paper_leg_snapshots (--no-save for dry-run). _hedge_verdict shows overlay protection ratio. Uses format_track_summary() for summary-first reporting; --verbose for leg details.
│   ├── ic/
│   │   ├── __init__.py   # Package marker
│   │   ├── ic_entry_gates.py    # Shared pre-entry gate helpers (check_duplicate, resolve_ivr w/ VIX-staleness guard, resolve_expiry, capture_entry_margin) used by both V1 and V2 entry scripts.
│   │   ├── paper_ic_entry.py    # Config-driven IC entry helper for all four V1 variants (weekly/monthly/leaps/yearly); IVR/duplicate/DTE/liquidity gates (portfolio-delta gate removed 2026-07-03 — IC entries judged in isolation); --dry-run default.
│   │   ├── paper_ic_entry_v2.py # V2-only entry helper — delta-based 10Δ long-wing placement via live chain scan, long_wing_min_premium floor enforced, shares gates via ic_entry_gates.py.
│   │   ├── paper_ic_snapshot.py # EOD audit cron for all IC variants (V1 loop over all four + V2 loop over CONFIGS_V2); per-leg Greeks snapshot; ROI-on-margin line; Telegram summary; cron 45 15 * * 1-5.
│   │   └── paper_ic_monthly_comparison.py # EOD V1 vs V2 monthly comparison cron; ICMonthlyStats dataclass; side-by-side Telegram report (entry credit / captured % / deltas / P&L / profit-lock zone / adjustments); cron 45 15 * * 1-5.
│   └── cc_calibration/   # NiftyBees lot-sizing probe (retire after 3 cycles)
│       ├── __init__.py   # Package marker
│       ├── paper_cc_entry.py
│       └── paper_cc_roll.py
├── portfolio/            # live portfolio P&L — not paper, not strategy-specific
│   ├── __init__.py       # Package marker
│   ├── backup_db.py      # Online SQLite backup cron — copies data/portfolio/portfolio.sqlite via the sqlite3 backup API (safe under WAL).
│   ├── daily_snapshot.py # Thin I/O orchestration only. Live mode: holiday guard (is_trading_day) exits early on NSE holidays before any API call; fetches LTPs, records snapshots, prints P&L, sends Telegram (non-fatal). Historical mode (--date YYYY-MM-DD): reads stored snapshots, computes P&L offline — no holiday guard, no API call. Pure computation in src/portfolio/summary.py; pure formatting in src/portfolio/formatting.py. Live mode: create_client(UPSTOX_ENV) — UPSTOX_ENV=test → MockBrokerClient. _historical_main reconstructs NuvamaBondHolding objects using actual qty+ltp from NuvamaStore.get_snapshot_for_date() (AR-6 — no more qty=1 stub).
│   ├── morning_nav.py    # MF NAV backfill cron (09:15 IST, weekdays). Fetches AMFI and upserts MFNavSnapshot for prev_trading_day(today) — fixes stale T-2 NAV written by the 15:45 daily_snapshot run (AMFI not yet published at that time). --date override for manual recovery. Exit 0/1. Cron: 15 9 * * 1-5.
│   ├── paper_snapshot.py # EOD mark-to-market for CSP Nifty. Dry-run by default; --no-dry-run to write. Integrated format_pnl_table() for standardized output.
│   └── roll_leg.py       # CLI for atomic option leg rolls. Closes old leg + opens new leg in a single DB transaction. Pure _build_trades() validates both Trade objects before any DB write. --old-*/--new-* flag pairs. --dry-run. Calls store.record_roll().
├── intraday/             # intraday monitoring crons (*/15 9-15 * * 1-5)
│   ├── __init__.py       # Package marker
│   ├── intraday_tracker.py # combined Dhan+Nuvama orchestrator.
│   ├── nuvama_intraday_tracker.py # Invoked every 5 minutes by Cron (*/5 9-15 * * 1-5). Holiday guard (is_trading_day) exits early on NSE holidays. Fetches Nuvama NetPosition() for options positions + Nifty 50 spot from Upstox batch LTP. Records per-leg intraday state via store.record_intraday_positions() (auto-purges rows > 30 days). os._exit() required — Nuvama SDK spawns a non-daemon background thread that hangs sys.exit().
│   └── dhan_intraday_tracker.py
├── seed/                 # one-time DB seeds; never in cron
│   ├── __init__.py       # Package marker
│   ├── seed_mf_holdings.py # One-time CLI. Inserts 11 INITIAL MF transactions. Idempotent. --dry-run flag.
│   ├── seed_nuvama_positions.py # One-time seed of Nuvama bond cost-basis. build_positions() pure (6 instruments). seed_positions() I/O wrapper. --write (required to commit), --overwrite, --db. Dry-run by default.
│   ├── seed_portfolio.py
│   └── seed_trades.py    # Idempotent backfill of all finideas_ilts + finrakshak executions as Trade rows. build_trades() (pure) + seed_trades() (I/O). --dry-run flag. 7 trades total. strategy_name must match strategies table (finideas_ilts, finrakshak).
├── council/              # council workflow tooling; used during planning, not trading
│   ├── __init__.py       # Package marker
│   ├── ask_council.py
│   └── council_templates/
├── dev/                  # diagnostics, smoke tests, one-off migrations
│   ├── __init__.py       # Package marker
│   ├── send_test_telegram.py # Smoke-test script. Reads TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID from .env, sends a sample P&L message. Exit code 0/1. Run before first cron to verify credentials.
│   ├── validate_strategy_spec.py # strategy spec linter.
│   ├── probe_nuvama_schema.py # Diagnostic script (not production). Dumps all rmsHdg fields from live Holdings() response.
│   ├── migrate_strike_to_text.py
│   ├── migrate_add_closed_state.py    # One-off migration: adds CLOSED to TradeState-related schema.
│   ├── migrate_exit_events_decimal.py # One-off migration: paper_exit_events numeric columns → Decimal-safe TEXT.
│   ├── migrate_paper_action_audit.py  # One-off migration: adds action-audit columns/table for paper trade actions.
│   ├── migrate_paper_strategies.py    # One-off migration: paper_strategies table schema updates (e.g. proxy_delta_breach_count).
│   ├── migrate_paper_trades_state.py  # One-off migration: adds TradeState column to paper_trades.
│   ├── migrate_paper_trades_unique.py # One-off migration: uniqueness constraint fix on paper_trades.
│   ├── check_ic_margin.py    # Diagnostic: queries live/mock order margin for an IC leg basket.
│   ├── cleanup_cc_collar_dedup.py # One-off cleanup: dedupes overlapping CC/Collar paper positions from a historical bug.
│   ├── generate_3track_viz.py # Generates a visualization/report of the 3-track comparison history.
│   ├── test_api_version.py
│   ├── paper_track_snapshot.py # Legacy snapshot script (preserved for compatibility).
│   ├── verify_analytics.py     # Smoke-tests LTP, option chain, Greeks, historical candles via Analytics Token. Moved from src/analytics/ (SS1).
│   └── sandbox_order_lifecycle.py # Place → Modify → Cancel via V3 Order API (sandbox=True). Moved from src/sandbox/ (SS1).
├── healthcheck.py         # Dead man's switch for EOD cron validation (top-level, not under daemon/). Trading-day guard, DB/snapshot/VIX recency checks, disk space. Silent on pass; Telegram alert + exit 1 on failure. Cron: 30 16 * * 1-5.
├── position_health_check.py # Standalone position/Greeks sanity-check cron — flags stale or missing Greeks/LTP on open paper positions.
├── eod_summary.py         # EOD P&L summary cron — Telegram digest across all strategies. (Moved out of scripts/daemon/ — that subfolder no longer exists.)
├── pre_market_brief.py    # Pre-market summary cron. (Moved out of scripts/daemon/ — that subfolder no longer exists.)
├── monitor_daemon.py      # Monitor daemon main loop (StrategyMonitor host process). (Moved out of scripts/daemon/ — that subfolder no longer exists.)
├── start_monitor.py       # Launcher for monitor_daemon.py. (Moved out of scripts/daemon/ — that subfolder no longer exists.)
└── stop_monitor.py        # Graceful shutdown for monitor_daemon.py. (Moved out of scripts/daemon/ — that subfolder no longer exists.)

.claude/
├── settings.json             # PreToolUse hook: warns on Read targeting src/ or scripts/
├── settings.local.json       # Local permissions allowlist (not committed)
├── hooks/
│   └── guard_src_reads.sh    # Hook script: prints graph decision tree reminder, exit 0 (warn only)
├── skills/commit/SKILL.md    # NiftyShield commit format (disable-model-invocation: true — manual only)
└── agents/
    ├── code-reviewer.md      # Opus: checks Decimal, BrokerClient protocol, type hints, async correctness
    ├── test-runner.md        # Haiku: runs python -m pytest tests/unit/ and reports
    ├── greeks-analyst.md     # Sonnet: OptionChain model design, _extract_greeks_from_chain(), fixture analysis
    ├── roll-validator.md     # Opus: pre-roll position check, Trade model integrity, DB atomicity — hard deadline 2026-06-30
    └── options-strategist.md # Opus: delta-neutral sizing, IC/strangle design, risk module logic (src/risk/ scope)

docs/archive/
├── CODE_REVIEW_2026-04-04.md              # Full codebase code review from foundation sprint
├── daily_snapshot_old_2026-04-12.py       # Pre-factory.py version of daily_snapshot script
├── JIRA_enterprise_plan_2026-04-12.md     # Speculative SQLAlchemy/loguru/UoW architecture plan — never activated
├── PROJECT_INSTRUCTIONS_DRAFT_2026-04-12.md # Claude Desktop instructions draft — superseded by live project settings
└── PROMPT_TEMPLATE_2026-04-12.md          # Session prompt template — superseded by INSTRUCTION.md

tests/
├── unit/
│   ├── portfolio/
│   │   ├── __init__.py
│   │   ├── test_trade_models.py    # 20 tests: TradeAction enum, Trade valid/invalid construction, qty/price validators, frozen=True, Decimal precision
│   │   ├── test_trade_store.py     # 25 tests: record_trade CRUD, idempotency, get_trades filters + ordering, get_position (BUY-only, SELL-only, mixed, weighted avg, ignores SELL price, schema coexistence)
│   │   ├── test_seed_trades.py     # 13 tests: build_trades shape, strategy/leg/key correctness, BUY+SELL actions, idempotency (3×), EBBETF0431 weighted avg, NIFTY_JUN_PE short position
│   │   ├── test_roll_leg.py        # 10 tests: _build_trades happy path (fields, notes, leg independence), validation errors (zero/negative qty, zero price)
│   │   └── test_telegram_formatting.py  # 1 test: _format_combined_summary smoke test — fully populated cross-source PortfolioSummary; asserts section presence + per-section numeric output (day deltas, total value)
│   └── mf/
│       ├── __init__.py       # Package marker
│       ├── test_models.py    # 25 tests: MFTransaction + MFNavSnapshot valid/invalid/edge cases
│       ├── test_store.py     # 33 tests: CRUD, upsert idempotency, date range queries, schema coexistence. get_holdings tests updated for MFHolding return type.
│       ├── test_nav_fetcher.py  # 20 tests: AMFI parse logic, fixture-driven, fully offline. Updated to correct AMFI codes.
│       ├── test_tracker.py   # 27 tests: pure P&L math + mocked store/fetcher orchestration
│       ├── test_seed.py      # 20 tests: seed transaction shape, verified AMFI code set, idempotency, Decimal precision, total_invested sum
│       ├── test_daily_snapshot_mf.py   # 12 tests: MF wire-up path — schema coexistence, full seed→snapshot→aggregate, empty holdings, nav failure
│       └── test_daily_snapshot_helpers.py  # 30 tests: _etf_current_value + _etf_cost_basis helpers; PortfolioSummary construction with mf/dhan/nuvama source objects; mf_available/dhan_available/nuvama_available @property behaviour; total_value/invested/pnl aggregation across sources. Assertions use direct field access (result.mf_pnl is None / result.dhan.equity_value == ...) — no conditional ternaries.
└── instruments/
    ├── __init__.py
    ├── test_lot_size.py      # 3 tests: DateAwareLotSizeResolver happy paths (Nifty, Bank Nifty) and edge cases (ETFs, fallback to 1)
    └── test_lookup.py        # 27 tests: _score_query tiers, _best_score field selection, InstrumentLookup.search ranking/filters/min_score/edge cases
└── auth/
    ├── __init__.py
    ├── test_nuvama_login.py   # 16 tests: build_login_url, extract_request_id (full URL + bare token + whitespace), initialize_session (APIConnect args, parent dir creation, is_production flag), save_settings_path (write + upsert), login flow (missing creds, empty input, full flow). autouse clean_env fixture prevents dotenv leakage.
    ├── test_nuvama_verify.py  # 17 tests: parse_holdings (flat list, whitespace strip, multiple records, empty, invalid JSON, missing key), load_api_connect (missing creds, settings file missing, happy path), verify (true/false on valid/invalid response, config error, api exception, stdout count). autouse clean_env fixture.
    ├── test_dhan_login.py     # 13 tests: build_login_url, validate_token (strip/empty/whitespace), save_token (write/upsert/preserve), login flow (missing client_id, empty input, full flow, whitespace token). autouse clean_env fixture.
    └── test_dhan_verify.py    # 18 tests: _build_headers, load_dhan_credentials (happy/missing_id/missing_token/whitespace), fetch_profile (happy/401), fetch_holdings (list/empty/dict), parse_holdings (multiple/empty/missing/malformed), verify (success/missing_creds/401/stdout). autouse clean_env fixture.
└── market_calendar/
│   ├── __init__.py
│   └── test_holidays.py      # 31 tests: load_holidays (happy path, missing file, cache, malformed entries), is_trading_day (weekdays/weekends/holidays/fail-open), prev_trading_day (normal/weekend-skip/holiday-skip/fail-open), real 2026 YAML smoke tests
└── fixtures/
    ├── responses/            # 7 JSON fixtures recorded from real APIs (LTP, option chain, Greeks, candles)
    └── amfi/
        └── nav_slice.txt     # Realistic AMFI flat file slice: 11 valid schemes with correct AMFI codes, N.A. line, malformed line
```
