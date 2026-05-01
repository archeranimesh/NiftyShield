# NiftyShield — Swing Strategy Research Pipeline

| Field        | Value                                                     |
|--------------|-----------------------------------------------------------|
| Author       | Animesh Bhadra (archeranimesh)                            |
| Date         | 2026-04-27                                                |
| Status       | Draft — pending Phase 0 gate (BACKTEST_PLAN.md §0.8)      |
| Signal source| Nifty 50 Index spot (`NSE_INDEX|Nifty 50`)                |
| Regime filter| India VIX (`NSE_INDEX|India VIX`, Dhan: security ID `25`) |
| Execution    | Nifty index options — vertical spreads + iron condors     |
| Data sources | Upstox (live candles, VIX), DhanHQ (expired options, Tier 2) |

> **Purpose:** Research plan for 3 rule-based directional/neutral swing strategies on Nifty 50
> Index. Signals are generated from spot OHLC + VIX. Execution uses defined-risk option spreads,
> not naked positions or futures. Each strategy maps to a specific spread type depending on
> the signal direction and the VIX regime. Backtesting uses a two-tier approach: Tier 1 (Nifty
> points, always available) validates signal quality; Tier 2 (option spread P&L) validates the
> execution layer when historical option data is available.
>
> **Relationship to BACKTEST_PLAN.md:** This plan runs *inside* the backtest engine built in
> Phase 1 of BACKTEST_PLAN.md. The CSP strategy (Phase 0) is the calibration strategy — its
> paper-trade → backtest variance check validates the engine. The strategies in *this* document
> are the payload that engine will eventually process. Do not start this work until Phase 1
> gate (§1.12) is passed.
>
> **Companion document:** [INVESTMENT_STRATEGY_RESEARCH.md](INVESTMENT_STRATEGY_RESEARCH.md)
> — 3 long-term (>1 year) systematic allocation strategies on NiftyBees ETF. Separate capital
> pool, separate validation thresholds, shared backtest engine infrastructure.
>
> **Prerequisite reading:** `BACKTEST_PLAN.md` (engine architecture), `CONTEXT.md` (codebase
> state), `REFERENCES.md` (instrument keys, DhanHQ data constraints).

---

## Design Constraint: Why Spreads, Not Futures

Futures require continuous position management, overnight margin, and expose the full notional
to gap risk. Defined-risk spreads cap loss at the spread width minus premium collected (credit
spreads) or premium paid (debit spreads). For a retail operator running this alongside an
existing Finideas portfolio and ₹1.2 cr+ collateral pool, capital efficiency and max-loss
predictability matter more than the theoretical purity of a futures backtest.

The tradeoff: option spreads introduce IV sensitivity, bid-ask slippage on 4-leg structures
(iron condors), and theta decay as a profit/cost component that doesn't exist in a futures
backtest. The backtest must model these — see §Implementation Stage 3.

**Execution mapping:**

| Signal direction | Backtest (Tier 2) | Post-validation (if edge confirmed) |
|-----------------|-------------------|-------------------------------------|
| Bullish         | Bull put spread (credit, 30–45 DTE) | Credit in normal/high VIX; debit in low VIX |
| Bearish         | Bear call spread (credit, 30–45 DTE) | Credit in normal/high VIX; debit in low VIX |
| Neutral         | Not applicable (signal-in-only — no neutral entry) | Iron condor if regime-switch validated |

> **Council decision (2026-04-30):** VIX-based credit/debit regime switching is deferred out
> of the Tier 2 backtest. Use **credit spreads uniformly** for both bullish and bearish
> signals during backtesting. The switching logic has insufficient sample size (~30–50 trades
> over 5 years) to validate independently, and VIX boundary noise (std dev ~1.2 points/day)
> affects ~20–30% of entry days around the threshold. The directional signal is the edge to
> validate first.
>
> **Post-validation only:** If the directional edge is confirmed and the regime switch is
> subsequently tested, require Sharpe improvement >0.15 to justify added complexity. If
> implemented, use **hysteresis (Schmitt Trigger)**: enter credit regime when VIX rises
> above upper band (~19); enter debit regime when VIX falls below lower band (~14); maintain
> previous classification in the dead zone (14–19) to prevent boundary ping-pong.

**Why credit spreads in normal/high VIX and debit in low VIX (rationale, for post-validation):**
When VIX is elevated, option premiums are rich — selling spreads captures inflated premium
with a statistical tailwind (realised vol typically undershoots implied during mean-reversion
from VIX spikes). When VIX is low, premiums are thin and selling offers poor risk/reward;
buying a debit spread costs less and benefits if the directional move materialises with any
vol expansion. The neutral/low-VIX iron condor skip remains: collecting tiny premiums against
large spread width at VIX < 25th percentile is structurally negative-EV.

---

## Part 1 — Strategy Selection

### Strategy 1: Donchian Channel Trend Following

**Core hypothesis:** Nifty exhibits sustained directional trends lasting 3–12 weeks, driven
by FII flow cycles, RBI rate decisions, global risk-on/off rotations, and election/budget
macro events. These trends persist because Nifty's participant structure — FII directional
flow on one side, retail and DII absorption on the other — creates momentum that takes weeks
to exhaust. A channel breakout on daily bars captures the initiation of these trends.

**Signal source:** Nifty 50 Index daily close vs. N-day high/low channel.

**Timeframe:** Daily bars. Not 60-min — sub-daily channel breakouts on Nifty are noise-
dominated and add false signals without improving trend capture. Not weekly — too slow to
catch 3-week trends and generates too few trades for statistical validation in 5 years.

**Parameters (3):**

