# Cash-Secured Put — Nifty 50 v1

| Field                    | Value                                                                        |
|--------------------------|------------------------------------------------------------------------------|
| Name                     | Cash-Secured Put on Nifty 50                                                 |
| Version                  | v1                                                                           |
| Author                   | Animesh Bhadra (archeranimesh)                                               |
| Date                     | 2026-04-25                                                                   |
| Status                   | Paper trading — Phase 0.6                                                    |
| Underlying (option leg)  | Nifty 50 index (`NSE_INDEX|Nifty 50`, Dhan: security ID `13`, segment `IDX_I`) |
| Collateral               | NiftyBees ETF (`NSE_EQ|INF204KB14I2`) — already pledged                     |
| Instrument               | Nifty 50 monthly put options (NSE)                                           |

> **Instrument distinction:** The short put leg is written on the **Nifty 50 index** for
> liquidity. The pledged collateral backing the position is **NiftyBees ETF** units already
> held in the portfolio. NiftyBees tracks Nifty 50 with ≤0.02% annual tracking error, making
> it a near-perfect collateral proxy. The "cash-secured" framing is accurate at the portfolio
> level: the operator's ₹1.2 cr+ collateral pool (₹75L MF + ₹30L bonds + ₹15.5L NiftyBees)
> more than covers the notional of any single lot. The correlated-collateral concern was
> reviewed 2026-04-25 and closed — no margin concern given the pool size and instrument
> correlation.

> **Predecessor:** This document supersedes `docs/strategies/csp_niftybees_v1.md` (now
> DEPRECATED). The underlying was switched from NiftyBees options to Nifty 50 index options
> on 2026-04-25; see `DECISIONS.md` for rationale. NiftyBees options were liquid enough to
> specify a strategy but too thin (OI typically < 1,000 on monthlies, spreads > 5% of mid)
> to trade with confidence.

---

## Purpose

First paper-trade strategy for NiftyShield. Designed to be structurally simple — one leg,
three exit rules, no adjustments — so that every deviation between paper results and the
Phase 1 backtest is attributable to data quality, cost modelling, or execution slippage, not
strategy complexity. The simplicity is intentional; resist the urge to improve it during
Phase 0.

---

## Entry Rule

**What:** Sell one put option on the Nifty 50 index (short put, 1 lot = 65 units).

**When:** The Wednesday after the most recent monthly expiry, provided this Wednesday falls
within the 30–45 DTE window for the *next* monthly expiry. Monthly Nifty options expire on
the **last Tuesday of each calendar month** (changed from last Thursday in 2025; verify
against the NSE lot-size and expiry schedule before each entry). If the target Wednesday is
a market holiday, enter on the next trading day.

Do not enter if a CSP position for the current cycle is already open. One open position at a
time, always.

**IVR filter (R3 — specified, not yet enforced):** Skip the cycle if India VIX < 12 OR IVR
< 25 (trailing 252-day percentile of India VIX). Rationale: short premium at the floor of
IV has near-zero positive expectancy after costs, with unbounded vol-expansion risk on any
shock. *This rule is specified but cannot yet be enforced in backtesting or paper-trade
monitoring — India VIX historical data ingestion does not yet exist in the repo. A Phase 1
ingestion sub-task is required before R3 can be applied to the backtest engine (see
BACKTEST_PLAN.md Phase 1 notes). Until then: log India VIX level and IVR at every entry so
the data is available for R3 calibration once the pipeline is live.*

**Event filter (R4 — specified, not yet enforced):** Skip the cycle if any of the following
falls inside the trade DTE window: Union Budget (Feb 1 ± 1 trading day), RBI MPC
announcement day, election-result day. Indian-market tail-event premium is not adequately
priced into 22-delta (and was not at 25-delta either). *Enforcement depends on `src/market_calendar/events.yaml`
(BACKTEST_PLAN.md task 3.3 — not yet created). Until 3.3 lands, document any event exposure
in the trade log for each cycle.*

