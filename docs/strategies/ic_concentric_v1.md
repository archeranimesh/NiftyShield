# Concentric Iron Condor — Nifty 50 v1

| Field                   | Value                                                                 |
|-------------------------|-----------------------------------------------------------------------|
| Name                    | Concentric Iron Condor on Nifty 50                                    |
| Version                 | v1                                                                    |
| Author                  | Animesh Bhadra (archeranimesh)                                        |
| Date                    | 2026-05-21                                                            |
| Status                  | **Draft — under discussion. Not yet paper-traded or backtested.**     |
| Underlying              | Nifty 50 index (`NSE_INDEX|Nifty 50`)                                 |
| Instrument              | Nifty 50 options — four simultaneous ICs across four expiry horizons  |
| Relationship to v1      | Independent hypothesis. ic_nifty_v1 runs its own paper/backtest pipeline separately. |

---

## Purpose and Hypothesis

This is a paper-trading hypothesis, not a production strategy. The goal is to test whether
running four Iron Condors simultaneously — each at a different expiry horizon — produces a
more consistent, lower-variance theta-decay income stream than any single-expiry IC.

**Core hypothesis:**

> Four ICs at yearly / quarterly / monthly / weekly expiries, structured so their wings are
> concentric (each shorter-duration IC sits inside the wings of the next longer-duration IC),
> creates a layered risk architecture where: (a) premium income flows continuously from all
> four horizons, (b) adjustments cascade inward-to-outward — the weekly absorbs most intraday
> pressure, the monthly absorbs swing moves, the quarterly and yearly are rarely touched, and
> (c) the outer IC's short strikes serve as natural roll-boundaries when adjusting an inner IC.

**What success looks like:** After running all four layers for at least one full yearly cycle,
the combined P&L distribution shows lower drawdown depth and shorter drawdown duration than a
single monthly IC of equivalent notional size, with comparable or better total premium capture.

**This document is a living draft.** Open design decisions are flagged throughout with
`⚠️ OPEN:` markers. These must be resolved before paper trading begins.

---

## The Concentric Property

The concentric wing structure is not manually engineered — it emerges automatically from
using delta-based strike selection across timeframes.

**Why this works:** A fixed delta target (e.g., 15Δ short put) sits progressively further OTM
as DTE increases, because longer-dated options have more time value to distribute across a
wider price range. With Nifty at approximately 24,000:

| Layer    | Approx DTE at entry | 15Δ short put (approx) | 15Δ short call (approx) |
|----------|--------------------:|----------------------:|------------------------:|
| Yearly   | 200–350             | ~18,500–19,500        | ~28,500–29,500          |
| Quarterly| 60–120              | ~21,000–22,000        | ~26,000–27,000          |
| Monthly  | 30–45               | ~22,500–23,000        | ~25,000–25,500          |
| Weekly   | 5–10                | ~23,300–23,500        | ~24,500–24,700          |

> *All strike estimates are illustrative at Nifty ~24,000, current IV regime. Actual deltas
> must be computed from live option chain at entry.*

Each inner IC's short strikes sit comfortably inside the outer IC's short strikes. This is
the concentric property. If delta-based selection ever produces overlapping strikes between
two adjacent layers, that is a signal that IV term structure has collapsed (flat or inverted)
and entry for the inner layer should be deferred.

**Implication for adjustments:** When rolling an inner IC's tested wing, the outer IC's
short strike at the same expiry horizon acts as the maximum roll boundary. Rolling the
weekly short put beyond the monthly short put level means the weekly is now stacked on top of
the monthly — the adjustment budget is exhausted; close instead of roll.

---

## Layer Definitions

### Layer 1 — Yearly IC

| Parameter        | Value / Status                                                       |
|------------------|----------------------------------------------------------------------|
| Target expiry    | December expiry of the current or next calendar year                 |
| DTE at entry     | 200–350 DTE                                                          |
| Entry timing     | Once per year — first eligible trading day after the prior year's December expiry settles |
| Short put Δ      | ⚠️ OPEN: 10Δ or 15Δ — see Open Questions                           |
| Short call Δ     | ⚠️ OPEN: 8Δ or 10Δ                                                 |
| Wing width       | ⚠️ OPEN: fixed points vs ATR-proportional — see Open Questions      |
| Role             | Structural anchor. Slow-moving vega trade. Almost never adjusted.    |
| Liquidity risk   | **High.** OI at far-OTM yearly strikes is thin. Log observed bid/ask spreads at every entry and exit. If spread > 10% of mid on any leg, log it — this data validates whether yearly IC is realistically executable. |

