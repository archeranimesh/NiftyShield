# Council Decision: nifty-long-instrument-comparison-protection

Date: 2026-05-02  
Chairman: openai/gpt-4.1-2025-04-14  
Council members: openai/gpt-4.1-2025-04-14, google/gemini-3.1-pro-preview-20260219, x-ai/grok-4-07-09, deepseek/deepseek-r1-0528

---

## Stage 3 — Chairman Synthesis

## NiftyShield Council Synthesis: Structured 3-Track Nifty Options Paper-Trade Framework

**Context:**  
You are designing a rigorous options paper-trading and backtest matrix comparing three distinct methods of long Nifty exposure (physical ETF, futures, and options-based proxy). Overlays like protective puts, covered calls, CSPs (cash-secured puts), and additional defined-risk structures should be tested on all three bases. All design and reporting choices must align with NiftyShield’s Mission Principles (esp. capital protection, avoidance of undefined downside, clear risk attribution, and apples-to-apples capital efficiency metrics).

Below is the comprehensive, consensus-guided answer, integrating the best ideas and cautions from all council responses and peer reviews.

---

## 1. **Track C: Best Structure for “Long Nifty via Option”**

**Recommendation:**  
**Use a single-leg Deep ITM Call (delta ≈ 0.90, strike ~2000–2500 below spot, monthly expiry) as the base position for Track C.**

### **Council Reasoning & Key Points:**

- **Avoid Synthetic Longs** (ATM call + ATM put):  
  - **Critical issue:** Adding a CSP (short 25-delta put) overlay to a synthetic long doubles the short put risk (ATM + CSP strikes). This violates risk segregation and expands your downside convexity, possibly breaching your max drawdown tolerance.
  - **Margin/cashflows:** While margin efficiency is high, it’s not “clean” for overlay comparisons, and accounting becomes ambiguous.

- **Deep ITM Call Advantages:**  
  - **Delta fidelity:** Roughly tracks Nifty with lower gamma slippage than a near-ATM call and less cost-of-carry.
  - **Defined risk:** Maximum loss = premium paid, never undefined.
  - **Overlay compatibility:** Overlays (CSP, covered call, protective put) sit “on top” of the position without unintended replication or overlap.
  - **Carry cost:** Theta is present but much lower than for near-ATM options; extrinsic value is minimal.
  - **Practicality:** Liquidity sufficient for a 1-lot strategy; slippage manageable with disciplined order routing.

- **Near-ATM ITM Calls:**  
  - Disadvantageous due to higher theta, lower delta, and increased exposure to vega/gamma swings—not a consistent “long Nifty” proxy for comparative research.

**Operational advice:** Each roll, select the lowest-strike call with delta ≈ 0.90, verify OI and spreads, and roll monthly at expiry. Treat the option premium paid as “capital at risk” for reporting normalization.

---

## 2. **Overlay Interaction Matrix: Risks, Redundancies, and Greeks**

Below is a clear summary matrix, followed by core conclusions:

| **Base \ Overlay**      | **Protective Put** | **Covered Call**             | **CSP (Short Put, ~25Δ)**      |
|-------------------------|--------------------|-----------------------------|-------------------------------|
| **A: NiftyBees ETF**    | Textbook, safe     | Textbook, safe              | Increases downside, treat with caution (double long ETF if assigned) |
| **B: Nifty Futures**    | **Redundant:** This combo is equivalent to a long call | **Dangerous:** Futures + covered call = synthetic short put (unlimited downside) | **Dangerous:** Futures + CSP = double short put (high tail risk) |
| **C: Deep ITM Call**    | **Redundant:** Just use/roll a call spread | **Vertical/Diagonal spread:** Capped upside, defined risk | Safe, but ensure not double-counting synthetic short puts |

**Council Synthesis and Red Flags:**
- **Synthetic Structures:**  
  - Many overlays + base combos are functionally equivalent to basic spreads or synthetics (e.g., futures + PP = long call), which can be entered more cost-effectively as a spread. For research validity, avoid accidentally redundant exposures.
- **Double Short-Put Exposure:**  
  - *Track B: Futures + CSP or covered call*—both create a double short-put risk (either overtly with CSP or synthetically via covered call). This is capital-destructive in drawdowns and violates capital protection mandates.
- **Track C + Overlays:**  
  - Deep ITM calls + additional overlays remain low-risk and clean as long as you avoid constructing synthetic short puts via over-complex overlays.
- **Recommendation:**  
  - Programmatic overlays/portfolio construction should contain explicit “dangerous structure” detection logic: if the net Greeks or position equivalents create unintentional risk (e.g., total short-puts position > intended), warn or block the configuration.

---

## 3. **Additional Protection Structures (Beyond Put, Call, CSP)**

**Council-Approved Advanced Overlays (for backtesting only):**

### a) **Collars (Protective Put + Covered Call)**
- **Why?** Collars utilize the index put/call skew: OTM puts are more expensive than equidistant OTM calls, but selling the call can offset much/all of the put’s cost.  
- **Payoff:** Limited upside, protected downside; significantly cheaper than buying a put outright.
- **Implementation:** Buy OTM put (e.g., 8–10% below spot), sell OTM call (e.g., 3–5% above spot), both with same expiry.
- **Operational fit:** Collars are capital-efficient, align with protection-first philosophy, and are “quiet” in churn and risk.

### b) **Put Spread (Vertical or Backspread)**
- **Why?** A vertical put spread (buy higher-strike put, sell lower-strike put) caps both max loss and max gain versus a “naked” protective put.
- **Payoff:** Cheaper than pure protective put, gives moderate crash coverage at lower carry cost; best for those willing to accept reduced insurance for reduced theta drag.

### c) **Others:**
- **Ratio Spreads & Backspreads:**  
  - **REJECTED** as core overlays. While ratio spreads can be zero-cost, Nifty’s negative skew means the second short put can create catastrophic tail risk, directly violating NiftyShield’s “protect before you earn” rule. Only to be modeled as an academic tail-risk experiment.
- **Jade Lizards, Iron Condors, Strangles:**  
  - **REJECTED** for this risk framework. These either introduce undefined downside or are capital-inefficient for the test size and Nifty’s bid/ask structure.

---

## 4. **Daily P&L Reporting Design**

**Key Principles:**
- Must allow granular attribution (base vs. overlay) and cross-strategy, cross-track comparability—without introducing risk illusion via leverage or margin accounting tricks.
- Must report actionable risk measures (portfolio Greeks) to surface hidden convexity or theta drag.