| Parameter                | Initial | Sweep range | Step |
|--------------------------|---------|-------------|------|
| Channel lookback (N days)| 40      | 20–60       | 5    |
| ATR trailing stop mult.  | 3.0     | 2.0–4.5     | 0.5  |
| ATR lookback (days)      | 20      | 14, 20      | —    |

**Entry:** Go long (bull spread) when daily close > N-day high channel. Go short (bear spread)
when daily close < N-day low channel. **Signal-in-only** — a position is only held when an
active channel breakout signal exists. A new breakout in the opposite direction while in a
trade triggers exit of the current spread and entry of a new one in the new direction.

**Exit:** Trailing stop at entry price ± (ATR multiplier × current ATR). Recalculated daily.
When stop triggers, **close spread and go flat** — do not enter a new spread until the next
fresh channel breakout fires. Additionally: if the trade reaches 21 DTE with ≥50% of maximum
profit captured, close to harvest theta acceleration and avoid gamma risk near expiry. If
unprofitable at 21 DTE but stop has not fired, hold — directional thesis remains intact.

> **Council decision (2026-04-30):** The original "always-in" architecture was rejected.
> Being flat between signals costs nothing and eliminates ₹800–2,160/lot of uncompensated
> inter-signal theta bleed per inactive period. Mid-contract rolls (close + open simultaneously)
> are also eliminated — every new entry occurs on a fresh signal at 30–45 DTE, controlled
> timing, not forced by a stop event.

**Spread sizing:** Enter the spread on the signal day's close. Strike selection: short strike
at the nearest 15-delta option. **ATR-proportional spread width (dynamic):**

```
spread_width = min(round_to_50(k × ATR_40d), 500 points)
k = 0.8 (sweep [0.6, 0.7, 0.8, 0.9, 1.0] in walk-forward optimisation)
floor: 150 points (minimum 3 strikes for meaningful premium)
cap: 500 points (liquidity + DhanHQ strike coverage boundary)
```

Monthly expiry, 30–45 DTE at entry. If the signal triggers within 14 DTE of the nearest
monthly, use the *next* monthly.

**Position sizing (complement to dynamic width):**

```
max_risk_per_trade = ₹7,500 (research phase)
lots = max(1, floor(max_risk_per_trade / (spread_width × 75)))
```

Note: lot size changed to 75 (from 25) in November 2024. Use 75 for all current calculations.

> **Council decision (2026-04-30):** Fixed 200-point width rejected. At 40-day ATR of
> 400–500 points, a 200-point spread is traversed by a single average day's adverse move,
> producing structurally poor 1:6+ risk:reward. ATR-proportional width maintains ~10%
> breach probability across all vol regimes.

**Works in:** Sustained FII-driven trends (2021 H1 bull run, 2022 H1 correction, 2023
recovery, 2024 post-election rally). Nifty has spent roughly 55–60% of the last 5 years in
trending regimes — above average for a major index and the structural foundation of this edge.

**Fails in:** Choppy consolidation ranges. 2022 H2 (16000–18500 for months) is the canonical
failure period. Also fails during sharp V-reversals where the trailing stop exits at the worst
moment. Budget-week and election-week whipsaws can generate consecutive losing round-trips.

---

### Strategy 2: Opening Range Breakout (ORB) with Volatility Filter

**Core hypothesis:** The first 30 minutes of Nifty trading (9:15–9:45) absorb overnight
information — GIFT Nifty gap, Asian open, US close — through concentrated institutional order
flow. When the opening range (OR) is narrow relative to recent volatility, the market hasn't
chosen a direction yet. A breakout from this compressed range carries directional conviction
because it represents the resolution of overnight uncertainty. The compression filter is where
the edge concentrates — unfiltered ORB on Nifty is break-even at best.

**Signal source:** Nifty 50 Index 15-min candles (first N candles define the OR), filtered by
14-day ATR on daily bars.

**Timeframe:** 15-min bars for the opening range. Daily ATR for the volatility filter.

**Parameters (3):**

| Parameter                           | Initial | Sweep range | Step |
|-------------------------------------|---------|-------------|------|
| Opening candle count (15-min bars)  | 2       | 1–3         | 1    |
| Max OR width (fraction of 14d ATR)  | 0.6     | 0.3–0.8     | 0.1  |
| Risk-reward target multiple         | 1.5     | 1.0–2.5     | 0.5  |

**Entry:** Compute OR = high − low of first N 15-min candles. If OR < (filter × 14-day ATR),
the day qualifies. Go long (bull spread) on break above OR high. Go short (bear spread) on
break below OR low. One entry per direction per day. The spread is entered on the breakout
candle's close, not intraday — no live execution required.

**Exit:** Target at entry ± (R:R multiple × OR width). Hard close at 15:15 IST if target not
hit. This is strictly intraday — no overnight carry. Spread expiry is the nearest weekly
(Thursday expiry), giving 0–4 DTE. Use weekly options, not monthly, to minimise premium cost
on what is a same-day directional bet.

**Structural filter:** Exclude weekly expiry days (Thursday) from the universe entirely. Weekly
options expiry creates artificial pinning and two-way chop that systematically destroys ORB
entries. This is not an optimisation — it is a structural exclusion.

**Works in:** Trending days following overnight gaps, post-event days (RBI, Fed, earnings
season). Approximately 40–50% of Nifty trading days show a clean directional move from the
opening range.

**Fails in:** Expiry days (excluded). Gap days where the gap *is* the move and the OR just
consolidates. Days where the OR is wide (high-ATR-fraction filter catches this).

