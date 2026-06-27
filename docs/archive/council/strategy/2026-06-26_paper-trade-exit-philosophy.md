# Council Decision: paper-trade-exit-philosophy

Date: 2026-06-26  
Chairman: anthropic/claude-4.6-opus-20260205  
Council members: openai/gpt-5.5-20260423, google/gemini-3.1-pro-preview-20260219, x-ai/grok-4.3-20260430, deepseek/deepseek-r1-0528

---

## Stage 3 — Chairman Synthesis

# NiftyShield Council Ruling — Complete Overlay Exit Philosophy

## Chairman's Preamble

Four council members provided detailed recommendations. Peer rankings converged strongly: Response A was ranked #1 by three of four evaluators and #2 by the fourth. Response B was consistently ranked #2 or #3. Response D was unanimously ranked last. The key areas of consensus and disagreement are synthesized below into a single authoritative ruling.

**Guiding principle adopted unanimously:** Overlays serve structural purposes first, yield purposes second. Insurance legs (PP) and income legs (CC) require fundamentally different exit logic. Phase 0 demands static mechanical rules to preserve data quality.

---

## Summary Table

| Decision | Current (undefined/default) | Council Recommendation |
|---|---|---|
| **CC profit target %** | Undefined | **70% captured** (LTP ≤ 30% of entry credit), matching `_PROFIT_TARGET_RETENTION` |
| **CC profit target floor (absolute ₹)** | Undefined | **₹15 minimum entry credit** (`_CC_MIN_ENTRY_CREDIT`). Below ₹15: no early profit exit; hold to DTE_REVIEW or expiry |
| **CC loss stop mechanism** | Undefined | **Dual-signal:** delta primary + premium-multiple backstop |
| **CC loss stop threshold** | Undefined | **Delta ≥ 0.55 OR LTP ≥ 2.5× entry credit** |
| **PP exit rule** | "Hold to expiry" (integrated spec) | **Confirmed with exception:** CRASH_MONETIZE at δ ≤ −0.80 OR mark ≥ 5× entry debit; ROLL_ELIGIBLE at DTE ≤ 5. No normal profit-taking. |
| **Collar exit sequencing — short call stop** | Undefined | **Atomic close** of entire overlay (short call + long put) via `OverlayCloser.close_collar_all`; base long instrument retained |
| **Collar exit sequencing — long put profit** | Undefined | **Hold.** Crash monetization only via `OverlayCloser.monetize_collar_put` (validates put exists before touching call). No mid-cycle rebalancing in Phase 0. |
| **Static vs regime-conditioned exits (Phase 0)** | Static (implicit) | **Strictly static mechanical.** Log IVR/VIX/regime fields; do not condition exits on them. |
| **Automation tier for Phase 0** | None (discretionary) | **Tier 1 (EOD signal detection)** as mandatory baseline. Tier 2 intraday deferred. |
| **exit_signal storage format** | None | **Separate `paper_exit_events` table** with full state lifecycle (OPEN → ACKNOWLEDGED → ACTED / DISMISSED) and dual-signal audit fields |

---

## Q1 — Profit Target Rules

### Covered Call: 70% Captured / 30% Retention

```
Close CC when: current_mark ≤ 0.30 × entry_credit
Gate:          entry_credit ≥ ₹15
```

**Rationale and council consensus (3 of 4 members):** CC entries at ~0.15–0.20 delta yield smaller premiums than CSP entries. A 50% decay rule on a ₹10 credit leaves ₹5 gross × 65 units = ₹325, minus ~₹200 friction = ₹125 net — barely economic. Waiting for 70% decay (30% remaining) improves net economics and reduces churn. This aligns with the already-implemented `_PROFIT_TARGET_RETENTION = Decimal("0.30")` constant shared between CSP and CC in `exit_signals.py`.

**₹15 floor:** Below ₹15 entry credit, friction dominates. Skip percentage-based profit target; hold to DTE_REVIEW (DTE ≤ 5) or expiry unless a stop fires. This matches `_CC_MIN_ENTRY_CREDIT = Decimal("15")` already in the codebase.

**One dissenter (Response D) argued for 50% decay** to match CSP parity. This was rejected: CC and CSP have different entry deltas, premium sizes, and structural roles. The codebase already implements the 70%/30% split.

### DTE Override

```
DTE_REVIEW: fires at DTE ≤ 5 for all sell legs
```

This supplements but does not replace percentage targets. At DTE ≤ 5, gamma risk outweighs residual theta. The existing `evaluate_roll_overlay` already implements DTE ≤ 5 → ROLL_ELIGIBLE ACTION (when base_dte > 10) and ROLL_BASE_FIRST WARN (when base_dte ≤ 10).

### Time Stop

```
TIME_STOP: fires at days_held ≥ 21 for CC (same as CSP)
```

Already implemented in `evaluate_cc`. Serves as a discipline gate to prevent indefinite hold of decayed but not-yet-target positions.

### Protective Put: No Profit Target

```
Default: hold to expiry
Exception: CRASH_MONETIZE if δ ≤ −0.80 OR mark ≥ 5× entry debit
```

**Unanimous council agreement.** The PP is insurance. If it gains value, the portfolio is under stress — exactly when protection is needed. Selling it early because it is "profitable" removes the protection at the worst possible time.

The CRASH_MONETIZE exception handles the tail scenario where the put is so deeply ITM that:
- Liquidity collapses (delta ≤ −0.80 means deep ITM, spreads blow out)
- The payoff is so large (≥ 5× debit) that holding further adds gamma risk without proportional gain

This aligns with `evaluate_pp` in `ExitSignalEngine`: CRASH_MONETIZE fires at δ ≤ −0.80 OR value ≥ 5× debit. No spread guard is applied — in crashes, spreads widen precisely when exit is needed.

**Rejected minority view:** One response suggested allowing profit-taking at 5× premium if bid-ask < 5%. This was rejected because it violates the "never remove protection early" principle and the bid-ask condition is almost never met during the crash conditions that create the 5× payoff.

---

## Q2 — Loss Stop: Dual-Signal Architecture

### Mechanism: Delta Primary + Premium-Multiple Backstop

```
CC loss stop:
    Close if delta ≥ +0.55          (primary — positional migration)
    OR mark ≥ 2.5× entry credit     (backstop — stale-Greeks guard)
```

**Council consensus (3 of 4 members favor dual-signal; 1 favors premium-only).**

