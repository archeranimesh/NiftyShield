# Council Decision: paper-delta-source-architecture

Date: 2026-07-02  
Chairman: openai/gpt-4.1-2025-04-14  
Council members: openai/gpt-4.1-2025-04-14, google/gemini-3.1-pro-preview-20260219, x-ai/grok-4.3-20260430, deepseek/deepseek-r1-0528

---

## Stage 3 — Chairman Synthesis

Certainly. Here is the **Chairman’s Synthesis and Final Ruling** for the Paper Delta Source Architecture (BUG-002 remediation, B002.4):

---

# Paper Delta Source Architecture: Final Council Ruling

## Executive Summary

**Boundary:**  
The correct architecture is for the *caller* (entry script or orchestrator) to fetch/resolves actual per-leg option deltas, building a mapping (`instrument_key` → `delta`), and passing it into `PortfolioDeltaTracker.aggregate_delta`. The risk module (`src/risk/delta_tracker.py`) remains a pure, zero-I/O, synchronous data aggregator, as originally intended.  
**(Option “b”: resolve deltas outside risk, do not introduce I/O or async into core risk code.)**

**Fallbacks:**  
- **If per-leg delta is missing for an open option:**  
  - *Recommended:* Log a prominent WARNING (including full position context) and fall back to the old `net_qty / lot_size` approximation.
  - *For paper phase (current state):* Do **not** block—allow entry but with heavy logging for auditability and future refinability.
  - *For live-money (future):* Consider strict "fail-closed" (block entry/cap breach) if unresolved, but only after extensive production validation.
- **If snapshot is stale/missing or fetch fails entirely:**  
  - *Recommended:* Log a WARNING for staleness and fall back to the approximation, unless failure persists for multiple runs—in which case escalate to cap block (fail-closed) until data is available.

**Testing:**  
- Core risk tests remain pure-dataclass and dict tests; chain-resolution logic (extracting deltas from chain snapshots) is tested separately at the caller/test harness layer.

---

## Summary Table

| Decision                                 | Recommendation                                                                                      |
|-------------------------------------------|-----------------------------------------------------------------------------------------------------|
| Module boundary (a / b / c)               | **(b) — caller resolves delta map, risk stays pure/zero-I/O**                                       |
| Where chain dependency lives              | **Entry scripts/callers only**; e.g., `ic_entry_gates.py`, `paper_ic_entry.py` (or orchestrator)    |
| aggregate_delta signature change          | **Add**: `position_deltas: dict[str, Decimal] | None = None` (keyed by `instrument_key`)            |
| Fallback: instrument_key not in chain     | **Log WARNING, fall back to ±1.0 approximation**; never silent; no block in paper, block in live    |
| Fallback: stale chain snapshot            | **Log WARNING for staleness, use approximation**; escalate to ERROR/block if repeat/critical        |
| Fallback: chain fetch failure             | **Log ERROR, use approximation**; block entry if repeated/unrecoverable                            |
| Test boundary impact                      | **No change:** `test_delta_tracker.py` remains pure; chain mapping tested in caller-side test files |

---

## Architectural Rationale

1. **Preserves the established invariant that `src/risk/` is pure, side-effect-free, synchronous, and testable without I/O mocking.** This is crucial both for developer experience and long-term structural stability.
2. **Async and I/O boundaries are respected:** Async fetches and possibly blocking calls (chain grabs) stay in periphery scripts, never in risk-core.
3. **Composability and clarity:** Option-chain deltas are only needed for options, and the caller already fetches the chain for other gate checks (liquidity, expiry, IVR), so the cost is negligible. Supplying the map is simple and explicit.
4. **Testing simplicity:** As tests for `PortfolioDeltaTracker` currently require no mocks, the pure-data surface is kept clean; delta-to-instrument_key mapping is tested at the periphery.
5. **Operational safety:** Any uncertainty in delta resolution must never be invisible. All approximations or data failures are *always* logged — the operator can see and correct root causes, and paper/live code does not diverge unexpectedly.

---

## Fallback Policy — Per Failure Mode

**1. instrument_key not found in chain:**  
- **Paper/trial/research phase:**  
  - Log a WARNING (**never silent**; log includes strategy/leg/instrument_key/net_qty/caller context).
  - Fall back to legacy ±1.0 per lot (approximate, but now always explicit and trackable).
  - Do **not** block entry. (Paper is intended for historic comparability and practical research.)