**Assumption to verify:** Confirm whether Upstox 15-min candles at 9:15 include the pre-open
auction match price or only regular-session trades. This changes OR calculation significantly.
Also verify that DhanHQ expired options data for weekly Nifty options covers the strikes needed
(ATM ± how many? — per BACKTEST_PLAN.md §1.1, coverage is ATM±10 near expiry, ATM±3 otherwise;
for weekly 0–4 DTE, ATM±10 should apply, but verify the "nearing expiry" cutoff).

---

### Strategy 3: Mean-Reversion Overnight Gap Fade

**Core hypothesis:** Nifty's open is driven by GIFT Nifty, which prices in US/Europe overnight
moves. Small-to-moderate gaps (0.3%–1.0% of previous close) are correlation-driven, not
information-driven, and domestic participants re-price independently during the session,
partially closing the gap. Large gaps (>1.0%) reflect genuine regime change and persist. The
strategy fades small gaps and ignores large ones.

This persists because the GIFT Nifty → NSE open arbitrage structure creates a systematic
opening dislocation that domestic institutional flow corrects within the first 2–3 hours.

**Signal source:** Nifty 50 Index daily open vs. previous daily close.

**Timeframe:** Daily bars for gap identification, 15-min bars for entry timing (enter after
the second 15-min candle, i.e., at 9:45, to let opening volatility settle).

**Parameters (3):**

| Parameter                              | Initial | Sweep range | Step |
|----------------------------------------|---------|-------------|------|
| Min gap size (% of prev close)         | 0.3%    | 0.2%–0.5%  | 0.1% |
| Max gap size (% of prev close)         | 1.0%    | 0.7%–1.5%  | 0.1% |
| Partial fill target (fraction of gap)  | 0.5     | 0.3–0.7    | 0.1  |

**Entry:** Gap-up > min and < max → short signal (bear spread). Gap-down > min and < max →
long signal (bull spread). Enter at the close of the second 15-min candle (9:45). Stop at the
session's high/low established in the first two candles. Weekly expiry options, 0–4 DTE.

**Exit:** Target at open ± (fill fraction × gap size). Hard exit at 12:30 IST — gap fills
that haven't happened by lunch rarely complete. Close spread at 12:30 regardless.

**Works in:** Normal-volatility days with overnight gaps driven by US futures correlation
rather than India-specific news. This is the majority of gap days.

**Fails in:** Budget day, RBI policy days, major global events. Gaps on these days are
information-driven and persist. Also fails during sustained high-VIX regimes where even
correlation-driven gaps carry genuine directional information. The VIX filter (§Regime
Classification) handles this — skip gap-fade signals when VIX > 75th percentile.

---

### Confidence Ranking

**1. Donchian Channel Trend Following (highest).** The edge is structural: Nifty trends
because of the FII flow mechanism, which is embedded in the market's participant structure.
Trend following on daily timeframes is the most validated anomaly in futures/index markets
globally, and Nifty's trending character is above-average among major indices. The risk is
drawdown magnitude during consolidation, not that the edge disappears. Credit spreads cap
that drawdown structurally.

**2. Opening Range Breakout (moderate).** The information-resolution mechanism at open is real
and grounded, but the edge is thinner — Nifty's algo penetration has increased since 2020,
and many participants trade ORB variants. The ATR-relative volatility filter is where the
differentiation lies. Without it, ORB on Nifty is noise. With it, you're selecting only the
compressed-range days where breakout conviction is highest.

**3. Gap Fade (lowest).** The hypothesis is sound but the signal-to-noise ratio is marginal.
Gap sizes on Nifty are often 0.2–0.5%, and after slippage + spread costs on options, a large
fraction of the expected move is consumed by transaction costs. Included because it is
structurally uncorrelated with the other two (mean-reversion vs. momentum), which matters for
portfolio construction. Expected to be the first strategy killed by validation.

---

## Part 2 — Validation Design

### Regime Classification: VIX + Trend (the regime engine)

Every validation step below depends on regime tags. Define them first.

**Dimension 1 — Trend strength:** 50-day linear regression slope of Nifty daily close,
normalised by 50-day ATR. This produces a dimensionless trend score.

| Score          | Label        |
|----------------|--------------|
| > +1.0         | Trending up  |
| −1.0 to +1.0   | Range-bound  |
| < −1.0         | Trending down|

**Dimension 2 — Volatility regime (VIX-based):** India VIX daily close, classified by its
own trailing 252-day percentile rank.

| VIX percentile  | Label     |
|-----------------|-----------|
| > 75th          | High vol  |
| 25th–75th       | Normal vol|
| < 25th          | Low vol   |

This produces a 3 × 3 grid of 9 regimes. In practice, several cells will be sparsely
populated (e.g., trending-up + high-vol is rare outside crash recoveries). The purpose is not
to have balanced cells but to tag each trading day and check whether strategy profits
concentrate in a single cell (fragile) or distribute across multiple cells (robust).

**Why VIX over ATR-only:** ATR is a backward-looking realised volatility measure. VIX is
forward-looking implied volatility. For option spread execution specifically, VIX directly
governs the premium you collect or pay. A regime classifier that ignores VIX would misclassify
periods where realised vol is low but implied vol is elevated (pre-event buildup) — exactly
the periods where credit spreads are most attractive.

**VIX data availability:** India VIX is published by NSE as a standalone index. Available via
Upstox as `NSE_INDEX|India VIX` (verify instrument key). Historical daily close data from
Upstox should cover 5 years. If Upstox historical VIX data has gaps, NSE publishes VIX
historical data as downloadable CSV on their website — use as backfill source.

---

### Train/Test Split

**Split point: 1 January 2024.**

Training: everything before Jan 2024. This captures: the 2021 bull run, the 2022 rate-hike
correction and H2 consolidation (16000–18500 range), the 2023 recovery to new highs. At
minimum two complete trend cycles, two major consolidation phases, and the 2022 correction.
This is the minimum set of regimes needed to calibrate parameters that aren't regime-specific
artifacts.

