# Council Decision: data-source-routing

Date: 2026-10-07  
Chairman: anthropic/claude-opus-4.6  
Council members: openai/gpt-6.1-sol, google/gemini-3.1-pro-preview, x-ai/grok-4.7, deepseek/deepseek-r1-0528

---

## Stage 3 — Chairman Synthesis

## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Q1 Contract identity (A / B) | **Option A — side-table resolver, frozen `OptionLeg`.** Introduce `ContractRef` and `ChainSnapshot`; do not add broker-specific identity to the canonical domain model. |
| Q2 Routing granularity | **Per-capability routing** with an ordered source list per capability, health-aware circuit breaking, and shared Dhan throttling. No global broker switch. |
| Q3 Greeks provenance across the source transition | **(ii) Switch at a logged seam with a guarded grace period.** Dhan is the active Greeks source while Upstox returns zero delta on the held strikes; when Upstox re-acquires pricing, transition back after verification, with delta-stop suppression for the transition session. |
| Q4 Stale or missing Greeks fallback order for the yearly book | Live routed delta → last-known capture delta (max 3 trading days, with intraday action gated at 1 trading day age) → fail closed. The ±1 approximation is banned from yearly-book gates and stops. No unvalidated local model. |
| Q5 Pre-roll vs post-roll scope | **Split is sound.** Chain routing, contract resolver, source tags, token-staleness alerting, and the yearly bootstrap wiring land before the roll. LTP/candle routing, the 27-importer migration, token auto-renewal, and streaming stay post-roll. Add the Upstox BOD coverage check to the pre-roll bucket. |

---

## Design Rationale

### Q1 — Option A: side-table resolver

The council unanimously recommends Option A. The reasoning is convergent across all four panelists and their peer reviews:

`OptionLeg` is a canonical, broker-neutral domain type. `instrument_key` (Upstox) and `security_id` (Dhan) are infrastructure-layer routing identifiers. Adding an optional `instrument_key` to `OptionLeg` (Option B) would couple the domain model to Upstox's identity namespace, make `None` a normal outcome that selection code must defensively handle, and require a schema change if a third source is ever added. Option A avoids all three problems.

Three distinct concepts must be kept separate:

1. **Contract identity** — `ContractRef(underlying, expiry, strike, side)`: broker-neutral, mathematical.
2. **Canonical ledger key** — the Upstox `instrument_key` already persisted in `paper_trades`, `trades`, and snapshot tables. Not migrated.
3. **Source-native identifier** — Upstox key or Dhan (exchange segment, security id), resolved bidirectionally by a pure `ContractResolver`.

A critical refinement (identified by the top-ranked response and validated by peer review): `ChainSnapshot.instrument_keys` must map to **Upstox ledger keys** even when `greeks_source="dhan"`, because the downstream ledger requires Upstox keys. The resolver is a separate collaborator; the snapshot carries the map consumers need. The map is allowed to be **partial** — a Dhan chain may contain strikes that Upstox's master does not list, and that is not an error at fetch time. It is a structural abort only at the point of **ledger write** (opening a paper leg or joining an existing trade record).

**Strike-list disagreement** between masters is made visible: `to_native(ref, "upstox")` returns `None` for an unmapped strike, and the bootstrap aborts the entry, not the chain read. Resolution uses exact master-data joins — never fuzzy matching.

A third source would require only a new resolver mapping, not a model change.

### Q2 — Per-capability routing

A global `DATA_BROKER` switch is structurally invalid given the capability asymmetry: orders and portfolio reads are Upstox-only (and blocked); far-expiry Greeks are Dhan-only for ~9 months; LTP and candles are available from both. A single switch either breaks execution or blinds the yearly book.

The router distinguishes **availability** (can the source respond?) from **suitability** (does the response contain usable data for the held legs?). An Upstox chain with one nonzero delta somewhere does not establish usable Greeks for a specific held position — a distinction all three top-ranked panelists emphasized.

The current `CompositeChainSource` all-zero-delta trigger is expected Upstox behavior past ~90 DTE, not an outage. It must remain a **per-request, per-expiry** fallback. Opening a source-wide circuit on it would send monthly chains to Dhan, violate the byte-identical monthly pin, and walk into Dhan's 4-second rate limit.

**Circuit-breaker failure taxonomy:**

| Failure | Meaning | Action |
|---|---|---|
| **805 (rate limit)** | Too fast | Back off (floor 4 s). Stay on Dhan. Do not flip source. Never tight-loop. |
| **806 (unsubscribed) or stale/missing token** | Capability unavailable | Mark `chain-on-Dhan` unhealthy. Alert via Telegram. Fall back to Upstox for that capability. Do not retry in a tight loop; recovery uses bounded probes. |
| **Empty or all-zero delta for this expiry** | Per-expiry data gap, not source outage | Fall back for **this expiry only**. Do not mark Upstox globally unhealthy. Do not contaminate near-expiry routing. |
| **Transport failure / `DataFetchError`** | This call failed | One bounded retry, then treat as temporary capability circuit. Log source and expiry. |

**Shared Dhan throttling** must coordinate all callers sharing the same account — capture cron and monitor daemon — not merely individual in-process limiters. Health state is keyed by `(source, capability)`, not by source globally.

**Minimum config surface** (declared through `Settings`, not env-var broker switches):

```
market_data.chain.sources: ["upstox", "dhan"]
market_data.quote.sources: ["upstox"]
market_data.candles.sources: ["upstox"]
market_data.chain.dhan_min_interval_s: 4
```

Orders, positions, and margin are not entries in this routing map — they stay outside this epic's scope.

### Q3 — Switch at a logged seam

The council considered three options:

- **(i) Pin to Dhan for the position's lifecycle.** Avoids discontinuity but conflicts with the epic's own rule that an 806 degrades to Upstox. A Dhan plan lapse would leave the yearly book with no legal delta source, since the pin forbids Upstox. Rejected.
- **(iii) Never compare across sources — gate on a source-independent measure (e.g., IVR).** IVR is not a substitute for directional delta exposure; delta stops, entry gates, and `PortfolioDelta` are delta-denominated. This option was identified as technically unsound by three of four peer reviewers. Rejected.
- **(ii) Switch at a logged seam.** Adopted, with the following protocol:

**Switch trigger:** Flip the position's active Greeks source from Dhan to Upstox only after **2 consecutive trading days** where Upstox returns non-zero delta on the **held** `ContractRef`s. Do not flip on a DTE threshold; the DDP-5 observation (DTE 91→90 transition) was one expiry and is not a universal boundary.

