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

### Paper trade entry helper: strike selection by delta
`scripts/find_strike_by_delta.py` — fetches live option chain, filters strikes by delta range, prints strike/premium/IV/key table. Closes the gap between "I want delta ~−0.20" and the `--price` + `--key` arguments required by `record_paper_trade.py`. Unblocked — all dependencies in place (`OptionChainStrike`, `parse_upstox_option_chain`, `UPSTOX_ANALYTICS_TOKEN`).

### FinRakshak effectiveness tracking
Automated monthly report: FinRakshak P&L vs MF portfolio drawdown.
`finrakshak_day_delta` already in `PortfolioSummary` — query over snapshot history.

### P&L visualization
Matplotlib chart from `daily_snapshots` time series (component breakdown over time).
Start once 4+ weeks of snapshot data available.
`snapshot_date` field already in `PortfolioSummary` — ready to query.

---

## Medium-Term (Q3–Q4 2026)

### Swing Strategy Research Pipeline (Phase 2 Track A — starts after Phase 1.12 gate)

Full methodology: `docs/plan/SWING_STRATEGY_RESEARCH.md`. Three rule-based directional/neutral swing strategies on Nifty index options (Donchian Channel, ORB, Gap Fade), validated sequentially.

**Stage sequence and data cost:**
- **2.S0 — Data infra (free):** Verify Upstox OHLC Parquet from task 1.3a covers Nifty 50 daily + 15-min + India VIX daily.
- **2.S1 — Regime engine (free):** `src/strategy/regime.py` — 3×3 classifier (50D trend slope × 252D VIX percentile). Tags every historical trading day.
- **2.S2 — Signal generators (free):** One per strategy (Donchian, ORB, Gap Fade) on spot OHLC. Pure directional signals, no option data.
- **2.S3a — Tier 1 backtester (free):** `src/backtest/points_bt.py` — P&L in Nifty points. Validates signal quality with zero paid data. Mandatory first pass.
- **2.S3b — Tier 2 backtester (NSE Bhavcopy — FREE):** `src/backtest/spread_bt.py` — option spread P&L using Bhavcopy EOD data + BS IV reconstruction. Conditional on Tier 1 passing. If Bhavcopy strike exclusion rate >20%, Tier 1 is authoritative.
- **2.S4 — Walk-forward + validation (Code + Strategy):** 252-day rolling window, 63-day step. 6 failure conditions (OOS Calmar, consistency, MC 95th DD, sensitivity, regime concentration, slippage). Calmar thresholds: Donchian ≥0.8, ORB ≥0.6, Gap Fade ≥0.5.
- **2.S5 — Portfolio construction (Code):** Equal-risk allocation if ≥2 strategies pass. Combined Calmar ≥1.0; pairwise correlation <0.3.
- **2.S6 — Paper trading (Animesh):** 60 trading days minimum; prefix `paper_research_<strategy>_v1`.
- **2.S7 — Live deployment (Animesh):** 1 lot; scale to 2 after 60 days within envelope.

**Key data cost note:** Tier 1 and all regime/signal work is entirely free (existing `UPSTOX_ANALYTICS_TOKEN`). Tier 2 uses NSE Bhavcopy (free, task 1.3) with BS IV reconstruction (task 1.6a). DhanHQ was evaluated and rejected (2026-04-27) — 1-min data is only 5 days deep, not the documented 5 years.

### Investment Strategy Research Pipeline (Phase 2 Track B — starts after Phase 1.12 gate)

Full methodology: `docs/plan/INVESTMENT_STRATEGY_RESEARCH.md`. Three systematic NiftyBees ETF allocation strategies (10-Month SMA, Dual Momentum, PE Band Rebalancing) on separate capital pool, >1yr holding periods, validated sequentially.

