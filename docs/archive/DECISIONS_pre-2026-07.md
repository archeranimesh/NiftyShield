# NiftyShield — Archived Decisions (pre-2026-07)

> Split out of [DECISIONS.md](../../DECISIONS.md) on 2026-08-27 (round-2 token-optimization
> #3b). These five sections are fully historical and self-contained — none states a rule
> still enforced in code. Same format as the parent file. New decisions go in DECISIONS.md,
> never here.

---

## TradingView MCP Regime Probe (2026-05-23)

**Tool:** `tradesdontlie/tradingview-mcp` — Chrome DevTools Protocol bridge to TradingView Desktop (port 9222). 78 MCP tools. Used via ChatGPT/Codex with the MCP server running locally.

**Validated findings (from `docs/archive/tv_mcp_testing_framework.md` Phases 0, 3, 3C):**

- `chart_get_state` returns a manifest only (symbol, resolution, chartType, study name+ID list). Study IDs are session-scoped random strings — call `chart_get_state` at the start of every session to resolve current IDs before calling `indicator_set_inputs`.
- `data_get_pine_tables` reads Pine Script `table.new()` output as a flat `rows: string[]` array, each entry pipe-separated (`"key | value"`). Numeric values arrive as strings — explicit `float()` cast required at consumption. Tables are identified by study name (stable), not by session ID.
- **Timeframe switching is reliable** — table updates correctly after `chart_set_timeframe`, no stale data.
- **Parser pattern** (Python): `dict(row.split(" | ", 1) for row in rows[1:])` + explicit numeric cast.

**Multi-timeframe regime divergence (key finding):**

Running the probe on 2026-05-22 (NIFTY at 23,719):

| Timeframe | Regime | Code | Options Rec |
|---|---|---|---|
| 1D | Sideways | −2 | Strangle: Standard |
| 1W | Volatile-Ranging | 2 | Defined Risk Only |

The weekly regime vetoes the daily tactical signal. **Rule: if 1W regime_code ≥ 2 (Volatile), do not deploy strangles regardless of daily regime.** Both signals must be ≤ 0 (Sideways/Transitioning) for strangle entry to proceed.

**HV annualization bug (known):** `hv_20_ann` in `docs/strategies/regime_probe.pine` uses `math.sqrt(252)` hardcoded regardless of timeframe. On weekly charts this overstates annualized HV by a factor of √(252/52) ≈ 2.2×. The daily HV figure is correct; never use `hv_20_ann` from the weekly table. **Fix:** Version 2 probe should run everything on the daily chart and pull weekly regime via `request.security()`.

**Regime × VIX options recommendation matrix (implemented in probe, validated live):**

| | VIX < 14 (Low) | 14 ≤ VIX ≤ 20 (Mid) | VIX > 20 (High) |
|---|---|---|---|
| Sideways (−2) | Strangle: Small/Skip | Strangle: Standard | Strangle: Aggressive |
| Transitioning (0) | Strangle: Watch | Strangle: Entry Zone | Strangle: Entry Zone |
| Trend-Up/Down (±1) | Collar/CSP Only | Collar/CSP Only | Defined Risk Only |
| Volatile-* (2, 3) | Defined Risk Only | Defined Risk Only | Defined Risk Only |

**Next step:** Version 2 probe — single daily-chart script pulling weekly regime via `request.security()`, both TF signals in one table, timeframe-aware HV formula.

---

## Backtest Data Source Decision (2026-04-27)

| Tool | Status | Reason |
|---|---|---|
| TrueData API | Rejected | 1-min API: 6 months depth; tick API: 5 days depth; no historical Greeks via API |
| TrueData historical dump | Adopted — 1-min intraday pipeline (task 1.3b) | Dump product (separate from API) delivers daily zips back to Jun 2015. ₹7,999/year of data. First purchase: 2022–2024. See `BACKTEST_PLAN_PHASE1.md §1.3b` and "TrueData Historical Dump (2026-05-09)" below |
| DhanHQ Data API | Rejected | 1-min: ~5 days depth (not 5 years); EOD misses COVID Mar 2020 + IL&FS Sep 2018 |
| Stockmock | Adopted — calibration backtests | Already subscribed; covers all critical stress windows; UI-only |
| NSE F&O Bhavcopy | Adopted — programmatic pipeline | Free; exchange-authoritative; 2016–present; see `BACKTEST_PLAN_PHASE1.md §1.3` |
| Upstox Analytics API | Confirmed — forward testing + production | Already integrated; live Greeks at zero additional cost |

---

## TrueData Historical Dump (2026-05-09)

**Context:** TrueData's API was evaluated and rejected in April 2026 (depth too shallow). Their separate *historical data dump* product was re-evaluated in May 2026 after receiving sample files. These are different products — the dump delivers complete historical CSVs, one zip per trading day, going back to Jun 2015 (1-min) and Oct 2018 (tick).

**What was confirmed from sample analysis (2026-05-09):**

| Property | Value |
|---|---|
| Zip naming | `NSE_OPT_1MIN_YYYYMMDD.zip`, `NSE_IDX_1MIN_YYYYMMDD.zip` |
| Schema | No header row. Columns: `YMD, Time(HH:MM), O, H, L, C, Volume, OI` |
| Contract naming | Weekly: `NIFTY{YY}{MMDD}{STRIKE}{CE/PE}.csv`; Monthly: `NIFTY{YY}{MMM}{STRIKE}{CE/PE}.csv` |
| Sparse bars | Minutes with no trades are absent — not zero-filled. Expected. |
| Volume/OI | In contracts, not lots. Requires lot-size lookup at ingestion time. |
| NIFTY contracts/day | ~327 in 2019; estimated 1,500–2,500 in 2022–2024 (weekly expiry proliferation) |
| IDX zip contents | `NIFTY.csv` (spot 1-min) + `INDIAVIX.csv` (VIX 1-min) — same schema |
| No Greeks | IV/delta not in raw data — must compute via Black '76 (same as Bhavcopy pipeline) |

**Decision: buy 1-min, not tick.**
Tick data (₹11,999/year) gives sub-second OHLCV. CSP exit triggers (50% profit, 21-day time stop, delta stop) do not require sub-minute resolution. 1-min is sufficient through Phase 2. Revisit tick if execution latency becomes material in Phase 3+.

**Decision: buy 2022–2024 first (₹24K), not full history (₹64K+).**
Rationale: modern weekly-expiry regime, covers 2022 rate-hike crash and 2024 election spike. If Phase 1.11 variance check requires older history (COVID crash Feb–Apr 2020), purchase 2019–2021 at that point. Do not buy 8 years upfront before quality gate passes.

**Storage decision:**
Parquet, partitioned by `year/month/date`, NIFTY-only filter at ingestion. Estimated 1.5–3 GB for 3 years of NIFTY options. Raw zips (~9 GB for 3 years) kept on cold/external storage. Full storage layout and ingestion pipeline: `BACKTEST_PLAN_PHASE1.md §1.3b`.

**Relationship to Bhavcopy (task 1.3):**
TrueData supplements, does not replace, Bhavcopy. Bhavcopy remains the free EOD source for 8-year history. TrueData adds 1-min intraday resolution for the purchased date range, enabling intraday exit simulation.

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

**Early guards (active from first live trade):** R6 single-cycle catastrophic loss; 3-cycle rolling drawdown > 4× credit → paper-only; 3 consecutive losses → halt; open MTM > 3× credit → close + pause; regime-divergence flag (VIX >95th pct, IVR <25, R4 event); slippage > 2× modeled for 2 cycles → paper-only. **Implementation:** `src/risk/monitoring.py` (Phase 2).

---

## src/ Model Placement Rule (2026-05-31)

| Rule | Detail | Source |
|---|---|---|
| Shared types → `src/models/` | Types used by two or more modules go into `src/models/` (currently: `portfolio.py`, `mf.py`, `options.py`). Do not create a domain `models.py` and migrate later. | src-restructure SS4 |
| Domain-local types → `src/<module>/models.py` | Types used only within one domain stay local (dhan, nuvama, paper, risk). | src-restructure SS4 |

---
