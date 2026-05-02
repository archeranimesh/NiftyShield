# NiftyShield Integrated Strategy — v1

| Field                    | Value                                                                        |
|--------------------------|------------------------------------------------------------------------------|
| Name                     | NiftyShield Integrated (CSP Income + MF Protection)                          |
| Version                  | v1                                                                           |
| Author                   | Animesh Bhadra (archeranimesh)                                               |
| Date                     | 2026-04-26                                                                   |
| Status                   | Design — pending Phase 0.6 paper start                                       |
| Underlying (option legs) | Nifty 50 index (`NSE_INDEX|Nifty 50`, Dhan: security ID `13`, segment `IDX_I`) |
| Collateral               | NiftyBees ETF (`NSE_EQ|INF204KB14I2`) — pledged                             |
| Instruments              | Nifty 50 monthly put options (NSE) — sell + buy legs                         |

> **Design rationale:** FinRakshak provides ~15% coverage of the ₹80L+ MF portfolio
> (1 lot NIFTY DEC 23000 PE ≈ ₹15L notional). The remaining ~85% is unhedged against
> moderate corrections (8–20%) and tail events (20%+). This strategy integrates the
> CSP income engine (already specified in `csp_nifty_v1.md`) with layered protective
> puts to close the hedge gap, funded partly by CSP premium and partly by an explicit
> annual insurance budget of 3–5% of MF portfolio value (₹2.4L–₹4L at ₹80L).
>
> **Relationship to `csp_nifty_v1.md`:** The CSP leg (Leg 1) uses identical rules —
> same entry, exit, adjustment, and kill criteria. This document does not redefine
> them; it references CSP v1 by inclusion. The protective legs (Legs 2 and 3) are
> additive. If Leg 1 is paper-traded under `paper_csp_nifty_v1`, the integrated
> strategy is tracked under `paper_niftyshield_v1` and includes all three legs.
>
> **FinRakshak independence:** FinRakshak's 1 lot NIFTY DEC 23000 PE is NOT counted
> in NiftyShield's hedge ratio. FinRakshak operates on its own expiry/roll cycle
> managed by Finideas. NiftyShield's protection stands independently. When
> FinRakshak's DEC expiry arrives, Finideas rolls or exits per their protocol.
> Any overlap is treated as bonus protection, not sized against.

---

## Purpose

Close the MF portfolio protection gap that FinRakshak leaves open while generating
rental income via CSP to partially offset the cost of protection and accumulate
NiftyBees over time. The strategy is designed as a single integrated P&L unit: CSP
income, protective put spread payoff, tail put payoff, and NiftyBees collateral
mark-to-market are all measured together.

The protection target is moderate-to-tail: activate at >8% Nifty decline, provide
meaningful payout through a 20% decline, and maintain catastrophic coverage beyond 20%
via quarterly tail puts.

---

## Portfolio Context — The Protection Gap

**MF portfolio composition (at cost → current market value):**

| Category         | Schemes                                                    | Cost (₹L) | Est. Current (₹L) | Beta to Nifty |
|------------------|------------------------------------------------------------|------------|--------------------|----|
| Mid/Small Cap    | DSP Midcap, Edelweiss Small Cap, Mahindra Mid Cap, quant Small Cap | ~14.9 | ~25–30 | 1.3–1.5 |
| Flexi/Multi Cap  | PPFAS, Kotak Flexicap, WhiteOak Large Cap                 | ~22.5      | ~30–35             | 1.0–1.2 |
| Value/Focused    | Tata Value, HDFC Focused                                   | ~17.5      | ~18–22             | 1.1–1.3 |
| Index            | HDFC Sensex, Tata Nifty 50                                 | ~7.7       | ~8–10              | 1.0 |
| **Total**        |                                                            | **~46.6**  | **~80+**           | **~1.25 wtd avg** |

**Nifty-equivalent exposure:** ₹80L × 1.25 beta = ~₹100L effective. At Nifty ~24000
with lot size 65, full delta coverage requires ~6.4 lots.

**FinRakshak coverage:** 1 lot = ₹15.6L notional = ~15.6% of effective exposure.

**NiftyShield target coverage:** 4–5 additional lots of put spread protection,
covering ~60–80% of the remaining exposure. 100% coverage is uneconomical within the
3–5% budget.

