# Cash-Secured Put — NiftyBees ETF v1

> **DEPRECATED 2026-04-25.** This strategy document has been superseded by
> [`docs/strategies/csp_nifty_v1.md`](csp_nifty_v1.md), which switches the option leg from
> NiftyBees options to Nifty 50 index options for liquidity reasons (OI typically < 1,000
> on NiftyBees monthlies; spreads > 5% of mid). NiftyBees ETF is retained as pledged
> collateral. Rules R1–R7 were also revised. See `DECISIONS.md` for the full rationale.
> This file is retained as a historical reference only — do not use it for any new work.

| Field       | Value                               |
|-------------|-------------------------------------|
| Name        | Cash-Secured Put on NiftyBees ETF   |
| Version     | v1                                  |
| Author      | Animesh Bhadra (archeranimesh)      |
| Date        | 2026-04-25                          |
| Status      | Paper trading — Phase 0.6           |
| Underlying  | NiftyBees ETF (`NSE_EQ|INF204KB14I2`) |
| Instrument  | NiftyBees monthly put options (NSE) |

---

## Purpose

First paper-trade strategy for NiftyShield. Designed to be structurally simple — one leg, three exit rules, no adjustments — so that every deviation between paper results and the Phase 1 backtest is attributable to data quality, cost modelling, or execution slippage, not strategy complexity. The simplicity is intentional; resist the urge to improve it during Phase 0.

---

## Entry Rule

**What:** Sell one put option on NiftyBees ETF (short put, 1 lot).

**When:** The Monday of the week that puts us in the 30–45 DTE window for the next monthly expiry. Monthly NiftyBees options expire on the last Thursday of each calendar month. If the target Monday is a market holiday, enter on the next trading day.

Do not enter if a CSP position for the current cycle is already open. One open position at a time, always.

**Strike selection:** Closest available strike to the 25-delta put, as reported by the live Dhan option chain (`/v2/optionchain`, Phase 1.10) or Upstox option chain fallback (Phase 0, current). If two strikes straddle 25-delta exactly, take the further OTM one (lower absolute delta) to reduce assignment probability.

**Entry time:** 10:00–10:30 AM IST. Allow the first 30 minutes of price discovery to settle before reading delta.

**Execution:** Limit order at the mid price of bid/ask at the time of entry. If unfilled after 5 minutes, improve the limit by ₹0.25 and resubmit once. If still unfilled, log the skipped cycle in `TODOS.md` with the reason (thin market, wide spread, etc.) and do not force a fill.

**Record the following at entry (required fields for `record_paper_trade.py`):** strike, expiry date, entry delta, entry mid price, actual fill price (mid − 0.25 as slippage haircut; see Sizing section), IV at entry, underlying spot price at entry, DTE at entry.

---

## Exit Rule

Three independent triggers. The first to fire wins. Monitor daily via `daily_snapshot.py` output.

**1. Profit target:** Close when the current option mark-to-market value has decayed to ≤50% of entry credit. Example: entered at ₹8.00 credit → close when option is worth ≤₹4.00. Retain the remaining 50% as realised gain rather than running to expiry.

**2. Time stop:** Close on or before 21 DTE, regardless of P&L, if neither profit target nor loss stop has fired. Do not carry into the final 3-week gamma-risk window.

**3. Loss stop:** Close immediately if the current option mark-to-market value reaches 2× the entry credit. Example: entered at ₹8.00 → close when option is worth ≥₹16.00. This is the maximum loss tolerance for this strategy.

**Exit execution:** Same limit-at-mid discipline as entry. For loss-stop triggers, tolerate up to ₹0.50 of slippage (wider spread is expected in stressed moves). Do not use market orders except on expiry-day closure.

**Expiry handling:** If the time stop fires on expiry day itself (DTE = 0), close before 3:20 PM IST to avoid last-minute gamma spikes and settlement risk.

---

## Adjustment Rule

**None.**

No rolling, no strike adjustments, no defensive buys. If the position is under pressure and no exit trigger has fired yet, hold until a trigger fires. If the urge to adjust arises, log the reason in `TODOS.md` as a strategy-discipline note — this is valuable data about your own behavioural edge — and then follow the spec.

This rule will be revisited when designing v2, informed by the paper-trade log.

