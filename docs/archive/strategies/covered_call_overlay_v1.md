# Covered Call Overlay on Pledged NiftyBees v1

| Field                    | Value                                                                        |
|--------------------------|------------------------------------------------------------------------------|
| Name                     | Covered Call Overlay on NiftyBees / Nifty 50                                |
| Version                  | v1                                                                           |
| Author                   | Animesh Bhadra (archeranimesh)                                               |
| Date                     | 2026-05-27                                                                   |
| Status                   | ✅ Broker confirmed 2026-05-28 — ready for paper-trading                    |
| Underlying (option leg)  | Nifty 50 index (`NSE_INDEX|Nifty 50`, same as CSP)                          |
| Collateral               | NiftyBees ETF (`NSE_EQ|INF204KB14I2`) — already pledged for Finideas margin |
| Instrument               | Nifty 50 monthly call options (NSE) — same cycle as CSP                     |
| Strategy type            | Yield enhancement overlay (always-on; not an allocation strategy)            |

> **Source:** Specified in `docs/plan/signals-eval-core/stories.md §SE4.4`.
> Council review not required for paper-trading phase; full council warranted before live
> deployment if broker mechanics confirm the position is viable.
>
> **Relationship to CSP:** This strategy runs alongside `paper_csp_nifty_v1` (short put).
> Together they form a synthetic short strangle: short put + short call, both supported by the
> ₹1.2 cr+ collateral pool. The call leg is "covered" by the NiftyBees holding — a sharp Nifty
> rally that drives the call into loss simultaneously appreciates the ETF units, netting near zero.
>
> **Relationship to Iron Condor:** When IC is eventually deployed, evaluate whether to retire
> the standalone Covered Call leg to avoid position overlap and double margin consumption.

---

## Broker Mechanics

> **✅ Confirmed 2026-05-28 — hard block cleared.**

**Question confirmed with Upstox:**
NiftyBees ETF units are pledged as margin collateral for the Finideas portfolio (the existing
CSP strategy and related positions). If a short Nifty 50 call is simultaneously opened, does
Upstox treat the NiftyBees pledge as covering the call exposure, or does it require
independent cash margin for the call?

**Resolution:**
- **✅ Confirmed compatible:** NiftyBees pledge counts as covered call collateral — no
  independent cash margin required for the call. Capital efficiency argument holds.
  Quantity constraint (`max_lots` formula) is valid as specified.

**Status:** ✅ Confirmed 2026-05-28 (verbal confirmation from Upstox)

---

## Purpose

Convert the pledged NiftyBees collateral position from a passive hold into an active yield
source. The NiftyBees units earn no options premium while pledged. Selling a 15-delta OTM
Nifty monthly call against these units adds ~2.7–4.2% annualised yield on the collateral
position without changing the fundamental exposure — a sharp rally causes the call to lose
but the ETF units to gain by an offsetting amount.

**Validation approach:** A 6-month paper overlay period (5–6 monthly cycles) is sufficient
to calibrate the cost model, confirm broker mechanics, and measure delta-stop frequency.
The full walk-forward backtest pipeline (signals-eval-core SE5–SE6) is not required — the
hedge is structural and the edge is the IV risk premium, which is well-documented.

---

## Entry Rule

**When:** Same Wednesday-after-expiry entry window as CSP (30–45 DTE for the next monthly
expiry). Coordinate with CSP so both legs are entered in the same cycle — this keeps
monitoring and exit tracking on a single weekly schedule.

**IVR filter:** Skip the cycle if IVR < 25 (trailing 252-day percentile of India VIX).
Same R3 discipline as CSP — at the IV floor, call premium is thin with near-zero positive
expectancy after costs. Log India VIX + IVR at every entry decision, including skipped cycles.

**Strike selection:** Sell the Nifty 50 monthly call at the 15-delta strike. Use the live
Upstox option chain for delta reading (same infrastructure as CSP strike selection).
Limit order at mid of bid/ask; ₹0.25/unit improvement if unfilled after 5 minutes.

**Quantity:** Maximum 1 Nifty lot call (65 units) per ~5,700 NiftyBees units pledged.
This is derived from the CSP collateral calculation:
```
max_lots = floor(niftybees_units_pledged / (nifty_spot / niftybees_ltp × 65))
```
Recompute at each annual NiftyBees leg reset. At current holding (~5,725 units), this gives
exactly 1 lot. Do not sell more call notional than is covered by the pledged position.

