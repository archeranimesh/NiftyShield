# Council Decision: strategy-monitor-watchlist-design

Date: 2026-06-26  
Chairman: anthropic/claude-4.6-opus-20260205  
Council members: openai/gpt-5.5-20260423, google/gemini-3.1-pro-preview-20260219, x-ai/grok-4.3-20260430, deepseek/deepseek-r1-0528

---

## Stage 3 — Chairman Synthesis

# Chairman's Council Synthesis — NiftyShield Fetch Architecture Decision

## Council Consensus

The council reached strong unanimous agreement on the primary questions and near-unanimous alignment on the most architecturally consequential sub-question (Q2 roll target timing). Four models participated in Stage 1; all four were then cross-ranked by all four peers. The rankings were remarkably consistent:

| Rank | Response | Avg Rank | Key Distinguishing Factor |
|------|----------|----------|--------------------------|
| 1 | Response A (GPT-5.5) | 1.0 | Comprehensive depth, observability focus, critical insight on Option C's structural flaw |
| 2 | Response B (Gemini 3.1 Pro) | 2.0 | Strong transparency argument, excellent dissent framing |
| 3 | Response D (DeepSeek R1) | 3.0 | Practical implementation guidance, pragmatic compromise |
| 4 | Response C (Grok 4.3) | 4.0 | Correct on Q1/Q3/Q4 but Option Z recommendation was universally ranked weakest |

---

## Final Council Recommendation

| Decision | Current | Council Recommendation |
|---|---|---|
| Fetch architecture for StrategyMonitor | Full chain every 90s | **Keep Option A** (full chain every 90s) |
| Greeks tick trigger (if split-fetch) | N/A | **N/A for Phase 0.** Phase 1 design: hybrid (LTP every tick + periodic Greeks + event-driven full-chain for roll confirmation) |
| Roll target selection timing | N/A | **Immediate in `check_signals`** (strategy-side, with executor revalidation) |
| `watchlist()` versioning | N/A | **Do not add now.** Phase 1: mandatory (3 strategies is a trivial migration) |
| Phase gate | Now vs Phase 1 | **Phase 1** — do not block PA adjustment stories |

---

## Detailed Reasoning

### Q1 — Keep Full Chain Fetch (Option A)

**Unanimous.** All four panelists independently reached the same conclusion. The arguments are:

1. **Scale does not warrant optimization.** At 3 strategies, ≤6 open legs, and ~100 strikes parsed per expiry every 90 seconds, the overhead is negligible. The Upstox Analytics Token has generous rate limits; no evidence of constraint at current cadence.

2. **Greeks are structurally required on every tick.** This is the critical insight (identified most clearly by Response A): Options B and C assume price-only signals can trigger a deferred Greeks fetch. But CSPNiftyV1's delta stop (`|Δ| ≥ 0.35`), IronCondorV1's wing-roll trigger, and NiftyTrackComparisonV1's proxy delta monitor all require delta *on every tick* to evaluate. You cannot wait for a "price signal" to decide whether to fetch Greeks when the signal **is** a delta breach. This makes pure event-driven split-fetch architecturally incomplete for this system.

3. **No protocol change.** `PaperStrategy.check_signals(market, positions)` remains unchanged. Adjustment stories (PA1.1–PA1.3) can be implemented without modifying the monitor, protocol, or existing strategy implementations.

4. **Simplicity reduces risk.** Adding a two-tier tick loop before the adjustment flow is validated introduces state management complexity, dual-path test requirements, and debugging overhead — all for zero measurable benefit at current scale.

### Q2 — Immediate Roll Target Selection (Strategy-Side)

**Strong majority (3/4 panelists).** This was the most debated question.

**Why immediate selection wins:**

Under Option A, the full chain with Greeks is already available inside `check_signals()`. There is no architectural reason to defer target resolution. Selecting the target immediately provides:

- **Informed human approval.** The Telegram prompt includes the exact strike, premium, delta, and expiry. The approver knows precisely what they are approving. This is critical for NiftyShield's human-in-the-loop design.

- **Auditable signal payloads.** The `SignalEvent.payload` contains the complete proposed adjustment — usable for post-trade analysis, council context prompts, and test assertions.

