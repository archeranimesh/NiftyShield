# DS Router Migration — prompt

> Every direct `UpstoxMarketClient` importer sits behind the capability router (or is a recorded exception), and a lapsed Dhan subscription degrades to Upstox without a crash.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

27 modules outside `src/client/` import the legacy `UpstoxMarketClient` (against `src/client/CLAUDE.md`), 15 call `parse_upstox_option_chain`, and routing LTP, candles and chains by config needs
consumers to stop naming a broker. None of it is needed for the yearly book (Upstox LTP works for far expiries; only the Greeks are zero), so it is deliberately after the Dec 2026 roll.

## Scope guard

**In bounds:** quote and candle sources, the router for those capabilities, migration of direct importers one cluster per task, subscription-health fallback (806) generalised beyond the chain.

**Out of bounds:** orders, order margin and positions (unless DSM-1 verified a Dhan margin endpoint and Animesh opens a separate story); a Dhan `MarketStream` implementation; Kite; schema changes; the
persisted Upstox keys (never migrated).

## Design review

Run the triggers in `docs/refactor/design-principles.md` before DSR-2, and the `code-deduplication-and-taxonomy.md` audit in DSR-1 against the 27 + 15 sites before any migration. Router stays a `dict`
registry over `Protocol`-typed sources; migrate by constructor injection, one cluster per commit.

## Session-start load hints

`docs/plan/data-source-routing/README.md`, `DECISIONS.md` (ruling), `ds-chain-seam/` outputs, `src/client/CLAUDE.md`, `docs/refactor/code-deduplication-and-taxonomy.md`.

## Task overview

DSR-1 prior-art audit and cluster plan → DSR-2 quote / candle sources + router → DSR-3..n one migration task per cluster (enumerated by DSR-1) → DSR-last subscription-health fallback.

## Definition of done

`audit.md` lists every direct importer with its disposition; each cluster is migrated or a recorded exception; a grep for `from src.client.upstox_market import` outside `src/client/` returns only the
recorded exceptions; 806 fallback tested offline; `python -m pytest tests/unit/ --tb=no -q` green.

## Perspectives not covered

Behavioural drift between Upstox and Dhan LTP (timing, last-trade vs best-quote) is not analysed; consumers that compare LTPs across sources are flagged by DSR-1 but not fixed here.