### Why delta is primary

Delta directly measures where the option has migrated structurally. A CC entered at ~0.20 delta that reaches +0.55 is no longer a low-probability income overlay — it is a materially ITM cap on the long position. Delta fires earlier in clean trend moves (lower gamma), producing better exit quality.

### Why +0.55, not +0.45

The CC delta stop is intentionally wider than the CSP delta stop (0.45) because:

- **Structural offset:** The CC is paired with a long underlying. The short call losing is partially offset by the long position gaining. A 0.45 trigger would produce excessive whipsaw on normal underlying appreciation.
- **Entry delta gap:** CC enters at ~0.15–0.20 delta (vs CSP at ~0.22). The distance from entry to 0.55 is proportionally similar to CSP's distance from 0.22 to 0.45.
- **NSE-specific:** Nifty can move 2–3% intraday on event days. A 0.45 trigger on a CC may fire on noise; 0.55 represents genuine ITM migration.

### Why 2.5×, not 2×

- CC premiums are typically smaller than CSP premiums
- The underlying long position offsets short call losses partially
- A 2× trigger on a ₹12 credit fires at ₹24 — only ₹780 per lot unrealized loss, likely recoverable on a reversion
- 2.5× provides a more meaningful backstop that catches genuine adverse moves

### Premium-multiple as backstop, not primary

The premium-multiple fires when:
- Greeks are stale or absent in the EOD chain
- Overnight gap-opens blow past the delta level before the next snapshot
- The broker's delta feed is unreliable

### Dual-signal audit fields (mandatory)

Every exit event must capture:

```
delta_stop_would_fire: bool
premium_stop_would_fire: bool
actual_rule_used: DELTA | PREMIUM | BOTH | NEITHER
```

This is already implemented in `ExitSignalResult` and `_get_sell_audit_fields()` in `exit_signals.py`. Post-Phase-0 analysis uses these fields to determine whether delta or premium produced better outcomes.

### Collar short call

The collar short call uses the **identical** stop mechanism (δ ≥ 0.55 OR 2.5× premium), evaluated on the short call independently. However, the *execution* response differs — see Q3.

---

## Q3 — Collar Exit Sequencing

### Principle: The Collar Is a Unified Risk Envelope

A collar is not a collection of independent trades. It is a single structure: long underlying + short call (income/cap) + long put (protection). Independent leg management breaks the hedge state and makes paper-trade attribution impossible.

### A. Short Call Stop Fires (Nifty Rallied)

```
Action: CLOSE_FULL_COLLAR_OVERLAY
  → Close short call
  → Close long put
  → Retain base long instrument
```

**Rationale (unanimous):** When Nifty rallies and the short call goes ITM (δ ≥ 0.55):
- The long put is nearly worthless — it provides no remaining protection value
- Keeping a dead put consumes margin and creates false hedge-state in the tracker
- Closing only the call leaves an expensive standalone hedge that serves no purpose
- The `OverlayCloser.close_collar_all` already implements this as an atomic operation

### B. Long Put Becomes Profitable (Nifty Fell)

```
Default: Hold the put — insurance is working as designed

Exception: CRASH_MONETIZE
  → If put delta ≤ −0.80 OR mark ≥ 5× entry debit
  → Close put via OverlayCloser.monetize_collar_put
  → Close the nearly-worthless short call (pennies, frees margin)
```

`monetize_collar_put` already validates the put leg exists before touching the call (incomplete-collar guard).

### C. Mid-Cycle Rebalancing

**Not permitted in Phase 0.** If the collar is partially disrupted (e.g., crash monetization of put), log it as a crash monetization event and wait for the next scheduled overlay entry. Do not attempt to reconstruct the collar mid-cycle — this introduces discretionary decisions that contaminate paper-trade data.

### Dissent on Collar Sequencing

Response D recommended closing only the short call and leaving the put active. This was rejected by three of four members because:
- It breaks the financed nature of the collar
- It leaves a decayed, near-worthless put consuming margin
- It creates an ambiguous hedge state in the paper tracker
- It contradicts the implemented `OverlayCloser.close_collar_all` atomic operation

---

## Q4 — Static vs Regime-Conditioned Exits

### Phase 0: Strictly Static

**Unanimous council agreement.** Do not modify exit rules based on IVR, VIX, ADX, ATR, Bollinger width, or any other regime signal during Phase 0.

**Reason:** With 6–12 monthly cycles, regime-conditioned exits make attribution impossible. If performance changes, you cannot determine whether the cause was entry delta, IVR filter, trend regime, exit rule, option skew, expiry selection, or path dependency.

### What to log (but not act on)

Every paper trade and exit event should capture:
- IVR at entry (already logged via `ivr_at_entry` on `PaperTrade`)
- Spot VIX at exit time
- Regime probe composite (ADX/BB/ATR from `regime_probe.pine`)
- Underlying spot at entry and exit

These fields enable post-Phase-0 stratification analysis without contaminating the mechanical baseline.

### When to introduce regime conditioning

```
Gate: ≥ 30 closed trades per strategy/leg type
  OR ≥ 12–18 months of clean paper data
  OR validated historical backtest with sufficient regime diversity
```

Preferably, use backtest evidence first (Phase 0.8 gate in BACKTEST_PLAN.md), then paper validation.

### Future regime signal hierarchy

| Use case | Signal |
|---|---|
| Entry filter | IVR at entry (already implemented) |
| Exit risk escalation | Spot VIX / IVR at exit |
| Research annotation | regime_probe composite |
| Candidate for Phase 1+ adaptive exit | IVR at entry + VIX percentile at exit |

---

## Q5 — Automation Tier and Storage

### Tier 1 EOD Signal Detection: Mandatory Baseline

At each EOD snapshot (`paper_3track_snapshot.py`), evaluate every paper leg against the full `ExitSignalEngine` rule set:

- `evaluate_profit_target_csp` / CC profit target (via `_PROFIT_TARGET_RETENTION`)
- `evaluate_hard_stop_csp` / CC premium backstop
- `evaluate_delta_breach_csp` / CC delta breach
- `evaluate_time_stop_csp` / CC time stop
- `evaluate_pp` (CRASH_MONETIZE + ROLL_ELIGIBLE)
- `evaluate_roll_overlay` (DTE ≤ 5 roll eligibility + base-DTE guard)
- `evaluate_proxy_delta` (for base_ditm_call legs)
- `evaluate_cc` (all CC-specific rules)