---

## Entry Rules

The strategy has three legs entered on different schedules:

### Leg 1 — CSP (Income Leg)

**Identical to `csp_nifty_v1.md` rules.** Sell 1 lot Nifty 22-delta put (updated
from 25-delta per 2026-05-02 council ruling in DECISIONS.md), 30–45 DTE, Wednesday
after monthly expiry. All entry rules (R1–R7), exit rules, and kill criteria from that
spec apply without modification.

Entry, exit, and adjustment rules for Leg 1 are governed entirely by
`csp_nifty_v1.md`. They are not repeated here to avoid spec divergence.

### Leg 2 — Protective Put Spread (Moderate Correction Buffer)

**What:** Buy Nifty put at 8% OTM, sell Nifty put at 20% OTM. Same monthly expiry as
Leg 1. 4 lots.

**Strike selection:**

- Long put: closest available strike to `Nifty_spot × 0.92` (8% below spot). At Nifty
  24000, this is ~22080 → round to nearest 50 = 22050 or 22100.
- Short put: closest available strike to `Nifty_spot × 0.80` (20% below spot). At
  Nifty 24000, this is ~19200.

**Liquidity filter (2026-05-02 council ruling):** At time of entry, check OI on the
selected 8% OTM long put strike. If OI < 500 contracts, step one strike inward to
the nearest 50-point increment closer to spot (e.g., ~7% OTM). If that strike also
has OI < 500, step again to ~6% OTM. Log any deviation from the 8% base in the trade
record (`trade_metadata` field or paper trade notes) including the OI observed at the
base strike. Do not use delta-based selection as a fallback — the liquidity filter
applies strictly within the %OTM framework. Rationale and full council analysis:
`docs/council/2026-05-02_integrated-leg2-strike-methodology.md`.

**Lot count:** 4 lots. Derived from:

```
target_lots = floor(mf_nifty_equivalent / nifty_notional_per_lot × coverage_ratio)
            = floor(100L / 15.6L × 0.65)
            ≈ 4.2 → 4 lots
```

Where `coverage_ratio = 0.65` (target 65% of remaining unhedged exposure after
FinRakshak). Rebalance lot count annually in January alongside the NiftyBees
collateral reset — recalculate `mf_nifty_equivalent` from current MF NAV and
current beta estimate.

**Entry timing:** Same day as Leg 1 entry (Wednesday after monthly expiry), within the
10:00–10:30 AM IST window. Enter after Leg 1 is filled — the CSP credit is known
before committing to the put spread debit.

**Entry execution:** Leg the spread as two separate limit orders (buy long put first,
then sell short put). Do not use combo/spread orders — Nifty option spread order
books are thin on monthlies. Slippage model per R7 from `csp_nifty_v1.md` applies to
each leg independently.

**DTE requirement:** Same as Leg 1 — 30–45 DTE. If Leg 1 entry is skipped due to R3
(IVR filter) or R4 (event filter), Leg 2 is STILL entered. The protection mandate
is unconditional — you do not skip insurance because the premium is cheap.

### Leg 3 — Quarterly Tail Puts (Black Swan Insurance)

**What:** Buy Nifty deep OTM puts at 5-delta (~28–32% OTM). Quarterly expiry
(Mar/Jun/Sep/Dec). 2 lots.

**Strike selection:** Closest available strike to the 5-delta put on the quarterly
expiry, as reported by the live option chain. At Nifty 24000 and moderate IV, this
typically lands at 16500–17500. If two strikes straddle 5-delta, take the further OTM
one.

**Lot count:** 2 lots. This is the tail-risk layer — sized to provide ₹2.5L–₹4L+
payout in a 30%+ crash scenario (each lot gains ~₹1.3L–₹2L+ when Nifty drops from
24000 to 16800). Not sized to fully offset MF losses in a tail event — that would
require 6+ lots and blow the budget.

**Entry timing:** First trading Wednesday of the quarter (January, April, July,
October). Quarterly entry is independent of the monthly CSP/put-spread cycle.

**Entry execution:** Single limit order per lot. Slippage tolerance is wider for deep
OTM (R7 base model × 1.5) — these strikes are thin.

