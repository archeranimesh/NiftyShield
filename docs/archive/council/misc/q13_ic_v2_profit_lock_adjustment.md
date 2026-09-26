# IC V2 Profit-Lock Adjustment Design

## System Context

NiftyShield runs `IronCondorV2` (paper strategy, auto_execute=True) on Nifty 50 monthly
options. Entry: 25Δ put / 22Δ call short legs, 10Δ long wings (≥5Δ floor, ≥₹15 mid-price
floor). DTE at entry: 30–45. Lot size: 75. Profit target: 70% credit decay captured
(combined mark ≤ 30% of entry credit → CLOSE_FULL). Defensive roll (D3 ruling): if
|short_delta| ≥ 0.35, attempt 4-leg atomic partial roll of challenged vertical only;
max 1 roll per side per cycle; roll debit ≤ 50% of original IC credit.

**The gap this question addresses:**

Once decay is captured (position is ahead), the 10Δ long wings have also decayed
significantly and provide little residual protection. If the market reverses sharply
after 50% decay, the original max-loss is again the relevant risk — the position has
no mechanism to protect accumulated gain. The user wants a *structural* profit-lock:
a strike-level restructuring that makes it mathematically impossible (or very hard) to
lose the locked gain, without exiting the position.

**Three profit zones (trigger thresholds):**

| Zone | Trigger | Lock goal |
|------|---------|-----------|
| Zone 1 | 25% of entry credit captured | Acknowledge profit; optional light restructure |
| Zone 2 | 50% of entry credit captured | Hard lock: ensure ≤25% credit can be lost from here |
| Zone 3 | 75% of entry credit captured | Tight lock: ensure ≤10% credit can be lost from here |

**Critical constraint on Zone 2 → 3 transition:**
Once Zone 2 is crossed (50% captured), the position must NEVER fall back below Zone 1
(25% captured) under any subsequent market move. This must be enforced structurally
(via strike placement / spread width), not merely via a trailing delta stop.

---

## Q1 — Mathematical Framework for Profit Locking

The question is whether option Greeks and market structure provide a sufficient mathematical
basis to guarantee profit floors without exit.

**Candidate approaches — please evaluate each rigorously:**

**A. Spread-width contraction (roll long wings inward):**
At Zone 2 (50% captured), buy back existing 10Δ long wings (now nearly worthless;
mark ≈ ₹5–15) and sell new long wings at ~18–20Δ. This narrows each spread from
~(short_strike - long_strike) to a tighter range. Max loss from the restructured
position is now: (new_spread_width × lot_size) - remaining_credit - premium_collected
on new longs. Can the math be shown to guarantee the 25% floor?

Derive the condition:
```
new_spread_width ≤ (current_mark - 0.25 × entry_credit) / lot_size
```
Is this always satisfiable given typical Nifty chain liquidity at 18–20Δ?

**B. Short-leg inward roll (recenter the shorts, not the longs):**
At Zone 2, buy back both short legs (now 0.30–0.40Δ due to market drift or time)
and resell at current 20Δ/18Δ — farther OTM than current short but closer to ATM
than original entry. Net: fresh credit collected, delta reset, but new shorts are
closer to ATM so gamma risk is higher near expiry.

Mathematical question: at what DTE and IV level does the freshly-collected credit
from the inward roll reliably lock ≥25% of original credit even if market moves 1SD?
Derive using: `credit_buffer = new_credit_collected - max_intrinsic_loss_at_1SD_move`.

**C. Delta-neutral hedge (add a long straddle or long futures position):**
At Zone 2, add a long futures or synthetic delta hedge to neutralise position delta.
This does not change spread max-loss but reduces path-dependency of the reversal.
Evaluate whether this is tractable for an auto-execute daemon without live hedging
infrastructure (position sizing, margin, continuous rebalancing).

**D. IV-regime-conditional roll (only restructure if VIX conditions support it):**
Profit-lock rolls are expensive (transaction cost, slippage) if done in low-IV
environments where premium on replacement longs is thin. Propose: restructure only
when India VIX ≥ X and IVR ≥ Y, otherwise accept the trailing delta-stop as the
sole protection. Derive X and Y thresholds for Nifty.