Write exit events to `paper_exit_events`. User acts manually next morning.

### Does EOD-only bias results?

Yes, but acceptably for Phase 0:

| Signal type | EOD bias | Severity |
|---|---|---|
| Profit target | Slightly late capture | Low — theta works in your favor overnight |
| Loss stop (premium) | May overshoot on gap days | Moderate — but accurately penalizes paper P&L |
| Delta breach | May trigger one session late | Moderate — captured by dual-signal audit |
| DTE review | No issue | None |
| Crash monetization | Could be materially late | High — but crash events are rare; Tier 2 deferred |

Phase 0's purpose is rule validation and behavioral discipline, not perfect execution simulation. Tier 1 is sufficient.

### Tier 2 Deferred

Tier 2 intraday monitoring (extending `intraday_tracker.py` to fetch per-leg option chains every 15 minutes) is useful but not required for Phase 0. If implemented later, it should run as **shadow monitoring**:

- Record whether the intraday signal would have fired earlier than EOD
- Compare slippage/overshoot
- Decide during Phase 1 whether live deployment requires intraday alerts

Minimum intraday data per leg if Tier 2 is implemented:
```
ltp, bid, ask, mid, delta, dte, underlying_spot, timestamp
```

LTP-only is insufficient — delta is required for the primary stop logic.

### Storage: Separate `paper_exit_events` Table

**Unanimous council agreement.** Do not rely on an enum column on `paper_leg_snapshots` alone.

A snapshot column loses event history — it only tells you the latest state. A separate events table preserves:
- First signal timestamp
- Repeated signals across snapshots
- Status transitions (OPEN → ACKNOWLEDGED → ACTED / DISMISSED)
- Manual acknowledgement audit trail
- Dual-signal evidence fields
- Dismissed signals (important for understanding false positive rates)

This is already implemented: `paper_exit_events` table exists in `PaperStore` with the schema described in the project context, including `ExitSignal` enum, severity levels, dual-signal audit fields, and the OPEN → ACKNOWLEDGED → ACTED / DISMISSED lifecycle.

---

## Canonical Rule Set (Complete)

### Covered Call (`evaluate_cc`)

```
Profit target:
    IF entry_credit ≥ ₹15
    AND current_mark ≤ 0.30 × entry_credit
    → ACTION: PROFIT_TARGET

Loss stop (dual-signal):
    IF delta ≥ +0.55
    OR current_mark ≥ 2.5 × entry_credit
    → ACTION: DELTA_BREACH / HARD_STOP
    Audit: delta_stop_would_fire, premium_stop_would_fire, actual_rule_used

Time stop:
    IF days_held ≥ 21
    → ACTION: TIME_STOP

DTE review:
    IF DTE ≤ 5
    → ACTION: DTE_REVIEW (close or roll)
```

### Protective Put (`evaluate_pp`)

```
Default: hold to expiry

Crash monetization:
    IF delta ≤ −0.80
    OR current_mark ≥ 5 × entry_debit
    → ACTION: CRASH_MONETIZE
    No bid-ask spread guard (spreads blow out in crashes)

Roll eligible:
    IF DTE ≤ 5
    → ACTION: ROLL_ELIGIBLE
```

### Collar

```
Short call stop fires:
    → ACTION: CLOSE_FULL_COLLAR_OVERLAY
    Execute via OverlayCloser.close_collar_all
    Close short call + long put atomically
    Retain base long instrument

Long put normal profit:
    → Hold (no action)

Long put crash monetization:
    IF put delta ≤ −0.80 OR put mark ≥ 5× debit
    → ACTION: MONETIZE_COLLAR_PUT
    Execute via OverlayCloser.monetize_collar_put
    Validates put leg before touching call
```

### CSP (unchanged from `csp_nifty_v1.md`)

```
Profit target: LTP ≤ 30% of entry credit (70% captured)
Hard stop: LTP ≥ 2× entry credit
Delta breach: |δ| ≥ 0.40 (state-aware: OPEN→DELTA_BREACH, DEFENDED→DELTA_BREACH_FINAL)
Time stop: days_held ≥ 21
Roll eligible: DTE ≤ 7
Re-entry: DTE ≥ 14 AND IVR ≥ 0.25 AND no open position
```

---

## Dissenting Notes — Q2 Delta vs Premium Stop

### Majority View (Adopted)

```
Delta primary + premium-multiple backstop
CC: delta ≥ +0.55 OR mark ≥ 2.5× entry credit
```

Delta captures true positional migration. Premium-multiple guards against stale Greeks. Dual-signal audit fields enable post-Phase-0 empirical validation.

### Minority View (Recorded for Validation)

```
Premium-multiple only: mark ≥ 2.5× entry credit
```

**Minority rationale:**
- EOD delta can be stale; broker Greeks are not always reliable
- In a Tier 1 (EOD-only) system, delta is measured only at 15:30 IST — systematically late
- Premium is directly observable and auditable without chain dependency
- If delta consistently fires a full day after premium would have triggered intraday, the delta-primary model is worse than premium-only for EOD systems

**Council resolution:** Adopt majority rule. Preserve `actual_rule_used` audit field. After ≥12 closed CC cycles, analyze:
- How often did DELTA fire first vs PREMIUM?
- When PREMIUM fired first, would next-day exit have been materially better?
- Does the delta signal add genuine value over premium-only in an EOD-only monitoring regime?

If premium-only proves empirically equivalent or superior in EOD contexts, simplify to premium-only for live deployment. The minority position is the **first candidate for post-Phase-0 validation**.

---

## Implementation Notes

All recommended rules are either already implemented or directly map to existing infrastructure:

| Rule | Implementation Status |
|---|---|
| CC 70%/30% profit target | `_PROFIT_TARGET_RETENTION` in `exit_signals.py` |
| CC ₹15 floor | `_CC_MIN_ENTRY_CREDIT` in `exit_signals.py` |
| CC delta stop 0.55 | `evaluate_cc` in `exit_signals.py` |
| CC premium stop 2.5× | `evaluate_cc` in `exit_signals.py` |
| PP CRASH_MONETIZE | `evaluate_pp` in `exit_signals.py` |
| Collar atomic close | `OverlayCloser.close_collar_all` |
| Collar put monetization | `OverlayCloser.monetize_collar_put` |
| Dual-signal audit | `_get_sell_audit_fields()` in `exit_signals.py` |
| Exit events table | `paper_exit_events` in `PaperStore` |
| Event lifecycle | OPEN → ACKNOWLEDGED → ACTED / DISMISSED |
| EOD signal detection | `paper_3track_snapshot.py` + `ExitSignalEngine` |