**No roll-forward:** If the quarterly put expires worthless (expected outcome ~85% of
quarters), the loss is the full premium. This is the insurance cost. Do not attempt
to recover premium by selling the put before expiry — the liquidity haircut on
closing a deep OTM put is worse than the residual value.

---

## Exit Rules

### Leg 1 — CSP

Per `csp_nifty_v1.md`: profit target (50% decay), time stop (21 calendar days), loss
stop (delta −0.45 OR 1.75× mark). No changes.

### Leg 2 — Protective Put Spread

**1. Expiry:** Hold to expiry. Put spreads are protection, not a trading position. If
Nifty is above the long put strike at expiry, both legs expire worthless — the
premium is the insurance cost for that month.

**2. Early exercise / deep ITM at expiry:** If Nifty drops below the long put strike
and the spread is fully in-the-money (Nifty < short put strike), close both legs on
the last trading day before 3:20 PM IST. Do not hold to settlement — index option
settlement is cash-settled but the mark-to-market on the short leg can swing
violently in the last hour.

**3. Partial payoff (Nifty between long and short put strikes):** If Nifty is between
the two strikes at expiry, the long put has intrinsic value and the short put is OTM.
Close the long put; the short put expires worthless. Retain the payoff as realised
gain to offset MF losses for the month.

**4. Pre-expiry profit-taking:** NOT permitted. The protection exists for the full
month. Selling the long put early because it's "profitable" removes protection for the
remaining days. This is the discipline trap — the put is profitable because Nifty is
falling, which is exactly when you need it.

### Leg 3 — Quarterly Tail Puts

**1. Expiry:** Hold to expiry. Expected outcome: expires worthless ~85% of quarters.
Full premium lost. This is by design.

**2. Crash payoff:** If a >20% Nifty decline occurs during the quarter, the tail put
becomes deeply in-the-money. Close on any trading day where the put's delta exceeds
−0.80 (deeply ITM, minimal theta left). Do not hold past this point — liquidity
collapses on deep ITM index puts in a crisis. Take the cash and reallocate.

**3. Partial decline (15–20%):** The tail put gains some value but may not justify
early closure given the bid-ask spread on deep OTM options. Decision: hold to expiry
unless the put's mark-to-market exceeds 5× entry premium AND the bid-ask spread is
<10% of mid. Otherwise, let it expire — the protection from Leg 2 covers this zone.

---

## Adjustment Rule

**Leg 1 (CSP):** None. Per `csp_nifty_v1.md`.

**Leg 2 (Put Spread):** None within a cycle. The strikes are set at entry and held to
expiry. No strike adjustment, no rolling mid-month. If Nifty moves significantly
between entry and expiry (e.g., a 5%+ rally shifts the 8% OTM strike to 13% OTM),
the next month's fresh entry auto-corrects by selecting new strikes relative to
current spot.

**Leg 3 (Tail Put):** None. Quarterly horizon eliminates the need for monthly
adjustments.

**Beta rebalancing (annual):** The lot count for Leg 2 (currently 4) is recalculated
in January alongside the NiftyBees collateral leg annual reset. Inputs:
- Updated MF portfolio NAV (from `mf_nav_snapshots`)
- Updated beta estimate (static 1.25 initially; switch to rolling 60-day beta once
  12+ months of clean NAV history exists — see `DECISIONS.md`)
- Updated Nifty spot

If the recalculated lot count differs by ≥1 lot from the current allocation, adjust
from the next monthly entry. If <1 lot difference, hold steady.

---

## Position Sizing

### Monthly Cost Budget

| Component | Per month (est.) | Annual (est.) |
|---|---|---|
| Leg 1: CSP income (1 lot) | +₹4,000–6,000 net | +₹50K–70K |
| Leg 2: Put spread cost (4 lots) | −₹18,000–31,000 | −₹2.2L–3.7L |
| Leg 3: Tail puts (2 lots, quarterly → monthly amortised) | −₹1,500–2,700 | −₹18K–32K |
| **Net annual cost** | | **₹1.5L–₹3.3L** |

**Budget cap:** 5% of MF portfolio value per annum = ₹4L at ₹80L. The strategy
operates well within this cap. If net annual cost exceeds the cap (possible in high-IV
regimes where put spread premiums inflate), reduce Leg 2 to 3 lots before reducing
Leg 3.