**Strike selection:** Closest available strike to the **22-delta put** (council default,
2026-05-02 — supersedes 25-delta; see `docs/council/2026-05-02_csp-entry-delta-v2.md` and
`DECISIONS.md`), as reported by the live Dhan option chain (`/v2/optionchain`, Phase 1.10)
or Upstox option chain fallback (Phase 0, current). If two strikes straddle 22-delta exactly,
take the further OTM one (lower absolute delta) to reduce assignment probability. Delta is a
**parameterised input** — candidate values 20, 22, 25 are selectable at entry to enable
regime-adaptive operation once IVR ingestion is live. **Liquidity gate (new):** if the
bid/ask spread at the target delta strike exceeds 5% of the option mid price, skip the cycle
for that delta and try the adjacent candidate (e.g., 22 → 25); if no candidate passes the
gate, skip the cycle entirely and log in `TODOS.md`.

**Entry time:** 10:00–10:30 AM IST. Allow the first 30 minutes of price discovery to settle
before reading delta.

**Execution:** Limit order at the mid price of bid/ask at the time of entry. If unfilled
after 5 minutes, improve the limit by ₹0.25 and resubmit once. If still unfilled, log the
skipped cycle in `TODOS.md` with the reason and do not force a fill.

**Record the following at entry (required fields for `record_paper_trade.py`):** strike,
expiry date, entry delta, entry mid price, actual fill price (mid minus slippage haircut per
R7 below), IV at entry, India VIX at entry, IVR at entry (log even before R3 is enforced),
underlying spot price at entry, DTE at entry.

**Collateral leg — record once per strategy year (not per cycle):**

The paper strategy tracks the full combined P&L: short put premium + NiftyBees ETF
mark-to-market. This reflects the real economics — NiftyBees is the pledged collateral whose
value moves with Nifty 50, and its P&L belongs in the strategy's total return picture.

Record the NiftyBees leg as a BUY at strategy inception (or at each annual reset). The
quantity is calculated as:

```
qty = floor((lot_size × nifty_spot) / niftybees_ltp)
```

Example — strategy start 2026-04-25 (lot size 65, Nifty 23,897.95, NiftyBees 271.35):

```bash
python -m scripts.record_paper_trade \
  --strategy paper_csp_nifty_v1 \
  --leg long_niftybees \
  --key "NSE_EQ|INF204KB14I2" \
  --action BUY \
  --qty 5725 \
  --price 271.35 \
  --date 2026-04-25 \
  --notes "Collateral leg: 1 Nifty lot equiv (65 × 23897.95 / 271.35 = 5725 units). Annual reset."
```

**Annual reset procedure:** Once per calendar year (January, after expiry), record a SELL at
current NiftyBees LTP to close the old position (realises P&L), then immediately record a
fresh BUY at the new qty computed from current Nifty spot and NiftyBees LTP. This keeps the
collateral-equivalent sizing accurate as Nifty drifts over the year.

> **Note on combined P&L:** `PaperTracker.compute_pnl` includes all open legs automatically —
> the short put and `long_niftybees` are fetched together in one LTP batch. The
> `paper_nav_snapshots` `total_pnl` field already reflects the combined position. During a
> Nifty selloff both legs move against you simultaneously; this is the correct view of risk.

---

## Exit Rules

Three independent triggers. The first to fire wins. Monitor daily via `daily_snapshot.py`
output.

**1. Profit target:** Close when the current option mark-to-market value has decayed to ≤50%
of entry credit. Example: entered at ₹80.00 credit → close when option is worth ≤₹40.00.
Retain the remaining 50% as realised gain rather than running to expiry.

**2. Time stop (R1 — clarified):** Hold for **21 calendar days from entry**, then exit if no
other trigger has fired. This is not "close on or before 21 DTE remaining" — it is a
21-day clock that starts on the *entry date*.