**Seam protection:** On the flip snapshot, persist both the Dhan and Upstox deltas. If absolute option-delta difference exceeds **0.05** or the relative gap exceeds **25%**, suppress delta-stop, delta re-entry, and delta entry gates for that position for **that session only**. Log a WARNING. Still snapshot both numbers. This band is a provisional safety limit — the first dual-read week should be logged and the band revised based on observed Upstox-vs-Dhan gaps on held strikes.

**What is not bridged:** The ±1 approximation is not used across the seam. No automatic blending. Collar legs sharing an expiry must use the same Greeks source.

**Quotes stay independently routable.** Pinning Greeks does not require pinning LTP.

### Q4 — Stale or missing Greeks fallback for the yearly book

The July 2 ruling's ±1 per lot approximation was designed for a context where delta approaches 1.0 or 0.0 rapidly. For a delta-0.15 far-dated call, it overstates position delta roughly six-fold and can block entries or trip caps wrongly. The council extends that ruling for the yearly namespace without reopening it for existing near-dated paper legs.

**Fallback order:**

| Priority | Source | Permitted use | Bound |
|---|---|---|---|
| 1 | Live routed chain delta | Normal strategy and portfolio decisions | Age ≤ monitor cadence (60 s initially) |
| 2 | Last-known delta from daily capture store | **Display and degraded paper aggregation only.** No new entries, rolls, delta-stop exits, or delta entry gates. | Age ≤ **1 trading day** for any automated action; age ≤ **3 trading days** for explicitly-labelled diagnostic display |
| 3 | Fail closed | Alert and refuse to act | When no eligible observation exists within the 3-trading-day window |

**Explicitly banned from yearly-book gates and stops:** the ±1 approximation. It may still be computed for a diagnostic line but must not enter `check_entry_allowed`, a delta stop, or a yearly roll decision.

**Local Black-Scholes / Black '76 from Dhan IV** is not in the pre-roll path. The settled IV model is Black '76 on the Nifty futures forward — introducing a second model next to the broker model is a new discontinuity. It is deferred to post-roll and built only if capture-store outages show last-known aging out within the 3-day window. If built, it requires a separately validated estimator with explicit forward, timestamp, rate, and model provenance.

**Alert threshold:** When the newest usable delta is older than 1 trading day, the monitor must alert and suppress delta-dependent automation. This covers the first missed weekday capture, a stale Dhan token discovered at monitor start, and a capture cron failure.

### Q5 — Pre-roll vs post-roll scope

The split is sound. The council confirms the boundary and adds one item to the pre-roll bucket:

**Must land before the Dec 2026 roll (2026-12-29):**

- `ContractResolver` + `ChainSnapshot` (YF-6 depends on it)
- Per-expiry zero-delta fallback with the 805/806/empty-chain distinctions above
- `greeks_source` and `delta_asof` tags on every held-position chain snapshot from the first Dec 2027 read
- Token-staleness **alert** (not programmatic renewal — that is unresolved and not a roll prerequisite; a weekday stale token must page, then follow Q4)
- Shared Dhan rate limiter across capture and monitor
- **Upstox BOD coverage check** (moved earlier): does the Upstox instrument master list Dec 2027 contracts on the date of intended entry? If it does not, the yearly ledger key question must be resolved before the roll — not discovered on roll day.
- Offline tests: config parse; monthly fixture selects Upstox without calling Dhan; far-expiry all-zero Upstox falls through to Dhan without changing a near-expiry on the next call; 805 does not flip; 806 and stale token do not issue a Dhan call and emit an alert; missing Upstox key aborts the bootstrap write, not the parse; default pytest has no network, no token, no real DB.

**Safely deferred to post-roll:**

- LTP and candle routers
- Migration of the 27 direct `UpstoxMarketClient` importers
- `MarketStream` implementation
- Programmatic Dhan token renewal
- Kite / Zerodha
- Local Black '76 fallback estimator
- Broad auth abstraction (`BA-14`/`BA-15`)

**Constraint on the deferred bucket:** New yearly code must not add another direct `UpstoxMarketClient` chain import while the migration waits.

---

## Data Model / Schema Detail

### New frozen types (additive, `OptionLeg` unchanged)

```python
# src/models/contract.py
from datetime import date
from decimal import Decimal
from typing import Literal, Mapping
from datetime import datetime
from pydantic import BaseModel

class ContractRef(BaseModel, frozen=True):
    underlying: str          # normalized, e.g. "NIFTY"
    expiry: date
    strike: Decimal
    side: Literal["CE", "PE"]

class ChainSnapshot(BaseModel, frozen=True):
    chain: OptionChain
    greeks_source: Literal["upstox", "dhan"]
    fetched_at: datetime                          # UTC, always recorded
    instrument_keys: Mapping[ContractRef, str]    # Upstox ledger keys; partial is legal
```

`instrument_keys` maps to Upstox keys even when `greeks_source="dhan"`. The resolver is a separate collaborator:

```python
class ContractResolver(Protocol):
    def to_native(self, ref: ContractRef, broker: Literal["upstox", "dhan"]) -> str | None: ...
    def from_native(self, broker: Literal["upstox", "dhan"], native_key: str) -> ContractRef | None: ...
```

Built from each broker's instrument master via exact joins. Duplicate or ambiguous mappings are structural errors.

### Config surface (all via `Settings`)

```
market_data.chain.sources: ["upstox", "dhan"]
market_data.quote.sources: ["upstox"]
market_data.candles.sources: ["upstox"]
market_data.chain.dhan_min_interval_s: 4
yearly_chain_monitor_cadence_s: 60
greeks_fresh_max_age_s: 120
greeks_cache_max_age_trading_days: 3
greeks_action_max_age_trading_days: 1
```

### Persisted columns (all `TEXT NULL`, additive — old rows stay `NULL`)

| Table | New Column | Values |
|---|---|---|
| `paper_leg_snapshots` | `delta_source` | `upstox`, `dhan`, `last_known`, `unavailable` |
| `paper_leg_snapshots` | `delta_asof` | ISO timestamp of the delta observation actually used |
| `paper_overlay_pnl_snapshots` | `chain_source` | `upstox`, `dhan`, `last_known` |
| `paper_overlay_pnl_snapshots` | `chain_fetched_at` | ISO timestamp |

Provenance is recorded at **leg level** (`paper_leg_snapshots`), not only at the aggregate level. If `paper_overlay_pnl_snapshots` persists an aggregated delta, the contributing leg observations are linked through `delta_asof`, not collapsed into a single potentially misleading source string.

Monetary and Decimal values stored as TEXT per the settled convention. No new tables are required for the pre-roll scope — the existing far-expiry capture store (`FC-*` tables) serves as the last-known delta cache; the leg snapshots record which observation was used.