### NiftyBees Accumulation

In months where all legs expire favourably (Leg 1 profit target hit, Legs 2+3 expire
worthless), the net monthly surplus is approximately ₹2,000–4,000 after all costs.
This surplus is allocated to NiftyBees purchases:

```
monthly_niftybees_units = floor(net_surplus / niftybees_ltp)
```

At NiftyBees ~₹271: ~7–15 units/month, ~100–180 units/year, ~₹27K–₹49K added to
the collateral pool annually. Over the 4–5 year BACKTEST_PLAN horizon: 500–900
NiftyBees units accumulated from strategy income alone.

NiftyBees purchases are recorded as separate BUY trades in the paper ledger under
`paper_niftyshield_v1` with `leg_role=accumulated_niftybees`. These are not the
collateral leg — they represent newly accumulated units from income.

### Capital Deployment

| Metric | Value |
|---|---|
| Leg 1 margin (CSP, 1 lot) | ~₹1.2–1.5L (SPAN + exposure) |
| Leg 2 max risk (put spread, 4 lots) | 4 × 65 × spread_width (₹2,850) = ₹7.4L max |
| Leg 3 max risk (tail puts, 2 lots) | 2 × 65 × premium ≈ ₹2K–3.5K per quarter |
| Total capital at risk (worst month) | ~₹8.9L (all protection expires worthless + CSP loss stop) |
| % of total portfolio (₹1.2 cr collateral pool) | ~7.4% — within 25% single-strategy hard cap |

### Slippage Model

Per `csp_nifty_v1.md` R7 for Leg 1.

For Legs 2 and 3, the same formula applies with a wider base:
- Leg 2 (8% OTM): `slippage = max(₹0.50, 0.5 × bid-ask spread)` per unit. These
  strikes are less liquid than ATM — bid-ask typically ₹1–3 under normal vol.
- Leg 3 (30% OTM): `slippage = max(₹1.00, 0.5 × bid-ask spread)` per unit. Deep OTM
  liquidity is thin — bid-ask can be ₹2–8.

### Transaction Cost Model

Same rates as `csp_nifty_v1.md` (brokerage ₹20/order, STT 0.1% sell-side, exchange
0.0345%, GST 18%, SEBI ₹10/cr, stamp 0.003% buy-side). Applied per leg per round
trip.

Estimated monthly transaction costs for the integrated strategy:
- Leg 1: ~₹80–100 (1 lot, 2 orders)
- Leg 2: ~₹320–500 (4 lots, 8 orders — buy long put + sell short put × 4)
- Leg 3: ~₹60–80 per quarter (2 lots, 2 orders — buy only; expires worthless)
- **Total monthly: ~₹420–620**

---

## Expected P&L Distribution Prior

Prior hypotheses to validate — not claims of edge. Written before backtesting.

### Regime: Normal / Mildly Bullish (60–65% of months)

All legs expire worthless or CSP hits profit target. Net monthly P&L:

```
CSP credit (~₹5,200) − Put spread cost (~₹5,000–7,500 for 4 lots)
− tail put amortised (~₹800) − transaction costs (~₹500)
≈ −₹1,100 to −₹3,600
```

Net cost of ₹1K–4K/month for holding portfolio protection. This is the insurance
premium in a non-event month.

### Regime: Moderate Correction (8–15% Nifty decline, ~15–20% of months)

CSP hits loss stop (R2): loss of ₹8K–15K per lot.
Put spread payoff: 4 lots × 65 × (long_put_intrinsic − short_put_intrinsic).
At 12% Nifty decline (24000 → 21120): long put (22050) gains ~₹930/unit, short put
(19200) still OTM → payoff = 4 × 65 × 930 = ₹2.42L.

**Net: +₹2.42L − ₹0.15L (CSP loss) − ₹0.07L (put spread cost) ≈ +₹2.2L**

The protection pays meaningful amounts, net of CSP drag.

### Regime: Crash (>20% Nifty decline, ~3–5% of months)

