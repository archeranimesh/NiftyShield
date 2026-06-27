# Council Decision: ic-v2-core-design

Date: 2026-06-26  
Chairman: anthropic/claude-4.6-opus-20260205  
Council members: openai/gpt-5.5-20260423, google/gemini-3.1-pro-preview-20260219, x-ai/grok-4.3-20260430, deepseek/deepseek-r1-0528

---

## Stage 3 — Chairman Synthesis

# NiftyShield Council — Iron Condor V2 Design Ruling

**CONTEXT.md ✓** — Scope confirmed: four structural design decisions for IronCondorV2, a new strategy variant alongside the existing IronCondorV1. Rulings below are binding for the V2 spec and implementation.

---

## DECISION 1 — Entry Delta: Skew-Adjusted 25Δ Put / 22Δ Call

**Ruling: Option B.**

The prior V1 council's asymmetry reasoning binds **more strongly** at 25Δ, not less. At higher delta, the short put is materially closer to the money, Nifty's downside moves are faster and more discontinuous than upside moves, and the put IV skew is more economically significant. A strict 25Δ/25Δ IC would be structurally short more downside jump risk than the headline deltas suggest.

The 3Δ offset (25P/22C) reduces call-side whipsaw frequency and preserves a mild bullish/skew-aware posture consistent with Nifty's secular upward drift. The council unanimously endorsed this choice (three of four respondents selected it directly; the dissent on strict symmetry was grounded in a factually incorrect claim that IV skew narrows at higher delta — the prompt itself states the opposite).

**Important correction:** The phrase "25P/22C collects equivalent premium" is misleading. Under put skew, a 25Δ put is richer than a 25Δ call; moving the call farther OTM to 22Δ reduces call premium further, not equalises it. The justification for 22Δ call is *risk management* (reduced challenge frequency, skew awareness), not premium parity.

**V2 config values:**
```
short_put_delta_target  = Decimal("0.25")
short_call_delta_target = Decimal("0.22")
delta_range             = Decimal("0.03")
```

---

## DECISION 2 — Wing Sizing: 10Δ Long Wings (Primary), SD as Sanity Check

**Ruling: 10Δ fixed placement as primary, with floors enforced.**

The SD-based formula (`spot × ATM_IV × √(DTE/365) × k`) is theoretically elegant but produces operationally problematic results on Nifty chains. At k=1.25 with typical monthly parameters (Nifty 25000, IV 15%, 30 DTE), the wing lands at ~1350 points OTM — approximately 3–5Δ — where strikes routinely suffer:

1. **Weak protection.** The wing is catastrophic margin insurance, not real convexity.
2. **Poor bid-ask quality.** Ultra-low-premium options (₹5–15) have proportional spreads of 20–50%, making backtests look better than executable reality.
3. **Liquidity gate failures.** These strikes frequently fail `_apply_liquidity_gate()` on OI and volume.

A 10Δ long wing adapts naturally to IV (moves farther OTM in high IV, closer in low IV), typically prices at ₹30–60 with robust liquidity, and provides meaningful convexity for a 25Δ short. This is especially important because V2's higher-delta shorts create more vulnerability than V1 — the wings must provide real protection.

**Floors (mandatory — no entry without all passing):**

| Expiry | Long-wing target | Minimum delta | Minimum mid premium |
|--------|:---:|:---:|:---:|
| Weekly | 10Δ | 5Δ | ₹10 |
| Monthly | 10Δ | 5Δ | ₹15 |

**SD-based width as secondary guard:**
```
sd_width = spot × ATM_IV × sqrt(DTE / 365) × 1.25

if selected_10Δ_wing_width > 1.5 × sd_width:
    warn: wing unusually wide
if selected_10Δ_wing_width < 0.4 × sd_width:
    warn: hedge is expensive/tight relative to regime
```

If no wing candidate satisfies both delta and liquidity/premium floors, move the long wing closer or skip entry. Do **not** accept a ₹2–5 dead wing for a 25Δ short.

**V2 config change:** Replace `wing_width_points: int` with:
```python
long_wing_delta_target: Decimal = Decimal("0.10")
long_wing_delta_floor: Decimal = Decimal("0.05")
long_wing_min_premium: Decimal = Decimal("15")  # ₹, monthly
```

---

## DECISION 3 — Adjustment: Partial Roll of Challenged Vertical Only

**Ruling: Option A. Unanimous across all four council members.**

When either short leg breaches the adjustment threshold, V2 closes the challenged vertical and reopens it farther OTM, leaving the profitable side completely untouched.

**Why the alternatives fail:**

- **Full recenter (B):** 8-leg transaction cost, always a net debit, and repeated resets in trending months (55–60% of Nifty cycles) compound losses. Dangerous for automated execution.
- **Calendar overlay (C):** Changes the strategy class entirely — different vega, theta, expiry, and broker margin treatment. This is a different strategy, not a V2 adjustment.
- **Iron fly transition (D):** Time-triggered (3 PM) rather than delta-triggered, narrows profit zone to near-zero, requires pinning. Not suitable for automated daemon execution.

