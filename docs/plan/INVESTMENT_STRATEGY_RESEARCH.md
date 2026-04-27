# NiftyShield — Investment Strategy Research Pipeline

| Field        | Value                                                     |
|--------------|-----------------------------------------------------------|
| Author       | Animesh Bhadra (archeranimesh)                            |
| Date         | 2026-04-27                                                |
| Status       | Draft — pending Phase 0 gate (BACKTEST_PLAN.md §0.8)      |
| Signal source| Nifty 50 Index spot (`NSE_INDEX|Nifty 50`), Nifty PE ratio (NSE) |
| Execution    | NiftyBees ETF (buy/sell/hold)                             |
| Data sources | Upstox (Nifty/NiftyBees OHLC, VIX), NSE (PE data), AMFI (liquid fund NAV) |

> **Purpose:** Research plan for 3 systematic long-term investment strategies on NiftyBees ETF.
> Holding periods exceed 1 year, signals use weekly/monthly bars, and rebalancing is quarterly
> at most. The objective is not to capture individual price swings but to systematically time
> exposure to Indian large-cap equity, reducing drawdowns relative to buy-and-hold while
> capturing the bulk of the long-term compounding.
>
> **Execution instrument:** NiftyBees ETF exclusively. No options, no futures. NiftyBees is
> already pledged as collateral for the Finideas portfolio — these strategies govern *how much*
> NiftyBees to hold and *when* to adjust, not whether to hold it. The simplicity is deliberate:
> long-term strategies with options overlays add IV risk and roll complexity that destroy the
> primary benefit of a low-maintenance investment approach.
>
> **Relationship to swing strategies:** The swing strategies
> ([SWING_STRATEGY_RESEARCH.md](SWING_STRATEGY_RESEARCH.md)) and investment strategies (this
> file) run on separate capital pools with no interaction. The swing strategies use index
> options on Nifty for short-term directional/neutral bets. The investment strategies manage
> the underlying NiftyBees ETF position that exists *regardless* of the swing strategies. If
> both are running, NiftyBees serves a dual purpose — collateral for Finideas + the investment
> portfolio asset — but the position sizing for each is independent.
>
> **Relationship to BACKTEST_PLAN.md:** This plan runs *inside* the backtest engine built in
> Phase 1 of BACKTEST_PLAN.md, sharing infrastructure with the swing strategies but using
> different signal generators and operating on different timeframes. Do not start this work
> until Phase 1 gate (§1.12) is passed.
>
> **Backtesting data:** All strategies in this document use Nifty 50 Index spot OHLC (daily
> and weekly) plus NiftyBees NAV/price data from Upstox. No option chain data required — this
> entire document uses points-based / NAV-based backtesting only. The simplicity of the data
> requirement is a feature, not a limitation.
>
> **Prerequisite reading:** `BACKTEST_PLAN.md` (engine architecture), `CONTEXT.md` (codebase
> state), `REFERENCES.md` (instrument keys), `SWING_STRATEGY_RESEARCH.md` §Part 2 (shared
> validation framework: regime engine, train/test split, Monte Carlo design, parameter
> sensitivity protocol — this document adapts those with modified thresholds, not replaces them).

---

## Design Constraint: Why ETF, Not Futures or Options

For a >1 year holding period, futures require quarterly rolls (each with slippage and cost of
carry), and options require continuous roll management plus IV exposure that overwhelms the
signal edge on monthly timeframes. NiftyBees is a hold-and-forget instrument with ₹0 roll
cost, near-zero tracking error to Nifty 50, and the collateral pledge benefit. The only
execution cost is brokerage + STT on buy/sell, which at quarterly rebalancing frequency is
negligible relative to the position size.

**Position sizing model:** Strategies below output a target allocation percentage (0%, 50%,
100% of the designated NiftyBees investment pool). Transitions between levels happen at the
next quarterly rebalancing date or on a signal trigger, whichever comes first. No intraday
execution precision required — place the order anytime during market hours on the rebalancing
day.

