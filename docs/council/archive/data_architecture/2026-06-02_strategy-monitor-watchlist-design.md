# Council Decision: strategy-monitor-watchlist-design

Date: 2026-06-02  
Chairman: anthropic/claude-4.6-opus-20260205  
Council members: openai/gpt-5.5-20260423, google/gemini-3.1-pro-preview-20260219, x-ai/grok-4.3-20260430, deepseek/deepseek-r1-0528

---

## Stage 3 — Chairman Synthesis

# Chairman's Synthesis — NiftyShield Fetch Architecture Council Decision

---

## Executive Directive

| Decision | Current | Council Recommendation |
|---|---|---|
| Fetch architecture for StrategyMonitor | Full chain every 90s | **Keep (Option A)** |
| Greeks tick trigger (if split-fetch) | N/A | **N/A — not needed in Phase 0** |
| Roll target selection timing | N/A | **Option Y — Immediate target selection within check_signals** |
| watchlist() versioning | N/A | **Defer entirely — no protocol change before PA stories** |
| Phase gate | Now vs Phase 1 | **Phase 1** |

---

## Rationale

### Q1 — Keep the full chain fetch (Option A)

The council is **unanimous** on this point. At current paper-trading scale (3 strategies, ≤6 open legs, one API call every 90 seconds), the full chain fetch is not a bottleneck — it is a feature.

**Why Option A is correct now:**

- Delta-stop signals (`DELTA_STOP` at |Δ| ≥ 0.35) require live Greeks on every tick. A batch-LTP watchlist strips delta from the hot path, making the most critical exit signal stale or unavailable.
- Roll target selection requires scanning 20–40 strikes in a delta band. The full chain already provides this data at zero additional cost.
- Upstox Analytics Token capacity is ~300 req/min; current usage is ~0.7 req/min. We are at <1% utilization.
- There is no "partial chain" Upstox endpoint. Under Options B/C, we would make *more* API calls (batch LTP + triggered full-chain fetch) than the current single call.

**Why Options B and C are premature:**

Option B (watchlist + batch LTP) requires a protocol change, two-tier market data modes, and strategies that work with partial data sometimes and full data other times. Option C (hybrid with event-triggered chain fetch) is better than B but introduces a blind spot: delta can move from spot movement, IV change, or time decay without any price signal firing first. A delta stop should not depend on a price signal as a precondition.

**Cost of the current approach:** ~100 strikes parsed per tick, ~250 ticks/day, ~25,000 strike rows/day — trivial for Python, entirely in-memory, no persistence overhead.

### Q2 — Immediate roll target selection (Option Y)

This was the most debated question across the council. The **majority position** (3 of 4 substantive responses) recommends Option Y. The dissent favoring Option Z is architecturally principled but inappropriate for Phase 0's safety posture.

**Why Option Y:**

The human-in-the-loop approval flow requires that the Telegram prompt contain the specific proposed trade:

> "Roll CSP short put from 23000PE to 22500PE (Δ = −0.22, expiry 2026-06-25, estimated credit ₹45)"

is materially superior to:

> "Approve roll. Executor will choose target later."

The roll target strike is not an implementation detail — it is the risk being approved. Under Option Z, either (a) the user approves an abstract policy rather than a trade, or (b) the executor makes a material discretionary choice after approval. Neither is acceptable in a human-reviewed paper-trading system.

Since the full chain is already in memory during `check_signals`, scanning for a delta-band candidate adds negligible latency (pure in-memory filtering). The strategy selects the target, packs it into `SignalEvent.payload`, and `describe_context()` renders it for the council prompt and Telegram message. The executor validates and applies the approved action but does not silently choose a different strike.

**Executor safeguard:** At execution time, the executor should perform a final sanity check (instrument still available, LTP not wildly stale, delta still within tolerance). If the target has materially changed, the executor should reject and request re-approval rather than substituting.

### Dissenting Notes on Q2

**Dissent — Option Z is architecturally cleaner (2/5 panelists):**

Option Z achieves the cleanest separation of concerns: strategy signals intent, executor resolves implementation. A roll signal could carry constraints rather than a specific strike:

```
Roll short put to next expiry,
target delta 0.18–0.28,
prefer 0.22,
minimum credit ₹X
```

