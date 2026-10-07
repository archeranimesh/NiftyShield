# Data Source Routing (capability-based broker routing) — epic index

> Gives every market-data consumer one broker-neutral way to ask for a quote, a chain, candles or a contract, and routes each capability to Upstox or Dhan by config with health-aware fallback. One
> epic because the chain seam, the Dhan token / monitoring work and the later consumer migration all hang on the same contract-identity decision, which is council-gated.

## Why this epic exists

Three plans each solve a slice of the same missing seam and none names it:

- `broker-abstraction/` designed it top-down (16 tasks, LOW priority, written before Dhan was bought, six tasks spent on Kite).
- `dhan-far-expiry-chain/` built part of it bottom-up. `DhanMarketClient`, `parse_dhan_option_chain` and `CompositeChainSource` shipped under DA-2 / DA-3. That already covers most of BA-3 and part of
  BA-5.
- `yearly-overlays/` is the first real consumer and exposed the flaw: `BrokerClient.get_option_chain` returns raw Upstox rows, `ChainSource` returns a canonical `OptionChain` that carries no
  `instrument_key`, and the overlay bootstraps need the key (DA-4 relocation, `dhan-far-expiry-chain/dhan-chain-adapter/findings.md` §DA-4).

The yearly book makes this standing, not one-off. After Dec 2026 expires (2026-12-29) it holds Dec 2027 legs (about 360 DTE). Upstox returns zero Greeks past about 90 DTE (DDP-5, one expiry), so for
about nine months every delta the book reads comes from Dhan. Upstox's `instrument_key` is the de facto canonical identity in 27 modules that import `UpstoxMarketClient` directly, 15 that call
`parse_upstox_option_chain`, 50 that touch `InstrumentLookup`, and the persisted ledgers.

## Scope decisions

Decided with Animesh, 2026-10-07:

- **One new epic for the seam only.** `yearly-overlays/` and `dhan-far-expiry-chain/` stay separate epics (they have their own deliverables and the capture has its own deadline); the edges between the
  three are recorded in each README's Depends-on column and Supersession section, not by nesting.
- **`broker-abstraction/` is folded into this epic**, not run as written. See Supersession.
- **Routing is split at the Dec 2026 roll** (council-confirmed). Before it: contract resolver and `ChainSnapshot`, per-expiry fallback with the 805 / 806 / empty-chain taxonomy, provenance tags, a
  Dhan token-staleness **alert** (not renewal), a cross-process Dhan throttle, the Upstox BOD coverage check, and the yearly bootstrap wiring (YF-6). After it: LTP / candle routing, migration of the
  27 direct importers, `MarketStream`, programmatic token renewal, Kite, local Black '76, BA-14 / BA-15.
- **Council ruled 2026-10-07** (`DECISIONS.md`, "Data source routing …"): Option A side-table resolver, per-capability routing, Greeks source switch at a logged seam, no +/-1 approximation in yearly
  gates. Animesh's Q4 clarification is recorded there: stale-Greeks handling splits by action class, with a delta-independent backstop alert and a freshness bound tied to the monitor cadence.

## Verified facts that shape the design

From the archived Dhan POC (`docs/archive/plan/dhan-data-poc/findings.md`, 2026-10-05) and repo recon (2026-10-07):

- `BrokerClient.get_option_chain` returns `list[dict[str, Any]]` (`src/client/protocol.py:152`). `OptionLeg` has no `instrument_key` (`src/models/options.py`).
- `CompositeChainSource` (`src/client/chain_source.py:50`) falls back to Dhan only when every Upstox delta is zero. `chain_source.py` imports the legacy `UpstoxMarketClient`.
- Dhan live chain: one unique request per 3 s (use 4 s); error 805 on too-fast, 806 on "Data APIs not subscribed". Expired options: ATM +/- 10, IV only, no delta / bid / ask.
- `factory.create_client(env)` selects by environment (`prod` / `sandbox` / `test`), not by capability.
- The Dhan access token is a manual 24 h token (`DECISIONS.md` Dhan Integration). Programmatic renewal is **unresolved** and post-roll (`ds-router-migration/` DSR-0 / DSR-4); pre-roll is an alert only
  (`ds-chain-monitoring/` DSN-1).