### What stays unchanged

- `OptionLeg` — no new fields
- `OptionChain` — no new fields
- Parquet schemas — no changes
- `paper_trades.instrument_key` — stays the Upstox key; yearly entry writes it only when `to_native(ref, "upstox")` returns non-`None`
- All existing persisted `instrument_key` values — not migrated, not reinterpreted

---

## Historical Data Handling

New columns are `NULL` on all pre-epic rows. Readers treat `NULL` `delta_source` as **unknown provenance** — not as a fabricated "Upstox" attribution. For monthly positions that predate this epic, current behavior is unchanged; no historical source is inferred or backfilled.

If a pre-existing yearly position exists at the time the new delta-dependent monitor is enabled, it requires an explicit, recorded source assignment before the monitor may act on its delta observations.

---

## Dissenting Notes

**Q1:** No dissent. All four panelists and all peer reviews agreed on Option A. The only friction point is what happens if Upstox's BOD file does not list Dec 2027 contracts at roll time — the resolver cannot produce an `instrument_key`, and a strict reading of "unresolved key aborts" blocks entry. The council's position: abort the **ledger write**, not the chain read. If the BOD check (pre-roll deliverable) confirms missing coverage, a dedicated architectural decision is required before the roll — not a silent fallback to serialized `ContractRef` identity.

**Q3:** The strongest dissent. One panelist recommended pinning to Dhan for the position's lifecycle (avoiding the September seam entirely); another recommended gating on IVR instead of delta. Pinning was rejected because it conflicts with the 806 degradation rule and creates a dead-end on Dhan plan lapse. IVR was rejected because it is not a substitute for directional delta exposure. The adopted switch-at-seam approach carries a known risk: the 0.05 / 25% tolerance band is a judgment, not a measurement. The first dual-read week (when Upstox Greeks return for Dec 2027 strikes) must be logged with both providers' values, and the band must be revised based on observed gaps.

**Q4:** Debate on maximum cache age (1 day vs. 3 days vs. 7 days). The 7-day proposal was rejected as unsupported — far-dated options still move materially on underlying and volatility shifts. The compromise: 1 trading day for any automated action, 3 trading days for labelled diagnostic display. The ±1 approximation is not overturned outside the yearly namespace.

---

## Stage 1 — Individual Responses

### openai/gpt-6.1-sol

CONTEXT.md ✓ — reviewed the supplied project state and council materials. Scope: architecture recommendation only; no code or repository changes. Recommendations below preserve the July 2 pure-risk-layer ruling and distinguish **usable market data** from a successful broker response.

## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Q1 Contract identity (A / B) | **A: side-table resolver with frozen `OptionLeg`.** Keep persisted Upstox keys; normalize contract identity separately from broker-native identifiers. |
| Q2 Routing granularity | **Per-capability routing**, with request-level requirements and source affinity for held-position Greeks. A global broker switch cannot express the required configuration. |
| Q3 Greeks provenance across the source transition | **(i) Pin the Greeks source for a position’s lifecycle.** Dec 2026 positions use Upstox; Dec 2027 positions use Dhan through expiry. Do not automatically switch when Upstox Greeks reappear. |
| Q4 Stale or missing Greeks fallback order for the yearly book | Fresh pinned-source delta → bounded last-known delta → July-rule approximation for explicitly degraded paper portfolio aggregation. **Suppress automated delta-dependent decisions on stale/missing data.** Do not introduce unvalidated local Black-Scholes. |
| Q5 Pre-roll vs post-roll scope | The split is sound. Move **held-leg identity coverage, provenance persistence, shared Dhan throttling, outage behavior and operational readiness tests** into pre-roll scope. Broad quote/candle routing and importer migration can remain post-roll. |

## Design Rationale

### Q1 — Separate contract identity from market observations

Option A best preserves the existing model and ledger contracts. It also avoids making `instrument_key=None` a normal outcome that selection code might discover only after ranking or attempting entry.

Use three distinct concepts:

1. **Contract identity:** underlying, exchange segment, expiry, strike and option side.
2. **Canonical ledger key:** the existing Upstox `instrument_key`.
3. **Source-native identifier:** Upstox key or Dhan exchange segment plus security ID.

The underlying in `ContractRef` must be normalized, not a free-form broker display name. Strike must be `Decimal`; expiry must be a date.

Resolve through exact master-data joins, never fuzzy matching. Missing or ambiguous mappings are structural failures for selected or held contracts and cannot be waived by `--log-only-gates`.

**Different strike lists are not inherently an error.** A snapshot can contain source-listed contracts absent from another source. Selection must establish that its chosen contract has a unique canonical ledger key. Held-position monitoring must explicitly establish coverage of every required held leg.

This distinction matters because the current `_is_chain_empty_or_zero_delta()` accepts a chain if **any** leg has nonzero delta. That is insufficient for monitoring a particular position.

A third source strengthens the case for A: add another native-ID mapping without modifying `OptionLeg` or persisted trade keys.

The blast radius is contained to new chain consumers and their adapters. The 27 legacy importers and 15 parser callers need not migrate merely to establish this seam.

### Q2 — Route capabilities, then evaluate suitability

A global switch is not adequate: Dhan-only far-expiry Greeks must coexist with Upstox quotes and Upstox-only execution interfaces. Execution and portfolio reads remain outside this routing epic.

Routing needs two stages:

- **Availability:** token validity, subscription health, transport success and throttling.
- **Suitability:** contract identity, held-leg coverage, freshness and required fields.

An Upstox response with zero held-leg Greeks is not a successful Greeks fallback merely because HTTP succeeded.

Minimum failure distinctions:

| Condition | Required behavior |
|---|---|
| **805 / rate limit** | Shared limiter and bounded backoff; no tight retry. Do not classify as subscription loss. |
| **806 / unsubscribed** | Open the affected data-capability circuit, alert, and attempt only a suitable configured fallback. Recovery uses bounded probes. |
| **Expired/invalid token** | Track authentication health separately; suppress repeated requests until credential refresh or a bounded recovery probe. Alert promptly. |
| **Empty chain** | Treat as request-specific data unavailability; do not immediately disable unrelated expiries or capabilities. |
| **Partial or zero required-leg Greeks** | Mark the request unsuitable for Greeks-dependent use, even if other strikes have populated Greeks. |
| **Timeout/transport failure** | Bounded retries followed by a temporary capability circuit; no unbounded blocking of the monitor. |

The four-second Dhan spacing must cover **all callers sharing the rate-limit scope**, including capture and monitor processes. Separate in-process limiters are insufficient if both processes call the same account.

