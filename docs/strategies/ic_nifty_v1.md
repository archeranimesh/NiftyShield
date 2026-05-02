# Iron Condor — Nifty 50 v1

| Field                   | Value                                                                        |
|-------------------------|------------------------------------------------------------------------------|
| Name                    | Iron Condor on Nifty 50                                                      |
| Version                 | v1                                                                           |
| Author                  | Animesh Bhadra (archeranimesh)                                               |
| Date                    | 2026-05-02                                                                   |
| Status                  | Specification — Phase 2 (backtest pending)                                   |
| Underlying              | Nifty 50 index (`NSE_INDEX|Nifty 50`, Dhan: security ID `13`, segment `IDX_I`) |
| Instrument              | Nifty 50 monthly options (NSE) — 4 legs: short put + long put + short call + long call |
| Council decision source | `docs/council/2026-05-02_iron-condor-v1-core-design.md`                     |

---

## Purpose

Phase 2 range-premium income strategy, designed to run alongside the CSP. The IC adds
controlled *range-premium* exposure — collecting from both time decay and the bid/ask of
being short gamma on both sides — without materially increasing portfolio crash sensitivity.

**Governing design principle:**

> IC v1 must not become a second short-put strategy. CSP already owns the left-tail premium
> trade. If the IC cannot be entered without breaching portfolio limits, skip the cycle. The
> skip is the risk management.

Like the CSP, the spec is deliberately simple: four legs, a defined exit stack, no
adjustments. Every deviation between paper results and the Phase 2 backtest is attributable
to data quality, cost modelling, or execution slippage — not strategy complexity. Resist the
urge to improve it during Phase 2.

---

## Entry Rule

**What:** Sell one Iron Condor on the Nifty 50 index (1 lot = current NSE lot size — verify
before each cycle; do not assume 65). Structure:

```
Short put spread:  SELL put at target-delta strike   /  BUY put 500 points further OTM
Short call spread: SELL call at target-delta strike  /  BUY call 500 points further OTM
```

Equal-width wings (500 points) on both sides. All four legs are the same monthly expiry.

**When:** The Wednesday after the most recent monthly expiry, provided this Wednesday falls
within the 30–45 DTE window for the *next* monthly expiry. Monthly Nifty options expire on
the **last Tuesday of each calendar month** (verify against NSE lot-size and expiry schedule
before each entry). If the target Wednesday is a market holiday, enter on the next trading
day.

Do not enter if an IC position for the current cycle is already open. One open IC at a time,
always.

**Delta targets (asymmetric — council mandate, 2026-05-02):**

| Mode | Short Put Target Δ | Short Call Target Δ |
|------|-----------------:|------------------:|
| Standalone IC (no CSP open) | ~15Δ | ~10Δ |
| Concurrent with CSP open | ~8–10Δ | ~12–15Δ |

The asymmetry is intentional and council-mandated. Nifty's structural put skew (3–6 IV points
richer at equivalent deltas) means a 15-delta put and a 15-delta call are not the same risk
object. The concurrent-with-CSP deltas shift the put wing farther OTM to avoid doubling the
portfolio's left-tail exposure.

Delta targets are **parameterised inputs** — candidate put values: 10, 12, 15, 18, 20;
candidate call values: 8, 10, 12, 15. Defaults above are for paper v1 and initial backtest.
A regime-adaptive policy (e.g., tighter deltas at low IVR) is reserved for v2 once IVR
ingestion is live.

**Tie-breaker:** If two strikes straddle the target delta, choose the farther OTM strike
(lower absolute delta) on both wings — consistent with CSP v1's rule.

**Portfolio interaction check — mandatory before entry when CSP is open:**

Before entering the IC, verify that the combined book satisfies both of the following:

1. **Combined option delta (lot-equivalent):** −0.05 to +0.25
2. **Combined downside max loss** (CSP stop-loss + IC put-side max loss): ≤ ₹6L (monthly risk budget)

