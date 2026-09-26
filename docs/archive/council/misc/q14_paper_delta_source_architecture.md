# Paper Delta Source Architecture (BUG-002 remediation, B002.4)

## System Context

`PortfolioDeltaTracker.aggregate_delta` (`src/risk/delta_tracker.py`, 24 call sites)
computes the delta-neutral gate that blocks/allows new IC entries and drives the
±0.05..0.25 lot risk cap. It is currently pure, synchronous, and has zero I/O or
filesystem dependency — tests construct `PaperPosition` dataclasses directly with no
mocking required.

**Confirmed bug (BUG-002, CRITICAL):** `_position_delta` classifies put/call by
substring-matching `"PE"`/`"CE"` against `instrument_key`. Real Upstox keys are pure
numeric (`NSE_FO|63916`), so that match is dead code — every option position falls
into the `else` branch and is priced as a naked future (`net_qty / lot_size`, full
±1.0 delta per lot regardless of strike/moneyness). A short 1-lot put with real delta
≈ +0.25–0.35 lots was returning -1.0 lot — wrong sign, 3-4x wrong magnitude. This fed
a real `ic_weekly.log` rejection: `Projected=6.901 lots (outside [-0.05, 0.25])`.

**Already fixed (B002.3, committed 96398b4):** `PaperPosition` now carries
`option_type: Literal["PE", "CE", "FUT", "EQ"] | None`, resolved lazily and read-time
in `PaperStore.get_position`/`get_positions` via `InstrumentLookup.get_by_key`
(offline BOD JSON lookup — no chain/network dependency). This fixes sign
classification but not magnitude: the code still uses ±1.0 lot per position instead
of the real option delta.

**What remains (B002.4 — this question):** replace the ±1.0 approximation with the
actual option delta sourced from a chain snapshot (live fetch, or `GammaStore`/
`ChainReader` recent persisted snapshot — both exist in the codebase already for
other purposes: `src/gamma/store.py::GammaStore`, `src/backtest/chain_reader.py`
persists/reads EOD and intraday chain snapshots with per-strike delta).

## Two candidate architectures

**(a) Chain dependency lives inside `src/risk/delta_tracker.py`.**
`PortfolioDeltaTracker` or `_position_delta` is given a `ChainReader`/`GammaStore`/
live `BrokerClient.get_option_chain` dependency and resolves Greeks per position at
aggregation time. Callers' signatures barely change (`aggregate_delta(positions,
nifty_spot, lot_size)` stays close to today's shape). Cost: the module goes from
zero-I/O pure-data to depending on chain freshness, and per root `CLAUDE.md`'s async
rule ("never mix asyncio with blocking calls in the hot path" — chain fetch may be
async, `aggregate_delta` callers are currently sync), a new failure mode (stale/
missing/partial chain) now lives inside the risk-gate module itself. Every existing
test in `tests/unit/risk/test_delta_tracker.py` (currently pure dataclass
construction) would need chain mocking.

**(b) Caller resolves a delta map; `src/risk/delta_tracker.py` stays pure.**
`aggregate_delta` gains a `position_deltas: dict[str, Decimal] | None = None` (keyed
by `instrument_key`) parameter. The caller — `scripts/strategies/ic/paper_ic_entry.py`
or `ic_entry_gates.py`, which already fetches the option chain for entry-gating
purposes elsewhere in the same script — resolves per-position deltas from whatever
chain data it already has in hand and passes the map in. `src/risk/` remains
zero-I/O and its existing tests are untouched in shape. Unresolved instrument_keys
(not present in the map) fall back to *some* behavior — see Q2.

## Q1 — Module boundary

Given the existing invariant that `src/risk/` is pure/sync/zero-I/O (deliberately
preserved through B002.3 specifically to avoid adding an `InstrumentLookup`/
filesystem dependency to delta tests — see B002.3 implementation notes), and the
project's stated async-boundary discipline (asyncio + aiohttp for I/O, never mixed
with blocking calls in the hot path, CPU-bound work dispatched to
`ProcessPoolExecutor`), is (a) or (b) the correct module boundary? Is there a third
option — e.g. delta resolved once at the `PaperPosition` construction layer in
`PaperStore` (parallel to how `option_type` was added in B002.3) rather than at
either the risk-gate or the entry-script layer?

## Q2 — Fallback contract when chain data is missing or stale

This is the load-bearing question. Regardless of (a)/(b)/(c), what happens when:

1. The chain snapshot exists but doesn't cover a given `instrument_key` (leg not
   found in the fetched strikes).
2. The chain snapshot is stale (analogous to the sibling BUG-004: a snapshot can be
   present but N trading days old with no recency check).
3. The chain fetch itself fails (network/API error) at gate-check time.

Candidate fallback policies:
- **Fail closed:** treat any unresolved position's delta as unknown → block entry /
  treat as a cap breach (safest for capital, but could false-positive-block on a
  transient chain hiccup).
- **Fail open to the old approximation:** unresolved positions fall back to the
  current `net_qty / lot_size` ±1.0 approximation, but **must** log a WARNING (never
  silent — silent fallback to the exact approximation this bug is fixing would
  reintroduce BUG-002's failure mode under a different trigger).
- **Fail open to zero:** unresolved positions contribute 0 delta (conservative in one
  direction, dangerous in the other — could mask a real short-put delta entirely).

This is a live-money delta-neutral risk gate (BUG-002 severity CRITICAL) — the
fallback choice has direct capital-at-risk consequences, not just a code-cleanliness
tradeoff. Recommend a specific policy per failure mode (1)/(2)/(3) above, not a single
blanket answer, and justify each against the existing multi-strategy risk allocation
decision (`docs/council/archive/risk/2026-05-02_multi-strategy-portfolio-risk-allocation.md`
— delta caps +1.0/+2.0 lots, ₹3-4L stress loss, ₹6L drawdown kill).

## Q3 — Test boundary implications

`tests/unit/risk/test_delta_tracker.py` currently requires no I/O mocking (per
project-wide "No network in tests" mandate, and `src/risk/` specifically has none
today). For whichever architecture is recommended, what does the test surface look
like — does `test_delta_tracker.py` need a `MockBrokerClient`/fake `ChainReader`
injected, or can it stay at pure dict/dataclass fixtures with the chain-resolution
logic tested separately (e.g. in the caller script's own test file)?

## Required Council Output Format

```
## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Module boundary (a / b / c) | |
| Where does the chain dependency live | |
| aggregate_delta signature change | |
| Fallback: instrument_key not in chain | |
| Fallback: stale chain snapshot | |
| Fallback: chain fetch failure | |
| Test boundary impact | |

## Architecture Rationale
[Why the recommended module boundary is correct given the existing zero-I/O invariant
and async-boundary discipline]

## Fallback Policy Detail
[Explicit policy per failure mode 1/2/3 from Q2, with justification tied to the
existing risk allocation caps]

## Dissenting Notes
[Panel disagreements, particularly on whether fail-closed is too aggressive for a
paper-trading system vs a live-money system]
```
