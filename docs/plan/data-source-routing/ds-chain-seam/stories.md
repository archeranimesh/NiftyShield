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

1. `SourceId(str, Enum)`: the one vocabulary for data sources (`UPSTOX = "upstox"`, `DHAN = "dhan"`). Every other place that names a source — `ChainSnapshot.greeks_source`, the resolver, source health
   keys, routing config, and the persisted `delta_source` / `chain_source` text — uses `SourceId` values, so adding a source is one enum member, not an edit to each model (added 2026-11-03, design
   review). Persisted columns stay `TEXT`.
2. `ContractRef(BaseModel, frozen=True)`: `underlying: str` (normalised, e.g. `"NIFTY"`), `expiry: date`, `strike: Decimal`, `side: Literal["CE", "PE"]`.
3. `ChainSnapshot(BaseModel, frozen=True)`: `chain: OptionChain`, `greeks_source: SourceId`, `fetched_at: datetime` (UTC-aware, validated), `instrument_keys: Mapping[ContractRef, str]` — values are
   **Upstox ledger keys** even when `greeks_source` is `DHAN`, whichever source supplied the Greeks; a partial map is legal. The field name stays `instrument_keys` (the ruling fixes it); document the
   Upstox-ledger coupling in its docstring so no other broker's keys are put there.
4. `ContractResolver(Protocol)`: `to_native(ref, source: SourceId) -> str | None`, `from_native(source: SourceId, native_key) -> ContractRef | None`.
5. A shared pure predicate `has_usable_delta(chain, refs: Collection[ContractRef] | None = None) -> bool` (any non-zero delta in the chain, or on the given held contracts). DSC-3, DSN-3 and DSN-5 all
   call it; none re-implements a zero-delta check. It replaces `_is_chain_empty_or_zero_delta` in `chain_source.py`.
6. No concrete broker import in this module. `OptionLeg` and `OptionChain` are not touched.

**Tests (`tests/unit/models/test_contract.py`, no network, no real DB):**
- `test_contract_ref_equality_and_hash` — `Decimal("24000")` and `Decimal("24000.0")` give equal refs and equal hashes; usable as dict keys.
- `test_chain_snapshot_partial_instrument_keys_is_legal` — a snapshot with fewer keys than strikes constructs.
- `test_chain_snapshot_rejects_naive_fetched_at` — naive datetime raises.
- `test_models_are_frozen` — assignment raises.
- `test_source_id_values_are_the_persisted_strings` — `SourceId.DHAN.value == "dhan"`.
- `test_has_usable_delta_whole_chain_and_held_refs` — a chain with a non-zero delta elsewhere is usable as a whole but not for a held ref whose delta is zero or missing.

**Commit:** `feat(models): add ContractRef, ChainSnapshot, ContractResolver`

---

## DSC-2 — Contract resolver implementation

**Files to change / create:**
- `src/client/contract_resolver.py` — new. A `ContractMaster` protocol (`to_native(ref)`, `from_native(native_key)`; one implementation per broker master) and a `ContractResolver` that composes a
  `dict[SourceId, ContractMaster]`. A new broker is a new master registered in the dict, with no edit to the resolver.
- `src/client/exceptions.py` — add `AmbiguousContractError(BrokerError)`.
- `tests/fixtures/` — a small Dhan instrument-master slice (sanitised) and a matching Upstox BOD slice with Dec 2026 and Dec 2027 NIFTY options.
- `tests/unit/client/test_contract_resolver.py` — new.

**Before any code:**
- `get_code_snippet("InstrumentLookup")` — reuse it for the Upstox side; do not fork a second contract-lookup helper (design review in `prompt.md`).
- The fixtures already exist (2026-11-03): `tests/fixtures/contract_resolver/dhan_scrip_master_nifty_dec.csv` (598 NIFTY OPTIDX rows, expiries 2026-12-29 and 2027-12-28, full original header from
  `https://images.dhan.co/api-data/api-scrip-master-detailed.csv`: join columns `EXCH_ID`, `SEGMENT`, `SECURITY_ID`, `UNDERLYING_SYMBOL`, `SM_EXPIRY_DATE`, `STRIKE_PRICE`, `OPTION_TYPE`; the NSE
  derivatives segment is `D`) and `upstox_bod_nifty_dec.json` (265 NSE_FO records, same expiries, cut from `data/instruments/NSE.json.gz`; `expiry` is epoch milliseconds). 265 contracts are in both;
  333 Dhan-only contracts cover the unlisted-strike test. Do not recreate them; note the format in the commit body.