### Layer 2 — Quarterly IC

| Parameter        | Value / Status                                                       |
|------------------|----------------------------------------------------------------------|
| Target expiry    | Next quarterly expiry (March / June / September / December)          |
| DTE at entry     | 60–120 DTE                                                           |
| Entry timing     | Wednesday after the prior quarterly expiry settles, if within the DTE window |
| Short put Δ      | 15Δ                                                                  |
| Short call Δ     | 10–12Δ                                                               |
| Wing width       | ⚠️ OPEN: 1000 points or ATR-proportional                            |
| Role             | Medium-term premium layer. Adjusted only on large trend moves.        |
| Liquidity risk   | Low-moderate. Quarterly options have adequate OI.                    |

### Layer 3 — Monthly IC

| Parameter        | Value / Status                                                       |
|------------------|----------------------------------------------------------------------|
| Target expiry    | Next monthly expiry (last Thursday of the month)                     |
| DTE at entry     | 30–45 DTE                                                            |
| Entry timing     | Wednesday after the prior monthly expiry settles                     |
| Short put Δ      | 15Δ (standalone) / 8–10Δ (if CSP also open — portfolio delta check) |
| Short call Δ     | 10–12Δ                                                               |
| Wing width       | 500 points (same as ic_nifty_v1 — baseline reference)               |
| Role             | Core theta-collection layer. Primary comparison baseline vs ic_nifty_v1. |
| Liquidity risk   | Low. Standard monthly options have the deepest OI.                   |

### Layer 4 — Weekly IC

| Parameter        | Value / Status                                                       |
|------------------|----------------------------------------------------------------------|
| Target expiry    | Next weekly expiry (**Tuesday**)                                     |
| DTE at entry     | ~6 DTE (entered Wednesday, expires following Tuesday)                |
| Entry timing     | **Wednesday 10:30 AM IST** — after the prior week's Tuesday expiry settles |
| Hard time stop   | **Monday 2:30 PM IST** — exit all legs irrespective of P&L. Never hold into Tuesday expiry day. |
| Short put Δ      | ⚠️ OPEN: 8–10Δ recommended (15Δ is too close to ATM at 7 DTE)      |
| Short call Δ     | ⚠️ OPEN: 5–8Δ                                                      |
| Wing width       | ⚠️ OPEN: 100–200 points (500 points is structurally unworkable at 7 DTE — long protection would be nearly worthless with a wide spread) |
| Role             | High-frequency adjustment layer. Most active. Absorbs intraday pressure. |
| Liquidity risk   | Moderate. Near-ATM weekly options liquid; far-OTM weekly options thin. Delta target must be chosen to stay within liquid strikes. |

---

## Entry Rules (All Layers)

**Concentric overlap check (mandatory before any entry):**
Before entering any layer, verify that its short strikes sit inside the short strikes of the
next outer layer (if that outer layer is currently open). If they do not — i.e., the
term structure has compressed enough that delta-based selection produces the same or adjacent
strikes — defer the inner layer's entry and log the reason.

**Minimum credit gate:** Each layer must independently meet its own minimum credit threshold.
⚠️ OPEN: Define per-layer minimum credit gate (as % of wing width). The monthly IC inherits
the 15% rule from ic_nifty_v1. Weekly and quarterly need separate calibration.

**IVR filter:** ⚠️ OPEN — not enforced in v1. Log India VIX and IVR at every entry for all
four layers. This data will inform whether a per-layer IVR filter is warranted.

**Entry time:** 10:00–10:30 AM IST for all layers. Do not enter outside this window.

**Execution:** Limit order at combined net credit mid per IC. If unfilled after 5 minutes,
improve limit by ₹0.25 and resubmit once. If still unfilled, log as skipped cycle.

**Record at entry (all four layers):** strikes, expiry, DTE, delta of each short leg,
net credit, IV of each short leg, India VIX, IVR, underlying spot, observed bid/ask spread
on each leg (liquidity audit), concentric overlap check result.

---

## Exit Rules

Each layer manages its own exits independently. Exits are not coordinated across layers.

### Per-layer exit triggers (first to fire wins):