Test: Jan 2024 onward (~2.5 years). This period contains genuine out-of-sample regime events:
the 2024 general election (Apr–Jun), the post-election correction, the 2025 tariff-driven
selloff, and subsequent recovery. If a strategy survives election volatility and the tariff
shock without reoptimisation, the edge is structural.

**Why this split and not 70/30 or 50/50:** With 5 years of daily data (~1250 trading days),
trend following generates ~15–25 trades per year. The split gives ~750 training days (~60–75
trend trades, statistically sufficient for parameter estimation) and ~500+ test days (~30–50
trend trades, sufficient detection power). For intraday strategies, trade counts are much
higher, so the split is generous.

---

### Walk-Forward Configuration

**Window type:** Rolling (not anchored). Anchored walk-forward on Nifty is a mistake because
pre-2022 and post-2022 regimes differ structurally in algo participation, weekly options volume
(Nifty weekly options dominate since ~2020), and FII flow patterns. Anchoring drags in
increasingly stale data.

| Parameter               | Value | Rationale                                   |
|-------------------------|-------|---------------------------------------------|
| Training window         | 252 days (1 year) | Full seasonal cycle including budget + expiry effects |
| Step size               | 63 days (1 quarter) | Quarter-aligned re-optimisation          |
| Min trades per window   | 10 (daily strategies), 30 (intraday) | Below this, parameter estimates are noise |
| Insufficient-window cap | ≤25% of total windows | If >25% are insufficient, strategy lacks opportunity — abandon |

After each step, re-optimise parameters on the trailing 252-day window, then trade the next
63 days with those frozen parameters. The OOS equity curve is the concatenation of all 63-day
forward segments.

---

### Monte Carlo Design

**What is simulated:** Trade-level return bootstrapping. Take the realised per-trade returns
from all walk-forward OOS windows, then shuffle the trade sequence 10,000 times. Compute max
drawdown for each shuffled sequence.

**Purpose:** Separate "the strategy has edge" (captured by mean trade return) from "the
observed drawdown path was lucky or unlucky" (captured by the distribution of shuffled
drawdowns). This tells you whether your position sizing, which is calibrated to the *observed*
max drawdown, is realistic or optimistic.

**Iteration count:** 10,000. At this count, the 95th and 99th percentile estimates stabilise
to within ~2% of asymptotic values. 5,000 is borderline; 50,000 adds compute cost without
improving decision quality.

**Percentile bands:**

| Percentile | Use                                                            |
|------------|----------------------------------------------------------------|
| 50th       | Expected drawdown under this return profile. If this exceeds capital tolerance, strategy is unviable regardless of edge. |
| 95th       | Position-sizing anchor. Size so that 95th-percentile drawdown = max tolerable drawdown for the allocated capital. |
| 99th       | Sanity check. If >50% of allocated capital, tail risk is unacceptable. |

The 95th percentile is the decision-driving number. The 50th tells you capital efficiency;
the 99th tells you whether ruin is possible.

---

### Parameter Sensitivity Protocol

After walk-forward optimisation identifies the best parameter set, test all combinations
within ±2 steps of the optimum on every parameter simultaneously (full local grid).

**Plateau definition:** Compute the ranking metric (walk-forward median Calmar, defined below)
for each neighbouring combination. If ≥60% of neighbours produce a metric ≥80% of the
optimal value, the optimum sits on a plateau. This is acceptable — the edge is regime-driven,
not parameter-driven.

**Spike definition:** If <40% of neighbours reach 80% of optimal, the performance depends on
the exact parameter value, not on the underlying market behaviour. Abandon that parameter set.

**Concrete example:** Optimal Donchian lookback = 40 days, Calmar = 1.8. Test lookbacks 30,
35, 45, 50 with the same trailing stop. At least 3 of those 4 must produce Calmar ≥ 1.44
(80% × 1.8). If only 1 does, the 40-day lookback is a historical coincidence.

**Why 60%/80%:** 60% is strict enough to reject single-point optima but permissive enough to
accept the natural performance gradient around a real edge. The 80% value threshold ensures
the plateau represents genuinely similar performance, not "technically profitable but much
worse."

---

### Ranking Metric

**Walk-forward median Calmar ratio** (annualised return / maximum drawdown), computed per
walk-forward OOS window, then take the median across all windows.

**Why Calmar over Sharpe:** Sharpe penalises upside volatility — irrelevant for a spread
strategy that wins via premium collection and loses via defined max loss. Calmar directly
answers: "how much return per unit of worst pain?"

**Why median over mean across windows:** Walk-forward windows are not identically distributed.
Some contain trending regimes, some consolidation. The mean is pulled by outlier windows; the
median represents a typical forward period.

**Why not profit factor or expectancy:** Profit factor ignores drawdown. Expectancy (avg win ×
win rate − avg loss × loss rate) doesn't penalise the path — a high-expectancy strategy with
40% drawdowns will get stopped out psychologically before the expectancy materialises.

---

## Part 3 — Failure Conditions

These are hard kills. When a threshold is breached, the strategy is abandoned and research
moves to the next one. No "let's see if it improves with a tweak."

### 3.1 — Out-of-Sample Calmar

**Kill: OOS Calmar < 0.5.** A Calmar of 0.5 means earning half of what you draw down — it
takes two years of returns to recover from the worst drawdown. Nifty buy-and-hold has
historically delivered Calmar ~0.4–0.7. A systematic strategy must beat the upper end to
justify the complexity and operational overhead.

### 3.2 — Walk-Forward Consistency

