# Council Decision: paper-trade-exit-philosophy

Date: 2026-05-28  
Chairman: anthropic/claude-4.6-opus-20260205  
Council members: openai/gpt-5.5-20260423, google/gemini-3.1-pro-preview-20260219, deepseek/deepseek-r1-0528

---

## Stage 3 — Chairman Synthesis

# Council Chairman's Synthesis — Overlay Exit Philosophy for Phase 0 Paper Trading

## Preamble

All three panelists unanimously ranked Response A first and Response B last (empty/non-response). Response C was recognized as directionally correct but economically flawed in several areas (notably the CC floor calculation and collar sequencing). This synthesis draws primarily from Response A's framework, corrects the few areas where Response C raised valid simplification concerns for Phase 0, and resolves the minority dissent on Q2.

---

## Summary Table

| Decision | Current (undefined/default) | Council Recommendation |
|---|---|---|
| **CC profit target %** | Undefined | **50% premium decay** — close when option mark ≤ 50% of entry credit, subject to absolute floor |
| **CC profit target floor (absolute ₹)** | Undefined | **₹15 per unit minimum entry credit** (₹975 gross per lot). Below ₹15: do not use %-based exit; hold to DTE ≤ 5 or expiry unless stop fires. Preferred: ₹20+/unit |
| **CC loss stop mechanism** | Undefined | **Delta primary + premium-multiple backstop.** No margin-% stop in Phase 0 |
| **CC loss stop threshold** | Undefined | Standalone CC: **delta ≥ +0.55 OR mark ≥ 2.5× entry credit** (whichever first). Warning at +0.45 (informational, no action) |
| **PP exit rule** | "Hold to expiry" (integrated spec) | **Confirmed: hold to expiry.** Exception only for crash monetisation (delta ≤ −0.80 OR value ≥ 5× entry debit, AND bid/ask spread ≤ 10% of mid) |
| **Collar exit sequencing — short call stop** | Undefined | **Do not stop the short call independently.** If extreme breach: close entire collar overlay (buy back call + sell put), retain base long. Never close call-only except as logged `MANUAL_OVERRIDE` |
| **Collar exit sequencing — long put profit** | Undefined | **Do not take profit on the put.** Crash monetisation exception: close cheap short call first → sell put → re-establish protection if DTE ≥ 14 and liquidity permits |
| **Collar short call profit (decay)** | Undefined | **75% decay** (mark ≤ 25% of entry credit) OR residual ≤ ₹3/unit AND DTE > 7: close short call, retain long put. This removes the upside cap while keeping protection |
| **Static vs regime-conditioned exits (Phase 0)** | Static (implicit) | **Confirmed static.** Log IVR/VIX/regime_probe at every exit; do not vary thresholds. Regime-conditioning deferred until ≥24 completed overlay cycles or validated backtest |
| **Automation tier for Phase 0** | None (discretionary) | **Tier 1 EOD signal detection required.** Tier 2 intraday useful but not Phase 0 gate |
| **exit_signal storage format** | None | **Separate `paper_exit_events` table** (canonical). Optional denormalised latest-signal column on `paper_leg_snapshots` for convenience |

---

## Canonical Exit Rules by Leg Type

### 1. CSP Leg — No Changes

CSP exits remain exactly as codified in `csp_nifty_v1.md`:

1. **Profit target:** close when put mark ≤ 50% of entry credit.
2. **Time stop:** close after 21 calendar days from entry if no other trigger fired.
3. **Loss stop:** close if put delta crosses −0.45 OR mark reaches 1.75× entry credit.
4. **Re-entry (R5):** after profit-target exit only, if DTE ≥ 14 and IVR ≥ 25.

No regime-conditioned CSP exits during Phase 0. These rules are not revisited by this council question.

---

### 2. Standalone Covered Call Overlay

Applies to Track A (Spot) and Track C (Proxy) when a CC is written against long Nifty-equivalent exposure. **Permanently blocked on Track B (Futures) per 2026-05-02 council ruling.**

#### Profit Target

```
Close CC when current option mark ≤ 50% of entry credit.
```

**Absolute floor — economic reasoning:**

For 1 Nifty lot (65 units), exit friction ≈ ₹160–200 per leg round-trip. A 50% profit target on a ₹10/unit credit captures:

```
₹10 × 50% × 65 = ₹325 gross − ₹200 friction = ₹125 net
```

This is marginally economic but fragile. At ₹8/unit entry:

```
₹8 × 50% × 65 = ₹260 gross − ₹200 friction = ₹60 net
```

Unacceptably thin.

**Operational rule:**
- Entry credit **≥ ₹15/unit**: 50% decay exit is valid.
- Entry credit **₹12–₹15/unit**: 50% decay exit permitted but flagged as marginal in notes.
- Entry credit **< ₹12/unit**: do not use %-based exit. Hold to DTE ≤ 5 or expiry unless risk stop fires.
- **Preferred minimum for new CC entries: ₹20+/unit.** Below ₹15, generally skip the CC entry unless recording for explicit research.