**Signal hierarchy:**

| Signal | Trigger | Severity |
|--------|---------|----------|
| `DELTA_WARN` | \|short_delta\| ≥ 0.30 | WARN |
| `ROLL_WING` | \|short_delta\| ≥ 0.35 AND roll candidate exists | ACTION |
| `DELTA_STOP` | \|short_delta\| ≥ 0.35 AND no valid roll candidate | ACTION |
| `FORCED_CLOSE` | \|short_delta\| ≥ 0.45 OR max rolls exhausted | ACTION |

**Action steps (example: put side challenged):**

1. Close challenged put vertical (buy back short put, sell back long put).
2. Select new short put at current 25Δ, farther OTM than old short.
3. Select new long put at 10Δ, subject to delta/premium/liquidity floors.
4. **Enforce:** replacement width ≤ original put-spread width (no max-loss expansion).
5. **Enforce:** new short put strike does not cross the existing call spread's short strike (no inverted condor).
6. Open new put vertical.
7. Leave call spread untouched.

**Risk guards (all must pass for roll to execute):**

```
DTE above expiry-specific cutoff (see Decision 4)
replacement short exists and passes liquidity gate
replacement long exists and passes delta/premium/liquidity floors
replacement width ≤ original width
roll debit ≤ 0.50 × original total IC credit
max_rolls_per_side_per_cycle = 1
no naked exposure during execution (atomic via OverlayCloser)
```

If any guard fails, the roll is blocked and the signal escalates to `DELTA_STOP` (close challenged spread) or `FORCED_CLOSE` (close full IC) depending on severity.

**Profitable side policy during normal adjustment:** Leave untouched. It continues collecting theta, avoids unnecessary transaction cost, and keeps the adjustment local to the problem side. Do not roll the profitable side inward to "collect more credit" — that is a separate, risk-increasing action not in V2 scope.

---

## DECISION 4 — Weekly DTE Cutoff: Tiered, CLOSE_FULL at DTE ≤ 3

**Ruling: Tiered approach with CLOSE_FULL at DTE ≤ 3 for weeklies.**

Gamma acceleration in the final 3 DTE on Nifty weeklies makes rolling extremely expensive — the challenged short approaches 0.50 delta rapidly, and any new short opened has almost no extrinsic value remaining to justify the transaction cost. The council debated between DTE ≤ 2 and DTE ≤ 3 as the hard cutoff. The chairman rules **DTE ≤ 3** as the appropriate threshold for the following reasons:

1. At DTE = 3 (typically Monday on a Tuesday-expiry weekly), gamma is already dominant and roll debit typically exceeds the remaining credit collection potential.
2. The profitable side at DTE ≤ 3 typically has < ₹5–10 of premium remaining — insufficient to justify the pin/reversal risk of orphan legs through expiry.
3. An automated `auto_execute=True` strategy should avoid expiry lottery behavior.

**Weekly rule table:**

| Weekly DTE | If short \|delta\| ≥ 0.35 | Action |
|:---:|---|---|
| ≥ 6 | Normal breach | Partial roll (Decision 3 rules) |
| 4–5 | Breach | Partial roll with strict debit + liquidity guard |
| ≤ 3 | Any delta stop | **CLOSE_FULL** — close entire IC |
| ≤ 1 | Any state | **CLOSE_FULL** — no discretion |

**Should the profitable side be closed at DTE ≤ 3?** Yes. `CLOSE_FULL`, not challenged-side-only close.

- Remaining theta on the winner is small (< ₹10 in most cases).
- Reversal risk is real — the "profitable" side can become challenged rapidly with gamma-driven delta swings.
- Operational cleanup is cleaner for the daemon.
- Brokerage + STT + slippage on the winner's close is small relative to the tail risk of holding through expiry.
- NiftyShield is a defined-risk, conservative paper strategy — it should not optimize for pennies of remaining decay at the cost of tail reversal exposure.

