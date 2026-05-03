# 3-Track Nifty Long Instrument Comparison v1

| Field     | Value                                                                    |
|-----------|--------------------------------------------------------------------------|
| Name      | 3-Track Nifty Long Instrument Comparison                                 |
| Version   | v1                                                                       |
| Author    | Animesh Bhadra (archeranimesh)                                           |
| Date      | 2026-05-03                                                               |
| Status    | Paper trading — Phase 0.6b                                               |
| Purpose   | Compare three structurally distinct methods of long Nifty exposure with overlay strategies, using a controlled apples-to-apples capital basis |
| Source    | `docs/council/2026-05-02_nifty-long-instrument-comparison-protection.md` Stage 3 |

---

## Purpose and Research Question

This is not a trading strategy in the sense of `csp_nifty_v1.md`. It is a **controlled
comparison framework** with two distinct research questions answered from a single data
collection run.

**Research question 1 — Base instrument comparison (all three tracks, no overlays):**
Given equivalent notional Nifty exposure (NEE), how do the three instruments differ in:
- Delta sensitivity: if Nifty moves 1%, how much does each position move in ₹?
- Margin and capital locked at broker level
- Transaction costs and rolling costs annualised

**Research question 2 — Protection effectiveness (Track A / NiftyBees only):**
When the Nifty index falls, how much protection does each overlay structure deliver, and
what is the long-term running cost of carrying that protection? Protection overlays are
applied to Track A (NiftyBees) as the base because it is the primary capital deployment.
Track B and Track C receive the same overlays for data completeness — the DB can be queried
later to compare (base × overlay) combinations across all three tracks — but the primary
protection analysis is Track A only.

**Three tracks:**

- **Track A** — Long NiftyBees ETF (physical, delivery)
  - Strategy namespace: `paper_track_a`
  - Collateral: cash deployed
- **Track B** — Long Nifty Futures (monthly roll, full notional)
  - Strategy namespace: `paper_track_b`
  - Collateral: SPAN margin (~₹1.5L) + surplus parked in liquid fund (tracked separately)
- **Track C** — Long Nifty via Deep ITM Call (delta ≈ 0.90, monthly expiry)
  - Strategy namespace: `paper_track_c`
  - Collateral: option premium paid upfront (~₹2–3L)

All three tracks run simultaneously for the full comparison window.

---

## Approved Overlay Menu

| Overlay | Track A | Track B | Track C |
|---------|---------|---------|---------|
| Protective Put (buy OTM put, ~8–10% OTM) | ✅ Safe | ✅ Safe (note: Track B + PP ≡ long call — record for completeness) | ✅ Safe (note: Track C + PP ≡ bull call spread) |
| Covered Call (sell OTM call, ~3–5% OTM) | ✅ Safe | 🚫 **BLOCKED** | ✅ Safe (creates diagonal/vertical spread) |
| Collar (PP + Covered Call together) | ✅ Preferred | ✅ Safe (collar only — never standalone covered call) | ✅ Safe |

**Blocked combinations — hard rules, never record:**

- **Track B + standalone Covered Call:** Futures + short call = synthetic short put (unlimited downside). Violates `MISSION.md` Principle I.

This combination is documented in `DECISIONS.md` as permanently blocked per the council ruling.
CSP (Cash-Secured Put) is excluded from this framework entirely — it is tracked as a
standalone strategy in `paper_csp_nifty_v1` and is not an overlay here.

**Redundant but not blocked (record, flag in leg notes):**

- Track C + Protective Put: equivalent to entering a bull call spread directly. Record for completeness; note in `--notes` that it is structurally redundant.
- Track B + Protective Put: equivalent to buying a long call. Record; note redundancy.

---

## Entry Rules

### Phase 1 — Base Leg Entry (Day 1, all three tracks simultaneously)