---

## Part 1 — Strategy Selection

### Strategy 1: 10-Month SMA Trend Filter (Faber-style)

**Core hypothesis:** Nifty 50 exhibits multi-year secular trends driven by earnings growth
cycles, RBI rate regimes, and global EM capital flows. The 200-day (≈10-month) simple moving
average has historically separated "in trend" from "correcting" with a favourable hit rate on
Nifty because these secular forces are slow-moving and persistent. The strategy is not trying
to time tops or bottoms — it is trying to avoid the bulk of bear markets (2008, 2020 March,
2022 H1) while staying invested during the 70%+ of the time Nifty is above its long-term
trend.

This is the most well-documented tactical allocation rule in quantitative finance (Faber 2007,
replicated across 100+ years of US data and multiple global markets). Its persistence comes
from the behavioural mechanism: institutional mandates and retail herding create trends that
overshoot in both directions, and a simple trend filter exploits this without requiring any
forecast of when the overshoot ends.

**Signal source:** Nifty 50 Index monthly close vs. 10-month SMA.

**Timeframe:** Monthly bars. Checked on the last trading day of each month. Not weekly —
weekly crossovers on a 10-month SMA generate whipsaws during sideways markets that destroy
the rule's simplicity advantage.

**Parameters (2):**

| Parameter               | Initial | Sweep range | Step |
|-------------------------|---------|-------------|------|
| SMA lookback (months)   | 10      | 8–14        | 1    |
| Re-entry delay (months) | 0       | 0–2         | 1    |

**Entry:** Allocate 100% to NiftyBees when Nifty monthly close > N-month SMA. Reduce to 0%
(fully exit to cash/liquid fund) when Nifty monthly close < N-month SMA. The re-entry delay
parameter optionally requires N consecutive months above the SMA before re-entering — this
reduces whipsaws during the transition from bear to bull but delays re-entry (costs
compounding during the initial recovery move).

**Exit:** Monthly check. If Nifty closes below the SMA, exit on the first trading day of the
next month. No intraday urgency — the signal is monthly; a 1-day delay is noise.

**Cash allocation when out:** Park in liquid fund (existing MF infrastructure in `src/mf/`
can track this). The return on cash is not zero — it earns ~6–7% annualised in a liquid fund,
which partially offsets missed equity returns during whipsaw exits.

**Works in:** Secular bear markets and extended corrections. The 2008 crash, 2020 COVID drop,
and 2022 correction would all have triggered exits within 1–2 months of the top, avoiding
50–70% of the drawdown. Also works during the subsequent recovery — re-entry happens 1–3
months after the bottom, capturing the bulk of the V-shaped recovery.

**Fails in:** Choppy sideways markets where Nifty oscillates around the SMA for months.
2015–2016 and late 2019 are canonical failure periods on Nifty — multiple whipsaw signals
that generate small losses on each round-trip. The cumulative whipsaw cost can reach 5–8% of
portfolio value over a 12-month chop period. The re-entry delay parameter is the primary
mitigation.

---

### Strategy 2: Dual Momentum (Absolute + Relative)

**Core hypothesis:** Combining absolute momentum (is Nifty trending up in isolation?) with
relative momentum (is Nifty outperforming a risk-free alternative?) produces a more robust
allocation signal than either alone. Absolute momentum avoids bear markets; relative momentum
avoids periods where equity risk is not compensated relative to fixed income. The intersection
of both conditions is a higher-quality "risk-on" signal.

This is Antonacci's (2014) dual momentum framework, adapted to a single-asset context.
In the original framework, relative momentum compares across asset classes (US equity vs.
international equity vs. bonds). Here, relative momentum compares Nifty total return against
the 1-year T-bill rate (or liquid fund return) — the opportunity cost of equity exposure.

**Signal source:** Nifty 50 Index total return (price + dividend yield proxy) vs. its own
trailing return and vs. risk-free rate.

**Timeframe:** Monthly bars. Evaluated on the last trading day of each month.