Offline tests must cover these distinctions, recovery, pinned-source behavior, missing/ambiguous identities, partial held-leg coverage, concurrent callers, and unchanged monthly routing.

### Q3 — Pin the source; do not create an automatic September seam

Pin the Greeks source at entry and persist it with the position’s opening trade records:

- Dec 2026 yearly positions: Upstox.
- Dec 2027 yearly positions: Dhan.
- Collar legs: one common Greeks source for the pair.

Keep quotes independently routable. Pinning Greeks does not require pinning LTP.

**No cross-source delta tolerance band is needed**, because automatic cross-source switching is prohibited. Existing strategy delta thresholds remain unchanged; this ruling does not calibrate new yearly thresholds.

If Dhan becomes unavailable, Upstox may supply comparison observations, but they must not silently become the active delta-stop series. Any deliberate source reassignment requires a recorded operator decision and fresh observations from both sources where available. Until a separate transition policy is validated, automatic reassignment stays disabled.

Pinning the provider cannot guarantee an unchanged model: brokers may alter their calculations without exposing a version. Record that uncertainty rather than inventing a model version.

### Q4 — Separate stale valuation from authority to act

Recommended initial operational bounds, to be validated during the paper run:

| Delta quality | Bound | Permitted use |
|---|---|---|
| Fresh pinned-source observation | Age **≤120 seconds** | Normal strategy and portfolio decisions |
| Last-known pinned-source observation | Age **≤15 minutes**, DTE **>30**, underlying move since observation **≤1%** | Degraded reporting and paper portfolio aggregation; **not** new delta-dependent entries, rolls or delta-stop exits |
| Older daily-capture observation | At most **24 hours** | Clearly labelled diagnostic/reference display only |
| No eligible observation | July-rule approximation | Explicitly degraded paper portfolio aggregation only |

These are proposed safety limits, not findings derived from capture data.

For the yearly monitor, begin with a **60-second cadence**, sharing fetched chains across consumers where possible. Cross the 120-second freshness bound: alert and suspend delta-dependent automation. Other independently valid rules—such as an expiry rule—need not be disabled solely because Greeks are stale.

The daily capture store is useful for recovery and diagnosis, but daily data alone cannot support intraday delta-stop execution. Persist operational last-known observations from successful monitor fetches as well.

**Do not add local Black-Scholes as an outage shortcut.** Dhan IV may itself be stale, and a spot-based model would conflict with the settled Black ’76/Nifty-futures-forward approach. A local estimate requires a separately validated estimator with explicit forward, timestamp, rate and model provenance.

The July ruling remains intact: `src/risk/` receives a caller-resolved delta map and performs no I/O. Where the approximation is used, expose the result as degraded; do not let it masquerade as an observed six-fold increase in exposure. Live-money delta-dependent actions remain fail-closed.

### Q5 — Pre-roll scope must include ongoing operation

Before enabling Dec 2027 entry, require:

- Exact selected-contract and held-contract mapping.
- Source pinning and persisted provenance.
- Shared rate limiting across capture and monitor.
- Token-expiry detection and a documented renewal procedure.
- Freshness evaluation, bounded cache, alerts and action suppression.
- Routed monitor, entry-risk and EOD snapshot paths for the yearly namespace.
- Offline outage/recovery tests and an opt-in live readiness check.
- Confirmed capability access and liquidity for the intended expiry.

Programmatic token renewal is **not** mandatory if unsupported. A reliable manual renewal workflow with expiry alerts is mandatory. Broad auth abstraction can be cut.

Broad LTP/candle migration, streaming implementation, Kite support and migration of unrelated direct importers remain post-roll. Any specific legacy importer serving a required yearly Greeks path must move earlier.

## Data Model / Schema Detail

### New frozen types

```text
ContractRef
  underlying: str                 # normalized identity
  exchange_segment: str
  expiry: date
  strike: Decimal
  side: Literal["CE", "PE"]

NativeContractId
  source: str
  exchange_segment: str
  native_id: str

ChainSnapshot
  chain: OptionChain
  source: str
  observed_at: datetime | None     # provider timestamp, when available
  fetched_at: datetime             # UTC, always recorded
  keys: Mapping[ContractRef, str]  # canonical Upstox ledger keys
  native_ids: Mapping[ContractRef, NativeContractId]
  parser_version: str
  provider_model_version: str | None
```

Mappings must be defensively frozen, not merely stored inside a frozen wrapper. Resolve native IDs bidirectionally; reject duplicate mappings.

A separate per-leg observation type should carry delta, source, timestamps, model metadata and quality. Avoid adding cached Greeks to a fresh chain without per-leg provenance.

### Config surface

Declare all settings through `Settings`:

```text
market_data_routes:
  chain: [upstox, dhan]
  quote: [upstox]
  candles: [upstox]

chain_policies:
  monthly: existing behavior
  yearly: source affinity determined at entry

dhan_chain_min_interval_seconds: 4
yearly_chain_monitor_seconds: 60
greeks_fresh_max_age_seconds: 120
greeks_cache_max_age_seconds: 900
greeks_cache_max_underlying_move: Decimal("0.01")
greeks_cache_min_dte: 30
```

Timeouts, bounded retry counts and circuit recovery intervals also need explicit configuration. No execution routing settings belong here.

### Persistence

Preserve `OptionLeg`, existing chain-file schemas and all persisted instrument keys.

Add:

- **`paper_trades.greeks_source_pin TEXT NULL`** — populated on yearly opening option trades; closing trades retain the associated pin.
- **New `paper_leg_greeks_observations` table**, keyed by strategy, canonical instrument key and observation ID/time:
  - `strategy_name`, `instrument_key`
  - `greeks_source`
  - `greeks_observed_at`, `greeks_fetched_at`
  - `delta TEXT`
  - `underlying_price TEXT`
  - `greeks_quality`
  - `provider_model_version NULL`
  - `parser_version`
- **`paper_leg_snapshots` additive fields**:
  - `greeks_source`
  - `greeks_observed_at`
  - `greeks_quality`
  - `provider_model_version`
  - `greeks_observation_id`

Use the new observation table as the operational cache. Store monetary and Decimal values as TEXT.

**No Greeks column is required on `paper_overlay_pnl_snapshots` solely for P&L reporting.** Provenance belongs at leg level. If that table persists a delta aggregate, link its contributing observations rather than assigning one potentially misleading source string.

Exact existing snapshot keys and migration compatibility must be checked against the repository before implementation.

## Historical Data Handling

Additive fields remain `NULL` on historical rows. Do not infer historical provider/model provenance or fabricate source pins.