> **Worked examples:**
> - Entry at 34 DTE → time stop fires at 13 DTE remaining (34 − 21 = 13).
> - Entry at 27 DTE → time stop fires at 6 DTE remaining (27 − 21 = 6).

The position is held into peak-theta territory and also into elevated gamma. This is
intentional — the strategy's edge is the 21-day theta capture. Gamma risk is managed by the
loss stop (below), not by exiting early.

**3. Loss stop (R2 — revised):** Close immediately if **put delta crosses −0.45** OR
**mark-to-market reaches 1.75× entry credit**, whichever fires first. Example: entered at
₹80.00 → mark trigger fires at ₹140.00.

> **Rationale for the revision from 2× to delta-gated:** The old 2× rule typically fires
> when delta is already −0.50 to −0.65 (peak gamma), producing poor fills in a fast market.
> The delta gate fires earlier, at lower gamma, yielding materially better execution. The
> 1.75× mark trigger provides a backstop for periods when the chain is stale or delta is
> temporarily unavailable.

**Re-entry after early profit exit (R5 — revised):** After a profit-target exit (50% target
hit before the time stop fires), if DTE to the current expiry is ≥ 14 AND IVR ≥ 25,
re-enter at the new **22-delta** strike of the same expiry (matching the default delta at
first entry). If either condition fails, wait for the standard Wednesday-after-next-expiry
entry. No re-entry is permitted after a loss-stop or time-stop exit within the same expiry
cycle.

> **Rationale:** Reduces idle-capital drag on winning cycles without abandoning v1 simplicity.
> The IVR floor matches R3, keeping entry discipline consistent across first entry and
> re-entry.

**Exit execution:** Same limit-at-mid discipline as entry. Slippage tolerance on exits is per
the R7 model below — not a flat ₹0.50. Do not use market orders except on expiry-day closure.

**Expiry handling:** If the time stop fires on expiry day itself (DTE = 0), close before
3:20 PM IST to avoid last-minute gamma spikes and settlement risk.

---

## Adjustment Rule

**None.**

No rolling, no strike adjustments, no defensive buys. If the position is under pressure and
no exit trigger has fired yet, hold until a trigger fires. If the urge to adjust arises, log
the reason in `TODOS.md` as a strategy-discipline note — this is valuable data about
behavioural edge — and then follow the spec.

This rule will be revisited when designing v2, informed by the paper-trade log.

---

## Position Sizing

**Quantity:** 1 lot = **65 units** (effective January 2026).

> **Lot size revision history (Nifty 50 options):** Was 50 units prior to approximately 2022;
> revised to 75 in 2024; revised again to 65 effective January 2026. NSE revises lot sizes
> periodically — verify against the NSE lot-size schedule before every entry. The 65-unit
> figure is not permanent.

**Notional capital deployed:** Strike × 65. At a 22-delta strike near 22,700–22,800 (Nifty
spot ~23,897 as of 2026-04-25; 22-delta sits approximately 100–200 points further OTM than
25-delta), notional ≈ ₹14,75,000–14,82,000 per lot. In the portfolio's cash-secured framing,
this notional is backed by the existing pledged collateral pool.

**Margin / collateral note:** The operator's collateral pool is approximately ₹1.2 cr (₹75L
MF + ₹30L bonds + ₹15.5L NiftyBees). SPAN + exposure margin for a single short Nifty put
is typically ₹1.2–1.5L at current volatility levels; the pool covers this comfortably at the
portfolio level. The "cash-secured" label reflects the portfolio stance: sufficient
liquid/near-liquid collateral exists to cover notional assignment at the strike. NiftyBees is
the primary pledged instrument; the option leg is on the Nifty index. This distinction was
reviewed and accepted on 2026-04-25.

**Slippage model (R7 — revised):**

- Entry and profit-target exit: `slippage = max(₹0.25, 0.5 × bid-ask spread)` per unit.
- Loss-stop exit: `slippage = 1.5 × max(₹0.25, 0.5 × bid-ask spread)` per unit (stressed
  market conditions produce wider spreads and partial fills).

