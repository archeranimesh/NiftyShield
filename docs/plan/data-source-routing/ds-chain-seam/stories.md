# DS Chain Seam — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

> **Specced after council.** The shapes below are the working default (Option A, per-capability routing). `ds-capability-map/` DSM-3 replaces this stub with full per-task specs from the council
> Summary Table. A task is not startable while this banner is present.

---

## DSC-1 — Canonical types and capability protocols (working outline)

- `src/client/capabilities.py` (new) — `Protocol`s: `QuoteSource`, `ChainSource` (moved or re-exported from `chain_source.py`), `CandleSource`, `ContractMaster`; `MarketStream` stays as in
  `protocol.py`.
- `src/models/` or `src/client/` — `ContractRef(underlying, expiry, strike, side)` frozen; `ChainSnapshot(chain, source, keys)` frozen. Final home and shape per the ruling (Option A vs B).
- Tests: equality / hash of `ContractRef`; `ChainSnapshot` immutability; protocols satisfied structurally by the existing sources.

## DSC-2 — Contract resolver (working outline)

- Pure functions over each broker's instrument master: Upstox BOD (reuse `InstrumentLookup`, do not fork it) and the Dhan CSV master. Both directions.
- Tests: round trip per broker from fixtures; strike one broker does not list raises a typed error (extend `src/client/exceptions.py`).

## DSC-3 — Chain sources return `ChainSnapshot` (working outline)

- Extend `UpstoxChainSource`, `DhanChainSource`, `CompositeChainSource` in `src/client/chain_source.py`; the composite sets `source` on the snapshot. Zero-Greek detection stays
  `_is_chain_empty_or_zero_delta`.
- `greeks-analyst` review is mandatory (delta fields touched).

## DSC-4 — Routing config and wiring (working outline)

- `src/config.py` — chain routing setting (capability → ordered sources). `factory.py` builds the router; it stays the only module naming concrete sources.
- Regression test pins that default config reproduces today's Upstox-only behaviour.