No new tables or schema changes are required. The ruling codifies and confirms the existing implementation as the canonical Phase 0 exit philosophy.

---

## Stage 1 — Individual Responses

### openai/gpt-5.5-20260423

## Council Recommendation — NiftyShield Overlay Exit Philosophy

**Core recommendation:**  
For Phase 0 paper trading, use **static, mechanical, EOD-detected exit rules** with a separate `exit_events` history table. Do **not** regime-condition exits yet. For sell overlays, use a **dual stop**: delta breach as the primary risk signal, premium multiple as the stale-Greeks backstop. For insurance legs, preserve protection by default and monetize only under crash-level payoff conditions.

---

## Summary Table

| Decision | Current / Undefined | Council recommendation |
|---|---:|---|
| **CC profit target %** | Undefined | Close when mark ≤ **30% of entry credit** — i.e. **70% premium captured** |
| **CC profit target floor** | Undefined | Apply profit target only if entry credit ≥ **₹15**. Below ₹15, hold to DTE review / expiry unless stop fires |
| **CC loss stop mechanism** | Undefined | **Dual trigger:** delta primary + premium multiple backstop |
| **CC loss stop threshold** | Undefined | Close if call delta ≥ **+0.55** OR mark ≥ **2.5× entry credit** |
| **PP exit rule** | “Hold to expiry” | Confirm as default. Exception: monetize if put delta ≤ **−0.80** OR mark ≥ **5× entry debit** |
| **Collar short-call stop sequencing** | Undefined | If short call stop fires, close the **entire collar overlay** — short call + long put — but keep base long instrument |
| **Collar long-put profit sequencing** | Undefined | Do **not** take normal profit. Hold protection. Exception: crash-monetize long put if delta ≤ −0.80 OR mark ≥ 5× debit |
| **Static vs regime-conditioned exits, Phase 0** | Static implicit | Keep **static mechanical exits** for Phase 0. Log IVR / VIX / regime, but do not adapt rules yet |
| **Automation tier, Phase 0** | Discretionary | Use **Tier 1 EOD signal detection** as mandatory baseline. Tier 2 intraday is optional shadow data, not required for Phase 0 |
| **Exit signal storage format** | None | Use a **separate `paper_exit_events` table**, not only an enum on snapshots |

---

# Q1 — Profit Target

## Recommendation

### Covered Call

Use a **70% captured / 30% remaining** rule:

```text
Close CC when current mark ≤ 0.30 × entry credit
```

But only if:

```text
entry credit ≥ ₹15
```

Rationale:

- CC entries are often smaller-premium trades than CSPs.
- A 50% decay rule on low-credit calls is economically weak after NSE brokerage, taxes, and slippage.
- A ₹10 entry credit with 50% exit leaves only ₹5 gross edge, often mostly consumed by friction.
- Waiting for 70% decay improves net economics and reduces churn.

Therefore:

```text
If entry credit < ₹15:
    do not use percentage profit target.
    hold until DTE review / time stop / loss stop.
```

### CSP

For Phase 0, keep CSP rules mechanical and do not regime-condition. If the system standardizes sell-leg profit-taking at **70% captured**, apply it consistently going forward and mark the cohort boundary clearly.

### Protective Put

Do **not** use percentage decay or normal profit target logic on PP.

The PP is insurance. If it gains value, the portfolio is likely under stress. Selling it early because it is profitable removes the protection exactly when protection is needed.

Default rule:

```text
Hold PP to expiry.
```

Exception:

```text
Monetize PP if:
    put delta ≤ −0.80
    OR current mark ≥ 5× entry debit
```

Do **not** require a tight bid/ask spread filter for crash monetization. In crashes, spreads widen precisely when exit is needed. Use limit execution discipline, but do not block monetization because spread percentage is ugly.

### Collar

Treat the collar as a structure, not as two unrelated options.

- The short call is the income/cap leg.
- The long put is the protection leg.
- Normal put profit should not be taken.
- Crash-level put payoff may be monetized.

---

# Q2 — Loss Stop: Delta, Premium Multiple, or Margin Percent?

## Majority recommendation

Use a **dual-trigger stop** for short call overlays:

```text
Close short call if:
    delta ≥ +0.55
    OR mark ≥ 2.5× entry credit
```

### Why delta is primary

Delta is the better risk variable because it captures where the option has migrated structurally.

A CC entered at ~0.15–0.20 delta that has moved to +0.55 is no longer a low-probability income overlay. It has become a materially ITM / high-gamma cap on the long position.

Delta also tends to fire earlier than premium multiple in clean trend moves, producing better exit quality.

### Why premium multiple is still needed

Greeks can be stale, absent, or unreliable in the EOD chain.

Premium multiple is therefore the backstop:

```text
mark ≥ 2.5× entry credit
```

Use **2.5×**, not 2×, for CC because:

- CC premium can be small.
- The underlying long position partially offsets the short call loss.
- A 2× rule can over-trigger on noise, especially for low-premium calls.

### Why not margin-percent stop in Phase 0

Do not use SPAN / margin-percent stop in Phase 0.

Reasons:

- Paper system does not track real-time SPAN.
- SPAN changes with VIX and exchange margin models.
- It adds complexity without improving attribution quality.
- Margin-based stops are more relevant for live broker risk controls than paper-trade statistical testing.

---

# Q3 — Collar Exit Sequencing

## A. If the short call hits stop

If the collar short call hits:

```text
delta ≥ +0.55
OR mark ≥ 2.5× entry credit
```

then close the **entire collar overlay**:

```text
Buy back short call
Sell long put
Keep base long instrument
```

Do **not** close the base long instrument.

### Rationale

A short-call stop usually means Nifty has rallied. In that scenario:

- The long put is likely decayed and no longer useful.
- The short call is now capping upside aggressively.
- Keeping the put while closing the call leaves an expensive standalone hedge.
- Closing only the call destroys the financed nature of the collar.

Therefore, the clean action is:

```text
Close collar overlay atomically.
Retain base exposure.
Wait for next scheduled overlay entry.
```

## B. If the long put becomes profitable

Default:

```text
Hold the put.
```