**Stage sequence and data cost — all stages zero paid data:**
- **2.I0 — Data infra (free):** NiftyBees ETF daily (Upstox), Nifty PE monthly (NSE historical CSV, free), liquid fund NAV (AMFI, already in `src/mf/`).
- **2.I1 — Signal generators (free):** SMA filter (monthly), dual momentum (monthly), PE band (quarterly allocation tiers).
- **2.I2 — Backtest (free):** `src/backtest/allocation_bt.py` — P&L in NiftyBees NAV terms; includes cash return during out-of-market periods; buy-and-hold comparison mandatory.
- **2.I3 — Walk-forward + validation (Code + Strategy):** 36-month window, 12-month step; relaxed thresholds (OOS Calmar ≥0.3); buy-and-hold must be beaten on risk-adjusted basis OR drawdown must be reduced >30%.
- **2.I4 — Paper trading (Animesh):** 6 months minimum; prefix `paper_invest_<strategy>_v1`.
- **2.I5 — Live deployment (Animesh):** ₹5L NiftyBees pool; quarterly rebalance review.

**Key data cost note:** No DhanHQ at any stage. The entire investment strategy pipeline costs nothing beyond the existing Upstox analytics token.

### Order execution layer (`src/execution/`) — post static IP
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

### Swing + Investment strategy pipelines mature into Phase 3

By Phase 2 end (mid-2027), the parallel research tracks (Track A: `docs/plan/SWING_STRATEGY_RESEARCH.md`, Track B: `docs/plan/INVESTMENT_STRATEGY_RESEARCH.md`) will have produced 0–3 validated live swing strategies and 0–3 validated live investment strategies. These feed into Phase 3 portfolio construction. Key long-term milestones:

- **Track A → Phase 3:** Validated swing strategies (Donchian, ORB, Gap Fade) enter Phase 3 alongside CSP + IC. Decision on calendar spread (§3.2) vs Track A graduates required before Phase 3 starts — see Open Questions.
- **Track B → Phase 3:** Validated investment strategies go live with ₹5L NiftyBees allocation and run independently of the options book. Regime classifier (Phase 3.5) and Track A's regime engine (2.S1) consolidate into a single `src/regime/` module.
- **Phase 4 (2028+):** Finideas evaluation uses ≥24 months of tracked realised P&L. Basket of 3–5 validated strategies benchmarked against passive alternatives.

### Backtesting engine (`src/backtest/`)
- **Unblocked (2026-04-27 decision):** Data source stack finalised — TrueData rejected (EOD-only historical); DhanHQ rejected (1-min data only 5 days deep, not 5 years as documented). Adopted: Stockmock for calibration backtests (manual UI, already subscribed) + NSE F&O Bhavcopy for programmatic pipeline (free, 2016–present, covers IL&FS + COVID stress windows).
- **TimescaleDB deferred indefinitely:** Original justification was DhanHQ 500M-row 1-min volume. With Bhavcopy EOD-only (~4M rows for 8 years), Parquet + SQLite is sufficient.
- **Data pipeline:** `src/backtest/bhavcopy_ingest.py` + `scripts/bhavcopy_bootstrap.py` (see P1-NEXT in TODOS.md). Parquet partitioned by `data/offline/options_ohlcv/{year}/{month}/`.
- **IV reconstruction:** Bhavcopy has no IV field — compute via BS inverse (`scipy.optimize.brentq` on `settle_price`). Implementation: `src/backtest/greeks.py` task 1.6a.
- **Live Greeks:** Upstox confirmed as sole production source (existing `src/client/upstox_market.py`). No new broker client needed.
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
| Historical candles (expired instruments) | ~~Paid Upstox subscription~~ → **Unblocked:** NSE Bhavcopy (task 1.3) provides EOD options OHLCV free, 2016–present | See TODOS P1-NEXT |
| Expired option contracts | ~~Paid Upstox subscription~~ → **Unblocked:** NSE Bhavcopy covers all expired contracts; DhanHQ evaluated and rejected 2026-04-27 | See TODOS P1-NEXT |
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