### a) **Base and Overlay Reporting:**  
- **MANDATORY**: Report both *separately* and *in combination*.
    - e.g., “Track A: NiftyBees P&L -₹8,500, Put Overlay +₹12,000, CSP overlay +₹500, Net +₹4,000.”
    - This enables true attribution: Did the overlay hedge a loss, or was it a drag?
    - Combined P&L is required for final equity curve assessment.

### b) **Cross-Track Comparison & Capital Normalization:**
- **Standardization Method:** Use **Notional Equivalent Exposure (NEE)** for all tracks—e.g., set all tracks to 1 Nifty lot equivalent (~₹15.5–16L at current spot).
    - For Track A (ETF): Use cash deployed.
    - For Track B (Futures): Use the notional value (not just the margin); also track “surplus” capital allocated to liquid funds for apples-to-apples assessment.
    - For Track C (Deep ITM Call): Cash paid in option premium + required margin (if any) for overlays.
- **Metrics:**  
    - Absolute and percent P&L.
    - Run and max drawdown, both in absolutes and as percent of NEE.
    - Return on Notional (RoN).
    - Tracking error (delta drift) between tracks over time.
    - Overlay cost quantification (cumulative premium paid/received).

### c) **Daily Greeks to Report:**
- **Delta:** (Net, per track) – reveals directional equivalence, highlights drift (e.g., is Track C falling to 0.7 delta as expiry nears?)
- **Theta:** (Net, per track) – reveals how much “burn” overlays cost per day—important to quantify true cost of protection/income overlays.
- **Vega:** (Net, per track) – surfaces sensitivity to IV moves (especially relevant to options-based tracks and overlays).
- **Gamma:** (Optional, per peer synthesis, but advisable for options-heavy overlays)—useful for tail event risk but less critical for monthly cycle reporting unless convexity risk rises sharply.
- **Other:** Rolling realized volatility (20dd/60dd) per track for risk insight.

**Example Daily Table:**

| Date   | Track | Base P&L | Overlays (Put/Call/CSP) P&L(s) | Net P&L | Delta | Theta | Vega | Max DD % | Return on Notional % |
|--------|-------|----------|------------------------|---------|-------|-------|------|---------|----------------------|
| ...    | A     | ...      | ...                    | ...     | ...   | ...   | ...  | ...     | ...                  |

---

## 5. **Implementation and Operational Controls**

- **Paper trading infrastructure:** Implement as distinct tracked namespaces per track/overlay within your codebase (e.g., paper_track_a, paper_track_b, paper_track_c in your snapshot/trade recording scripts).
- **Guardrails:**  
    - Automatically block or flag any configuration that creates double short puts, uncovered short puts, or other mission-violating exposures.
    - Auto-convert redundant overlays (e.g., futures + protective put → long call) for simplified reporting.
    - Max loss circuit-breaker per track (e.g., preset at −2% of notional per day) to model realistic risk controls.

---

## 6. **Summary Table**
**Optimal Framework:**

| Track         | Base Position   | Capital Basis        | Overlay Compat.         | Main Caution                          | Best-Use Overlays             |
|---------------|----------------|---------------------|------------------------|---------------------------------------|-------------------------------|
| Track A       | NiftyBees ETF  | ₹15.5L (1 lot equiv.)| Fully compatible       | CSP overlay increases tail risk (if assigned, own 2x ETF) | Protective Put, Covered Call, Collar|
| Track B       | Nifty Futures  | Notional (₹15.5L), Margin ~₹1.5L| Avoid Covered Call, CSP overlay | Both can introduce hidden/unlimited short put risk; only use with explicit paired hedges | Protective Put (becomes long call), Collar|
| Track C       | Deep ITM Call  | Premium Paid (~₹2.0–3.0L)| Fully compatible       | None if overlays managed per above    | Put Spread, Collar, Covered Call, CSP (w/ tracking)|

---

## **Closing Guidance:**  
This framework enables a robust, transparent apples-to-apples, risk-matched comparison of Nifty exposure plus overlays—honoring NiftyShield’s mission of capital protection, empirical validation before deployment, and systematic risk measurement. By separating and normalizing P&L, strictly enforcing defined-risk overlays, and tracking actionable Greeks daily, you ensure research output that is both meaningful and operationally resilient.

Should you desire, the council recommends implementing all reporting as modular scripts referencing your `PaperTracker` structures, with overlays and base tracked as independent but aggregable instrument legs, and per-day metrics exportable for time-series/statistical analysis.

**Council consensus: This combined design maximizes research clarity, respects operational safety, and allows for sound extension to live trading after full Phase 0–1 validation.**

---

## Stage 1 — Individual Responses

### openai/gpt-4.1-2025-04-14

CONTEXT.md ✓ & all required context files reviewed.

## OVERVIEW

You're building a **3-track, multi-overlay options backtest and paper-trading comparison platform** for Nifty long exposure:

- **Track A:** Physical NiftyBees ETF holding (1 lot equivalent, ₹15.5L, pledgeable)
- **Track B:** Long Nifty Futures (1 lot, rolled)
- **Track C:** Long Nifty via ITM option (structure options: deep ITM call, synthetic future, or near-ATM ITM call)

On each, you want to test overlays: protective puts, covered calls, CSP (short 25-delta puts), and others (collars, ratio spreads, etc.).

Below, I answer each question in detail, including rationale, risk diagram notes, and recommendations for paper/live phases.

---

## (1) **ITM OPTION STRUCTURE FOR TRACK C**

### **Summary Table of Options**

| Structure       | Delta | Margin | Cost of Carry | Theta Drag | CSP Overlap Risk | Realism | Comments |
|-----------------|-------|--------|--------------|------------|------------------|---------|----------|
| Deep ITM Call   | 0.90+ | Margin: Option premium | Pays all upfront, no roll | Moderate, esp as expiry nears | No short put | High | Closest to “synthetic stock”; pays theta but avoids short put risk. |
| Synthetic Long  | ~1.0  | Margin: Futures-like | Near 0 premium, daily mark-to-market | None | **Short put** | Highest | True future: ATM call buy + ATM put sell at same strike. Overlaps CSP if also short put at lower strike. |
| Near-ATM ITM Call | 0.70 | Margin: Option premium | Lower upfront, more slippage | High | No short put | Medium | More reactive to vega/theta moves. Less meaningful for "stock-like" behavior. |

---

### **Detailed Analysis**

#### **a) Deep ITM Call (Single Leg, delta ~0.90, 2000-2500 points ITM)**

