# Data source routing: canonical contract identity, routing granularity, and Greeks provenance for a far-dated yearly book

## System Context

NiftyShield reads market data from Upstox through `UpstoxLiveClient` / the legacy `UpstoxMarketClient`. `BrokerClient.get_option_chain` returns `list[dict[str, Any]]` — Upstox's raw wire rows
(`src/client/protocol.py:152`). Upstox's `instrument_key` (`NSE_FO|63895`) is the de facto canonical contract identity: 27 modules outside `src/client/` import `UpstoxMarketClient` directly, 15 call
`parse_upstox_option_chain`, 50 touch `InstrumentLookup`, and the key is persisted in `paper_trades`, `trades` and snapshot tables.

Dhan was added as a second source for far-dated chains. `DhanMarketClient.get_option_chain` (`src/client/dhan_market.py:188`) returns a canonical `OptionChain` (frozen Pydantic,
`src/models/options.py`) parsed by `parse_dhan_option_chain`. `CompositeChainSource` (`src/client/chain_source.py:50`) calls Upstox first and falls back to Dhan only when every Upstox delta is zero.
`OptionLeg` carries price and Greeks but **no `instrument_key`**; Dhan identifies contracts by (exchange segment, security id).

**Trigger:** epic `docs/plan/data-source-routing/`, opened 2026-10-07. It folds in `docs/plan/broker-abstraction/` (superseded in part) and the DA-4 relocation finding in
`docs/plan/dhan-far-expiry-chain/dhan-chain-adapter/findings.md` §DA-4.

## Mechanics of the problem

1. **Identity.** The overlay bootstraps (`auto_cc_bootstrap`, `auto_pp_bootstrap`, `auto_collar_bootstrap`) filter, rank and liquidity-gate the raw Upstox row list, and `OverlayConfig` needs
   `instrument_key`. A parsed `OptionChain` from `CompositeChainSource` cannot feed them: it has no key. Wiring Dhan in therefore needs a (strike, side, expiry) → Upstox key resolver, or a change to
   the chain model.
2. **Greeks provenance.** After the Dec 2026 expiry (2026-12-29) the yearly book holds Dec 2027 legs, about 360 DTE. Upstox returns zero Greeks past about 90 DTE (DDP-5 measured Dec 2026 flipping from
   zero at DTE 91 to non-zero at DTE 90, one expiry only), i.e. until about Sep 2027. For about nine months every delta the yearly book sees — delta stop, `PortfolioDelta`, EOD snapshot, entry gates —
   would come from Dhan. Around Sep 2027 Upstox Greeks return, so a position can see a model discontinuity in its own delta series mid-lifecycle (different IV source and rate assumptions).
3. **Capability asymmetry.** Dhan's data plan (Rs 499 / month, Rs 4,788 / year) covers: live LTP / quote, candles (5 years), live chain with delta, gamma, theta, vega, IV, OI, top bid / ask (one
   unique request per 3 s; error 805 seen at 3.2 s, so 4 s is used), and expired options (ATM +/- 10, IV only, no delta, bid or ask). Per a secondhand summary of the live-feed page (unverified), the
   WebSocket feed offers ticker / quote / full modes with OI and 5-level depth, **no Greeks**, up to 5 connections and 5,000 instruments per connection. Order margin, orders and positions are not
   routable to Dhan today (read-only integration; static IP).
4. **Token lifecycle.** The Upstox analytics token is long-lived. The Dhan token is a manual 24 h token (`DECISIONS.md` Dhan Integration). Whether it can be renewed programmatically is unresolved
   (story `ds-capability-map/` DSM-1). A stale Dhan token on a weekday makes the yearly book blind to delta, not merely late.

## Relevant existing machinery

- `src/client/protocol.py` — `BrokerClient`, `MarketDataProvider`, `MarketStream` (protocol only, no implementation).
- `src/client/factory.py` — `create_client(env)`, the only composition root; selects by environment, not by capability.
- `src/client/chain_source.py` — `ChainSource` (`:17`), `UpstoxChainSource` (`:21`), `DhanChainSource` (`:30`), `CompositeChainSource` (`:50`).
- `src/instruments/lookup.py` — `InstrumentLookup` over the Upstox BOD file; `get_expiry_candidates(preference=...)`.
- `src/risk/delta_tracker.py` — `PortfolioDeltaTracker.aggregate_delta(position_deltas: dict[str, Decimal] | None)`, pure and zero-I/O.
- `docs/plan/yearly-overlays/` — `OverlayTenorPolicy` registry (YF-3), `resolve_overlay_expiry` (YF-4), chain wiring (YF-6, depends on this epic), roll gate (YV-5).
- `docs/plan/dhan-far-expiry-chain/` — forward-only daily Dhan chain capture (FC-*) and the data-calibrated liquidity gate (FG-*).

**Already decided / out of scope for the council:**

