# NiftyShield — Planner

> Forward-looking roadmap. Read when starting new feature work or evaluating architecture changes.
> Distinct from TODOS.md (immediate actionable items) — this covers multi-sprint thinking,
> blocked items, and design decisions being evaluated.

---

## Completed (April–May 2026) ✓

- ✓ **Greeks capture** — `OptionChain` model live, Greeks populating `daily_snapshots` from 2026-04-25
- ✓ **`scripts/find_strike_by_delta.py`** — live delta filter + `record_paper_trade.py` command output (shipped 2026-05-03)
- ✓ **Bhavcopy pipeline** — `src/backtest/bhavcopy_ingest.py` + `bhavcopy_loader.py` + bootstrap script (Phase 1.3, 2026-05-03). UDiFF fix pending — see TODOS Task 0.
- ✓ **3-track strategy spec (0.4b)** — `docs/strategies/nifty_track_comparison_v1.md` written + passes validator (2026-05-03). Unblocks 0.6b paper entry.
- ✓ **Dhan intraday options tracking** — all phases A–E complete:
  `DhanOptionPosition`, `DhanOptionsSummary`, `DhanFundLimit`, `dhan_options_snapshots` + `dhan_margin_snapshots`, combined `intraday_tracker.py` orchestrator (2026-05-06)
- ✓ **3-track paper framework** — entry (`paper_3track_overlay.py`), snapshot (`paper_3track_snapshot.py`), roll (`paper_3track_overlay_roll.py`) scripts all shipped;
  `PaperLegSnapshot` + `paper_leg_snapshots` table (2026-05-04)
- ✓ **Intraday tracker schema refactor** — `IntradayMarketStore` isolates market context (Nifty+VIX);
  Nuvama v3 schema migration removes `nifty_spot` column; orchestrator fetches market data once async (2026-05-08)
- ✓ **Auto-expiry for CSP entry scripts** — `get_expiry_candidates()` in `src/instruments/lookup.py`;
  `--expiry` optional on `find_strike_by_delta.py` + `record_paper_trade.py`;
  cross-ranks across monthly/quarterly/yearly expiry buckets (2026-05-10, SHA 21cd505)

---

## Near-Term (May–June 2026)

Active code queue in priority order — see `TODOS.md` for full specs.

### Task 0 — Fix bhavcopy UDiFF format migration (ASAP)
`src/backtest/bhavcopy_ingest.py` needs dual-URL + dual-parser to cover Dec 2024+. Safe range until fix ships: `--end 2024-11-01`.

### Task 1 — India VIX ingestion + IVR calculation (Jun 2026)
Daily VIX Parquet from Upstox (`NSE_INDEX|India VIX`). Wires `compute_ivr()` (already in `src/backtest/ivr.py`) into paper trade entry logging. Enables R3 filter + Phase 0.8 gate criteria C/D.

### Task 2 — PortfolioDeltaTracker (Jun 2026)
`src/risk/` package: `PortfolioDelta` dataclass, `PortfolioDeltaTracker.aggregate_delta()`, `check_entry_allowed()`. Caps: options-only +1.0 lots, combined +2.0 lots.

### Task 3 — June 2026 Finideas Roll (HARD DEADLINE 2026-06-30)
NIFTY_JUN 23000 CE + PE legs expire. Invoke `roll-validator` agent ≥1 week before deadline.

### Task 4c — paper-backbone (Jun–Jul 2026)
`src/strategy/` protocol + `StrategyMonitor` daemon + `RapidCouncil` + `TelegramGateway` approval flow.
CSP and 3-Track strategies are already live as paper trades (since 2026-05-11); this phase adds
automated signal detection and Telegram approval routing. **Full spec: `docs/plan/paper-backbone/`** — copy `prompt.md` to start.
PT-0 (PB1.1–PB1.7) is the only unblocked entry point and blocks all strategy phases.

