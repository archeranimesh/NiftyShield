NiftyShield already has IronCondorV1 running on Nifty 50 monthly options (strategy class: `src/strategy/ic_nifty_v1.py`, config: `src/strategy/ic_expiry_config.py`). The prior council (2026-05-02, `iron-condor-v1-core-design.md`) set V1 at mild asymmetry: short put 16Δ / short call 14Δ, fixed wing widths (200pt weekly, 500pt monthly), and adjustment-free design (ROLL_WING only — roll threatened short farther OTM, no spread close).

IronCondorV2 is a new variant with three structural departures from V1: (1) higher delta entry at 25Δ both sides, (2) SD-computed wing widths instead of fixed points, (3) active adjustment via partial roll of the challenged vertical. This question asks the council to settle four design decisions before the V2 spec is written and implementation begins.

---

**DECISION 1 — Entry delta symmetry at 25Δ**

The prior council rejected symmetric deltas at 15Δ because Nifty's put skew means the 15Δ put carries 3–6 IV points more than the 15Δ call, making symmetric delta asymmetric in premium and risk. At 25Δ, this skew effect intensifies — the 25Δ put is structurally richer, closer to ATM, and historically challenged more frequently than the 25Δ call (Nifty drops sharper than it rallies). Two approaches:

A. Strict symmetric: 25Δ put / 25Δ call — clean, rules-based, delta-neutral at entry by construction. Accept that the put side carries higher premium and higher challenge frequency.

B. Skew-adjusted symmetric: 25Δ put / 22Δ call — collect equivalent premium on both sides rather than equivalent delta, partial correction for skew. Complicates the rule ("25-delta IC" is no longer exactly that).

Which is appropriate for V2 at 25Δ, and does the council's prior asymmetry reasoning from V1 bind here or does the higher delta change the calculus?

---

**DECISION 2 — Wing sizing: SD-based vs 10-delta placement**

V1 uses fixed point widths (200pt weekly, 500pt monthly). Two principled alternatives:

A. SD-based formula: `wing_width = spot × ATM_IV × √(DTE/365) × k`, where k is a configurable multiplier (1.0 to 1.5). Wing rounds to nearest 50pt. At entry: Nifty 25000, IV 15%, 30 DTE → 1 SD ≈ 1075pt; k=1.25 → wing ≈ 1350pt. At 7 DTE → 1 SD ≈ 519pt; k=1.25 → wing ≈ 650pt. Wings adapt automatically to IV regime and DTE — wider when IV is high (more protection when needed), narrower when IV is low (more credit). The long strike at 1.25 SD is approximately 3–5 delta.

B. 10-delta fixed placement: long wing placed at whichever strike has 10Δ absolute delta at entry time. Also adapts to IV (10Δ moves farther in high IV), simpler to express in natural options terms, directly comparable across strategies.

Both approaches place the long at roughly 3–10 delta depending on IV and DTE. Key differences: SD-based is deterministic given spot/IV/DTE; 10Δ requires live chain lookup. SD-based debit will be very low (5–15 Rs) in most cases — the wing is catastrophic-insurance not real protection; 10Δ placement is slightly closer and debit is 30–60 Rs with better bid-ask proportional spread. Which approach is more robust and backtestable for a 25Δ IC on Nifty weekly and monthly? Should debit floor (minimum 15 Rs) or delta floor (minimum 5Δ) be enforced to ensure the wing provides real protection?

---

**DECISION 3 — Primary adjustment mechanism when short delta ≥ 0.35**

When either short leg reaches 0.35 delta (the V1 DELTA_STOP trigger), V2 needs an active adjustment rather than spread close. Four candidates from the literature and our design discussion:

A. Partial roll of challenged vertical only: close the challenged spread (buy back short, sell back long), reopen with new short at 25Δ and new long at 10Δ or 1.25 SD from new short. Leave the profitable side completely untouched — it continues collecting theta. Net debit on the roll (losing side's loss > winning side's gain). Works best on monthlies with DTE ≥ 14.

B. Full recenter: close all 4 legs, reopen IC centered at current spot at 25Δ/25Δ. Clean restart but 8-leg transaction cost, always a net debit, and in trending markets triggers repeated cycles compounding losses.

C. Calendar overlay: replace the challenged long wing with a next-month long at same strike. Exploits differential theta decay between weekly short and monthly long. Changes structure from standard IC to diagonal — different Greek profile, margin treatment differs at broker level.

D. Iron Fly transition at 3 PM: if short delta ≥ 0.35 at 3 PM, close profitable put spread and sell a new ATM put to create Iron Fly. Reduces max loss but narrows profit zone to near-zero, requires pinning to profit. Time-triggered (3 PM) rather than delta-triggered — no statistical basis for the time choice.

For NiftyShield's automated context (StrategyMonitor loop, auto_execute=True), which mechanism: (a) is most margin-neutral (no increase in max loss), (b) is implementable without manual intervention in the daemon, (c) performs best in the trending Nifty regime that characterizes 55–60% of monthly cycles, and (d) does not create naked exposure or change the defined-risk character of the structure? Specify trigger delta, action steps, and what happens to the profitable side.

---

**DECISION 4 — Weekly-specific rules at DTE ≤ 3**

Gamma acceleration in the last 3 DTE on Nifty weekly makes adjustment at that point extremely expensive — the challenged short is approaching 0.5 delta rapidly and any roll opens a new position with almost no time value remaining. Two options:

A. Hard close: at DTE ≤ 3, any DELTA_STOP fires a CLOSE_FULL rather than adjustment. Accept the loss on the challenged spread, close the profitable side for whatever theta remains, no roll.

B. Tiered: at DTE ≤ 5, partial roll is still viable (enough time value exists on the new short to justify transaction cost). At DTE ≤ 2, hard close only.

Should the DTE cutoff for disabling adjustment be 3 or some other threshold, and should the profitable side be closed simultaneously (CLOSE_FULL) or allowed to run to expiry (close challenged side only, hold winner)?
