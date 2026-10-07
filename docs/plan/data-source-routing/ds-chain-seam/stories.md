# DS Chain Seam — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

Source of truth for every shape below: the ruling in `DECISIONS.md` ("Data source routing …, 2026-10-07, council") and `docs/archive/council/data_architecture/2026-10-07_data-source-routing.md` Stage
3 §Data Model / Schema Detail. Where this file and the ruling disagree, the ruling wins.

---

## DSC-1 — Contract types and resolver protocol

**Files to change / create:**
- `src/models/contract.py` — new. `ContractRef`, `ChainSnapshot`, `ContractResolver` (Protocol).
- `tests/unit/models/test_contract.py` — new (add `__init__.py` if the directory is new).

**Before any code (graph queries — do not write model constructors from memory):**
- `get_code_snippet("OptionChain")`, `get_code_snippet("OptionLeg")` — exact fields.
- `search_graph("ContractRef")`, `search_graph("ChainSnapshot")` — confirm no existing type with these names.

**What to implement:**

1. `ContractRef(BaseModel, frozen=True)`: `underlying: str` (normalised, e.g. `"NIFTY"`), `expiry: date`, `strike: Decimal`, `side: Literal["CE", "PE"]`.
2. `ChainSnapshot(BaseModel, frozen=True)`: `chain: OptionChain`, `greeks_source: Literal["upstox", "dhan"]`, `fetched_at: datetime` (UTC-aware, validated), `instrument_keys: Mapping[ContractRef,
   str]` — values are **Upstox ledger keys** even when `greeks_source="dhan"`; a partial map is legal.
3. `ContractResolver(Protocol)`: `to_native(ref, broker) -> str | None`, `from_native(broker, native_key) -> ContractRef | None`.
4. No concrete broker import in this module. `OptionLeg` and `OptionChain` are not touched.

**Tests (`tests/unit/models/test_contract.py`, no network, no real DB):**
- `test_contract_ref_equality_and_hash` — `Decimal("24000")` and `Decimal("24000.0")` give equal refs and equal hashes; usable as dict keys.
- `test_chain_snapshot_partial_instrument_keys_is_legal` — a snapshot with fewer keys than strikes constructs.
- `test_chain_snapshot_rejects_naive_fetched_at` — naive datetime raises.
- `test_models_are_frozen` — assignment raises.

**Commit:** `feat(models): add ContractRef, ChainSnapshot, ContractResolver`

---

## DSC-2 — Contract resolver implementation

**Files to change / create:**
- `src/client/contract_resolver.py` — new. Concrete resolver built from the two masters.
- `src/client/exceptions.py` — add `AmbiguousContractError(BrokerError)`.
- `tests/fixtures/` — a small Dhan instrument-master slice (sanitised) and a matching Upstox BOD slice with Dec 2026 and Dec 2027 NIFTY options.
- `tests/unit/client/test_contract_resolver.py` — new.

**Before any code:**
- `get_code_snippet("InstrumentLookup")` — reuse it for the Upstox side; do not fork a second contract-lookup helper (design review in `prompt.md`).
- Record the real Dhan master format from a downloaded file (segment and security-id columns) into the fixture; Animesh may need to supply the slice. Note the format in the commit body.
- Read `DSM-1`'s `roll_checks.md`: if the BOD does not list Dec 2027, stop and report — the council requires a separate decision.

**What to implement:**

1. Exact joins on (underlying, expiry, strike, side) between each master and `ContractRef`. No fuzzy matching.
2. `to_native(ref, "upstox")` returns the Upstox `instrument_key` or `None` when the master does not list that contract. `to_native(ref, "dhan")` returns the Dhan segment and security id in one
   documented string form.
3. A duplicate or ambiguous mapping in a master raises `AmbiguousContractError` at build time.
4. `from_native` is the exact inverse.

**Tests:**
- `test_round_trip_both_brokers` — canonical to native to canonical for every fixture contract.
- `test_unlisted_strike_returns_none` — a strike Dhan lists and Upstox does not returns `None` on the Upstox side, no exception.
- `test_duplicate_mapping_raises` — a master with two rows for one contract raises `AmbiguousContractError`.

**Commit:** `feat(client): add contract resolver over Upstox and Dhan masters`

---

## DSC-3 — Chain sources return `ChainSnapshot`; per-expiry fallback and health