| Trigger           | Weekly     | Monthly    | Quarterly  | Yearly     |
|-------------------|-----------|-----------|-----------|-----------|
| Profit target     | **>75% of original net credit** | 50% of credit | 50% of credit | 50% of credit |
| Loss stop         | 1.5× credit | 2.0× credit | 2.0× credit | 2.0× credit |
| Delta stop        | 0.30Δ on either short leg | 0.35Δ | 0.35Δ | 0.40Δ |
| Time stop         | **Monday 2:30 PM IST** (hard — no exceptions) | 14 DTE | 21 DTE | 30 DTE |
| Never hold to expiry | Always  | Always    | Always    | Always    |

> **Weekly profit target (>75%):** Higher than a naked IC because the long-leg tightening
> adjustment progressively reduces max loss over the trade's life — by the time 75% is
> captured, the wings are typically much narrower than at entry, making the remaining risk
> small. The 75% threshold is measured against the **original net credit at entry** (before
> tightening debits), not the adjusted net credit.
>
> **Weekly time stop (Monday 2:30 PM):** Hard rule — no exceptions. The trade window is
> Wednesday 10:30 AM to Monday 2:30 PM (~4 trading days). Exiting Monday afternoon avoids
> holding into Tuesday expiry day while still leaving enough DTE for reasonable liquidity
> on the exit fills.
>
> **Yearly delta stop is looser (0.40Δ)** because at 200+ DTE, a single large-move day can
> push an option to 0.40Δ without it being a trend reversal — giving the position more room
> before triggering an exit preserves the structural vega trade.

### No re-entry within a cycle:
After any exit from a given layer — for any reason — do not re-enter that layer's expiry.
Wait for the next standard entry window for that layer.

---

## Adjustment Rules

**Philosophy:** Most adjustments happen in the weekly and monthly layers. The quarterly and
yearly layers are structural anchors — they are exited per the exit stack above, not rolled.

### When to adjust vs when to exit

An adjustment (roll) is preferred over exit when:
1. The trigger is delta-based (not loss-stop or time-stop), AND
2. The layer being adjusted has enough DTE remaining for the rolled position to recover theta, AND
3. The roll does not require placing the new short strike outside the next outer layer's short strike.

If any of these three conditions fails, exit instead of rolling.

### Long-leg tightening (Weekly IC only)

This adjustment applies exclusively to the **bought (long) legs** of the weekly IC. The
short legs are never touched by this rule.

**Concept:** At any point during the trade's life, monitor the premium differential between
the current long leg and the next strike one step closer to the short leg (i.e., one step
toward ATM). When this differential is ≤ ₹3, it costs almost nothing to step the long leg
closer. This fires in **both market directions**:

- Market moves **toward** the short strike → short-side premiums spike, adjacent differentials
  compress on the threatened side → tighten the long leg to improve delta hedge and reduce max loss.
- Market moves **away from** the short strike → that side's premiums decay, adjacent
  differentials compress as all strikes approach zero → tighten the long leg cheaply while
  the position is safe, so protection is already closer if the market reverses.

**Example (13→14 May 2026):**
Spot moved up (23,413 → 23,491). Put side became safer.
22500PE decayed from ₹31 → ₹10.8. Adjacent 22550PE (one step toward short at 22800) = ₹12.4.
Differential = ₹1.6 → trigger fires. Sell 22500PE at ₹10.8, buy 22550PE at ₹12.4. Net debit
₹1.6/unit = ₹104 (65 units). Long put moves 22500 → 22550, 50 points closer to the short.

The trigger is purely premium-differential-based, not directional.

**Trigger:** At any 15-minute check during market hours:

```
abs(next_strike_premium − current_long_leg_premium) ≤ ₹3
```

where `next_strike_premium` is the premium of the strike one step closer to the short leg
(i.e., one step toward ATM for puts; one step toward ATM for calls).

**Action:**
1. Exit (sell) the current long leg at market.
2. Buy the next strike one step closer to the short leg.
3. Net debit = difference between the two premiums (≤ ₹3 by trigger condition).
4. Record: old strike, new strike, debit paid, reason = "long-leg tighten".

**This applies independently to both sides:**
- Put spread: long put walks up toward the short put as the market falls.
- Call spread: long call walks down toward the short call as the market rallies.
- Each side triggers and executes independently — a call-side tighten does not depend on
  what the put side is doing.

**No limit on number of tightening steps per cycle.** The long leg may step multiple times
in a single session if the market keeps moving and the ₹3 threshold keeps being met. The
only hard stop is when the long leg reaches the strike immediately adjacent to the short leg
(one strike away) — at that point the spread width is at minimum and no further tightening
is possible.