| Parameter | Decision |
|---|---|
| Caller resolves the per-leg delta map; `src/risk/` stays pure, zero-I/O | `docs/council/2026-07-02_paper-delta-source-architecture.md` (active, not yet absorbed into `DECISIONS.md`) |
| Paper phase: missing, stale or failed delta data logs WARNING / ERROR and falls back to the +/-1 per lot approximation; live money later fails closed | same file, Stage 3 Fallback Policy |
| Dec 2026 yearly legs run on the Upstox chain; Dec 2027 uses Dhan Greeks | `docs/plan/yearly-overlays/README.md` scope decisions |
| Order execution and Upstox portfolio reads stay blocked; Dhan stays read-only | `src/client/CLAUDE.md` Active Constraints; `DECISIONS.md` Dhan Integration |
| Kite / Zerodha is not part of this epic | proposed 2026-10-07, pending Animesh confirmation (epic README open decision 1) |
| Persisted Upstox keys are not migrated | design constraint of this epic |

## The decision to resolve

### Option A — side-table resolver, frozen `OptionLeg`

Add a pure, bidirectional contract resolver per broker, built from each broker's instrument master: canonical `ContractRef(underlying, expiry, strike, side)` ↔ native key (Upstox `instrument_key`;
Dhan segment + security id). Chain sources return `ChainSnapshot(chain: OptionChain, source: str, keys: Mapping[ContractRef, str])`. `OptionLeg` and the Parquet / SQLite schemas stay frozen. Every
consumer that needs a key looks it up in `keys`. Cost: every selection site carries the snapshot, not just the chain, and the resolver must stay in step with two instrument masters.

### Option B — additive optional field on `OptionLeg`

Add `instrument_key: str | None = None` (and a `source` tag) to `OptionLeg`; each broker parser fills it. Consumers read the key off the leg and need no side table. Cost: it amends a frozen canonical
model that `broker-abstraction/` declared out of bounds, every existing fixture and constructor stays valid only if the field is optional, and a leg then carries broker-specific identity inside a
"canonical" type.

### Routing granularity (independent of A / B)

- **Per-capability routing:** config such as `ltp=upstox, chain=[upstox, dhan], candles=dhan`, each capability with an explicit fallback chain and a health-aware circuit breaker (Dhan error 806, "Data
  APIs not subscribed", or a stale token degrades that capability to Upstox).
- **Global broker switch:** one `DATA_BROKER=upstox|dhan` setting that selects an entire client.

## Q1 — Option A or Option B for canonical contract identity?

Weigh: blast radius on 27 direct importers and 15 parser callers, risk to frozen models, fixture churn, and how each option behaves when Upstox and Dhan lists disagree about which strikes exist (Dec
2027 lists about 39 strikes on Dhan). Say whether the identity decision changes if a third source is ever added.

## Q2 — Per-capability routing or a global broker switch?

Given the capability asymmetry in Mechanics §3 (order margin and orders are Upstox-only today; far-expiry Greeks are Dhan-only; LTP and candles are available from both), is a global switch ever
correct? If per-capability, what is the minimum config surface and which failure modes (805, 806, stale token, empty chain) must the circuit breaker distinguish? State what must be tested offline.

## Q3 — Greeks provenance for a position held across the Upstox-to-Dhan-to-Upstox transition

The yearly book sees Dhan deltas from the roll to about Sep 2027, then Upstox deltas return. Choose one and give the thresholds it implies: (i) pin the source per position for its whole life (stay on
Dhan to expiry), (ii) switch at a logged seam with a tolerance band on delta stops, or (iii) never compare across sources — gate on a source-independent measure. Say what must be persisted per
snapshot (`source`, model version) and whether `paper_overlay_pnl_snapshots` or any other table needs a column.

## Q4 — Stale or missing Greeks for a 360-DTE leg

The 2026-07-02 ruling accepts the +/-1 per lot approximation with a WARNING in paper. For a delta-0.15 far-dated call that overstates position delta roughly six-fold and could block entries or trip
caps wrongly. For the yearly book, pick the fallback order among: last-known delta from the daily capture store with a maximum age, local Black-Scholes delta from Dhan's IV, the +/-1 approximation, or
fail closed. Give the maximum acceptable age and the point at which the monitor must alert instead of acting.

## Q5 — Sequencing against the Dec 2026 roll

Today is 2026-10-07; the roll is after 2026-12-29. Only the chain capability, the resolver, the token-freshness slice and the monitor path are needed before the roll; the LTP and candle router and the
migration of the 27 direct importers can follow. Is that split sound? Name any piece of the "after the roll" bucket that must move earlier, and any "before the roll" piece that can safely be cut.

---

## Required Council Output Format

```
## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Q1 Contract identity (A / B) | |
| Q2 Routing granularity | |
| Q3 Greeks provenance across the source transition | |
| Q4 Stale or missing Greeks fallback order for the yearly book | |
| Q5 Pre-roll vs post-roll scope | |

## Design Rationale
[Why the recommended options are correct given the specific constraints named above.]

## Data Model / Schema Detail
[Exact new types (ContractRef, ChainSnapshot or the OptionLeg change), config keys, and any persisted column — name the table and field.]

## Historical Data Handling
[Only if existing stored rows are affected — omit this section otherwise.]

## Dissenting Notes
[Panel disagreements, particularly on the Q1 and Q3 splits.]
```