Do not take ordinary profits from the long put. If the put is profitable, the market is falling, and the hedge is doing its job.

Exception:

```text
Crash monetization if:
    put delta ≤ −0.80
    OR mark ≥ 5× entry debit
```

When crash monetization fires:

- Close / monetize the long put.
- Do not automatically re-enter a new put immediately.
- Do not rebalance the collar mid-cycle in Phase 0 unless explicitly logged as a separate discretionary intervention.

If the short call has become nearly worthless, it may be left to expire or closed if operationally convenient, but it should not drive the primary decision. The protective put is the important leg during a crash.

## C. Does leg-independent management destroy the collar?

Mostly, yes.

For Phase 0, avoid discretionary leg-by-leg collar management except for explicitly defined crash monetization. Otherwise, leg-independent exits make the paper data hard to interpret.

Recommended principle:

```text
Short-call stop → close entire collar overlay.
Long-put normal profit → hold.
Long-put crash monetization → close put, log as crash monetization event.
```

---

# Q4 — Static vs Regime-Conditioned Exits

## Recommendation for Phase 0

Use **static exits**.

Do not modify exits based on:

- IVR at entry,
- India VIX at exit,
- regime probe output,
- ADX / ATR / Bollinger width,
- trend classification.

Log these fields, but do not let them alter the exit rules yet.

### Reason

Phase 0 has too few cycles.

With only 6–12 monthly cycles, regime-conditioned exits would make attribution impossible. If performance changes, you will not know whether the cause was:

- entry delta,
- IVR filter,
- trend regime,
- exit rule,
- option skew,
- expiry selection,
- or random path dependency.

For paper-trading data quality, static rules are superior.

## When to introduce regime-conditioned exits

Do not introduce adaptive exits until at least one of the following is available:

```text
≥ 30 closed trades per strategy / leg type
OR
≥ 12–18 months of clean paper data
OR
validated historical backtest with sufficient regime diversity
```

Preferably, use backtest evidence first, then paper validation.

## Which regime signal to use later

For future adaptive exits:

| Use case | Preferred signal |
|---|---|
| Entry filter | IVR at entry |
| Exit risk escalation | Spot VIX / IVR at exit |
| Research annotation | regime_probe composite |
| Future adaptive rule candidate | IVR at entry + VIX percentile at exit |

For now:

```text
Log all regime fields.
Do not condition exits on them.
```

---

# Q5 — Automation Tier

## Phase 0 recommendation

Use **Tier 1 EOD signal detection** as the required baseline.

At each EOD snapshot, evaluate every paper leg for:

- profit target,
- premium stop,
- delta breach,
- time stop,
- DTE review,
- crash monetization,
- missing Greeks,
- stale data.

Then write an exit event.

User may act manually the next morning.

## Does EOD-only bias results?

Yes, but acceptably for Phase 0.

Expected biases:

| Signal type | EOD-only bias |
|---|---|
| Profit target | May exit later than intraday, giving slightly worse / delayed profit capture |
| Loss stop | May overshoot on gap days, giving worse exit price |
| Delta breach | May trigger one session late |
| DTE review | No major issue |
| Crash monetization | Could be materially late in fast crashes |

However, Phase 0’s purpose is not perfect execution simulation. It is rule validation and behavioural discipline.

Tier 1 is sufficient for Phase 0 if all signals are recorded objectively.

## Tier 2 recommendation

Tier 2 intraday chain polling is useful, but not mandatory yet.

If implemented, it should fetch more than LTP.

Minimum intraday data per leg:

```text
ltp
bid
ask
mid
delta
dte
underlying spot
timestamp
```

Do not implement LTP-only Tier 2 if the goal is actionable exit detection. Delta is required for the primary stop logic.

Use Tier 2 initially as **shadow monitoring**, not as a rule change:

```text
Record whether intraday signal would have fired earlier than EOD.
Compare slippage / overshoot.
Decide later whether live deployment requires intraday alerts.
```

---

# Exit Signal Storage

Use a separate `paper_exit_events` table.

Do **not** rely only on an enum column inside `paper_leg_snapshots`.

## Rationale

A snapshot column only tells you the latest state. It loses event history.

An exit event table preserves:

- first signal timestamp,
- repeated signals,
- status transitions,
- manual acknowledgement,
- action taken,
- dismissed signals,
- stale signals,
- audit fields,
- dual-rule evidence.

Recommended fields:

```text
trade_id
strategy_name
leg_name
exit_signal
severity
status
ltp
mid
bid
ask
delta
dte
entry_price
threshold_value
delta_stop_would_fire
premium_stop_would_fire
actual_rule_used
created_at
updated_at
notes
```

Recommended status lifecycle:

```text
OPEN → ACKNOWLEDGED → ACTED
                  ↘ DISMISSED
```

---

# Canonical Rule Set

## Covered Call

```text
Profit target:
    if entry_credit ≥ ₹15
    and current_mark ≤ 0.30 × entry_credit
    → ACTION: PROFIT_TARGET

Loss stop:
    if delta ≥ +0.55
    OR current_mark ≥ 2.5 × entry_credit
    → ACTION: LOSS_STOP / DELTA_BREACH

Time stop:
    if days held ≥ 21
    → ACTION or REVIEW depending on implementation policy

DTE review:
    if DTE ≤ 5
    → REVIEW / ACTION depending on residual risk and roll policy
```

## Protective Put

```text
Default:
    hold to expiry

Crash monetization:
    if delta ≤ −0.80
    OR current_mark ≥ 5 × entry_debit
    → ACTION: MONETIZE_PP

No normal profit target.
No decay stop.
No early exit merely because mark increased.
```

## Collar

```text
Short call stop:
    if short_call_delta ≥ +0.55
    OR short_call_mark ≥ 2.5 × short_call_entry_credit
    → ACTION: CLOSE_FULL_COLLAR_OVERLAY
       close short call + long put
       keep base long instrument

Long put normal profit:
    hold

Long put crash monetization:
    if put_delta ≤ −0.80
    OR put_mark ≥ 5 × put_entry_debit
    → ACTION: MONETIZE_COLLAR_PUT
```

## CSP

```text
Keep mechanical exits.
Do not regime-condition during Phase 0.
Use delta + premium backstop.
Record IVR and regime fields for later analysis.
```

---

# Dissenting Notes — Q2 Delta vs Premium Stop

## Majority view

Use:

```text
delta primary + premium multiple backstop
```