Nifty index option typical bid-ask: ₹0.50–1.50 under normal vol, ₹2–5 under stress. At a
normal spread of ₹1.00, entry slippage ≈ ₹0.50/unit = ₹32.50/lot. At a stressed spread of
₹3.00, loss-stop exit slippage ≈ ₹2.25/unit = ₹146.25/lot. The multiplier at stop exits
matters more than the base — size the model accordingly when computing paper P&L.

**Transaction cost model (applied to paper P&L calculations):**

| Cost            | Rate                               |
|-----------------|------------------------------------|
| Brokerage       | ₹20 flat per order leg             |
| STT             | 0.1% of sell-side premium          |
| Exchange charge | 0.0345% of premium turnover        |
| GST             | 18% on brokerage + exchange charge |
| SEBI fee        | ₹10 per crore of premium turnover  |
| Stamp duty      | 0.003% on buy side                 |

At ₹80.00 credit on 65 units (₹5,200 gross premium per lot), total transaction costs are
approximately ₹80–100 per round trip.

**Hard sizing cap:** Maximum 25% of total portfolio capital deployed in this strategy at any
time. During Phase 0 paper trading and the first 3 months of Phase 2 live trading, the cap
is **1 lot**, irrespective of capital availability.

---

## Expected P&L Distribution Prior

These are prior hypotheses to validate — not claims of edge. Written before running the
backtest so there is a genuine prediction to compare against.

> **Note:** The figures below are indicative estimates originally calibrated against 25-delta
> monthly put performance on Nifty 50, 65-unit lot size, under moderate-IV conditions.
> The strategy default was updated to **22-delta** (council 2026-05-02); at 22-delta, credit
> is approximately 85% of 25-delta and stop-out frequency is approximately halved — expect
> the win-rate and average-winning-month figures to improve modestly, average-losing-month
> to shrink (less frequent stops, but stops are deeper moves when they do fire).
> These priors are *not* derived from a backtest. They will be replaced with the measured
> backtest distribution from Phase 1.8 (V1 variant — now parameterised to run at 22-delta)
> once that run is complete.

| Metric                          | Prior estimate (indicative, pending 1.8) |
|---------------------------------|------------------------------------------|
| Monthly win rate                | 65–72%                                   |
| Average winning month           | +₹6,000–9,000 per lot net                |
| Average losing month            | −₹10,000–15,000 per lot net              |
| Expected annual net return      | +12–18% on deployed capital              |
| Sharpe (annualised)             | 0.7–1.1                                  |
| Max drawdown (1 lot, worst case)| −₹30,000–35,000 (2 consecutive loss-stop cycles) |
| Worst single month              | −₹13,000 to −₹17,000 per lot net        |

---

## Regimes Expected to Work In

**High IV (IVR > 50):** Premium richness compensates for elevated move probability. Preferred
entry environment. Target delta stays at **22** — do not chase higher delta to inflate credit.
If IVR > 40 specifically (strongly elevated vol expansion), consider stepping down to 20-delta
(regime-adaptive rule, selectable via the parameterised delta input; requires IVR ingestion
pipeline to be live before enforcing programmatically).

**Neutral to mildly bullish market:** Time decay is the primary P&L driver. Strategy is
structurally long theta, short gamma.

**Range-bound:** Ideal. No directional stress. Both profit target and time stop can fire
cleanly.

**Post-spike IV mean reversion:** If IV has just collapsed from a spike, entering CSP
captures the elevated IV decay before it fully normalises.

---

## Regimes Expected to Fail In

**Sustained downtrend ≥ 8% within the trade window:** Nifty put goes deep ITM; delta gate or
mark trigger fires. The loss cap limits damage but the strategy has no edge in a trending
bear.