CSP hits loss stop early (delta gate): loss of ₹8K–15K.
Put spread at max payout: 4 × 65 × 2850 (full spread width) = ₹7.4L.
Tail puts deeply ITM: 2 × 65 × (strike − spot). At 30% decline (24000 → 16800),
tail put at 17000 gains ₹200/unit → 2 × 65 × 200 = ₹26K. If entered at 16500:
gains zero until Nifty < 16500.

**Net: +₹7.4L + ₹0–0.26L − ₹0.15L ≈ +₹7.3L–₹7.5L**

Against ₹80L MF portfolio losing ~₹24L (30% × 1.0 beta for index funds) to ~₹36L
(30% × 1.5 beta for mid/small cap heavy portion), the strategy recovers ₹7.3L–₹7.5L
= **20–30% of MF losses cushioned**.

This is partial, not full protection. Full protection (6+ lots of put spreads + 4+
lots of tail puts) would cost 6–8% annually — beyond the budget.

### Aggregate Annual Prior

| Metric | Prior estimate (indicative, pending backtest) |
|---|---|
| Expected annual net cost in flat/up markets | ₹1.5L–₹3.3L (insurance premium) |
| Expected payoff in 10% correction | ₹1.5L–₹2.5L net |
| Expected payoff in 20%+ crash | ₹6L–₹7.5L net |
| Worst single month (no correction, all costs) | −₹4K–₹6K |
| NiftyBees accumulated per year (surplus months) | 100–180 units (~₹27K–₹49K) |

---

## Regimes Expected to Work In

**High IV (IVR > 50):** CSP credit is rich, offsetting more of the protection cost.
Put spread premiums also inflated — but the net income-to-cost ratio improves because
CSP income scales faster with IV than protection cost (CSP is ATM-adjacent; put
spreads are further OTM where vega is lower).

**Moderate correction (8–15%):** The put spread payoff zone. This is where the strategy
earns its keep — the protection cost of the prior 6–12 calm months is recouped in one
event.

**Tail events (>20%):** Put spread at max payout + tail puts activate. The strategy
provides meaningful but partial cushion. FinRakshak's independent put adds to the
total protection.

**Choppy / range-bound:** CSP income ticks along, put spreads expire worthless. Net
cost is manageable within budget. Boring months are good months.

---

## Regimes Expected to Fail In

**Slow grind down (5–8% over 2–3 months):** The worst regime for this strategy. CSP
may not hit the loss stop (delta stays above −0.45), but the MF portfolio erodes
steadily. Put spread at 8% OTM doesn't kick in. The strategy bleeds insurance cost
without any payoff. This is the "dead zone" — Nifty falls enough to hurt MFs but
not enough to trigger protection.

**Rapid V-recovery (flash crash + immediate rebound):** The put spread may briefly
become profitable but can't be closed fast enough at the bottom (liquidity vanishes
in a flash crash). By the time the recovery plays out, the protection has expired.
The tail put suffers the same fate — briefly ITM, then worthless. MF portfolio
recovers, but the protection cost is a pure drag.

**Sustained high IV with flat market:** Put spread premiums stay elevated (cost rises)
but no directional move triggers payoff. CSP income also rises, partially offsetting,
but net cost can creep toward the 5% budget cap. If this persists >3 months, reduce
Leg 2 to 3 lots.

**Beta divergence (mid/small caps decouple from Nifty):** In a sector rotation where
Nifty holds but mid/small caps sell off 10%+, the Nifty put spreads provide zero
protection because Nifty hasn't dropped. The hedge is imperfect by design — we hedge
Nifty as a proxy for the MF portfolio. In a sector-specific selloff, the 1.25 beta
assumption breaks. This is the fundamental limitation of hedging a multi-cap MF
portfolio with index options.

---

## Kill Criteria

### Strategy-Level Kills (all legs)

1. **Net annual cost exceeds 6% of MF portfolio value for 2 consecutive quarters.**
   The strategy is structurally uneconomical. Reduce leg count or restructure.

2. **Trailing 12-month realised protection payoff is zero AND net insurance cost
   exceeds ₹3.5L.** Twelve consecutive months with no correction >8% while paying
   full protection cost. Review whether the 8% OTM threshold should widen to 10% to
   reduce cost, or whether the market regime has shifted to low-vol permanently
   (unlikely but possible).