**Minimum spread floor:** ⚠️ OPEN — define the minimum number of strikes between long and
short leg below which no further tightening occurs (e.g., never narrow to fewer than 2
strikes between long and short). Prevents the position from degenerating into a near-zero
width spread that has no practical protection value.

**The ₹3 threshold is a parameter, not a constant.** For the paper-trade hypothesis,
start at ₹3 and log every tightening event with the actual premium differential at trigger
time. This data will reveal whether ₹3 is too tight (rarely triggers) or too loose
(over-trades). Candidate range: ₹2–₹5.

**Why only the weekly IC:** At 5–10 DTE, gamma is high enough that intraday moves
materially change the premium differential between adjacent strikes. At monthly DTE (30–45),
this differential compresses much more slowly — the tightening trigger would rarely fire and
the incremental delta improvement per step is smaller. The monthly and outer layers use the
roll mechanics below instead.

---

### Roll mechanics (inner layers only: Weekly and Monthly)

**Trigger:** Either short leg reaches the layer's delta-stop threshold.

**Action — roll the tested wing:**
1. Buy back the threatened short strike at market.
2. Sell a new short strike further OTM, same expiry, targeting the original entry delta.
3. The new short strike must remain inside the next outer layer's short strike (the roll boundary).
4. The long protection strike shifts proportionally (same wing width).
5. Record: original credit, roll debit/credit, new net position credit, reason for roll.

**Roll limit:** Maximum two rolls per IC per cycle. On the third trigger within the same
cycle, exit the full IC — do not roll again.