---

## Position Sizing

**Quantity:** 1 lot. NiftyBees F&O lot size is currently 35 units; verify against the NSE lot-size schedule before every entry — lot sizes are revised periodically.

**Notional capital deployed:** Strike price × lot size. At a strike of ₹225 and lot size 35, this is ₹7,875 per lot. In a true cash-secured structure, this capital is reserved or the equivalent value is held in pledged NiftyBees units (already held in portfolio for margin).

**Slippage haircut:** Apply a ₹0.25/unit adverse fill assumption at both entry and exit legs when recording paper trades. This models a realistic single-tick miss on NiftyBees options, which are thinner than Nifty index options. The paper P&L should be calculated on (entry fill − 0.25) credited and (exit fill + 0.25) debited.

**Transaction cost model (applied to paper P&L calculations):**

| Cost            | Rate                                      |
|-----------------|-------------------------------------------|
| Brokerage       | ₹20 flat per order leg                    |
| STT             | 0.1% of sell-side premium                 |
| Exchange charge | 0.0345% of premium turnover               |
| GST             | 18% on brokerage + exchange charge        |
| SEBI fee        | ₹10 per crore of premium turnover         |
| Stamp duty      | 0.003% on buy side                        |

At ₹8.00 credit on 35 units (₹280 gross premium per lot), total transaction costs are approximately ₹50–60 per round trip. Net credit to target is roughly ₹220–230 per lot.

**Hard sizing cap:** Maximum 25% of total portfolio capital deployed in this strategy at any time. For a ₹5L notional portfolio, that is ₹1.25L — approximately 15 lots at current NiftyBees strike levels. Do not exceed this cap regardless of P&L history. During Phase 0 paper trading and the first 3 months of Phase 2 live trading, the cap is 1 lot, irrespective of capital availability.

---

## Expected P&L Distribution Prior

These are prior hypotheses to validate — not claims of edge. Write them down before running the backtest so you have a genuine prediction to compare against.

| Metric                      | Prior estimate            |
|-----------------------------|---------------------------|
| Monthly win rate            | 65–72%                    |
| Average winning month       | +₹180–240 per lot net     |
| Average losing month        | −₹280–380 per lot net     |
| Expected annual net return  | +12–18% on deployed capital (gross of cost) |
| Sharpe (annualised)         | 0.7–1.1                   |
| Max drawdown (1 lot, worst case) | −₹550–700 (2× credit on 2 consecutive losing cycles) |
| Worst single month          | −₹400 (loss stop × 1 lot, net of entry credit) |

These estimates are calibrated against generic 25-delta monthly put performance on Nifty-correlated underlyings in Indian markets, not against any NiftyBees-specific backtest. The Phase 1 backtest (task 1.7–1.8) is the authoritative source.

---

## Regimes Expected to Work In

**High IV (IVR > 50):** Premium richness compensates for elevated move probability. Preferred entry environment. Target delta stays at 25 — do not chase higher delta to inflate credit.

**Neutral to mildly bullish market:** Time decay is the primary P&L driver. Strategy is structurally long theta, short gamma.

**Range-bound:** Ideal. No directional stress. Both profit target and time stop can fire cleanly.

**Post-spike IV mean reversion:** If IV has just collapsed from a spike, entering CSP captures the elevated IV decay before it fully normalises.

---

## Regimes Expected to Fail In

**Sustained downtrend ≥ 8% within the trade window:** NiftyBees put goes deep ITM, loss stop fires. The 2× loss cap limits damage but the strategy has no edge in a trending bear.

**Rapid IV expansion after entry (event-driven spike):** Even without a large directional move, a VIX jump of 30%+ can take a 25-delta put to 45–50 delta within days. Mark-to-market loss accumulates quickly. Loss stop may fire without significant underlying movement.

**Low IV at entry (IVR < 20):** Premium collected is structurally thin. The risk/reward degrades to a point where the expected value is near zero after costs. Consider skipping the cycle if IVR < 20 at entry time. This is a preference guideline, not a hard rule in v1 — log the IVR at every entry so the data is available for v2 calibration.

**Assignment risk near expiry:** If the trade is carried past 21 DTE (time stop not respected), the short gamma exposure accelerates. This is addressed by the time stop rule, not an adjustment rule.

