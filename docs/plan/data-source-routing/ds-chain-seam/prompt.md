# DS Chain Seam — prompt

> A yearly-tenor consumer gets an option chain with working instrument keys from Upstox or Dhan, chosen by config, without any consumer learning which broker answered.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

`ChainSource` returns a canonical `OptionChain` with no `instrument_key`; the overlay bootstraps consume raw Upstox rows that carry it. DA-4 found the swap is not drop-in
(`dhan-far-expiry-chain/dhan-chain-adapter/findings.md` §DA-4). Dhan identifies contracts by segment + security id. The yearly book needs Dhan Greeks for about nine months after the Dec 2026 roll, so
this seam is a standing dependency, not a bootstrap one-off.

## Scope guard

**In bounds:** `src/client/` (capability protocols, resolver, chain sources, routing config), `factory.py` wiring for the chain capability, `src/config.py` routing settings, tests.

**Out of bounds:** LTP / candle routing and migration of the 27 direct `UpstoxMarketClient` importers (`ds-router-migration/`); the overlay bootstraps themselves (`yearly-foundation` YF-6 consumes
this story's output); `OptionLeg` and the Parquet / SQLite schemas, unless the council ruling picks Option B; any order, margin or positions path.

## Design review

Run `docs/refactor/design-principles.md` triggers before DSC-1: ISP (one narrow `Protocol` per capability), DIP (constructor injection; `factory.py` is the only place that names a concrete source),
OCP (routing is a `dict` registry, not an `elif`), SRP (resolver, rate limiter, router separate). Prior-art: extend `ChainSource` / `CompositeChainSource` / `parse_dhan_option_chain`, do not duplicate
them; run the `code-deduplication-and-taxonomy.md` check against `InstrumentLookup` before writing a second contract-lookup helper. Record the outcome here when DSC-1 starts.

## Session-start load hints

`docs/plan/data-source-routing/README.md` and the absorbed ruling in `DECISIONS.md`. `src/client/CLAUDE.md`. `src/client/chain_source.py`, `src/client/dhan_market.py`. `REFERENCES.md`. For any test
helper that builds a domain model, run `get_code_snippet` first (CLAUDE.md Step 4).

## Task overview

DSC-1 canonical types and capability protocols → DSC-2 bidirectional contract resolver (Upstox BOD + Dhan master) → DSC-3 chain sources return `ChainSnapshot` with source tag → DSC-4 chain routing
config and factory wiring.

## Definition of done

From fixtures, offline: a yearly-tenor request for Dec 2027 returns a `ChainSnapshot` with non-zero deltas and a resolvable native key for every selectable leg when Upstox is all-zero; Upstox-only
config reproduces today's behaviour exactly; an unresolved key raises structurally. `python -m pytest tests/unit/ --tb=no -q` green.

## Perspectives not covered

Dhan and Upstox may list different strikes for the same expiry (Dec 2027 lists about 39 strikes on Dhan); the resolver cannot invent a key for a strike one broker does not list. The council ruling
sets how a consumer should react.