**Rapid IV expansion after entry (event-driven spike):** Even without a large directional
move, a VIX jump of 30%+ can take a 22-delta put to 45+ delta within days, triggering the R2
delta gate. At 22-delta the initial gamma is lower than at 25-delta, so the path to −0.45 is
somewhat longer — but it is not immune to sharp vol spikes. Mark-to-market loss accumulates
quickly. The event filter (R4) is intended to reduce exposure to known catalyst events.

**Low IV at entry (IVR < 25):** R3 mandates skipping the cycle. At the IV floor, premium
collected is structurally thin and risk/reward degrades to near-zero after costs. Losses on
the rare downside move are not compensated by the credit.

**Assignment risk near expiry:** If the trade is carried past the 21-day clock, the short
gamma exposure accelerates. This is addressed by the time stop rule, not an adjustment rule.

---

## Kill Criteria

These conditions trigger an **immediate pause** on the strategy — no new entries. The
existing position is managed to completion under the standard exit rules (not panic-closed).
Within 30 days of triggering, review and decide: resume, modify spec → v2, or retire.

1. **Trailing 6-month realised P&L < 0** (across all completed cycles in the trailing 180
   days).

2. **Maximum drawdown on deployed capital > 10%** — for 1 lot at ~₹14,95,000 notional, this
   is approximately ₹1,50,000 cumulative loss across all cycles in any rolling 3-month window.

3. **Rolling 3-month Z-score of realised vs backtest |Z| > 2.0 for 4 consecutive weeks** —
   strategy behaviour has structurally diverged from the backtested model.

4. **Three consecutive execution errors** — wrong-side fill, missed exit, fat-finger entry.
   Each error must be individually logged in `TODOS.md` with root cause before the count
   resets.

5. **Nifty index options market structure degradation** — if average daily open interest in
   Nifty 50 monthly puts falls below 10,000 contracts, or bid/ask spread exceeds 5% of mid
   consistently across 3 consecutive entry opportunities, skip cycles and review instrument
   viability. (This threshold is far more conservative than the NiftyBees equivalent. Nifty
   options are liquid by global standards; degradation at this level would signal a structural
   market event, not routine thinness.)

6. **Single-cycle loss > 3× trailing-12-cycle average credit (R6 — new):** Any single cycle
   where the realised loss exceeds 3× the trailing-12-cycle average entry credit pauses the
   strategy automatically pending a review session. This is a per-cycle early warning that
   complements criterion 1 above — the trailing-6-month criterion fires too late to catch a
   single catastrophic cycle cleanly.

---

## Variance Threshold for Live Deployment

Before Phase 2 live deployment is authorised (task 2.2), the following must hold:

**Condition:** Monthly P&L distribution from paper trading must satisfy |Z| ≤ 1.5 relative
to the Phase 1 backtest distribution (V1 variant — Wednesday-after-expiry only, no early
re-entry), measured over the paper-trade window.

**Minimum paper-trade duration:** **6 full monthly expiry cycles (approximately 6 months)**,
with at least one cycle that triggers each of: profit target, time stop, delta-stop. Two
cycles is 2 data points — not enough to distinguish execution variance from structural drift.
Six cycles provides a coarse but credible distribution. This is a minimum, not a target;
prefer 8+ cycles if calendar permits before committing capital.

**Z-score formula:** `Z = (paper_mean − backtest_mean) / backtest_std`

**Bias adjustment (required before computing Z):** The Black-Scholes delta used for
backtesting (Phase 1.6a) will systematically differ from the Dhan live-chain delta used for
paper strike selection by approximately 0.5–2 delta points. Compute this structural bias by
re-running the V1 backtest with strike selection forced to match the actual paper-traded
strikes. Subtract this bias from the paper-vs-backtest gap before evaluating Z. The active
variant being paper-traded (V1, V2, or V3 — see BACKTEST_PLAN.md task 1.11) determines which
backtest distribution is used here. If the bias-adjusted |Z| still exceeds 1.5, the backtest
requires recalibration — do not override this gate.