**Kill: >40% of walk-forward OOS windows are net-negative.** If 4 of 8 windows lose money,
the edge is intermittent and untimeable. A trend follower will have losing windows during chop
(expected), but >60% positive windows is the minimum bar for a strategy you can hold through
live drawdowns.

**Secondary kill:** If the worst window's drawdown exceeds 2× the median window's drawdown,
the tail risk is regime-concentrated and Monte Carlo sizing will be unreliable. Not automatic
— requires investigation of which regime caused it and whether the VIX filter can exclude it.

### 3.3 — Monte Carlo 95th Percentile Drawdown

**Kill: MC 95th percentile drawdown > 1.5× observed maximum drawdown.** If the "bad luck"
scenario is only 50% worse than observed, the backtest drawdown is representative. If >1.5×,
the backtest got lucky on trade sequencing and you are underestimating tail risk. This is the
most common way strategies die — backtest shows 15% max DD, Monte Carlo shows 28% at the 95th
percentile, and your position sizing assumed 15% was the realistic worst case.

### 3.4 — Parameter Sensitivity

**Kill: plateau width < 3 steps in any parameter dimension.** If performance degrades sharply
within ±1 step (< 80% of optimal metric) on any axis, the edge is an artifact of the specific
parameter value. Three steps means the edge persists across at least a ±15–30% range of the
parameter value. If a strategy can't survive that perturbation, it won't survive regime drift
in live trading.

### 3.5 — Regime Concentration

**Kill: >80% of cumulative profit comes from a single regime cell.** If the strategy only
works in "trending-up + normal-vol," it's a regime bet, not a systematic edge. You're betting
you can identify when that regime starts and ends — which you can't, reliably, in real time.

### 3.6 — Slippage Sensitivity (option-specific)

**Kill: strategy turns unprofitable at 2-point round-trip slippage on Nifty options.**
Credit spreads involve 2 legs (4 trades for iron condors); each leg has a bid-ask spread.
If the edge disappears when you model realistic execution costs, the edge is inside the
spread and cannot be captured.

---

## Part 4 — Implementation Sequence

### Stage 0: Data Infrastructure (prerequisite — partially complete)

**Work:**
- Continuous Nifty 50 Index daily + 15-min OHLC series from Upstox (no rollover — spot index)
- India VIX daily close series from Upstox (verify `NSE_INDEX|India VIX` instrument key)
- Derived fields: 14-day ATR, 20-day ATR, 50-day linear regression slope, regime tags
- Parquet storage partitioned by instrument + date (per CONTEXT.md data layer convention)

**Gate:** Nifty Index daily close must match NSE published values within ±0.05% for 95% of
days over the full history. VIX series must have <1% missing days (fill with previous close
for holidays; flag and investigate gaps >1 trading day). ATR and slope values must be visually
consistent with a chart overlay.

**Pass criteria:** Data integrity report generated and reviewed. No code written until data is
verified.

---

### Stage 1: Regime Engine (`src/strategy/regime.py`)

**Work:**
- Implement the 3×3 regime classifier (trend slope + VIX percentile)
- Tag every historical trading day with its regime cell
- Generate regime distribution report: % of days and % of total Nifty return in each cell
- Store regime tags alongside OHLC in the signal database

**Gate:** Regime tags must be deterministic (same input → same output) and visually verifiable
on a chart (overlay regime colours on Nifty price chart, confirm transitions match known
events — e.g., 2022 correction should be "trending-down + high-vol" transitioning to
"range-bound + normal-vol").

**Pass criteria:** Regime distribution printed. No single cell should contain >40% of all
trading days (if it does, the thresholds need recalibration — but adjust only once, document
the change, do not iterate).

---

### Stage 2: Signal Generators (one per strategy)

**Work (sequential — one strategy at a time, do not parallelise):**

**2a — Donchian Channel signal generator:**
- Input: daily OHLC + regime tags
- Output: per-day signal (LONG / SHORT / FLAT) + trailing stop level + ATR value
- No spread selection yet — pure directional signal on spot index

**2b — ORB signal generator:**
- Input: 15-min OHLC + daily ATR + regime tags
- Output: per-day signal (LONG / SHORT / NO_TRADE) + OR high/low + target/stop levels
- Structural filter: exclude weekly expiry Thursdays

**2c — Gap Fade signal generator:**
- Input: daily OHLC (open vs prev close) + 15-min candles (entry timing) + regime tags
- Output: per-day signal (LONG / SHORT / NO_TRADE) + gap size + target/stop levels
- VIX filter: skip when VIX > 75th percentile

**Gate per signal generator:** Run on the full training set (pre-Jan 2024). Generate trade
log: entry date, signal direction, entry price, exit price, exit reason (target/stop/time),
holding period, regime at entry. Inspect visually on a chart. If the trade log contains
obvious errors (e.g., signals on non-trading days, stops that never trigger), fix before
proceeding. No optimisation at this stage — use initial parameter values only.

**Pass criteria:** Trade log generated with initial parameters. Trade count within expected
range (Donchian: 15–25/year, ORB: 80–150/year after filter, Gap Fade: 60–100/year after
filter). If trade count is <50% or >200% of expected, the signal logic has a bug.

---

### Stage 3: Two-Tier Backtester (Points + Option Spreads)

This stage has two tiers. **Tier 1 is mandatory and always runs first.** Tier 2 is conditional
on DhanHQ expired option data availability and coverage. A strategy must pass Tier 1 before
Tier 2 is attempted. If Tier 2 data is unavailable or exclusion rates are too high, the
strategy proceeds through walk-forward validation (Stage 4) on Tier 1 P&L alone — Tier 2 is
layered on later when data access improves.

