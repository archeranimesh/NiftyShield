# Council Question 9 — Gamma-Acceleration + BS Mispricing Option Buying Strategy: Signal Hierarchy and Forward Test Protocol for Near-Expiry Premium Explosion Events

## Why This Is Council-Worthy

1. **Load-bearing and costly to reverse.** The signal hierarchy — which Greek leads, which
   confirms, what threshold triggers entry — is the strategy specification. Getting it wrong
   means the forward test collects data against the wrong signal, and six months of option
   chain storage produces an uninterpretable dataset. The data collection schema must be
   designed against the correct causal model before the first snapshot is taken. Reversing
   this after the forward test is underway means discarding the collected data.

2. **Two defensible signal hierarchies with materially different outcomes.** The original
   hypothesis is Vega + Gamma simultaneous spike + OI divergence → buy. The reframed
   hypothesis (argued below) is Gamma acceleration primary + BS mispricing confirmation +
   Vega as regime filter only + OI velocity as flow confirmation. These produce different
   entry frequencies, different false positive rates, different data schemas, and different
   break-even win rates. The original framing enters on IV expansion; the reframed framing
   enters on convexity inflection. Near 0–2 DTE these are not the same signal.

3. **Spans multiple disciplines simultaneously.** Options microstructure (Gamma convexity
   near expiry vs. Vega term structure), statistical signal design (threshold setting in the
   presence of wide bid-ask on sub-₹5 options), NSE market structure (retail "hero zero"
   flow + institutional positioning behaviour near expiry), Black '76 smile calibration
   (already council-resolved: quadratic smile + stepped repo), and forward test methodology
   (minimum sample size at low event frequency, schema design for hindsight reconstruction).
   No single domain resolves the tradeoff; all five must be satisfied simultaneously.

---

## Hypothesis Being Submitted for Validation or Refutation

**Observed phenomenon:** Near-expiry Nifty weekly options — primarily in the current expiry
week (0–3 DTE) — occasionally exhibit rapid premium expansion of the order of 20× or more
(e.g., ₹1 → ₹20) within a single session or sub-session window. The retail market refers
to these as "hero zero" trades; the same strikes are also the subject of expiry-day
institutional positioning strategies documented in public market analysis (Jane Street-style
expiry-day mechanics on NSE).

**Operator's original hypothesis:** These events are detectable in advance via:
- Simultaneous Vega + Gamma spike on the option at that strike
- OI divergence (rapid OI buildup on the strike in question)
- Market premium diverging from Black '76 + quadratic smile theoretical price

**Reframing submitted for council validation or refutation:**

Near expiry (0–2 DTE), Gamma and Vega move in *opposite directions*:
- Gamma peaks as DTE → 0 for near-ATM options (convexity is maximum)
- Vega approaches zero as DTE → 0 (there is almost no time value left for IV to act on)

A 1→20 premium move on a ₹1 option near expiry is structurally a **Gamma event**: the
underlying moves toward the strike, delta goes from ~0.03–0.05 to ~0.40–0.50, and the
option premium follows the convexity of the payoff function. This does NOT require IV to
move. To produce a 20× premium expansion from pure Vega (IV) alone, you would need IV to go
from ~15% to ~300% — this does not happen on NSE index options.

Therefore the proposed reframed signal hierarchy is:

| Rank | Signal | Role | Rationale |
|------|--------|------|-----------|
| 1 | Gamma acceleration (∂Γ/∂t or dΓ/dS — "color" / "speed") | Primary entry trigger | Directly predicts convexity inflection — identifies strikes where a small underlying move causes disproportionate premium expansion |
| 2 | BS mispricing (market premium < Black '76 theoretical premium) | Entry confirmation | If the market is underpricing the option relative to its theoretical value at current IV + Gamma, the risk/reward improves. Uses the established Black '76 + quadratic smile + stepped repo pricer. |
| 3 | OI velocity (rate of OI change at the strike, not absolute OI) | Flow confirmation | Rapid OI buildup = informed or institutional positioning; high OI + acceleration → market maker forced hedging if strike becomes ATM |
| 4 | Vega / IV percentile at the strike | Regime filter (exclusion, not entry) | Avoid entering when IV at the strike is already at the floor of its historical range — even a correct directional Gamma call yields minimal premium expansion if there is no IV to re-expand |

**The council is asked to validate or refute this reframing.** If the original hypothesis
(Vega primary) is defensible in a specific sub-regime (e.g., 2–3 DTE remaining with an
event catalyst), the council should specify that sub-regime explicitly with the conditions
under which Vega overtakes Gamma as the leading signal.

---

## Background Context

**Current infrastructure:**
- Black '76 + quadratic smile + stepped repo rate pricer: established (council decision 2026-04-30)
- Slippage model: absolute INR, VIX-regime-aware, OI liquidity multiplier (council decision 2026-04-30)
- Live option chain fetch: operational (`src/client/upstox_market.py`, `parse_upstox_option_chain`)
- Option chain snapshot storage: can be activated immediately at 5-minute intervals at low cost
- Greeks populated from 2026-04-25 onwards in `nuvama_intraday_snapshots`

**Strategy parameters confirmed by operator:**
- Underlying: Nifty 50 index weekly options, current expiry week (0–3 DTE)
- Instrument: calls or puts (council to recommend directional bias or both)
- R:R: fixed 1:5 (risk 1× entry premium, target 5× entry premium)
- Win rate expectation: low (20–35%?), compensated by asymmetric payoff — the rare 20× move
  pays for many small losers
- Phase gate: data collection starts Phase 0 (now); forward test design + execution is Phase 3
- The strategy is an option BUYER, not a seller — this is a long-premium, long-Gamma position

**Why forward test before backtest:**
Historical option chain data with tick-level Greeks at 0–2 DTE is not available in the
current data pipeline. The backtest engine (Phase 1) reconstructs IV via Black '76 smile but
does not have the intraday Greek snapshots needed to replay the Gamma acceleration signal.
The forward test builds that dataset from scratch while the signal design is validated in
real time. The backtest calibration comes after ≥6 months of forward test data exists.

---

## Four Questions for the Council

### Question 1 — Signal Hierarchy: Is the Vega-to-Gamma Reframing Correct?

The operator's original hypothesis attributes the premium explosion to Vega + Gamma
simultaneously spiking. The reframed hypothesis argues Vega is irrelevant near expiry (0–2
DTE) and the event is purely a Gamma convexity phenomenon.

**Specific questions:**

(a) Is the reframing theoretically correct as stated? Under what conditions, if any, does
Vega become a leading signal rather than a lagging or irrelevant one near expiry? Candidate
conditions: (i) the option has 2–3 DTE and an event catalyst (RBI policy, Budget day,
macro print) arrives unexpectedly — IV re-expansion is possible if IV was suppressed before
the event; (ii) the option chain is on a monthly expiry (not weekly) at 1–2 DTE, where
the strike is farther OTM and Vega has more time value to act on; (iii) a sudden market-wide
IV spike (circuit-breaker conditions, panic gap-down) where VIX moves 5+ points intraday.
Under which of these, if any, should Vega be promoted to primary or co-primary?

(b) What is the correct mathematical measure of "Gamma acceleration" for this purpose? Three
candidates: (i) dΓ/dt ("color") — the rate at which Gamma is increasing as time passes,
directly measures the Gamma blowup near expiry; (ii) dΓ/dS ("speed") — the rate at which
Gamma changes with the underlying price, relevant when identifying which strikes will exhibit
the most convexity for a given underlying move; (iii) Gamma/premium ratio — a normalised
measure of convexity relative to cost, which directly captures the "bang per rupee" of a
given strike. Which is the most practically computable signal from a 5-minute option chain
snapshot? Which has the strongest predictive relationship to the ₹1→₹20 class events?

(c) The Jane Street-style expiry mechanics documented in public NSE analysis involve
institutional actors building large positions at specific strikes and then exerting pressure
on the underlying near expiry. Does this flow behaviour create a detectable pattern in OI
velocity before the premium explosion, or is the OI buildup a lagging indicator (it appears
after the move, as retail and hedgers respond)? Is OI velocity a genuine *anticipatory*
signal here or a confirming/coincident one?

---

### Question 2 — Mispricing Threshold: What Constitutes a Real Signal vs. Bid-Ask Noise?

The established Black '76 + quadratic smile pricer produces a theoretical premium for every
strike at the current futures price, IV smile, and time-to-expiry. The operator wants to
use divergence between this theoretical premium and the market premium as a buy signal.

**The structural problem:** A ₹1 Nifty option near expiry has a typical bid-ask of ₹0.50
(bid) / ₹1.50 (ask) — the spread is 100% of the midpoint. The theoretical premium computed
at the midpoint may fall anywhere within this spread and still represent no mispricing
whatsoever. Additionally, the quadratic smile fit is calibrated on liquid strikes; at the
OTM extremes (where ₹1 options live), the smile extrapolation degrades.

**Specific questions:**

(a) Should mispricing be computed against the bid, the ask, or the midpoint? For a buy
signal, the operator pays the ask. If market ask < theoretical premium, that is the buy
signal (the option is cheap at the ask relative to model). Is this the correct direction,
or is the more useful signal the inverse: market ask is ABOVE theoretical but Gamma
acceleration predicts the theoretical will increase rapidly (the option will become more
fairly priced as the underlying moves)?

(b) What is the minimum absolute INR divergence (ask < theoretical) that is statistically
distinguishable from smile-fit calibration noise and bid-ask spread noise? Given a ₹1 option
with ask ₹1.20 and a theoretical value of ₹1.50, the divergence is ₹0.30 — but the smile
fit error on an extreme OTM strike could itself be ±₹0.30. What is a reasonable minimum
divergence threshold? Express this as an absolute INR value AND as a multiple of the
estimated smile-fit uncertainty at the target delta range.

(c) Is the BS mispricing signal most useful as a primary signal or as a filter? Specifically:
should the operator enter any option where ask < theoretical by more than threshold X, OR
should the operator require that Gamma acceleration has already triggered and *then* use
BS underpricing as a quality filter to rank which OTM option to buy? The second framing
avoids buying options that are "cheap for a reason" (deeply illiquid, no real premium
catalyst expected).

---

### Question 3 — OI Signal Construction and Causal Link

**Three OI signal candidates, evaluated against the ₹1→₹20 premium explosion thesis:**

(a) **Absolute OI concentration** — a strike with very high absolute OI has more market
participants committed at that level. If the underlying moves toward that strike, the hedging
activity required to maintain delta-neutral positions is larger, potentially amplifying the
move (self-reinforcing gamma squeeze). This is a slow-changing, structural signal — it
identifies "wall" strikes but not the timing of a move.

(b) **OI velocity (Δ OI over a 15–30 minute window)** — rapid OI buildup at a strike,
especially within the last 30–60 minutes of trading, may indicate institutional positioning
ahead of an expiry pin/move attempt. This is a fast signal — detects positioning as it
occurs. The causal story: informed actors accumulate at the target strike, then push the
underlying, causing the premium to explode. The OI buildup is both the cause (the weight
of positions creates gamma squeeze conditions) and an early warning of intent.

(c) **Strike-level PCR (put/call OI ratio at the specific strike, not index-level PCR)** —
a high put/call OI ratio at a call strike (or low PCR at a put strike) indicates imbalanced
open interest that creates forced hedging asymmetry if the underlying moves through. This is
a structural positioning signal, not a timing signal.

**Questions for the council:**

(i) Which of the three has the strongest *causal* (not merely correlational) link to the
rapid premium expansion mechanism in near-expiry Nifty options? Is there a combined signal
(e.g., "OI velocity > threshold AND absolute OI > percentile N") that reduces false positives
without significantly reducing event detection rate?

(ii) Is OI velocity from a 5-minute option chain snapshot a reliable signal, or is the
5-minute OI change too noisy to be actionable? What is the appropriate lookback window for
OI velocity in near-expiry (0–2 DTE) conditions where OI changes can occur due to position
closeouts as well as new initiations?

(iii) Should the OI signal be directional (i.e., call-side OI velocity signals a call buy,
put-side OI velocity signals a put buy)? Or is a large OI move on *either* side a signal of
underlying volatility regardless of direction?

---

### Question 4 — Break-Even Win Rate, Forward Test Sample Size, and Data Schema

**Break-even arithmetic (operator's baseline):**

Given 1:5 R:R, a strategy breaks even at 1/(1+5) = 16.7% win rate assuming zero transaction
costs. But this ignores bid-ask slippage:

- Entry cost on a ₹1 option: pay ask ₹1.20–1.50. Effective cost = ₹1.20–1.50 per unit.
- Exit on a winner (₹1 → ₹5 target at 5×): bid on ₹5 option near expiry ≈ ₹4.00–4.50.
  Effective exit = ₹4.00. Net realised gain on a "winner": ₹4.00 – ₹1.40 = ₹2.60 on a
  ₹1.40 investment. Actual R:R achieved ≈ 1:1.86, not 1:5.
- Exit on a loser: full loss = ₹1.40 (buy at ask, expire worthless).
- Break-even win rate at realistic R:R of 1:1.86 ≈ 35%, not 16.7%.

**Questions:**

(a) Is this bid-ask reality the dominant reason option buying strategies on near-expiry OTM
Nifty options are structurally difficult to make profitable? Or are there execution strategies
(limit order only, entry at or below mid, exit as underlying approaches strike) that recover
most of the bid-ask drag and restore the theoretical 1:5 R:R in practice?

(b) Given an estimated event frequency of 2–5 qualifying signals per expiry cycle (weekly),
and an expected win rate of 20–35%, how many observed trades are needed to reach 95%
confidence that the strategy has positive EV rather than being within the variance of random
option buying? Provide a sample size estimate assuming a two-sided binomial test with null
hypothesis = 35% win rate (break-even) and alternative = 45% win rate (genuinely positive EV).

(c) **Data schema for forward test:** The option chain can be snapshot at 5-minute intervals
from the existing Upstox client. What is the minimum per-snapshot schema required to
reconstruct the Gamma acceleration + BS mispricing + OI velocity signals in hindsight without
requiring re-download? Required fields at minimum: strike, option_type (CE/PE), bid, ask,
last_traded_price, open_interest, delta, gamma, vega, theta, iv, theoretical_price (computed
at snapshot time by Black '76 + smile), underlying_futures_price, timestamp_utc, expiry_date,
dte. Are there additional fields that are cheap to capture now but expensive to reconstruct
later (e.g., total_bid_qty, total_ask_qty for order book imbalance)?

(d) At what minimum snapshot frequency is the Gamma acceleration signal computable with
acceptable noise? 5-minute intervals capture ~75 snapshots in a trading day but may miss
sub-5-minute Gamma inflection events. 1-minute intervals capture ~375 snapshots but increase
storage and API call rate. Given Upstox's 3 API calls per 5-minute rate limit for the
Analytics token, what is the practical resolution trade-off?

---

## Command

```bash
python scripts/ask_council.py \
    --topic gamma-acceleration-mispricing-option-buying \
    --template strategy_parameters \
    --context docs/strategies/csp_nifty_v1.md \
    --context BACKTEST_PLAN.md \
    --context MISSION.md \
    --question "This question validates or refutes a reframed hypothesis for a near-expiry Nifty options buying strategy targeting rapid premium expansion events (the '1 to 20' class: options that go from ₹1 to ₹20+ in a single session). The operator's original hypothesis attributes these events to simultaneous Vega + Gamma spikes plus OI divergence. The reframed hypothesis, submitted here for council validation or refutation, is that near 0-2 DTE, Gamma is the correct primary signal and Vega is only a regime filter, because: (1) near expiry, Gamma peaks while Vega approaches zero — Vega has almost nothing to act on when time value has decayed; (2) a 20x premium move from pure IV expansion requires IV to go from 15% to 300% which does not happen on NSE index options; (3) the causal mechanism is a Gamma convexity event — the underlying moves toward the strike and the option's delta goes from 0.03 to 0.45, driving the premium explosion. The reframed signal hierarchy is: PRIMARY = Gamma acceleration (color/speed — rate of Gamma change vs time or price), CONFIRMATION = BS mispricing (market ask < Black '76 + quadratic smile theoretical premium by a meaningful threshold), FLOW SIGNAL = OI velocity (rate of OI change at the strike over 15-30 min), REGIME FILTER = Vega/IV percentile (exclude entries when IV is already at its floor). The established Black '76 + quadratic smile + stepped repo pricer (council decision 2026-04-30) is the theoretical pricer. Exit is fixed 1:5 R:R. Win rate expectation: low (20-35%), compensated by asymmetric payoff. Data collection starts now (Phase 0); forward test design + execution is Phase 3. FOUR QUESTIONS: (1) SIGNAL HIERARCHY VALIDATION: Is the reframing correct that Vega is irrelevant at 0-2 DTE and Gamma acceleration is the only meaningful entry signal? Under what specific conditions (event catalysts, 2-3 DTE monthly expiry, VIX circuit conditions) does Vega re-emerge as a primary or co-primary signal? What is the correct mathematical measure of Gamma acceleration for a 5-minute snapshot — color (dGamma/dt), speed (dGamma/dS), or Gamma/premium ratio (convexity per rupee of cost)? Is OI velocity an anticipatory signal or a coincident/lagging one relative to the premium explosion? (2) MISPRICING THRESHOLD: For a buy signal using ask < Black '76 theoretical, what is the minimum absolute INR divergence that is statistically distinguishable from smile-fit calibration noise and bid-ask spread noise on a sub-₹5 option? Should mispricing be used as the primary signal or as a quality filter applied after Gamma acceleration has already triggered? On extreme OTM strikes where the quadratic smile extrapolation degrades, is the BS theoretical price reliable enough to serve as a mispricing signal at all, or should it be replaced with a simpler measure (e.g., IV percentile rank at the strike vs its own 20-day history)? (3) OI SIGNAL CONSTRUCTION: Of three candidates — absolute OI concentration (wall strike detection), OI velocity (rapid buildup in 15-30 min = positioning), strike-level PCR (put-call OI ratio imbalance at the specific strike) — which has the strongest causal link to the near-expiry premium explosion mechanism? Is there a combined signal that reduces false positives? Is 5-minute OI delta too noisy for OI velocity, and what lookback window handles the mix of new position opens vs expiry-driven closeouts near 0 DTE? Should the OI signal be directional (call-side OI velocity signals call buy) or direction-agnostic (any large OI move signals underlying volatility)? (4) FORWARD TEST VIABILITY: At 1:5 theoretical R:R, slippage on a ₹1 option (entry at ask ₹1.40, exit at bid ₹4.00) reduces realised R:R to approximately 1:1.86, raising the break-even win rate from 16.7% to ~35%. Is execution via limit orders (entry at mid or below) a practical solution on NSE near-expiry options, or does illiquidity at OTM strikes make limit-only execution structurally unreliable (orders simply do not fill before the move is over)? Given 2-5 qualifying signals per expiry cycle and an expected 20-35% win rate, what is the minimum forward test window (number of observed trades) for 95% confidence in positive EV vs a binomial null at break-even? For the data schema: beyond the obvious fields (strike, bid, ask, OI, delta, gamma, vega, iv, theoretical_price, futures_price, timestamp, expiry), are there fields that are cheap to capture at snapshot time but impossible to reconstruct later (order book depth, total bid/ask qty) that should be added to the schema now even if not immediately used?"
```

---

## Parameters Summary

| Parameter | Value |
|---|---|
| `--topic` | `gamma-acceleration-mispricing-option-buying` |
| `--template` | `strategy_parameters` |
| `--context` | `docs/strategies/csp_nifty_v1.md`, `BACKTEST_PLAN.md`, `MISSION.md` |
| `--question` | See command above (long-form, all 4 sub-questions included) |

---

## Additional Context Files (load before submitting)

- `docs/strategies/csp_nifty_v1.md` — the existing live paper strategy; ensures Q9's option
  buying strategy is framed as a distinct, non-overlapping strategy, not a hedge or leg of
  the CSP. The council must not conflate the two.
- `BACKTEST_PLAN.md` §Phase 3 — confirms event-driven is the designated third strategy slot;
  data collection for the forward test begins in Phase 0 but the live execution is Phase 3.
- `MISSION.md` — Principle II (backtest before live) and Principle I (one strategy at a
  time): the council answer must be compatible with these constraints. Forward test design
  should not assume simultaneous live trading; it is purely observational initially.
- `docs/council/2026-04-30_iv-reconstruction.md` *(if available)* — the established Black
  '76 + quadratic smile + stepped repo pricer. The council answer for Q9 must assume this
  pricer, not re-litigate IV reconstruction.
- `docs/council/2026-04-30_slippage-model.md` *(if available)* — the established slippage
  model. The break-even win rate analysis in Q4 must use the OI-adjusted slippage model.

---

## What This Decision Unlocks

- **Forward test data collection schema** — defines exactly what the 5-minute option chain
  snapshot must capture. This feeds a new table (e.g., `option_chain_snapshots`) in
  `portfolio.sqlite` or a dedicated Parquet store, schema determined by the council answer.
- **Phase 3 strategy spec** — `docs/strategies/gamma_mispricing_buy_v1.md`. The council
  output drives the Entry, Confirmation, Regime Filter, and Exit sections.
- **Snapshot frequency decision** — whether the existing 5-minute Upstox option chain fetch
  (3 API calls per 5 min, within Analytics token budget) is sufficient or whether a higher
  frequency requires a second API token or Dhan's feed.
- **Council answer on signal hierarchy** gates the Phase 3 entry signal implementation in
  `src/strategy/` (currently empty, planned per BACKTEST_PLAN.md Phase 3).
- **Win rate / sample size answer** sets the minimum observation window before the forward
  test can be declared a pass or fail — a concrete go/no-go gate that does not exist today.

---

## My Working Hypothesis on Signal Ordering (for context when reviewing council output)

**Primary: Gamma/premium ratio (convexity per rupee)**

Of the three Gamma acceleration candidates, Gamma/premium ratio is the most directly
actionable for a buying strategy. It answers the question: "for ₹1 of premium I pay, how
much convexity am I buying?" A strike with Gamma=0.002 and premium=₹1.00 has a Gamma/premium
ratio of 0.002. A strike with Gamma=0.005 and premium=₹0.80 has ratio 0.00625 — the second
is a better buy even though the absolute premium is lower. This normalisation prevents the
signal from simply pointing at the nearest-to-ATM strike, which always has the highest
absolute Gamma but not necessarily the best R:R.

**Confirmation: BS mispricing against the ask, minimum ₹0.40 INR divergence**

On a ₹1 option, a ₹0.40 divergence (ask ₹1.00 < theoretical ₹1.40) represents a
~40% discount. Given smile-fit uncertainty of ±₹0.20–0.30 on extreme OTM strikes, this is
the floor of a meaningful signal. Below ₹0.30 divergence, the signal is indistinguishable
from model noise.

**OI signal: velocity over a 30-minute window, directional**

A 30-minute OI velocity window filters out the noise of intraday position closeouts while
still capturing the 30–60 minute institutional pre-positioning window that would precede a
deliberate expiry-day move. Directional: call-side OI buildup = call buy candidate.

**Vega: exclusion filter at IV percentile < 20th**

Only exclude when IV at the strike is at its 20-session floor. Do not use as an entry
signal. This keeps the filter narrow enough that it does not suppress the signal on most
days, while protecting against days when all premium has already been crushed out.