- **Delta ~0.90:** Closest proxy to a long future or spot holding, but not perfect — will slightly underperform in sharp rallies due to <1.0 delta.
- **Theta Decay:** You pay theta. The deeper ITM, the less theta per day, especially if option retains substantial extrinsic value, but you do not escape entirely.
- **Vega:** Very low. Deep ITM options are less sensitive to IV swings.
- **Margin:** You pay full premium upfront — say, ₹2–3L.
- **Roll:** Only at expiry. If expiry is monthly, you must roll each month; can use quarterly contracts to reduce churn.
- **CSP Conflicts:** **None** — you have no embedded short put, so layering a CSP overlay won’t create double short puts at different strikes.
- **Slippage:** Deep ITM options on Nifty have wider spreads but usually enough OI to fill one lot. May require patience.
- **Other:** The downside is limited to the option premium paid (max loss = premium); upside is linear from strike + premium upward, until expiry.

#### **b) Synthetic Long (ATM Call Buy + ATM Put Sell, same expiry & strike)**

- **Delta ~1.0:** Perfect future proxy — replicates P&L of spot Nifty/futures exactly (before cost).
- **Margin:** Like a future — combined margin required (generally similar to Nifty future margin on Upstox/NSE).
- **Net Premium:** ~zero (call-ATM and put-ATM premiums offset).
- **Theta:** Net theta ≈ 0; the negative theta of the long call is neutralized by positive theta from the short put.
- **Vega:** Nearly cancels; minor drift persists due to skew and microstructure.
- **CSP Overlap:** **Critical problem:** If you overlay a CSP (short 25-delta put), you now have TWO short puts: one ATM (synthetic), one OTM (overlay). P&L becomes distorted — the total portfolio is long Nifty + short put ladder, NOT a clean long plus CSP.
- **Slippage:** Both ATM contracts are liquid. No major issue.
- **Other:** Margin and cashflows match synthetic future; risk: if CSP overlay is also at ATM, you are double short the same strike, which is dangerous and unnatural vs. real futures.
- **Conclusion:** **Best for pure “replicate a future”, but problematic in overlay framework (you will unintentionally double short puts).**

#### **c) Near-ATM, Moderately ITM Call (delta ~0.70, 1000–1500 points ITM)**

- **Delta ~0.70:** Not full Nifty exposure — about 70% participation. Easier to fill, costs less premium (~₹1–1.5L).
- **Theta:** Higher daily decay than deep ITM.
- **Vega:** Higher IV risk.
- **Margin:** Lower — you only pay for the premium.
- **CSP Overlap:** No embedded short put, so CSP overlay is clean.
- **Realism:** Not a true “long Nifty” — use only if not seeking perfect 1:1 tracking.
- **Risk:** Underperforms on strong up-moves; cushions down-moves due to delta drop below ATM.

---

### **Best Choice for Track C:**

**Deep ITM Call (candidate a) is the best structure for cost-effective, clean, and analyzable comparison in this framework:**

- **Why:** It tracks “long Nifty” exposure while separating overlays cleanly (no embedded short put, so CSP and protection overlays are accurately benchmarked).
- **Trade-offs:** Some theta decay, but less than nearer-ATM calls, and acceptable for a 1-lot structure. Margin and simplicity make it operationally smooth for retail paper/live trading.
- **Synthetic Long** is ideal for theoretical precision, but will corrupt overlay test results with extra short put exposure (unintended risk overlap).
- **Operational Guidance:** Pick the strike so delta is as close to 0.90 as possible; use monthly expiry, roll on expiry.

---

## (2) **OVERLAY STRATEGY INTERACTION MATRIX**

### **Summary Table**

| Base        | Protective Put         | Covered Call              | CSP (Short Put ~25Δ)            | Notes on Risk/Product |
|-------------|---------------------- |--------------------------|---------------------------------|----------------------|
| NiftyBees   | Standard protective   | Standard covered call    | Adds short put to long ETF      | Textbook. No interactions. |
| Nifty Futures| Std protective put    | Synthetic short put      | Adds short put to linear future | Futures + short OTM call = short put, risky if unhedged. |
| Deep ITM Call| Bull call spread      | Calendar vertical (diag) | Adds naked put if CSP overlay   | Long deep call + OTM put = vertical spread; + CSP = net short put at CSP strike. |

#### **Portfolio Greeks**:

- **Protective Put Overlay:** Reduces delta as Nifty falls; adds positive convexity (gamma), increases cost (net debit = insurance).
- **Covered Call Overlay:** Reduces upside delta; adds negative gamma; reduces net vega; caps profit but adds premium income.
- **CSP Overlay:** Adds a short OTM put delta; increases downside convexity; netting effect: combines two short puts at different strikes if already using synthetics.

---

### **Structural Dangers/Redundancies**

**Dangerous:**
- **Futures/Deep Call + Covered Call = Covered Call:** Losses on downside, capped upside. If you then add a CSP (short put), you become overexposed to downside — netting 2 or more short puts from overlays. Must not double up inadvertently.
- **Futures + Short Call only = Synthetic Short Put:** Beware this is already riskier — avoid adding CSP overlays that further increase short put exposure beyond intended.

**Redundant:**
- **Futures + short OTM put (CSP):** Is just a leveraged put-writing strategy; if you also have NiftyBees + CSP, you can view these as levered/unlevered versions.
- **Deep ITM Call + Protective Put:** This IS a bull call spread (if strikes close, vertical; if separated, risk-reversal or spread).
- **Deep ITM Call + Covered Call:** If expiry dates match = vertical call spread (profit capped).

**Recommendations:**
- Flag any portfolio where overlay creates net unhedged additional short put exposure unless expressly intended.
- Avoid synthetic/futures base + CSP overlays in the same portfolio (structurally unclear accounting & risk).

---

## (3) **ADDITIONAL PROTECTION STRUCTURES**

### **a) Collar (Long base, Long OTM Put, Short OTM Call)**

- **What:** Long NiftyBees/Deep-ITM Call/Future, buy OTM put, sell OTM call at higher strike.
- **Net:** Reduces insurance cost (put premium minus call premium), caps upside, preserves downside floor.
- **Why valuable:** Cost is lower than pure protective put, and real-world buywrite/collar ETFs deliver this efficiently. Avoids the negative theta drag of pure protection.
- **Implementation:** For paper/live trading, OTM call and OTM put should have similar DTE and OI.
- **Risk:** Misses “home run” rallies above covered call but provides clean P&L marks for protection vs. capped return.

### **b) Ratio Spreads (e.g., 1×2 Put Spread)**

- **What:** Buy 1 ATM (or near-ATM) put, sell 2 OTM puts.
- **Why:** Costs zero (or even nets a small credit); profits in small/medium drop, but creates net short put exposure below furthest sold strike.
- **When useful:** Nifty's negative skew/expensive puts means you can sometimes build these for zero cash.
- **Counterpoint:** **Dangerous if Nifty crashes:** Large open-ended losses below furthest strike. Must be included only for advanced risk tolerance (operator must strictly limit exposure, size, and document cases).