If either limit cannot be satisfied at 1 lot using the concurrent-mode delta targets:
- First attempt: shift IC put wing one strike farther OTM.
- If still failing: **skip the IC cycle**. Log the skip in `TODOS.md` with the combined delta at the time.

Do not sell calls beyond 15Δ merely to achieve combined delta neutrality — that creates
excessive short-call exposure in Nifty's persistent upward-drift regime.

**IVR filter (specified, not yet enforced):** Skip the cycle if IVR < 25 (trailing 252-day
percentile of India VIX). Same threshold as CSP R3. Log India VIX and IVR at every entry
even before enforcement is live, so the data is available for calibration.

**Trend filter (specified, not yet enforced):** Skip entry if Nifty spot is below its
200-DMA. ICs are fragile in persistent bearish trends — downside moves are sharper and faster
than equivalent upside moves, creating asymmetric wing breach probability even with the
asymmetric delta design.

**Event filter (specified, not yet enforced):** Skip the cycle if any of the following falls
inside the trade DTE window: Union Budget, RBI MPC announcement, election-result day. Same
as CSP R4. Enforcement depends on `src/market_calendar/events.yaml` (BACKTEST_PLAN.md task
3.3 — not yet created).

**Minimum credit gate:** Enter only if total net IC credit ≥ 15% of wing width after
estimated round-trip costs. For 500-point-wide wings: minimum acceptable net credit ≈ 75
points (75 × lot-size in INR). If the credit is below this threshold, skip the cycle — a
low-credit IC has poor tail compensation.

**Liquidity gate:** At entry, require bid/ask spread of each of the four legs ≤ 5% of that
leg's mid price. If any leg fails, try the adjacent strike (±50 points) for that wing. If the
structure still fails the liquidity gate, skip the cycle and log in `TODOS.md`.

**Entry time:** 10:00–10:30 AM IST. Allow the first 30 minutes of price discovery to settle
before reading deltas.

**Execution:** Limit order at the combined net credit mid. If unfilled after 5 minutes,
improve the net credit limit by ₹0.25 and resubmit once. If still unfilled, log the skipped
cycle in `TODOS.md` and do not force a fill.

**Record the following at entry (required for `record_paper_trade.py`):** all four strikes,
expiry date, entry delta of each short leg, net credit received, IV of each short leg, India
VIX at entry, IVR at entry (log even before filter enforcement), underlying spot price,
DTE at entry, combined book delta at entry (if CSP is also open).

---

## Exit Rules

Five independent triggers. The **first to fire wins.** Monitor daily via `daily_snapshot.py`
output and the paper tracker.

**1. Profit target:** Close the full IC (all four legs) when the total IC mark-to-market cost
to close has decayed to ≤ 50% of the opening net credit. Example: entered at ₹100 net credit
→ close when the IC can be bought back for ≤ ₹50.

**2. Loss stop:** Close the full IC (all four legs) when the total IC mark-to-market cost to
close reaches ≥ 2.0× the opening net credit. Example: entered at ₹100 net credit → close
when it costs ≥ ₹200 to close.

**3. Delta stop:** Close the full IC if either short leg (short put or short call) reaches an
absolute delta ≥ **0.35**. This is an *exit* trigger, not a roll trigger.

> **Calibration note:** Backtest both 0.30 and 0.35 in Phase 2. Default to 0.35 for paper v1
> because 0.30 tends to over-exit the call side on normal intraday noise. If paper-trade
> analysis shows that 0.30 materially reduces max loss without sacrificing expected premium
> capture, revisit for v2.

**4. Time stop:** Close the full IC at **14 DTE** if none of the above has fired. Do not hold
an IC into the high-gamma period within 2 weeks of expiry.

**5. Expiry rule:** Never hold the IC to expiry in v1. If the time stop has not fired and
expiry is ≤ 2 trading days away, close immediately regardless of P&L.