**Parameters (3):**

| Parameter                          | Initial | Sweep range | Step |
|------------------------------------|---------|-------------|------|
| Absolute momentum lookback (months)| 12      | 6–15        | 3    |
| Relative momentum lookback (months)| 12      | 6–15        | 3    |
| Risk-free rate proxy (annualised)  | 7%      | 5%–8%       | 1%   |

**Entry rules:**
- **Absolute momentum check:** Nifty trailing N-month return > 0%. If no, stay in cash.
- **Relative momentum check:** Nifty trailing N-month return > risk-free rate (annualised,
  converted to N-month equivalent). If no, stay in cash.
- **Both pass:** Allocate 100% to NiftyBees.
- **Either fails:** Allocate 0% (exit to liquid fund).

This is stricter than Strategy 1 (SMA filter). The SMA filter only asks "is the trend up?"
Dual momentum also asks "is the trend up *enough* to compensate for equity risk?" In a
low-return, low-vol uptrend (Nifty drifting up at 4% annualised), the SMA filter stays
invested but dual momentum exits — correctly, because 4% equity return with 12% drawdown
risk is worse than 7% risk-free.

**Exit:** Monthly check. When either momentum condition fails, exit on the first trading day
of the next month.

**Works in:** Extended bear markets and flat/low-return periods. The dual filter catches
both the 2008/2020 drawdowns (absolute momentum fails) and the 2018–2019 period where Nifty
returned ~2–3% while liquid funds returned 7% (relative momentum fails). Strategy 1 would
stay invested through the latter; Strategy 2 correctly exits.

**Fails in:** V-shaped recoveries. The 12-month lookback means absolute momentum stays
negative for months after the bottom (the trailing 12-month return includes the crash). Re-
entry is slow — potentially 6–9 months after the trough vs. 1–3 months for the SMA filter.
The cost is significant: the March 2020 to March 2021 recovery returned ~80% on Nifty, and
a 12-month absolute momentum filter would have missed the first 30–40% of that move.

---

### Strategy 3: Nifty PE Band Rebalancing (Value-Weighted)

**Core hypothesis:** Nifty's trailing PE ratio mean-reverts over multi-year cycles. When the
PE is below its long-term median (~20–22 on Nifty 50 trailing), expected forward 3-year
returns are historically elevated. When PE is stretched above ~25, forward returns compress
and drawdown risk increases. A systematic allocation rule that increases equity exposure at
low PE and reduces at high PE captures this mean-reversion without requiring a timing call on
when the reversion happens.

This is not a market timing strategy — it is a value-weighted allocation rule. It will
underperform buy-and-hold during bubble extensions (late 2007, late 2024) and outperform
during the corrections that follow. Over a full cycle, the value-weighted allocation earns a
higher geometric return because it reduces exposure before large drawdowns that destroy
compounding.

**Signal source:** Nifty 50 trailing PE ratio. Published by NSE daily. Historical PE data
available from NSE website as CSV download (going back to 1999).

**Timeframe:** Monthly. PE changes slowly — daily rebalancing adds transaction cost without
improving signal quality.

**Parameters (3):**

| Parameter                      | Initial | Sweep range | Step |
|--------------------------------|---------|-------------|------|
| Low PE threshold               | 18      | 15–20       | 1    |
| High PE threshold              | 25      | 23–28       | 1    |
| Intermediate allocation (%)    | 70%     | 50%–80%     | 10%  |

**Allocation rules:**

| Nifty PE (trailing) | NiftyBees allocation |
|---------------------|----------------------|
| < Low threshold     | 100%                 |
| Low – High          | Intermediate %       |
| > High threshold    | 30%                  |

Transitions happen at quarterly rebalancing dates only — not on every monthly PE change. The
quarterly cadence prevents over-trading during PE oscillation around thresholds.

**Why not 0% at high PE:** NiftyBees is pledged as collateral. Exiting entirely removes
the margin benefit for Finideas. The 30% floor ensures minimum collateral is always
available. This is a portfolio-level constraint, not a signal design choice.