- **Secondhand, unverified** (summaries pasted by Animesh on 2026-10-07, the pages themselves were unreachable from the session): the live market feed has ticker / quote / full modes, OI and 5-level
  depth, **no Greeks**, 5 connections x 5,000 instruments, 100 per subscribe message, 10 s ping with a 40 s pong timeout, token passed in the connect query string. The Dhan MCP server
  (`mcp.dhan.co/mcp`) is an interactive connector exposing orders as well as data. The Agent Skills pack is developer tooling. DSR-0 must confirm each against the primary page before it is relied on.
- Adjacent ruling: `docs/council/2026-07-02_paper-delta-source-architecture.md` (active, not yet absorbed) — callers resolve a `position_deltas` map keyed by `instrument_key`; `src/risk/` stays pure.

## Architecture and design review

SOLID triggers run against the plan (`docs/refactor/design-principles.md`):

- **ISP:** four narrow capability `Protocol`s — quote, chain, candles, contract master — plus `MarketStream` as a protocol only. Consumers depend on the one they use, never on a broker.
- **DIP:** consumers receive sources by constructor injection; `factory.py` stays the only composition root and gains capability-based construction.
- **OCP:** routing is a config-driven `dict` registry (capability → ordered list of sources). A third source is a new entry, not a new `elif`.
- **SRP:** the contract resolver, the rate limiter, the health / circuit-breaker state and the router are separate collaborators.
- **Prior-art audit:** `ds-router-migration/` DSR-1 runs the `code-deduplication-and-taxonomy.md` check across the 27 importers and 15 parser callers before any migration code. The existing
  `CompositeChainSource` and `parse_dhan_option_chain` are extended, not replaced.
- Frozen-model guard: `OptionLeg`, `OptionChain` and the Parquet schemas stay unchanged (council chose Option A). The only persisted change is four additive `TEXT NULL` provenance columns on
  `paper_leg_snapshots` and `paper_overlay_pnl_snapshots` (`ds-chain-monitoring/schema.md`); `yearly-overlays/` YF-1's "no schema change" expectation does not account for them.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `ds-capability-map/` | Council run and absorb (done), roll-critical checks (BOD Dec 2027 coverage, Dhan failure shapes) | 🔄 In progress — next DSM-1 | — | — |
| `ds-chain-seam/` | `ContractRef` / `ChainSnapshot`, resolver, per-expiry fallback and health, chain routing config, shared Dhan throttle | ⬜ Not started | `ds-capability-map` | — |
| `ds-chain-monitoring/` | Token alert, yearly read path with provenance, stale-Greeks policy, cadence, source flip | ⬜ Not started | `ds-chain-seam`; `yearly-foundation` YF-3 | — |
| `ds-router-migration/` | Capability matrix, quote / candle router, importer migration, token renewal, generalised health | ⬜ Not started | `ds-chain-monitoring` (and Dec 2026 roll done) | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view — per-task checkboxes live only in each sub-story's `tasks.md`.

## Open decisions for Animesh

Resolved by the council on 2026-10-07: contract identity (Option A) and token renewal (alert pre-roll, renewal post-roll).