**No re-entry rule:** After any exit within a cycle — profit target, loss stop, delta stop,
or time stop — do not re-enter an IC in the same expiry cycle. Wait for the next standard
entry Wednesday. This is simpler than the CSP's R5 re-entry rule and is appropriate for v1.

**Exit execution:** Limit at combined mid for the four-leg close. Same discipline as entry.
Slippage on loss-stop exits is higher than on profit-target exits (stressed market conditions
widen spreads and thin depth); account for this in paper P&L recording per the cost model
below.

---

## Adjustment Rule

**None.**

No rolling of breached wing. No rolling of untested wing. No widening. No converting to iron
butterfly. No doubling down. No defensive buying of additional protection.

If the position is under pressure and no exit trigger has fired, hold until a trigger fires.
If the urge to adjust arises, log the reason in `TODOS.md` as a strategy-discipline note —
this is valuable data about behavioural edge in IC trading — then follow the spec.

Adjustments are deferred to IC v2, informed by v1 paper-trade and backtest data. The
decision to add adjustment complexity will require a Calmar-failure evidence base from v1,
not speculation about what might improve performance.

---

## Position Sizing

**Quantity:** 1 lot per wing side = current NSE lot size. Verify against the NSE lot-size
schedule before every entry. As of January 2026, Nifty 50 lot size is **65 units** — this
is not permanent and will change.

**Wing width:** 500 points (equal both sides). The 500-point width is preferred over 300
points for: (1) better OI and bid/ask liquidity at the long protection strikes; (2) more
stable Greeks during the trade's life; (3) reduced relative weight of transaction costs.
Backtest 300-point width as an alternative in Phase 2 (BACKTEST_PLAN.md task 2.3); default
remains 500 unless the backtest shows meaningful Calmar improvement at 300.

**Notional max loss per wing:** Wing width × lot size = 500 × 65 = ₹32,500 per wing, or
₹65,000 total IC max loss if both wings hit max (which cannot happen simultaneously). Actual
max single-wing loss is ₹32,500 minus the net credit received for that wing; full-IC max
loss is ₹32,500 minus total net IC credit.

**Slippage model (4-leg structure — note asymmetry from CSP):**

- Entry (all 4 legs): `slippage = max(₹0.25, 0.5 × bid-ask spread)` per unit per leg.
- Profit-target exit: same as entry slippage.
- Loss-stop exit: `slippage = 1.5 × max(₹0.25, 0.5 × bid-ask spread)` per unit per leg.
  Stressed markets widen spreads on the ITM leg(s); apply the multiplier to the ITM leg(s)
  specifically if their spread is measurably wider.

With 4 legs at ₹0.50 average spread each, round-trip slippage ≈ ₹0.25 × 4 × 65 = ₹65 at
normal conditions. At a stressed spread of ₹3.00 on the breached leg, loss-stop exit
slippage on that leg ≈ ₹2.25 × 65 = ₹146.

**Transaction cost model (per round trip, 4-leg IC):**

| Cost            | Rate                               |
|-----------------|------------------------------------|
| Brokerage       | ₹20 flat per order leg × 4 = ₹80  |
| STT             | 0.1% of sell-side premium (2 legs at entry + 2 legs at exit) |
| Exchange charge | 0.0345% of premium turnover        |
| GST             | 18% on brokerage + exchange charge |
| SEBI fee        | ₹10 per crore of premium turnover  |
| Stamp duty      | 0.003% on buy side                 |

At ₹100 net credit on 65 units (₹6,500 gross credit), total transaction costs are
approximately ₹150–200 per round trip across all 4 legs. This is a significantly higher cost
drag per rupee of credit than a single-leg CSP. Minimum credit gate (≥75 points ≈ ₹4,875/lot)
is sized to ensure costs do not consume the structural edge.

**Hard sizing cap:** Maximum 1 IC position at any time. No overlapping IC cycles. During
Phase 2 paper trading and first 3 months of any live trading, the cap is 1 lot irrespective
of capital availability.