### **c) Vertical Call/Put Spreads, Put Ratio Backspread, Calendar Diagonals**

- **Call/Put verticals:** Standard defined-risk structures; can be used for tactical overlays if operator wants to simulate "levered hedged returns".
- **Put Ratio Backspread:** Buy more puts than you sell at higher strike — net positive gamma/tail insurance, but net debit.
- **Calendars:** Sell short-term OTM put or call, buy longer-term further OTM. Exploits term structure but adds complexity.

### **d) Short Strangles/Straddles (Not Recommended)**

- Highly capital-intensive, requires full margin; tail risk is not defined unless explicitly capped with wings.

### **e) Iron Condors, Butterfly Spreads**

- Useful in theory, unlikely to be capital-efficient at 1-lot retail scale (bid/ask and fees eat most edge).

**Net Recommendation:** Collars are operationally simple and align with your mission ("protect before you earn"). Ratio spreads, if used, need *extreme* discipline and visibility. Simple verticals and backspreads only if risk is defined.

---

## (4) **DAILY P&L REPORT DESIGN**

### **a) Report Base and Overlay P&L Separate or Combined?**

**Strong Recommendation:** **Report both SEPARATELY and in combination, per track.**

- Operator must see:
    - How much of P&L comes from "core" (e.g., NiftyBees/Future/Deep ITM call)
    - How much is purely from overlays (protection, income)
- This clarity is *critical* for risk and accountability — especially in drawdowns, you want to know if the hedge overlay paid off (e.g., on a -2% day, NiftyBees -₹8,500, but protective put +₹9,000, net +₹500), or if it's dead weight during rallies.

### **b) Cross-Track Comparison & Capital Normalization**

**YES, must include cross-track comparisons.**

- **Absolute P&L** is misleading, since:
    - NiftyBees (delivery) ties up ₹15.5L
    - Futures trade on ₹1.5L margin (remainder can be parked in liquid funds — **track separately**)
- **Standardize:** Report both *absolute* return *and* *capital efficiency* return (P&L as % of capital at risk).
    - For physical (NiftyBees): capital = invested amount.
    - For futures: capital = margin + notional cash reserve (to match NiftyBees exposure).
    - For deep-ITM calls: capital = option premium + cash needed to collateralize equivalent exposure (if required by overlay).
- **Drawdowns:** Also report *max drawdown* for each track, in absolute and % terms.

### **c) Minimum Set of Greeks for Daily Mark-to-Market**

**Per track, report portfolio-level:**
1. **Delta:** Total exposure to Nifty moves (net sum across legs including overlays).
2. **Theta:** Daily decay/gain from time value (the real cost of options overlays).
3. **Vega:** Net sensitivity to IV moves (very useful for bounding expected MTM drift in low-volatility periods or during vol spikes).
4. **Gamma:** Optional, but high value for option structures with non-linear P&L around strikes.
5. **(Optional, but desirable)** For collar/spread overlays, Greeks *by overlay* (i.e., see portfolio-level AND overlay-level Greeks).

**Daily table example:**

| Date | Track | Base P&L | Overlay P&L | Net P&L | Total Delta | Total Theta | Total Vega | Max DD (abs/%) |
|------|-------|----------|-------------|---------|-------------|-------------|------------|----------------|
| ...  | ...   | ...      | ...         | ...     | ...         | ...         | ...        | ...            |

**Also provide:**
- Rolling 20/60-day realized volatility per track.
- Overlay cost/benefit, e.g., cumulative premium paid/received from overlay, cumulative P&L from each overlay.

---

# **SUMMARY OF THE BEST PRACTICE ANSWERS**

1. **Track C "long Nifty via option":** Use a deep ITM call (single-leg, delta ~0.90, monthly expiry). Avoid synthetic future for this use case, as it creates CSP overlay interaction (hidden double short put risk).

2. **Interaction Matrix:** Overlay P&L and Greeks must be tracked per overlay, per base instrument. Avoid combining synthetic future + CSP; all other combinations have well-defined risk, but be careful with overlays adding duplicate exposures.

3. **Additional Protection Structures:** Collars (put + covered call) are well suited for your risk discipline and capital efficiency. Ratio spreads/backspreads are advanced and only suitable with strict visibility and capital/risk limits.

4. **Daily P&L Report:** Structure as both base and overlay breakouts *and* combined, per track. Normalize capital for track-to-track comparisons; include delta/theta/vega daily, and max DD/return. This supports actionable review and meets the "protect before you earn" mission.

**If you want, I can draft a template schema for the daily report, or code snippets for how the paper-trading engine should aggregate and report overlay + base positions and Greeks.**

### google/gemini-3.1-pro-preview-20260219

**CONTEXT.md ✓**

Here is the analysis and structural blueprint for the 3-track Nifty combined paper-trading framework, strictly aligned with `MISSION.md` (specifically Principle I: Protect Before You Earn, and Principle IV: Segregate Pools) and the existing `niftyshield_integrated_v1` architecture.

---

### 1. ITM Option Structure for Track C

**Recommendation:** **(a) Deep ITM Call (delta ~0.90)** is the objectively superior structure for Track C.

**Rationale based on cost, margin, and strategy interaction:**
*   **The synthetic long (b) must be rejected.** While computationally elegant, buying an ATM call and selling an ATM put creates a short put leg. Since the framework introduces a Cash-Secured Put (CSP) at ~25 delta as an overlay, Track C would become net short *two* puts. In a market crash, overlapping margin expansions on both the synthetic short put and the CSP short put will violate risk parameters and blow past the ~₹6L max drawdown limit.
*   **The near-ATM call (c) suffers from gamma risk and high theta drag.** At 0.70 delta, movement is non-linear. As Nifty drops, delta rapidly evaporates, breaking the equivalence to Track A (ETF) and Track B (Futures).
*   **The Deep ITM Call (a) isolates the variable.** By paying the ₹2–3L intrinsic premium upfront, there is no margin blockage (beyond the premium itself), and the theta drag (extrinsic value decay) is negligible. More importantly, it creates a perfectly clean substrate for the overlays. If you run a Covered Call against it, it simply becomes a capital-efficient bull call diagonal/vertical spread. If you run a CSP, the short put remains isolated as the sole naked tail risk.

### 2. Overlay Strategy Interaction Matrix: The Dangers & Redundancies

When tracking combinations across the base variations, clear redundancies and structural traps emerge. 