This avoids duplicating target-selection logic in both strategy and executor. However, this changes the meaning of approval from "approve this specific trade" to "approve this bounded algorithm." That pattern may be appropriate in Phase 1+ automated execution, but it undermines Phase 0's auditability goals.

**Dissent — Option X acceptable for low-urgency signals (1/5 panelists):**

For non-critical maintenance signals (DTE ≤ 5 reminders, premium decay notifications), a two-stage WARN → ACTION flow is acceptable. But for delta-breach or wing-roll scenarios in fast-moving markets, even a 5-minute lag is undesirable.

**Resolution:** Use Option Y as the primary flow for all ACTION-severity roll signals. Option X may be acceptable for purely informational WARN signals that don't gate an approval flow. Option Z is deferred to Phase 1+ consideration.

### Q3 — No protocol change now

Do not add `watchlist()` before PA1.1–PA1.3 adjustment stories. The current protocol provides everything the adjustment flow needs:

```python
async def check_signals(market: OptionChain, positions: list[PaperPosition]) -> list[SignalEvent]
```

The `OptionChain` already contains all strikes, Greeks, and LTP data required for both exit signals and roll target selection.

If a `watchlist()` or `market_requirements()` method is introduced in Phase 1, make it **mandatory** (protocol-v2 style), not backward-compatible. With only 3 strategies, retrofitting is cheap. Backward-compatible optional behavior creates ambiguous conditional logic in the monitor:

```python
# Avoid this in Phase 1:
if strategy.watchlist():
    fetch_ltp_batch()
else:
    fetch_full_chain()
```

A cleaner Phase 1 design would introduce a `MarketDataRequest` object:

```python
class PaperStrategyV2(Protocol):
    def market_requirements(self) -> MarketDataRequest: ...
    async def check_signals(self, market: MarketDataView, ...) -> list[SignalEvent]: ...
```

This is a Phase 1 concern.

### Q4 — Defer to Phase 1

The watchlist optimization is **not** a Phase 0 blocker.

Phase 0 goals for the adjustment stories are:

1. Validate adjustment signal correctness (ROLL, ROLL_WING, ROLL_OVERLAY)
2. Validate council prompt quality with concrete targets
3. Validate Telegram approval flow end-to-end
4. Validate `ApprovedAction` structure for multi-leg rolls
5. Validate paper executor behavior
6. Validate auditability: what was proposed → what was approved → what was applied

Adding fetch optimization before the adjustment flow itself is validated adds risk without measurable benefit.

Phase 1 triggers for revisiting this decision:
- ≥5 strategies registered
- ≥15 open legs simultaneously
- Multiple expiries monitored per tick
- Live execution latency constraints
- Rate limit utilization exceeding 10%

---

## Architectural Note: Multi-Expiry Fetching

The current `StrategyMonitor._fetch_chain()` fetches one NIFTY expiry per tick. This is sufficient for same-expiry exit signals and same-expiry roll targets.

However, `NiftyTrackComparisonV1` rolls overlay legs to the **next expiry**. The adjustment stories will need a small extension:

- **Same-expiry exits/stops:** use the already-fetched chain.
- **Same-expiry roll targets:** use the already-fetched chain.
- **Next-expiry roll targets:** fetch the next-expiry chain immediately during ACTION construction within `check_signals`.

This is not a watchlist architecture — it is targeted full-chain fetching for a second expiry when a specific roll condition requires it. The strategy should include the next-expiry target in `SignalEvent.payload` so the council prompt has full context.

Recommended implementation: pass the `expiry_fn` or broker reference to strategies that need multi-expiry access, or have the monitor pre-fetch both current and next expiry when registered strategies declare that need. The exact wiring is a PA-story implementation detail, not an architectural decision.

---

## Implementation Guidance for PA1.1–PA1.3

1. **No changes to `StrategyMonitor._fetch_chain()`** — continue fetching full chain for primary expiry.
2. **Roll target selection lives in the strategy**, not the executor. Extract shared logic into a utility:
   ```python
   # src/strategy/roll_utils.py
   def find_strike_by_delta(
       chain: OptionChain,
       option_type: Literal["CE", "PE"],
       delta_range: tuple[Decimal, Decimal],
       target_delta: Decimal,
   ) -> OptionLeg | None:
       """Filter chain strikes by delta band, return closest to target."""
   ```
