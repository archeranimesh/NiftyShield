# DS Chain Monitoring — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

> **Specced after council.** Outlines only. `ds-capability-map/` DSM-3 replaces this stub with full per-task specs from the council Summary Table (Q3 provenance, Q4 fallback order, Q5 scope). A task
> is not startable while this banner is present. If the ruling adds a persisted column, add `schema.md` and check `DB_REGISTRY.md` before DSN-2.

---

## DSN-1 — Dhan token freshness (working outline)

- Depends on DSM-1 question 1. If renewal is possible: a renewal job with its own alert on failure (a missed day must not silently chain-break). If not: an alert when the token age approaches expiry
  and a healthcheck line.
- Tests: expired-token and 806 fixtures raise the alert; token value never appears in a log line.

## DSN-2 — Chain-in-monitor and snapshot path (working outline)

- Yearly-tenor monitor / snapshot code reads delta through the injected chain source; the resolved `position_deltas` map goes to `PortfolioDeltaTracker` unchanged (2026-07-02 ruling).
- Persist `source` per snapshot; exact table and column per the ruling and `DB_REGISTRY.md`.

## DSN-3 — Stale-Greeks and source-flip policy (working outline)

- Fallback order and maximum age per council Q4 (candidates: last-known capture-store delta, local Black-Scholes from Dhan IV, +/-1 approximation, fail closed). Source-flip handling per Q3.
- Policies live in the `OverlayTenorPolicy` registry, not in the monitor.

## DSN-4 — Monitor cadence (working outline)

- Add a cadence field to the YF-3 registry; yearly set by DSM-1 / council evidence, monthly pinned to today's value. One Dhan chain call per cycle, at least 4 s after the previous call.