---

## Parameters

| Parameter                     | Initial | Sweep range       | Step |
|-------------------------------|---------|-------------------|------|
| Call delta target             | 15      | 10–20             | 5    |
| Exit profit target (% credit) | 50%     | 40%–70%           | 10%  |

Parameter sweep is deferred to post-paper-trading calibration. Initial values are fixed for
the paper-trading phase to keep the comparison clean.

---

## Exit Rules

Three independent triggers — first to fire wins:

1. **Profit target:** Close when the call's mark-to-market value has decayed to ≤50% of entry
   credit. Retains the remaining 50% without holding to expiry (eliminates late-gamma risk).

2. **Time stop:** Close at 21 calendar days from entry if no other trigger has fired.
   Same 21-day clock as CSP.

3. **Delta stop:** Close immediately if call delta crosses **+0.40** (Nifty has rallied
   sharply toward the strike). Fires earlier than the mark-based trigger, at lower gamma,
   yielding better fills in a fast-moving market.

---

## Expected Yield (indicative — pending paper calibration)

At IVR ~35, the 15-delta OTM Nifty monthly call typically collects ₹55–85/unit.

| Component                        | Low      | High     |
|----------------------------------|----------|----------|
| Gross credit per lot (65 units)  | ₹3,575   | ₹5,525   |
| Round-trip costs (est.)          | −₹100    | −₹100    |
| **Net credit per cycle**         | **₹3,475** | **₹5,425** |
| On ₹15.5L notional (per cycle)   | 0.22%    | 0.35%    |
| **Annualised yield**             | **2.7%** | **4.2%** |

These numbers assume 1 lot, IVR ~35, and full cycle held to the profit target or time stop.
Higher IVR (>50) generates richer premium for the same delta target.

---

## What This Strategy Covers and Does Not Cover

**Covered (capped upside is accepted):** A Nifty rally that drives the call past the strike.
NiftyBees appreciates and partially offsets the call loss — the net result is a capped total
return (opportunity cost), not a capital loss. The delta stop limits the realised call loss
by closing before terminal gamma acceleration.

**Not covered:** A Nifty decline. The short call generates premium income during a selloff
(premium decays as Nifty moves away from the strike), but the NiftyBees position loses value.
The covered call is not a hedge against a correction — the CSP (short put) and Finideas
portfolio provide the downside structure.

---

## Paper Trading

**Prefix:** `paper_covered_call_v1`

**Duration:** Minimum 6 months (5–6 monthly cycles). Extend to 12 months if first 2 cycles
are insufficient for comparison to the indicative yield range.

**What to record per cycle (via `record_paper_trade.py`):**
- Entry: strategy = `paper_covered_call_v1`, leg_role = `covered_call`, strike, expiry,
  credit collected (₹/unit), IVR at entry, delta at entry, NiftyBees LTP at entry
- Exit: exit trigger (profit_target / time_stop / delta_stop), credit retained, full P&L

**Retrospective Bhavcopy cross-check:** Once SE7.1 Bhavcopy data is available, cross-check
paper entry/exit prices against Bhavcopy settle_price for validation. Any systematic
discrepancy (paper mid vs. actual Bhavcopy) >₹5/unit should be investigated.

---

## Failure Conditions (paper trading phase)

| Condition                                       | Action                                         |
|-------------------------------------------------|------------------------------------------------|
| Delta stop fires in >40% of cycles              | Strike is too close; test 10-delta target      |
| Net realised yield < 1% annualised over 6m     | IV floor is not generating sufficient premium; reconsider IVR filter threshold |
| Upstox broker mechanics confirmed incompatible | Retire this strategy; reconfigure as cash-covered position if free margin permits |
| Covered call assignment triggered (exercise)   | Investigate — monthly options are European; exercise before expiry should not occur |

---

## Completion Log

| Date       | Stage   | Outcome | Notes                                           |
|------------|---------|---------|------------------------------------------------|
| 2026-05-27 | —       | Created | Spec from INVESTMENT_STRATEGY_RESEARCH.md §Strategy 4. Pending broker confirmation. |
| 2026-05-28 | Broker  | ✅ Confirmed | Upstox confirmed: NiftyBees pledge covers short call exposure — no independent cash margin required. Hard block cleared. Ready for paper-trading. |