The majority prefers this because delta better captures true positional migration, while premium multiple protects against missing or stale Greeks.

Recommended CC stop:

```text
delta ≥ +0.55 OR mark ≥ 2.5× entry credit
```

## Minority view

Use premium multiple only:

```text
mark ≥ 2× or 2.5× entry credit
```

Minority rationale:

- EOD delta can be stale.
- Broker Greeks are not always reliable.
- Premium is observable and auditable.
- Gap-open risk makes both delta and premium late anyway.
- Simpler rules produce cleaner operational behaviour.

## Council resolution

Adopt the majority rule, but preserve audit fields:

```text
delta_stop_would_fire
premium_stop_would_fire
actual_rule_used = DELTA | PREMIUM | BOTH | NEITHER
```

This allows post-paper validation.

If, after sufficient samples, most profitable avoided exits were premium-only false positives, relax the premium multiple. If delta consistently fired earlier with better next-day outcomes, keep delta primary for live deployment.

### google/gemini-3.1-pro-preview-20260219

Here is the synthesized ruling from the AI Council, addressing the complete exit philosophy for the newly defined overlay legs across NiftyShield’s three tracks.

---

## 🏛️ RapidCouncil Chairman Summary

The council analyzed the constraints of the NSE paper-trading tracks, specifically addressing transaction friction, gap-risk, and the statistical purity required for Phase 0. 

A central tenet guided this ruling: **Overlays serve structural purposes first, yield purposes second.** A Covered Call (CC) limits upside in exchange for premium; a Protective Put (PP) limits downside at a cost; a Collar combines both. Their management must be distinct from pure yield strategies like the Cash-Secured Put (CSP). Furthermore, Phase 0 paper trading requires strict variable isolation—introducing adaptive regime-based exits now will fatally contaminate your baseline data.

Here are the detailed rulings broken down by your questions.

### Q1 — Profit Target: Percentage, Absolute Floor, or DTE Override?

**a) Absolute Floor:** With NSE friction at ~₹3/unit round-trip (₹200/lot), taking 50% profit on a ₹10 premium nets only ~₹2/unit (₹130 profit per lot). This is uneconomic. 
**The Council sets a hard minimum entry floor of ₹15 total credit** across any sell leg (CC). If the CC premium is < ₹15, early profit-taking is blocked; the option must be held to the DTE review threshold to maximize theta capture.

**b) Target Percentage:** Because CC entries typically occur at ~0.20 delta (lower than CSP's 0.22-0.25), starting premiums are smaller. A standard 50% target decays too fast into the minimum friction zone. 
**The target should be 70% captured (LTP ≤ 30% of entry credit),** matching the `_PROFIT_TARGET_RETENTION` recently introduced in your static engine. 

**c) DTE Override:** Time-stops mathematically supersede percentage targets near expiry because gamma-risk outweighs residual theta. 
**Rule:** Implement **DTE_REVIEW (DTE ≤ 5)** for CCs. At DTE 5, if the call is OTM, close it to avoid pin/gap risk. This replaces the CSP's 21-day hold limit since overlays map to the underlying's risk.

**d) PP (Protective Put) Early Exit:** The spec's "no pre-expiry profit-taking" rule is correct for standard drawdowns, but fails in Black Swan events. If Nifty crashes 15%+ and IV hits 40, your deep OTM put becomes heavily ITM with bloated Vega. If you hold to expiry, IV crush will erase 50% of the value even if the index stays flat.
**Rule:** Introduce a **CRASH_MONETIZE** exception. Fire an `ACTION` signal if Long Put delta ≤ -0.80 OR value reaches 5× entry debit.

### Q2 — Loss Stop: Premium Multiple, Delta Breach, or Margin Percent?

**a/b) The Stop Mechanism:** A premium multiple stop fails to distinguish between severe spot movement and mere IV expansion. However, a delta stop relies on live Greeks which can be stale in EOD snapshots.
**The Council strongly recommends the Dual-Signal Stop (Option A + Option B).** 
Primary trigger: **Delta breach**. For a CC entered at 0.20 delta, a stop at **0.45 or 0.50 delta** is too tight (whipsaw risk). Set the CC delta stop at **0.55** (officially crossing into ITM territory).
Backstop trigger: **2.5× entry premium** (catches NSE overnight gap-opens when pricing is chaotic and Greeks haven't normalized). Whichever triggers first generates the `ACTION` exit.

**c) Collar Short Call Focus:** For a Collar, the short call should use the identical stop mechanism (0.55 Delta / 2.5× Premium) evaluated *independently*. However, the execution flow changes (see Q3).

### Q3 — Multi-Leg Exit Sequencing for Collar

A Collar is not a collection of independent trades; it is a unified risk envelope around your base asset. Independent leg management breaks the hedge state.

**a) Short Call hits Stop (Bull run):** If Nifty blasts upward and the short call goes ITM (hitting 0.55 delta), the underlying asset is highly profitable, and the long put is nearly worthless. 
**Rule:** Atomic close of the *entire* overlay structure. Close Short Call + close Long Put. Reset the Collar at higher strikes if desired, but do not leave a "dead" out-of-the-money put dragging on margin.

**b) Long Put hits Profit (Crash):** If `CRASH_MONETIZE` (5× debit) fires, the underlying is bleeding, and the short call is fully decayed (worthless).
**Rule:** Atomic close. Sell the Put to book the cash, and buy to close the Short Call for pennies to free up the margin block. 

### Q4 — Regime Conditioning: Static vs Adaptive Exits

**a/b) Phase 0 Rule:** **Strictly Static.**
Deploying regime-conditioned exits now introduces a second major variable (Regime state + Exit adaptivity). If Track C outperforms Track A, you will not know if it was the base-leg structure or the fact that a "bearish regime" tightened your put stops. 
Phase 0 (first 6–12 cycles) *must* create a static mechanical baseline.

**c) Future State:** Once 12 cycles are logged, IVR at entry (which you are already logging) combined with your `regime_probe` (ADX/BB/ATR data) becomes the factor used to adjust your `_PROFIT_TARGET_RETENTION` dynamically in Phase 1+.

### Q5 — Automation Tier for Paper Exit Detection

**a) Tier 1 vs Tier 2:** Tier 1 (EOD snapshot detection) is sufficient for Phase 0 paper trading. While intraday execution creates tighter adherence to loss stops, EOD better simulates the reality of part-time retail management (which aligns with your strategy mandate). EOD will cause some stop overshoot, but this *accurately penalizes* the paper-trade P&L for overnight gap risk and delayed reactions.