### P&L Visualization artifact
~6 weeks of snapshot data now available — buildable.
Four panels: MF, Dhan ETFs, Nuvama Bonds, Nuvama Options.
Cowork artifact (self-contained HTML, live DB queries).
Revisit once Tasks 0–2 are shipped.

### FinRakshak effectiveness tracking
Automated monthly report: FinRakshak P&L vs MF portfolio drawdown.
`finrakshak_day_delta` already in `PortfolioSummary` — query over snapshot history.

---

## Medium-Term (Q3–Q4 2026)

### Swing Strategy Research Pipeline (Phase 2 Track A — starts after Phase 1.12 gate)

Full methodology: `docs/plan/signals-eval-core/` (stories SE3.x + SE5–SE6).
Three rule-based directional/neutral swing strategies on Nifty index options (Donchian Channel, ORB, Gap Fade), validated sequentially.

**Stage sequence and data cost:**
- **2.S0 — Data infra (free):** Verify Upstox OHLC Parquet from task 1.3a covers Nifty 50 daily + 15-min + India VIX daily.
- **2.S1 — Regime engine (free):** `src/strategy/regime.py` — 3×3 classifier (50D trend slope × 252D VIX percentile). Tags every historical trading day.
  **Prototype validated 2026-05-23:** `docs/strategies/regime_probe.pine` is a live Pine Script probe (TV MCP-readable via `data_get_pine_tables`)
  that has validated the core regime signal design against real NIFTY data.
  Key design constraints surfaced by the prototype that `src/strategy/regime.py` must respect:
  (1) **Multi-timeframe check is mandatory** — 1D and 1W regime signals diverged on 2026-05-22 (1D=Sideways, 1W=Volatile-Ranging).
  Weekly regime vetoes daily for strangle entry.
  The `regime.py` classifier must tag each bar with both TF signals, not just the chart timeframe.
  (2) **HV annualization must be timeframe-aware** — `std(log_returns, 20) × sqrt(annualization_factor)` where `annualization_factor = 252` (daily), `52` (weekly), `12` (monthly).
  Hardcoding 252 overstates weekly HV by ~2.2×.
  (3) **Regime × VIX matrix drives options recommendation** — see `docs/archive/DECISIONS_pre-2026-07.md → TradingView MCP Regime Probe` for the full 4×3 matrix.
  `regime.py` should output both `regime_code` (int) and `vix_level` (str) so the recommendation lookup is a trivial dict access downstream.
  (4) **ATR% percentile rank** is a more reliable vol signal than raw ATR on historical data — compute as `percentrank(atr_pct, 252)` across the training window.
  An `atr_pct_rank ≥ 80` veto overrides the Sideways label when weekly vol is elevated.
- **2.S2 — Signal generators (free):** One per strategy (Donchian, ORB, Gap Fade) on spot OHLC. Pure directional signals, no option data.
- **2.S3a — Tier 1 backtester (free):** `src/backtest/points_bt.py` — P&L in Nifty points. Validates signal quality with zero paid data. Mandatory first pass.
- **2.S3b — Tier 2 backtester (NSE Bhavcopy — FREE):** `src/backtest/spread_bt.py` — option spread P&L using Bhavcopy EOD data + BS IV reconstruction.
  Conditional on Tier 1 passing. If Bhavcopy strike exclusion rate >20%, Tier 1 is authoritative.
- **2.S4 — Walk-forward + validation (Code + Strategy):** 252-day rolling window, 63-day step.
  6 failure conditions (OOS Calmar, consistency, MC 95th DD, sensitivity, regime concentration, slippage).
  Calmar thresholds: Donchian ≥0.8, ORB ≥0.6, Gap Fade ≥0.5.
- **2.S5 — Portfolio construction (Code):** Equal-risk allocation if ≥2 strategies pass. Combined Calmar ≥1.0; pairwise correlation <0.3.
- **2.S6 — Paper trading (Animesh):** 60 trading days minimum; prefix `paper_research_<strategy>_v1`.
- **2.S7 — Live deployment (Animesh):** 1 lot; scale to 2 after 60 days within envelope.