**PE data reliability:** Trailing PE is backward-looking and can be distorted by one-time
earnings events (e.g., TCS buyback, Reliance Jio reclassification). Use the NSE-published
Nifty PE, which aggregates across 50 constituents and is relatively robust to single-stock
distortions. Do NOT compute PE independently from individual stock data — aggregation
methodology differences will create phantom signals.

**Works in:** Multi-year cycles. The 2008–2009 low-PE period (PE ~12–14) followed by the
2010–2014 recovery is the canonical win case. The 2020 March crash briefly pushed PE to ~18
(earnings hadn't yet fallen to reflect COVID), and the subsequent recovery rewarded full
allocation. The 2003–2007 cycle (PE expansion from 14 to 28) would have systematically
reduced allocation as PE climbed, then reloaded after the 2008 crash.

**Fails in:** Sustained PE expansion regimes where earnings growth justifies higher multiples
(e.g., 2020–2024 where Nifty PE stayed 22–26 while earnings grew 15%+ CAGR). The strategy
would hold 70% or 30% through a period that buy-and-hold captured fully. Also fails if
India's structural PE re-rates permanently higher (as has arguably happened vs. pre-2015
levels) — the thresholds would need a one-time recalibration.

---

### Confidence Ranking

**1. 10-Month SMA Trend Filter (highest).** The most validated single rule in tactical
allocation literature. Faber (2007) tested it across US equities, international equities,
commodities, REITs, and bonds over 100+ years. Applied to Nifty, the FII flow cycle and
RBI rate cycle create secular trends that a monthly SMA captures well. The risk is whipsaw
cost, which is bounded and quantifiable. The simplicity is the edge — fewer parameters means
fewer ways to overfit.

**2. Dual Momentum (moderate).** Adds the relative momentum filter, which is theoretically
sound (risk-adjusted return comparison), but the additional parameter (risk-free rate proxy)
and the slower re-entry after V-reversals reduce the practical advantage over the SMA filter.
The value-add is concentrated in flat/low-return periods — useful if those periods are
frequent, but Nifty has historically spent limited time in the "trending up slowly" regime
where dual momentum differentiates.

**3. PE Band Rebalancing (lowest but complementary).** Structurally uncorrelated with
momentum-based signals (mean-reversion vs. trend-following), which makes it valuable for
portfolio construction even if standalone performance is mediocre. The risk is that PE
thresholds need periodic recalibration as India's market structure evolves. Included because
the combination of a momentum filter (Strategy 1 or 2) with a value filter (Strategy 3)
is more robust than either alone — momentum catches crashes, value catches recoveries.

---

## Part 2 — Validation Design

The validation framework from the swing strategy pipeline
([SWING_STRATEGY_RESEARCH.md](SWING_STRATEGY_RESEARCH.md) §Part 2) provides the foundational
methodology: regime classification, train/test split, walk-forward optimisation, Monte Carlo
simulation, parameter sensitivity protocol, and the Calmar ranking metric. This section
documents only the **modifications** specific to investment strategies. Read the swing
document's Part 2 first — everything there applies here unless overridden below.

### Regime Engine

Uses the same 3×3 regime classifier (trend slope + VIX percentile) defined in the swing
pipeline. Investment strategies use regime tags for decomposition analysis (checking whether
profits concentrate in a single cell), not for trade filtering — the signals operate on
monthly bars and the regime engine tags daily bars, so the mapping is: each month inherits the
regime tag of its last trading day.

### Train/Test Split

Same split point (1 January 2024) as swing strategies. For monthly-bar strategies, the
training set contains ~48 monthly observations (~2–4 allocation changes per year, so 8–16
total transitions). This is statistically thin — acknowledged but unavoidable with 5-year
history. If PE data from NSE extends back to 1999, use the full ~25-year history for
Strategy 3 and extend the training set to pre-2020 for all three strategies (gives 20+ years
of data and 50+ transitions for the SMA filter, which is adequate).

