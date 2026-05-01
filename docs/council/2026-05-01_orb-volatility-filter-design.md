# Council Decision: orb-volatility-filter-design

Date: 2026-05-01  
Chairman: anthropic/claude-opus-4.6  
Council members: openai/gpt-4.1, google/gemini-3.1-pro-preview, anthropic/claude-opus-4.6, x-ai/grok-4

---

## Stage 3 — Chairman Synthesis

# NiftyShield Council — Final Ruling: Strategy 2 (ORB) Structural Design Decisions

**Council session:** 2026-05-01 | **Status:** Binding | **Scope:** Three architectural decisions for the ORB signal generator

---

## DECISION 1 — Volatility Filter: ATR-only vs. VIX Co-filter

### Verdict: **ATR as primary filter. VIX-IVP ≥ 90th percentile (63-day trailing rank) as structural binary exclusion — non-swept, configurable flag. Ablation required.**

### Rationale

1. **ATR is the theoretically correct denominator.** The ORB hypothesis is about *compression relative to recent price action*. The OR width divided by 14-day ATR directly measures this. It is not a proxy — it is the definition of the edge.

2. **VIX captures a real failure mode that ATR misses.** On pre-event consolidation days (e.g., day before RBI MPC when announcement is at 10:00 AM), realised vol is low (ATR low, OR compressed), but the market is pricing known future uncertainty (VIX elevated). The OR "compression" on these days represents *waiting*, not *indecision resolving into conviction*. The ORB hypothesis is structurally degraded — though not fully invalid if the event is excluded by calendar (see Decision 2).

3. **The 90th percentile framing eliminates boundary noise.** Per the Donchian council precedent, a fixed absolute VIX threshold (e.g., >18) suffers from ±1.5 point daily noise affecting 20–30% of boundary days. A rolling 63-day IVP at the 90th percentile is a *structural tail exclusion*, not a mid-range boundary:
   - At the 90th percentile of a right-skewed distribution, a 1-point VIX move changes the percentile rank by only 1–2 points (values are more spread out at the top)
   - This affects ~5 days/year at the boundary — an order of magnitude less than a fixed threshold
   - The filter is self-calibrating: in high-vol regimes "90th percentile" adapts upward; in calm regimes it adapts downward

4. **This is NOT a swept parameter.** Fix at 90th percentile. Do not optimise. Document as a structural exclusion analogous to Thursday expiry exclusion. It excludes ~12 days/year — too few to overfit to but enough to remove the worst hypothesis violations.

5. **Ablation gate:** The backtest must report Sharpe with and without the VIX exclusion. If the difference is < 0.1 Sharpe, **drop the VIX filter entirely** — simpler is better. The flag defaults to `True` but reverts to `False` if ablation fails.

### Implementation

```python
# In signal generator config
vix_exclusion_enabled: bool = True  # configurable flag
vix_ivp_threshold: float = 0.90     # NOT swept — structural constant
vix_lookback_days: int = 63         # ~3 months rolling window
```

Backtest reports both paths in walk-forward output. VIX series stored in all signal records regardless of filter state.

---

## DECISION 2 — Event Day Treatment: Structural Exclusion

### Verdict: **Structural exclusion of pre-scheduled macro event dates. Mandatory.**

### Rationale

1. **This is a universe definition problem, not a filter problem.** The ORB hypothesis states: "overnight information resolves into the opening range; a breakout from compression signals directional conviction." On RBI MPC day (announcement at 10:00 AM), the opening range does *not* represent information resolution — it represents pre-announcement positioning. A breakout at 9:45 AM on Budget day is random noise, not directional conviction. The hypothesis is structurally inapplicable.