3. **`SignalEvent.payload`** for ROLL actions must include: `target_instrument_key`, `target_strike`, `target_delta`, `target_expiry`, `estimated_credit_or_debit`.
4. **`describe_context()`** renders the full roll proposal for the council prompt.
5. **Executor** validates the approved target at execution time; rejects if materially stale.

---

## Council Confidence

- **Q1 (Keep Option A):** Unanimous. No dissent.
- **Q2 (Option Y):** Strong majority. Dissent recorded and mitigated.
- **Q3 (Defer watchlist):** Unanimous. No dissent.
- **Q4 (Phase 1):** Unanimous. No dissent.

---

## Stage 1 — Individual Responses

### openai/gpt-5.5-20260423

CONTEXT.md ✓

## Council Recommendation

| Decision | Current | Council recommendation |
|---|---:|---|
| Fetch architecture for StrategyMonitor | Full chain every 90s | **Keep Option A for Phase 0** |
| Greeks tick trigger if split-fetch later | N/A | **Hybrid**: periodic Greeks refresh + event-driven immediate fetch |
| Roll target selection timing | N/A | **Option Y — Immediate roll target selection before approval** |
| `watchlist()` versioning | N/A | **Defer. If added in Phase 1, make it mandatory / protocol-v2 style** |
| Phase gate | Now vs Phase 1 | **Phase 1 concern. Do not block PA adjustment stories on watchlist optimization.** |

---

## Executive Recommendation

For the current paper-trading scale — 3 strategies, roughly 6 open legs, 90-second ticks — **keep the existing full-chain fetch architecture**.

Do **not** add `watchlist()` before implementing adjustment stories.

The extra parsing of ~80–120 strikes every 90 seconds is not the bottleneck. The higher risk is introducing a two-tier market-data system before the roll/adjustment workflow itself has been validated.

The adjustment stories should be implemented assuming:

1. The strategy receives a full `OptionChain`.
2. The strategy can scan the chain for roll targets.
3. `ACTION` events include the proposed roll target in the payload/context.
4. The council and Telegram approval prompt sees the actual proposed strike before approval.
5. `PaperExecutor` executes or records the already-approved action; it should not silently choose a materially different strike after approval.

---

# Q1 — Full chain fetch vs watchlist-based batch LTP

## Recommendation: Option A for Phase 0

Keep:

```python
OptionChain -> every strategy.check_signals(...)
```

### Why

At current scale, full-chain fetch is acceptable.

Approximate load:

- 90-second tick
- 09:15–15:30 = 375 minutes
- ~250 ticks/day
- ~100 strikes/tick
- ~25,000 strike rows parsed/day

That is trivial for Python, SQLite-free, and well within the stated Upstox Analytics Token comfort zone.

More importantly, full-chain fetch gives the system the data it actually needs:

- LTP for profit/loss/decay checks
- delta for delta stops
- IV for context and future ranking
- all strikes for roll-target discovery

A batch-LTP watchlist only solves the easiest part — price monitoring — but the upcoming stories are specifically about adjustment logic that depends on Greeks and candidate search.

## Why not Option B now

`watchlist()` + batch LTP adds several complications:

- Breaks or expands the `PaperStrategy` protocol.
- Requires the monitor to manage two market-data modes.
- Requires strategies to work with partial market data sometimes and full chain data other times.
- Still does not solve delta-band roll selection unless a full chain is fetched periodically.
- Makes delta-stop detection stale unless Greeks are refreshed separately.
- Forces adjustment stories to handle “target unavailable yet” states.

That is premature for Phase 0.

## Why not Option C now

Option C is better than B, but still unnecessary right now.

Event-triggered full-chain fetch has one important blind spot: **some Greek-based triggers may happen without an obvious price signal first**.

For example:

- Delta can move because spot moves, IV changes, or time passes.
- A delta stop should not depend on a price stop firing first.
- A roll target cannot be confidently selected from LTP-only data.

So if the system eventually splits price ticks and Greeks ticks, it should not be purely event-driven. It should be hybrid.

## If split-fetch is introduced later

Use:

```text
LTP tick every 30–90s
Greeks/full-chain tick every 5–10 min
Immediate full-chain refresh when an ACTION candidate needs target selection
```

So the later Phase 1 design should be:

