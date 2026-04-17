# NiftyShield — Planner

> Forward-looking roadmap. Read when starting new feature work or evaluating architecture changes.
> Distinct from TODOS.md (immediate actionable items) — this covers multi-sprint thinking,
> blocked items, and design decisions being evaluated.

---

## Current Sprint (April 2026)

### Next up: Greeks capture
- Define `OptionChain` Pydantic model using `tests/fixtures/responses/nifty_chain_2026-04-07.json`
- Implement `_extract_greeks_from_chain()` in `src/portfolio/tracker.py`
- Fix the option chain API call (must use `NSE_INDEX|Nifty 50`)
- Store Greeks columns in `daily_snapshots` (columns exist, currently null)
- Tests: fixture-driven, fully offline

---

## Near-Term (May–June 2026)

### FinRakshak effectiveness tracking
Automated monthly report: FinRakshak P&L vs MF portfolio drawdown.
`finrakshak_day_delta` already in `PortfolioSummary` — query over snapshot history.

### P&L visualization
Matplotlib chart from `daily_snapshots` time series (component breakdown over time).
Start once 4+ weeks of snapshot data available.
`snapshot_date` field already in `PortfolioSummary` — ready to query.

---

## Medium-Term (Q3 2026 — post static IP)

### Order execution layer (`src/execution/`)
Unblocked when static IP is provisioned.
- `place_order`, `modify_order`, `cancel_order` on `UpstoxLiveClient`
- GTT orders for SL management
- Pre-order margin validation via `src/risk/`
- All logic already designed against `BrokerClient` protocol — implementation is straightforward once unblocked

### Risk module (`src/risk/`)
- Margin checks (pre-order validation)
- Position sizing for short strangles / Iron Condors
- Delta monitoring and rebalance triggers
- Depends on: Greeks capture being live + order execution unblocked

### Strategy engine (`src/strategy/`)
- Signal generation for NiftyBees price action (demand/supply zones)
- Entry/exit logic for delta-neutral positions
- Connects to websocket streaming for real-time triggers

### Websocket streaming (`src/streaming/`)
- `live.py`: Upstox websocket handler
- `recorder.py`: `StreamRecorder` — captures live ticks to Parquet
- `replay.py`: `ReplayMarketStream` — replays from Parquet at configurable speed

---

## Long-Term (Q4 2026+)

### Backtesting engine (`src/backtest/`)
- **Unblocked:** Evaluated APIs and decided to adopt the paid DhanHQ Data API (₹400/month) for expired options due to its superior ATM-relative querying model.
- Prerequisite: Spin up a PostgreSQL + TimescaleDB container for storing the daily option chain OHLC data, as SQLite will not scale for 5 years of 1-minute deep tick data.
- Interim: Continue using the NSE option chain CSV dumps for structural testing if necessary, but Dhan Data API gives a direct path to production-grade data lakes.
- Data models already designed; need to map Dhan `POST /v2/charts/rollingoption` payload formats into internal Pydantic standards.
- **Reference implementation available:** See "quant-4pc-local reference" section below — backtest engine + IC strategy scaffold already designed and tested. Port rather than build from scratch.

---

## quant-4pc-local Reference (local repo, not committed to NiftyShield)

> Location: `quant-4pc-local/` inside the NiftyShield folder (gitignored).
> Analysed: 2026-04-15. A prior Dhan-focused research project targeting weekly Iron Condors.
> Left off at M1 (data ingestion done, M2 backtest engine scaffolded). No live execution.

### What to port when starting `src/backtest/` and `src/strategy/`

**1. Backtest engine — `quant-4pc-local/src/backtest/engine.py`** (highest priority)
Port almost as-is into `src/backtest/engine.py`. Design is fully compatible with NiftyShield conventions:
- `Strategy` Protocol: `setup(df) / on_day(ctx: DayContext) / teardown() → BacktestResult`
- `DayContext` dataclass: date, row, idx, total_days, extras — minimal and explicit
- `BacktestEngine`: `load_data(df)`, `run()`, `report(result)` — simple daily loop
- Only NiftyShield-specific wiring needed: make the data loader consume Parquet/DuckDB candle format

**2. Iron Condor strategy — `quant-4pc-local/src/strategies/iron_condor.py`**
Port into `src/strategy/iron_condor.py` when starting the IC/strangle backtest:
- `IronCondorConfig` (frozen dataclass): target_dte, wing_width, entry_day_of_week, credit_target_pct, stop_loss_pct, risk_cap_pct, margin — all knobs explicit
- `IronCondorState`: open_position, trades, pnl
- `IronCondorStrategy`: entry on weekday, TP/SL exit, risk cap check, pluggable pricers via `price_ic` + `m2m_ic` callbacks — allows toy pricers offline and real OC MTM when data is available
- `risk_cap_pct + margin` fields map directly to `src/risk/` design in `options-strategist.md`

**3. Data normalisation — `quant-4pc-local/src/data/client.py` → `DhanDataClient._normalize_df()`**
Strengthen `src/dhan/reader.py` with this when cleaning up the Dhan data path:
- Five fast-path timestamp format detectors (ISO, dd-mm-yyyy, etc.)
- 1% bad-row tolerance before raising (vs hard fail)
- Vectorised OHLC coercion with threshold-aware drop
- Volume coerce + fillna(0) pattern

**4. Retry/backoff pattern — `quant-4pc-local/scripts/check_dhan_connection.py` → `DhanAuthService.check_profile()`**
Extract the exponential backoff loop (configurable retries 0–5, base sleep * 2^attempt) into a shared utility when building the rate-limiter middleware.

### What NOT to port
- `dhanhq>=2.0.0` SDK — NiftyShield uses raw `requests` intentionally (no SDK coupling)
- Feature engineering + ML stubs — empty; nothing to take
- Index/VIX data pipelines — out of scope
- M0 boilerplate (pytest.ini, Makefile, commit conventions) — NiftyShield's own are more mature

### Rate limiter + retry middleware
- Token bucket decorator for all API calls
- Exponential backoff with jitter for retryable errors (429, 5xx, timeout)
- Idempotent order placement (correlation IDs)
- Build when moving to live order execution

---

## Blocked Items

| What | Blocked By | ETA |
|---|---|---|
| Order execution (place/modify/cancel) | Static IP not provisioned | Unknown |
| GTT orders, webhooks | Static IP not provisioned | Unknown |
| Historical candles (expired instruments) | Paid Upstox subscription | Unknown |
| Expired option contracts | Paid Upstox subscription | Unknown |
| Portfolio/positions read on `UpstoxLiveClient` | Daily OAuth token not wired | When needed |

---

## Design Decisions Being Evaluated

**Replace `UpstoxMarketClient` (sync `requests`) with full async `aiohttp` client:**
Pros: eliminates the sync/async mismatch, removes the only sync network call, cleaner `UpstoxLiveClient` delegation.
Cons: larger change, breaks existing `test_client.py` tests, needs aiohttp fixture pattern.
Status: deferred until order execution is unblocked (natural refactor moment).

**Nuvama order execution:**
Currently read-only. Evaluate whether to wire order execution for Nuvama's bond/NCD legs
(would bypass Upstox static IP constraint for non-F&O legs).
Status: deferred — assess after Upstox order execution is live for comparison.