Enter all three base legs on the same calendar date to ensure identical starting conditions.
Target entry date: first Wednesday after the most recent Nifty monthly expiry within a
30–45 DTE window for the next expiry. If that Wednesday is a market holiday, use the next
trading day. All three must enter on the same day; do not stagger tracks.

**Entry time:** 10:00–10:30 AM IST for all legs.

**Track A — Long NiftyBees ETF:**

Quantity = `floor((lot_size × nifty_spot) / niftybees_ltp)` where lot_size = 65
(1 Nifty lot equivalent, as per NEE definition in Position Sizing).

```bash
python -m scripts.record_paper_trade \
  --strategy paper_track_a \
  --leg base_etf \
  --key "NSE_EQ|INF204KB14I2" \
  --action BUY \
  --qty <computed_qty> \
  --price <niftybees_ltp> \
  --date <entry_date> \
  --notes "Track A base: NEE qty. Nifty spot=<spot>, lot_size=65."
```

**Track B — Long Nifty Futures (1 lot, monthly front contract):**

Record the notional futures position at the current front-month futures price.
Qty = 65 (1 lot). Instrument key: look up the current front-month Nifty futures key
from the BOD instrument file (pattern: `NSE_FO|NIFTY<DDMMMYYYY>FUT`).

```bash
python -m scripts.record_paper_trade \
  --strategy paper_track_b \
  --leg base_futures \
  --key "<front_month_futures_key>" \
  --action BUY \
  --qty 65 \
  --price <futures_price> \
  --date <entry_date> \
  --notes "Track B base: 1 lot Nifty futures. Notional=<65×futures_price>. Surplus capital=<nee_capital - span_margin> parked notionally."
```

**Track C — Long Deep ITM Call (delta ≈ 0.90, monthly expiry):**

Use `find_strike_by_delta.py` to locate the call strike closest to delta = 0.90 (search
range 0.85–0.95). Select the strike whose delta is nearest 0.90; if equidistant between
two strikes, take the one with higher delta (deeper ITM) for consistency. Verify OI ≥ 5,000
contracts and bid/ask spread ≤ ₹5.00 before recording.

```bash
# Step 1: find the strike
python -m scripts.find_strike_by_delta \
  --underlying "NSE_INDEX|Nifty 50" \
  --expiry <monthly_expiry_date> \
  --option-type CE \
  --delta-min 0.85 \
  --delta-max 0.95

# Step 2: record the entry
python -m scripts.record_paper_trade \
  --strategy paper_track_c \
  --leg base_ditm_call \
  --underlying "NSE_INDEX|Nifty 50" \
  --strike <selected_strike> \
  --option-type CE \
  --expiry <monthly_expiry_date> \
  --action BUY \
  --qty 65 \
  --price <mid_price_minus_slippage> \
  --date <entry_date> \
  --notes "Track C base: Deep ITM CE delta=<actual_delta>, strike=<strike>. Target delta 0.90."
```

### Phase 2 — Overlay Entry

Overlays are entered after the three base legs are established. Start with the approved
overlay menu above; blocked combinations are never recorded.

Each overlay is a separate leg within the same strategy namespace:

- Leg role naming: `overlay_pp` (protective put), `overlay_cc` (covered call),
  `overlay_collar_put` / `overlay_collar_call` (collar).
- Collar legs must always be entered together in the same session — never enter the
  covered-call leg of a collar without simultaneously entering the protective put.
- Enter overlays on the same day as the base leg, or at the next entry window if
  liquidity is insufficient on day 1.

### Overlay Expiry Selection (Quarterly vs Yearly vs Monthly)

The objective is cost efficiency — longer DTE means lower annualised theta drag and fewer
rolls. Use the following decision process at each overlay entry:

1. **Query the option chain for three candidate expiries:** next quarterly (Mar/Jun/Sep/Dec),
   next yearly (Jun or Dec far-dated), and next monthly. For each, find the target strike
   (e.g., 8–10% OTM put for protective put; 3–5% OTM call for covered call).

