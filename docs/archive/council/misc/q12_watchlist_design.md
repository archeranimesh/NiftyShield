NiftyShield runs a StrategyMonitor daemon (09:15–15:30 IST, Mon–Fri) that ticks every
90 seconds. On each tick it fetches the full NIFTY option chain for one expiry (~80–120
strikes, each with LTP, delta, IV, OI) and passes the entire OptionChain object to every
registered strategy's check_signals(market, positions). Each strategy scans the chain for
its 1–4 open positions and emits SignalEvents.

We are about to implement adjustment signals (ROLL, ROLL_WING, ROLL_OVERLAY) in
CSPNiftyV1, IronCondorV1, and NiftyTrackComparisonV1. Roll target selection requires
scanning the full chain for candidates in a delta band (e.g. 18–28 delta for CSP).

This council question decides the fetch architecture before those stories are coded.

---

## System Context

**Registered strategies:**
- CSPNiftyV1 — 1 short put leg. Signals: profit target (mark ≤ 50% of entry credit),
  loss stop (mark ≥ 2×), delta stop (|Δ| ≥ 0.35), time stop (DTE ≤ 21).
  Roll target: nearest PE strike with |Δ| in 0.18–0.28, ranked by proximity to 0.22.
- IronCondorV1 — 2 short legs (1 CE + 1 PE). Wing-roll when |Δ| ≥ 0.35 on either short.
  Roll target: nearest OTM strike with |Δ| in 0.10–0.20, ranked by proximity to 0.15.
- NiftyTrackComparisonV1 — up to 4 overlay legs (overlay_pp, overlay_cc,
  overlay_collar_put, overlay_collar_call) across 3 tracks. Roll when DTE ≤ 5 or
  premium ≤ 25% of entry. Target: same overlay type on next expiry, |Δ| ~0.20.

**The tension:**
The full chain fetch delivers Greeks (delta, IV) needed for delta-stop signals and roll
target selection. A batch LTP call delivers price only — no delta, no IV — but is faster
and fetches only the keys the strategies actually monitor.

**Current protocol (PaperStrategy):**
```python
async def check_signals(market: OptionChain, positions: list[PaperPosition]) -> list[SignalEvent]
def describe_context(event, market, positions) -> str
async def apply_action(positions, action) -> list[PaperPosition]
```
No watchlist() method exists. Adding one is a breaking protocol change (all registered
strategies must be updated).

**Infrastructure facts:**
- UpstoxMarketClient already has get_ltp_batch(instrument_keys) used by DhanTracker.
  Adding it to BrokerClient protocol is possible but is itself a protocol change.
- UpstoxMarketClient.get_option_chain() returns the full chain for one expiry.
  There is no "partial chain" endpoint.
- Upstox Analytics Token has generous rate limits — API cost is not a hard constraint
  at current paper trading scale.
- Phase 0 paper trading: at most 3 strategies, 6 open legs simultaneously.
  Live execution (Phase 1+) may run 10+ strategies with 20+ open legs.

---

## Q1 — Full chain fetch vs. watchlist-based batch LTP

**Option A — Keep full chain fetch (current):**
Every tick fetches the complete chain for one expiry. All Greeks available on every tick.
Roll target selection always available. No protocol change. Simple.
Cost: ~100+ unused strikes parsed and discarded each tick.

**Option B — watchlist() method + batch LTP:**
Add watchlist() to PaperStrategy protocol. Each strategy returns only the instrument keys
it needs (current legs + a small candidate band). StrategyMonitor aggregates, deduplicates,
and calls get_ltp_batch(). Price signals (profit target, loss stop, decay) run every 90s.
Greeks and roll selection only on a separate Greeks tick.
Cost: protocol change + two-tier tick complexity.

**Option C — Hybrid (price tick + event-triggered chain fetch):**
Watchlist-based LTP every 90s for price signals. When a price signal fires that requires
Greeks (delta stop, roll target), immediately trigger a full chain fetch for that expiry only.
No periodic Greeks tick — Greeks fetched on demand only.

a) At paper trading scale (3 strategies, 6 legs), is Option A wasteful enough to warrant
   the complexity of B or C? Or is the full chain fetch acceptable until Phase 1?
b) If B or C is recommended, what is the right trigger for the Greeks fetch — periodic
   (every N min), event-driven (only when a price signal fires), or hybrid?

---

## Q2 — Roll target selection and Greeks availability

Roll target selection scans all strikes in a delta band from the full chain. Under a
watchlist design, the chain is not always available.

**Option X — Deferred roll (two-stage signal):**
On a price tick, a qualifying position emits ROLL as WARN (no target yet). On the next
Greeks tick, WARN upgrades to ACTION with a suggested target in the payload.
Pro: avoids forcing a chain fetch on every tick. Con: 5–10 min lag between signal and action.

**Option Y — Immediate roll fetch:**
When a roll-qualifying signal fires on a price tick, force an immediate chain fetch for
that expiry. ROLL emits as ACTION immediately with a suggested target.
Pro: no lag. Con: unpredictable latency spikes on the 90s tick loop.

**Option Z — Roll selection stays in executor (lazy):**
ROLL signal carries no suggested target. PaperExecutor fetches the chain at approval time
(after Telegram approval arrives) to select the target. No chain fetch in check_signals at all.
Pro: cleanest separation — strategy signals intent, executor resolves the target.
Con: target selected after approval, not before — council prompt cannot include strike details.

a) Which option best fits a human-in-the-loop approval flow where the council prompt
   should ideally include the suggested strike?
b) Is Option Z architecturally cleaner despite the council prompt limitation?

---

## Q3 — Protocol versioning: backward compatible or mandatory

If watchlist() is added to PaperStrategy:

**Backward compatible:** watchlist() has a default implementation returning [] — strategies
that don't implement it fall back to full chain fetch. StrategyMonitor checks: if
watchlist() returns empty, fetch full chain; otherwise batch LTP.

**Mandatory:** All strategies must implement watchlist(). @runtime_checkable Protocol
would fail isinstance() checks on old strategies until updated.

a) For a small codebase with 3 strategy implementations, is mandatory cleaner than the
   conditional logic of backward-compatible?
b) Should watchlist() be added now (before PA1.1–PA1.3) or deferred to Phase 1 when
   scale justifies it?

---

## Q4 — Phase gate: now or Phase 1

Is the watchlist optimization a Phase 0 concern (implement before adjustment stories) or
a Phase 1 concern (defer until scale justifies it)?

Factors favouring now: cleaner to add protocol method before 3 strategies are written;
retrofitting after PA1.1–PA1.3 requires touching all 3 strategies again.

Factors favouring Phase 1: paper scale is trivially small; full chain fetch works; adding
complexity before the adjustment flow is validated adds risk; the analytics token is not
rate-limited at current scale.

---

## Required Council Output Format

| Decision | Current | Council recommendation |
|---|---|---|
| Fetch architecture for StrategyMonitor | Full chain every 90s | Keep / Option B / Option C |
| Greeks tick trigger (if split-fetch) | N/A | Periodic / Event-driven / Hybrid |
| Roll target selection timing | N/A | Option X (deferred) / Y (immediate) / Z (executor) |
| watchlist() versioning | N/A | Backward compatible / Mandatory |
| Phase gate | Now (before PA stories) / Phase 1 | ? |

Dissenting Notes must capture panel disagreement on Q2 (roll target timing) — this has
the highest architectural impact if Option Z (executor-based) is chosen, as it changes
the executor's responsibilities.