**E. Gamma-based timing (restructure at the inflection where gamma accelerates):**
Gamma peaks at ATM and accelerates as DTE → 0. At typical monthly DTE (15–20 days
remaining when 50% decay is captured), gamma on the short legs is entering the steep
part of the curve. Evaluate: is there a DTE × delta × IV surface threshold where
restructuring is mathematically optimal (i.e., cost of restructure < expected loss
from gamma exposure in the next 5 sessions)?

---

## Q2 — Structural Guarantee Math

For Option A (spread-width contraction), provide the explicit formula showing:

Given:
- `entry_credit` = total IC credit at entry (₹ per lot)
- `current_mark` = current combined mark (cost to close all 4 legs)
- `captured` = entry_credit - current_mark
- `new_spread_width_pts` = width of restructured spread (in Nifty index points)
- `lot_size` = 75
- `restructure_debit` = net cost to roll the long wings inward

Condition for guaranteeing ≥25% profit floor:
```
(new_spread_width_pts × lot_size) + restructure_debit ≤ (entry_credit - 0.25 × entry_credit)
```

Is this formula correct? What term is missing (slippage, theta decay between restructure
and expiry, etc.)? Derive the complete version.

For the Zone 2 → Zone 3 transition (once 50% captured, never fall below 25%):
What spread width does the restructured IC need at Zone 2 so that even a 2SD adverse
move on Nifty cannot breach the 25% floor? Assume:
- Nifty spot: 24,500
- ATM IV: 13%
- DTE at restructure: 18
- Entry credit: ₹200 per lot (₹15,000 total)
- 2SD daily move: spot × IV × sqrt(DTE/365)

Solve numerically and state whether the resulting spread width is achievable with
liquid Nifty strikes (multiples of 50 pts, OI > 50k contracts).

---

## Q3 — Interaction with Existing D3 Defensive Roll

The D3 ruling (max 1 defensive roll per side per cycle, triggered at |delta| ≥ 0.35)
must co-exist with the profit-lock restructure. Potential conflicts:

1. A profit-lock roll at Zone 2 changes the spread structure — how does D3's
   "original_spread_width" reference point update after a profit-lock roll?
2. If a profit-lock roll has already been executed, does it consume the D3 roll
   budget for that side?
3. What is the priority when both fire simultaneously (|delta| ≥ 0.35 AND 50%
   captured on the same tick)?

Propose an interaction model with explicit precedence rules.

---

## Q4 — Automation Feasibility

`IronCondorV2` is `auto_execute=True`. Profit-lock rolls must be automatable:

1. Can the trigger (25%/50%/75% thresholds) be computed purely from data already
   in `check_signals(market, positions)` — i.e., `current_mark` and `entry_credit`?
   Both are available from `PaperStore`. No additional API call required?

2. The 4-leg atomic restructure (close old longs, open new longs at different strikes)
   uses `OverlayCloser`-style atomic execution. Is the same `PositionUpdate` + single
   DB transaction pattern sufficient, or does profit-lock require a new transaction type?

3. State tracking: the strategy must know which zone it's in and not re-fire a
   profit-lock roll it's already executed. Propose the minimal state fields needed
   (e.g., `profit_lock_zone: int`, `profit_lock_executed: set[int]`).

---

## Q5 — Model Recommendation

Given the above analysis, which combination of approaches (A–E) do you recommend for
each of the three zones? Specifically:

| Zone | Trigger | Recommended approach | Guard conditions |
|------|---------|---------------------|-----------------|
| Zone 1 (25% captured) | | | |
| Zone 2 (50% captured) | | | |
| Zone 3 (75% captured) | | | |

Include: the exact trigger condition (formula), the leg actions, any DTE / IV /
debit-cap guards, and how the 25% floor guarantee is maintained mathematically
across the Zone 2 → Zone 3 transition.

---

## Required Council Output Format

```
## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Zone 1 approach | |
| Zone 2 approach | |
| Zone 3 approach | |
| Zone 2→3 floor guarantee mechanism | |
| D3 interaction model | |
| State fields required | |

## Mathematical Derivation
[Complete formula for spread-width constraint at Zone 2 with numerical example]

## Guard Conditions
[DTE cutoff below which profit-lock is skipped, IV conditions, debit cap]

## Dissenting Notes
[Panel disagreements, particularly on Option C (delta hedge) tractability]
```

Council members must show their working for Q2 (the numerical derivation). A
qualitative answer to Q2 is insufficient.