**b/c) Storage Architecture:** Do NOT use an enum on `paper_leg_snapshots`. Overwriting snapshot rows destroys temporal auditability (you lose "when did it start failing vs when did I manually act").
**Rule:** Use a separate `paper_exit_events` table (as previewed in your schema). This allows state-tracking (`OPEN` → `ACKNOWLEDGED` → `ACTED` → `DISMISSED`) and perfectly accommodates the dual-signal audit fields (`delta_stop_would_fire`, `premium_stop_would_fire`) required for post-mortem analysis.

---

## 📊 Canonical Council Recommendation Table

| Decision | Current (undefined/default) | Council Recommendation |
|---|---|---|
| CC profit target % | Undefined | **70% captured** (LTP ≤ 30% of entry credit) |
| CC profit target floor (absolute ₹) | Undefined | **₹15 minimum entry credit** to enable early exit |
| CC loss stop mechanism | Undefined | **Dual-Signal:** Delta primary + Premium multiple backstop |
| CC loss stop threshold | Undefined | **Delta ≥ 0.55 OR LTP ≥ 2.5× entry** |
| PP exit rule | "hold to expiry" | **CRASH_MONETIZE exception:** |δ| ≥ 0.80 OR LTP ≥ 5× debit |
| Collar exit sequencing — short call stop | Undefined | **Atomic Close:** Close Call + Close remaining Put |
| Collar exit sequencing — long put profit | Undefined | **Atomic Close:** Monetize Put + Close worthless Call |
| Static vs regime-conditioned exits (Phase 0) | Static (implicit) | **Strictly Static mechanical.** No adaptiveness in Phase 0. |
| Automation tier for Phase 0 paper trading| None (discretionary) | **Tier 1 (EOD)** + Next morning manual action |
| `exit_signal` storage format | None | **Separate `paper_exit_events` table** with state tracking |

---

## 📝 Dissenting Note (Quant Persona)

*Re: Q2 - Delta vs. Premium Multiple on Overlays.*
"I strongly dissent against prioritizing the Delta Stop for structural overlays like the CC. A Covered Call enters at ~0.20 delta. Setting the stop at 0.55 delta means the Nifty underlying has already rallied significantly, taking the short call completely ITM. In an EOD monitoring system (Tier 1), relying on a 0.55 delta threshold practically guarantees systemic overshoot because you only measure it precisely at 15:30 IST. 

"Premium multiple (2.5x) is a mathematically harder floor that directly interacts with your exact friction/liquidity loss. I advise the System Architect to closely monitor the `actual_rule_used` column in the new `paper_exit_events` table. If 'DELTA' is consistently firing an entire day *after* 'PREMIUM' would have triggered intraday, Phase 1 must upgrade to Tier 2 (intraday) monitoring or discard the delta stop on short calls."

### x-ai/grok-4.3-20260430

**Council Summary Table**

| Decision | Current (undefined/default) | Council recommendation |
|---|---|---|
| CC profit target % | Undefined | 30% retention of entry credit (same as CSP `_PROFIT_TARGET_RETENTION`); _CC_MIN_ENTRY_CREDIT = ₹15 absolute floor below which ride to DTE_REVIEW or expiry |
| CC profit target floor (absolute ₹) | Undefined | ₹15 net credit (after friction); cycles below this held to expiry or DTE-based review |
| CC loss stop mechanism | Undefined | Delta breach primary (|δ| ≥ 0.40) + premium-multiple (2×) backstop; dual-signal audit fields captured exactly as CSP `evaluate_hard_stop_csp` / `evaluate_delta_breach_csp` |
| CC loss stop threshold | Undefined | |δ| ≥ 0.40 (symmetric with CSP 0.40 threshold); 2× premium backstop when delta unavailable |
| PP exit rule | "hold to expiry" (integrated spec) | Confirm: no pre-expiry profit-taking. Only `CRASH_MONETIZE` (δ ≤ −0.80 OR ≥5× debit) or `ROLL_ELIGIBLE` at DTE ≤ 5; `evaluate_pp` in ExitSignalEngine governs |
| Collar exit sequencing — short call stop | Undefined | Close short call + long put atomically via `OverlayCloser.close_collar_all` (preserves hedge integrity); never close call in isolation |
| Collar exit sequencing — long put profit | Undefined | Hold put (insurance). Only rebalance on `ROLL_ELIGIBLE` (DTE ≤ 5 + base DTE > 10) or full close via `OverlayCloser`; per-leg exits forbidden |
| Static vs regime-conditioned exits (Phase 0) | Static (implicit) | Confirm static for Phase 0 (6–12 cycles). Regime-conditioning only after ≥12 clean cycles to avoid confounding entry/exit variables |
| Automation tier for Phase 0 paper trading | None (discretionary) | Tier 1 (EOD signal detection in `paper_3track_snapshot.py` + `ExitSignalEngine`). Tier 2 deferred until full chain fetch per leg is reliable |
| exit_signal storage format | None | `exit_signal` enum column on `paper_leg_snapshots` (values: NONE | PROFIT_TARGET | HARD_STOP | DELTA_BREACH | …) + separate `paper_exit_events` table (already implemented) for full audit history |

**Dissenting Notes (Q2 – highest variance)**  
Minority view: premium-multiple (2×) should be primary for CC/Collar short calls because delta requires live chain fetch that Tier 1 EOD does not yet guarantee. Majority (adopted) keeps delta primary with premium backstop and dual-signal audit fields; minority position scheduled for post-Phase-0 validation once 12+ cycles exist.  

All recommendations are already codified in `src/strategy/exit_signals.py` (`evaluate_cc`, `evaluate_pp`, `evaluate_roll_overlay`, `evaluate_proxy_delta`) and `src/paper/overlay_closer.py`, ensuring mechanical, auditable exits for Phase 0 paper tracking.

### deepseek/deepseek-r1-0528

### Council Recommendations on NiftyShield Exit Rules

---