**⚠️ OPEN:** What is the adjustment action when the roll boundary is hit (new short strike
would exceed outer layer's short strike)?
- Option A: Close the inner IC entirely.
- Option B: Close only the tested side (become a single vertical spread for the remainder).
- Option C: Buy back only the short strike (become a long vertical — defined debit position).

### Quarterly and Yearly layers — no rolling

These layers use exit-only management. If a delta-stop or loss-stop fires on the quarterly
or yearly IC, close the full IC per the exit stack. The structural position of these outer
layers must not be compromised by rolling into positions that eat into the inner layers'
adjustment space.

---

## Combined Portfolio Delta

Each layer contributes its own net delta. The combined book delta is the sum across all four
layers plus any open CSP or other positions.

**⚠️ OPEN:** Define the combined delta cap for this strategy. ic_nifty_v1 specifies −0.05
to +0.25 combined with CSP. With four concurrent ICs, the delta arithmetic changes
materially. Candidates:

- Per-layer delta caps (each IC manages its own delta budget independently), OR
- Combined portfolio delta cap with a defined layer priority for which IC is adjusted or
  closed first when the cap is breached.

Priority if combined cap used: Weekly closes/adjusts first (cheapest, shortest DTE),
then Monthly, then Quarterly. Yearly is never closed for delta management alone — it is a
structural position and must be managed to its own exit triggers only.

---

## Capital and Margin Requirements

Running four simultaneous ICs means four separate margin blocks. At current Nifty lot sizes:

| Layer     | Wing width (indicative) | Max loss per wing (indicative) | SPAN margin (approx) |
|-----------|------------------------:|-------------------------------:|---------------------:|
| Weekly    | 100–200 pts             | ₹6,500–13,000                 | ⚠️ To be measured   |
| Monthly   | 500 pts                 | ₹32,500                       | ⚠️ To be measured   |
| Quarterly | 1000 pts                | ₹65,000                       | ⚠️ To be measured   |
| Yearly    | ⚠️ TBD                  | ⚠️ TBD                       | ⚠️ To be measured   |

**Total capital requirement:** ⚠️ OPEN — must be computed from live margin calculator before
paper trading begins. For paper trading this is notional, but it must be sized against the
actual capital envelope to be meaningful as a hypothesis test.

---

## Monitoring and Automation Requirements

For the hypothesis to be testable with "no manual intervention," the following must be
implemented or instrumented in the paper trading system:

| Function                              | Frequency       | Priority |
|---------------------------------------|-----------------|----------|
| Delta monitoring — all four layers    | Every 15 min (market hours) | High |
| Profit target check                   | Every 15 min    | High     |
| Loss stop check                       | Every 15 min    | High     |
| Time stop check                       | Daily pre-market | Medium  |
| Concentric overlap check              | At each entry   | High     |
| Roll boundary check                   | Before each roll | High    |
| IVR + VIX logging at entry            | At each entry   | Medium  |
| Bid/ask spread logging (liquidity audit) | At entry/exit  | Medium  |
| Roll count tracking per cycle         | Continuous      | High     |

The weekly IC specifically requires intraday delta monitoring — it cannot be managed on
daily snapshots alone given the high gamma near expiry.

---

## Open Design Decisions

These must be resolved (through discussion or initial paper-trade observation) before
the spec is considered final.

| # | Question | Options | Impact |
|---|----------|---------|--------|
| 1 | Wing width for yearly IC | Fixed 1500 pts / ATR-proportional / % of spot | Risk profile, liquidity, margin |
| 2 | Wing width for quarterly IC | Fixed 1000 pts / ATR-proportional | Same |
| 3 | Wing width for weekly IC | 100 pts / 150 pts / 200 pts | Credit quality, gamma risk |
| 4 | Delta targets for yearly IC | 10Δ or 15Δ short put; 8Δ or 10Δ short call | Concentric spacing, premium income |
| 5 | Delta targets for weekly IC | 5–8Δ or 8–10Δ | Liquidity, credit vs safety |
| 6 | Action when roll boundary is hit | Close IC / close tested side only / buy back short | P&L outcome on large moves |
| 7 | Combined portfolio delta cap | Per-layer independent / combined cap with priority | Risk management framework |
| 8 | Minimum credit gate per layer | % of wing width — define per layer | Entry quality filter |
| 9 | Yearly IC entry: full 300+ DTE or enter at 200 DTE? | Enter at listing / enter at 200 DTE window | Vega exposure at entry |
| 10 | Weekly IC: skip expiry week of monthly/quarterly expiry? | Skip (avoid overlapping expiry week) / allow | Execution complexity |
| 11 | Long-leg tightening threshold | ₹2 / ₹3 / ₹5 — start at ₹3, calibrate from paper data | Trigger frequency, transaction cost drag |
| 12 | Minimum spread floor (tightening stop) | 1 strike / 2 strikes between long and short | Prevents degenerate near-zero-width spread |

---

## What This Hypothesis Will Tell Us

After running for one full yearly cycle with complete records:

1. **Premium consistency:** Does the four-layer structure produce more consistent weekly theta
   income than a single monthly IC? Measured by standard deviation of weekly P&L across all
   layers combined.

2. **Adjustment frequency:** How often do weekly and monthly layers require rolling? Does the
   roll mechanic add net positive EV or does it just delay inevitable losses?

3. **Yearly IC viability:** Are the yearly IC fills at realistic bid/ask spreads? If the
   liquidity audit shows systematic fill quality degradation, the yearly layer is not viable
   for live deployment regardless of theoretical P&L.

4. **Concentric property stability:** Does the concentric structure hold across different IV
   regimes, or does IV term-structure compression cause layer overlap (invalidating the
   roll-boundary logic)?

5. **Drawdown profile:** Does the layered structure produce shallower drawdowns than the
   monthly-only baseline, or does a large move simultaneously pressure all layers?

---

## Relationship to ic_nifty_v1

| Dimension               | ic_nifty_v1                        | ic_concentric_v1                   |
|-------------------------|------------------------------------|------------------------------------|
| Open positions at a time | 1                                 | 4 (one per timeframe)              |
| Adjustments             | None — exit only                  | Rolling allowed on weekly + monthly |
| Wing width              | Fixed 500 pts                     | Variable per layer (TBD)           |
| Automation level        | EOD snapshot sufficient           | Requires intraday delta monitoring |
| Paper trade purpose     | Validate backtest, gate live       | Hypothesis test — no live path yet |
| Backtest required first | Yes (Phase 2 gate)                 | No — paper first, backtest if viable |

These are independent strategies. ic_nifty_v1 results do not gate ic_concentric_v1 paper
trading, and vice versa.

---

## Revision History

| Date       | Change                                                    |
|------------|-----------------------------------------------------------|
| 2026-05-21 | Initial draft from design discussion. All open questions flagged. |
| 2026-05-21 | Added long-leg tightening rule for weekly IC. OQ #11 (threshold) and #12 (floor) added. |
| 2026-05-21 | Corrected tightening rule — trigger is direction-agnostic (fires on decay AND on rally). Added real example from 13–14 May 2026 trade. |
| 2026-05-21 | Weekly IC rules finalised: entry Wednesday 10:30 AM, profit target >75% of original credit, hard time stop Monday 2:30 PM. |