### Walk-Forward Configuration (modified)

| Parameter               | Value | Rationale                                   |
|-------------------------|-------|---------------------------------------------|
| Training window         | 36 months (3 years) | Full market cycle including at least one correction + recovery |
| Step size               | 12 months (1 year)  | Annual re-optimisation — quarterly is too frequent for monthly signals |
| Min trades per window   | 2 (allocation changes are infrequent by design) | 2 transitions per year is typical |
| Insufficient-window cap | ≤25% of total windows | Same as swing                   |

### Monte Carlo (modified)

Same 10,000 iteration bootstrap, but the "trade" unit is a full allocation period (date of
entry to date of exit), not a single day. This is structurally correct for investment
strategies because the allocation periods are the independent return units — individual days
within an allocation period are serially correlated.

### Ranking Metric

Walk-forward median Calmar ratio, same as swing strategies. For investment strategies,
annualised return is computed on the full equity curve (including cash returns during
out-of-market periods), and max drawdown is measured peak-to-trough on the invested capital
only (not on the cash portion).

---

## Part 3 — Failure Conditions

These are hard kills, adapted from the swing pipeline (SWING_STRATEGY_RESEARCH.md §Part 3)
with relaxed thresholds reflecting the structural differences of long-term strategies: fewer
trades, chunkier drawdowns, monthly rebalancing latency.

| Condition | Threshold | Rationale |
|-----------|-----------|-----------|
| OOS Calmar | < 0.3 (lower bar than swing — long-term strategies have deeper drawdowns by nature) | Must beat Nifty buy-and-hold Calmar (~0.4–0.7) on a risk-adjusted basis; 0.3 is the floor |
| Walk-forward consistency | >50% windows net-negative (relaxed from 40% — fewer windows, higher variance) | With 36-month windows and 12-month steps, there are only 3–4 OOS windows; >50% negative means ≤1 positive window |
| MC 95th percentile DD | > 2× observed max DD (relaxed from 1.5× — monthly rebalancing has inherently chunkier drawdowns) | Monthly exit means you ride the first month of a crash; DD variance is structurally higher |
| Parameter sensitivity | Plateau width < 2 steps (relaxed from 3 — only 2–3 parameters with narrow sweep ranges) | SMA lookback 8–14 has only 7 values; requiring 3-step plateau from a 7-value sweep is unreasonable |
| Regime concentration | >90% of profit from one regime (relaxed from 80% — investment strategies legitimately profit from secular uptrends) | If 100% of profit is from "trending-up", that is the regime the strategy is designed for — but 90%+ with zero contribution from recovery periods is fragile |
| Transaction cost sensitivity | Unprofitable after ₹100 per round-trip (NiftyBees brokerage + STT + impact cost on large qty) | Much lower bar than option slippage — ETF execution costs are trivial relative to position size |

### Buy-and-Hold Comparison (mandatory — not required for swing)

Every investment strategy must be compared to a simple buy-and-hold NiftyBees baseline over
the same period. The strategy must demonstrate either (a) higher risk-adjusted return (Calmar
or Sharpe), OR (b) materially lower max drawdown (>30% reduction) with no more than 20%
underperformance in total return. If the strategy neither improves risk-adjusted return nor
reduces drawdown meaningfully, it adds complexity without value — abandon it regardless of
other metrics.

---

## Part 4 — Implementation Sequence

These stages run in parallel with (but independently of) the swing strategy stages. They share
the same backtest engine infrastructure (BACKTEST_PLAN.md Phase 1) but use different signal
generators and operate on different timeframes.

### Stage I-0: Data Infrastructure

**Work:**
- Nifty 50 Index weekly + monthly OHLC (derived from daily data already in swing Stage 0)
- NiftyBees ETF daily close (from Upstox, instrument key in REFERENCES.md)
- Nifty PE ratio monthly series (from NSE historical data CSV download — verify availability
  and format; if available back to 1999, use the full series)