2. **Compute spread quality for each expiry at the target strike:**
   `spread_pct = (ask - bid) / mid × 100`

3. **Prefer quarterly if `spread_pct ≤ 3%`.** Quarterly Nifty options (near-term Mar/Jun/Sep/Dec
   contracts) typically carry OI of 2,000–5,000 contracts on relevant put strikes — sufficient
   to fill 1 lot with manageable slippage.

4. **Prefer yearly if quarterly spread_pct > 3% AND yearly spread_pct ≤ 3%.** Far-dated yearly
   puts (e.g., Dec of next year) can occasionally be tighter than quarterly if there is a
   concentrated institutional hedging flow. Use the data, not the assumption.

5. **Fall back to monthly if both quarterly and yearly spread_pct > 3%.** Log the spread values
   in `--notes` at entry so the liquidity history builds over time.

6. **For collars:** both legs (put and call) must use the same expiry. Apply the gate to
   `max(put_spread_pct, call_spread_pct)` — use the expiry where the worse of the two legs
   still passes the 3% gate. If no single expiry passes for both legs, fall back to monthly
   for the collar and log the reason.

7. **Log at every entry:** expiry chosen, DTE at entry, `spread_pct` for each leg, OI at
   the target strike. This builds the empirical record of liquidity across the expiry curve
   and is the primary data for answering "what is the running cost of protection?"

### Entry Constraints

- Do not enter any overlay on Track B except Protective Put or Collar. The `paper_track_b`
  namespace should be inspected before adding any new leg; if no protective put exists,
  a standalone covered call leg must not be recorded.
- Track C delta must be ≥ 0.85 at entry. If `find_strike_by_delta.py` cannot find a strike
  with delta ≥ 0.85 in the current monthly expiry, use the next quarterly expiry.

---

## Exit Rules

### Monthly Roll — All Tracks

All three tracks roll on the **same day each month**: the Wednesday after the current
monthly Nifty expiry (matching the entry cadence). If that Wednesday is a market holiday,
roll on the next trading day.

**Roll procedure per track:**

1. Record a SELL/BUY-to-close for the expiring leg at LTP (mid price with slippage per
   Position Sizing).
2. Immediately record the new leg (same role, next expiry) at the new entry price.
3. For Track C: re-run `find_strike_by_delta.py` for the new expiry to find the fresh
   delta ≈ 0.90 strike. The strike will differ from the previous cycle.
4. For Track B: roll to the new front-month futures contract.
5. All overlay legs with the same expiry are rolled simultaneously. Overlays on longer
   expiries (e.g., quarterly tail puts) are managed independently.

**Do not defer a roll.** If any roll cannot be executed on the target date (market holiday,
system error), log the reason in `TODOS.md` and execute on the next trading day. Never
carry an expiring short option leg through to settlement.

### Track C — Early Exit Trigger (Delta Decay)

Track C has an additional exit trigger independent of the monthly roll. If the deep ITM
call delta falls below **0.40 for 3 consecutive trading days**, close the position
immediately (buy-to-close) and re-enter at a deeper strike (delta ≈ 0.90 for the current
or next monthly expiry, whichever has ≥ 7 DTE remaining). Log the delta values for all
3 days and the re-entry in `TODOS.md`.

This trigger fires when: (a) Nifty has fallen substantially toward or below the call strike,
or (b) gamma decay has compressed the delta as expiry approaches. Either condition degrades
Track C's ability to serve as a "long Nifty" proxy.

### Track B — Intra-Cycle Exit

No intra-cycle exit rule for the base futures leg. Futures are marked to market daily;
unrealised losses are captured in paper P&L without forcing a close. The only exit is the
monthly roll.

For protective put overlays on Track B: hold to expiry unless the underlying moves
unexpectedly strongly upward (put value ≈ zero and DTE ≤ 5) — in that case close early to
capture residual value; log the decision.

### Framework Exit (End of Comparison)

