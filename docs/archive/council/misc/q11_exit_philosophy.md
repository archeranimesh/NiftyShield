NiftyShield runs three parallel paper-trading tracks on Nifty 50 index options.
All tracks have fully specified entry rules. Exit rules exist only for the CSP leg.
The overlay legs (Covered Call, Protective Put, Collar) have no codified exits.
This council question defines a complete exit philosophy for all legs across all tracks.

---

## System Context

**Three tracks:**

- Track A: Cash-Secured Put (CSP), sell 22-delta Nifty put, 30–45 DTE, monthly expiry.
  Entry: Wednesday after monthly expiry, 10:00–10:30 AM IST. IVR filter (skip if IVR < 25).
  Collateral: pledged NiftyBees ETF units.

- Track B: Deep ITM Call long (delta ≈ 0.90) as Nifty-equivalent synthetic long.
  CC overlay permanently blocked on Track B (hard rule per 2026-05-02 council).
  Track B may carry a Protective Put overlay only.

- Track C: Covered Call overlay on a separate long instrument (not futures).
  Can carry CC, PP, or Collar overlays.

**Overlay types actively running:**
- Covered Call (CC): short OTM call on a long underlying. Generates income, caps upside.
- Protective Put (PP): long OTM put for downside insurance. Pure cost, no income.
- Collar: simultaneous CC + PP on the same underlying. CC premium partially funds PP cost.

**Existing exit rules (CSP leg only — codified in csp_nifty_v1.md):**
1. Profit target: close when option mark decays to ≤50% of entry credit.
2. Time stop: close after 21 calendar days from entry if no other trigger fired.
3. Loss stop: close if put delta crosses −0.45 OR mark-to-market reaches 1.75× entry credit (whichever fires first). Delta gate fires earlier (lower gamma), better fills; mark multiplier is backstop when chain is stale.
4. Re-entry (R5): after profit-target exit, re-enter at 22-delta same expiry if DTE ≥ 14 AND IVR ≥ 25.

**The gap this council must resolve:**
- Exit rules for CC, PP, and Collar overlay legs are entirely undefined.
- Whether CSP exit rules need regime-conditioning or remain static mechanical.
- Intraday vs EOD monitoring: paper system runs EOD cron (paper_3track_snapshot.py).
  Intraday tracker exists on */15 cron but does not pull option chain data per leg.
- All exits are currently discretionary, defeating the statistical purpose of paper trading.

**Constraint set (NSE-specific, must hold in all recommendations):**
- NSE index options only. Cash-settled. No physical assignment risk.
- Paper trading phase — no live order execution. Exits flagged, acted on manually.
- EOD snapshot is the primary monitoring cadence. Intraday monitoring is opt-in.
- Transaction friction: each exit = 2 brokerage cycles ≈ ₹160–200 per leg.
  Minimum economic credit at entry: effectively ₹12–15 net of friction.
  A 50% decay exit on a ₹10 entry premium = ₹5 residual × 65 units = ₹325 gross
  minus ₹200 friction = ₹125 net. The percentage rule needs an absolute floor.
- Lot size: 65 units (Nifty 50, effective Jan 2026).

---

## Q1 — Profit Target: Percentage, Absolute Floor, or DTE Override?

The CSP uses 50% premium decay as profit target. Should CC overlays use the same rule?

Sub-questions:
a) What is the minimum absolute entry credit below which a percentage-based profit target
   is uneconomic given NSE friction? Should cycles below this floor be held to expiry?
b) Is 50% the right decay target for CC, PP, and Collar legs, or does each leg type
   warrant a different threshold given its structural role (income vs insurance vs combined)?
c) Should a DTE-based override replace or supplement the percentage target — e.g., close
   all sell legs at DTE ≤ 5 regardless of decay? Trade-offs vs percentage-triggered close
   for NSE weekly/monthly expiry structure?
d) For the PP (long put, insurance leg): the integrated strategy spec says "no pre-expiry
   profit-taking — the put is profitable because Nifty is falling, which is exactly when
   you need it." Is this rule correct, or is there a threshold (e.g., 5× entry premium AND
   bid-ask < 10% of mid) at which early exit makes sense even for protection legs?

---

## Q2 — Loss Stop: Premium Multiple, Delta Breach, or Margin Percent?

Three competing stop mechanisms for sell legs (CC short call, Collar short call):

**Option A — Premium multiple (2× entry premium = close):**
Simple, premium-size-anchored. Problem: does not distinguish a 1.5% Nifty move from a 4%
move. NSE gap-open risk: premium can jump past 2× overnight; stop fires at yesterday's
close, after the gap.

**Option B — Delta breach (|delta| crosses threshold):**
Fires earlier (lower gamma), produces better fills, directly measures positional risk.
The CSP already uses this (−0.45 delta stop). Problem: requires live chain delta at
exit time. Paper system runs EOD only; intraday delta is not currently fetched per leg.