Existing open monthly positions retain their current behavior. A pre-existing yearly position requires an explicit, recorded source assignment before enabling the new delta-dependent monitor.

## Dissenting Notes

No panel votes or disagreements were supplied; these are architectural trade-offs, not attributed dissent.

- **Option B** simplifies leg selection, but an optional key does not resolve master disagreement and introduces nullable identity into every canonical leg. A is preferable under the frozen-model constraint.
- **Automatic source switching** offers better availability and lower Dhan dependency, but a tolerance band cannot be justified without paired provider observations. Pinning is the safer initial paper policy.
- **Longer stale-cache windows** reduce alerts but weaken stop semantics. Daily capture data should remain diagnostic, not silently authorize intraday actions.

### google/gemini-3.1-pro-preview

```markdown
## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Q1 Contract identity (A / B) | **Option A (side-table resolver).** Preserve the frozen `OptionLeg` and `OptionChain`. Introduce `ContractRef` and `ChainSnapshot` to map canonical domain identity to broker-specific native keys without polluting the domain models. |
| Q2 Routing granularity | **Per-capability routing.** A global switch is structurally invalid given the capability asymmetry (Upstox-only orders vs. Dhan-only far-expiry Greeks). |
| Q3 Greeks provenance across the source transition | **Switch at a logged seam (Upstox takes precedence).** Do not pin to Dhan. When Upstox re-acquires pricing capability (~90 DTE), smoothly transition. Persist `greeks_source` on the snapshots. |
| Q4 Stale or missing Greeks fallback order for the yearly book | **(1) Live Routed Chain → (2) Last-known from DB (max 48h age) → (3) Alert/Fail Closed.** Explicitly ban the +/-1 approximation for far-dated legs. |
| Q5 Pre-roll vs post-roll scope | **The split is sound.** Only the chain capability, token freshness monitor, and contract resolver are strictly required to unblock the Dec 2026 roll. Migrating the 27 legacy LTP/candle importers is safely deferred. |

## Design Rationale

**Q1: Contract identity (Option A vs B)**
Option A is mandated by the Single Responsibility Principle and the imperative to keep domain models pure. `OptionLeg` is a canonical, mathematical representation of a contract. `instrument_key` (Upstox) and `security_id` (Dhan) are infrastructure-layer routing identifiers. Blending them (Option B) permanently couples the domain to the current brokers. If a third broker is ever added, a single `instrument_key` field becomes inherently ambiguous. 
By using `ChainSnapshot`, the infrastructure layer wraps the pure `OptionChain` with a translation dictionary (`keys: dict[ContractRef, str]`). The 15 existing callers of the parser can be updated to handle `ChainSnapshot` without fundamentally breaking the serialization schemas of `OptionLeg`.

**Q2: Routing granularity**
Per-capability routing is strictly required because NiftyShield operates in a hybrid state. Dhan is a read-only integration lacking order margin capabilities, while Upstox cannot price far-dated chains. A global switch would either break execution or blind the yearly book.
The router must implement a health-aware circuit breaker distinguishing temporary failures (Dhan 805 rate limit → async sleep/backoff, up to 4s) from capability degradation (Dhan 806 unsubscribed / empty chain / stale manual token → flip capability state to unhealthy and fallback to Upstox). 

**Q3: Greeks provenance across the source transition**
Upstox is the system's primary broker and order execution venue. Dhan is a fallback to cover a specific data gap (DTE > 90). When Upstox re-acquires the ability to calculate Greeks, the system must transition back to Upstox to align risk math with the actual execution venue. Pinning to Dhan for the option's lifecycle would incur unnecessary API calls against Dhan's strict 4-second rate limit. 
The transition should not use a "blended" band; it should be a hard switch (Upstox takes priority in the router config) with a logged seam. To protect against Delta stops being wrongly triggered by model discontinuity on the day of the switch, the Delta monitor must rely on the persisted `greeks_source`. If `greeks_source` changes from `dhan` to `upstox` between `T-1` and `T0`, a WARNING is logged and tight delta-stop execution should be manually reviewed (or given a 1-day grace period).

**Q4: Stale or missing Greeks fallback for the yearly book**
The Stage 3 fallback (using +/- 1 per lot) was designed for near-dated expirations where Delta approaches 1.0 or 0.0 rapidly. Applying this to a 360-DTE leg with a true delta of 0.15 wildly overstates risk, immediately blocking entry gates and tripping risk caps. 
For far-dated legs (DTE > 90), the system must query the `far-expiry-capture` store for the last known delta. The maximum acceptable age is **48 hours** (to bridge weekends/holidays). If no Delta < 48h old is found (e.g., token expired on Friday, now it is Tuesday), the system must **fail closed** and page the Telegram gateway. It must not guess.

**Q5: Pre-roll vs post-roll scope**
The proposed split cleanly isolates the critical path. The yearly overlay bootstraps and the risk/delta monitors only need `ChainSnapshot` and the `ds-chain-monitoring` circuit breakers to execute the roll successfully. The 27 legacy `UpstoxMarketClient` importers are reading LTP/Candles—capabilities Upstox handles perfectly for far-dated options today. Modifying them before the roll introduces unnecessary regression risk.

## Data Model / Schema Detail

**Python Models:**
```python
# src/models/options.py (Additive, keeps OptionLeg frozen)
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

class OptionSide(str, Enum):
    CE = "CE"
    PE = "PE"

@dataclass(frozen=True)
class ContractRef:
    underlying: str
    expiry: date
    strike: Decimal
    side: OptionSide

@dataclass(frozen=True)
class ChainSnapshot:
    chain: OptionChain
    source: str  # "upstox", "dhan", etc.
    keys: dict[ContractRef, str]  # Canonical Ref -> Broker Native String (e.g. "NSE_FO|63895")
```

**Router Config (in `src/config.py` / YAML):**
```python
class CapabilityRouting(BaseModel):
    chain: list[str] = ["upstox", "dhan"]
    ltp: list[str] = ["upstox"]
    candles: list[str] = ["upstox"]
    orders: list[str] = ["upstox"]