The comparison runs for a **minimum of 6 complete monthly cycles** across all three tracks
simultaneously. Do not close any track early for comparison purposes; all three must run
the full minimum window. After 6 cycles, review per the Variance Threshold section. The
framework continues beyond 6 cycles if: (a) the variance check gate has not passed, or
(b) no high-VIX event (India VIX > 18) has occurred during the window (require ≥ 1 such
event for the comparison to be credible).

---

## Adjustment Rules

### Track A — No Adjustments

Once the NiftyBees base leg is entered, it is not adjusted intra-cycle. If India VIX
spikes, hold. If NiftyBees price drifts due to tracking error, note in `TODOS.md` but do
not rebalance until the annual reset.

**Annual reset (Track A):** Once per calendar year (January, after expiry), record a SELL
at current NiftyBees LTP to close the old position, then immediately record a fresh BUY at
the new NEE quantity. This keeps the notional equivalent sizing accurate as Nifty drifts.

### Track B — No Intra-Cycle Adjustment

The futures leg carries its full delta exposure throughout the cycle. No stop-losses, no
delta hedging. If the position is materially underwater, hold until roll. The purpose is to
capture the unmanaged futures P&L as the Track B baseline — adjusting it defeats the
comparison.

### Track C — Delta Monitoring (Daily)

Record the deep ITM call's delta at each `paper_snapshot.py` run. If delta falls below
0.65 (warning threshold), flag it in the daily snapshot log. If delta falls below 0.40 for
3 consecutive days, execute the early exit procedure described in Exit Rules.

Delta readings come from the live Upstox option chain. If the option chain is unavailable
on a given day, interpolate from the prior day's delta and document the gap. Do not leave a
Track C position unmonitored for more than 2 consecutive trading days.

### Overlay Adjustments

Overlays are not adjusted intra-cycle except:

- **Collar legs:** If the market rallies sharply past the short call strike of a collar
  (covered call leg is deep ITM), do not roll the short call higher. Hold to expiry. Record
  the outcome; this is data for the comparison.
- **Long-dated overlay rolls:** Quarterly or yearly overlay legs do not expire on the same
  cycle as the base leg. When the base leg rolls monthly, the overlay continues unchanged.
  Only roll an overlay leg when it expires or when its DTE falls below 5. Log the roll
  separately with DTE and remaining extrinsic value at time of roll.

---

## Position Sizing

### Notional Equivalent Exposure (NEE)

All three tracks are sized to **1 Nifty lot equivalent** using NEE as the normalisation
basis. NEE = `nifty_spot × lot_size` = `nifty_spot × 65`.

At Nifty spot ~24,000 (approximate as of mid-2026): NEE ≈ ₹15,60,000.

| Track | Capital deployed | NEE-equivalent basis |
|-------|-----------------|----------------------|
| A | NEE qty × NiftyBees LTP ≈ NEE | Full cash deployed equals notional |
| B | SPAN margin ~₹1.5L + surplus ~₹14.1L notionally tracked | SPAN covers margin; surplus is notional (not actually deployed in paper) |
| C | Option premium paid (~₹2–3L) | Capital at risk = premium; notional exposure = NEE |

**Track B capital note:** In paper trading, Track B only "locks" the SPAN margin. Record the
surplus capital (NEE − SPAN margin) in `--notes` at entry for each cycle. When computing
Return on NEE for cross-track comparison, always divide by the full NEE, not just the
SPAN margin — the notional exposure is identical for all three tracks and that is the correct
denominator.

**Lot size:** 1 lot = 65 units (Nifty 50, effective January 2026). NSE revises lot sizes
periodically — verify before each entry cycle.

### Slippage Model (applies to all legs, all tracks)

| Condition | Slippage per unit |
|-----------|------------------|
| Normal entry / profit exit | `max(₹0.25, 0.50 × bid-ask spread)` |
| Forced exit (stop trigger, expiry day) | `1.5 × max(₹0.25, 0.50 × bid-ask spread)` |
| Track C deep ITM call (wide spreads) | `max(₹0.50, 0.50 × bid-ask spread)` |

