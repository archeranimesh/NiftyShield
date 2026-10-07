# DS Chain Monitoring — prompt

> The yearly book reads delta every day from the routed chain with a persisted source tag, and a stale Dhan token or a lapsed plan produces an alert and a decided fallback, never silence.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

After 2026-12-29 the yearly book holds Dec 2027 legs and Upstox returns zero Greeks until about Sep 2027, so the book's delta stop, `PortfolioDelta`, EOD snapshot and entry gates all depend on Dhan
for about nine months. Dhan's token is a manual 24 h token (`DECISIONS.md` Dhan Integration), so a missed refresh on a weekday blinds the book. The 2026-07-02 council ruling accepts a +/-1 per lot
approximation with a WARNING in paper, which overstates a delta-0.15 far-dated leg roughly six-fold (council Q4). The same token gate protects the `far-expiry-capture` cron.

## Scope guard

**In bounds:** Dhan token freshness check / renewal (as DSM-1 allows) and its healthcheck, the monitor and snapshot read path for yearly-tenor legs, per-snapshot `source` persistence, the stale-Greeks
and source-flip policies as the council rules, the monitor-cadence field on `OverlayTenorPolicy`.

**Out of bounds:** the overlay bootstraps (`yearly-foundation` YF-6), LTP / candle routing (`ds-router-migration/`), streaming (`MarketStream` stays unimplemented), any order path, changes to monthly
monitor cadence or behaviour.

## Design review

Run `docs/refactor/design-principles.md` triggers before DSN-2: the monitor depends on a `ChainSource` injected through the router, not on Dhan; staleness and source-flip are strategy-policy objects
(a registry `dict` in `OverlayTenorPolicy`), not branches in the monitor; `src/risk/` stays pure and receives a resolved `position_deltas` map (2026-07-02 ruling). Record the outcome here.

## Session-start load hints

`docs/plan/data-source-routing/README.md`, the absorbed ruling in `DECISIONS.md`, `docs/council/2026-07-02_paper-delta-source-architecture.md`, `src/strategy/CLAUDE.md`, `src/paper/CLAUDE.md`,
`DB_REGISTRY.md` (before any column), `LOGGING.md`, `docs/plan/yearly-overlays/yearly-foundation/` (YF-3 registry).

## Task overview

DSN-1 token freshness and healthcheck → DSN-2 chain-in-monitor / snapshot path with source tag → DSN-3 stale-Greeks and source-flip policy → DSN-4 yearly cadence in `OverlayTenorPolicy`.

## Definition of done

Offline tests show: a stale token and an 806 each raise an alert and take the ruled fallback; the yearly monitor reads delta from the routed chain at the policy cadence; every persisted snapshot for a
held yearly position carries its source; the monthly path is unchanged. `python -m pytest tests/unit/ --tb=no -q` green; `greeks-analyst` clean on every task touching delta fields.

## Perspectives not covered

Margin impact of holding a far-dated short call is not modelled here (also not covered in `yearly-overlays/`). Intraday gap risk between daily chain reads on a 360-DTE leg is accepted by the cadence
choice, not analysed.