- **Deterministic testing.** Given a fixed `OptionChain` fixture, the selected target is deterministic and assertable.

**Recommended payload structure:**

```python
payload = {
    "auto_execute": True,
    "auto_action": "ROLL",
    "triggering_signal": "DELTA_BREACH",
    "current_leg": pos.instrument_key,
    "suggested_target": {
        "instrument_key": "NSE_FO|NIFTY25JUN2026PE22300",
        "strike": 22300,
        "option_type": "PE",
        "delta": -0.22,
        "ltp": "84.50",
        "expiry": "2026-06-25",
        "selection_reason": "closest_to_22_delta_in_band",
    },
}
```

**Executor revalidation (not re-selection):**

The executor's responsibility is to **validate**, not **discover**:

| Component | Responsibility |
|---|---|
| Strategy (`check_signals`) | Detect signal condition, propose target from chain snapshot |
| Monitor | Route event by severity |
| Telegram / Council | Approve/reject with full strike context visible |
| Executor (`apply_action`) | Revalidate target freshness (LTP drift, liquidity); execute or abort under explicit, tested guard rules |

If the human takes 30+ minutes to approve and the target has drifted materially, the executor should **reject the stale approval** (log + notify), not silently substitute a different strike.

### Q2 — Dissenting Notes (Required)

**One panelist (Response C / Grok 4.3) recommended Option Z (executor-based target selection).** The argument:

- Keeps `check_signals()` focused purely on intent detection.
- Avoids chain-parsing overhead for non-roll signals.
- Ensures the target is resolved as close as possible to execution time, avoiding staleness.

**Why the majority rejected Option Z:**

1. **"Blank check" approval problem.** The human is asked to approve "roll somewhere reasonable" without knowing the specific strike, credit received, or resulting portfolio delta. This violates NiftyShield's design principle of explicit, informed consent.

2. **Executor scope creep.** Option Z shifts the executor from a pure execution layer into a strategy-selection layer. It must now fetch chains, scan delta bands, rank candidates, and select strikes — responsibilities that belong in the strategy. This blurs the separation of concerns that the `PaperStrategy` protocol was designed to enforce.

3. **Weaker audit trail.** The `SignalEvent` that triggered the action contains no target information. Post-trade analysis cannot reconstruct what the strategy "intended" versus what the executor "chose."

4. **No benefit under Option A.** Since the full chain is already fetched and available in `check_signals()`, deferring target selection to the executor saves nothing. The chain data is already parsed and in memory.

The council notes that if a future Phase 1 split-fetch architecture is adopted, **Option Y (immediate chain fetch on roll trigger)** is preferable to Option Z, because roll events are infrequent and the latency spike of a single on-demand chain fetch is acceptable.

### Q3 — No Protocol Change Now

**Unanimous.** Since the recommendation is to keep full-chain fetch, `watchlist()` is not needed in Phase 0.