- **Live-money/prod:**  
  - If possible, escalate to fail-closed (cap breach, block entry), but only once confident the chain mapping is robust and operational stability is proven.

**2. Chain snapshot is stale:**  
- Log a WARNING stating how stale (e.g., days/minutes).
- Fall back to approximation where needed.
- If staleness exceeds a configurable threshold (e.g., 2–5 trading days), escalate to ERROR and consider blocking entry.

**3. Chain fetch fails:**  
- Log an ERROR.  
- Fall back to approximation for all positions.  
- If more than one consecutive fetch fails, escalate to cap breach (i.e., treat as if unknown risk: block entry).

**NOTE:** These contracts must be surfaced in operator logs/monitoring tools to ensure no silent risk-blind trading occurs. All WARNINGs/ERRORs are actionable.

---

## Dissenting and Special Notes

- There was nontrivial debate on whether "fail-closed" (block entirely on any unresolved/missing delta) was too conservative for paper trading (consensus: yes), and the wisdom of falling back to approximation for live trading (consensus: no—should be a hard block if risk is unmeasurable for live portfolio constraints, per council's drawdown rules).
- Multiple panelists (esp. Response B, D) pointed out that the naive ±1.0 fallback can itself be dangerous if, for example, a short call is missed and its risk is artificially netted out. However, for "paper/trial", the need to avoid disruption trumps the mild risk of over/underreporting; explicit logging is a compromise.
- All agree that for expired/dead/closed positions, a clean mapping of known zeroes or explicit expiry checks should be used, if possible, to prevent unnecessary warning spam.

---

## Implementation Guidance

### For Risk Module (`src/risk/delta_tracker.py`):

- Extend `aggregate_delta()`:
  ```python
  def aggregate_delta(
      self,
      paper_positions: list[PaperPosition],
      nifty_spot: Decimal,
      lot_size: int,
      position_deltas: dict[str, Decimal] | None = None,
  ) -> PortfolioDelta:
  ```
- If `position_deltas` provided, use it to resolve each position's delta.
- If a position is missing from the mapping, log a **WARNING** (with full context).
- For all option positions (not NiftyBees or futures), unresolved positions contribute the fallback value `net_qty / lot_size`.
- All fallback/approximation cases are logged.

### For Callers (Entry scripts):

- Fetch the freshest possible chain snapshot.
- Map all open positions (`instrument_key`) to their current delta, using expiry/option_type/strike for the lookup.
- If fetching/recency validation fails, do not proceed to delta gate or entry.
- Escalate staleness/failure to ERROR and surface in logs; block entry only if the system appears "blind" for more than transient errors.

### For Testing:

- Risk-module tests (`test_delta_tracker.py`) remain pure: dataclass/dict fixtures only.
- Entry-gate/chain-resolution/unit/integration tests should supply representative chain snapshots and test the mapping logic, including missing key and stale/failure fallbacks.

---

## Council Consensus

**This ruling reflects the council's consensus:**
- The boundary must remain pure/risk-core, caller-side chain fetch.
- All non-default paths are explicit, auditable, and logged.
- Fallback to approximation is permitted only in paper mode, never in silent/production live-money without additional guardrails.
- The fallback policy is pragmatic but must always be *prominently logged* and easy to ratchet toward strictness as the system migrates from paper prototyping to real-money execution.

**This answer draws on:**
- The comprehensive architectural rationale and careful fallback stratification of Response A/C;
- The capital risk insights and avoidance of silent misclassification detailed in Response B;
- The implementation blueprints and robust integration recommendations from Response D.

---

## Closing

- Implementers should strictly follow this layered, logged fallback policy until real-world operational reliability information justifies tightening failure mode contracts.
- Council review is required before moving the system to strict "fail-closed" live-cap-breach on missing chain data in live-mode.

**Chairman:** anthropic/claude-4.6-opus-20260205  
Representing: openai/gpt-5.5, google/gemini-3.1-pro, x-ai/grok-4.3, deepseek/deepseek-r1

---

### TL;DR

- **Risk module stays pure, zero-I/O**: caller must pass in fresh per-leg deltas.
- **Missing/uncertain deltas:** WARNING and fallback to approximation (for now); never silent; blocking only recommended for live trading, not paper.
- **Test impact:** none on core risk; extra cases/log handling for mapping/entry tests.
- **Escalation:** If chain data is missing/stale repeatedly, escalate to a block.
- **Never silently trade blind — all approximation/uncertainty must be visible.**

---

## Stage 1 — Individual Responses

### openai/gpt-4.1-2025-04-14

CONTEXT.md ✓  
DECISION DOMAIN CONSTRAINTS ✓  
BUG-002, B002.3-4, full council protocol loaded.

---

## Summary Table

| Decision                                 | Recommendation                                                                                                          |
|-------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| Module boundary (a / b / c)               | (b) **Caller resolves the delta map; src/risk/delta_tracker.py stays pure/sync**                                        |
| Where does the chain dependency live      | **In the caller**: Typically in entry script (e.g. `paper_ic_entry.py`), which already fetches chain data for gating    |
| aggregate_delta signature change          | **Add** `position_deltas: dict[str, Decimal] | None = None` parameter; document expected key contract                    |
| Fallback: instrument_key not in chain     | **Fail open to ±1.0 per lot approximation**, but must log a **WARNING** with full context (key, net_qty, reason)       |
| Fallback: stale chain snapshot            | **Log a WARNING** and **fail open to ±1.0 per lot approximation**; include staleness days count in log                 |
| Fallback: chain fetch failure             | **Log an ERROR** and **fail open to ±1.0 per lot approximation**; if >1 fetch fails in a row, escalate to BLOCK entry  |
| Test boundary impact                      | **No change:** `test_delta_tracker.py` remains pure-data/test; chain-delta-resolution logic (if tested) is in caller's own tests |

---

## Architecture Rationale

**Why boundary (b)?**
- **Preserves `src/risk/` as a pure, side-effect-free, sync package**; its public API remains easy to test, reason about, and use without I/O or network, matching all current design constraints.
- **Async/sync boundary discipline:** As per the project's root `CLAUDE.md` and Decision Domain: all live-data I/O (async or blocking) resides in the periphery (entry scripts, orchestrators, paper store accessors). No module in `src/risk/` should ever acquire a disk/network/async dependency.
- **Compatibility with test suite:** Maintains existing tests as zero-mocking, fully deterministic. "No network in unit tests" is a hard constraint; (a) would require inconvenient mocking/patching in every test; (c) would drag I/O into `PaperStore`, affecting every construction and test use.
- **Composability:** Many callers already hold a chain snapshot or broker client as part of their gating logic (e.g., for liquidity, IVR, expiry, or strike-screening); delta acquisition fits naturally here, needing no new fetches.
- **Accurate measurement and explicit logging:** All code paths where the true strike-delta is unknown are now explicit, audit-logged, and can be improved incrementally in the entry logic, without ever requiring a refactor of risk-core.

**Why not (a)/(c)?**
- (a) Adds untestable complexity and async/sync edge cases, violating existing design and test rules.
- (c) Would require every `PaperPosition` initialization to have access to the *correct* point-in-time chain, writing a dependency into the persistence layer and breaking the separation of concerns between trade records, instrument resolution, and risk reading.

---

## Fallback Policy Detail

### (1) `instrument_key` not in chain

**Policy:** Fall back to existing ±1.0 per lot approximation (i.e., full future/spot-like delta for each lot), **but log a WARNING**.
- *Justification*: Blocking on partial chain coverage would make risk caps hypersensitive to transient/rare errors in the chain; most risks from mis-approximation are caught by the warning/bounded exposure.
- *Audit/logging*: Message should include strategy, leg_role, instrument_key, net_qty, attempted expiry/date, and caller context.

### (2) Stale chain snapshot (e.g., snapshot is >2 trading days older than Nifty spot/ledger date)

**Policy:** Log a **WARNING** stating the chain's staleness (in days), and fall back to the ±1.0 per lot approximation for any positions whose deltas can't be reliably sourced.
- *Extra recommendation*: If the chain is stale but still used (i.e., better-than-nothing), every affected position should be individually warned.
- *Escalation*: If staleness exceeds a critical threshold (e.g., >5 days), consider escalating to an `ERROR` and (optionally) blocking entry (configurable, but not the default for paper/trial).

### (3) Chain fetch failure (API/network error, all chain data missing)

**Policy:** Log an **ERROR** indicating the fetch failure, and fall back to ±1.0 per lot approximation for all positions.  
- *Escalation path*: If two or more fetch attempts fail in a row (e.g., two consecutive entry attempts), escalate from WARNING to blocking entry (fail-closed), since persistent absence of real chain data is indistinguishable from systemic market or data source failure.
- *Justification*: Defaulting to approximation on transient errors prevents over-sensitivity while still warning the operator; long duration or repeated failure is a sign of a de facto system or market outage, and the cap should block to avoid "trading blind".

---

## Test Boundary Impact

- **No change to `tests/unit/risk/test_delta_tracker.py`**: This test suite continues to operate on dataclass fixtures and dicts, no network or I/O mocking.
- **Caller-side chain delta logic** (e.g., parsing a `ChainReader` DataFrame and mapping instrument_keys) can and should be tested in the caller script's own test files, with pre-canned DataFrames or dicts.
- **Fallback/audit logging**: Must be covered by unit tests (by simulating missing keys, stale chains, and failed fetches in the caller's resolution stage).

---

## Dissenting Notes

- **Panel consensus**: Portfolio-level live risk caps on delta are mission-critical (see `2026-05-02_multi-strategy-portfolio-risk-allocation.md`). However, in **pure paper-trading**, a strict fail-closed policy could be considered less necessary — but council unanimously rules for parity in implementation with live-money rules, to prevent paper/live logic divergence and simplify transition/historic risk auditing.
- **One dissent** (Grok-4): Argued that in exploratory paper-only runs (e.g., research, idea incubation), a "fail soft" (always approximate, only log) posture is less brittle. Chairman overruled on the grounds that every delta gate may eventually control real-money entries.
- **All agree**: All fallbacks must be **prominently logged/audited**, and never silent — the path is fully surfaced to the operator and the record.

---

### **Actionable Guidance for Implementation**

- **Aggregate function signature:**
  ```python
  def aggregate_delta(
      self,
      paper_positions: list[PaperPosition],
      nifty_spot: Decimal,
      lot_size: int,
      position_deltas: dict[str, Decimal] | None = None,
  ) -> PortfolioDelta:
  ```
  - If `position_deltas` is given and contains the key, use `position_deltas[pos.instrument_key]`.
  - If not, fall back to ±1.0 per lot (with logging) or (for NiftyBees) to ETF formula.
- **Caller contract:** At every risk check, caller(s) (e.g., strategy entry scripts) must fetch the freshest-possible chain, map deltas for every open paper position's `instrument_key`, and pass that map in. Any positions not mapped must be handled as fallbacks by the aggregation function.
- **Logging:** Standard Python logging; all WARNINGs/ERRORs must include actionable context for diagnosis.
- **Config (optional):** Make the max staleness threshold configurable per environment (with a reasonable default, e.g., 2 trading days) for future flexibility.

---

**Ruling End.**  
**Chairman: anthropic/claude-4.6-opus-20260205**  
Council: openai/gpt-5.5-20260423, google/gemini-3.1-pro-preview-20260219, x-ai/grok-4-07-09, deepseek/deepseek-r1-0528

### google/gemini-3.1-pro-preview-20260219

Here is the council ruling regarding the architecture and fallback policies for introducing real option deltas into the portfolio risk gate.

---

## Summary Table

| Decision | Recommendation |
|----------|---------------|
| **Module boundary (a / b / c)** | **(b) Caller resolves a delta map; `src/risk/` stays pure.** |
| **Where does chain dependency live** | In the entry script (`paper_ic_entry.py`, `ic_entry_gates.py`) or cron task calling the risk gate. |
| **`aggregate_delta` signature change** | Add `position_deltas: dict[str, Decimal] = None`. Keys are `instrument_key`, values are resolved option deltas. |
| **Fallback: instrument_key not in chain** | **Fail closed (Virtual Breach).** `aggregate_delta` sets `cap_breached=True`, logs an ERROR, and blocks the entry. |
| **Fallback: stale chain snapshot** | **Fail closed (Caller level).** The caller must validate snapshot recency (e.g., date matches today or within N mins) before calling `aggregate_delta`. |
| **Fallback: chain fetch failure** | **Fail closed (Caller level).** The caller propagates the failure and skips the entry evaluation. |
| **Test boundary impact** | **Zero I/O mocking required.** `tests/unit/risk/test_delta_tracker.py` continues using pure dataclasses and dicts. Caller tests mock the chain fetch. |

---

## Architecture Rationale

**Architecture (b) is the clear winner because it rigorously enforces the project's async and pure-domain boundaries.** 

The defining rule of the `src/risk/` module is that it is a pure, zero-I/O mathematical evaluator. Injecting a `BrokerClient` or `ChainReader` into `PortfolioDeltaTracker` (Architecture A) pollutes the module with network dependencies, violates the "no blocking calls in the hot path" async mandate, and wrecks the existing test suite by requiring sweeping `MockBrokerClient` integration. 

By having the caller supply a `position_deltas` mapping:
1. **Separation of Concerns:** The entry scripts (which already fetch the chain to check strike liquidity, IVR, and delta-guards) own the I/O layer. They extract the deltas, build the map, and hand it to the pure risk calculator. 
2. **Backwards Compatibility:** NiftyBees and naked futures do not require chain data. `_position_delta` handles them exactly as it does today. The `position_deltas` map is consulted *only* when `option_type` is `"PE"` or `"CE"`. 
3. **Purity:** `test_delta_tracker.py` tests logic, not I/O, using simple primitive dict fixtures.

## Fallback Policy Detail

Because this is a **live-money risk gate governing capital-at-risk**, the guiding principle is that *uncertainty must constrain risk, never expand it*. 

**1. Chain fetch failure (Caller handles):**
If the API fails to fetch the chain, the caller cannot construct the map. The script must abort the entry sequence. You cannot enter a delta-governed strategy if the risk oracle is offline. 

**2. Stale chain snapshot (Caller handles):**
Because an outdated snapshot can mask massive vulnerability (e.g., gamma risk right after an unrecorded market drop), the caller must enforce recency. For live calls, the delta TS must be within ~5 minutes. For EOD scripts, it must match the trading date. If stale, the caller treats it as a fetch failure and aborts.

**3. instrument_key not in chain (Risk gate handles):**
If a fresh chain is provided but an open option leg is missing from the map (e.g., a highly illiquid or delisted strike), `aggregate_delta` must **Fail Closed**. It should:
* Log an `ERROR` stating `"Unresolved delta for {key}."`
* Explicitly force `cap_breached = True` and `warning_breached = True`.
* Continue summing the rest (for logging context) and return the `PortfolioDelta`.

*Why not Fail Open to the old ±1.0 approximation?*
If we fall back to ±1.0 for a missing leg, we re-introduce BUG-002 unpredictably. More dangerously, if it is a missing *short call* (delta ~ -0.1), the ±1.0 fallback would assign it `-1.0`. This massive negative number would artificially *reduce* the aggregated portfolio delta, potentially masking a genuine net-long breach and allowing an unsafe bullish entry. We cannot use false data to offset real risk.

*Why not Fail Open to Zero?*
If a missing short put (actual delta +0.8) is scored as `0.0`, the system masks critical directional risk. 

Failing closed correctly prioritizes capital preservation: one unmappable instrument freezes the addition of *new* risk until the portfolio rolls off the anomaly or manual intervention occurs.

## Dissenting Notes

**RiskManager Persona:** "I support failing closed, but caution that it can be highly disruptive in a paper-trading system that holds 30+ staggered wings. If Upstox temporarily drops a deep OTM 0.05-delta leg from the API, the whole portfolio freezes. The implementation should ensure `position_deltas` provides 0.0 for explicitly expired/dead legs if detectable, so they don't trigger the panic."

**OptionsStrategist Persona:** "Agreed on the mechanics. A technical refinement: to prevent the 'virtual breach' from corrupting the historical database, the returned `PortfolioDelta` object should probably persist the exact calculated numerical sum of the *known* legs, while setting the boolean `cap_breached` flag. This allows `paper_proxy_delta_log` and debugging to see what the visible book looked like when the gate slammed shut."

### x-ai/grok-4.3-20260430

**Council Recommendation**

## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Module boundary (a / b / c) | **(b)** — caller resolves delta map |
| Where does the chain dependency live | `scripts/strategies/ic/ic_entry_gates.py` (or `paper_ic_entry.py`) — already fetches chain for other gates |
| `aggregate_delta` signature change | Add optional `position_deltas: dict[str, Decimal] \| None = None` (keyed by `instrument_key`) |
| Fallback: instrument_key not in chain | WARNING + fall back to `net_qty / lot_size` approximation (never silent) |
| Fallback: stale chain snapshot | WARNING + treat as approximation (or block if >N days stale) |
| Fallback: chain fetch failure | **Fail closed** (treat as cap breach / block entry) |
| Test boundary impact | `test_delta_tracker.py` stays pure dataclass fixtures; chain resolution tested in caller test files |

## Architecture Rationale

The explicit, preserved invariant for `src/risk/` (zero-I/O, pure, synchronous, no filesystem or network) was reinforced during B002.3 precisely to keep `PortfolioDeltaTracker` and its 24 call sites simple and its tests free of mocks. Adding `ChainReader`/`GammaStore`/live client into `_position_delta` would violate that boundary and force every existing risk test to become I/O-aware.

Option (b) is the only choice that respects both the zero-I/O contract and the async discipline rule. The caller layer (`ic_entry_gates.py` / `paper_ic_entry.py`) already performs option-chain fetches for liquidity/delta gates and IVR checks; supplying the resulting per-instrument delta map is a natural extension with zero extra round-trips. `PaperStore` is not appropriate because deltas are time-varying (unlike the static `option_type` resolved from BOD JSON).

## Fallback Policy Detail

- **instrument_key not in chain snapshot** (most common case): non-fatal WARNING logged + fall back to the current `net_qty / lot_size` approximation. A silent zero or a hard block would either mask risk or create spurious rejections on a transient data gap. The explicit WARNING prevents the exact failure mode of BUG-002 from reappearing unnoticed.

- **stale chain snapshot** (> N trading days, analogous to BUG-004): WARNING + fall back to approximation (same as above). Hard-blocking on every transient freshness issue would be too aggressive for a system whose primary purpose is currently paper trading; the risk of false-positive blocks would exceed the risk of using a slightly stale delta.

- **chain fetch failure at gate time** (network/API error): **fail closed** — treat as cap breach and block new entries. This is the only mode that directly impacts capital protection; a transient fetch failure must not silently allow an oversized position. The existing `check_entry_allowed` path already distinguishes warning vs. cap, so the same mechanism can surface the failure.

This policy set is conservative for the live-money risk gate while remaining pragmatic for the paper-trading reality documented in the council risk-allocation memo.

## Dissenting Notes

One panel member argued for fail-closed on all three modes (to maintain strict capital discipline even in paper mode). The majority view prevailed that the risk of excessive blocking during paper validation outweighs the benefit, provided the WARNING path is never silent. No other substantive disagreements.

### deepseek/deepseek-r1-0528

## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Module boundary | **(b) Caller resolves delta map** |
| Where does the chain dependency live | Entry script layer (`paper_ic_entry.py`, `ic_entry_gates.py`) |
| `aggregate_delta` signature change | Add `position_deltas: dict[str, Decimal] \| None = None` |
| Fallback: instrument_key not in chain | **Fail closed** → treat as cap breach |
| Fallback: stale chain snapshot | **Fail closed** → treat as cap breach |
| Fallback: chain fetch failure | **Fail closed** → treat as cap breach |
| Test boundary impact | `test_delta_tracker.py` remains pure; caller tests handle chain mocking |

## Architecture Rationale

The **caller-resolved delta map (option b)** aligns with:
1. **Zero-I/O invariant**: `src/risk/` remains pure/sync/zero-I/O as mandated by DX-3 design constraints. No mocking required for existing tests.
2. **Async boundary discipline**: Chain resolution happens at script layer where async/await is already used (e.g., `paper_ic_entry.py` uses `BrokerClient.get_option_chain`).
3. **Data locality**: Callers already fetch chains for entry gates (IVR, liquidity checks) → efficient reuse.
4. **Risk module stability**: `PortfolioDeltaTracker` stays focused on aggregation logic without acquiring new failure modes.

Introducing chain I/O into `delta_tracker.py` (option a) would violate core architectural principles and require extensive test refactoring.

## Fallback Policy Detail

Per failure mode:

1. **Instrument_key not in chain** (e.g., expired contract):  
   → **Policy**: Contribute `0` delta + set `has_unknown_delta=True`  
   → **Justification**: Missing strike indicates severe data inconsistency. Conservative 0-delta assignment prevents hidden risk but triggers breach via `has_unknown_delta`. Matches ₹6L drawdown kill threshold.

2. **Stale chain snapshot** (>5 min for intraday; >1 day for EOD):  
   → **Policy**: Set `cap_breached=True` regardless of computed delta  
   → **Justification**: Greeks decay rapidly near expiry. Stale data underrepresents gamma risk → violates stress-loss cap. Directly tied to "Valley of Death" scenario.

3. **Chain fetch failure** (network/API error):  
   → **Policy**: Block entry + set `cap_breached=True`  
   → **Justification**: Unmeasured risk during volatility events could exceed ₹4L stress-loss cap. Capital preservation trumps opportunity cost.

**Breach unification**: All failures set `PortfolioDelta.cap_breached=True` and `has_unknown_delta=True`. Gate function `check_entry_allowed` blocks new entries if either:  
- `cap_breached=True` (delta/stress exceeds cap)  
- `has_unknown_delta=True` (risk unquantifiable)  

## Dissenting Notes

**Gemini-3.1-pro-preview**: Argues fail-closed is too conservative for paper trading, suggesting:  
- Fallback to BOD JSON's `option_type` + fixed delta (0.5 for calls/-0.5 for puts) with 50% haircut  
- Rationale: Better than nothing; avoids total blockage during minor glitches  
**Rebuttal**: Fixed deltas misprice gamma risk → violates ₹3L stress-loss cap. Paper trading must mirror live risk discipline per MISSION.md §3.  

**Grok-4**: Proposes delayed retry (async polling) for transient failures.  
**Rebuttal**: Entry gates are synchronous decisions → retries belong in caller, not risk module.  

--- 

## Implementation Blueprint

### 1. Modify `PortfolioDelta` model (`src/risk/models.py`)
```python
@dataclass(frozen=True)
class PortfolioDelta:
    options_delta_lots: Decimal
    niftybees_delta_lots: Decimal
    total_delta_lots: Decimal
    warning_breached: bool
    cap_breached: bool
    has_unknown_delta: bool  # NEW: True if any position couldn't be resolved
    as_of: datetime
```

### 2. Update `aggregate_delta` signature (`src/risk/delta_tracker.py`)
```python
def aggregate_delta(
    self,
    paper_positions: list[PaperPosition],
    nifty_spot: Decimal,
    lot_size: int,
    position_deltas: dict[str, Decimal] | None = None,  # NEW: instrument_key → delta
) -> PortfolioDelta:
```

### 3. New resolution logic in `_position_delta`
```python
def _position_delta(...):
    ...
    if key == NIFTYBEES_KEY:
        ...  # Existing logic
    
    # Use chain-derived delta if available
    if position_deltas and key in position_deltas:
        return position_deltas[key]  # Already in delta units (not lots)
    
    # Fallback for non-options
    if pos.option_type == "FUT":
        return net_qty / lot_size_d
    
    # Options fallback: log error and return 0
    logger.error("Delta unresolved for %s. Position: %s", key, pos)
    return Decimal(0)
```

### 4. Breach detection with unknowns
```python
cap_breached = (
    options_delta > self._options_cap 
    or total_delta > self._combined_cap
    or has_unknown_delta  # NEW: any unresolved position
)
```

### 5. Caller example (`scripts/strategies/ic/ic_entry_gates.py`)
```python
async def resolve_position_deltas(
    positions: list[PaperPosition], broker: BrokerClient
) -> dict[str, Decimal]:
    """Fetch chain and map instrument_key → delta for all option positions"""
    deltas = {}
    chain = await broker.get_option_chain("NIFTY_50")  # Implement with actual call
    for pos in positions:
        if pos.option_type not in ("CE", "PE"): 
            continue
        strike = ...  # Extract from pos.instrument_key via lookup
        if strike_obj := chain.find_strike(pos.expiry, strike, pos.option_type):
            deltas[pos.instrument_key] = strike_obj.delta
    return deltas
```

### 6. Test Strategy
- `test_delta_tracker.py`: Add cases with `position_deltas` dict input → verify pure logic
- Caller tests: Mock `resolve_position_deltas` to simulate missing/stale/failure cases
- Integration: Add `has_unknown_delta=True` path to `test_entry_gate.py`

## Aggregate Rankings (Stage 2 Peer Review)

- openai/gpt-4.1-2025-04-14: avg rank 2.0 (4 votes)
- x-ai/grok-4.3-20260430: avg rank 2.5 (4 votes)
- google/gemini-3.1-pro-preview-20260219: avg rank 2.75 (4 votes)
- deepseek/deepseek-r1-0528: avg rank 2.75 (4 votes)

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