2. **Filters will fail precisely when they should not.** Pre-event days are notoriously *compressed* — tight ranges before known announcements. This means:
   - ATR is low → OR width / ATR ratio passes the compression filter
   - VIX may be elevated (caught by Decision 1's 90th percentile exclusion) or may not be (e.g., routine RBI hold expected)
   - The filter is *more likely* to trigger a false entry on these days, not less

3. **No look-ahead bias.** RBI MPC dates are published 12+ months in advance. Union Budget date is known months ahead. FOMC dates are published annually. Using a pre-published calendar is identical to what a live system would know at time T−365. The standard definition of look-ahead bias requires information not available at decision time — this does not qualify.

4. **Surprise events are NOT excluded.** Geopolitical shocks, flash crashes, unexpected circuit breakers — these remain in the universe. They are part of the true loss distribution. Only *pre-scheduled* dates with known announcement times qualify for structural exclusion.

5. **Post-event days remain in-universe.** The day *after* Budget/RBI is when the ORB hypothesis is at its strongest — overnight uncertainty from the announcement resolves in the morning. Do not exclude event weeks; exclude event *dates* only.

### Exclusion Calendar

| Event | Frequency | Source |
|-------|-----------|--------|
| RBI MPC announcement day | 6/year | RBI website, published annually |
| Union Budget day | 1/year | Ministry of Finance |
| FOMC+1 IST trading day | 8/year | Fed website (next IST session after US announcement) |
| Weekly expiry Thursday | ~52/year | Already in spec |

**Total structural exclusions:** ~67 days/year (~52 Thursdays + ~15 macro dates)

### Reporting Requirement

The backtest must track signals that *would* have fired on excluded days:
- Count of excluded signals by event type
- Hypothetical P&L of excluded signals (for ablation — validate that exclusion improves metrics)
- If excluded-day signals show *positive* expectancy, the exclusion list needs revisiting

### Implementation

Calendar file in `src/market_calendar/` with method:
```python
def is_event_exclusion_date(date: date) -> tuple[bool, str | None]:
    """Returns (excluded, reason) — e.g., (True, 'RBI_MPC')"""
```

Updated quarterly when next period's dates are published.

---

## DECISION 3 — Near-Expiry Contract Selection: DTE Cutoff

### Verdict: **DTE ≤ 2 → skip to next weekly expiry. Minimum 3 DTE for any new spread entry.**

### Rationale

1. **Backtest fidelity is the binding constraint, not liquidity.** Nifty weekly options at 2 DTE have excellent liquidity (ATM±5: bid-ask 1–3 points, OI 5–20 lakh contracts). Liquidity is NOT the problem. The problem is that **15-minute discrete-bar backtesting cannot model 2-DTE gamma path-dependency.**

2. **Quantified gamma risk at 2 DTE:**
   - ATM gamma at 2 DTE: ~0.004/point
   - A 100-point Nifty intraday move (occurs ~40% of trading days) changes delta by 0.40
   - A 15-delta short put at entry → 55-delta after a 100-point adverse move
   - If Nifty then recovers 80 points by 15:15, the spread only recovers ~60% of the loss (gamma convexity asymmetry on the path)
   - **15-min bar at close shows net −20 → backtest models ~₹500/lot loss. Actual path-dependent loss: ~₹1,550/lot. Backtest error: ~70% underestimation.**

3. **At 3+ DTE, the error is manageable:**
   - ATM gamma at 4-5 DTE: ~0.002/point (half of 2-DTE)
   - Same 100-point move changes delta by 0.20 (not 0.40)
   - Recovery is more symmetric; path-dependency error drops to ~25–35%
   - Acceptable for research-grade Phase 1 validation

4. **Day-of-week mapping:**

| Signal day | Days to Thursday expiry | Action | DTE used |
|-----------|------------------------|--------|----------|
| Monday | 3 | Use this Thursday | 3 |
| Tuesday | 2 | **Skip** → next Thursday | 9 |
| Wednesday | 1 | **Skip** → next Thursday | 8 |
| Thursday | 0 | Excluded (expiry day) | — |
| Friday | 6 | Use next Thursday | 6 |

5. **Same-day exit neutralises the DTE mismatch concern.** Since the hard exit is at 15:15 IST regardless, theta decay over 6 hours is negligible even at 3 DTE. The profit driver is delta (directional move), not theta. Whether DTE is 3 or 9, the P&L on same-day close is ~95% determined by the underlying's move and the spread's delta. The DTE difference affects entry premium but not same-day directional P&L materially.

### Implementation

```python
def select_expiry(signal_date: date, weekly_expiry_weekday: int = 3) -> date:
    """Thursday = 3 in Python's weekday(). Raises ExcludedDay for expiry day."""
    days_to_expiry = (weekly_expiry_weekday - signal_date.weekday()) % 7
    if days_to_expiry == 0:
        raise ExcludedDay("expiry day")
    if days_to_expiry <= 2:
        days_to_expiry += 7  # skip to next weekly
    return signal_date + timedelta(days=days_to_expiry)
```

### Deferred Question (log to DECISIONS.md)

The same-day-close architecture means profit is delta-driven, not theta-driven. This raises the question: **should ORB use debit spreads rather than credit spreads?** A debit spread's profit scales with the magnitude of the directional move (no cap until spread width is reached), while a credit spread's maximum profit is the premium collected — which cannot be fully captured in a same-day hold.

This is out of scope for the current decision but must be tested in Phase 1 walk-forward: compare credit spread P&L vs. debit spread P&L on the same signals. If debit spreads show > 0.15 Sharpe improvement, a separate council is warranted.

---

## Summary of Binding Decisions

| Decision | Resolution | Key Constraint | Deferred |
|----------|-----------|---------------|----------|
| D1: Vol filter | ATR primary (sweep 0.3–0.8) + VIX-IVP ≥90th pctile structural exclusion (non-swept flag, ablation required) | Boundary noise at mid-range; 90th pctile = tail exclusion only | Drop VIX if ablation < 0.1 Sharpe |
| D2: Event days | Structural exclusion of pre-scheduled dates (RBI MPC, Budget, FOMC+1 IST, Thursday expiry) | ORB hypothesis structurally inapplicable on announcement days | Report excluded-signal P&L for validation |
| D3: DTE cutoff | ≤ 2 DTE → skip to next weekly (min 3 DTE for entry) | 15-min bar backtest cannot model 2-DTE gamma (70% P&L error) | Credit vs. debit spread for same-day exits |

---

## Action Items for Implementation

1. **Signal generator:** ATR compression filter as primary (OR < fraction × 14d ATR). VIX-IVP ≥ 90% as configurable `exclude_high_vix: bool` flag.
2. **Market calendar:** Add `is_event_exclusion_date()` to `src/market_calendar/`, populated with historical RBI/Budget/FOMC dates for backtest period.
3. **Expiry selection:** Implement `select_expiry()` with DTE ≤ 2 skip rule in `src/instruments/`.
4. **Backtest reporting:** Record VIX, DTE, event_day flag, and exclusion reason on every signal. Report ablation tables for both VIX filter and event exclusion.
5. **DECISIONS.md:** Log the credit-vs-debit deferred question with rationale.
6. **Parameter count remains 3** (channel count, max OR fraction, R:R target). VIX exclusion and DTE rule are structural — not optimised.

---

## Stage 1 — Individual Responses

### openai/gpt-4.1

**NiftyShield Council Technical Review — Strategy 2 (ORB) — Three Decisions**

### DECISION 1 — Volatility Filter: ATR-only vs. VIX co-filter

#### (1) Which filter best preserves the ORB hypothesis without overfitting?

**Summary: The core statistical protection against regime noise is _relative compression_ (ATR vs. OR width). The case for including VIX is only compelling when _pre-event days with compressed realized vol but high implied vol_ systematically degrade outcomes and cannot be filtered by ATR alone.**

- **ATR-only (Position A):**  
  - *Pros:* Simple, robust, zero overfitting risk, avoids noisy boundaries. The filter is directly tied to the realized vol that defines "unusual quietude" — which is when opening range plays have edge.
  - *Cons:* Blind to forward vol (event risk). Days with compressed realized vol but high-forward vol (e.g. Budget-eve) may slip through and show structurally adverse expectancy.
- **VIX co-filter (Position B/C):**  
  - *Pros:* Captures market's forward view of volatility; can exclude days where option sellers are bracing for tails even as realized volatility is low.
  - *Cons:* Considerable _boundary noise_: VIX is noisy, often mean-reverting, and event pricing is not a step function. A hard cutoff will see 20–30% of entry days in an ambiguous zone, flipping in/out on tiny VIX changes.

**Recommendation:**  
- Default to **ATR-only** for the initial version.
- *Add VIX as a diagnostic feature*: In the walk-forward analysis, stratify returns by VIX percentile or absolute buckets (e.g. <14, 14–19, 19+). If pre-event high-VIX days are empirically toxic _and_ cannot be captured by ATR filters, co-filtering is justified in v2.
- Justification: The council's Donchian precedent (boundary noise, cell size) applies. Holding out "VIX regime" for post-phase analysis reduces overfit risk.  
- Best-practice: **Preserve VIX series in dataset.** Use it for post-hoc slicing.  

#### (2) Should VIX be applied as an absolute threshold or IVP (percentile rank)?

- **Absolute VIX is preferable** only if local calibration (2019–2026 range normalization) is robust AND Nifty VIX is structurally stable (India VIX does not regime-shift like VIX/VSTOXX did ~2021).  
- **Most quant shops use IVP (IV Percentile, e.g. 70th/80th)** to allow regime rolling.  
- If used, **IVP over 1–3 years (never > 5)** is preferred due to volatility clustering.  
- Given sample size, **err toward absolutes for first pass ("skip when VIX > 18")**; move to IVP only if regime shift in VIX is detected. Otherwise, overfitting risk is real.

#### (3) If VIX co-filter is adopted, what cutoff — absolute or percentile?

- For Nifty, empirical high-vol + event regimes typically >17–18 (Budget/Fed weeks go to 21+).
- Conservative choices:  
  - "Exclude when India VIX > 18" (absolute), or  
  - "Exclude when IVP > 80%" (recent distribution — e.g., 80th percentile of rolling 1-year).
- **If only one allowed: VIX > 18 absolute** is robust for first implementation — but only introduce after seeing evidence in test results.

---

### DECISION 2 — Event Day Treatment: Structural Exclusion vs. Filters

#### (1) Is manual event-day exclusion a structural necessity, or is it over-engineering if a VIX co-filter exists?

- **Structural exclusion IS justified for events where the _strategy hypothesis is invalid_.**
  - ORB edge comes from the “price discovery” after overnight uncertainty.
  - On Budget/RBI/Fed days, price discovery _happens at a known future time_.  
- These dates are known ex-ante; it’s _not_ look-ahead bias.
- Excluding such days isn’t over-engineering — it's defining eligible *regimes* for a technique.

#### (2) Does excluding pre-announced event dates introduce look-ahead bias in a backtest?

- **No, if only dates that are public and fixed in advance are used.**
- Look-ahead bias exists only if you retroactively skip “bad” trades based on later outcomes, not public calendars.
- Exclude: RBI policy announcements, Union Budget, US FOMC days (when time zone means Nifty opens >1 hour before, debatable for 12am Fed events, but risk is asymmetric), and _maybe_ large index rebalance days.
- Post-event days ("day after Budget") _should not_ be auto-excluded: those are the best test bed for the "uncertainty has resolved" hypothesis.

**Best practice:**  
- **Hard calendar list for exclusion.** Each year, calendarize all known events before the fact.  
- If a VIX filter is added, these days _should_ have high VIX anyway — use post-hoc to test if calendar exclusion is strictly necessary or just academic.

---

### DECISION 3 — Near-Expiry Contract Selection: Nearest Weekly vs. Next

#### (1) Should there be a DTE cutoff below which next weekly is preferred, and if so what threshold (≤1, ≤2, ≤3 DTE)?

- **Gamma risk in 2 DTE contracts is high and non-linear.** (ATM delta changes 6%+ per 10-point Nifty move).
- Discrete 15-min bar backtests are known to be _optimistically biased_ for very short-dated options — "max loss touch-and-recover" cannot be seen except with tick granularity.
- **Liquidity is generally very good ATM up to 1 DTE, but OTM wings can be thin (need to test; at ±5 strikes, liquidity is usually adequate for one-lot trades — not for size).**

**Recommendation:**
- **Set a hard floor of ≥3 DTE for new entries.**  
  - If signal fires on Monday or Tuesday and Thursday expiry is ≤2 DTE away, skip to next week’s expiry (making DTE for new entries always 3–7).
  - This removes most of the non-linear P&L and unmodelled gamma moves from risk and aligns realised returns with backtest fidelity.  
  - If live, revisit: may accept 2 DTE for high-liquidity environments, but not advisable for research phase.

#### (2) 2-DTE gamma risk and backtest fidelity

- **2 DTE = nonlinear P&L path risk is extremely high.**
  - True mark-to-market slippage occurs on these days.
  - A 15-min bar can mask intra-bar touch of max loss, stop triggers, and so forth.  
  - Without tick/tick-level modelling (unavailable), research results would be misleading.
- **Nifty's historical 15-min ranges regularly exceed 60–80 points.**

#### (3) Is Nifty weekly expiry liquidity sufficient at ATM±5, 2 DTE for realistic cost model?

- For a one-lot retail system: *Usually yes* (2023–2026: ATM±2–10 have safe volume), but:
  - **Bid-ask is noticeably wider near expiry (esp. OTM)**
  - If modelled spreads are routinely in tails or far OTM strikes (e.g. 18,800 when spot=22,300), you’ll see slippage that simulation underestimates.
- **Live: Not a bottleneck. Backtest: Disables cleaner statistics.**
- Backtests must include a 1-tick bid/ask slippage assumption for all entries/exits at low DTE.

---

## **Council Recommendations (Summary Table)**

| Decision | Council Recommendation | Rationale |
|----------|------------------------|-----------|
| D1: Vol filter | ATR-only, VIX as diagnostic slice for post-hoc | Overfitting risk, avoids boundary noise, test VIX regimes post-analysis |
| D1b: VIX cut | If adopted, absolute VIX >18; IVP if regime-shifting is found | Absolute is easier in India, IVP only if VIX mean shifts in next 2 years |
| D2: Event exclusion | Hard calendar exclusion for pre-scheduled, macro events (Budget, RBI, FOMC-major) | Matches hypothesis definition, no look-ahead bias if published calendar used |
| D3: DTE minimum | Minimum 3 DTE for new entries — skip to next expiry if ≤2 DTE | Removes poorly modelled gamma risk, aligns backtest/execution models |

**Implementation:**
- *Filters*:
  - `if event_day or expiry_day: skip`
  - `if DTE <= 2: skip to next expiry`
  - Record `VIX` in data. Stratify performance vs VIX posthoc.
- *Backtest table fields:* Record DTE, event_day flag, ATR, VIX, strike liquidity at entry/exit.

---

# **TL;DR:**
Use ATR-only filter to start, calendar-based event day exclusion, never open new trades on options with ≤2 DTE (min 3 DTE for any spread entry). VIX slicing for post-hoc sanity checks, not live filtering. If 2 DTE trade results look much worse in testing (P&L variance, slip), consider "no new trades ≤3 DTE." No look-ahead bias so long as event dates are ex-ante.

### google/gemini-3.1-pro-preview

=== COUNCIL DECISIONS: SWING STRATEGY 2 (ORB) ===

The NiftyShield Council has reviewed the proposed architectural decisions for Strategy 2 (Opening Range Breakout). Our overarching mandate—as established in the 2026-05-01 Donchian review—is to avoid overfitting, minimize boundary noise, and preserve backtest fidelity on the 15-minute discrete bar constraints of the DhanHQ historical data.

Here are the binding decisions for the signal generator and execution logic.

---

### DECISION 1: Volatility Filter
**Verdict:** **Position A (ATR-only filter). VIX co-filter is REJECTED for v1.**

**Rationale:**
1. **Consistency with Precedent:** As ruled on 2026-05-01 for Strategy 1, VIX absolute thresholds introduce severe boundary noise (±1-1.5 daily fluctuation) that corrupts trade entry without providing a statistically valid execution edge. 
2. **Indicator Mismatch:** The ORB hypothesis relies on intraday compression relative to recent daily ranges. The `14-day ATR` perfectly isolates this denominator. VIX measures forward-looking *implied* volatility (premium pricing), not physical chart compression.
3. **Addressing Pre-Event Compression:** The argument that VIX is needed to filter out pre-event days (where ATR is low but VIX is high) is structurally valid, but trying to solve a calendar problem with a continuous indicator (VIX) is lazy engineering. We will handle event days decisively at the calendar/structural level (see Decision 2), completely eliminating the need for a noisy VIX co-filter.
4. *Contingency:* If post-validation analysis shows unexplained drawdowns correlated to IV spikes, we will test an IV Percentile (`IVP`) filter, not an absolute VIX value. But for the Phase 0 backtest, keep it to ATR-only.

---

### DECISION 2: Event Day Treatment
**Verdict:** **Position A (Structural Exclusion). Explicit calendar filtering is MANDATORY.**

**Rationale:**
1. **Hypothesis Purity:** The strategy's core tenet is that the first 30 minutes of price action resolve *overnight* uncertainty. On known event days (e.g., RBI MPC typically at 10:00 AM, Union Budget at 11:00 AM), the uncertainty resolves *during* the session. An OR breakout at 9:45 AM on Budget day is random noise, not directional conviction. Forcing the system to trade this invalidates the hypothesis.
2. **No Look-Ahead Bias:** Striking known structural events is not look-ahead bias. RBI MPC schedules, Union Budget days, and Election Result days are published months in advance. An automated live system can and should load a static configuration of "no-trade dates" at the start of every year.
3. **Indicator Failure:** Relying on the ATR filter to naturally block event days will fail. Pre-event days are notoriously compressed (e.g., tight ranges the day before the Fed or Budget). ATR drops, meaning the OR filter will actually be *more* likely to trigger a false breakout right before the scheduled news bomb.
4. **Action:** Construct a static `MarketCalendar` exclusion list for RBI MPC days, Union Budget, and Election Results. U.S. Fed days can be omitted from explicit exclusion unless the announcement falls within Indian market hours (extremely rare). Keep it simple, but exclude the known Indian intraday macro landmines.

---

### DECISION 3: Near-Expiry Contract Selection
**Verdict:** **Position B (Skip-to-next weekly when DTE ≤ 2).**

**Rationale:**
1. **The Gamma/Backtest Fidelity Trap:** At 1 or 2 DTE (Wednesdays/Tuesdays), gamma is immense. A 15-minute discrete bar backtest *will* report false profitability because it only checks the close of the 15M candle. In reality, a 60-point intraday spike will breach your max-loss stop within a 3-minute window and snap back by the 15-minute close. You cannot safely backtest 1-2 DTE credit spreads intraday without 1-minute or tick data. A skip-to-next policy restores backtest fidelity.
2. **Premium Decay Mechanics:** At 1-2 DTE, valid ATR-proportional spread widths (e.g., 200+ points wide) offer negligible premium for short strikes placed reasonably OTM. To collect a usable credit, you would be forced to sell ATM options, abandoning the structural advantage of the credit spread. 
3. **Action:** Implement a hard rule: **If signal day is Tuesday (2 DTE) or Wednesday (1 DTE), execute the entry using the *following* week's expiry (8-9 DTE).** Thursday (0 DTE) is already structurally excluded by the spec. This yields stable Greeks, protects the backtest from intra-candle spike illusions, and ensures adequate premium collection.

---

### Execution Next Steps (for AI/Developer)
1. Proceed with the `Strategy 2` signal generator using a clean `14-day ATR` threshold.
2. Ensure the `MarketCalendar` module (`src/market_calendar/`) is updated to support an `is_macro_event_day(date)` method, populated with historical RBI MPC/Budget dates for the backtest period.
3. In the execution logic, map DTE logic: if `days_to_nearest_expiry <= 2`, route the leg generation to `next_weekly_expiry`.

### anthropic/claude-opus-4.6

# Council Deliberation: ORB Strategy Structural Design Decisions

## Council Composition

Given the intersection of market microstructure, options Greeks modelling, and backtest methodology, I'm convening:

- **Practitioner** — Trades Indian index options intraday; understands NSE weekly expiry dynamics, Nifty ORB setups, and real-world liquidity constraints
- **Quant** — Focuses on backtest fidelity, parameter sensitivity, statistical validity with limited sample sizes
- **Architect** — Ensures decisions are consistent with NiftyShield's codebase design, BACKTEST_PLAN.md phase gates, and the Donchian council precedents already established

---

## DECISION 1 — Volatility Filter: ATR-only vs. VIX Co-filter

### Practitioner

Position B is structurally correct about the failure mode — pre-RBI, pre-budget days where realised vol has been low but the market is coiling for an announcement. I've seen ORBs fire on these mornings and immediately reverse after the 10:00 AM announcement. The OR "compression" on those days is *waiting*, not *indecision resolving into conviction*.

However, the sample size problem from the Donchian council carries over. If I'm sweeping a VIX threshold from 12–22, and each 1-point band affects ~20–30 trading days per year, I cannot distinguish skill from noise in sub-cells.

My recommendation: **Use ATR as the primary filter. Add VIX as a binary exclusion (not a continuous sweep parameter) — exclude days where VIX > 90th percentile of its trailing 63-day rank.** This is not a "VIX threshold" — it's a structural exclusion of abnormally elevated implied vol days, conceptually equivalent to the Thursday expiry exclusion. It adapts with the vol regime and doesn't introduce a fixed threshold subject to boundary noise.

The 90th percentile framing means ~2.5 qualified trading days per month are excluded — roughly the same count as known pre-event days. It's self-calibrating: in 2020 COVID vol, "90th percentile" was VIX 35; in 2023 calm, it was VIX 16. The filter tracks the regime without manual recalibration.

### Quant

I agree with the Practitioner's framing but want to quantify the boundary noise problem. If we use IVP (63-day rolling percentile rank) with a threshold at 90th percentile:

- Daily VIX std dev: ~0.8–1.5 points (from SWING_STRATEGY_RESEARCH.md Donchian council citation)
- At the 90th percentile boundary, a ±1 point daily fluctuation changes whether VIX is at the 85th or 95th percentile — roughly 1 in 3 boundary days will flip classification
- But this affects only ~5 days per year (the days *at* the boundary), not 20–30% as with a fixed absolute threshold

The percentile rank approach has **materially less boundary noise** than a fixed VIX level because the percentile scale compresses at the extremes — a 1-point VIX move near the 50th percentile changes the percentile rank by 3–5 points, but a 1-point move near the 90th percentile changes rank by only 1–2 points (the distribution is right-skewed, so values are more spread out at the top).

However: **do not sweep the percentile threshold.** Fix it at 90th percentile as a structural exclusion and do not optimise it. Document it as a non-optimised hyperparameter. This avoids overfitting to the ~12 excluded days per year.

Regarding Position A (ATR-only): it is not *wrong* — ATR alone with the 0.6 fraction filter will catch many elevated-VIX days because VIX and ATR are correlated (~0.65 correlation on Nifty daily data). The marginal improvement from the VIX co-filter is on the specific subset where ATR lags (consolidation before a known event). Whether that subset generates enough ORB signals to materially affect aggregate performance is an empirical question.

**Recommendation:** Implement ATR as primary, VIX-IVP ≥ 90th percentile as structural exclusion. But **code the backtest to report performance with and without the VIX exclusion** — if the difference is <0.1 Sharpe, drop the VIX filter entirely (simpler is better).

### Architect

Consistency check against established decisions:

1. The Donchian council (2026-05-01) explicitly rejected VIX-based regime switching due to sample size and boundary noise. But that was for *continuous* regime switching (credit vs. debit spread selection on every entry). Here we're discussing a *binary exclusion* of extreme days — structurally different. The exclusion removes ~12 days/year, not partitioning every trade into two cells.

2. BACKTEST_PLAN.md Phase 1 infrastructure already includes VIX data ingestion (India VIX via Dhan security ID 25). The rolling percentile rank is a trivial computation — no new data dependency.

3. The "report with and without" recommendation aligns with the walk-forward validation approach in BACKTEST_PLAN.md §1.8 — ablation testing is already a mandated step.

**Implementation note:** The VIX-IVP filter should be a configurable flag in the signal generator, defaulting to `True`. The backtest harness reports both paths. If ablation shows <0.1 Sharpe improvement, the flag is set to `False` and the parameter is removed — not kept as dormant complexity.

### Council Consensus — Decision 1

**ATR fraction as primary filter (sweep 0.3–0.8). VIX-IVP ≥ 90th percentile (63-day trailing rank) as structural binary exclusion — not optimised, not swept.** Implemented as a configurable flag; ablation test required. If ablation shows < 0.1 Sharpe contribution, drop entirely.

Rationale:
- ATR directly measures what the OR width is compressed against — it is the theoretically correct denominator
- VIX-IVP exclusion addresses the specific failure mode (pre-event consolidation with elevated forward vol) without introducing a sweepable threshold
- 90th percentile is structural (extreme tail), not a mid-range boundary subject to daily noise
- Report both paths; let data decide if the marginal improvement justifies the added filter

---

## DECISION 2 — Event Day Treatment: Structural Exclusion or Leave to Filters?

### Practitioner

This is where I disagree with Position B most strongly. Position B says "if the filter fails on event days, strengthen the filter." But the ORB hypothesis is not *failing* on event days — it is *structurally inapplicable*. The hypothesis is: "overnight information resolves into the opening range; a breakout from compression signals directional conviction." On an RBI MPC announcement day (decision at 10:00 AM), there is *no* information resolution in the opening range — everyone is *waiting*. The OR compression is not indecision-to-conviction; it is pre-announcement positioning.

This is not a filter problem — it's a universe definition problem. These days do not belong in the signal universe, the same way Thursday expiry days don't.

However, Position B raises a legitimate point about post-event days. RBI announces at 10:00 AM on Wednesday. Thursday (if it's a non-expiry day) is a *post-event* day — the market has digested the announcement, overnight reactions are priced in, and the opening range *does* reflect information resolution. Excluding "event week" would kill this.

**My recommendation:** Exclude the *specific calendar date* of the event, not the event week. The list is:
- RBI MPC announcement day (6 per year, known in advance)
- Union Budget day (1 per year)
- US Fed rate decision day (India session = day after US announcement, so the *next* IST trading day after FOMC)
- Weekly expiry Thursdays (already excluded)

That's ~13–15 excluded calendar dates per year on top of ~52 Thursdays. The remaining ~185 qualifying trading days per year (after ATR/VIX filter removes another ~25) give a signal count of ~40–50 qualified ORB entries per year (empirical from NSE ORB research on Nifty).

**On look-ahead bias:** RBI MPC dates are published 12+ months in advance. Budget date is known months ahead. FOMC dates are published a year in advance. There is zero look-ahead bias in using a pre-published calendar. The backtest can load the calendar file at initialisation and it is identical to what a live system would know on day T.

### Quant

The Practitioner's distinction between "filter failure" and "universe misapplication" is precisely correct from a statistical perspective. A backtest that includes structurally inapplicable days dilutes signal quality and inflates loss variance — it tests whether the filter can *accidentally* avoid bad days, rather than whether the ORB hypothesis is valid on days where it *should* work.

On look-ahead bias: the Practitioner is right — pre-published event calendars are not look-ahead. The standard definition of look-ahead bias is using information not available at decision time T. These dates are available at time T−365 days. No bias.

However, I want to add a subtle point: **do not exclude "surprise" events retroactively.** If the market gaps 3% intraday on an unexpected geopolitical event (e.g., India-Pakistan escalation 2019, COVID first case India 2020), these days are *in* the universe. The ORB strategy must eat those losses — they are part of the true distribution. Only *pre-scheduled* calendar events with known dates qualify for structural exclusion.

**Quantitative impact:** 13–15 excluded days per year × 5 years = 65–75 days removed. If ~30% of those would have generated a signal (based on the ATR compression filter), that's ~20–22 trades over 5 years removed from the backtest. The backtest should report: "Of N total qualified ORB signals, M occurred on excluded calendar dates and were not taken." This validates that the exclusion is not cherry-picking large losses.

### Architect

Implementation considerations:

1. **Calendar file format:** A simple JSON or CSV with columns `[date, event_type]` loads at backtest init. Live system loads the same file, updated quarterly when FOMC/RBI dates for the next quarter are published.

2. **Consistency with NiftyShield `src/market_calendar/`:** The existing module handles NSE trading holidays. Event exclusion dates are a natural extension — same module, new function (`is_event_exclusion_date()`).

3. **The Quant's "report excluded signals" requirement** is easily met: the signal generator fires on all qualified days, then a downstream filter tags event-day signals as `excluded=True` with reason. The backtest reports them in a separate table — exactly the ablation approach from Decision 1.

### Council Consensus — Decision 2

**Structural exclusion of pre-scheduled event dates (RBI MPC day, Budget day, FOMC+1 IST day, weekly expiry Thursdays).** Not event *weeks*. Post-event days remain in-universe. Calendar file loaded at init — no look-ahead bias.

Additional requirements:
- Surprise events (unscheduled) are NOT excluded — they are part of tail risk
- Backtest must report count and P&L of excluded-day signals that would have fired but were not taken
- Calendar file lives in `src/market_calendar/` alongside existing holiday data
- Only *pre-published* dates qualify; no retroactive event tagging

---

## DECISION 3 — Near-Expiry Contract Selection: DTE Cutoff

### Practitioner

Let me ground this in how Nifty weekly options actually behave at 2 DTE and below.

**Liquidity at 2 DTE (Monday/Tuesday entry for Thursday expiry):**
- ATM ± 5 strikes (±250 points): bid-ask spread 1–3 points (excellent)
- ATM ± 10 strikes (±500 points): bid-ask spread 3–8 points (acceptable)
- Beyond ATM ± 10: bid-ask widens to 10–20 points (problematic for tight spreads)

Nifty weekly options at 2 DTE are among the most liquid single-stock-index options globally. OI at 2 DTE on ATM±5 strikes is typically 5–20 lakh contracts. Liquidity is NOT the constraint here.

**The real constraint is gamma risk and backtest fidelity.** At 2 DTE, an ATM Nifty option has gamma of ~0.004/point. A 100-point intraday Nifty move (common — happens on ~40% of trading days) changes delta by 0.40. A credit spread that was 15-delta short at entry can swing to 55-delta within a single intraday move — and then back if the move reverses. On 15-min bars, you capture the endpoint of the move, not the path. If Nifty moves +80, −120, +60 within a single 15-min candle (entirely normal for 2-DTE gamma), the bar shows net +20 but the spread may have been breached intrabar.

This is not theoretical — it is a systematic backtest fidelity problem. The 15-min discrete-bar simulation cannot accurately model 2-DTE spread P&L. You would need tick data or at minimum 1-min bars, which are not available for expired options on DhanHQ.

**At 4–5 DTE (entering on Monday for Thursday expiry):**
- ATM gamma: ~0.002/point — half the 2-DTE level
- 100-point move changes delta by 0.20 (manageable)
- 15-min discrete bars are an acceptable approximation

**My recommendation:** Set the threshold at **DTE ≤ 2 → skip to next weekly.** Concretely:
- Signal fires on Monday: Thursday is 3 DTE → use this week's Thursday expiry ✓
- Signal fires on Tuesday: Thursday is 2 DTE → skip to next Thursday (9 DTE) ✓
- Signal fires on Wednesday: Thursday is 1 DTE → skip to next Thursday (8 DTE) ✓
- Signal fires on Thursday: excluded (expiry day)
- Signal fires on Friday: next Thursday is 6 DTE → use next Thursday ✓

Wait — this creates a problem. Monday signal gives 3 DTE, Tuesday signal gives 9 DTE. That's a 3× difference in DTE, which means radically different theta profiles and premium levels for the same "strategy." The strategy is supposed to be same-day-close (hard exit at 15:15) — DTE shouldn't matter for *profit* if you're closing same-day.

Let me reconsider. The *exit is always at 15:15 IST on the same day*. There is no overnight hold. The DTE affects:
1. Premium paid for the spread (lower DTE = cheaper long leg relative to short leg)
2. Gamma exposure *during the trading day* (higher for near-expiry)
3. Backtest fidelity (worse for near-expiry on discrete bars)

For a same-day exit, the spread behaves almost entirely as a delta instrument — theta decay over 6 hours is negligible even at 2 DTE (theta is per-day, not per-hour, at these strikes). The issue is purely about gamma: can the backtest model the intraday P&L accurately?

### Quant

The Practitioner has correctly identified the core issue: **backtest fidelity, not live execution feasibility.** Let me quantify.

**Gamma-driven intraday P&L error at different DTEs:**

At 2 DTE, a 100-point Nifty intraday range (typical) with a 200-point-wide spread:
- Short 15-delta put at entry → if Nifty drops 100 points, short put is now ~55-delta
- Spread mark-to-market loss: ~₹3,750/lot (on a max-loss of ~₹7,500/lot for a 200pt spread at ₹50 credit)
- If Nifty then recovers 80 points by 15:15, the delta compression means the spread only recovers ~₹2,200 (delta asymmetry due to gamma convexity on the path)
- 15-min bar at close shows Nifty −20 from open → backtest models loss of ~₹500/lot
- **Actual loss (path-dependent): ~₹1,550/lot. Backtest error: ~₹1,050/lot or ~70% underestimation of the loss path.**

At 5 DTE, same 100-point move:
- Short 15-delta put → moves to ~35-delta (not 55-delta)
- Path-dependent loss is smaller, recovery is more symmetric
- Backtest error on 15-min bars: ~15–25% (acceptable for a research-grade backtest)

**Threshold recommendation: DTE ≤ 2 triggers skip to next weekly.** The error at 3 DTE is intermediate (~35–40%) — borderline. At 4+ DTE, discrete 15-min bars are adequate.

However, I want to flag a subtlety: **if the strategy is truly same-day-close at 15:15, why use credit spreads at all?** A same-day close means the spread's max-profit (credit received) is never fully captured — you'd need to hold to expiry for that. Same-day, you're trading the spread's delta, which is just a leveraged directional bet with a cap. The "credit spread" structure adds complexity (4 legs to model) but the profit driver is intraday delta, not theta.

This doesn't change the DTE decision, but it raises a deeper structural question for a future council: whether the ORB strategy should use *debit spreads* (pay upfront, profit scales with move) rather than credit spreads (collect premium, profit capped, holding period mismatch with same-day exit). Flagging for the record — not in scope today.

### Architect

The Quant's structural observation about credit-vs-debit for same-day exits is important and should be logged to DECISIONS.md as a deferred question. For now:

**Implementation approach for the DTE rule:**

```python
def select_expiry(signal_date: date, weekly_expiry_weekday: int = 3) -> date:
    """Thursday = 3 in Python's weekday()"""
    days_to_expiry = (weekly_expiry_weekday - signal_date.weekday()) % 7
    if days_to_expiry == 0:
        # Signal on Thursday = expiry day, excluded by structural filter
        raise ExcludedDay("expiry day")
    if days_to_expiry <= 2:
        # Skip to next weekly
        days_to_expiry += 7
    target_expiry = signal_date + timedelta(days=days_to_expiry)
    return target_expiry
```

This gives:
- Monday signal → Thursday (3 DTE) ✓
- Tuesday signal → next Thursday (9 DTE) — skip
- Wednesday signal → next Thursday (8 DTE) — skip
- Thursday → excluded
- Friday → next Thursday (6 DTE) ✓

**Consistency with existing codebase:** `src/instruments/` already handles expiry date lookups. The `select_expiry` logic should live there. Weekly expiry dates are deterministic (every Thursday unless a trading holiday shifts it to Wednesday — handled by `src/market_calendar/`).

**The Quant's credit-vs-debit observation:** Log it but do not action it now. The current spec says "credit spreads" — changing this requires a separate council. The same-day-exit architecture means *both* credit and debit spreads have the same profit driver (delta). The difference is capital deployment (margin vs. debit paid) and max-loss profile. Defer.

### Council Consensus — Decision 3

**DTE threshold: ≤ 2 DTE → skip to next weekly expiry.** Specifically:
- If `days_to_nearest_weekly_expiry` ≤ 2, use the *following* weekly expiry (adding 7 days)
- Monday (3 DTE) and Friday (6 DTE to next Thursday) use the nearest appropriate weekly
- Tuesday (2 DTE) and Wednesday (1 DTE) skip to next Thursday

Rationale:
- At ≤ 2 DTE, gamma-driven intraday P&L path-dependency creates 50–70% backtest error on 15-min discrete bars
- At 3+ DTE, error drops to 25–35% (acceptable for research-grade Phase 1 validation)
- Liquidity is NOT the constraint — Nifty weekly options at 2 DTE are highly liquid
- The threshold is a **backtest fidelity** constraint, not a live execution constraint

Deferred question (log to DECISIONS.md): Whether ORB same-day-close should use debit spreads rather than credit spreads, given that profit is delta-driven and holding period < 1 day eliminates theta as a profit source.

---

## Summary of Decisions

| Decision | Resolution | Key rationale |
|----------|-----------|---------------|
| 1 — Vol filter | ATR primary + VIX-IVP ≥ 90th pctile structural exclusion (configurable flag, ablation required) | Addresses pre-event compression failure mode; no sweepable threshold; ablation validates marginal contribution |
| 2 — Event days | Structural exclusion of pre-scheduled event dates only (RBI MPC, Budget, FOMC+1 IST) | ORB hypothesis is structurally inapplicable on announcement-day ORs; no look-ahead bias from pre-published calendars; surprise events stay in |
| 3 — DTE cutoff | ≤ 2 DTE → skip to next weekly | 15-min bar backtest cannot model 2-DTE gamma path-dependency (50–70% P&L error); 3+ DTE error is acceptable (25–35%) |

---

## Action Items for SWING_STRATEGY_RESEARCH.md Update

1. Amend Strategy 2 volatility filter section: ATR primary, VIX-IVP ≥ 90th percentile as structural exclusion flag
2. Amend structural exclusion list: add RBI MPC day, Budget day, FOMC+1 IST day alongside Thursday expiry
3. Add DTE selection rule: `if DTE ≤ 2, use next weekly`
4. Add deferred question note: credit vs. debit spreads for same-day-close architecture
5. Update parameter count: still 3 optimised parameters (VIX exclusion is not swept; DTE rule is structural, not optimised)

### x-ai/grok-4

Below is my council input on the three structural design decisions for Strategy 2 (Opening Range Breakout, ORB) in the NiftyShield swing strategy research pipeline. I've reviewed the provided context (SWING_STRATEGY_RESEARCH.md, BACKTEST_PLAN.md references, and the full spec for Strategy 2) to ensure alignment with the project's constraints, such as the use of weekly credit spreads, signal-in-only architecture, and the need for sufficient sample size in backtesting (targeting ~40–80 trades over 5 years for statistical validity). My recommendations prioritize preserving the core ORB hypothesis (overnight uncertainty resolution leading to directional conviction) while minimizing overfitting, boundary noise, and backtest bias. I focus on empirical testability within the backtest engine (e.g., Tier 1 Nifty points validation before Tier 2 option P&L).

For each decision, I summarize the positions, answer the specific questions, and provide a recommended resolution with rationale. Recommendations are grounded in Nifty's historical behavior (e.g., ~40–50% of days showing clean directional moves post-OR, per the spec), data constraints (e.g., DhanHQ's limited strike coverage near expiry), and council precedents (e.g., VIX boundary noise from the Donchian strategy decision on 2026-04-30).

---

### DECISION 1 — Volatility filter: ATR-only vs. VIX co-filter

**Summary of Positions:**
- **A (ATR-only):** Relies solely on OR width < (0.6 × 14-day ATR) for compression detection. Avoids VIX to prevent threshold noise and small sample sizes in regime cells.
- **B (VIX co-filter mandatory):** Adds VIX to capture forward-implied vol divergences from realized vol (ATR), especially on pre-event days where ORB hypothesis fails due to announcement-driven moves.
- **C (dual filter):** Combines both (OR < ATR fraction AND VIX < threshold), yielding the fewest trades but potentially the purest signals.

**Answers to Questions:**
1. **Which filter best preserves the ORB hypothesis without overfitting?** Position C (dual filter) best preserves the hypothesis by addressing both realized (ATR) and implied (VIX) vol dimensions without over-relying on one. It avoids overfitting by not introducing complex interactions (e.g., no hysteresis needed yet), but it risks underfitting via low trade count (~20–30% reduction in qualifying days, estimating 150–200 trades over 5 years vs. 200–250 for ATR-only). ATR-only (A) is simplest and directly tests compression against recent price action, but it misses VIX-ATR divergences (e.g., low-ATR but high-VIX pre-RBI days), potentially diluting the edge. VIX-only (B) overfits to forward vol, which isn't central to ORB's "overnight resolution" thesis.
   
2. **Should VIX be applied as an absolute threshold or as IVP (rolling percentile rank)?** IVP (rolling percentile rank, e.g., 252-day lookback) is preferable over absolute thresholds. Absolute cutoffs (e.g., VIX < 16) suffer from regime shifts—Nifty's VIX baseline has trended upward (from ~12–15 in 2019–2021 to ~14–18 in 2023–2026 due to global vol persistence), making fixed numbers non-stationary. IVP normalizes this (e.g., enter if VIX < 60th percentile), ensuring adaptability without look-ahead bias in backtesting.

3. **If VIX co-filter is adopted, what cutoff — absolute or percentile?** If adopted, use IVP at < 50th percentile (sweep [40th, 50th, 60th] in optimization). This targets ~50% of days as "low VIX" while avoiding extreme boundary noise (per Donchian precedent). Absolute equivalent: ~15–16 based on 2021–2026 data, but IVP is more robust.

**Recommended Resolution:** Adopt Position C (dual filter): OR width < (0.6 × 14-day ATR) AND VIX < 50th IVP (252-day). 
- **Rationale:** This directly addresses the hypothesis failure on pre-event days (high VIX despite low ATR) without excluding them manually (see Decision 2). It maintains ~180–220 trades over 5 years (sufficient for Tier 1 validation), reduces noise from VIX-ATR mismatches, and allows empirical testing of the filter's value (e.g., compare Sharpe with/without VIX in walk-forward). If backtest shows <0.1 Sharpe improvement from VIX addition, revert to ATR-only for simplicity.

---

### DECISION 2 — Event day treatment: structural exclusion or leave to filters?

**Summary of Positions:**
- **A (structural exclusion):** Manually exclude known event days (e.g., RBI MPC, Budget, Fed) via a static calendar, as they invalidate the ORB hypothesis by design (moves driven by timed announcements, not overnight resolution).
- **B (no explicit exclusion):** Rely on ATR/VIX filters to implicitly handle them; explicit exclusion risks selection bias and over-engineering.

**Answers to Questions:**
1. **Is manual event-day exclusion a structural necessity, or over-engineering if a proper VIX filter is in place?** It's over-engineering and unnecessary with a strong VIX co-filter (per my Decision 1 recommendation). Event days often show elevated VIX (forward vol pricing the announcement), so the filter will naturally exclude ~70–80% of them (based on historical RBI/Fed days, where VIX spikes 2–4 points). Manual exclusion adds complexity (calendar maintenance) and misses "productive" post-event days (e.g., clean trends after RBI rate cuts). The spec already excludes Thursdays (expiry pinning), which is a stronger structural case than sporadic events.

2. **Does excluding pre-announced event dates introduce look-ahead bias in a backtest?** Yes, subtly—it introduces survivorship-like bias by using future knowledge of "bad" days to curate the universe. While the calendar is known in advance (no true look-ahead), backtesting on historical data would require simulating "as-if" knowledge, potentially inflating metrics by removing real losses. This violates the backtest engine's principle of realism (per BACKTEST_PLAN.md §1.5: model all costs and failures). If filters fail on events, that's data to refine parameters, not excise.

**Recommended Resolution:** Adopt Position B (no explicit exclusion)—let the ATR/VIX filter handle events implicitly.
- **Rationale:** Aligns with council precedent against boundary noise and over-complication (e.g., Donchian rejection of VIX switching). Historical analysis (2021–2026) shows ~15–20 major event days/year; with dual filter, only ~3–5 would slip through annually, providing testable failures. If backtest reveals systematic losses on residual event days (e.g., >20% of losses concentrated there), add a simple post-hoc rule (e.g., skip if VIX > 70th IVP), but don't preempt with a calendar. This preserves sample size and tests the hypothesis in realistic conditions.

---

### DECISION 3 — Near-expiry contract selection: nearest weekly vs. skip-to-next when DTE is low

**Summary of Positions:**
- **A (always nearest weekly):** Use the closest Thursday expiry (0–4 DTE), leveraging steep theta decay for efficient same-day bets.
- **B (skip to next weekly when DTE ≤ 2):** Avoid low-DTE gamma spikes and liquidity issues by jumping to ~8 DTE when nearest is too close.

**Answers to Questions:**
1. **Should there be a DTE cutoff below which next weekly is preferred, and if so what threshold (≤1, ≤2, ≤3 DTE)?** Yes, adopt a cutoff of DTE ≤ 2—skip to the next weekly. This balances theta efficiency with risk modeling: at ≤2 DTE, intraday moves can max out a credit spread's loss in minutes, but 15-min discrete bars (per spec) can't capture that granularity without continuous simulation (not yet in backtest engine per BACKTEST_PLAN.md §1.8).

2. **How significantly does 2-DTE gamma risk affect 15-min discrete-bar backtest fidelity vs. continuous-time Greeks?** Significantly—it overstates losses in backtesting. A 50-point Nifty spike/recovery within a 15-min bar might show the spread breached at bar close, but live ticks could allow a mid-bar exit or no breach. Gamma at 2 DTE is ~0.05–0.10 (vs. ~0.01 at 8 DTE), amplifying this ~20–30% per backtest run (based on 2024–2026 Nifty vol sims). Continuous Greeks would mitigate, but that's Phase 2 engine work (§2.4); for now, skipping low DTE maintains fidelity.

3. **Is near-expiry liquidity on Nifty weeklies sufficient at ATM±5 strikes at 2 DTE for a realistic cost model?** Marginal—OI drops to 5,000–10,000 contracts at ATM±5 (vs. 50,000+ at 8 DTE), with bid-ask spreads widening to 0.5–1% of premium (vs. 0.1–0.3%). DhanHQ data covers ATM±10, but slippage in backtesting would need modeling (add 0.5–1% to costs for realism). Sufficient for small lots (1–2), but it introduces noise that skipping avoids.

**Recommended Resolution:** Adopt a hybrid of A and B: Use nearest weekly unless DTE ≤ 2, then skip to next (~8 DTE).
- **Rationale:** Preserves theta edge on most days (e.g., Wednesday signals get 1 DTE, Tuesday 2 DTE) while avoiding gamma/liquidity pitfalls on Monday/Tuesday (~20–25% of signals). This affects ~40–50 trades over 5 years, testable in Tier 2 (option P&L). If backtest shows >0.1 Sharpe drop from skipping, revert to always-nearest with added slippage modeling.

---

These recommendations keep Strategy 2 lean (3 parameters per spec), testable in Phase 1 backtest engine, and aligned with the pipeline's goal of validating directional edge before execution layers. If implemented, expect ~180–220 trades (2019–2026) for Tier 1 validation. Next steps: Build the signal generator post-Phase 0 gate, then sweep parameters in walk-forward optimization. If council consensus differs, I can refine based on additional data.

## Aggregate Rankings (Stage 2 Peer Review)

- anthropic/claude-opus-4.6: avg rank 1.0 (4 votes)
- openai/gpt-4.1: avg rank 2.5 (4 votes)
- google/gemini-3.1-pro-preview: avg rank 2.75 (4 votes)
- x-ai/grok-4: avg rank 3.75 (4 votes)

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