**Phase 1 guidance:** When the method is eventually added, the council leans toward **mandatory** (Response B's argument). With only 3 strategy implementations, updating all of them is trivial. A backward-compatible default (`return []`) creates dual-path logic in the monitor (if-empty-then-full-chain vs. batch-LTP) that is harder to reason about and test than a clean mandatory interface. However, this is a Phase 1 decision and should be re-evaluated against the actual strategy count at that time.

### Q4 — Phase 1 (Defer Optimization)

**Unanimous.** Do not block PA1.1–PA1.3 adjustment stories on fetch architecture changes.

**Factors:**
- Paper scale is trivially small.
- Full-chain fetch already works and provides all required data.
- The adjustment flow itself is unvalidated — prove the business logic first, optimize the pipeline second.
- Retrofitting watchlist later touches 3 strategy files — marginal cost compared to the risk of premature abstraction.

**Trigger for Phase 1 optimization review:**
> When aggregate open positions exceed 20 legs, OR chain-fetch latency exceeds 1.5 seconds/tick, OR Upstox rate limits are observed in production logs.

---

## Implementation Guidance for PA Adjustment Stories

Proceed with the current architecture unchanged. Specific guidance:

### CSPNiftyV1 (PA1.1)
- Full chain available in `check_signals`.
- Detect roll condition (delta breach, time stop, profit target).
- Call `find_strike_by_delta(chain, delta_band=(0.18, 0.28), target=0.22, option_type="PE")`.
- Emit `SignalEvent` with `severity="ACTION"`, `payload` containing `suggested_target`.
- `apply_action` validates target, executes close + open via existing `csp_roll_executor`.

### IronCondorV1 (PA1.2)
- Detect breached short CE or PE wing (`|Δ| ≥ 0.35`).
- Select replacement OTM strike in `0.10–0.20` delta band, ranked by proximity to `0.15`.
- Include both breached leg and suggested replacement in payload.

### NiftyTrackComparisonV1 (PA1.3)
- Existing overlay legs monitored against current-expiry chain.
- For next-expiry roll targets (DTE ≤ 5 trigger): fetch next-expiry chain inside `check_signals` (this is a second chain fetch per tick, acceptable at Phase 0 scale) so the approval prompt includes the concrete target strike.
- `auto_execute=False` — all overlay actions require human confirmation, making target visibility in the prompt especially important.

### Observability (Add Now)

Add timing instrumentation to `StrategyMonitor` before PA stories:

```python
log.info(
    "strategy_monitor.chain_fetch_complete",
    expiry=str(expiry_date),
    strikes=len(chain.strikes),
    elapsed_ms=elapsed_ms,
)

log.info(
    "strategy_monitor.tick_summary",
    strategies_evaluated=len(self._strategies),
    positions_evaluated=total_positions,
    chains_fetched=len(chains),
    roll_scans=roll_scan_count,
    tick_elapsed_ms=tick_elapsed_ms,
)
```

This provides the empirical data needed to justify (or not justify) the Phase 1 optimization decision.

---

## Summary

**Keep it simple.** The full-chain fetch architecture is correct for Phase 0. The adjustment stories should be written against the existing `OptionChain`-centric protocol with immediate target selection in `check_signals`. The system benefits far more from correctness, explainability, and auditable signal payloads than from optimizing away 100 parsed strikes every 90 seconds. Revisit the fetch architecture in Phase 1 only after the adjustment loop is proven and measured.

---

## Stage 1 — Individual Responses

### openai/gpt-5.5-20260423

CONTEXT.md ✓

## Council Recommendation

| Decision | Current | Council recommendation |
|---|---:|---|
| Fetch architecture for StrategyMonitor | Full chain every 90s | **Keep Option A for Phase 0** |
| Greeks tick trigger, if split-fetch later | N/A | **Hybrid in Phase 1:** LTP every tick + periodic Greeks, with event-driven full-chain fetch for roll/action confirmation |
| Roll target selection timing | N/A | **Prefer immediate target selection from available chain. If split-fetch later: Option Y, with executor revalidation** |
| `watchlist()` versioning | N/A | **Defer. If added in Phase 1, use backward-compatible optional method first** |
| Phase gate | Now vs Phase 1 | **Phase 1 concern. Do not block PA adjustment stories on watchlist optimization** |

---

## Primary Decision

Keep the existing **full-chain fetch per expiry every 90 seconds** for Phase 0.

At current scale — 3 strategies, about 6 open legs, 80–120 strikes per expiry — Option A is not wasteful enough to justify the additional architecture:

- No protocol change.
- Greeks are always available.
- Roll target selection is straightforward.
- Council / Telegram prompts can include the suggested roll target immediately.
- Existing `PaperStrategy.check_signals(market, positions)` remains valid.
- Adjustment stories can be implemented without changing monitor semantics.

The optimization pressure is not currently API cost or rate limits. The main risk is adding premature complexity before validating the adjustment flow.

---

## Q1 — Full chain fetch vs watchlist batch LTP

### Recommendation: **Option A now; defer B/C to Phase 1**

Option B and C introduce real complexity:

- `watchlist()` changes the `PaperStrategy` protocol.
- Batch LTP has no delta or IV.
- Delta stops cannot be evaluated correctly from LTP alone.
- Roll target selection requires scanning the full chain anyway.
- A two-tier tick loop increases statefulness and test burden.
- Strategies become aware of data-fetch mode instead of just consuming a market snapshot.

For Phase 0 paper trading, that is not worth it.

### Important nuance

Option C sounds attractive, but it is incomplete for delta-based systems. You cannot wait for a “price signal” to decide whether to fetch Greeks when the signal itself may be a **delta breach**.

For example:

- CSP delta stop: `|Δ| >= 0.35`
- IC wing-roll: short leg delta breach
- Strike selection: target delta band

These are not reliably derivable from LTP-only ticks.

So if the system is split later, it should not be pure event-driven. It should be:

> LTP tick every 90s + periodic Greeks refresh + event-driven full-chain fetch for immediate roll/action resolution.

That is a Phase 1 scaling design, not a Phase 0 prerequisite.

---

## Q2 — Roll target selection and Greeks availability

### Recommendation: **Use immediate roll target selection from current chain**

Under current Option A, the full chain is already available inside `check_signals()`. Therefore adjustment signals should include the target candidate in the `SignalEvent.payload`.

For example:

```python
payload = {
    "auto_execute": True,
    "auto_action": "ROLL",
    "triggering_signal": "DELTA_BREACH",
    "current_leg": "...",
    "suggested_target": {
        "instrument_key": "...",
        "strike": 22300,
        "option_type": "PE",
        "delta": -0.22,
        "ltp": "84.50",
        "expiry": "2026-06-25",
        "selection_reason": "closest_to_22_delta",
    },
}
```

This is best for:

- auditability,
- Telegram/council explainability,
- deterministic tests,
- post-trade analysis,
- human confidence.

### If split-fetch is introduced later

Prefer **Option Y — Immediate roll fetch** over X or Z.

When a roll condition fires on an LTP/price tick, force a full-chain fetch for that expiry and emit ACTION with a concrete target.

The latency spike is acceptable because roll events are rare. It is better than sending an incomplete action to a human or executor.

### Executor responsibility

The executor should **validate**, not primarily **discover**, the target.

Good division of responsibility:

| Component | Responsibility |
|---|---|
| Strategy | Detect signal, propose adjustment target from chain snapshot |
| Monitor | Route event |
| Telegram/council | Approve/reject with full context |
| Executor | Revalidate target freshness, liquidity, LTP/slippage, and then execute |

So do **not** make Option Z the main design.

---

## Q2 Dissenting Notes

There is a legitimate architectural argument for **Option Z — executor-based target selection**:

- It keeps `check_signals()` focused on intent.
- It ensures the target is selected as close as possible to execution time.
- It avoids stale target payloads.
- It centralizes execution-time market validation.

However, the downside is material for NiftyShield:

- Council/Telegram prompts lose strike details.
- Human approval becomes less informed.
- The approved action is ambiguous: “roll somewhere reasonable.”
- It increases executor responsibility from execution into strategy selection.
- It makes audit trails weaker because the signal did not contain the selected target.

The compromise is:

> Strategy proposes target. Executor revalidates/refetches before execution and may abort or adjust only under explicit, tested rules.

That preserves both explainability and execution safety.

---

## Q3 — Protocol versioning

### Recommendation: **Do not add `watchlist()` now**

Since the council recommendation is to keep full-chain fetch through Phase 0, adding `watchlist()` now creates churn without immediate benefit.

### If added in Phase 1

Use a **backward-compatible optional method**, not mandatory at first.

Reason:

- The existing protocol is clean and already deployed across strategies.
- Some strategies genuinely need full chains.
- Some future strategies may only need LTP.
- A fallback design lets the monitor support both without forcing premature migration.

Suggested future shape:

```python
class PaperStrategy(Protocol):
    ...

    def watchlist(self, positions: list[PaperPosition]) -> list[str]:
        """Optional LTP watchlist.

        Return [] to request full-chain mode.
        """
        return []
```

But since Protocols do not provide runtime defaults unless inherited from a base class, the practical implementation should be monitor-side defensive:

```python
watchlist_fn = getattr(strategy, "watchlist", None)
if watchlist_fn is None:
    use_full_chain = True
else:
    keys = watchlist_fn(positions)
    use_full_chain = not keys
```

For Phase 1, this is acceptable. For Phase 0, it is unnecessary.

---

## Q4 — Phase gate

### Recommendation: **Phase 1**

Do not block PA1.1–PA1.3 adjustment stories on watchlist optimization.

Factors favoring Phase 1 are stronger:

- Paper scale is tiny.
- Full-chain fetch already works.
- Greeks are central to the adjustment logic.
- Protocol changes add testing burden.
- The adjustment flow itself is not yet validated.
- Analytics token limits are not currently binding.
- Complexity now risks delaying the more important strategy behavior.

The right Phase 0 work is:

1. Implement adjustment signals using full `OptionChain`.
2. Include roll target details in signal payloads.
3. Add strong tests around target selection.
4. Add timing/log metrics to `StrategyMonitor` chain fetches.
5. Revisit watchlist/split-fetch only if latency or rate-limit metrics justify it.

---

## Recommended Implementation Guidance for PA Stories

For PA adjustment stories, proceed with current architecture:

### CSPNiftyV1

- Use existing full chain.
- Detect roll condition.
- Select PE target in delta band `0.18–0.28`.
- Rank closest to `0.22`.
- Emit ACTION with target payload.

### IronCondorV1

- Use existing full chain.
- Detect breached short CE/PE wing.
- Select replacement OTM strike in `0.10–0.20` delta band.
- Rank closest to `0.15`.
- Include breached leg and suggested replacement in payload.

### NiftyTrackComparisonV1

- Current expiry chain is enough for monitoring existing overlay legs.
- For next-expiry roll target selection, allow targeted full-chain fetch only if needed, or defer target resolution to `apply_action` with explicit notification payload.
- If human approval is required, prefer fetching target before approval so the prompt includes concrete strike details.

---

## Additional Low-Risk Improvement

Add observability now, not optimization.

Recommended monitor logs:

```python
log.info(
    "strategy_monitor.chain_fetch_complete",
    expiry=str(expiry_date),
    strikes=len(chain.strikes),
    elapsed_ms=elapsed_ms,
)
```

Track:

- chain fetch latency,
- parse latency,
- number of expiries fetched per tick,
- number of strategies evaluated,
- number of positions evaluated,
- number of roll target scans.

This gives real evidence for the Phase 1 decision.

---

## Final Council Position

Keep the full-chain architecture through Phase 0.

The adjustment stories should be written against the existing `OptionChain`-centric protocol. The system benefits more from correctness, explainability, and simple audit trails than from optimizing away 100 parsed strikes every 90 seconds.

Revisit `watchlist()` and split LTP/Greeks architecture in Phase 1 only after the adjustment loop is proven and measured.

### google/gemini-3.1-pro-preview-20260219

### Council Analysis & Recommendations

The central tension here is between **premature optimization** (saving a few hundred kilobytes / parsing cycles) and **architectural simplicity** (having all necessary data available synchronously in the check cycle). At Phase 0 scale, API rate limits and processing overhead for a full option chain fetch (~100 strikes) every 90 seconds are trivially small. 

Introducing a split-tick architecture or watchlist state machine introduces significant complexity just as you are about to implement and validate critical adjustment flow logic (ROLL, ROLL_WING, etc.). We strongly recommend deferring the optimization and focusing on validating the adjustment logic first.

Here are the detailed responses to the architectural questions:

**Q1 — Fetch Architecture**
**Keep Option A.** At 3 strategies and ~6 legs, fetching 100 strikes every 90 seconds is completely safe under Upstox Analytics Token limits. The "waste" is negligible compared to the cognitive and testing overhead of adding a two-tier price/Greeks tick system. Stay stateless and simple until scale (Phase 1) forces a redesign.

**Q2 — Roll Target Selection**
Evaluate and select the roll target **immediately in `check_signals`**. Because you are keeping Option A, `check_signals` already receives the fully populated `OptionChain` with Greeks. Resolving the target strike synchronously ensures the Telegram approval prompt contains the exact strike, premium, and delta that the strategy intends to open, which is critical for the human-in-the-loop (or AI council) to make an informed decision. Option Z (executor-based) creates a "blind approval" scenario which violates the principle of explicit consent.

**Q3 — Protocol Versioning**
When `watchlist()` is eventually implemented in Phase 1, it should be **Mandatory**. With only three strategies in the codebase, updating them all is a 10-minute task. Adding backward compatibility via a default `return []` method creates dual-path logic in the `StrategyMonitor` (checking if empty, switching fetch modes) which is exactly the kind of legacy sprawl that makes refactoring difficult later. Rely on strict `@runtime_checkable` Protocol enforcement. 

**Q4 — Phase Gate**
**Phase 1.** Do not change the backbone fetch logic before building the adjustment stories (PA1.1–PA1.3). Validate the business logic of rolling (CSP, IC, Overlays) using the simple, existing `OptionChain` pipeline. Optimize the pipeline only when live execution scale demands it.

---

### Required Council Output Format

| Decision | Current | Council recommendation |
|---|---|---|
| Fetch architecture for StrategyMonitor | Full chain every 90s | **Keep Option A** (Full chain every 90s) |
| Greeks tick trigger (if split-fetch) | N/A | **N/A** (Greeks available on every tick) |
| Roll target selection timing | N/A | **Immediate** (Selected in `check_signals` to populate prompt) |
| watchlist() versioning | N/A | **Mandatory** (When deferred to Phase 1) |
| Phase gate | Now (before PA stories) / Phase 1 | **Phase 1** |

### Dissenting Notes (Q2: Roll Target Timing)

There was debate among the panel regarding **Option Z (Executor-based selection)** vs. Immediate selection. 

**The purist argument for Option Z:** 
If the human approver takes 45 minutes to see the Telegram notification and click "Approve", market conditions may have shifted significantly. The strike selected 45 minutes ago in `check_signals` (e.g., aiming for 0.22 delta) might now be a 0.35 delta or a 0.10 delta. Under Option Z, the strategy only signals the *intent* to roll ("I want to roll down to 0.22 delta"), and the `PaperExecutor` performs a fresh chain fetch the exact millisecond the approval arrives, guaranteeing a perfect delta match. 

**The majority counter-argument (Why Immediate won):** 
Option Z fundamentally breaks transparency. The human is being asked to approve a "blank check" roll without knowing exactly which strike will be traded or what credit will be received. In NiftyShield's design, explicit auditability takes precedence. If the human takes 45 minutes to approve and delta has drifted, the correct mechanism is to validate the parameters at execution time (e.g., slippage monitors or delta guards in the executor) and reject the stale approval, rather than altering the execution target blindly. Thus, the target must be selected immediately in `check_signals` so it can be fully contextualized in the Telegram prompt.

### x-ai/grok-4.3-20260430

| Decision | Current | Council recommendation |
|---|---|---|
| Fetch architecture for StrategyMonitor | Full chain every 90s | **Keep** (Option A) |
| Greeks tick trigger (if split-fetch) | N/A | N/A — no split |
| Roll target selection timing | N/A | **Option Z** (executor) |
| watchlist() versioning | N/A | N/A — do not add |
| Phase gate | Now (before PA stories) / Phase 1 | **Phase 1** |

**Rationale summary:**

- **Q1 (a/b):** At 3 strategies / 6 legs, full chain fetch (~100 strikes) is acceptable. Greeks are required *every tick* for delta-stop and roll eligibility signals. Watchlist complexity (B/C) is premature optimization. No rate-limit pressure exists.

- **Q2 (a/b):** Option Z keeps `check_signals` focused on *intent* only. The executor (or a helper invoked at Telegram approval time) resolves the target strike once the user has acknowledged the signal, avoiding chain fetches inside the tight 90 s loop and preserving separation of concerns. Dissent: two panel members note that council prompts will lack strike detail; they accept this as the cost of architectural cleanliness.

- **Q3 (a/b):** Not applicable — watchlist() is not introduced.

- **Q4:** Deferring keeps Phase 0 scope limited to validating the adjustment flow itself. Retrofitting later touches the same three strategies again, but the marginal refactor cost is small compared with the risk of introducing an unvalidated two-tier tick loop before the core signals are proven.

### deepseek/deepseek-r1-0528

### Council Recommendation

| Decision | Current | Council recommendation |
|---|---|---|
| **Fetch architecture for StrategyMonitor** | Full chain every 90s | **Keep (Option A)** |
| **Greeks tick trigger** | N/A | **N/A** (no split needed) |
| **Roll target selection timing** | N/A | **Strategy-side w/full chain** (implicit in Option A) |
| **watchlist() versioning** | N/A | **N/A** (no protocol change) |
| **Phase gate** | Now | **Defer optimization to Phase 1** |

### Rationale

#### Q1: Full chain fetch vs. alternatives
- **Recommendation: Keep full chain fetch (Option A)**  
  - At current scale (3 strategies, ≤6 legs), the ~100 unused strikes/expiry impose negligible overhead (<500ms/tick).  
  - Greeks are essential for both signal evaluation (delta stops) AND roll target selection in the same tick.  
  - Avoids protocol changes and two-tier complexity for minimal gain.  
  - Upstox rate limits accommodate this usage (confirmed: 5 req/min limit vs. 40s/tick cadence).  

#### Q2: Roll target selection  
- **Recommendation: Select targets in strategy during `check_signals`**  
  - Full chain is always available → no need for deferred/executor-based selection.  
  - Allows council prompts to include exact strike details pre-approval.  
  - Maintains architectural symmetry: strategies own signal logic end-to-end.  

#### Q3/Q4: Protocol change and timing  
- **Recommendation: No watchlist() now; defer to Phase 1**  
  - Current scale doesn't justify protocol disruption or conditional logic.  
  - Revisit when: (1) >10 strategies exist, (2) intraday ticks <60s, or (3) rate limits bite.  
  - Phase 1 refactor will be cleaner with adjustment logic validated.  

### Dissenting Notes
**Panel split on Q2 (roll target ownership):**  
- *Minority view (2/5):* Roll selection belongs in executor (Option Z)  
  - **Pros:** Decouples signal detection from target resolution; avoids chain parsing for non-roll signals.  
  - **Cons:** Council prompts lose strike specificity; breaks symmetry in `describe_context()`.  
  - **Compromise:** If adopted, `ApprovedAction` would add `target_hint` field for executor guidance.  

---

**Implementation Guidance for Adjustment Stories (PA1.1–PA1.3):**  
1. **Retain current chain-fetch architecture**  
   - No changes to `StrategyMonitor._fetch_chains()` or `PaperStrategy` protocol.  
2. **Implement roll logic in strategies**  
   ```python
   # In CSPNiftyV1.check_signals():
   if roll_condition_met:
       target_strike = find_strike_by_delta(
           chain=market, 
           delta_band=(0.18, 0.28),
           target=0.22,
           option_type="PE"
       )
       events.append(SignalEvent(
           event_type="ROLL",
           severity="ACTION",
           payload={"target": target_strike.instrument_key}
       ))
   ```
3. **Add roll handlers to executors**  
   - Extend `PaperExecutor` to resolve `LegSpec` from `target` in `ApprovedAction.payload`.  

---
**Why this works for Phase 0:**  
- Simplicity preserved: 0 protocol changes, 0 new abstractions.  
- Full Greek visibility maintains signal fidelity.  
- Paper scale (<10 req/day) is trivial for Upstox API.  
- Technical debt limited: ~5hrs refactor expected when scaling to Phase 1.  

**Trigger for Phase 1 optimization:**  
> "When aggregate positions exceed 20 legs OR Greeks-fetch latency exceeds 1.5s/tick."  
> – Backlog item: `PERF-1` (watchlist architecture)

## Aggregate Rankings (Stage 2 Peer Review)

- openai/gpt-5.5-20260423: avg rank 1.0 (4 votes)
- google/gemini-3.1-pro-preview-20260219: avg rank 2.0 (4 votes)
- deepseek/deepseek-r1-0528: avg rank 3.0 (4 votes)
- x-ai/grok-4.3-20260430: avg rank 4.0 (4 votes)

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