---

## Expected P&L Distribution Prior

These are prior hypotheses to validate against the backtest — not claims of edge. Written
before running Phase 2 backtests so there is a genuine prediction to compare against.

| Metric                          | Prior estimate (indicative, pending Phase 2) |
|---------------------------------|----------------------------------------------|
| Monthly win rate                | 60–70%                                       |
| Average winning month           | +₹4,000–7,000 per lot net                   |
| Average losing month            | −₹8,000–14,000 per lot net                  |
| Expected annual net return      | +8–14% on deployed capital (protection premium) |
| Sharpe (annualised)             | 0.6–1.0                                      |
| Max drawdown (1 lot, worst case)| −₹25,000–32,000 (consecutive full-wing stops) |
| Worst single cycle              | −₹28,000 to −₹32,000 (near max loss on put wing) |

> These priors are not derived from a backtest. They will be replaced with the Phase 2
> walk-forward results (train 2018–2022, test 2023–2026; Calmar ≥ 0.7 OOS gate) once the
> engine is complete.

---

## Regimes Expected to Work In

**Range-bound, moderate-IV (IVR 25–60):** The IC's primary target environment. Both wings
collect theta, neither is threatened by a directional move, and the spread structure caps
max loss cleanly.

**High IV (IVR > 60) with subsequent mean reversion:** Elevated credit on entry; if IV
contracts during the trade window, both wings decay faster than the max-loss cap tightens.

**Mildly bullish drift:** The call wing at 10-delta (standalone) has significant room before
being threatened by Nifty's typical upward drift rate. The put wing collects the put-skew
premium.

---

## Regimes Expected to Fail In

**Sustained downtrend ≥ 5% within the trade window:** Put wing enters delta-stop territory
quickly. The 200-DMA trend filter is intended to reduce entry frequency in these regimes.
The CSP simultaneous exposure means losses compound; the portfolio-aware cap is the primary
guard.

**Rapid IV expansion after entry:** Both wings become more expensive to close; the loss-stop
mark trigger (2× credit) fires if IV expansion is large enough even without a large
directional move.

**Trending breakouts in either direction:** Defined-risk ICs have limited ability to profit
when the underlying makes a sustained directional move. The trend filter (below 200-DMA →
skip) catches the put-side risk; the call wing has less structural protection if a rapid
rally occurs after entry.

**Low IV at entry (IVR < 25):** Net credit is structurally thin; costs consume the margin.
IVR filter mandates skip.

**Concurrent with CSP when combined delta limits are breached:** If CSP is open and the IC's
put delta cannot be set to 8–10Δ without breaching the combined −0.05 to +0.25 delta cap,
the cycle must be skipped. A structurally overcrowded short-put book is the primary risk mode
for the combined strategy.

---

## Kill Criteria

These conditions trigger an **immediate pause** on the IC strategy — no new entries. The
existing open position (if any) is managed to completion under the standard exit rules. Within
30 days of triggering, review and decide: resume, modify spec → v2, or retire.

1. **Trailing 6-month realised P&L < 0** (across all completed IC cycles in the trailing
   180 days).

2. **Maximum drawdown > 10%** of IC deployed capital across all cycles in any rolling
   3-month window. At ~₹32,500 wing max loss × 2 possible wings = ₹65,000 maximum IC
   exposure, this equates to approximately ₹6,500 cumulative loss.

3. **Rolling 3-month Z-score |Z| > 2.0 for 4 consecutive weeks** relative to the Phase 2
   backtest distribution — strategy behaviour has structurally diverged from the backtested
   model.

4. **Three consecutive execution errors** — wrong-side fill, missed exit, leg misallocation.
   Each error logged in `TODOS.md` with root cause before count resets.

5. **Portfolio delta cap breached in a live session** — if combined CSP + IC book crosses
   −0.40 net delta on any single day, pause IC entries and review combined positioning
   before next cycle.