- Risk-free rate series: 364-day T-bill yield OR liquid fund NAV series (from AMFI, already
  in `src/mf/` infrastructure)
- Storage: same Parquet convention as swing strategies, partitioned by instrument + date

**Gate:** NiftyBees NAV tracks Nifty 50 within ±0.5% tracking error over any rolling 1-year
period. PE data has <2% missing months (fill with previous value for missing months). Risk-free
rate series is complete for the full backtest period.

**Pass criteria:** Data integrity report reviewed. PE data visually cross-checked against
published NSE PE charts for known inflection points (2008 crash PE ~12, 2020 crash PE ~18,
2024 peak PE ~24).

---

### Stage I-1: Signal Generators (one per strategy, sequential)

**Work:**
- I-1a: 10-month SMA signal → outputs monthly allocation % (0% or 100%)
- I-1b: Dual momentum signal → outputs monthly allocation % (0% or 100%)
- I-1c: PE band signal → outputs quarterly allocation % (30%, 70%, or 100%)

**Gate per signal:** Run on full training set, generate allocation log (date, PE/SMA value,
allocation %, regime tag). Visual overlay on Nifty price chart — allocation changes must
visually correspond to known market events.

**Pass criteria:** Allocation change count within expected range (SMA: 2–4/year, Dual
momentum: 2–4/year, PE bands: 1–3/year). If any strategy produces >6 allocation changes
per year, the signal is too noisy for a >1 year investment approach.

---

### Stage I-2: Points-Based Backtest (Tier 1 only)

**Work:**
- P&L in NiftyBees NAV terms: entry NAV × (exit NAV / entry NAV − 1) × allocation %
- Include cash return (liquid fund rate) during out-of-market periods
- Transaction costs: ₹100 per round-trip (conservative estimate for ₹5L+ NiftyBees orders)
- Generate equity curve, drawdown chart, buy-and-hold comparison

**Gate:** Run all three strategies through the training period. Generate:
- Equity curve vs buy-and-hold (single chart, both lines)
- Drawdown chart (strategy DD vs buy-and-hold DD)
- Summary: total return, CAGR, max DD, Calmar, time-in-market %, number of round-trips

**Pass criteria:** Backtester is internally consistent (no NAV jumps on non-rebalancing days,
cash return applied correctly during out-of-market periods, transaction costs deducted at each
round-trip). Visual inspection: equity curve should track buy-and-hold during bull periods and
diverge positively during corrections.

---

### Stage I-3: Walk-Forward + Validation

Same protocol as swing Stage 4 (SWING_STRATEGY_RESEARCH.md §Stage 4), with the adapted
thresholds from Part 3 of this document. Sequential: complete one strategy before starting
the next. Order: Strategy 1 (SMA) → Strategy 2 (Dual Momentum) → Strategy 3 (PE Bands).

**Pass criteria:** Strategy validation report with: equity curve, allocation log, Monte Carlo
distribution chart, parameter sensitivity heatmap, regime decomposition table, buy-and-hold
comparison. Human review and sign-off required.

---

### Stage I-4: Paper Trading

**Duration:** Minimum 6 months. Quarterly rebalancing means only 2 rebalance events in 6
months; extend to 12 months if the first 2 events are insufficient for statistical comparison
to backtest.

**Execution:**
- Record NiftyBees allocation changes using `record_paper_trade.py` with strategy name prefix
  `paper_invest_<strategy_name>` (e.g., `paper_invest_sma_v1`)
- On each monthly check day: record the signal value (SMA level, momentum return, PE value),
  the allocation decision, and the NiftyBees NAV at decision time
- On rebalancing days: record the trade (buy/sell quantity, execution price, costs)

**Gate:**
- Allocation decisions match what the backtest would have produced for the same market
  conditions (verify by running the signal generator on live data and comparing)
- Execution slippage (difference between decision-time NAV and actual fill) is within ₹0.50
  per unit (NiftyBees is highly liquid — slippage above this indicates execution problems)