*   **(d) Long Nifty Futures + Covered Call (Synthetic Short Put):** **DANGEROUS.** If operated simultaneously with the standard CSP overlay, this track effectively becomes a leveraged 2-lot short put strategy. Futures have linear downside. By capping upside via the short call, the unrecoverable capital is entirely exposed on the downside. If a protective put is not explicitly mandated here, this violates Principle I.
*   **(e) Long Deep-ITM Call + Protective Put:** **REDUNDANT.** A deep ITM call *already* has a defined max loss (the ₹2–3L premium). Buying a protective OTM put on top of an ITM call creates a structure equivalent to a synthetic long stock position plus a put—which structurally collapses into a long call at a higher strike price. You are paying double vega and double theta for protection you already purchased implicitly via the call option. It is substantially more efficient to run a pure bull call spread if you want downside protection on an option chain, rather than legging a deep ITM call and a far OTM put.
*   **(f) Long Deep-ITM Call + Covered Call:** **HIGHLY EFFICIENT.** This is just a vertical or diagonal debit spread (depending on expiry mismatch). It perfectly caps upside and downside while consuming a fraction of the capital of Track A or B. 

### 3. Additional Protection Structures to Paper-Trade

Taking advantage of the negative skew (expensive puts, cheap calls) and the operator’s ₹1.2cr NiftyBees/Bond collateral pool, the following structures should be tested:

*   **Funded Call-Put Collar (Zero-Cost Collar):** Nifty's skew means an equidistant OTM call will rarely fund an OTM put entirely. However, because you hold NiftyBees as collateral, establishing a Collar (Buy 8% OTM Put, Sell 4% OTM Call) uses the NiftyBees to cover the short call leg implicitly. This funds the downside hedge without adding net new margin.
*   **Put Spread Risk Reversal (Capped Risk Variant):** Standard ratio spreads (buy 1 put, sell 2 further OTM puts) are **rejected**—they violate Mission Principle I because they leave naked tail risk where you need it most. Instead, test the exact `niftyshield_integrated_v1.md` Leg 2 (Buy 8% OTM Put, Sell 20% OTM Put) **fully funded by selling a single 15-20 delta OTM Call**. This limits max loss 100%, caps upside slightly, provides moderate crash protection, and eliminates the theta bleed of standard protective puts. 
*   **Front-Month vs. Quarterly Calendar Diagonal:** A structural hedge capitalizing on vol term structure. Buy the deep OTM Quarterly Tail Put (Leg 3 from NiftyShield v1), and continuously sell 10-delta weekly or monthly puts against it. *Warning:* Margin intensive, but mathematically forces the long-term insurance to pay for itself.

### 4. Daily P&L Report Design

To prevent the Daily Snapshot from becoming a useless pile of nominal numbers, the reporting architecture must standardise inputs:

**a) Separated or Combined P&L?**
**Both.** The report must group P&L logically:
*   *Attribution P&L (Separated):* "Track A Base: -₹10,500 | Track A PP: +₹14,000 | Track A CSP: +₹500". This is mandatory to understand *why* a track is winning or losing (is the base instrument dragging, or are the overlays over-performing?).
*   *Unit P&L (Combined):* "Track A Net: +₹4,000". This tracks the real equity curve. 

**b) Capital Normalization across Tracks**
You cannot compare ₹1.5L futures margin vs. ₹15.5L NiftyBees cash. You must denominator-lock the report to **Notional Equity Equivalent (NEE)**.
*   Base all metric calculations on the exact notional value of 1 Nifty lot (~₹15L–15.6L).
*   Report **Return on Target Notional (RoTN)** per track. E.g., if Futures make ₹15,000, that is reported as a ~1% yield on the 1-lot equivalent, *not* a wildly misleading 10% yield on ₹1.5L margin. This aligns with Mission Principle V (predictable floor vs leveraged speculation).

**c) The Minimum Actionable Greeks**
At the *Track Portfolio* level, report exactly three aggregated numbers daily:
1.  **Net Position Delta:** Ensures tracks are roughly equivalent (e.g., Track A might be 1.0 delta, Track C might drift to 0.85). If Net Delta breaches <0.40 or >1.20, the comparison has mathematically drifted.
2.  **Net Theta (₹/Day):** Reveals the structural bleed. Track A alone will have 0 theta; Track C with a PP will show massive negative theta (-₹X/day). This exposes the true carry cost of the strategy before any price movement happens.
3.  **Net Vega:** Given Nifty's aggressive IV spikes leading into events, capturing how exposed each track is to a 1-point VIX rise dictates survivability during tail events. Track C will exhibit vastly different IV reactions than Track B + overlays. 

*Actionable Next Step:* For the backtest plan (`BACKTEST_PLAN.md` Phase 0 integration), define `paper_track_a`, `paper_track_b`, and `paper_track_c` as distinct strategy namespaces in `record_paper_trade.py` to keep the SQLite logs segregated for analysis.

### x-ai/grok-4-07-09

Below is my response to your four questions as a member of the council advising on the NiftyShield project. I've drawn on the provided context (e.g., strategy specs from `niftyshield_integrated_v1.md`, `csp_nifty_v1.md`, and `INVESTMENT_STRATEGY_RESEARCH.md`), decision domain constraints, and general principles of options trading, risk management, and backtesting for Nifty 50 index options. All recommendations are for paper trading and backtesting only (Phase 0), aligned with the project's immutable principles (e.g., protect before you earn, backtest before deploy). I've assumed good intent in your query, treating it as a hypothetical framework for research and comparison, not live trading advice. Responses are high-level, focusing on structural analysis without step-by-step execution details or code.

### (1) ITM OPTION STRUCTURE FOR TRACK C
The goal for Track C is to simulate long Nifty futures exposure via an options-based structure for a 12-month paper trading comparison, allowing clean overlays (protective put, covered call, CSP) while minimizing unintended interactions. Cost-effectiveness is evaluated across: (i) total cost of carry (theta decay, premium decay, and opportunity cost of capital); (ii) margin capital locked (using your ₹1.2cr collateral pool as context, with NiftyBees already pledged); (iii) interaction with the CSP overlay (which involves a short 25-delta put, per `csp_nifty_v1.md`); and (iv) overlay compatibility (how cleanly protective strategies apply without creating gamma/vega mismatches or excessive slippage in thin monthly chains).