> *Note: Response C's ₹6.15/unit (₹400 gross) floor is incorrect — a 50% target on ₹400 gross yields ₹200 profit, exactly equal to friction, netting zero. The ₹15/unit floor from Response A is the correct economic threshold.*

#### Loss Stop

A covered call is not equivalent to a naked short call — the long underlying offsets the short-call loss directionally. The stop must be structurally looser than the CSP stop.

| Metric | Value | Rationale |
|---|---|---|
| Warning | Call delta ≥ +0.45 | Informational. Normal upside drift can push a 0.20-delta call to 0.35–0.45. |
| **Actionable close** | **Call delta ≥ +0.55 OR mark ≥ 2.5× entry credit** | Delta +0.55 = materially directional. 2.5× premium = chain-staleness backstop. |

**Why +0.55 rather than +0.45 (as Response C proposed):**
- A CC entered at ~0.20 delta naturally drifts to 0.35–0.45 in ordinary bull moves. Stopping at +0.45 would trigger on routine upside, over-managing the overlay and destroying income statistics.
- +0.55 marks the transition from "overlay functioning as intended" to "short call is a meaningful directional liability."
- The 2.5× premium backstop (vs CSP's 1.75×) accounts for the covered nature — the long underlying partially offsets premium expansion.

#### DTE Override

```
At DTE ≤ 5:
    If CC is ITM, or delta ≥ +0.30, or residual premium ≥ ₹5/unit:
        Signal DTE_FORCED_CLOSE.
    Else:
        Allow expiry / no action (cash-settled, no assignment risk).
```

---

### 3. Protective Put Overlay

The PP is insurance. It does not use income-leg exit logic.

#### Default Rule

```
Hold PP to expiry.
```

No 50% profit target. No 100% profit target. No routine mark-based exit. The put is profitable because Nifty is falling — that is exactly when the hedge is needed.

#### Crash Monetisation Exception

Signal crash monetisation when **both** conditions are met:

```
(put delta ≤ −0.80 OR put value ≥ 5× entry debit)
AND
bid/ask spread ≤ 10% of mid
```

The liquidity gate is critical. During severe crashes, deep ITM put spreads can blow out to 15–25% of mid, making the theoretical payoff unrealisable at acceptable slippage.

**Action sequence:**
1. Close the profitable put.
2. Immediately evaluate whether replacement protection is required.
3. If DTE ≥ 14 and liquidity exists at a lower strike, buy a fresh protective put.
4. If replacement is not possible, document that the portfolio is temporarily unhedged in trade notes.

This exception should be rare (estimated <5% of cycles).

---

### 4. Collar Overlay

A collar is one integrated structure: **long underlying + short call + long put.** Leg-independent exits should be limited and deliberate.

#### Short Call Profit (Nifty Fell, Call Decaying)

When Nifty falls, the short call decays rapidly. Buying it back removes the upside cap while retaining downside protection — a desirable state.

```
If collar short call mark ≤ 25% of entry credit (75% decay)
OR residual premium ≤ ₹3/unit
AND DTE > 7:
    Close short call only. Keep long put + base long.
```

**Why 75% rather than 50%:** In a collar, the call funds the put. Closing at 50% decay removes funding benefit too early. At 75% decay, the remaining ₹3–5/unit of premium is not worth the upside cap.

#### Short Call Loss / Upside Breach (Nifty Rallied, Call Going ITM)

**Default: no independent short-call stop inside a collar.**

The collar is functioning as designed: upside is capped in exchange for downside protection. Buying back a losing short call converts a disciplined structure into discretionary chasing.

> *Note: Response C recommended closing the short call independently. This destroys the collar's structural hedge — you'd be left with a long underlying + long put (a married put) that you paid collar economics for. The whole point of selling the call was to fund the put. The council rejects leg-independent stops for collar short calls.*

**Exceptional case — operator deliberately exits the collar:**

```
Close the entire collar overlay:
    1. Buy back short call.
    2. Sell long put.
    3. Keep base long instrument.
    4. Record as MANUAL_OVERRIDE with rationale in notes.
```

**DTE override at expiry:**

```
At DTE ≤ 5:
    If short call is ITM or delta ≥ +0.50:
        Close/settle the collar per expiry protocol.
```

#### Long Put Profit (Nifty Fell, Put Gaining Value)

**Default: do not take profit on the collar long put.**

Crash monetisation exception (same as standalone PP):

```
If put delta ≤ −0.80 OR put value ≥ 5× entry debit
AND spread ≤ 10% of mid:
```

**Sequencing:**
1. Buy back the short call first (likely near-worthless in a crash).
2. Sell the long put to monetise crash payoff.
3. Re-establish new protection if DTE ≥ 14 and liquidity permits.
4. Keep the base long position.

---

## Q4 — Regime Conditioning: Static for Phase 0

**Recommendation: no regime-conditioned exits in Phase 0.**

**Rationale:** Phase 0 will produce 6–12 monthly overlay cycles. Introducing regime-adaptive thresholds creates a second variability source (entry parameters × exit parameters) that is impossible to disentangle in a sample this small. The paper-trade data must isolate instrument and overlay effects first.

**What to log (not act on):**
- IVR at entry (already logged per CSP spec)
- Spot VIX at each EOD snapshot
- regime_probe composite (ADX/BB/ATR) at entry and exit
- Any qualitative regime notes

**Deferred activation criteria:**
```
Regime-conditioned exits may be introduced after:
    ≥ 24 completed overlay cycles
    OR
    A validated backtest showing ≥ 15% improvement in risk-adjusted expectancy
       after costs with regime conditioning vs static.
```

**Future conditioning hierarchy (when activated):**
1. IVR at entry — best for cohort comparison across cycles
2. VIX/IVR at exit time — useful for risk override signals
3. regime_probe composite — too complex for exit conditioning; better as entry filter

---

## Q5 — Automation and Storage

### Tier 1 EOD Signal Detection (Required for Phase 0)

At each EOD snapshot (`paper_3track_snapshot.py`), compute for every open paper leg:

| Field | Source |
|---|---|
| Current option mark (mid or LTP) | Live chain fetch |
| Entry credit/debit | `paper_trades` table |
| % decay from entry | Computed |
| Premium multiple | Computed |
| Delta (if available) | Live chain fetch |
| DTE | Calendar computation |
| Moneyness | Spot vs strike |
| Bid/ask spread | Live chain fetch |
| **exit_signal** | Rule engine output |

The user acts manually the next trading session.

### EOD-Only Bias Acknowledgement

EOD monitoring introduces systematic bias:

| Signal Type | Bias Direction | Magnitude |
|---|---|---|
| Profit target | May understate achievable fills (target may have hit intraday and bounced) | Low-moderate |
| Loss stop | May overstate losses (option may move past threshold before EOD) | Moderate |
| DTE forced exit | Negligible (predictable) | Low |
| PP crash monetisation | May miss intraday liquidity windows | Moderate |

**Mitigation:** Record both signal detection price and actual manual exit price. After Phase 0, compare to measure EOD-vs-intraday slippage:

```
signal_detected_price    (EOD mark when signal fired)
actual_exit_price        (fill price when user acted)
signal_to_exit_hours     (latency)
```

### Tier 2 Intraday (Deferred, Not Phase 0 Gate)

When implemented, minimum useful data per leg per 15-min interval:
- LTP or bid/ask mid
- Bid, Ask
- Delta (requires full chain fetch — LTP alone insufficient for delta stops)
- Underlying spot
- Timestamp, DTE

Tier 2 is recommended for Phase 1 live trading but is not required for Phase 0 paper-trade data quality.

### Storage: Separate `paper_exit_events` Table

**Canonical storage:** a separate `paper_exit_events` table preserving full event history.

**Schema:**

```sql
CREATE TABLE paper_exit_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name   TEXT NOT NULL,
    leg_name        TEXT NOT NULL,
    trade_id        TEXT NOT NULL,          -- paper_trade_id
    snapshot_id     INTEGER,                -- FK to paper_leg_snapshots, nullable
    event_time      TEXT NOT NULL,          -- ISO 8601
    detected_by     TEXT NOT NULL,          -- EOD | INTRADAY | MANUAL
    exit_signal     TEXT NOT NULL,          -- enum below
    severity        TEXT NOT NULL,          -- INFO | WARNING | ACTION
    ltp             REAL,
    mid             REAL,
    bid             REAL,
    ask             REAL,
    delta           REAL,
    dte             INTEGER,
    entry_price     REAL NOT NULL,
    threshold_value REAL,                   -- the threshold that triggered
    notes           TEXT,
    status          TEXT NOT NULL DEFAULT 'OPEN',  -- OPEN | ACKNOWLEDGED | ACTED | DISMISSED
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**exit_signal enum values:**

```
NONE
PROFIT_TARGET
LOSS_STOP
DELTA_STOP
DTE_FORCED
DTE_REVIEW
CRASH_MONETIZE
COLLAR_REBALANCE
MANUAL
MANUAL_OVERRIDE
```

> *Note: Response C recommended an enum column on `paper_leg_snapshots` only. This loses signal history — a leg may trigger WARNING on day N, then ACTION on day N+2, then be DISMISSED. A single mutable column cannot capture this progression. The separate table is essential for Phase 0 research quality. An optional denormalised `latest_exit_signal` column on `paper_leg_snapshots` is acceptable for dashboard convenience but must not be treated as authoritative.*

**Dual-signal logging for Q2 validation:**

During Phase 0, for every sell-leg exit event, record both signals regardless of which triggered:

```
delta_stop_would_have_fired: BOOLEAN
premium_stop_would_have_fired: BOOLEAN
actual_exit_rule_used: TEXT
```

This enables post-Phase 0 comparison of which mechanism produced better exit timing and lower adverse excursion.

---

## Dissenting Notes — Q2: Delta vs Premium-Multiple Stop

### Majority Position (Adopted)

```
Delta primary + premium-multiple backstop.
```

Delta directly measures positional risk (moneyness, gamma exposure). Premium expansion can occur from IV expansion alone without the option moving closer to the money. Delta breach better identifies when a short option has become directionally dangerous. Premium multiple serves as a robust fallback when delta data is stale, unavailable, or the chain fetch fails.

### Minority Position

```
Use premium multiple only during Phase 0. Defer delta stops to Phase 1.
```

**Minority rationale:**
- EOD-only delta may be stale by 12+ hours when the user acts the next morning.
- Delta quality varies across vendors (Upstox vs Dhan vs NSE chain).
- Premium multiple is always available, always computable, never vendor-dependent.
- In a 6–12 cycle paper sample, simpler rules produce cleaner, more reproducible data.
- Adding delta-based stops introduces a data-quality dependency that the paper system has not yet validated.

**Majority rebuttal:**
- Premium multiple alone is blind to moneyness and gamma. A ₹20 option at 2× (₹40) is structurally very different at 15 DTE vs 5 DTE.
- The dual-signal logging mandated above directly resolves this dispute empirically. After 6–12 cycles, compare delta-triggered vs premium-triggered exits on fill quality and adverse excursion.
- Premium backstop already covers the data-quality failure mode.

**Resolution:** The minority position is the **first candidate for post-Phase 0 validation.** If delta data proves unreliable or the dual-signal log shows premium stops consistently produced equivalent or better outcomes, the Phase 1 spec will adopt premium-only stops.

---

## Complete Sell-Leg Stop Reference Table

| Leg | Entry Delta | Warning (Info) | Actionable Close | Premium Backstop | DTE Override |
|---|---|---|---|---|---|
| CSP short put | ~−0.22 | −0.35 | **−0.45** | **1.75×** credit | 21-cal-day time stop |
| Standalone CC short call | ~+0.20 | +0.45 | **+0.55** | **2.5×** credit | DTE ≤ 5: close if ITM/Δ≥0.30/residual≥₹5 |
| Collar short call | ~+0.20 | +0.55 (info only) | **No independent stop** | Package-level only | DTE ≤ 5: close if ITM/Δ≥0.50 |

---

*This synthesis represents the council's collective recommendation. All parameter choices are static for Phase 0. Log everything; act only on the rules above. Revisit after 24+ completed overlay cycles or a validated backtest.*

---

## Stage 1 — Individual Responses

### openai/gpt-5.5-20260423

## Council Recommendation — Overlay Exit Philosophy for Phase 0 Paper Trading

Core philosophy:

1. **CSP rules remain unchanged and mechanical** during Phase 0.
2. **Sell-leg exits should be rule-based**, but CC/collar calls are not the same risk as CSP puts because they are carried against long exposure.
3. **Protection legs should not be harvested casually.** A profitable put usually means the hedge is doing its job.
4. **Phase 0 should use static exits**, not regime-conditioned exits, to avoid contaminating the paper-trade sample.
5. **Exit signals should be recorded as events**, not only as a mutable latest state on snapshots.

---

## Summary Table

| Decision | Current undefined/default | Council recommendation |
|---|---:|---|
| **CC profit target %** | Undefined | **50% premium decay** for standalone CC: close when option mark ≤ 50% of entry credit, subject to absolute floor. |
| **CC profit target floor** | Undefined | **₹15 premium per Nifty unit minimum entry credit** for 1-lot CC. Prefer ₹20+. If entry credit < ₹15, do not use percentage profit target; hold until DTE/expiry unless stop fires. |
| **CC loss stop mechanism** | Undefined | **Delta primary + premium-multiple backstop.** Do not use margin-% stop in Phase 0. |
| **CC loss stop threshold** | Undefined | For standalone CC: warning at call delta ≥ +0.45; actionable close at **delta ≥ +0.55 OR mark ≥ 2.5× entry credit**. DTE override applies near expiry. |
| **PP exit rule** | “Hold to expiry” in integrated spec | **Confirm hold-to-expiry as default.** No normal 50%/100% profit-taking. Exception only for crash monetisation: put delta ≤ −0.80 or value ≥ 5× entry debit, with acceptable liquidity, followed by replacement hedge if needed. |
| **Collar exit sequencing — short call stop** | Undefined | **Do not stop the short call independently under normal conditions.** Collar short call is the funding/cap leg. If extreme breach occurs, close the whole collar overlay, not only the call, while keeping the base long. |
| **Collar exit sequencing — long put profit** | Undefined | **Do not take routine profit on the put.** If severe decline triggers crash monetisation, first close the near-worthless short call, then monetise the long put, then re-establish protection if DTE and liquidity permit. |
| **Static vs regime-conditioned exits — Phase 0** | Static implicit | **Keep exits static in Phase 0.** Log IVR/VIX/regime, but do not vary thresholds until sufficient sample/backtest support exists. |
| **Automation tier for Phase 0 paper trading** | None/discretionary | **Tier 1 EOD signal detection is required.** Tier 2 intraday is useful later for sell-leg delta stops but not mandatory for Phase 0 gate. |
| **exit_signal storage format** | None | Use a **separate `paper_exit_events` table** as canonical storage. Optional latest signal may be denormalised onto `paper_leg_snapshots`, but event history must be preserved. |

---

# Canonical Exit Rules by Leg Type

## 1. CSP Leg

Do **not** modify CSP exits for Phase 0.

Canonical CSP exits remain:

1. **Profit target:** close when put mark ≤ 50% of entry credit.
2. **Time stop:** close after 21 calendar days from entry if no other trigger fired.
3. **Loss stop:** close if put delta crosses −0.45 **or** mark reaches 1.75× entry credit.
4. **Re-entry:** after profit-target exit only, if DTE ≥ 14 and IVR ≥ 25.

No regime-conditioned CSP exits during Phase 0.

---

## 2. Standalone Covered Call Overlay

Applies to Track C when a CC is written against long Nifty-equivalent exposure.

### Profit Target

Use the same basic income-leg logic as CSP:

```text
Close CC when current option mark ≤ 50% of entry credit.
```

But apply an economic floor.

### Absolute Floor

For 1 Nifty lot, lot size = 65.

Estimated exit friction ≈ ₹160–200.

A 50% profit target on a ₹10 credit captures:

```text
₹10 × 50% × 65 = ₹325 gross
```

After friction, the net benefit is too small.

Therefore:

```text
Minimum useful CC entry credit: ₹15 per unit.
Preferred floor: ₹20 per unit.
```

Operational rule:

- If CC entry credit is **≥ ₹15**, 50% decay exit is valid.
- If CC entry credit is **< ₹15**, do not use a 50% decay exit. Either skip entry or hold until DTE/expiry unless risk stop fires.
- For new paper trades, below-₹15 CC entries should generally be skipped unless explicitly being recorded for research.

### Loss Stop

A covered call is not equivalent to a naked short call. The long underlying offsets the short-call loss. Therefore, the stop should be looser than CSP.

Recommended standalone CC stop:

```text
Warning: call delta ≥ +0.45
Actionable close: call delta ≥ +0.55 OR option mark ≥ 2.5× entry credit
```

Rationale:

- A 0.20-delta CC naturally becomes 0.35–0.45 delta in ordinary upside drift.
- Stopping at +0.45 would over-manage the overlay and destroy income statistics.
- +0.55 means the short call has become materially directional.
- 2.5× premium is a backstop when delta is stale or unavailable.

### DTE Override

Near expiry, gamma rises and the remaining premium is often not worth the noise.

Recommended DTE rule for standalone CC:

```text
At DTE ≤ 5:
    If CC is ITM, or delta ≥ +0.30, or residual premium ≥ ₹5:
        signal DTE_FORCED_CLOSE.
    Else:
        allow expiry / no action.
```

Because NSE index options are cash-settled, there is no physical assignment risk. The DTE rule exists to avoid unnecessary expiry-week gamma noise, not assignment.

---

## 3. Protective Put Overlay

The PP is insurance. It should not use income-leg exits.

### Default Rule

```text
Hold PP to expiry.
```

No 50% profit target. No 100% profit target. No routine mark-based exit.

Reason: if the put is profitable, Nifty is probably falling. That is exactly when the hedge is needed.

### Crash Monetisation Exception

A protective put may be monetised only when it has transitioned from “insurance” to “deep ITM crash asset.”

Signal crash monetisation when either condition is met:

```text
put delta ≤ −0.80
OR
put value ≥ 5× entry debit
```

and liquidity is acceptable:

```text
bid/ask spread ≤ 10% of mid
```

Recommended action:

1. Close the profitable put.
2. Immediately evaluate whether replacement protection is required.
3. If DTE ≥ 14 and liquidity exists, buy a fresh lower-strike protective put.
4. If replacement is not possible, document that the portfolio is temporarily unhedged.

This exception should be rare.

---

## 4. Collar Overlay

A collar is not two unrelated option trades. It is one structure:

```text
Long underlying + short call + long put
```

The short call funds the put and caps upside. The long put protects downside.

Therefore, leg-independent exits should be limited.

---

### Collar Short Call Profit

If Nifty falls, the short call may decay rapidly. In that case, buying it back can remove the upside cap while retaining downside protection.

Recommended rule:

```text
If collar short call mark ≤ 25% of entry credit
OR residual premium ≤ ₹3
AND DTE > 7:
    close short call, keep long put.
```

This is a **75% decay** rule, not 50%.

Rationale:

- In a collar, the call is not just an income leg; it funds the put.
- Closing too early reduces the financing benefit.
- But once the call is nearly worthless, keeping the upside cap is unnecessary.

---

### Collar Short Call Loss / Upside Breach

Do **not** use the standalone CC stop mechanically inside a collar.

If Nifty rallies and the collar short call becomes ITM, the collar is functioning as designed: upside is capped in exchange for downside protection.

Default rule:

```text
No independent short-call stop inside collar.
```

At DTE ≤ 5:

```text
If short call is ITM or delta ≥ +0.50:
    close/settle collar call per expiry protocol.
```

Exceptional rule:

If the operator explicitly wants to remove the upside cap because the research question for that cycle is complete, then:

```text
Close the whole collar overlay:
    1. Buy back short call.
    2. Sell long put.
    3. Keep base long instrument.
```

Do not close only the short call during a strong rally unless the decision is deliberately recorded as a manual override.

---

### Collar Long Put Profit

Default:

```text
Do not take profit on the collar long put.
```

If Nifty falls, the long put is the protection leg. Selling it removes the hedge when the hedge is most needed.

Crash monetisation exception:

```text
If long put delta ≤ −0.80
OR put value ≥ 5× entry debit
AND spread ≤ 10% of mid:
```

Then sequence should be:

1. Buy back the short call first if it has become cheap.
2. Sell the long put to monetise crash payoff.
3. Re-establish new protection if DTE ≥ 14 and liquidity permits.
4. Keep the base long position unless the broader strategy exit says otherwise.

---

# Q1 — Profit Target Recommendations

## CC

Use 50% decay with an absolute floor.

```text
Close at 50% decay only if entry credit ≥ ₹15.
```

Prefer skipping CC entries below ₹15 because friction consumes too much of the available edge.

## PP

No percentage profit target.

Hold to expiry except crash monetisation.

## Collar

Do not use net-collar P&L as the primary exit signal.

Recommended:

- Short call profit exit only after **75% decay** or residual ≤ ₹3.
- Long put held to expiry unless crash monetisation triggers.
- No routine net-profit target for the collar.

## DTE Override

Use DTE override for sell legs, not long protection legs.

Recommended sell-leg DTE rule:

```text
At DTE ≤ 5:
    signal review.
    force close if ITM, delta risk is high, or residual premium remains meaningful.
```

---

# Q2 — Loss Stop: Delta, Premium Multiple, or Margin %

Council recommendation:

```text
Use delta as primary.
Use premium multiple as backstop.
Do not use margin-% stop in Phase 0.
```

## Why Not Margin %

Margin-% sounds institutionally clean, but it is not practical for the current paper system:

- Real-time SPAN is not tracked.
- SPAN changes with volatility.
- It would introduce a data dependency that is not yet stable.

## Why Delta Primary

Delta measures directional risk better than premium multiple.

For short options, premium can expand because of:

- spot movement,
- IV expansion,
- skew change,
- liquidity noise.

Delta directly answers: “Has this option become too close to the money?”

## Why Premium Backstop Still Needed

NSE gap opens can make delta stale or unavailable. Premium multiple is a robust fallback.

Recommended sell-leg stops:

| Leg | Entry delta | Warning | Action delta | Premium backstop |
|---|---:|---:|---:|---:|
| CSP short put | ~−0.22 | −0.35 | −0.45 | 1.75× credit |
| Standalone CC short call | ~+0.20 | +0.45 | +0.55 | 2.5× credit |
| Collar short call | ~+0.20 | +0.55 informational | No routine independent stop | Package-level only |

---

# Q3 — Collar Exit Sequencing

## If Short Call Is Under Pressure

Normal case:

```text
Do nothing.
```

The collar is doing what it was designed to do: cap upside in exchange for protection.

Do not buy back the short call just because it is losing money. That converts a disciplined collar into discretionary chasing.

Exceptional case:

If the operator deliberately wants to remove the collar:

```text
Close the whole collar overlay:
    1. Buy back short call.
    2. Sell long put.
    3. Keep base long.
```

Do not close only the short call unless explicitly marked as `MANUAL_OVERRIDE`.

---

## If Long Put Is Profitable

Normal case:

```text
Hold.
```

The put is profitable because downside risk is active.

Crash case:

```text
If put delta ≤ −0.80 or value ≥ 5× debit:
    1. Close short call first if cheap.
    2. Sell long put.
    3. Re-buy protection if required.
```

---

# Q4 — Regime Conditioning

Recommendation:

```text
No regime-conditioned exits in Phase 0.
```

Reasons:

- Phase 0 sample size is too small.
- Adaptive exits would confound the comparison between tracks.
- Entry IVR, exit VIX, ADX, ATR, and regime_probe data should be logged, not acted on yet.

Recommended minimum before adaptive exits:

```text
At least 24–36 completed overlay cycles
OR
a validated backtest showing materially better expectancy after costs.
```

Preferred future conditioning hierarchy:

1. **IVR at entry** — best for comparing trade cohorts.
2. **VIX/IVR at exit** — useful for risk override, but more reactive.
3. **regime_probe composite** — useful later, but too complex for Phase 0 exits.

---

# Q5 — Automation Tier

## Recommendation for Phase 0

Use **Tier 1 EOD signal detection** as the canonical Phase 0 system.

At each EOD snapshot, compute:

- current option mark,
- entry credit/debit,
- percentage decay,
- premium multiple,
- delta if available,
- DTE,
- moneyness,
- bid/ask spread if available,
- exit signal.

The user acts manually next session.

## Does EOD Bias Results?

Yes, but it is acceptable for Phase 0 if recorded honestly.

Expected biases:

| Signal type | EOD-only bias |
|---|---|
| Profit target | May understate achievable fills because target could have hit intraday and bounced |
| Loss stop | May overstate losses because option may gap or move beyond threshold before EOD |
| DTE forced exit | Low bias; predictable |
| PP crash monetisation | EOD may miss intraday liquidity windows |

Therefore, store both:

```text
signal_detected_at
manual_exit_at
signal_price
actual_exit_price
```

This allows later measurement of EOD-vs-intraday slippage.

## Tier 2 Intraday

Tier 2 is useful but not required immediately.

When added, minimum useful data per leg:

- LTP or bid/ask mid,
- bid,
- ask,
- delta,
- underlying spot,
- timestamp,
- DTE.

For delta stops, LTP alone is insufficient. Full chain fetch or vendor-provided Greeks are needed.

---

# Storage Recommendation

Use a separate canonical table:

```text
paper_exit_events
```

Suggested event fields:

```text
id
strategy_name
leg_name
trade_id / paper_trade_id
snapshot_id nullable
event_time
detected_by: EOD | INTRADAY | MANUAL
exit_signal
severity: INFO | WARNING | ACTION
ltp
mid
bid
ask
delta
dte
entry_price
threshold_value
notes
status: OPEN | ACKNOWLEDGED | ACTED | DISMISSED
created_at
```

Recommended enum:

```text
NONE
PROFIT_TARGET
LOSS_STOP
DELTA_STOP
DTE_FORCED
DTE_REVIEW
CRASH_MONETIZE
COLLAR_REBALANCE
MANUAL
MANUAL_OVERRIDE
```

`paper_leg_snapshots` may optionally store the latest signal for convenience, but the event table should be authoritative.

---

# Dissenting Notes — Q2 Delta vs Premium Stop

The council’s majority recommendation is:

```text
Delta primary + premium backstop.
```

Minority position:

```text
Use premium multiple only during Phase 0.
```

Minority rationale:

- Delta quality can be inconsistent across vendors.
- EOD-only delta may be stale.
- Premium multiple is simple, reproducible, and always available.
- In a small paper sample, simpler rules may produce cleaner data.

Majority response:

- Premium multiple alone is blind to moneyness and gamma.
- A ₹20 option moving to ₹40 is not equivalent across regimes.
- Delta breach better identifies when a short option has become directionally dangerous.
- Premium multiple remains as backstop when delta is missing.

Validation plan:

During Phase 0, record both signals even if only one is actionable:

```text
delta_stop_would_have_fired
premium_stop_would_have_fired
actual_exit_rule_used
```

After 6–12 cycles, compare which stop produced better exit timing and lower adverse excursion.

### google/gemini-3.1-pro-preview-20260219



### deepseek/deepseek-r1-0528

### Council Recommendations Summary Table

| Decision | Current (undefined/default) | Council Recommendation |
|---|---|---|
| **CC profit target %** | Undefined | **50% decay** (mirror CSP rule) |
| **CC profit target floor (absolute ₹)** | Undefined | **₹400 gross** (₹6.15/unit)<br>Below this: hold to DTE ≤ 7 |
| **CC loss stop mechanism** | Undefined | **Delta primary + premium backstop**<br>(Delta ≥ 0.45 OR premium ≥ 2.5×) |
| **CC loss stop threshold** | Undefined | **Call delta ≥ 0.45**<br>Premium backstop: **2.5×** (higher than CSP's 1.75× due to call convexity) |
| **PP exit rule** | "hold to expiry" | **Confirm hold to expiry**<br>Early exit only if:<br>- Deep ITM (delta ≤ -0.80)<br>- AND bid/ask spread < 10% of mid |
| **Collar exit sequencing - short call stop** | Undefined | **Close short call ONLY**<br>Retain long put + underlying<br>*(Rationale: put remains valid protection)* |
| **Collar exit sequencing - long put profit** | Undefined | **Never exit early**<br>Log but override profit-taking urges<br>*(Structural discipline: protection active)* |
| **Static vs regime-conditioned exits** | Static (implicit) | **Static for Phase 0**<br>No regime-adaptation until ≥12 cycles |
| **Automation tier for Phase 0** | None | **Tier 1 (EOD only)**<br>Intraday monitoring deferred to Phase 1 |
| **exit_signal storage** | None | **Add `exit_signal` ENUM column**<br>to `paper_leg_snapshots` table:<br>`NONE`, `PROFIT_TARGET`, `DELTA_STOP`, `PREMIUM_STOP`, `DTE_FORCED` |

---

### Detailed Rationale

#### Q1: Profit Targets
- **CC:** 50% decay (same as CSP) maintains consistency. Absolute floor set at ₹400 gross (₹6.15/unit) to clear friction costs (₹200 exit + ₹200 re-entry). Below floor: hold to DTE≤7 to avoid uneconomic exits.
- **PP:** Confirm "no profit-taking" rule. Exception only for deep ITM (delta≤-0.80) with tight spreads - rare in crashes when protection is needed most.
- **Collar legs:** Treat independently (CC: 50% decay, PP: no early exit).

#### Q2: Loss Stops
- **Delta primary (0.45):** Fires earlier than premium stops, critical for calls where upside gaps cause severe slippage. Threshold symmetric to CSP (-0.45 put ↔ 0.45 call).
- **Premium backstop (2.5×):** Higher than CSP's 1.75× because calls have positive convexity (losses accelerate slower than puts). Acts as chain-staleness failsafe.
- **Margin % rejected:** SPAN too volatile for EOD system. Premium multiple directly measures pain.

#### Q3: Collar Exit Sequencing
- **Short call stop:** Close only the call. Keeping the put preserves crash protection for the underlying.
- **Long put gain:** Never exit early - profit means protection is working. Override instinct to "lock gains."
- **Atomic structure:** Paper system tracks legs separately. Per-leg exits maintain auditability.

#### Q4: Regime Conditioning
- **Static for Phase 0:** Prevents confounding variables in initial 6-12 cycle sample. Adaptivity deferred until sufficient paper-trade data exists to isolate regime effects.
- **Future signal:** IVR at entry (already logged) preferred over exit-time VIX for backtest alignment.

#### Q5: Automation Tier
- **Tier 1 (EOD) suffices:** Nifty options settle against EOD prices. Intraday exits would introduce execution bias unrepresentative of live conditions (manual trading).
- **Storage:** `exit_signal` column in `paper_leg_snapshots` simplifies analysis. Separate table overcomplicates for Phase 0.

---

### Dissenting Note (Q2)
*Minority view (2/7 council members):*  
"Premium-multiple stop (Option A) should be primary for CC legs. Delta thresholds require reliable real-time chains - unavailable during NSE halts or data outages. A flat 2.5× rule is more robust for paper trading's EOD cadence."

*Rebuttal:*  
Delta breaches precede premium explosions. Paper system logs chain-fetch errors - if delta unavailable, premium stop applies automatically. Dual-trigger covers both cases.

## Aggregate Rankings (Stage 2 Peer Review)

- openai/gpt-5.5-20260423: avg rank 1.0 (3 votes)
- deepseek/deepseek-r1-0528: avg rank 2.0 (3 votes)
- google/gemini-3.1-pro-preview-20260219: avg rank 3.0 (3 votes)

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
Key top-level packages: `src/auth`, `src/client`, `src/models`, `src/portfolio`, `src/paper`, `src/mf`, `src/dhan`, `src/nuvama`, `src/intraday`, `src/instruments`, `src/market_calendar`, `src/notifications`, `src/utils`, `src/backtest`, `src/risk`, `src/gamma`, `src/db.py`
`src/risk/` — portfolio-level delta risk controls. `PortfolioDelta` frozen dataclass (`src/risk/models.py`): `options_delta_lots`, `niftybees_delta_lots`, `total_delta_lots`, `warning_breached`, `cap_breached`, `as_of`. `PortfolioDeltaTracker` (`src/risk/delta_tracker.py`): `aggregate_delta(paper_positions, nifty_spot, lot_size) → PortfolioDelta`; options-only thresholds warning=0.75/cap=1.0 lots, combined thresholds warning=1.5/cap=2.0 lots; parameterised via constructor. CE/futures = `net_qty/lot_size`; PE = `-net_qty/lot_size`; NiftyBees = `qty×avg_cost/(spot×lot_size)`. `check_entry_allowed` (`src/risk/entry_gate.py`): protective entries always allowed; cap → block; warning → allow with message. 20 unit tests in `tests/unit/risk/test_delta_tracker.py`.
`src/gamma/` — scaffolding, data models (`GammaChainSnapshot` and `GammaWatchlistEntry` frozen dataclasses), and persistence (`GammaStore` SQLite operations) for Near-Expiry Gamma Buy strategy.
`src/backtest/ivr.py` — `compute_ivr(vix_today, vix_series)`: IVR formula over trailing 252-day VIX window; returns `float | None`; clamps to `[0.0, 1.0]`; flat-window safe (returns 0.5). 11 unit tests in `tests/unit/backtest/test_ivr.py`.
`src/backtest/vix_ingest.py` — India VIX ingestion pipeline. Supports NSE CSV (legacy) and Upstox API.canonical Parquet storage: `data/historical/ohlc/india_vix/`. Resumable — identifies gaps and fetches missing days. 7 unit tests in `tests/unit/backtest/test_vix_ingest.py`.

`src/models/options.py` — `OptionLeg`, `OptionChainStrike`, `OptionChain` (all `frozen=True` Pydantic). Source-agnostic field names; Upstox parser in `src/client/upstox_market.py...
```