**Fail path:** If Z fails after 6 cycles, audit in order: (1) cost model completeness,
(2) slippage assumption vs actual paper fills, (3) entry/exit rule divergence between code
and paper execution log, (4) BS-vs-Dhan delta drift magnitude. Fix, re-run 1.8, re-evaluate.

---

## Backtest Results

*Section to be populated after Phase 1 tasks 1.7–1.8 are complete.*

| Field                     | V1 (no re-entry) | V2 (R5 re-entry, IVR-gated) | V3 (always-on roll) |
|---------------------------|------------------|-----------------------------|---------------------|
| Run ID                    | TBD              | TBD                         | TBD                 |
| Backtest window           | TBD              | TBD                         | TBD                 |
| Net annualised return     | TBD              | TBD                         | TBD                 |
| Sharpe                    | TBD              | TBD                         | TBD                 |
| Sortino                   | TBD              | TBD                         | TBD                 |
| Max drawdown (depth)      | TBD              | TBD                         | TBD                 |
| Max drawdown (duration)   | TBD              | TBD                         | TBD                 |
| Monthly win rate          | TBD              | TBD                         | TBD                 |
| Worst month               | TBD              | TBD                         | TBD                 |
| Git SHA                   | TBD              | TBD                         | TBD                 |

---

## Variance Check Results

*Section to be populated after Phase 1 task 1.11 is complete.*

| Field                        | Value |
|------------------------------|-------|
| Active variant (V1/V2/V3)    | TBD   |
| Paper-trade window           | TBD   |
| Paper mean monthly return    | TBD   |
| Backtest mean (same window)  | TBD   |
| BS-vs-Dhan bias adjustment   | TBD   |
| Z-score (bias-adjusted)      | TBD   |
| Pass / Fail                  | TBD   |
| Decision                     | TBD   |

---

## Open Questions for v2

These are not blockers for v1. Log here; revisit when designing v2 after sufficient
paper-trade data.

- ~~Should v2 switch to Nifty 50 index puts (using NiftyBees as pledged margin collateral)
  to gain liquidity?~~ **RESOLVED 2026-04-25** — v1 now uses Nifty 50 index puts. NiftyBees
  ETF retained as pledged collateral. See `DECISIONS.md`.

- Is IVR < 25 the right hard-skip threshold for R3, or does Indian-market structure call for
  a higher floor (e.g. IVR < 30)? Calibrate after 6+ cycles once the IVR ingestion pipeline
  is live (currently no India VIX data in repo).

- ~~Is 25-delta the optimal entry point for Nifty 50 monthly CSP, or does the strategy's
  asymmetric payoff favour a tighter OTM target (20-delta) to reduce delta-stop frequency?~~
  **RESOLVED 2026-05-02 (council)** — analytical optimum is **22-delta** for the 21-day
  hold / −0.45 delta-stop / 50% profit-target system on Nifty 50. Captures ~85% of 25-delta
  credit, approximately halves stop-out frequency, best Sharpe in skew-adjusted model.
  Strategy doc updated accordingly. Policy gate: maintain 12-month parameter discipline;
  only re-tune when both backtest and live fill data show unambiguous advantage for a
  different value. Per-exit-type statistics in paper logs remain valuable for forward
  calibration — continue logging. See `docs/council/2026-05-02_csp-entry-delta-v2.md`.

- Does the R2 delta gate at −0.45 produce better outcomes than a pure mark-based stop?
  Requires per-exit-type P&L breakdown from the paper log.

- After 12 cycles of data: is the V2 (R5 re-entry) variant materially better on a
  risk-adjusted basis than V1? Use the Phase 1.8 V1-vs-V2 comparison as the prior; live data
  as the test.

- Does the 21-day hold period remain optimal as IV regime shifts? The theta-vs-gamma
  tradeoff moves with vol level; revisit if IVR regime changes structurally.