---

## Variance Threshold for Live Deployment

Before any Phase 2 live deployment is authorised, the following must hold:

**Condition:** Monthly P&L distribution from paper trading must satisfy |Z| ≤ 1.5 relative
to the Phase 2 backtest distribution (V1 variant), measured over the paper-trade window.

**Minimum paper-trade duration:** **6 full monthly expiry cycles** with at least one cycle
triggering each of: profit target, loss stop, delta stop. This minimum is in addition to any
CSP paper cycles — the IC paper log must be independently sufficient.

**Walk-forward gate:** Phase 2 backtest must achieve Calmar ≥ 0.7 on the out-of-sample
window (2023–2026 test set, trained on 2018–2022) before paper trading begins.

**Z-score formula:** `Z = (paper_mean − backtest_mean) / backtest_std`

**Fail path:** If Z fails after 6 cycles, audit: (1) cost model completeness for 4-leg
structure, (2) slippage assumption vs actual paper fills, (3) entry/exit rule divergence,
(4) delta-calculation method mismatch (Black '76 backtest vs live Upstox/Dhan Greeks). Fix,
re-run Phase 2 engine, re-evaluate.

---

## Backtest Results

*Section to be populated after Phase 2 tasks are complete.*

| Field                     | V1 (standalone) | V1 (concurrent with CSP) |
|---------------------------|-----------------|--------------------------|
| Run ID                    | TBD             | TBD                      |
| Backtest window           | TBD             | TBD                      |
| Net annualised return     | TBD             | TBD                      |
| Sharpe                    | TBD             | TBD                      |
| Calmar (OOS)              | TBD             | TBD                      |
| Max drawdown (depth)      | TBD             | TBD                      |
| Max drawdown (duration)   | TBD             | TBD                      |
| Monthly win rate          | TBD             | TBD                      |
| Worst cycle               | TBD             | TBD                      |
| % cycles delta-stopped    | TBD             | TBD                      |
| Git SHA                   | TBD             | TBD                      |

---

## Variance Check Results

*Section to be populated after paper trading completes the required cycles.*

| Field                        | Value |
|------------------------------|-------|
| Paper-trade window           | TBD   |
| Paper mean monthly return    | TBD   |
| Backtest mean (same window)  | TBD   |
| Bias adjustment applied      | TBD   |
| Z-score (bias-adjusted)      | TBD   |
| Pass / Fail                  | TBD   |
| Decision                     | TBD   |

---

## Open Questions for v2

These are not blockers for v1. Log here; revisit when designing v2 after sufficient
paper-trade and backtest data.

- Is 0.35 the optimal delta-stop threshold, or does the backtest show that 0.30 provides
  materially better Calmar without over-triggering on the call side? Phase 2 engine must
  backtest both explicitly.

- Should the 500-point wing width be adaptive (e.g., ATR-proportional like the Donchian
  strategy) rather than fixed? Council noted this as a v1 simplification — test after v1
  Calmar gate is cleared.

- Do intra-trade rolls become necessary if the backtest Calmar fails at 0.7? The council
  ruling is: if Calmar fails, tighten entry filters first (higher IVR threshold, stricter
  200-DMA rule). Add roll complexity only if tightened filters still fail.

- Is the 14 DTE time stop optimal, or would 21 days (like CSP) capture more theta while
  remaining within acceptable gamma risk? The IC's two-sided gamma exposure makes the earlier
  exit reasonable in v1; calibrate from backtest exit-type P&L breakdown.

- Should the minimum credit gate (≥15% of wing width) be parameterised for different IV
  regimes? A single threshold may be too permissive in low-IV and too restrictive in high-IV.

- Does re-entry (after profit-target exit, analogous to CSP R5) add meaningful EV for the
  IC? Deferred to v2; requires v1 paper-trade data to evaluate without overfitting.