---

## Kill Criteria

These conditions trigger an **immediate pause** on the strategy — no new entries. Existing position is managed to completion under the standard exit rules (not panic-closed). Within 30 days of triggering, review and decide: resume, modify spec → v2, or retire.

1. **Trailing 6-month realised P&L < 0** (across all completed cycles in the trailing 180 days).

2. **Maximum drawdown on deployed capital > 10%** — for 1 lot at typical ₹8,000 notional, this is approximately ₹800 cumulative loss across all cycles in any rolling 3-month window.

3. **Rolling 3-month Z-score of realised vs backtest |Z| > 2.0 for 4 consecutive weeks** — strategy behaviour has structurally diverged from the backtested model.

4. **Three consecutive execution errors** — wrong-side fill, missed exit, fat-finger entry. Each error must be individually logged in `TODOS.md` with root cause before the count resets.

5. **NiftyBees options market structure degradation** — if the average daily open interest in NiftyBees puts falls below 500 contracts or bid/ask spread exceeds 15% of mid price consistently across 3 consecutive entry opportunities, skip cycles and review instrument viability. NiftyBees options are thinner than Nifty index options; liquidity is a real constraint.

---

## Variance Threshold for Live Deployment

Before Phase 2 live deployment is authorised (task 2.2), the following must hold:

**Condition:** Monthly P&L distribution from paper trading must satisfy |Z| ≤ 1.5 relative to the Phase 1 backtest distribution, measured over the paper-trade window.

**Minimum paper-trade duration:** 8 weeks covering at least 2 full monthly expiry cycles. Prefer 4+ cycles before going live if calendar permits.

**Z-score formula:** `Z = (paper_mean − backtest_mean) / backtest_std`

**Bias adjustment (required before computing Z):** The Black-Scholes delta used for backtesting (Phase 1.6a) will systematically differ from the Dhan live-chain delta used for paper strike selection by approximately 0.5–2 delta points. Compute this structural bias by re-running the backtest with strike selection forced to match the actual paper-traded strikes. Subtract this bias from the paper-vs-backtest gap before evaluating Z. If the bias-adjusted |Z| still exceeds 1.5, the backtest requires recalibration before live deployment — do not override this gate.

**Fail path:** If Z fails after 4 cycles, audit in order: (1) cost model completeness, (2) slippage assumption vs actual paper fills, (3) entry/exit rule divergence between code and paper execution log, (4) BS-vs-Dhan delta drift magnitude. Fix, re-run 1.8, re-evaluate.

---

## Backtest Results

*Section to be populated after Phase 1 tasks 1.7–1.8 are complete.*

| Field               | Value     |
|---------------------|-----------|
| Run ID              | TBD       |
| Backtest window     | TBD       |
| Net annualised return | TBD     |
| Sharpe              | TBD       |
| Sortino             | TBD       |
| Max drawdown (depth)| TBD       |
| Max drawdown (duration) | TBD   |
| Monthly win rate    | TBD       |
| Worst month         | TBD       |
| Git SHA             | TBD       |

---

## Variance Check Results

*Section to be populated after Phase 1 task 1.11 is complete.*

| Field                        | Value  |
|------------------------------|--------|
| Paper-trade window           | TBD    |
| Paper mean monthly return    | TBD    |
| Backtest mean (same window)  | TBD    |
| BS-vs-Dhan bias adjustment   | TBD    |
| Z-score (bias-adjusted)      | TBD    |
| Pass / Fail                  | TBD    |
| Decision                     | TBD    |

---

## Open Questions for v2

These are not blockers for v1. Log here; revisit when designing v2 after sufficient paper-trade data:

- Should IVR < 20 be a hard skip rule or just a preference? Calibrate after 6+ cycles.
- Is a 25-delta entry optimal for NiftyBees specifically, or does the thinner liquidity favour a wider OTM target (20-delta) to reduce assignment risk and improve fills?
- Does NiftyBees options liquidity support 21 DTE exit reliably, or does the time stop need to move to 25–28 DTE to ensure fills?
- If NiftyBees options remain thin, should v2 switch to Nifty 50 index puts (using NiftyBees as pledged margin collateral) to gain liquidity?