**Why two tiers:** Historical Nifty option chain data is difficult to source reliably. DhanHQ
covers ATM±3 for non-near-expiry contracts, which may exclude 15-delta strikes at 30–45 DTE
(typically ATM±6 to ATM±10). NSE option chain CSV dumps are an interim alternative but have
their own coverage and format limitations. Rather than block the entire validation pipeline on
option data availability, Tier 1 validates the *signal quality* using Nifty spot points — the
dimension the trader actually controls — while Tier 2 validates the *execution layer* that
converts signals into spread P&L.

---

#### Tier 1: Nifty Points-Based P&L (always available)

**Data requirement:** Nifty 50 Index daily + 15-min OHLC (Upstox, already in Stage 0).
No option chain data needed.

**Work:**
- For each signal from Stage 2, compute P&L in Nifty points:
  - Entry price = Nifty spot at signal trigger (daily close for Donchian, 15-min candle close
    for ORB/Gap Fade)
  - Exit price = Nifty spot at exit trigger (trailing stop, target, time stop)
  - P&L = (exit − entry) × direction (+1 long, −1 short)
- Convert points to ₹ P&L using Nifty lot size (currently 25 units/lot) for position sizing
  context, but the primary metric is points — lot size changes over history and introduces a
  spurious variable
- Model costs: flat ₹40 per round-trip (₹20 entry + ₹20 exit brokerage equivalent) + 0.5
  points slippage per side (1 point round-trip). This understates true option execution costs
  but gives a directionally correct friction estimate for signal validation
- Mark-to-market daily: track unrealised P&L in points for the equity curve, not just
  trade-level entry/exit

**What Tier 1 validates:**
- Whether the signal generator has genuine predictive power on Nifty direction
- Win rate, average win/loss ratio, trade frequency, holding period distribution
- Regime decomposition — does the edge concentrate in one regime cell?
- Drawdown profile and recovery time in points

**What Tier 1 does NOT validate:**
- IV sensitivity, theta decay, and gamma risk that affect option spread execution
- Strike availability and liquidity at the required delta levels
- Actual spread entry/exit pricing and bid-ask slippage
- The credit/debit spread selection logic (§Design Constraint execution mapping)

**Gate:** Run the Donchian strategy (Strategy 1, highest confidence) through the full training
period with initial parameters. Generate:
- Equity curve in Nifty points (daily mark-to-market)
- Trade log: entry date, entry price, exit date, exit price, exit reason, P&L (points),
  regime at entry, holding period (days)
- Summary statistics: total P&L, win rate, avg win / avg loss, max consecutive losses,
  max drawdown (points), Calmar ratio (annualised points return / max drawdown in points)