- Read `DSM-1`'s `roll_checks.md`: if the BOD does not list Dec 2027, stop and report — the council requires a separate decision.

**What to implement:**

1. Exact joins on (underlying, expiry, strike, side) between each master and `ContractRef`. No fuzzy matching.
2. `to_native(ref, SourceId.UPSTOX)` returns the Upstox `instrument_key` or `None` when the master does not list that contract. `to_native(ref, SourceId.DHAN)` returns the Dhan segment and security id
   in one documented string form. A `source` with no registered master raises a typed error, not `None`.
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
- `src/client/chain_source.py` — `UpstoxChainSource` and `DhanChainSource` return `ChainSnapshot` and stay thin (fetch, parse, tag). `CompositeChainSource` is generalised, not extended, into a
  `ChainRouter` that takes an ordered `list[tuple[SourceId, ChainSource]]` and implements the failure taxonomy; its two named `upstox` / `dhan` constructor slots go away (2026-11-03, OCP: a third
  source is a list entry). Keep `parse_dhan_option_chain` and the existing parsing as is.
- `src/client/capability_router.py` — new. The reusable part: ordered-source fallback plus `SourceHealth`, with the "is this result usable" check injected as a callable. The chain router passes
  `has_usable_delta`; `ds-router-migration/` DSR-2 reuses this for quotes and candles instead of building a second router.
- `src/client/source_health.py` — new. Health state keyed `(SourceId, capability)` with bounded recovery probes; an injected alert callback (non-fatal, `NotifierProtocol`).
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
- `test_third_source_routes_without_editing_router` — register a fake `SourceId` member's stub source and stub master in the router and resolver and show it routes, falls back and tags provenance with
  no edit to router, resolver or models (the extensibility acceptance test).

**Review:** `code-reviewer` and `greeks-analyst` (delta fields).

**Commit:** `feat(client): route chain sources by capability with per-expiry fallback`

---

## DSC-4 — Routing config and wiring

**Files to change / create:**
- `src/config.py` — chain routing settings through `Settings`: `market_data.chain.sources` (default `["upstox"]`), `market_data.quote.sources`, `market_data.candles.sources`,
  `market_data.chain.dhan_min_interval_s` (default 4). Defaults reproduce today's Upstox-only behaviour; `["upstox", "dhan"]` is the yearly setting.
- `src/client/factory.py` — builds the chain router from config; remains the only module naming concrete sources. Source construction is a registry `dict[SourceId, builder]`, not an `if/elif` chain;
  `create_client`'s existing env `if` chain is left alone.
- `tests/unit/client/test_factory.py`, `tests/unit/test_config.py` — extend.

**Before any code:** `get_code_snippet("create_client")`; check how existing `Settings` nested config is declared (do not invent an env-var broker switch).

**What to implement:**

0. **Upstox-only default wires the bare `UpstoxChainSource`, not a one-entry `ChainRouter`** (decided at DSC-3 close): the router raises `DataFetchError` on an all-zero chain, the bare source returns
   it, and "default behaves exactly as today" requires the latter. Use `ChainRouter` only when the configured list has more than one source.
1. Parse the config; an unknown source name (not a `SourceId`, or with no registered builder) fails at startup, not at first call. Follow the existing `Settings` nested-config style and use one naming
   scheme across DSC-4 and DSN-4. `market_data.chain.dhan_min_interval_s` is the only place the 4 s floor is stated; DSC-3's backoff, DSC-5's limiter and DSN-4's slot read it.
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
2. The floor is `market_data.chain.dhan_min_interval_s` (default 4 s); do not hardcode it. A crashed holder cannot wedge the lock.
3. Injected `Clock` as today, so tests need no real sleeping.

**Tests (`tmp_path`, fake clock):**
- `test_two_instances_respect_the_floor` — two limiter instances on the same state path never grant calls closer than 4 s.
- `test_stale_lock_is_recovered` — a lock left by a dead holder does not block.

**Commit:** `feat(client): share the Dhan throttle across processes`