Track C typically has wider bid-ask spreads than ATM options. If the spread exceeds ₹10.00,
note it in `TODOS.md` and use the actual mid at fill time (not the tighter normal model).

### Transaction Costs (applied to paper P&L)

Same model as `csp_nifty_v1.md`:

| Cost | Rate |
|------|------|
| Brokerage | ₹20 flat per order leg |
| STT | 0.1% of sell-side premium (options only) |
| Exchange charge | 0.0345% of premium turnover |
| GST | 18% on brokerage + exchange charge |
| SEBI fee | ₹10 per crore of premium turnover |
| Stamp duty | 0.003% on buy side |

For equity (Track A NiftyBees): brokerage ₹20, STT 0.1% on sell-side, exchange 0.00345%,
GST 18% on brokerage + exchange, SEBI fee ₹10/crore. No STT on buy side for delivery.

---

## Daily P&L Report Schema

The daily mark-to-market run (`paper_snapshot.py`) must produce, per track, a structured
output separating base and overlay contributions. This is the mandatory daily reporting
format for this framework:

```
Date: YYYY-MM-DD
Track A (paper_track_a)
  Base (NiftyBees):      +₹X,XXX  Δ +0.92 Θ 0 V +₹YYY
  Overlay (PP):          -₹XXX    Δ -0.08 Θ -₹42 V +₹180
  Overlay (Collar-Call): +₹XXX    Δ -0.05 Θ +₹18 V -₹60
  NET:                   +₹X,XXX  Δ +0.79 Θ -₹24 V +₹120
  Max DD (cycle):        -₹X,XXX  (-X.X% of NEE)
  Return on NEE:         +X.XX%

Track B (paper_track_b)
  Base (Futures):        +₹X,XXX  Δ +1.00 Θ 0 V 0
  Overlay (Collar-Put):  +₹XXX    Δ -0.08 Θ -₹38 V +₹160
  Overlay (Collar-Call): +₹XXX    ...
  NET:                   ...

Track C (paper_track_c)
  Base (Deep ITM CE):    +₹X,XXX  Δ +0.88 Θ -₹55 V +₹90
  Overlay (PP):          -₹XXX    Δ -0.08 Θ -₹38 V +₹160
  Overlay (CC):          +₹XXX    Δ -0.05 Θ +₹18 V -₹60
  NET:                   ...
  Track C delta: 0.88 [OK / WARNING (<0.65) / CRITICAL (<0.40, day N of 3)]
```

**Mandatory daily fields per track:**

- Base P&L, per-overlay P&L, net combined P&L (absolute ₹)
- Net Delta, Net Theta (₹/day), Net Vega (₹ per 1% IV change)
- Cycle max drawdown (peak-to-trough since current entry, as % of NEE)
- Return on NEE (cumulative since cycle entry)

**Track C delta alert:** If Track C delta is < 0.65 (warning) or < 0.40 (critical), flag it
prominently in the snapshot output.

Greeks come from the live Upstox option chain (`parse_upstox_option_chain`). NiftyBees
and Futures legs carry no theta or vega; assign delta = 1.0 (Futures) and delta = NEE/notional
for NiftyBees (≈ 0.92 accounting for typical NiftyBees beta-to-Nifty).

---

## Expected P&L Distribution Prior

These are forward hypotheses for the comparison framework. Written before running any paper
trade; will be replaced by measured distributions after 6+ cycles and Phase 1 backtest.

**All figures per 1-lot per month, at 1 Nifty lot NEE (~₹15.5L).**