**Pass criteria:** Paper trading report: allocation log, equity curve, comparison to backtest
OOS distribution. Human review and explicit "proceed to live" decision.

---

### Stage I-5: Live Deployment

**Capital allocation:** Start with ₹5L NiftyBees allocation under the validated strategy.

**Monitoring:** Quarterly review — compare actual allocation changes and returns to backtest
envelope.

**Scaling:** No scaling rule needed — the allocation percentage governs sizing automatically.
To increase capital, simply increase the designated NiftyBees investment pool and the strategy
adjusts.

**Live kill criteria:**
- Trailing 12-month Calmar drops below 0.2 → review strategy parameters against current
  regime
- 2 consecutive allocation changes that are immediately reversed at the next check (back-to-
  back whipsaws) → pause and compare to backtest whipsaw frequency
- Strategy produces >6 allocation changes in any 12-month period → signal has degraded;
  suspend and investigate

---

## Appendix A — Data Requirements Summary

| Data series              | Source    | Resolution | History needed | Storage     |
|--------------------------|-----------|-----------|----------------|-------------|
| Nifty 50 Index OHLC      | Upstox    | Daily (derive weekly/monthly) | 5–25 years | Parquet |
| NiftyBees ETF close       | Upstox    | Daily     | 5 years (ETF inception ~2002) | Parquet |
| Nifty 50 trailing PE      | NSE CSV   | Daily     | 25 years (available from 1999) | Parquet |
| Risk-free rate (364d T-bill OR liquid fund NAV) | RBI / AMFI | Monthly | 10 years | Parquet |
| India VIX close           | Upstox    | Daily     | 5 years (shared with swing) | Parquet |

---

## Appendix B — Module Mapping (where code lives)

| Component                        | Target module                        | New or existing |
|----------------------------------|--------------------------------------|-----------------|
| SMA trend filter signal          | `src/strategy/signals/sma_filter.py` | New             |
| Dual momentum signal             | `src/strategy/signals/dual_mom.py`   | New             |
| PE band rebalancing signal       | `src/strategy/signals/pe_band.py`    | New             |
| NiftyBees allocation backtester  | `src/backtest/allocation_bt.py`      | New             |
| PE data loader (NSE CSV)         | `src/instruments/pe_loader.py`       | New             |

Shared infrastructure with swing strategies (defined in
[SWING_STRATEGY_RESEARCH.md](SWING_STRATEGY_RESEARCH.md) Appendix B):
`src/strategy/regime.py`, `src/backtest/walkforward.py`, `src/backtest/montecarlo.py`,
`src/backtest/sensitivity.py`, `src/backtest/reports.py`.

All modules follow `BrokerClient` protocol for live data access. Backtest modules operate on
Parquet data directly, no broker dependency.

---

## Appendix C — Verification Checklist (per strategy)

Use this checklist before declaring an investment strategy "passed."

- [ ] OOS Calmar ≥ 0.3
- [ ] ≥50% of walk-forward windows net-positive
- [ ] MC 95th percentile DD < 2× observed max DD
- [ ] Parameter plateau: ≥60% of neighbours within 80% of optimal
- [ ] Plateau width ≥ 2 steps on every parameter axis
- [ ] No single regime cell contributes >90% of profit
- [ ] Profitable after ₹100 round-trip transaction cost
- [ ] Buy-and-hold comparison: either higher Calmar OR >30% drawdown reduction with <20% return underperformance
- [ ] Cash return during out-of-market periods included in equity curve
- [ ] Visual chart inspection: allocation changes overlay on Nifty price chart
- [ ] Human sign-off on validation report

---

## Completion Log

| Date | Stage | Outcome | Notes |
|------|-------|---------|-------|
| 2026-04-27 | — | Created | Split from STRATEGY_RESEARCH.md. 3 investment strategies (SMA, dual momentum, PE bands) on NiftyBees ETF, >1yr horizon. |