**Files to change / create:**
- `src/client/chain_source.py` — `UpstoxChainSource`, `DhanChainSource`, `CompositeChainSource` return `ChainSnapshot`; the composite implements the failure taxonomy. Extend, do not replace.
- `src/client/source_health.py` — new. Health state keyed `(source, capability)` with bounded recovery probes; an injected alert callback (non-fatal, `NotifierProtocol`).
- `src/client/exceptions.py` — typed errors for rate-limit (805) and subscription / token (806 or stale token) if not already distinguishable.
- `tests/unit/client/test_chain_source.py` — extend.

**Before any code:**
- `get_code_snippet` for `CompositeChainSource`, `DhanMarketClient`, `parse_dhan_option_chain`; `trace_path("CompositeChainSource")` for current callers (none outside `src/client/` per recon).
- `DSM-1` `roll_checks.md` for the real 806 / stale-token shapes.

**What to implement (ruling §Q2 taxonomy):**

| Failure | Action |
|---|---|
| 805 | back off (floor 4 s), stay on Dhan, never flip, never tight-loop |
| 806 or stale / missing token | mark chain-on-Dhan unhealthy, alert, fall back to Upstox for that capability; recover with bounded probes |
| empty or all-zero delta for this expiry | fall back for **this expiry only**; Upstox is not marked unhealthy; the next near-expiry call is unaffected |
| transport failure / `DataFetchError` | one bounded retry, then a temporary capability circuit; log source and expiry |

Every snapshot carries `greeks_source`, `fetched_at` and `instrument_keys` (from the resolver; partial map legal). Availability and suitability are separate: a non-zero delta elsewhere in the chain
does not make Greeks usable for a specific held contract (callers check held contracts).

**Tests (the ruling's Q5 offline list):**
- `test_monthly_selects_upstox_without_dhan_call`
- `test_far_expiry_all_zero_falls_through_to_dhan_without_changing_next_near_expiry_call`
- `test_805_does_not_flip_source`
- `test_806_and_stale_token_issue_no_dhan_call_and_alert`
- `test_transport_failure_retries_once_then_opens_circuit`
- `test_default_pytest_has_no_network_token_or_db`

**Review:** `code-reviewer` and `greeks-analyst` (delta fields).

**Commit:** `feat(client): route chain sources by capability with per-expiry fallback`

---

## DSC-4 — Routing config and wiring

**Files to change / create:**
- `src/config.py` — chain routing settings through `Settings`: `market_data.chain.sources` (default `["upstox"]`), `market_data.quote.sources`, `market_data.candles.sources`,
  `market_data.chain.dhan_min_interval_s` (default 4). Defaults reproduce today's Upstox-only behaviour; `["upstox", "dhan"]` is the yearly setting.
- `src/client/factory.py` — builds the chain router from config; remains the only module naming concrete sources.
- `tests/unit/client/test_factory.py`, `tests/unit/test_config.py` — extend.

**Before any code:** `get_code_snippet("create_client")`; check how existing `Settings` nested config is declared (do not invent an env-var broker switch).

**What to implement:**

1. Parse the config; an unknown source name fails at startup, not at first call.
2. Quote and candle entries are accepted and validated but only `["upstox"]` is wired until `ds-router-migration/`.
3. Orders, positions and margin are not entries in this map.

**Tests:** config parse; default pins Upstox-only (regression); unknown source rejected.

**Commit:** `feat(client): chain routing config and factory wiring`

---

## DSC-5 — Cross-process Dhan throttle

**Files to change / create:**
- `src/client/shared_rate_limiter.py` — new. Implements the existing `RateLimiter` protocol (`src/client/dhan_market.py`) with state shared across processes.
- `src/client/factory.py` — inject it into `DhanMarketClient` where the in-process `SpacingRateLimiter` is built today.
- `tests/unit/client/test_shared_rate_limiter.py` — new.

**Before any code:** `get_code_snippet("SpacingRateLimiter")`, `get_code_snippet("RateLimiter")`, `search_graph("DhanMarketClient")` for every construction site (capture cron once it exists, monitor
daemon).

**What to implement:**

1. A limiter whose "last call" timestamp lives in shared state (default candidate: a lock file plus a timestamp file under the data directory; the task may pick another mechanism and records why).
2. The floor stays 4 s (`market_data.chain.dhan_min_interval_s`). A crashed holder cannot wedge the lock.
3. Injected `Clock` as today, so tests need no real sleeping.

**Tests (`tmp_path`, fake clock):**
- `test_two_instances_respect_the_floor` — two limiter instances on the same state path never grant calls closer than 4 s.
- `test_stale_lock_is_recovered` — a lock left by a dead holder does not block.

**Commit:** `feat(client): share the Dhan throttle across processes`
