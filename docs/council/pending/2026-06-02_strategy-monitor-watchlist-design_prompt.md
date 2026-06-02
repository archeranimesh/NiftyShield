# Council Question: StrategyMonitor watchlist vs. full-chain fetch design

**Topic:** strategy-monitor-watchlist-design
**Template:** data_architecture
**Context files:** src/strategy/protocol.py, src/strategy/monitor.py, src/strategy/csp_nifty_v1.py

---

## Background

NiftyShield runs a `StrategyMonitor` daemon (09:15–15:30 IST, Mon–Fri) that ticks every
90 seconds. On each tick it:

1. Fetches the full NIFTY option chain for one expiry via `UpstoxMarketClient.get_option_chain()`
   (returns ~80–120 strikes with LTP, delta, IV, OI per strike)
2. Passes the entire `OptionChain` object to each registered strategy's `check_signals(market, positions)`
3. Each strategy scans the chain for its open positions and emits `SignalEvent` objects

Current strategies registered:
- `CSPNiftyV1` — monitors 1 short put leg (price, delta, DTE signals)
- `IronCondorV1` — monitors 2 short legs (1 CE + 1 PE)
- `NiftyTrackComparisonV1` — monitors up to 4 overlay legs across 3 tracks

In the adjustment phase (paper-backbone-adj stories PA1.1–PA1.3), strategies will also
perform **strike selection** on the chain to suggest a roll target. This selection scans
all strikes in the delta target band (e.g. 18–28 delta for CSP) and ranks by proximity.

## The Problem

Fetching the full chain every 90 seconds is wasteful when a strategy only needs to monitor
1–4 specific instrument keys. At most 4–6 strikes are relevant at any tick; the other
100+ strikes are fetched, parsed, and discarded.

A `watchlist()` method on the `PaperStrategy` protocol would let each strategy declare
exactly which instrument keys it needs to monitor. `StrategyMonitor` could aggregate across
all strategies, deduplicate, and fetch only those keys via a batch LTP call.

## The Tension

The full chain fetch is expensive in data volume but **delivers Greeks (delta, IV)**,
which are required for:
- Delta stop signals (`|Δ| ≥ 0.35`)
- Roll target selection (scan for 22-delta replacement strike)
- `describe_context()` council prompt enrichment

A batch LTP call is fast and cheap but **delivers price only** — no delta, no IV.

This creates a possible split-fetch design:
- **Price tick** (every 90s): batch LTP on watchlist — profit target, loss stop, decay checks
- **Greeks tick** (every N min, or triggered when a price signal fires): full chain fetch for the relevant expiry — delta stop, roll target selection

## Specific Questions for the Council

1. **Should `PaperStrategy` grow a `watchlist()` method**, or is the full chain fetch
   acceptable for the paper trading scale (1–3 strategies, 1–4 open positions at a time)?
   Adding `watchlist()` is a breaking protocol change that touches every registered strategy.

2. **If a split-fetch design is adopted**, what is the right trigger for the Greeks tick?
   - Fixed interval (e.g. every 5 min regardless)?
   - Event-driven (only when a price signal fires)?
   - Hybrid (fixed 5-min baseline + immediate Greeks fetch when price signal fires)?

3. **Strike selection for roll targets** requires scanning the full chain for candidates
   in a delta band. If the Greeks tick is not always running, roll target selection is
   unavailable during price-only ticks. Should roll target selection be:
   - Deferred until the next Greeks tick (signal fires as WARN first, upgrades to ACTION
     on next Greeks tick if a target is found)?
   - Always triggered immediately (force a Greeks fetch when a roll-qualifying signal fires)?

4. **Protocol versioning**: if `watchlist()` is added, should existing strategies that
   don't implement it default to full chain fetch (backward compatible), or should
   `watchlist()` be mandatory (forces all strategies to declare their surface)?

## Current Architecture Facts

- `UpstoxMarketClient.get_option_chain()` returns the full chain for one expiry.
  There is no batch-LTP-by-instrument-key method on the current `BrokerClient` protocol,
  but `UpstoxMarketClient` already has `get_ltp_batch(instrument_keys)` used by `DhanTracker`.
- `BrokerClient` protocol would need `get_ltp_batch` added if the watchlist path is chosen.
- `PaperStrategy` protocol is `@runtime_checkable` — adding `watchlist()` with a default
  implementation (return empty list → fall back to full chain) is backward compatible.
- Paper trading scale: at most 3 strategies, 6 open legs simultaneously. This is Phase 0
  paper only — live execution is Phase 1+.
- Upstox Analytics Token: the chain fetch is covered by the long-lived analytics token
  with generous rate limits. Cost is not a hard constraint at current scale.

## What a Decision Here Unlocks

This decision gates the final design of `StrategyMonitor` before the adjustment stories
(PA1.1–PA1.3) are implemented. If `watchlist()` is added, the stories need updating.
If full-chain is kept, the stories proceed as written.