```

**SQLite Schema Changes:**
- `paper_overlay_pnl_snapshots`: Add `greeks_source TEXT NULL`.
- `daily_snapshots`: Add `greeks_source TEXT NULL`.
*(Both default to NULL to preserve historical rows; new snapshots populate with the `source` from `ChainSnapshot`).*

## Historical Data Handling

- No migration script is needed for Parquet files or existing `OptionLeg` DB rows, as the model remains untouched.
- `ALTER TABLE` statements will add `greeks_source` to `paper_overlay_pnl_snapshots` and `daily_snapshots`. Existing records will have `NULL`, which the system will interpret as the legacy default ("upstox").

## Dissenting Notes

- **Friction in Option A:** The council acknowledges that Option A requires modifying the 15 parser callers and the overlay bootstraps to extract `instrument_key` from `ChainSnapshot.keys[ref]`. Some developers may argue Option B is faster to implement. The council explicitly overrides this: development speed does not justify corrupting the canonical domain boundary. 
- **Grace Period on Mid-Lifecycle Transition:** The hard switch from Dhan to Upstox Greeks at ~90 DTE carries a known risk of tripping Delta Stops if Upstox's IV model differs significantly from Dhan's. While we rejected "pinning to Dhan", the execution layer must be defensively coded to ignore delta stop triggers that are solely the result of a source flip.
```

### x-ai/grok-4.7

## Summary Table

| Decision | Recommendation |
|----------|----------------|
| Q1 Contract identity (A / B) | **Option A.** `ContractRef` is the canonical identity. Upstox `instrument_key` and Dhan security id are native keys behind a bidirectional resolver. Do not add broker identity to `OptionLeg`. |
| Q2 Routing granularity | **Per-capability, per request for data quality; circuit-break only auth and subscription failures.** No global `DATA_BROKER` switch. Minimum surface: ordered source list for `chain`, `quote`, and `candles` only. |
| Q3 Greeks provenance across the source transition | **(ii) switch at a logged seam, with a one-session stop suppression.** Do not pin a position to Dhan for life. Do not run delta stops across an unlogged source change. |
| Q4 Stale or missing Greeks fallback order for the yearly book | **Live routed delta → last-known capture delta (max age 3 trading days) → fail closed for any action.** ±1 must not drive yearly gates or stops. Local Black '76 from Dhan IV is post-roll only. Alert and refuse to act once delta age exceeds 1 trading day. |
| Q5 Pre-roll vs post-roll scope | **Split is sound** if chain routing, resolver, source tags, token-staleness alert, and the yearly bootstrap wiring land before the roll. Move the Upstox BOD coverage check earlier. Leave LTP/candle migration, the 27-importer move, token auto-renewal, and the local IV model until after the roll. |

## Design Rationale

**Q1.** The key the ledger already stores is Upstox's `instrument_key`, and that column is not being migrated. The chain that actually has delta for a ~360 DTE leg is Dhan's. Those are different namespaces. Putting `instrument_key` on `OptionLeg` does not solve that: a Dhan parser can only fill an Upstox key by calling the same resolver Option A makes explicit. A single optional string also cannot survive a third source, and it collapses the case this book will actually hit — Dhan lists a strike Upstox does not, or the reverse — into one nullable field on a type that is supposed to be broker-neutral.

Option A keeps the blast radius on the chain consumers that already need a key (the overlay bootstraps, YF-6). It does not touch the 27 direct importers, the 15 parser callers, Parquet, or existing SQLite rows. `OptionLeg` stays frozen. Disagreement between masters stays visible: `to_native(ref, "upstox")` returns `None` instead of a leg that looks canonical but will not join `paper_trades`.

Two refinements to the epic's sketch of A:

- `ChainSnapshot.keys` must be the **Upstox** key map even when `greeks_source="dhan"`. A map of "whatever this broker calls the contract" forces every consumer to know which broker it just talked to. The resolver stays a separate collaborator; the snapshot carries the map the overlay ledger needs, and it is allowed to be partial.
- Structural abort applies to the **action that requires a key** (opening a paper leg, joining the existing ledger), not to the chain fetch itself. Fetching Dec 2027 Greeks must not fail just because the Upstox master has no row yet. DSM-1 has to check whether the Upstox BOD file even lists ~360 DTE contracts. If it does not, yearly rows cannot require a non-null `instrument_key` at entry; they persist `ContractRef` and fill the Upstox key when the master grows it. If the BOD does list them, abort-on-unresolved at entry is the right rule.

**Q2.** A global switch is wrong for this capability set. Orders, positions, and order margin stay Upstox-only and blocked. Far-dated Greeks are Dhan-only for about nine months. LTP and candles exist on both. `DATA_BROKER=dhan` would break the Upstox-shaped callers; `DATA_BROKER=upstox` blinds the yearly book.

The current `CompositeChainSource` trigger — every delta zero — is expected Upstox behaviour past ~90 DTE, not an outage. It must stay a **per-request, per-expiry** fallback. Opening a source-wide circuit on that would send monthly chains to Dhan, break the byte-identical monthly pin, and walk into error 805.

The circuit breaker distinguishes four outcomes:

| Failure | Meaning | Action |
|---|---|---|
| 805 | Too fast | Back off. Stay on Dhan. Do not flip source. Never tight-loop. Floor 4 s between Dhan chain calls. |
| 806, or token missing/stale before the call | Capability unavailable | Mark **chain-on-Dhan** unhealthy. Alert. Fall back to Upstox for that expiry. Do not retry in a loop. |
| Empty or all-zero delta | This expiry has no usable Greeks | Fall back for **this expiry only**. Do not mark Upstox unhealthy. |
| Transport / `DataFetchError` | This call failed | One bounded retry, then same as 806 for this call. Log source and expiry. |

Health is `(source, capability)`, not "Dhan is down" and not "this expiry looked empty." Quote and candle health are separate and are not required before the roll.

Offline tests that must exist before any consumer moves: config parse; monthly fixture still selects Upstox and does not call Dhan; one far expiry with all-zero Upstox delta falls through to Dhan without changing a near expiry on the next call; 805 does not flip; 806 and a stale token do not issue a Dhan call and do emit an alert; a missing Upstox key aborts the bootstrap write, not the parse; default pytest has no network, no token, and no real DB.

**Q3.** Pinning the position to Dhan until expiry conflicts with the lapse rule already adopted for this epic: 806 degrades to Upstox. A pin turns a plan lapse into a stuck book. It also does not buy a clean portfolio delta — monthly legs stay on Upstox, and `PortfolioDeltaTracker` sums the map it is given. The series was always mixed at book level.

Never-compare is the right rule for the seam, not for the nine months when Dhan is the only non-zero source. During that window, Dhan delta is the position's delta.

Switch rule:

- Flip the position's active Greeks source only after **2 consecutive trading days** where Upstox returns non-zero delta on the **held** `ContractRef`s. Do not flip on a DTE threshold. DDP-5 was one expiry.
- On the flip snapshot, persist both deltas. If absolute option-delta differs by more than **0.05**, or the relative gap is more than **25%**, suppress delta-stop, delta re-entry, and delta entry gates for that position for **that session**. Alert. Still snapshot both numbers.
- Do not bridge the seam with the ±1 approximation.