| Metric | Track A (ETF) | Track B (Futures) | Track C (Deep ITM Call) |
|--------|--------------|-------------------|------------------------|
| Monthly P&L distribution | Near-identical to Nifty 50 index return | Near-identical to Nifty 50 index return | Slightly lower on up-months (delta < 1.0); slightly better floor on down-months (max loss = premium) |
| Theta drag (base only) | None | None | ~₹55–80/day (extrinsic decay on deep ITM call) |
| Annualised theta drag (Track C base) | — | — | ~₹14,000–21,000/year |
| Capital at risk (per cycle, worst case) | Full NEE (~₹15.5L) | Full notional (unlimited beyond SPAN, but futures are closed at roll) | Option premium only (~₹2–3L) |
| Cross-track tracking error (base only) | Baseline | ~0% vs Nifty 50 (futures tracks perfectly) | Expected 5–10% drift per month due to delta decay; corrected at roll |
| Overlay edge hypothesis | Collar: drawdown reduced ~30–40% at cost of ~15–20% upside cap; PP alone: full downside floor at premium cost; CC alone: income offset vs capped upside | PP converts futures to long call (defined risk, full downside floor); Collar most capital-efficient here | PP creates bull call spread (defined risk, limited gain); CC creates vertical/diagonal spread |

**Key comparison hypothesis:** Track B (Futures) will have the highest raw return per ₹
of capital actually posted (SPAN margin basis), but the lowest return on NEE basis.
Track C will have the lowest absolute downside in a crash (max loss = premium) but ongoing
theta drag that penalises flat or slowly-rising markets. Track A will be the smoothest
equity curve with collars applied, at the cost of capped upside.

The comparison is only meaningful after ≥ 6 cycles including at least one high-VIX event
(India VIX > 18).

---

## Regimes Expected to Work In

**All three tracks benefit from a trending bull market:** All bases capture Nifty upside.
Covered call overlay adds further income; protective put is a mild drag (premium paid for
protection that does not fire). Best environment for the framework overall.