**Pass criteria:** Trade log is internally consistent (no trades on non-trading days, no
overlapping positions in the signal-in-only system, no open positions during flat/inter-signal
periods, exit prices within the day's high-low range).
Summary stats are plausible — Donchian on Nifty daily bars should produce 15–25 trades/year
with win rate 35–50% and profit factor > 1.3 if the trend-following hypothesis holds. If
win rate > 60% or < 25%, the signal logic likely has a bug.

---

#### Tier 2: Option Spread P&L (when data is available)

**Data requirement:** DhanHQ expired option chain data OR NSE option chain CSV dumps with
sufficient strike coverage. Tier 2 is attempted only after Tier 1 passes for the same strategy.

**Work:**
- Extend the Phase 1 backtest engine (BACKTEST_PLAN.md) to handle vertical spreads and
  iron condors, not just single legs
- For each signal, select strikes using the execution mapping table (§Design Constraint):
  - All structures: short strike at ~15-delta; long strike at ATR-proportional width
    further OTM (`min(round_to_50(0.8 × ATR_40d), 500)`, floor 150 points)
  - Backtest Tier 2 uses credit spreads uniformly (debit/iron condor deferred per council)
  - Iron condors: deferred to post-validation optimisation
- Use DhanHQ expired option data for historical pricing (BACKTEST_PLAN.md §1.1)
- Model costs: ₹20/order brokerage + STT + exchange charges + 2-point slippage per leg
- Greeks computation: local Black-Scholes from DhanHQ IV data (no Greeks in DhanHQ API —
  per BACKTEST_PLAN.md §1.1, `requiredData` has IV but no delta/gamma/theta/vega)
- Position-level P&L: mark-to-market daily using DhanHQ close prices for each leg

**Critical modelling decisions:**
1. **Strike availability:** DhanHQ covers ATM±3 for non-near-expiry contracts. A 15-delta
   short strike at 30–45 DTE is typically ATM−300 to ATM−500 for puts (ATM+300 to ATM+500
   for calls). This is ATM±6 to ATM±10 in 50-point strike increments. If the strike falls
   outside DhanHQ coverage, the trade is marked "no data" and excluded — do NOT interpolate.
   Track the exclusion rate; if >20% of trades are excluded, the strategy cannot be
   backtested with this data source and Tier 1 points-based results become the authoritative
   validation for that strategy.
2. **Spread entry price:** Use the mid of (bid, ask) for each leg, then apply 1-point adverse
   slippage per leg. For a 2-leg spread, net slippage = 2 points. For a 4-leg iron condor,
   net slippage = 4 points. DhanHQ provides close prices, not bid/ask — use close as mid
   proxy, which understates slippage. Document this limitation.
3. **Early exit:** If the signal generator triggers an exit (trailing stop, target, time stop)
   before spread expiry, close the spread at that day's close prices + slippage. Do not hold
   spreads to expiry unless the signal generator's exit coincides with expiry.

**NSE option chain CSV as interim source:** If DhanHQ data is unavailable or too expensive,
NSE option chain CSV dumps (manually downloaded) can serve as an interim data source for
structural testing. The `nse-option-chain` skill handles the tricky NSE CSV format. Limitation:
these are point-in-time snapshots, not continuous historical series — useful for verifying
spread construction logic and strike selection, not for generating a full equity curve.

**Gate:** Run the Donchian strategy through the full training period. Generate:
- Equity curve (daily mark-to-market, not just trade-level)
- Trade log with entry/exit prices, spread details, P&L per trade, regime at entry
- **Tier 1 vs Tier 2 comparison:** signal-only P&L (Tier 1 points) vs. spread-execution P&L
  (Tier 2). This comparison is the key output — it quantifies the cost of converting a
  directional edge into an options position
- Slippage sensitivity: re-run with 0, 2, 4 points per leg — if profitability flips between
  2 and 4 points, the edge is too thin for options execution

**Pass criteria:** Spread backtester produces internally consistent results (no negative
prices, no trades on non-trading days, P&L matches manual spot-check on 5 random trades).
Tier 1 vs Tier 2 P&L gap documented — spread execution will underperform raw signal P&L due
to costs, slippage, IV drag, and theta. The gap should be quantified, not ignored. If Tier 2
P&L is negative while Tier 1 is positive, the signal has edge but the options execution layer
destroys it — reconsider spread width, DTE selection, or execution instrument (e.g., futures
instead of spreads).

---

### Stage 4: Walk-Forward Optimisation + Validation (per strategy)

**Which P&L tier to use:** Run walk-forward on Tier 1 (points-based) P&L first. This is the
mandatory baseline. If Tier 2 (option spread) P&L is available from Stage 3, run walk-forward
on Tier 2 as well and compare. If the two tiers produce different parameter optima, the Tier 1
optimum is authoritative — the signal edge is in the direction, not in the execution layer.

**Work (sequential — complete one strategy before starting the next):**

**4a — Donchian Channel:**
- Run walk-forward optimisation: 252-day rolling window, 63-day step, parameter sweep
  across all 3 parameters within specified ranges
- Compute per-window OOS Calmar
- Run Monte Carlo (10,000 iterations) on OOS trade returns
- Run parameter sensitivity on the terminal-window optimal params
- Compute regime decomposition: % of profit per regime cell
- Apply all 6 failure conditions (§Part 3). Record result.

**4b — ORB (only if 4a passes or to gather data even if 4a fails):**
- Same protocol as 4a
- Additional check: profitability after 2-point and 4-point round-trip slippage

**4c — Gap Fade (only if at least one of 4a/4b shows promise):**
- Same protocol
- If both 4a and 4b failed, reconsider whether the option execution layer is viable
  before spending time on the weakest signal

**Gate per strategy:** All 6 failure conditions clear. Walk-forward median Calmar ≥ threshold
(0.8 for Donchian, 0.6 for ORB, 0.5 for Gap Fade — lower thresholds for higher-frequency
strategies because Calmar is structurally lower when trades are smaller and more frequent).

**Pass criteria:** Strategy validation report generated with: equity curve, trade log, Monte
Carlo distribution chart, parameter sensitivity heatmap, regime decomposition table. Human
review and sign-off required before proceeding.

---

### Stage 5: Portfolio Construction

**Prerequisite:** At least 2 of 3 strategies passed Stage 4.

**Work:**
- Combine surviving strategies with equal-risk allocation (normalise position size so each
  contributes equal ATR-based risk to the combined portfolio)
- Test the combined equity curve on the OOS period (Jan 2024 onward)
- Compute correlation of daily returns between strategies
- Run Monte Carlo on the combined trade sequence

**Gate:**
- Combined walk-forward median Calmar ≥ 1.0 (the combination must outperform any individual)
- Daily return correlation between strategies < 0.3 (if higher, combining adds complexity
  without diversification — trade the best one solo)
- Monte Carlo 95th percentile combined drawdown must be < individual strategy worst-case
  (diversification must actually reduce tail risk, not just average it)

**If only 1 strategy survived:** Skip portfolio construction. Proceed to Stage 6 with the
single strategy. The diversification benefit is lost, but a single validated strategy is
better than a forced combination.

**Pass criteria:** Portfolio allocation weights documented. Combined equity curve and risk
metrics reviewed. Human sign-off.

---

### Stage 6: Paper Trading

**Duration:** Minimum 60 trading days (~3 calendar months).

**Execution:**
- Deploy surviving strategy(ies) using `record_paper_trade.py` with strategy name prefix
  `paper_research_<strategy_name>` (e.g., `paper_research_donchian_v1`)
- Each signal day: observe the live option chain, select strikes per the execution mapping,
  record entry via CLI with bid/ask at decision time
- Apply 1-point adverse slippage on entry (record in notes field)
- Monitor exits daily; log exit trades when signal triggers

**Spread-specific paper trading rules (v1 — directional credit spreads only):**

> **Council decision (2026-04-30):** Debit spreads and iron condors are deferred to
> post-validation. Paper trading runs credit spreads only for both bull and bear signals.
> Spread width is ATR-proportional, not fixed 200 points.

- Compute `spread_width = min(round_to_50(0.8 × ATR_40d), 500)`, floor 150. Record ATR_40d
  and computed width in the paper trade notes field at entry.
- For **bull put spreads** (bullish credit): sell the 15-delta put, buy the put `spread_width`
  points lower. Record both legs as a single paper trade with net credit.
- For **bear call spreads** (bearish credit): sell the 15-delta call, buy the call
  `spread_width` points higher. Record both legs as a single paper trade with net credit.
- Debit spreads (bull call / bear put): deferred. Do not paper-trade until VIX regime switch
  is validated post-backtest.
- Iron condors: deferred. Do not paper-trade until neutral-signal architecture is validated.

**Gate:**
- Realised Sharpe, win rate, and average trade duration must fall within 1 standard deviation
  of the walk-forward OOS distribution
- If any metric is >1.5 SD below backtest expectation, stop and diagnose — either execution
  model is wrong (slippage, fill assumptions) or a regime shift occurred
- Minimum 15 completed trades for directional strategies

**Pass criteria:** Paper trading report generated: trade log, equity curve, comparison to
backtest OOS distribution, slippage analysis (actual vs. modelled). Human review and explicit
"proceed to live" decision.

---

### Stage 7: Live Deployment (minimum viable size)

**Capital allocation:** 1 lot Nifty options per spread (lot size = 75 as of Nov 2024).
Maximum 2 concurrent positions (2 directional from different strategies — neutral/iron condor
deferred to post-validation). Total max risk at any point = 2 × ATR-proportional spread width
× 75. At ATR 400 (normal vol), width = 300 points → 2 × 300 × 75 = ₹45,000 max concurrent
exposure. Scales down in low-vol and up in high-vol — review position count limits if ATR
pushes width to 500-point cap.

**Scaling rule:** After 60 live trading days with metrics within 1 SD of paper results,
increase to 2 lots. After another 60 days, consider 3 lots. Never scale faster than this.

**Live kill criteria (in addition to Part 3 thresholds):**
- Trailing 60-day Calmar drops below 0.3 → reduce to 1 lot, review
- 3 consecutive losing trades where each loss > 1.5× average backtest loss → pause, diagnose
- Any single trade loss > 2× the spread width (should be impossible with defined-risk spreads,
  but if it happens, there's an execution error — halt immediately)

---

## Appendix A — Data Requirements Summary

| Data series              | Source    | Resolution | History needed | Storage     |
|--------------------------|-----------|-----------|----------------|-------------|
| Nifty 50 Index OHLC      | Upstox    | Daily     | 5 years        | Parquet     |
| Nifty 50 Index OHLC      | Upstox    | 15-min    | 5 years        | Parquet     |
| India VIX close           | Upstox    | Daily     | 5 years        | Parquet     |
| Nifty option chains (expired) | DhanHQ | 1-min (aggregate to daily) | 5 years | Parquet (Tier 2 only) |
| Nifty option chains (live)    | Upstox | Real-time (for paper/live) | Current   | In-memory (Tier 2 only) |

---

## Appendix B — Module Mapping (where code lives)

| Component                  | Target module               | New or existing |
|----------------------------|-----------------------------|-----------------|
| Regime classifier          | `src/strategy/regime.py`    | New             |
| Signal generators (swing)  | `src/strategy/signals/`     | New             |
| Spread selector            | `src/strategy/execution.py` | New             |
| Points-based backtester    | `src/backtest/points_bt.py` | New (Tier 1)    |
| Option spread backtester   | `src/backtest/spread_bt.py` | New (Tier 2)    |
| Walk-forward engine        | `src/backtest/walkforward.py` | New (Phase 1) |
| Monte Carlo simulator      | `src/backtest/montecarlo.py`| New             |
| Parameter sensitivity      | `src/backtest/sensitivity.py`| New            |
| Validation reports         | `src/backtest/reports.py`   | New             |

All modules follow `BrokerClient` protocol for live data access. Backtest modules operate on
Parquet data directly, no broker dependency.

---

## Appendix C — Verification Checklist (per strategy)

Use this checklist before declaring a swing strategy "passed." Every item must be explicitly
confirmed.

- [ ] Tier 1 (points-based) backtest complete and internally consistent
- [ ] OOS Calmar ≥ threshold (0.8 / 0.6 / 0.5)
- [ ] ≥60% of walk-forward windows net-positive
- [ ] Worst window DD < 2× median window DD
- [ ] MC 95th percentile DD < 1.5× observed max DD
- [ ] MC 99th percentile DD < 50% of allocated capital
- [ ] Parameter plateau: ≥60% of neighbours within 80% of optimal
- [ ] Plateau width ≥ 3 steps on every parameter axis
- [ ] No single regime cell contributes >80% of profit
- [ ] Profitable after 2-point round-trip slippage per leg
- [ ] Profitable after 4-point round-trip slippage (iron condors)
- [ ] Trade exclusion rate due to missing DhanHQ strikes < 20% (Tier 2 only; N/A if Tier 1 only)
- [ ] Tier 1 vs Tier 2 P&L gap documented (if Tier 2 data available)
- [ ] Visual chart inspection: no obviously spurious signals
- [ ] Human sign-off on validation report

---

## Completion Log

| Date | Stage | Outcome | Notes |
|------|-------|---------|-------|
| 2026-04-26 | — | — | Plan created. Pending Phase 0 gate. |
| 2026-04-27 | Stage 3 | Expanded | Stage 3 → two-tier (Tier 1: points, Tier 2: options). |
| 2026-04-27 | — | Split | Separated from STRATEGY_RESEARCH.md into standalone swing file. Investment strategies moved to INVESTMENT_STRATEGY_RESEARCH.md. |
| 2026-04-30 | Strategy 1 | Council review | 3-model council (GPT-5.4, Gemini 3.1 Pro, Grok 4; chairman: Claude Opus 4.6) reviewed Donchian roll mechanics, VIX regime switching, and spread width. Three unanimous decisions: (1) always-in → signal-in-only + 21-DTE management rule; (2) VIX credit/debit switch deferred post-validation, uniform credit spreads for Tier 2 backtest; (3) fixed 200pt width → ATR-proportional `min(round_to_50(0.8 × ATR_40d), 500)`, floor 150. Full decision: `docs/council/2026-04-30_donchian-roll-mechanics.md`. |