> **Hybrid: periodic Greeks refresh + event-driven immediate fetch.**

---

# Q2 — Roll target selection and Greeks availability

## Recommendation: Option Y — Immediate roll target selection

For human-in-the-loop approval, the council prompt should include the proposed roll target.

A Telegram approval request that says:

> “Roll CSP short put to NIFTY 22500 PE, delta -0.22, expiry 2026-06-25, estimated credit ₹X”

is materially better than:

> “Approve roll; executor will choose target later.”

The target strike is not an implementation detail. It is the actual risk being approved.

## Why not Option X as the primary flow

Option X — deferred roll — is acceptable for low-urgency informational flows, but it is awkward for `ACTION` signals.

A 5–10 minute delay may be fine for:

- DTE ≤ 5 roll reminders
- premium decay reminders
- non-urgent overlay maintenance

But it is weaker for:

- delta breach
- short-leg stress
- wing roll
- fast-moving market conditions

Also, two-stage WARN → ACTION state management adds complexity:

- Need to remember pending roll intents.
- Need to suppress duplicate WARNs.
- Need to upgrade correctly after the next Greeks tick.
- Need to handle stale target prices.

Not worth it in Phase 0.

## Why not Option Z as the primary flow

Option Z is architecturally tempting because it keeps `check_signals()` simple:

```text
Strategy: “I want to roll”
Executor: “I will resolve the target later”
```

But it weakens the approval semantics.

If the user approves before seeing the target, then one of two things is true:

1. The user is approving an abstract policy, not a trade.
2. The executor is making a material discretionary choice after approval.

That is not ideal for this project’s current safety posture.

The executor should validate, price, and record approved actions. It should not decide the key economic terms after approval.

## Best compromise

Use Option Y now:

```text
Strategy detects roll condition
Strategy scans current/full chain
SignalEvent payload includes suggested target
Council prompt includes target
Telegram approval approves that target
Executor applies the approved action
```

Executor may still do a final sanity check:

- target instrument still available
- LTP not wildly stale
- delta still within tolerance, if available
- credit/debit not outside allowed slippage

If the target has materially changed, executor should reject or request re-approval rather than silently choosing another strike.

---

# Q3 — Protocol versioning

## Recommendation: do not add `watchlist()` now

Do not expand `PaperStrategy` before PA1.1–PA1.3 adjustment stories.

The current protocol is good enough:

```python
async def check_signals(
    market: OptionChain,
    positions: list[PaperPosition],
) -> list[SignalEvent]:
    ...
```

Adding `watchlist()` now optimizes a problem that does not yet exist.

## If `watchlist()` is added in Phase 1

For this codebase, prefer **mandatory protocol-v2 style** over backward-compatible optional behavior.

Reason:

- There are only 3 known strategies today.
- Retrofitting all of them is cheap.
- Mandatory behavior is easier to reason about.
- Avoids monitor logic like:

```python
if strategy.watchlist():
    fetch_ltp_batch()
else:
    fetch_full_chain()
```

That kind of fallback sounds convenient but creates ambiguous behavior:

- Some strategies receive partial data.
- Some receive full data.
- Some rely on implicit fallback.
- Test matrix doubles.

Better Phase 1 approach:

```python
class PaperStrategyV2(Protocol):
    strategy_name: str

    def market_requirements(...) -> MarketDataRequest:
        ...

    async def check_signals(
        self,
        market: MarketDataView,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        ...
```

That is cleaner than bolting `watchlist()` directly onto the current protocol.

---

# Q4 — Phase gate

## Recommendation: Phase 1

The watchlist optimization should not be a Phase 0 blocker.

Phase 0 goal should be:

1. Validate adjustment signal correctness.
2. Validate council prompt quality.
3. Validate Telegram approval flow.
4. Validate `ApprovedAction` structure.
5. Validate paper executor behavior.
6. Validate auditability of what was approved vs what was applied.

The fetch optimization can wait.

Phase 1 is the right time to revisit because by then the project may have:

- 10+ strategies
- 20+ open legs
- multiple expiries
- live execution constraints
- stricter latency expectations
- more expensive market data fanout

At that point, a more deliberate market-data layer makes sense.

---

# Additional Architectural Note: One Expiry May Not Be Enough

Current `StrategyMonitor._fetch_chain()` fetches one NIFTY expiry:

```python
raw = await self._broker.get_option_chain(_NIFTY_INSTRUMENT, expiry_str)
```

For current signals this is fine.

But some upcoming roll logic needs another expiry, especially:

> `NiftyTrackComparisonV1` — target same overlay type on next expiry, |Δ| ~0.20.

So even while keeping Option A, the adjustment stories may need one small extension:

```text
Base tick: fetch primary/current expiry chain.
If roll target requires next expiry: fetch that expiry’s full chain immediately.
```

This is still not a watchlist architecture. It is just targeted full-chain fetching by expiry.

Recommended rule:

- Current-expiry exits/stops: use already-fetched chain.
- Same-expiry roll target: use already-fetched chain.
- Next-expiry roll target: fetch next-expiry chain immediately during ACTION construction.
- Include selected target in `SignalEvent.payload`.

---

# Dissenting Notes on Q2

## Majority view

The majority recommends **Option Y**.

Reason:

- Human approval should include the actual target strike.
- Roll target is a material risk decision.
- The council prompt is more useful with concrete strike, expiry, delta, and premium.
- Executor should not choose the trade after approval.

## Dissent 1 — Executor-based target selection is architecturally cleaner

There is a valid argument for Option Z:

> Strategy emits intent; executor resolves implementation.

This is cleaner in abstract architecture, especially if actions are represented as constraints:

```text
Roll short put to next expiry,
target delta 0.18–0.28,
prefer 0.22,
minimum credit ₹X,
max slippage ₹Y.
```

Then the executor chooses the best live instrument at approval time.

But this changes the meaning of approval. The user is no longer approving a specific strike; they are approving a bounded algorithm.

That may be appropriate in a later automated-execution phase, but it is not ideal for Phase 0 paper trading where auditability and human review matter more.

## Dissent 2 — Deferred roll is acceptable for non-urgent rolls

Option X can be acceptable for low-urgency maintenance signals:

- DTE roll reminders
- premium decay rolls
- overlay cleanup

For these, a WARN first and ACTION later is not dangerous.

But for delta-stress or wing-roll cases, the delay is undesirable. Therefore Option X should not be the primary architecture.

## Final Q2 position

Use:

```text
Option Y for ACTION rolls.
Option X only for low-urgency WARN reminders.
Avoid Option Z until Phase 1+ and only if approvals become constraint-based.
```

---

# Final Council Position

Keep the current full-chain fetch model through Phase 0.

Do not add `watchlist()` before the adjustment stories.

Implement roll/adjustment signals with immediate target selection and concrete targets in the council prompt.

Revisit market-data optimization in Phase 1 after the adjustment flow is proven.

### google/gemini-3.1-pro-preview-20260219

### Council Synthesis

**To: NiftyShield Engineering**
**From: The Rapid Council (Architect, Risk Manager, Developer Paradigm, Ops, Chairman)**

**Executive Summary:** 
The council unanimously recommends avoiding premature optimization. At the current Phase 0 scale (3 strategies, ~6 open legs), the network and CPU cost of parsing 120 strikes every 90 seconds is negligible. Furthermore, strategies like `CSPNiftyV1` require live Greeks every 90 seconds to evaluate `DELTA_STOP` (`|Δ| ≥ 0.35`) accurately. Migrating to a watchlist/LTP-batch architecture introduces a complex, multi-tiered state machine that strips crucial Delta data from the hot path while solving a throttling problem we do not yet have. 

We will maintain the full-chain fetch strategy. Roll target selection should remain synchronous within `check_signals` so that exact target strikes are passed into the `SignalEvent` payload. This guarantees the AI Council and the human approver via Telegram have the full context before approving an action.

---

### Official Directive

| Decision | Current | Council recommendation |
|---|---|---|
| Fetch architecture for StrategyMonitor | Full chain every 90s | **Keep (Option A)** — Required for 90s `DELTA_STOP` evaluations. |
| Greeks tick trigger (if split-fetch) | N/A | **N/A** — Full chain provides continuous Greeks. |
| Roll target selection timing | N/A | **Synchronous (Effectively Option Y)** — Strategy selects exact target from the provided chain. |
| watchlist() versioning | N/A | **Defer entirely** — When introduced in Phase 1, make it Mandatory. |
| Phase gate | Now (before PA stories) / Phase 1 | **Phase 1** — Do not block Phase 0 adjustment stories on this optimization. |