1. **Kite / Zerodha.** The council deferred it post-roll; BA-6..BA-9 stay deferred (no credentials, no consumer). Confirm or restore.
2. **Dhan yearly plan.** Rs 4,788 / year against Rs 5,988 monthly. Tracked as DA-0 in `dhan-far-expiry-chain/`; the design holds if the plan lapses (806 degrades to Upstox).
3. **Yearly monitor cadence.** Proposal: 300 s or slower (the council's 60 s is "initial"). Set in DSN-4.
4. **Backstop thresholds.** Premium multiple or spot distance to strike for the delta-independent alert (DSN-3); depends on the yearly tenor policy values (`yearly-overlays/README.md` open decision
   1).
5. **Schema acceptance.** Four additive `TEXT NULL` columns (`ds-chain-monitoring/schema.md`). `yearly-overlays/` YF-1 must not conclude "no schema change".
6. **Dec 2027 not in the Upstox BOD.** If DSM-1 finds it absent, the council requires a separate architectural decision before the roll; do not fall back to serialised `ContractRef` identity.

## Cross-cutting constraints

- `monthly` and Upstox-only behaviour stay byte-identical: a regression test pins current routing before any consumer moves.
- No network, real token or real DB in the default `pytest` run; Dhan live checks are marker-gated.
- Every persisted leg snapshot for a held position carries `delta_source` and `delta_asof`, and every overlay snapshot `chain_source` and `chain_fetched_at`; old rows stay `NULL` (unknown, never
  inferred).
- New yearly code adds no direct `UpstoxMarketClient` chain import while the migration waits.
- Chain calls to Dhan stay at least 4 s apart; 805 backs off and is logged, 806 marks the capability unhealthy and falls back, neither retries in a tight loop.
- No credentials, tokens or client ids in docs, fixtures, logs or `council/question.md`.
- New package directories carry `__init__.py` and trigger a graph re-index. Changes to option-chain parsing or delta / gamma fields trigger `greeks-analyst`; any roll-path change triggers
  `roll-validator`.
- Order execution and portfolio reads stay blocked; Dhan stays read-only. The Dhan MCP connector and Agent Skills pack are not runtime dependencies of this epic.

## Supersession / coordination

- **`broker-abstraction/`** (2026-10-07): BA-3 and BA-5 superseded by DA-2 / DA-3 (shipped, `7abac89`); BA-0 is satisfied for Dhan by the archived POC, with the roll-critical remainder in
  `ds-capability-map/` DSM-1 and the broader matrix in `ds-router-migration/` DSR-0; BA-6..BA-9 (Kite) deferred; BA-1 / BA-2 / BA-11 / BA-12 / BA-13 are re-homed as `ds-chain-seam/` and
  `ds-router-migration/` tasks. BA-14 / BA-15 (auth abstraction) stay gated on `src/execution/` existing. The folder stays in place with a banner until its tasks are all closed or re-homed.
- **`yearly-overlays/`**: `yearly-foundation` YF-6 depends on `ds-chain-seam` (resolver and `ChainSnapshot`). `yearly-validation` YV-5 (roll gate) additionally requires `ds-chain-monitoring` (token
  freshness, chain-in-monitor path, stale-Greeks policy). `OverlayTenorPolicy` (YF-3) gains a monitor-cadence field, added by `ds-chain-monitoring` DSN-4.
- **`dhan-far-expiry-chain/`**: DA-4 stays relocated. `far-expiry-capture/` keeps calling `DhanMarketClient` directly (it must not wait on this epic); its store is the candidate last-known-delta cache
  for the stale-Greeks policy (council Q4). Dhan token freshness (`DSN-1`) is a precondition for the capture cron staying healthy.
- **`docs/council/2026-07-02_paper-delta-source-architecture.md`**: extended for far-dated legs by council Q4, not reopened.

## Epic done when

- **ds-capability-map** — the council ruling is absorbed into `DECISIONS.md` (done); `roll_checks.md` records the Upstox BOD Dec 2027 coverage and the Dhan 806 / stale-token shapes, each verified or
  marked unverified with an owner.
- **ds-chain-seam** — a yearly-tenor consumer gets a `ChainSnapshot` with Upstox ledger keys from Upstox or Dhan by config alone, offline from fixtures; a missing key aborts the ledger write, not the
  chain read; Dhan calls share one throttle across processes.
- **ds-chain-monitoring** — the yearly book's monitor and snapshot paths read delta from the routed chain with persisted provenance; a stale Dhan token or an 806 alerts; delta-dependent actions fail
  closed and delta-independent automation continues; the source-flip seam is logged and tolerance-banded.
- **ds-router-migration** — every direct `UpstoxMarketClient` importer is behind the router or recorded as a deliberate exception; subscription-lapse fallback tested for every capability; the legacy
  client has no new dependents.