**Track A + Collar in range-bound market:** Collar collects call premium while the put
provides a floor if Nifty drifts lower. The cost-of-carry is the net debit (typically
small when put IV > call IV, which is normal for Nifty's negative skew). The least
expensive protection structure in sideways-low-IV regimes.

**Track A + Protective Put in high-IV entry environments (VIX > 18):** Put premium is
expensive but IV mean-reversion tends to add mark-to-market value to the long put position
even before Nifty moves. The overlay earns on both the vol compression and any downside
move. Track A + PP is the cleanest expression of "buy protection when it is expensive
but justified."

**Track B + Protective Put in crash scenarios:** PP converts the unlimited-downside futures
to a long call profile — defined loss, unlimited upside. While the PP premium is the cost,
it is the only structure among the three that provides both unlimited upside AND a defined
floor. Track A loses the full ETF value below the put strike; Track C is already defined-
risk (premium). This makes Track B + PP the structurally superior crash protection among
the three — but only with the PP in place.

**Track C in high-IV environments (base only):** The deep ITM call's extrinsic value rises
with IV, which temporarily inflates the position's mark-to-market. Delta fidelity can also
improve transiently as the call's strike moves closer to ATM in a downdraft. However, the
theta drag is highest in high-IV environments, making long-dated Track C more favourable
than monthly in these regimes.

---

## Regimes Expected to Fail In

**Sustained Nifty downtrend ≥ 8% in a cycle:**

- Track A: full ETF drawdown; protective overlay essential to avoid large loss.
- Track B: full futures loss unless protective put is in place; without PP, worst performer.
- Track C: capped at premium paid; best natural floor of the three bases.

Covered call overlay will add losses on top of base drawdowns in this regime (short call
gains are offset by the faster-falling base). Protective put and collar are the only
overlays that improve the outcome.

**Sharp IV expansion post-entry:**

- Track C delta decays faster near the strike as Nifty falls, triggering the delta < 0.40
  kill criterion. If IV spikes while Nifty is flat, Track C's extrinsic value balloons —
  beneficial for the long call holder, but confuses the comparison (delta fidelity degrades).
- Track B + Collar: the short call leg of the collar benefits from IV spike (can close for
  profit), but the short call gains on IV while Nifty is falling — creates a complex
  interaction. Log carefully.

**Low-IV flat market (VIX < 12):**

Track C has the worst outcome: theta drag accumulates with no directional move to
compensate. Track A + Collar has the lowest cost structure here (thin premiums on both
legs, but net debit is also small). Track B (futures alone) is neutral; futures carry no
theta. The protective put on any track is pure drag in this regime — this is the regime
where the "running cost of protection" is most visible and most painful.

---

## Kill Criteria

### Per-Track Kill Criteria

**Track C — mandatory early exit (not a "pause", an immediate action):**

1. **Delta < 0.40 for 3 consecutive trading days:** Close the base leg and re-enter at
   delta ≈ 0.90. This is an intra-cycle correction, not a strategy pause.
2. **Premium decay to < ₹0.50 with DTE ≥ 5:** The deep ITM call has lost virtually all
   optionality; carry risk of rapid delta collapse if Nifty drops further. Close and re-enter
   at next expiry.

**Any track — immediate overlay close:**

If an overlay leg creates a net position that, when aggregated across legs, produces
an unhedged short put or short call exposure (e.g., a covered call on Track B entered
without a paired protective put), close the violating leg immediately and log in `TODOS.md`.

### Framework-Level Kill Criteria

These trigger an **immediate pause on new entries for all three tracks**. Existing positions
are managed to completion under the standard exit rules.

1. **Net framework loss > 5% of NEE across all three tracks combined in any rolling
   30-day window.** At NEE ~₹15.5L, this is ~₹77,500 combined loss across the three tracks
   in 30 days. This is an extreme scenario given defined-risk structures on all tracks.

2. **Track B positions have any open uncovered short put exposure at any point.** Immediate
   close of the violating leg AND pause on all Track B new entries pending a review session.
   Rationale: unlimited-downside risk on Track B is a mission violation; zero tolerance.

3. **Data quality failure for ≥ 3 consecutive days on Track C delta:** If the Upstox option
   chain returns no data for the Track C deep ITM call for 3+ consecutive days (and
   `find_strike_by_delta.py` cannot locate the position), pause Track C entries and investigate.

4. **Three consecutive roll failures** (any track): wrong-side fill, missed roll, unintended
   expiry carry-through. Each error logged individually in `TODOS.md` before the count resets.

5. **Framework minimum duration breached by external event:** If a regulatory change blocks
   Nifty futures or options access mid-comparison, pause all tracks, note the cycle count
   completed, and document in `DECISIONS.md` before resuming or closing.

### No "Kill the Framework" Criterion

The comparison framework itself has no kill criterion beyond the 5 above. Even if one track
performs dramatically worse than the others, all three must complete the minimum 6 cycles
for the comparison to be statistically valid. Do not drop a track because it is losing.

---

## Variance Threshold for Live Deployment

This framework is a **research instrument**, not a live-deployment candidate in its own
right. Its output informs which (base × overlay) combination proceeds to a proper strategy
spec and Phase 1 backtest. The "variance threshold" here is therefore a **comparison
conclusion gate**, not a live-trading gate.

### Minimum Duration

**6 complete monthly cycles** across all three tracks simultaneously, with at least one
high-VIX event (India VIX > 18) occurring during the window. Two to three cycles is
insufficient — Nifty's return distribution is skewed; 6 cycles provides the minimum
credible sample to distinguish structural from random performance differences.

### Conclusion Gate Criteria

After 6 cycles, the comparison produces a valid conclusion when **all** of the following hold:

1. **All three tracks completed all 6 cycles** without any framework kill criterion being
   triggered that distorts the comparison (e.g., Track B assignment risk breach).

2. **At least one cycle in each track triggered a loss scenario** (Nifty declined ≥ 3% in
   the cycle). Without a down-month observation, the comparison cannot measure the protective
   overlays' effectiveness.

3. **Per-track, per-overlay P&L attribution is complete** for all 6 cycles — base P&L and
   overlay P&L separately recorded and reconciled against daily snapshot data.

4. **Greeks logged (Delta/Theta/Vega) for ≥ 80% of trading days** across all cycles. Gaps
   of up to 2 consecutive days are acceptable if documented; systematic gaps invalidate the
   Greek attribution.

### Output of the Comparison

At conclusion, produce a summary report covering:

- **Return on NEE** (annualised): all three tracks, with and without overlays.
- **Max drawdown** (depth and duration): all three tracks.
- **Overlay cost/benefit**: cumulative premium paid vs protection delivered per overlay type.
- **Track C delta drift profile**: how often did delta drift below 0.65? How costly was each
  re-entry after a delta-trigger close?
- **Sharpe and Sortino** (annualised, 6-cycle basis — acknowledged to be a very short window).
- **Recommendation**: which (base × overlay) combination proceeds to a standalone strategy
  spec and Phase 1 backtest?

### Z-Score Gate (if comparison output triggers a live strategy)

If the comparison concludes that one combination (e.g., Track A + Collar) is strong enough
to proceed to live trading, that combination must first be spun off into its own strategy
spec (`nifty_<name>_v1.md`) and complete its own Phase 0 paper trading (minimum 6 additional
cycles) before Phase 2 live deployment. This framework's 6 cycles **do not substitute** for
the standalone paper-trading requirement. A Z-score threshold for that standalone strategy
will be defined in its own spec.

---

## Backtest Results

*Section to be populated once Phase 1 backtest engine is complete. The three-track
comparison is a Phase 0 research output; backtesting the winning combination is a Phase 1
task.*

| Field | Track A | Track B | Track C |
|-------|---------|---------|---------|
| Run ID | TBD | TBD | TBD |
| Backtest window | TBD | TBD | TBD |
| Net annualised return | TBD | TBD | TBD |
| Sharpe | TBD | TBD | TBD |
| Max drawdown | TBD | TBD | TBD |
| Git SHA | TBD | TBD | TBD |

---

## Variance Check Results

*Section to be populated after 6 monthly cycles are complete.*

| Field | Track A | Track B | Track C |
|-------|---------|---------|---------|
| Cycles completed | TBD | TBD | TBD |
| High-VIX events observed | TBD | TBD | TBD |
| Best overlay combination | TBD | TBD | TBD |
| Return on NEE (annualised) | TBD | TBD | TBD |
| Max drawdown (% NEE) | TBD | TBD | TBD |
| Conclusion gate: passed? | TBD | TBD | TBD |
| Recommended next step | TBD | TBD | TBD |

---

## Open Questions for Post-Comparison Review

- Does Track C's theta drag (estimated ₹14,000–21,000/year on the base alone) fully offset
  the capital efficiency advantage (₹2–3L at risk vs ₹15.5L for Track A)?
- Is the Track B + Collar meaningfully different from Track A + Collar once NEE-normalised?
  The council noted they may converge; the paper data will confirm.
- At what point does the Track C deep ITM call behave more like a futures position (delta
  stable near 0.90 all cycle) vs. an option (delta decaying, requiring frequent re-entries)?
  The 3-consecutive-days threshold is a first guess; calibrate from paper data.
- What is the actual spread_pct profile of quarterly vs yearly Nifty protective puts at
  the 8–10% OTM strike over the 6-cycle window? The bid/ask gate will generate this data
  automatically — use it to determine whether yearly overlays are ever genuinely accessible
  at 1-lot retail scale, or whether quarterly is the practical ceiling.
- Does the annualised premium cost of a quarterly protective put differ materially from
  three monthly rolls covering the same period, once slippage on the extra rolls is accounted
  for? The per-roll slippage on three monthlies may cancel out the theta efficiency advantage
  of the quarterly in thin-spread regimes.