---

### Dissenting Notes & Panel Discussion

**On Q1 & Q4 (Architecture & Scale):**
*Developer:* Writing the adjustment stories is vastly simpler if the strategy always has the `OptionChain` object. I don't want to build an event-driven queue where `check_signals` yields a `WAITING_ON_GREEKS` state.
*Ops:* Upstox Analytics limits are thousands of calls per minute, and we are making one call every 90 seconds. Do not optimize an I/O path that isn't bottlenecking.
*Architect:* Concur on deferring to Phase 1. Note that because Upstox doesn't offer a "partial chain" endpoint, we'd be making *more* API calls under a hybrid model (one for batch LTP, and another full chain pull when a roll signal fires). Keep Option A.

**On Q2 (Roll Target Selection & Separation of Concerns):**
*(This is where the council diverged significantly before the Chairman's override)*

*Architect:* **Option Z (Executor-lazy)** is the most robust software pattern. The `PaperStrategy` should only detect the *need* to adjust (e.g., "Leg X has breached DTE 5, emit `ROLL`"). The `PaperExecutor` should be responsible for scanning the market, finding the 0.20 delta strike, and constructing the `ApprovedAction`. This decouples signal generation from execution mechanics.

*Risk Manager (Fierce Dissent):* **Absolutely not.** Option Z fundamentally breaks NiftyShield's human-in-the-loop and council-review mandates. If the strategy only emits generic intent, what exactly is the Telegram prompt asking the human to approve? "Do you want to roll?" is an incomplete question. The prompt *must* be: "Do you want to roll the 23000PE to the 22500PE to collect ₹45 and reset delta to 0.18?" The council needs the proposed target to evaluate risk/reward. The strategy *must* select the strike before approval.

*Chairman (Resolution):* Risk is correct. The `OptionChain` is already available in memory inside `check_signals`. The strategy must scan the chain, locate the candidate strike, and pack it into the `SignalEvent.payload` and `describe_context()`. This perfectly satisfies our non-negotiable requirement that the Telegram alert and AI syntheis contain the complete, explicit proposal.

**Proceed with Phase 0 `ROLL` adjustment stories using the existing `OptionChain` fetch loop.**

### x-ai/grok-4.3-20260430

The current full-chain fetch (Option A) is the right choice for Phase 0.

| Decision | Current | Council recommendation |
|---|---|---|
| Fetch architecture for StrategyMonitor | Full chain every 90s | Keep |
| Greeks tick trigger (if split-fetch) | N/A | N/A |
| Roll target selection timing | N/A | N/A (full chain supplies strikes) |
| watchlist() versioning | N/A | N/A |
| Phase gate | Now (before PA stories) / Phase 1 | Phase 1 |

**Rationale summary**  
- Paper scale (≤3 strategies, ≤6 legs) makes 80–120 strikes per tick negligible in CPU, network, and token cost.  
- Full chain already supplies the deltas and strikes required for both delta-stop signals and roll target selection, so no protocol change or two-tier tick logic is required.  
- Adding `watchlist()` (Options B/C) before the adjustment flow is validated introduces complexity and a breaking change for no measurable benefit.  
- Roll target and council-prompt requirements are satisfied without a deferred or executor-based design.  

The optimisation is deferred to Phase 1 when strategy count and leg count justify it. No dissenting notes.

### deepseek/deepseek-r1-0528

Based on a thorough analysis of the system context, architectural constraints, and phase priorities, the council recommends the following approach:

### Council Recommendation Table

| Decision | Current | Council Recommendation |
|---|---|---|
| **Fetch architecture for StrategyMonitor** | Full chain every 90s | **Option A (Keep full chain fetch)** |
| **Greeks tick trigger** | N/A | **N/A (not applicable)** |
| **Roll target selection timing** | N/A | **Option Y (Immediate fetch)** |
| **watchlist() versioning** | N/A | **Not implemented** |
| **Phase gate** | Now | **Defer to Phase 1** |

### Detailed Rationale

#### Q1: Full chain vs watchlist
**Recommendation: Keep full chain fetch (Option A)**  
- At current scale (3 strategies, ≤6 legs), fetching 100 strikes every 90s is trivial (<5KB/tick). Upstox Analytics Token allows ~300 req/min - current usage is <1% of capacity.
- Roll target selection requires full chain scan - partial fetches would still need 20-30 strikes per strategy.
- Protocol change would require modifying all 3 strategies now and again in Phase 1 when Greeks become essential for live execution risk checks.
- Complexity cost outweighs benefits: Two-tier system would add state management, synchronization issues, and edge cases.

#### Q2: Roll target selection
**Recommendation: Immediate fetch (Option Y)**  
- Human approval requires target details: Council prompt must show specific strike/delta for informed decisions.
- Latency is acceptable: 200-400ms for chain fetch is negligible compared to 90s tick interval and human response time.
- Executor-based selection (Option Z) creates UI disconnect: Approval would be for "roll" generically, then executor picks target - violates principle of least surprise.
- Deferred signals (Option X) add operational risk: Critical roll decisions shouldn't wait 5-10 minutes during volatile periods.

#### Q3: Protocol versioning
**Recommendation: No watchlist() implementation**  
- Mandatory change would break all strategies for marginal gain
- Backward compatibility adds conditional logic debt: `if watchlist():...else:...` patterns would permeate monitor
- Phase 1 will likely need fundamentally different data architecture anyway (e.g., streaming Greeks)

#### Q4: Phase gate
**Recommendation: Defer to Phase 1**  
- **Phase 0 priority**: Validate adjustment logic, not optimize data flows
- **Risk profile**: Full chain works today; optimization might introduce new failure modes
- **Natural transition**: At Phase 1 gate (live execution), reassess with:
  1. Actual rate limit usage metrics
  2. Expanded strategy count (≥5 strategies)
  3. Real-time risk monitoring requirements

### Dissenting Notes
**On Q2 (Roll target timing):**  
While majority favors Option Y, 2/5 panelists advocate Option Z (executor-based) for:
1. Cleaner separation of concerns (signals vs execution)
2. Avoids duplicating target logic in strategy and executor
3. Council prompt could show target *criteria* (e.g., "PE 0.18-0.28 delta") instead of specific strike

**Mitigation for dissent:**  
Implement Phase 0 with Option Y, but:
1. Add `target_selection_mode` flag to `ApprovedAction`
2. Design executor to handle both pre-selected and criteria-based actions
3. Revisit during PA2.4 (executor refactor)

### Implementation Guidance for Phase 0
1. **Maintain current full-chain flow** - No changes to `StrategyMonitor._fetch_chain()`
2. **Implement roll signals** in strategies:
```python
# CSPNiftyV1 example
if roll_condition_met:
    target_put = self._find_roll_target(market, delta_range=(0.18, 0.28))
    events.append(SignalEvent(
        event_type="ROLL",
        severity="ACTION",
        description=f"Roll to {target_put.strike}PE (Δ={target_put.delta})",
        payload={
            "target_instrument": target_put.instrument_key,
            "target_delta": target_put.delta,
            # Include context for approval message
        }
    ))
```
3. **Add roll helpers** to strategy base:
```python
# src/strategy/roll_utils.py
def find_strike_by_delta(
    chain: OptionChain, 
    option_type: Literal["CE", "PE"], 
    delta_range: tuple[float, float],
    preference: Literal["closest", "highest", "lowest"] = "closest",
    target_delta: float | None = None
) -> OptionLeg | None:
    # Filter strikes, apply delta range, sort by preference
```

### Phase 1 Considerations
When scaling beyond 10 strategies:
1. Implement **expiry-indexed chain cache** updated every 30s
2. Add **watchlist-based LTP** for price checks between full updates
3. Introduce **Greeks-focused strategy protocol**:
```python
class LiveStrategy(Protocol):
    def greeks_requirements(self) -> set[str]:  # e.g., {"delta", "gamma"}
    def watchlist(self) -> set[str]:  # instrument keys
```

This approach delivers adjustment capabilities with minimal disruption to Phase 0 goals while establishing clear upgrade paths for Phase 1 scaling.

## Aggregate Rankings (Stage 2 Peer Review)

- openai/gpt-5.5-20260423: avg rank 1.5 (4 votes)
- google/gemini-3.1-pro-preview-20260219: avg rank 1.75 (4 votes)
- deepseek/deepseek-r1-0528: avg rank 2.75 (4 votes)
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