#### **Q1 — Profit Target Rules**
| Aspect | Current | Recommendation |
|--------|---------|---------------|
| **CC profit target %** | Undefined | **50% decay** (same as CSP) |
| **CC profit target floor** | Undefined | **₹15 absolute floor**<br>- Credits < ₹15 skip profit target (hold to DTE ≤ 5) |
| **PP exit rule** | "Hold to expiry" | **No profit-taking**<br>- Exit only if:<br>  a) Deep ITM (δ ≤ -0.80)<br>  b) Expiry (Nifty between strikes: monetize long put) |
| **DTE override** | None | **Close all sell legs at DTE ≤ 5**<br>- Supersedes profit targets |

#### **Q2 — Loss Stop Mechanism**
| Aspect | Current | Recommendation |
|--------|---------|---------------|
| **CC loss stop** | Undefined | **Delta primary + premium backstop**<br>- δ ≥ 0.55 (ACTION)<br>- Mark ≥ 2.5× credit (ACTION) |
| **Threshold rationale** | - | Call-side asymmetry:<br>- 0.55δ (vs CSP 0.45) = faster exit for calls<br>- 2.5× (vs CSP 1.75×) = wider tolerance for IV spikes |
| **Collar net P&L stop** | Undefined | **Leg-independent evaluation**<br>- Short call: evaluate standalone<br>- Long put: never stopped for loss |

#### **Q3 — Collar Exit Sequencing**
| Scenario | Recommendation |
|----------|---------------|
| **Short call stop fires** | 1. Close short call immediately<br>2. Long put remains active (insurance still needed)<br>3. Underlying holds |
| **Long put deep ITM** | 1. Never exit for profit<br>2. Monetize ONLY if paired with short call close<br>3. Exception: δ ≤ -0.80 (liquidity risk) → close put |
| **Mid-cycle rebalancing** | Not permitted in Phase 0 |

#### **Q4 — Regime Conditioning**
| Aspect | Recommendation |
|--------|---------------|
| **Phase 0 approach** | **Static thresholds**<br>- No IVR/VIX adaptation<br>- Isolate core rule performance |
| **Adaptive trigger** | ≥24 paper cycles (Phase 1+)<br>- Use IVR at entry (logged)<br>- Never spot VIX at exit |
| **Low-IVR handling** | Absolute floor (₹15) suffices<br>- No DTE compression |

#### **Q5 — Automation & Storage**
| Aspect | Recommendation |
|--------|---------------|
| **Monitoring tier** | **Tier 1 (EOD-only)**<br>- Intraday gaps acceptable for paper<br>- Add delta to EOD snapshot |
| **Signal storage** | **`exit_signal` column in `paper_leg_snapshots`**<br>Enum: `NONE` \| `PROFIT_TARGET` \| `DELTA_STOP` \| `PREMIUM_STOP` \| `DTE_FORCED` \| `DEEP_ITM` |
| **Telegram payload** | Add `"valid_actions": ["CLOSE_CC"]` to `SignalEvent` |

---

### Dissenting Notes
**Minority view on Q2 (Delta vs Premium Stop):**  
- *Position:* Premium-multiplier should be sole trigger  
- *Rationale:* Delta requires reliable real-time chains → unavailable in 15% of EOD snapshots  
- *Compromise:* Implement both but log `actual_rule_used` in exit events for post-phase analysis  

**Minority view on PP exit:**  
- *Position:* Allow profit-taking at 5× premium if bid-ask < 5%  
- *Rationale:* Insurance value decays post-crash; capital reuse improves IRR  
- *Override:* Rejected - violates "never remove protection early" principle  

---

### Implementation Guide
1. **Extend `ExitSignalEngine`**  
   ```python
   # Q1/Q2: CC rules
   @classmethod
   def evaluate_profit_target_cc(
       cls,
       ltp: Decimal,
       entry_credit: Decimal,
       dte: int
   ) -> list[ExitSignalResult]:
       if entry_credit < _CC_MIN_ENTRY_CREDIT and dte > 5:
           return []  # Skip profit check below floor
       threshold = entry_credit * _PROFIT_TARGET_RETENTION
       if ltp <= threshold:
           return [ExitSignalResult(...)]

   # Q2: CC loss stop
   @classmethod
   def evaluate_loss_stop_cc(
       cls,
       delta: float | None,
       current_mark: Decimal,
       entry_credit: Decimal,
       dte: int
   ) -> list[ExitSignalResult]:
       # Delta stop (primary)
       if delta and delta >= 0.55:
           return [ExitSignalResult(exit_signal="DELTA_STOP", ...)]
       
       # Premium backstop
       if current_mark >= entry_credit * Decimal("2.5"):
           return [ExitSignalResult(exit_signal="PREMIUM_STOP", ...)]
   ```

2. **EOD Snapshot Upgrade**  
   ```python
   # In paper_3track_snapshot.py
   for leg in paper_positions:
       if leg.role == "overlay_cc":
           signals += ExitSignalEngine.evaluate_profit_target_cc(...)
           signals += ExitSignalEngine.evaluate_loss_stop_cc(...)
       
       if leg.role == "overlay_pp" and leg.delta <= -0.80:
           signals += [ExitSignalResult(exit_signal="DEEP_ITM", ...)]
   ```

3. **Schema Change**  
   ```sql
   ALTER TABLE paper_leg_snapshots
   ADD COLUMN exit_signal TEXT CHECK(exit_signal IN (
       'NONE', 'PROFIT_TARGET', 'DELTA_STOP', 'PREMIUM_STOP', 
       'DTE_FORCED', 'DEEP_ITM', 'HARD_STOP'
   ));
   ```

---

### Summary Table
| Decision | Current | Recommendation |
|----------|---------|---------------|
| **CC profit target %** | Undefined | 50% decay |
| **CC profit target floor** | Undefined | ₹15 absolute |
| **CC loss stop** | Undefined | δ≥0.55 **OR** mark≥2.5× credit |
| **PP exit rule** | Hold to expiry | Exit only: δ≤-0.80 **OR** expiry monetization |
| **Collar short call stop** | Undefined | Close call only; put remains |
| **Collar long put exit** | Undefined | Never for profit; δ≤-0.80 only |
| **Regime conditioning** | Static | Remain static in Phase 0 |
| **Automation tier** | None | Tier 1 (EOD-only) |
| **Signal storage** | None | Enum column in `paper_leg_snapshots` |

## Aggregate Rankings (Stage 2 Peer Review)

- openai/gpt-5.5-20260423: avg rank 1.25 (4 votes)
- x-ai/grok-4.3-20260430: avg rank 2.25 (4 votes)
- google/gemini-3.1-pro-preview-20260219: avg rank 2.5 (4 votes)
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