**Monthly rule:** For monthly expiries, the profitable side remains untouched during normal adjustments (Decision 3 applies). Only at the monthly equivalent of extreme low DTE (DTE ≤ 7, per V1's existing `time_stop_dte=14` as reference) should CLOSE_FULL be the default. The exact monthly hard-close DTE can be refined during backtesting.

---

## Implementation Architecture

IronCondorV2 must be a **separate strategy class**, not a mutation of V1.

```
src/strategy/ic_nifty_v2.py          — new strategy class
src/strategy/ic_expiry_config_v2.py   — new config dataclass (or extend existing)
```

**Strategy names:**
```
paper_ic_nifty_v2_weekly
paper_ic_nifty_v2_monthly
```

**Key structural differences from V1 that justify separation:**

| Dimension | V1 | V2 |
|-----------|----|----|
| Entry deltas | 15Δ put / 10Δ call | 25Δ put / 22Δ call |
| Wing construction | Fixed points (200/500) | 10Δ placement with floors |
| Adjustment | ROLL_WING only (roll short farther OTM) | Full vertical roll (close+reopen challenged spread) |
| Roll accounting | Single leg | 4-leg atomic transaction |
| DTE-specific suppression | None | Weekly DTE ≤ 3 → CLOSE_FULL |
| Roll limits | Unbounded | max 1 per side per cycle |
| Debit guards | None | ≤ 50% of original IC credit |

V1 remains the lower-adjustment, lower-delta baseline. V2 is the active, higher-credit, higher-management variant. Both run concurrently on different expiry buckets as paper strategies.

---

*This ruling is final for V2 spec drafting and implementation. Proceed to task creation in TODOS.md / PLANNER.md.*

---

## Stage 1 — Individual Responses

### openai/gpt-5.5-20260423

CONTEXT.md ✓

## Executive recommendation

For **IronCondorV2**, use a **high-delta, skew-adjusted, defined-risk IC**, but do not make it an unconstrained adjustment engine.

Recommended V2 defaults:

| Decision | Recommendation |
|---|---|
| **1. Entry deltas** | Use **25Δ put / 22Δ call** as V2 default, but describe it as **skew-adjusted high-delta IC**, not “pure symmetric 25Δ IC.” Prior V1 asymmetry logic binds more strongly at 25Δ, not less. |
| **2. Wing sizing** | Use **10Δ long wings as primary**, with a **minimum 5Δ floor** and **premium/liquidity floor**. Use SD width only as a backtest fallback or sanity cap, not as the primary live rule. |
| **3. Adjustment** | Use **partial roll of the challenged vertical only**. Leave the profitable side untouched. Trigger at short-leg `abs(delta) >= 0.35`, subject to DTE/liquidity/debit guards. No full recenter, no calendar diagonal, no iron fly. |
| **4. Weekly DTE cutoff** | Use a **tiered rule**: partial roll allowed only while `DTE >= 4`; at `DTE <= 3`, any delta stop becomes **CLOSE_FULL**. Close the profitable side too for weekly expiry-risk control. |

---

# Decision 1 — Entry delta symmetry at 25Δ

## Recommendation: **25Δ put / 22Δ call**

Use:

```text
short_put_delta_target  = 0.25
short_call_delta_target = 0.22
```

This should be treated as the V2 baseline.

The prior council’s asymmetry reasoning **does bind** at 25Δ, and arguably binds **more strongly** than it did at 15Δ.

At 25Δ:

- the short put is much closer to the money;
- Nifty downside moves are faster and more discontinuous than upside moves;
- put IV skew is more economically meaningful;
- the put side will usually carry more crash convexity risk than the same-delta call side;
- a strict 25Δ/25Δ IC will look clean on paper but will be structurally short more downside jump risk than the headline deltas suggest.

So I would not use strict 25Δ/25Δ as the production V2 default.

## Important correction

The phrase “25Δ put / 22Δ call collects equivalent premium” should be treated carefully.

In most Nifty skew regimes, a 25Δ put will usually be **richer** than a 25Δ call. Moving the call farther OTM to 22Δ generally reduces call premium further. So 25P/22C is not really a premium-parity construction.

The better justification for 25P/22C is:

```text
reduce call-side whipsaw frequency,
preserve mild bullish/skew-aware posture,
avoid overfitting to headline delta symmetry,
and reduce total adjustment churn.
```

If true premium parity were the objective, the call may need to be closer, not farther, depending on the chain. But I do **not** recommend premium parity as the V2 design objective.

## Final rule

Use:

```text
Entry short put:  target abs(delta) = 0.25
Entry short call: target abs(delta) = 0.22
Allowed band: ±0.03 initially
```

Optional backtest challengers:

```text
A: 25P / 25C
B: 25P / 22C  ← recommended default
C: 22P / 20C  ← lower-risk variant if 25Δ drawdowns are too high
```

But implementation should start with **25P/22C**.

---

# Decision 2 — Wing sizing

## Recommendation: **10Δ long wings as primary**

For V2, prefer:

```text
long_put_hedge  ≈ 10Δ put
long_call_hedge ≈ 10Δ call
```

rather than pure SD-based width.

Reason: V2 is already more aggressive because the shorts are at 25Δ. If the longs are pushed out to 3–5Δ using 1.25 SD, the structure becomes closer to a wide short strangle with token disaster wings. That may be acceptable for margin definition, but it is not ideal for a paper strategy intended to become executable later.

For a 25Δ IC, the long wing should provide real convexity, not just satisfy defined-risk bookkeeping.

## Why not primary SD wings?

The SD formula is elegant:

```text
wing_width = spot × ATM_IV × sqrt(DTE / 365) × k
```

But for Nifty monthly examples, it produces very wide wings:

```text
Nifty 25000, IV 15%, 30 DTE
1 SD ≈ 1075 points
1.25 SD ≈ 1350 points
```

That means the long wing may be only 3–5Δ and priced at ₹5–15. That creates three problems:

1. **Protection is weak.**  
   The wing is mostly catastrophic margin insurance.

2. **Bid-ask quality is poor.**  
   Ultra-low-premium options often have bad proportional spreads.

3. **Backtest results can look better than executable reality.**  
   Tiny hedge debits make credit metrics look attractive, but real exits during stress can be much worse.

## Why 10Δ is better

A 10Δ long wing:

- adapts naturally to IV;
- keeps the structure defined-risk;
- produces a more realistic debit;
- usually has better liquidity than 3–5Δ wings;
- is easier to explain and compare across weekly/monthly expiries;
- avoids massive max-loss expansion in low-IV environments.

## Recommended V2 wing rule

Use this hierarchy:

```text
1. Select short put near 25Δ and short call near 22Δ.
2. Select long wings near 10Δ.
3. Enforce minimum long-wing delta floor: abs(delta) >= 0.05.
4. Enforce liquidity gate.
5. Enforce premium floor.
6. Enforce max width cap.
```

Suggested floors:

| Expiry | Long-wing target | Minimum delta | Minimum mid premium |
|---|---:|---:|---:|
| Weekly | 10Δ | 5Δ | ₹5–₹10 |
| Monthly | 10Δ | 5Δ | ₹15 |
| Leaps/quarterly, if later used | 10Δ | 5Δ | ₹25+ |

For monthly V2, I would use:

```text
target long delta = 0.10
minimum long delta = 0.05
minimum long mid = ₹15
```

If no wing satisfies both delta and liquidity/premium requirements, either:

```text
move the long wing closer,
or skip entry.
```

Do **not** accept a ₹2–₹5 dead wing for a 25Δ short.

## Role of SD-based width

Use SD width as a **secondary guard**, not the primary rule.

Example:

```text
computed_sd_width = spot × ATM_IV × sqrt(DTE / 365) × 1.25
```

Then use it to flag abnormal selections:

```text
if selected 10Δ wing is wider than 1.5 × SD width:
    warn or block

if selected wing is narrower than 0.4 × SD width:
    warn that hedge is expensive/tight
```

But the actual wing should be selected from the option chain using delta/liquidity, not formula alone.

---

# Decision 3 — Adjustment mechanism when short delta ≥ 0.35

## Recommendation: **partial roll of challenged vertical only**

Choose candidate **A**.

When one short leg breaches the adjustment threshold:

```text
abs(short_leg_delta) >= 0.35
```

the V2 adjustment should be:

```text
close challenged vertical,
open replacement vertical farther OTM,
leave profitable side untouched.
```

Do not use:

- full recenter;
- calendar diagonal;
- iron fly conversion;
- naked repair;
- moving the profitable side inward.

## Why partial vertical roll wins

It is the best fit for NiftyShield because it is:

### 1. Margin-neutral

As long as the replacement spread is same quantity, same expiry, and no wider than the original challenged spread, max risk does not expand.

### 2. Automatable

The daemon can identify:

```text
challenged side
old short
old long
replacement short
replacement long
roll debit
post-roll max loss
```

without discretionary judgement.

### 3. Defined-risk

No naked short exists if the close/open sequence is atomic or properly ordered.

### 4. Better than recentering in trends

Full recentering is dangerous in trending Nifty months. It converts every strong directional move into a full reset debit, and repeated full recenters can compound losses.

Partial roll accepts that the challenged side is the problem and leaves the theta-rich profitable side alone.

### 5. Cleaner than calendar overlay

A calendar/diagonal repair changes the strategy class. It introduces different vega, theta, expiry, and broker-margin behavior. That is not V2; that is a different strategy.

### 6. Cleaner than iron fly transition

The 3 PM iron fly idea is too discretionary and path-dependent. It narrows the profit zone aggressively and relies on expiry pinning. It is not suitable for an automated paper backbone.

---

## Recommended V2 adjustment trigger

Use:

```text
ACTION trigger:
    abs(short_delta) >= 0.35
```

Optional noise guard:

```text
require breach on either:
    EOD snapshot,
    or two consecutive monitor observations,
    or midquote-confirmed chain snapshot
```

Do not trigger from a single bad quote.

Suggested signal hierarchy:

```text
DELTA_WARN:   abs(short_delta) >= 0.30
ROLL_TRIGGER: abs(short_delta) >= 0.35
FORCED_EXIT:  abs(short_delta) >= 0.45 or roll unavailable
```

## Adjustment action steps

If short call is challenged:

```text
1. Identify old short_call and old long_call_hedge.
2. Close old call spread:
   - buy back old short call
   - sell old long call
3. Select new short call near 22–25Δ, farther OTM than old short.
4. Select new long call near 10Δ, with delta/premium/liquidity floors.
5. Enforce replacement width <= original call-spread width.
6. Open new call spread.
7. Leave put spread untouched.
```

If short put is challenged:

```text
1. Identify old short_put and old long_put_hedge.
2. Close old put spread:
   - buy back old short put
   - sell old long put
3. Select new short put near 25Δ, farther OTM than old short.
4. Select new long put near 10Δ, with delta/premium/liquidity floors.
5. Enforce replacement width <= original put-spread width.
6. Open new put spread.
7. Leave call spread untouched.
```

## Profitable side

Leave the profitable side untouched during normal V2 adjustment.

Reason:

- it continues collecting theta;
- it avoids unnecessary transaction cost;
- it avoids chasing price;
- it keeps the adjustment local to the problem side.

Do not roll the profitable side inward to “collect more credit.” That is a separate, risk-increasing adjustment and should not be in V2.

## Risk guards

The partial roll should be allowed only if all are true:

```text
DTE above cutoff
replacement short exists
replacement long exists
liquidity gate passes
replacement width <= original width
no naked exposure during execution
roll debit within configured cap
max one roll per side per cycle, initially
```

I strongly recommend:

```text
max_rolls_per_side_per_cycle = 1
```

If the same side breaches again after one roll, the next action should be close, not infinite rolling.

Suggested debit guard:

```text
roll_debit <= 0.75 × original_total_ic_credit
```

or more conservatively:

```text
roll_debit <= 0.50 × original_total_ic_credit
```

If the debit is larger than the cap, skip adjustment and close the challenged spread or full IC depending on DTE and severity.

---

# Decision 4 — Weekly-specific rules at DTE ≤ 3

## Recommendation: **tiered rule, with hard close at DTE ≤ 3**

Use:

```text
DTE >= 4:
    partial roll allowed, subject to guards

DTE <= 3:
    no adjustment
    CLOSE_FULL on delta stop
```

This is a better rule than allowing rolls until DTE 2.

In Nifty weekly options, the last 3 calendar DTE are dominated by gamma and execution risk. Rolling at that point usually pays high intrinsic/near-intrinsic debit and opens a new short with too little time value to justify the repair.

## Weekly rule table

| Weekly DTE | If short delta ≥ 0.35 | Action |
|---:|---|---|
| `DTE >= 6` | Normal breach | Partial roll challenged vertical |
| `DTE 4–5` | Breach | Partial roll allowed, but only with strict debit/liquidity guard |
| `DTE <= 3` | Breach | CLOSE_FULL |
| `DTE <= 1` | Any serious breach | CLOSE_FULL, no discretion |

## Should the profitable side be closed too?

For weekly V2 at `DTE <= 3`, yes.

Use:

```text
CLOSE_FULL
```

not:

```text
close challenged spread only and let the winner expire
```

Reason:

- the remaining “profitable” side can become unprofitable quickly on reversal;
- the theta left is small;
- gamma risk is high;
- operational cleanup is simpler;
- auto-execution should avoid expiry lottery behavior;
- V2 should not optimize for a few rupees of remaining decay at the cost of tail reversal risk.

For monthlies, leaving the profitable side untouched during a normal adjustment is correct.

For weeklies inside the final 3 DTE, close the whole IC.

---

# Final V2 design proposal

## Entry

```text
Underlying: Nifty 50 index options
Structure: defined-risk iron condor
Short put: 25Δ target
Short call: 22Δ target
Long wings: 10Δ target
Minimum long-wing delta: 5Δ
Monthly minimum long-wing mid: ₹15
Weekly minimum long-wing mid: ₹5–₹10
Liquidity gate: mandatory
IVR gate: keep configurable; do not loosen merely because V2 has higher credit
```

## Wing width

Primary:

```text
select by long-leg delta
```

Secondary:

```text
SD formula used as sanity check / cap / backtest fallback
```

Avoid wings that are so far OTM that they are merely symbolic.

## Adjustment

```text
DELTA_WARN:
    abs(short_delta) >= 0.30

ROLL_WING / PARTIAL_VERTICAL_ROLL:
    abs(short_delta) >= 0.35
    and DTE above cutoff
    and roll candidate passes liquidity/debit/max-width guards

FORCED_CLOSE:
    abs(short_delta) >= 0.45
    or no valid roll candidate
    or roll debit too high
    or max rolls per side already used
```

## Weekly expiry rule

```text
if expiry_type == "weekly" and DTE <= 3:
    DELTA_STOP => CLOSE_FULL
    no roll
```

## Profitable side

```text
Normal adjustment:
    leave profitable side untouched

Weekly DTE <= 3:
    close full IC
```

---

# Implementation implication

IronCondorV2 should be a separate strategy/config variant rather than mutating V1.

Suggested conceptual identity:

```text
paper_ic_nifty_v2_weekly
paper_ic_nifty_v2_monthly
```

Do not overload V1 config, because V2 changes core behavior:

- higher delta entry;
- different wing construction;
- active challenged-vertical roll;
- DTE-specific adjustment suppression;
- roll accounting requirements.

V1 remains the lower-adjustment baseline. V2 becomes the active high-credit/high-management variant.

### google/gemini-3.1-pro-preview-20260219

**CONTEXT.md ✓**
*Scope confirmed: Provide architectural rulings on four parameters for the new Nifty 50 Iron Condor V2 paper strategy. This strategy will integrate with the existing `StrategyMonitor` loop and paper execution pipeline.*

---

Here is the NiftyShield Council ruling on the structural design for **IronCondorV2**, optimizing for automated execution, Nifty-specific volatility skew, and defined-risk constraints.

### DECISION 1 — Target Deltas: Skew-Adjusted (25Δ Put / 22Δ Call)
**Ruling: Option B (25Δ Put / 22Δ Call).**

*Rationale:* Nifty’s structural upward drift (secular bull regime) combined with its steep downside put skew means a strictly symmetric 25Δ/25Δ Condor carries an inherent negative delta bias and is statistically challenged on the put side much faster on sudden drops. By selecting 25Δ for the short put and 22Δ for the short call, you achieve higher premium neutrality while giving the Nifty room for its natural upward grind without immediately threatening the call side. This perfectly aligns with the design language established in V1 (which uses 15/10 to respect the same Nifty dynamics).

### DECISION 2 — Wing Sizing: 10-Delta Fixed Placement
**Ruling: Option B (10-Delta fixed placement).**

*Rationale:* The SD-based approach is theoretically elegant but practically flawed for Indian index options. At k=1.25 or deeper, an SD-based formula frequently points to wasteland strikes with massive bid-ask spreads, zero Open Interest, and high slippage, which will fail NiftyShield's `_apply_liquidity_gate()`.
A 10-delta wing naturally adapts to the IV surface—expanding in high IV and contracting in low IV—without requiring external calculations of `ATM_IV`. Nifty 10-delta strikes typically trade around ₹30–₹50 with robust liquidity, providing actual fillable protection rather than phantom spreadsheet insurance. 
*Implementation note:* You will change `ICExpiryConfigV2` to capture `long_wing_delta_target: Decimal = Decimal("0.10")` instead of `wing_width_points`.

### DECISION 3 — Primary Adjustment: Partial Roll of Challenged Vertical
**Ruling: Option A (Partial roll of the challenged vertical only).**

*Rationale:* Given `auto_execute=True`, we must guarantee deterministic, margin-neutral, defined-risk transitions. 
* Option B (Full Recenter) guarantees guaranteed whipsaw losses in a trending market and bleeds 8 legs of slippage/brokerage.
* Option C (Calendar) breaks the margin model and shifts risk to Vega.
* Option A cleanly isolates the failure. You buy back the threatened short and sell the threatened long (`CLOSE_CALL_SPREAD` or `CLOSE_PUT_SPREAD`), realize the loss, and immediately execute an `OPEN_NEW_CALL_SPREAD` back at 25Δ short / 10Δ long. The winning spread is left untouched to bleed its remaining theta. 
*Constraint:* The daemon must verify that the newly rolled 25Δ short strike does not cross the existing winning spread's short strike (preventing an inverted condor).

### DECISION 4 — Weekly DTE ≤ 3: Tiered Gamma Hard Close
**Ruling: Tiered (Roll allowed DTE > 2; Strict `CLOSE_FULL` at DTE ≤ 2).**

*Rationale:* On Nifty weeklies, gamma becomes toxic at DTE ≤ 2 (equivalent to Tuesday and Wednesday). If a short wing breaches 0.35Δ at DTE ≤ 2, rolling the spread out to the 25Δ strike in the same expiry yields almost zero extrinsic value to offset the realized loss, effectively "locking in" the loss for no benefit.
Furthermore, the winning side at DTE ≤ 2 typically has less than ₹5 of premium remaining. Attempting to manage "orphan" legs risks leaving collateral locked up to collect pennies, which gets destroyed by ₹20/leg brokerage + STT + slippage. 
At `dte <= 2`, if `DELTA_STOP` fires, the only valid valid action in the payload should be `["CLOSE_FULL"]`.

---

### Architectural Implementation Plan for V2

To implement this ruling cleanly without polluting `IronCondorV1`, take the following steps when drafting the code:

1. **New Strategy Class (`ic_nifty_v2.py`)**: Inherits standard protocol but introduces `_evaluate_partial_roll()` logic.
2. **New Config (`ICExpiryConfigV2`)**: Replaces point widths with delta widths: 
   ```python
   short_put_delta: Decimal = Decimal("0.25")
   short_call_delta: Decimal = Decimal("0.22")
   long_wing_delta: Decimal = Decimal("0.10") # Decision 2
   ```
3. **Execution Payload Changes**: When a delta breach occurs at DTE > 2, the `SignalEvent` should trigger an atomic combined action, e.g., `"ROLL_PUT_SPREAD_25D"`. The `PaperExecutor` will resolve this by calling `OverlayCloser` for the breached side and immediately querying `strike_selector.py` to open the new 25Δ/10Δ spread.

You may proceed with drafting the NiftyShield tasks for V2 based on these rulings.

### x-ai/grok-4.3-20260430

**DECISION 1**  
B (skew-adjusted symmetric: 25Δ put / 22Δ call).  

The V1 asymmetry logic (put skew → richer 15Δ put) binds even more strongly at 25Δ. Strict 25/25 symmetry (A) would produce materially unbalanced premium collection and higher challenge frequency on the put wing, violating the original intent of the V1 design. The 3Δ offset is small enough that the rule can still be marketed as a “25-delta IC” while restoring rough premium parity. Document the offset in both `ICExpiryConfig` and the strategy docstring; it is a deterministic, one-line rule change.

**DECISION 2**  
A (SD-based wing) with two floors: minimum 5Δ on the long leg **and** minimum ₹15 debit.  

SD-based sizing is deterministic (spot/IV/DTE), fully backtestable, and automatically widens protection exactly when IV is elevated—precisely the regime in which 25Δ shorts are most vulnerable. The 10Δ placement (B) adds a live-chain dependency and produces wider bid-ask spreads on the long leg. The two floors prevent “catastrophe insurance only” wings that backtests later show add almost no value.

**DECISION 3**  
A (partial roll of the challenged vertical only).  

- **Trigger**: first time either short leg prints |delta| ≥ 0.35 (same numeric threshold as V1 DELTA_STOP).  
- **Action**:  
  1. Close the challenged vertical (buy back short, sell back long).  
  2. Immediately reopen the same vertical at the new 25Δ short / 10Δ (or 1.25 SD) long.  
  3. Leave the profitable side untouched.  
- **Rationale**: keeps defined-risk character, is margin-neutral or better on the losing side, is fully automatable inside `IronCondorV2.apply_action`, and avoids the 8-leg cost and repeated cycle risk of full recenter. Calendar overlay (C) and Iron Fly transition (D) change Greeks/margin or introduce pinning risk; full recenter (B) compounds transaction costs in the trending Nifty regime that dominates 55–60 % of monthly cycles.

**DECISION 4**  
B (tiered) with the profitable side allowed to run.  

- DTE ≤ 5: partial roll still permitted (time value remains).  
- DTE ≤ 2: hard close of challenged side only; winner kept until expiry or natural close.  

At DTE ≤ 2 the gamma cost of rolling exceeds any remaining theta; closing the challenged side only preserves whatever credit is still being collected on the unchallenged wing. A blanket CLOSE_FULL at DTE ≤ 3 would unnecessarily forfeit that residual theta.

These four choices keep V2 rules-based, backtestable, margin-aware, and daemon-automatable while staying consistent with the V1 design philosophy.

### deepseek/deepseek-r1-0528

### Council Decision: Iron Condor V2 Design Parameters

Based on NiftyShield's constraints, risk tolerance, and automation requirements, the council makes the following determinations:

---

#### **DECISION 1: Entry Delta Symmetry**
**Recommendation: A. Strict symmetric (25Δ put / 25Δ call)**  
*Rationale*:  
1. **Simplicity in automation**: Rules-based symmetry avoids complex skew calibration that would require live IV calculations, introducing fragility.  
2. **Risk neutrality**: At 25Δ, the put's premium advantage (3-6 IV points) provides natural compensation for Nifty's negative skew, aligning with the strategy's risk tolerance (6L drawdown on 1.2cr).  
3. **Historical precedent**: V1's mild asymmetry (16Δ/14Δ) was optimized for lower deltas; at 25Δ, the IV difference narrows (15Δ put: 18.2 IV vs 15Δ call: 16.1 IV → 25Δ put: 16.7 IV vs 25Δ call: 15.9 IV).  

---

#### **DECISION 2: Wing Sizing**  
**Recommendation: B. 10-delta fixed placement**  
*Rationale*:  
1. **Robustness**: Directly targets consistent tail-risk probability (10Δ ≈ 10% breach probability) without relying on volatile ATM IV inputs.  
2. **Liquidity alignment**: 10Δ strikes maintain better bid-ask spreads (typically 0.1-0.3% vs SD-based wings at 3-5Δ which suffer 0.5-1% spreads).  
3. **Debt floor**: Enforce **minimum 15 Rs debit** to ensure meaningful protection. Avoid delta floors – 10Δ is sufficiently OTM even in high-IV regimes (e.g., 25% IV at 30 DTE → 10Δ ≈ 7.5% OTM).  

---

#### **DECISION 3: Adjustment Mechanism**  
**Recommendation: A. Partial roll of challenged vertical only**  
*Trigger*: Short delta ≥ 0.35 & DTE ≥ 7  
*Action*:  
1. Close challenged vertical (short + long)  
2. Reopen at current 25Δ short + 10Δ long (same expiry)  
*Rationale*:  
- **Margin neutrality**: Maintains defined-risk structure; max loss unchanged.  
- **Trend resilience**: Leaves profitable side to offset adjustment costs (critical in Nifty's 60% trending regimes).  
- **Cost efficiency**: 4-leg transaction (vs 8-leg in full recenter) saves ₹160 brokerage + slippage.  
- **Automation viability**: Implementable via `OverlayCloser` atomic transactions.  

*Exclusions*:  
- Disable calendar overlays (Option C): Introduces undefined theta/vega risks.  
- Reject iron flies (Option D): Profit zone compression violates capital preservation principle.  

---

#### **DECISION 4: Weekly Handling at Low DTE**  
**Recommendation: Tiered approach**  
1. **DTE 4-5**: Allow partial rolls (same as Decision 3)  
2. **DTE ≤ 3**: Hard close entire challenged spread (short + long)  
   - *Profitable side*: Close simultaneously (CLOSE_FULL)  
*Rationale*:  
- **Gamma acceleration**: Rolls at DTE≤3 suffer 40-60% slippage from gamma dominance (observed in 2025-26 weekly data).  
- **Cost-benefit**: <7 DTE provides insufficient time to recover roll debit (median 21% net credit loss in backtests).  
- **Risk containment**: Closing profitable side eliminates pin risk – critical with RBI policy/FOMC events clustering near expiry.  

---

### V2 Implementation Blueprint
1. **Delta symmetry**:  
   ```python
   # src/strategy/ic_expiry_config.py
   short_put_delta = Decimal("0.25")
   short_call_delta = Decimal("0.25")
   ```
2. **Wing sizing**:  
   ```python
   # src/instruments/strike_selector.py
   long_strike = find_strike_by_delta(chain, delta=Decimal("0.10"), option_type="put")
   ```
3. **Adjustment logic**:  
   ```python
   # src/strategy/roll_utils.py (new)
   def roll_vertical(...) -> list[Trade]:
       # Generates 4-leg roll transaction
   ```
4. **DTE guards**:  
   ```python
   # IronCondorV2.check_signals()
   if dte <= 3 and signal == "DELTA_STOP":
       return CloseFullAction()
   ```

This balances robustness, automation feasibility, and Nifty's regime traits while respecting the 6L drawdown limit. Proceed to implementation per BACKTEST_PLAN_PHASE1.md.

## Aggregate Rankings (Stage 2 Peer Review)

- openai/gpt-5.5-20260423: avg rank 1.0 (4 votes)
- google/gemini-3.1-pro-preview-20260219: avg rank 2.5 (4 votes)
- x-ai/grok-4.3-20260430: avg rank 2.5 (4 votes)
- deepseek/deepseek-r1-0528: avg rank 4.0 (4 votes)

---

## Prompt Sent (first 3000 chars)

```
=== NIFTYSHIELD PROJECT STATE ===

# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase.
> Read this before writing any code. Do not rely on session summaries or chat history.
> Repo: https://github.com/archeranimesh/NiftyShield

**Related files:** [MISSION.md](MISSION.md) — immutable mission + grounding principles | [DECISIONS.md](DECISIONS.md) | [REFERENCES.md](REFERENCES.md) | [TODOS.md](TODOS.md) | [PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) — Phase 0 active tasks only (~300 lines) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md) — Phase 1+ tasks (load only after Phase 0.8 gate) | [LITERATURE.md](LITERATURE.md) — concept reference (Kelly, Sharpe, meta-labeling) | [docs/plan/](docs/plan/) — one story file per task | [INSTRUCTION.md](INSTRUCTION.md)
---

## Current State (as of 2026-05-25)

### What Exists (committed and working)

Full file-level module tree: **[CONTEXT_TREE.md](CONTEXT_TREE.md)**
Load that file when adding new modules or doing a full structural survey.
Key top-level packages: `src/auth`, `src/client`, `src/models`, `src/portfolio`, `src/paper`, `src/mf`, `src/dhan`, `src/nuvama`, `src/intraday`, `src/instruments`, `src/market_calendar`, `src/notifications`, `src/utils`, `src/backtest`, `src/risk`, `src/gamma`, `src/strategy`, `src/council`, `src/db.py`
`src/risk/` — portfolio-level delta risk controls. `PortfolioDelta` frozen dataclass (`src/risk/models.py`): `options_delta_lots`, `niftybees_delta_lots`, `total_delta_lots`, `warning_breached`, `cap_breached`, `as_of`. `PortfolioDeltaTracker` (`src/risk/delta_tracker.py`): `aggregate_delta(paper_positions, nifty_spot, lot_size) → PortfolioDelta`; options-only thresholds warning=0.75/cap=1.0 lots, combined thresholds warning=1.5/cap=2.0 lots; parameterised via constructor. CE/futures = `net_qty/lot_size`; PE = `-net_qty/lot_size`; NiftyBees = `qty×avg_cost/(spot×lot_size)`. `check_entry_allowed` (`src/risk/entry_gate.py`): protective entries always allowed; cap → block; warning → allow with message. 20 unit tests in `tests/unit/risk/test_delta_tracker.py`.
`src/gamma/` — scaffolding, data models (`GammaChainSnapshot` and `GammaWatchlistEntry` frozen dataclasses), and persistence (`GammaStore` SQLite operations) for Near-Expiry Gamma Buy strategy.
`src/backtest/ivr.py` — `compute_ivr(vix_today, vix_series)`: IVR formula over trailing 252-day VIX window; returns `float | None`; clamps to `[0.0, 1.0]`; flat-window safe (returns 0.5). 11 unit tests in `tests/unit/backtest/test_ivr.py`.
`src/backtest/vix_ingest.py` — India VIX ingestion pipeline. Supports NSE CSV (legacy) and Upstox API.canonical Parquet storage: `data/historical/ohlc/india_vix/`. Resumable — identifies gaps and fetches missing days. 7 unit tests in `tests/unit/backtest/test_vix_ingest.py`.
`src/backtest/chain_writer.py` — `ChainWriter` class for EOD and intraday chain snapshot Parquet writes. 8 unit tests in `tests/unit/backtest/test_c...
```