**Key data cost note:** Tier 1 and all regime/signal work is entirely free (existing `UPSTOX_ANALYTICS_TOKEN`).
Tier 2 uses NSE Bhavcopy (free, task 1.3) with BS IV reconstruction (task 1.6a).
DhanHQ was evaluated and rejected (2026-04-27) — 1-min data is only 5 days deep, not the documented 5 years.

### Investment Strategy Research Pipeline (Phase 2 Track B — starts after Phase 1.12 gate)

Full methodology: `docs/plan/signals-eval-core/` (stories SE4.x + SE5–SE6).
Three systematic NiftyBees ETF allocation strategies (10-Month SMA, Dual Momentum, PE Band Rebalancing) on separate capital pool, >1yr holding periods, validated sequentially.

**Stage sequence and data cost — all stages zero paid data:**
- **2.I0 — Data infra (free):** NiftyBees ETF daily (Upstox), Nifty PE monthly (NSE historical CSV, free), liquid fund NAV (AMFI, already in `src/mf/`).
- **2.I1 — Signal generators (free):** SMA filter (monthly), dual momentum (monthly), PE band (quarterly allocation tiers).
- **2.I2 — Backtest (free):** `src/backtest/allocation_bt.py` — P&L in NiftyBees NAV terms; includes cash return during out-of-market periods; buy-and-hold comparison mandatory.
- **2.I3 — Walk-forward + validation (Code + Strategy):** 36-month window, 12-month step; relaxed thresholds (OOS Calmar ≥0.3);
  buy-and-hold must be beaten on risk-adjusted basis OR drawdown must be reduced >30%.
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
- **paper-backbone (Task 4c)** — `PaperStrategy` protocol + `StrategyMonitor` daemon + pluggable strategies (CSP, IC, 3-Track, Signal Pipeline). Full spec: `docs/plan/paper-backbone/`.
- Phase 2 regime engine (`src/strategy/regime.py`) and swing signal generators are separate work, start after Phase 1.12 gate — see Phase 2 Track A below.

### Websocket streaming (`src/streaming/`)
- `live.py`: Upstox websocket handler
- `recorder.py`: `StreamRecorder` — captures live ticks to Parquet
- `replay.py`: `ReplayMarketStream` — replays from Parquet at configurable speed

---

## Long-Term (Q4 2026+)

### Swing + Investment strategy pipelines mature into Phase 3

By Phase 2 end (mid-2027), the parallel research tracks (Track A: swing strategies SE3.x in `docs/plan/signals-eval-core/`, Track B: investment strategies SE4.x in `docs/plan/signals-eval-core/`)
will have produced 0–3 validated live swing strategies and 0–3 validated live investment strategies.
These feed into Phase 3 portfolio construction. Key long-term milestones:

- **Track A → Phase 3:** Validated swing strategies (Donchian, ORB, Gap Fade) enter Phase 3 alongside CSP + IC.
  Decision on calendar spread (§3.2) vs Track A graduates required before Phase 3 starts — see Open Questions.
- **Track B → Phase 3:** Validated investment strategies go live with ₹5L NiftyBees allocation and run independently of the options book.
  Regime classifier (Phase 3.5) and Track A's regime engine (2.S1) consolidate into a single `src/regime/` module.
- **Phase 4 (2028+):** Finideas evaluation uses ≥24 months of tracked realised P&L. Basket of 3–5 validated strategies benchmarked against passive alternatives.

### Backtesting engine (`src/backtest/`)
- **Unblocked (2026-04-27 decision):** Data source stack finalised — TrueData rejected (EOD-only historical); DhanHQ rejected (1-min data only 5 days deep, not 5 years as documented).
  Adopted: Stockmock for calibration backtests (manual UI, already subscribed) + NSE F&O Bhavcopy for programmatic pipeline (free, 2016–present, covers IL&FS + COVID stress windows).
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