**Q4.** The 2026-07-02 ±1 paper fallback stays in force for near-dated paper legs, where delta is O(1). It is the wrong fallback for a 0.15 far-dated call: it overstates position delta about six-fold and can block an entry or trip a cap. Extend that ruling for the yearly namespace; do not reopen it.

Act only on:

1. Live routed chain delta for that expiry (`greeks_source` tagged).
2. Last-known delta from the daily Dhan capture store for the same `ContractRef`, age ≤ **3 trading days**, tagged `last_known`.

Alert, and **do not act** (no entry, no delta-stop, no roll), when the newest usable delta is older than **1 trading day**. That includes the first missed weekday capture and a stale Dhan token discovered at monitor start. Display may keep showing last-known through 3 trading days with an explicit stale label. Older than 3 trading days: fail closed, ERROR, alert. No silent ±1.

±1 may still be computed for a diagnostic line. It must not be passed into `check_entry_allowed`, a delta stop, or a yearly roll decision.

Local delta from Dhan IV is not in the pre-roll path. The settled IV model is Black '76 on the Nifty futures forward, not Black-Scholes. A second model next to the broker model is a new discontinuity, and the capture store already exists to avoid that. Build it only if post-roll outages show last-known aging out inside the 3-day window.

**Q5.** Nothing in the LTP or candle path, and nothing in the 27-importer migration, is on the critical path to holding a Dec 2027 leg. New yearly code must not add another direct `UpstoxMarketClient` chain import while that migration waits.

What cannot slip past the roll:

- Resolver plus `ChainSnapshot` (YF-6 is useless without it).
- Per-expiry zero-delta fallback with the 805/806 split above. If that logic is left inside the later router story, the first far-expiry read either blinds the book or contaminates monthly routing.
- Token-staleness **alert**. Programmatic renewal is unresolved and is not a roll prerequisite. A weekday stale token must page, then follow Q4.
- Source tag on every held-position chain snapshot from the first Dec 2027 read, or the Sep 2027 seam has no baseline.
- BOD coverage check: does Upstox list the Dec 2027 contracts on the date you intend to open them?

Safe to cut from the pre-roll bucket: quote and candle routers, importer migration, `MarketStream`, Kite, Dhan token auto-renewal, local Black '76 fallback.

## Data Model / Schema Detail

New types, frozen, no change to `OptionLeg`:

```python
class ContractRef(BaseModel, frozen=True):
    underlying: str          # same symbol the chain call already uses, e.g. "NIFTY"
    expiry: date
    strike: Decimal
    side: Literal["CE", "PE"]

class ChainSnapshot(BaseModel, frozen=True):
    chain: OptionChain
    greeks_source: Literal["upstox", "dhan"]
    fetched_at: datetime     # timezone-aware
    instrument_keys: Mapping[ContractRef, str]  # Upstox keys; partial is legal
```

Resolver, pure, built from each broker's instrument master, not from the live chain:

```python
class ContractResolver(Protocol):
    def to_native(self, ref: ContractRef, broker: Literal["upstox", "dhan"]) -> str | None: ...
    def from_native(self, broker: Literal["upstox", "dhan"], native_key: str) -> ContractRef | None: ...
```

`instrument_keys` on the snapshot is `to_native(ref, "upstox")` for strikes present in `chain`. Absence is not stored as `""`.

Config, capability lists, not a broker switch:

```text
market_data.chain.sources = ["upstox", "dhan"]
market_data.chain.dhan_min_interval_s = 4
market_data.quote.sources = ["upstox"]
market_data.candles.sources = ["upstox"]
```

Orders, positions, and margin are not entries in this map.

Persisted columns, all nullable so old rows stay valid. New overlay writes set them:

| Table | Column | Values |
|---|---|---|
| `paper_overlay_pnl_snapshots` | `chain_source` TEXT | `upstox`, `dhan`, `last_known` |
| `paper_overlay_pnl_snapshots` | `chain_fetched_at` TEXT | ISO timestamp of the delta actually used |
| `paper_leg_snapshots` | `delta_source` TEXT | same vocabulary, plus `unavailable` when fail-closed |
| `paper_leg_snapshots` | `delta_asof` TEXT | ISO timestamp of that delta |
| far-expiry capture store (FC-* table, unchanged grain) | `source` TEXT, `fetched_at` TEXT | already the last-known store; both columns required on new rows |

`greeks_model` is our label, not a broker version: `upstox_chain_v1` or `dhan_chain_v1`, stored only if a capture row already has a free text field. Do not invent a broker model version. No new table. `paper_trades.instrument_key` stays the Upstox key; yearly entry writes it only when `to_native(..., "upstox")` hits. If the BOD check shows it will miss at roll time, the yearly ledger key is `ContractRef` serialized as `underlying|expiry|strike|side`, and `instrument_key` is filled later — that is a YF-1 schema confirmation, not a silent NULL in a NOT NULL column.

## Historical Data Handling

Existing rows are not rewritten. New columns stay NULL on pre-epic snapshots; readers treat NULL `chain_source` as legacy Upstox for monthly history and as unknown for anything else. Persisted `instrument_key` values are not migrated, not backfilled, and not reinterpreted as Dhan security ids.

## Dissenting Notes

- **Q1.** Option B is smaller at the three bootstrap call sites and was the stronger "just read it off the leg" position. It loses on the cross-broker fact: the persisted key and the Greeks source are not the same broker, and a third source makes a single optional field a schema change anyway. The partial dissent that remains: if DSM-1 shows Upstox BOD has no Dec 2027 rows, a strict reading of "unresolved key aborts" will block the roll. Abort the ledger write, not the chain read, and decide the nullable-key yearly path before 2026-12-29.
- **Q3.** Pinning to Dhan until expiry is the cleaner single-position series and avoids a September 2027 stop firing on a model change. It was rejected because an 806 lapse would then have nowhere legal to go, and portfolio delta is already mixed with the monthly book. The 0.05 / 25% band is a judgment, not a measurement; the first dual-read week should be logged and the band revised if the real Upstox-vs-Dhan gap on held strikes is tighter.
- **Q4.** Fail-closed with no local model is stricter than a Black '76 bridge and can leave the monitor idle for days if the capture cron dies. That is accepted for paper. The ±1 rule is not overturned outside the yearly namespace.

### deepseek/deepseek-r1-0528

## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Q1 Contract identity (A / B) | Option A (side-table resolver) |
| Q2 Routing granularity | Per-capability routing |
| Q3 Greeks provenance across the source transition | (iii) Never compare across sources — gate on IVR |
| Q4 Stale or missing Greeks fallback order for the yearly book | Last-known delta (max 7d) → Dhan IV → Fail closed |
| Q5 Pre-roll vs post-roll scope | Split sound; add source tag to monitor path |

## Design Rationale
**Q1:** Option A preserves frozen models and minimizes blast radius. Existing consumers continue using Upstox keys directly; new yearly book uses resolver. Adding third source only requires new resolver mapping.

**Q2:** Per-capability routing handles asymmetry: Dhan for far-Greeks, Upstox for order margins. Global switch would break order execution. Circuit breaker distinguishes:
- 805 (backoff + retry)
- 806 (capability degradation + fallback)
- Empty chain (try next source)

**Q3:** Comparing deltas across sources introduces discontinuities. IVR (implied volatility percentile) is source-agnostic. Gates should use IVR thresholds instead of absolute delta values.

**Q4:** Far-dated deltas change slowly. Last-known delta (from daily capture) valid ≤7 days. Beyond 7d, compute from Dhan IV (if available) using Black '76. Fail closed prevents mis-hedging.

**Q5:** Token freshness monitoring (pre-roll) ensures Dec 2027 legs get Dhan Greeks. Migration of non-chain consumers can wait until post-roll without impacting yearly book.

## Data Model / Schema Detail
**New Types:**
```python
# src/models/contract.py
class ContractRef(NamedTuple):
    underlying: str
    expiry: date
    strike: Decimal
    side: Literal["CE", "PE"]

class ChainSnapshot(BaseModel):
    chain: OptionChain
    source: Literal["upstox", "dhan"]
    refmap: dict[ContractRef, str]  # Broker-specific key
```

**Config:**
```python
# .env
CHAIN_SOURCES=upstox,dhan  # Ordered fallback
LTP_SOURCES=upstox,dhan
CANDLE_SOURCES=dhan,upstox
```

**Persisted Columns:**
- `paper_overlay_pnl_snapshots`: add `delta_source TEXT`
- `paper_trades`: add `greek_source TEXT`

## Historical Data Handling
No action needed. Existing rows retain `instrument_key`; new resolver handles future contracts. NULL `delta_source` implies Upstox for backward compatibility.

## Dissenting Notes
- **Q1:** Minority favored Option B for simpler consumer code. Overruled due to frozen model violation risk.
- **Q3:** One panelist argued for source-pinning per position. Rejected due to operational complexity during Dhan→Upstox transition.
- **Q4:** Debate on max age (3d vs 7d). Settled at 7d given slow delta decay in far expiries.

## Aggregate Rankings (Stage 2 Peer Review)

- x-ai/grok-4.7: avg rank 1.25 (4 votes)
- openai/gpt-6.1-sol: avg rank 1.75 (4 votes)
- google/gemini-3.1-pro-preview: avg rank 3.0 (4 votes)
- deepseek/deepseek-r1-0528: avg rank 4.0 (4 votes)

---

## Prompt Sent (first 3000 chars)

```
=== NIFTYSHIELD PROJECT STATE ===

# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase. Read this before writing any code. Do not rely on session summaries or chat history. Repo:
> https://github.com/archeranimesh/NiftyShield

**Related files:** [MISSION.md](MISSION.md) — immutable mission + grounding principles | [DECISIONS.md](DECISIONS.md) | [REFERENCES.md](REFERENCES.md) | [TODOS.md](TODOS.md) | [PLANNER.md](PLANNER.md)
| [BACKTEST_PLAN.md](BACKTEST_PLAN.md) — Phase 0 active tasks only (~300 lines) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md) — Phase 1+ tasks (load only after Phase 0.8 gate) |
[LITERATURE.md](LITERATURE.md) — concept reference (Kelly, Sharpe, meta-labeling) | [LOGGING.md](LOGGING.md) — logging standard | [docs/plan/](docs/plan/) — one story file per task |
[INSTRUCTION.md](INSTRUCTION.md)

---

## Current State (as of 2026-08-26)

### What Exists (committed and working)

Full file-level module tree with per-file descriptions: **[CONTEXT_TREE.md](CONTEXT_TREE.md)**. Feature and bug-fix history with rationale (every `BUG-*` / `SNAP-*` / `PG-*` / council ruling
referenced below): **[DECISIONS.md](DECISIONS.md)**. Verbatim snapshot of the previous prose version of this section (nothing was deleted, only relocated):
**[docs/archive/CONTEXT_WHAT_EXISTS_2026-08.md](docs/archive/CONTEXT_WHAT_EXISTS_2026-08.md)**.

Top-level `src/` packages, one line each (detail → `CONTEXT_TREE.md`):

- `src/auth/` — Upstox OAuth + Nuvama request_id + Dhan manual-token login/verify flows.
- `src/client/` — `BrokerClient` / `ChainSource` protocols + impls (Upstox live/sandbox, Mock, Dhan, Composite); `factory.create_client(env)`; order exec + portfolio read blocked (static IP / daily
  token).
- `src/models/` — canonical domain types: `Leg`/`Trade`/`Strategy`/`DailySnapshot`/`PortfolioSummary` (portfolio.py), MF types (mf.py), `OptionLeg`/`OptionChain` frozen Pydantic (options.py).
- `src/portfolio/` — live (non-paper) P&L: `PortfolioStore`, `PortfolioTracker`, pure `summary.py`/`formatting.py`, `SnapshotService`, `overlay_coverage.py`; finideas strategies (ILTS, FinRakshak).
- `src/paper/` — paper-trading engine. Models: `PaperTrade`, `PaperPosition`, `PaperNavSnapshot`, `PaperLegSnapshot`, `PaperExitEvent`, `TrackComparisonSnapshot`, `TradeState` enum. `PaperStore`
  (SQLite — `paper_trades`, `paper_nav_snapshots`, `paper_leg_snapshots`, `paper_exit_events`, `gate_violations`, `warn_signal_state`, `paper_track_comparison_snapshots`, …). `PaperTracker`
  (`compute_pnl`, `compute_pnl_by_leg_group`), fill simulator, selectors. `cycle_pnl.py` (`reconstruct_cycles` / `get_last_cycle_realized_pnl` — round-trip cycle boundaries from the `paper_trades`
  ledger; shared with `scripts/dev/cycle_pnl_report.py` and BUG-043).
- `src/strategy/` — paper-backbone strategy layer. `PaperStrategy` protocol, `SignalEvent`/`ApprovedAction`/`LegSpec`/`LegClose`, `StrategyMonitor` daemon (tick loop, WARN d...
```