3. **Beta divergence: MF portfolio drawdown exceeds 10% in a period where Nifty
   drawdown is <5%.** The proxy hedge has failed — mid/small cap decoupling.
   Investigate whether sector-specific hedges (Bank Nifty puts for banking MFs, etc.)
   should replace some Nifty lots.

### Leg-Specific Kills

**Leg 1 (CSP):** All six kill criteria from `csp_nifty_v1.md` apply independently. If
CSP is killed, Legs 2 and 3 continue — the protection mandate is independent of the
income engine. CSP kill reduces the income offset; the full protection cost falls on
the explicit budget.

**Leg 2 (Put Spread):** No independent kill. As long as the MF portfolio exists and
the budget is available, the put spread runs. The lot count may be reduced (to 3, then
2) if budget pressure triggers criterion 1, but the leg is never fully killed while
MFs are held.

**Leg 3 (Tail Put):** Kill if India VIX trades below 10 for 6 consecutive months
(deep structural low-vol regime where tail puts are both cheap and near-useless). In
this regime, reallocate the tail put budget to additional Leg 2 lots.

---

## Variance Threshold for Live Deployment

### Two-Tier Validation

The integrated strategy requires separate variance checks for each tier:

**Tier 1 (CSP leg — real market data backtest):** Same variance threshold as
`csp_nifty_v1.md`: |Z| ≤ 1.5 over ≥6 monthly cycles, with BS-vs-Dhan bias
adjustment. This gate must pass independently before the CSP leg goes live.

**Tier 2 (Protective legs — synthetic pricing backtest):** Because Legs 2 and 3 use
Black-Scholes synthetic pricing (Dhan expired options data does not cover 8–30% OTM
strikes), the variance check methodology differs:

1. **Paper-trade Legs 2 and 3 for ≥6 monthly cycles** using real Dhan live chain
   prices (`/v2/optionchain` — returns all strikes, not limited to ATM±10).

2. **Backtest the same 6-month window** using BS synthetic pricing with the vol skew
   model (fixed markup initially, calibrated later per BACKTEST_PLAN.md 1.6a).

3. **Compute cost variance:** `Z_cost = (paper_avg_monthly_cost − bt_avg_monthly_cost) / bt_cost_std`.

4. **Pass condition:** |Z_cost| ≤ 2.0 (wider than Tier 1 because synthetic pricing
   is structurally less accurate — the 2.0 threshold accommodates the known vol-smile
   bias).

5. **If |Z_cost| > 2.0:** The BS skew model is miscalibrated. Recalibrate against
   the accumulated live chain snapshots (task 1.10) and re-run.

**Payoff validation (crash scenario — cannot be variance-checked statistically):**
The protective legs' payoff in a crash cannot be validated by a Z-score (crashes are
too infrequent for a monthly distribution). Instead, validate via:

- **Stress backtest:** Run the integrated strategy through Feb–Mar 2022 (Russia/Ukraine,
  ~15% Nifty drop) and Jun 2024 (election day, ~6% intraday). Verify that the put
  spread payoff is directionally correct (positive in Feb 2022, near-zero in Jun 2024).
- **Synthetic stress test:** Simulate a 30% Nifty decline over 5 trading days using
  the BS pricer. Verify put spread reaches max payout. Verify tail put payoff is
  positive and scales with the decline magnitude.

These are not pass/fail gates — they are sanity checks. The real validation of crash
protection happens live. Accept this limitation.

**Minimum paper-trade duration before live:** 6 full monthly cycles for Legs 1+2
together. 2 full quarterly cycles for Leg 3 (6 months minimum). At least one cycle
must overlap with a Nifty correction of ≥5% to observe the put spread in a non-trivial
scenario. If no ≥5% correction occurs during the paper window, extend the paper phase
until one occurs or until 12 cycles pass (whichever comes first), then go live
accepting that the crash payoff is untested.

---

## Backtest Design — Two-Tier Approach

### Tier 1: CSP Leg (Real Market Data)

Per BACKTEST_PLAN.md tasks 1.7–1.8. Uses Dhan `rollingoption` expired options data.
25-delta put is within ATM±3–4 coverage window. High-fidelity backtest across
2021-08 to present.