- **Candidate (a): Deep ITM call (~2000-2500 points ITM, delta ~0.90, premium ~₹2-3L, single leg)**  
  This has moderate theta decay (~₹100-200/day at entry, decaying as it goes deeper ITM) but no roll cost (hold to expiry, then re-enter). Margin is low (~₹1-1.5L, similar to futures, as it's deeply ITM). CSP interaction is neutral—no overlapping short put. Overlays work cleanly: protective put creates a bull call spread equivalent (defined risk/reward), covered call adds a diagonal spread flavor (theta-positive but caps upside). Cost-effectiveness: High for 12-month horizon—theta drag is offset by high delta fidelity (close to 1.0 linear exposure), and it's cheaper long-term than repeated synthetics. Slippage is manageable on deep ITM strikes (OI often >10k on Nifty monthlies).

- **Candidate (b): Synthetic long (buy ATM call + sell ATM put at same strike, near-zero net premium, delta ~1.0, margins like futures)**  
  This is the truest futures proxy (linear P&L, no theta on the net position). Theta is near-zero (call theta offsets put theta), but roll cost exists (re-enter monthly). Margin is ~₹1.5L (futures-like). However, CSP interaction is problematic: the synthetic's short ATM put + CSP's short 25-delta put creates a double short-put position (net short 2 puts at different strikes), amplifying downside gamma/vega risk and potentially violating the project's "protect before you earn" principle (unintended naked short-put exposure below the lower strike). Overlays are messy: protective put partially hedges the synthetic's short put but leaves CSP exposed; covered call turns it into a collar-like structure with high vega sensitivity. Cost-effectiveness: Medium—low carry cost but high risk of redundancy/overlap, making it unsuitable for clean comparison.

- **Candidate (c): Near-ATM call (~1000-1500 points ITM, delta ~0.70, premium ~₹1-1.5L)**  
  Cheaper upfront with moderate theta decay (~₹150-300/day), no roll cost. Margin is low (~₹0.8-1.2L). CSP interaction is neutral. Overlays apply similarly to (a) but with lower delta fidelity (exposure feels more like 0.7x futures, introducing convexity). Cost-effectiveness: Low for 12 months—theta drag accumulates (~₹30-50k/year), and lower delta means overlays (e.g., protective put) create asymmetric profiles that diverge from Tracks A/B, complicating comparisons.

**Recommendation:** Choose (a) Deep ITM call. It's the most cost-effective for your 12-month paper trading purpose—high delta fidelity mimics futures without the synthetic's short-put overlap (avoiding CSP interaction issues), low margin tie-up fits your collateral pool, and overlays integrate cleanly (e.g., protective put forms a defined-risk spread). Total carry cost is ~5-7% annualized (theta + broker costs), vs. 8-10% for (c) due to higher relative decay, and it avoids (b)'s structural redundancy. Paper-trade with monthly re-entry at the strike closest to 0.90 delta (e.g., ~22000 strike if Nifty spot ~24000).

### (2) OVERLAY STRATEGY INTERACTION MATRIX
For each base instrument (Track A: Long NiftyBees ETF; Track B: Long Nifty Futures; Track C: Long deep-ITM call per recommendation above), I'll describe how each overlay (protective put: buy OTM put ~8-10% OTM; covered call: sell OTM call ~5-10% OTM; CSP: short 25-delta put per `csp_nifty_v1.md`) alters combined portfolio Greeks (delta, gamma, theta, vega) and P&L characteristics. Assumptions: 1-lot scale, monthly cycles, Nifty spot ~24000. Dangerous combos (unlimited downside) and redundancies (equivalent to simpler/cheaper structures) are flagged.

- **Track A (Long NiftyBees + Overlay):**
  - + Protective put: Delta decreases nonlinearly below put strike (e.g., from +1.0 to +0.2); gamma peaks near strike; theta negative (put decay hurts); vega positive (benefits from IV spike). P&L: Textbook protective put—caps downside at put strike minus premium, unlimited upside. Safe, no redundancy.
  - + Covered call: Delta capped at ~+0.8-0.9; gamma reduced (call gamma offsets); theta positive (call premium income); vega negative (hurts in IV spike). P&L: Upside limited to call strike + premium; downside like naked long (full exposure). Safe if collateral covers, but redundant if NiftyBees is already pledged—equivalent to holding and writing calls directly (no added cost benefit).
  - + CSP: Delta ~+0.75 (ETF + short put); gamma elevated on downside; theta positive; vega negative. P&L: Income from put premium offsets ETF drawdowns mildly, but assignment risk turns it into doubled long ETF. Safe with your collateral, but interaction creates correlated risk (both legs hurt in down moves).

- **Track B (Long Nifty Futures + Overlay):**
  - + Protective put: Delta from +1.0 to near 0 below strike; gamma from put; theta negative; vega positive. P&L: Synthetic long call—defined downside (max loss = premium), unlimited upside. Safe, equivalent to buying a call outright (redundant/cheaper to enter directly if no futures preference).
  - + Covered call: Delta capped; gamma reduced; theta positive; vega negative. P&L: Synthetic short put—unlimited downside below breakeven (futures loss + call premium), capped upside. **Dangerous:** Unlimited downside without hedge; violates "protect before you earn." Avoid unless adding a put.
  - + CSP: Delta ~+0.75; gamma high on downside; theta positive; vega negative. P&L: Enhanced income but doubled downside (futures + short put assignment). **Dangerous if unhedged:** Potential for large losses in tail events; redundant with a naked short strangle if strikes align.

- **Track C (Long deep-ITM call + Overlay):**
  - + Protective put: Delta from ~+0.9 to near 0; gamma peaks (spread-like); theta negative but muted; vega low (offsetting). P&L: Bull call spread equivalent—max loss defined (premium difference), max gain capped. Safe, but redundant (just enter a bull call spread directly at lower slippage/cost).
  - + Covered call: Delta reduced to ~+0.4-0.6; gamma low; theta near-neutral (diagonal spread); vega negative. P&L: Diagonal/vertical spread—time-decay income, but upside/downside both limited. Safe, but complex interaction (calendar effects if expiries differ); equivalent to a covered call on a lower-delta base.
  - + CSP: Delta ~+0.65; gamma high downside; theta positive net; vega negative. P&L: Income-boosted but with theta drag from long call; assignment risk on CSP adds convexity. Safe with collateral, but interaction creates mild redundancy (long call + short put ≈ synthetic futures with income).

**Key Flags:** Dangerous combos include Track B + covered call (unlimited downside) and Track B + CSP (amplified tail risk). Redundancies: Track B + protective put = long call (enter directly); Track C + protective put = bull call spread (simpler entry). Overall, Track A overlays are "textbook" and least prone to issues; avoid Track B covered call entirely.

### (3) ADDITIONAL PROTECTION STRUCTURES
Beyond protective puts, covered calls, and CSP, consider these for paper-trading/backtesting in your framework (1-lot scale, retail setup, ₹1.2cr collateral). Focus on structures leveraging Nifty's negative skew (higher put IV vs. calls, ~5-10% premium on OTM puts) while ensuring defined downside (per mission principles). Evaluate feasibility: low execution complexity, margin fit, and alignment with Phase 0 simplicity.

- **Collars (protective put + covered call simultaneously):** Net debit ~₹500-1000/lot (call credit offsets put cost). Greeks: Neutral delta (~0.5-0.7), low gamma/vega, theta near-zero. P&L: Downside protected, upside capped—zero-cost hedge if strikes balanced. Worth paper-trading: Leverages skew (sell high-IV call to fund high-IV put), net cost < standalone put. Fits your profile (uses existing NiftyBees as base for "covered" element). Backtest 8% OTM put + 5% OTM call.

- **Ratio spreads (buy 1 ATM put, sell 2 OTM puts ~10-15% below):** Near-zero cost (OTM premiums fund ATM put). Greeks: Delta negative initially, flips positive below lower strike; gamma peaks sharply downside; theta positive; vega positive. P&L: Protection to lower strike, then naked short put beyond (unlimited downside). **Not recommended:** Violates defined-risk mandate—tail exposure dangerous for your single-operator setup. Skew benefit exists (OTM puts have high IV), but risk outweighs.

- **Other Worthwhile Structures:**
  - **Put butterfly (buy 1 ITM put, sell 2 ATM puts, buy 1 OTM put):** Zero/low cost, leverages skew for theta-positive protection. Greeks: Low delta/gamma outside wings, theta positive. P&L: Defined max loss/gain, profits in moderate down moves. Good fit—simple, margin-efficient (~₹50k/lot), backtest for tail protection overlay.
  - **Jade lizard (sell OTM put + sell OTM call spread):** Skew-leveraging income with no upside risk (call spread caps). Greeks: Delta neutral-ish, theta positive, vega negative. P&L: Income-focused protection. Paper-trade if CSP needs enhancement—complements your existing CSP without overlap.
  - Avoid complex exotics (e.g., condors) due to thin monthly liquidity and high slippage at 1-lot scale.

Prioritize collars and put butterflies for Phase 0— they enhance the matrix without redundancy, backtest easily (use NSE CSV dumps), and fit your beta-1.25 portfolio.

### (4) DAILY P&L REPORT DESIGN
For a meaningful 12-month comparison across 3 tracks + overlays, the report should normalize for capital differences, separate components for attribution, and include forward-looking metrics (Greeks) to inform decisions. Align with `paper/` module (e.g., `PaperTracker.compute_pnl` for snapshots).

- **(a) Separate vs. Combined P&L:** Report **separately within each track** (e.g., "Track A: NiftyBees Δday P&L -₹8,500; Protective put +₹12,000; Covered call -₹500; CSP +₹300; Track net +₹3,300"). This allows attribution (see which overlay drives returns) and isolates base vs. overlay performance. Include a combined track total for holistic view, but separation is essential for research—e.g., to quantify CSP's income offset in down days.

- **(b) Cross-Track Comparison and Normalization:** Yes, include cross-track metrics (e.g., "Track A total P&L +₹45k, max drawdown -4.2%; Track B +₹38k, -5.1%; Track C +₹52k, -3.8%"). Normalize by capital deployed: Use return on capital (e.g., P&L / initial capital—₹15.5L for Track A, ₹1.5L margin for B/C) to make fair (e.g., "Annualized ROC: Track A 12%, Track B 80%, Track C 65%"). Also normalize drawdowns (e.g., % of capital at risk). This avoids misleading raw P&L (futures leverage inflates Track B numbers).

- **(c) Minimum Greeks Set:** Report portfolio-level per track: Delta (net directional bias), Theta (daily decay/income), Vega (IV sensitivity). These are actionable—e.g., high negative theta signals decay drag; vega helps assess skew leverage. Omit gamma (less daily relevance for monthly strategies) unless tail events occur. Compute from Upstox chain (per `src/models/options.py`).

### deepseek/deepseek-r1-0528

Based on the comprehensive project context, decision constraints, and strategic objectives of NiftyShield, here are the Council's recommendations for the 3-track paper trading framework:

### 1. ITM Option Structure for Track C (Nifty Exposure via Options)
**Recommended:** **(a) Deep ITM Calls (~2000-2500 pts ITM, delta ~0.90)**
- **Cost-effectiveness:** Minimal theta decay (~10-25% of ATM premium) and no roll costs.
- **Margin:** Minimal capital requirement (premium only) vs. futures' recurring margin calls.
- **CSP overlay compatibility:** Zero conflict with CSP shorts (no overlapping short-put legs).
- **Protection synergy:** Greeks align cleanly with protective strategies:
  - ∆ ≈ 0.90 provides high directional fidelity
  - Minimal vega exposure reduces volatility noise
  - Low gamma prevents position distortion

**Rejected (b) Synthetic long:** Creates compounding short-put exposure conflicting with CSP overlay.  
**Rejected (c) Near-ATM calls:** Higher theta decay (~40-60% of premium monthly) distorts protection P&L.

### 2. Overlay Strategy Interaction Matrix
#### Risk Assessment Key:
- ✅ = Safe combination  
- ⚠️ = Requires tight risk controls  
- 🚫 = Structurally dangerous  
- 🔄 = Redundant (convert to simpler structure)

| Base \ Overlay       | Protective Put        | Covered Call          | CSP (Short Put)      |
|----------------------|-----------------------|-----------------------|----------------------|
| **Track A (NiftyBees)** | ✅ Textbook put protection<br>∆↓ on decline, ϴ-/V⁺ | ✅ Standard income strategy<br>∆↓ on rise, ϴ⁺/V⁻ | ⚠️ *Not recommended*<br>Doubles downside exposure |
| **Track B (Futures)**  | 🔄→ Long Call<br>(Convertible) | 🚫 Synthetic short put<br>(Unlimited risk) | 🚫 Double short-put exposure |
| **Track C (Deep ITM)** | 🔄→ Call Spread<br>(Clean protection) | 🔄→ Diagonal Spread<br>(Managed upside) | ⚠️ Synthetic straddle<br>(Requires monitoring) |

**High-Risk Combinations Requiring Blocks:**  
- Track B + Covered Call → Synthetic short put (unlimited downside)
- Any Track + CSP without explicit short-put sizing logic → Margin blowup risk

**Redundant Combinations to Simplify:**  
- Track A/B + Protective Put + Covered Call → Convert to collar (net debit/credit)
- Track C + Protective Put → Execute as call spread upfront

### 3. Additional Protection Structures Worth Testing
**Priority 1: Collars (Protective Put + Covered Call)**  
- **Advantage:** Lowers protection cost via premium monetization
- **Nifty skew benefit:** Exploits 4-6% IV premium for OTM puts vs OTM calls
- **Implementation:**  
  - Put strike: 8-10% OTM  
  - Call strike: 3-5% OTM  
  - Target net credit ≥ 0

**Priority 2: Vega-Neutral Put Spreads**  
- **Structure:** Buy 1x ATM Put + Sell 2x OTM Puts (25-30% OTM)  
- **Edge:** Capitalizes on Nifty's steep volatility smile  
- **Risk control:** Automatic stop at 2× max-loss estimate

**Excluded Structures:**  
- Ratio spreads (magnifies tail risk)  
- Calendar spreads (term structure unstable)  

### 4. Daily P&L Report Design Essentials
**(a) Position Granularity:**  
```markdown
Track A (NiftyBees):
- Base: +₹8,500 (△+0.92)
- Overlay (Put): -₹1,200 (ϴ-₹42, V+₹180)
- Net: +₹7,300 
```

**(b) Cross-Track Comparison Metrics:**  
- **Capital Productivity Ratio:** `(Total P&L) / (Capital Employed × Days)`  
- **Normalized Drawdown:** Peak-to-trough loss ÷ allocated capital  
- **Volatility Efficiency:** Return ÷ portfolio vega  

**Capital Normalization:**  
| Track | Capital Basis          | Example Allocation |
|-------|------------------------|-------------------|
| A     | Full asset value       | ₹15.5L            |
| B     | Margin requirement     | ₹1.5L (12.5% NLV) |
| C     | Option premium paid    | ₹2.8L             |

**(c) Critical Greek Minimums:**  
```python
report_metrics = {
    "delta": "Equivalent Nifty points exposure",  # e.g., △+58 = long 1.0 lot
    "theta": "Daily time decay (₹)", 
    "vega": "₹ exposure per 1% IV change",
    "gamma_risk": "△ per 1% move (only when |△| ≥ 0.70)"
}
```

### IMPLEMENTATION ROADMAP
1. **Paper Trading Setup**  
   - Track C: Execute single-leg deep ITM calls monthly  
   - Block dangerous combinations (Track B+covered call) in code  
   - Daily snapshot: `compute_portfolio_greeks()` + capital-normalized P&L  

2. **Operational Controls**  
   - Auto-convert redundant positions (e.g., futures+put → long call)  
   - Max loss circuit-breaker per track (2% allocated capital)  

3. **T+1 Reporting**  
```bash
python -m track_analytics --tracks A B C --normalize capital
```

This framework maintains NiftyShield's capital protection ethos while systematically comparing cost, protection efficiency, and operational practicality across approaches.

## Aggregate Rankings (Stage 2 Peer Review)

- openai/gpt-4.1-2025-04-14: avg rank 1.25 (4 votes)
- x-ai/grok-4-07-09: avg rank 2.75 (4 votes)
- google/gemini-3.1-pro-preview-20260219: avg rank 2.75 (4 votes)
- deepseek/deepseek-r1-0528: avg rank 3.25 (4 votes)

---

## Prompt Sent (first 3000 chars)

```
=== NIFTYSHIELD PROJECT STATE ===

# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase.
> Read this before writing any code. Do not rely on session summaries or chat history.
> Repo: https://github.com/archeranimesh/NiftyShield

**Related files:** [MISSION.md](MISSION.md) — immutable mission + grounding principles | [DECISIONS.md](DECISIONS.md) | [REFERENCES.md](REFERENCES.md) | [TODOS.md](TODOS.md) | [PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) — phased backtest → paper → live plan | [LITERATURE.md](LITERATURE.md) — concept reference (Kelly, Sharpe, meta-labeling) | [docs/plan/](docs/plan/) — one story file per task | [INSTRUCTION.md](INSTRUCTION.md)
---

## Current State (as of 2026-05-01)

### What Exists (committed and working)

Full file-level module tree: **[CONTEXT_TREE.md](CONTEXT_TREE.md)**
Load that file when adding new modules or doing a full structural survey.
For task work, use the graph: `search_graph`, `get_code_snippet`, `trace_path`.

Key top-level packages: `src/auth`, `src/client`, `src/models`, `src/portfolio`, `src/paper`, `src/mf`, `src/dhan`, `src/nuvama`, `src/instruments`, `src/market_calendar`, `src/notifications`, `src/utils`, `src/db.py`

`src/models/options.py` — `OptionLeg`, `OptionChainStrike`, `OptionChain` (all `frozen=True` Pydantic). Source-agnostic field names; Upstox parser in `src/client/upstox_market.py` (`parse_upstox_option_chain`). Dhan parser deferred to Phase 1.10.
`src/paper/` — paper trading module. `PaperTrade` model (frozen Pydantic, `paper_` prefix enforced), `PaperPosition` + `PaperNavSnapshot` (frozen dataclasses), `PaperStore` (`paper_trades` + `paper_nav_snapshots` tables in shared SQLite), `PaperTracker` (compute_pnl + record_daily_snapshot). See `src/paper/CLAUDE.md` for module invariants.
Scripts: `daily_snapshot.py`, `morning_nav.py`, `nuvama_intraday_tracker.py`, `seed_*.py`, `record_trade.py`, `record_paper_trade.py` (supports `--underlying/--strike/--option-type/--expiry` auto-lookup via BOD JSON), `paper_snapshot.py` (standalone paper mark-to-market), `roll_leg.py`

### What Does NOT Exist Yet

- `src/nuvama/CLAUDE.md` — module context file not yet written
- `src/strategy/`, `src/execution/`, `src/backtest/`, `src/risk/`, `src/streaming/` — all empty (planned per BACKTEST_PLAN.md Phase 1–2)

### Live Data

- SQLite DB path confirmed: `data/portfolio/portfolio.sqlite`
- DB wiped clean on 2026-04-04 (`daily_snapshots`, `mf_transactions`, `mf_nav_snapshots` all cleared)
- `mf_transactions` re-seeded with all 11 schemes using correct AMFI codes
- `mf_nav_snapshots` empty — first clean snapshot on Monday 2026-04-06 (pre-market run)
- `daily_snapshots` empty — first clean baseline on Monday 2026-04-06 (pre-market run)
- `underlying_price` will populate from 2026-04-06 onwards
- Greeks columns are null across all snapshots
- `trades` table seeded 2026-04-08 — 7 rows: finideas_ilts (6 legs including LIQUIDBEES) + finr...
```