**Option C — P&L percent of margin deployed:**
Stop when unrealised loss exceeds X% of SPAN margin for that leg. Margin-anchored,
stable when premium is small. Problem: SPAN fluctuates intraday with VIX; paper system
does not track real-time SPAN.

Sub-questions:
a) Which mechanism is most robust for NSE gap-open conditions? Is a combination
   (delta primary + premium-multiple backstop) superior to either alone?
b) If delta is the primary trigger, what threshold for CC overlays (entered at ~0.20 delta)?
   Is it symmetric with CSP delta stop (−0.45) or structurally different on the call side?
c) For the Collar (short call + long put combined), should the stop trigger evaluate the
   short call independently, or on net Collar P&L? A short call stop firing while the long
   put is gaining may be premature — the Collar structure may be functioning correctly.

---

## Q3 — Multi-Leg Exit Sequencing for Collar

The Collar is a 4-leg atomic structure: long underlying + short call + long put.

a) If the short call hits its stop (Nifty rallied, call is deep ITM):
   - Close short call only? Close short call + long put (exit hedge, keep long)? Close all?
   - What is the correct sequencing and rationale?

b) If the long put hits a take-profit (Nifty fell, put is profitable):
   - Existing rule: hold the put (protection needed during decline).
   - But if the decline is severe enough that the short call is now far OTM (near worthless),
     should the Collar be rebalanced mid-cycle or held to expiry?

c) Does leg-independent exit destroy the Collar's structural hedge, or is per-leg management
   appropriate for a paper-trading system where execution is manual?

---

## Q4 — Regime Conditioning: Static vs Adaptive Exits

Should exit rules be static mechanical (same thresholds in all regimes), or adapt to IVR/VIX?

Case for regime-conditioning:
- High IVR (> 50): CC premiums rich, extending target to 65–70% decay may improve EV.
- Low IVR (< 25): absolute premium thin; 50% decay may fire below friction floor;
  DTE-based close (hold to DTE ≤ 7) may be better.

Case against:
- Regime-conditioning introduces a second variability source into paper trade data.
  Isolating whether performance differences are due to entry delta, regime, or exit rule
  is impossible in a 6–12 cycle sample.

Sub-questions:
a) For Phase 0 paper trading (6–12 cycles), is static exit superior for data quality reasons?
b) At what paper-trade sample size does regime-conditioned exit become safe to introduce
   without confounding the backtest comparison?
c) Which regime signal is most appropriate for exit conditioning — IVR at entry (already
   logged), spot VIX at exit time, or the regime_probe composite (ADX/BB/ATR)?

---

## Q5 — Automation Tier for Paper Exit Detection

Current paper system:
- EOD cron: paper_3track_snapshot.py — fetches live spot + per-leg delta-from-yesterday.
- Intraday cron: intraday_tracker.py (*/15, 9:15–15:30) — does NOT pull option chain
  data per paper position.

**Tier 1 (EOD signal detection):** At EOD snapshot, check each paper leg for decay target,
premium stop, delta breach, DTE threshold. Write exit_signal to paper_leg_snapshots.
User acts manually next morning.

**Tier 2 (Intraday signal detection):** Extend intraday_tracker.py to fetch live option
chain per paper position every 15 minutes. Fire Telegram alert on signal. User acts same day.

Sub-questions:
a) For the paper-trading phase, is Tier 1 sufficient, or does EOD-only monitoring
   systematically bias exit price data vs what live execution would achieve?
   (Specifically: does it cause overshoot on loss stops and undershoot on profit targets?)
b) If Tier 2 is recommended, minimum data per leg per 15-min interval: just premium LTP
   or also delta (requires full chain fetch)?
c) Should exit signals be an enum column on paper_leg_snapshots
   (exit_signal: NONE | PROFIT_TARGET | LOSS_STOP | DELTA_STOP | DTE_FORCED | MANUAL)
   or a separate exit_events table to preserve signal history across snapshot cycles?

---

## Required Council Output Format

A Summary Table with canonical before/after for each decision:

| Decision | Current (undefined/default) | Council recommendation |
|---|---|---|
| CC profit target % | Undefined | ? |
| CC profit target floor (absolute ₹) | Undefined | ? |
| CC loss stop mechanism | Undefined | ? |
| CC loss stop threshold | Undefined | ? |
| PP exit rule | "hold to expiry" (integrated spec) | Confirm or revise? |
| Collar exit sequencing — short call stop | Undefined | ? |
| Collar exit sequencing — long put profit | Undefined | ? |
| Static vs regime-conditioned exits (Phase 0) | Static (implicit) | Confirm or revise? |
| Automation tier for Phase 0 paper trading | None (discretionary) | Tier 1 or Tier 2? |
| exit_signal storage format | None | Enum on leg_snapshots or separate table? |

Dissenting Notes must capture panel disagreement on Q2 (delta vs premium-multiple stop)
— highest-variance decision; minority position is first candidate for post-paper validation.