### Tier 2: Protective Legs (Synthetic Pricing)

**Data constraint:** Dhan `rollingoption` covers ATM±3 (non-nearing-expiry) and
ATM±10 (nearing expiry). An 8% OTM put (ATM−38 offsets) and 20% OTM put (ATM−96
offsets) are completely outside this coverage. No historical traded data available for
these strikes.

**Approach:** Black-Scholes synthetic pricing using:
- **Nifty spot:** Dhan underlying OHLC (available historically)
- **IV input:** India VIX OHLC (requires NSE/Upstox ingestion — Phase 1 prerequisite)
  plus a parametric skew model
- **Skew model (Phase 1):** Fixed IV markup per % OTM. Initial calibration:
  +2% IV per 5% OTM (e.g., 8% OTM put priced at ATM IV + 3.2%; 20% OTM put at
  ATM IV + 8%). Crude but directionally correct.
- **Skew model (Phase 2+):** Calibrate against accumulated live chain snapshots from
  task 1.10. Refit the skew parameters monthly using the most recent 60 trading days
  of observed IV across all strikes.

**Known biases:**
1. **BS underprices deep OTM puts** (vol smile not captured by flat IV). The fixed
   skew markup partially corrects this but may still underestimate by 10–20%.
   Effect: backtest shows protection as cheaper than reality → **optimistic bias on
   net cost**.
2. **BS overestimates payoff in crisis** (assumes continuous markets and constant vol;
   real crashes have gaps and liquidity withdrawal). Effect: backtest shows better
   fills than reality → **optimistic bias on payoff**.
3. Both biases are optimistic. The paper-trading phase is where reality bites.
   Accept this and document it in every backtest result.

---

## Correlation Warning — CSP vs Protection Interaction

During a Nifty decline, Leg 1 (CSP short put) loses money while Legs 2+3 gain.
The net protection is reduced by CSP drag.

**Quantified interaction by regime:**

| Nifty decline | CSP loss (Leg 1) | Put spread payoff (Leg 2, 4 lots) | Tail put payoff (Leg 3, 2 lots) | Net protection |
|---|---|---|---|---|
| 5% | ₹0–2K (may not trigger stop) | ₹0 (below 8% threshold) | ₹0 | −₹2K (CSP loss only) |
| 10% | ₹8K–12K (delta stop) | ~₹1.5L | ₹0 | ~₹1.4L |
| 15% | ₹10K–15K (delta stop) | ~₹3.5L | ₹0 | ~₹3.4L |
| 20% | ₹10K–15K (delta stop) | ~₹7.4L (max) | ~₹0–10K | ~₹7.3L |
| 30% | ₹10K–15K (delta stop) | ~₹7.4L (max) | ~₹26K–1.3L | ~₹7.5L–8.5L |

CSP drag is ≤2% of net protection in moderate-to-severe corrections. It's only
material in the 5–8% dead zone where protection doesn't yet kick in.

---

## Open Questions for v2

- ~~Should Leg 2 use delta-based strike selection (e.g., 15-delta) instead of
  percentage-OTM?~~ **Resolved 2026-05-02 (council):** fixed %OTM retained as
  primary. Delta-based rejected — dead zone widens in low-vol regimes where most
  moderate corrections occur; cost spikes at VIX>20. 92% vs 85% payoff reliability
  in 8–15% scenarios. Delta-based deferred as a conditional Phase 2 overlay at
  IVR > 70% only. See DECISIONS.md and
  `docs/council/2026-05-02_integrated-leg2-strike-methodology.md`.

- Should Leg 3 switch from quarterly to semi-annual (cheaper, but larger gap between
  renewals)? Depends on the observed frequency of tail events in the backtest window.

- At what MF portfolio size does it become economical to hedge mid/small cap exposure
  separately (e.g., Bank Nifty puts for banking-heavy MFs)? Currently the portfolio
  is too small and too diversified to justify sector hedges.

- Should NiftyBees accumulation from income surplus be automated (auto-buy on the
  first trading day after month-end P&L settles) or manual?

- After 12 months of data: is the static beta of 1.25 materially different from
  rolling 60-day beta? If yes, switch to rolling. If the difference is <0.1, stay
  with static (simpler, fewer moving parts).

---
