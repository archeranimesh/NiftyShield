# Phase 2 — Research Pipelines & Integrations — prompt

> Bundles the standalone Phase-2 items (P&L visualization, Zerodha/Kite, order execution, paper-snapshot Telegram wiring) that don't already have their own story dir.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked box that is not gated, and do **only** that task. Do not batch or combine tasks. One
task per session. Complete it fully. Stop.

**Gate check first:** PV-1 is the only ungated item — it can be picked up any time. ZK-1/OE-1/ PT-1 are each gated for their own stated reason (see `stories.md`), not on Phase 1.12 itself. Confirm the
specific gate for the task about to be picked up has actually cleared before starting — do not assume Phase 1.12 passing unblocks all four.

Read that task's full spec in `stories.md` (same task id) before writing any code.

## Why this story exists

Phase 2 items are research pipelines and integrations that extend beyond the core Phase 0/1 backtest and paper-trading buildout, but don't warrant their own story directory individually — each is
small, independent, and either gated or deferred for its own stated reason. Bundling them here avoids four near-empty story folders while keeping each item's gate/defer condition explicit and
re-checkable per session.

## Scope guard

This story does not touch the Swing/Investment signal pipelines — those are tracked separately under `docs/plan/signals-eval-core/tasks.md` (SE1–SE8). It changes `src/` behaviour: PV-1 reads existing
store/tracker code (no new `src/` module beyond helper functions); ZK-1 may add `src/zerodha/`; OE-1 implements `src/execution/`; PT-1 wires `src/notifications/` into
`scripts/portfolio/paper_snapshot.py`. No task in this story touches the `BrokerClient` protocol definition itself (`src/client/protocol.py`) beyond implementing it.

## Session-start load hints

- `PLANNER.md` and `DECISIONS.md` — full Phase 2 specs and the static-IP / Kite-MCP decisions.
- `src/client/protocol.py` — the `BrokerClient` protocol ZK-1 and OE-1 must follow exactly.
- `docs/plan/backtest-engine/phase1/tasks.md` — the Phase 1.12 gate this story (other than PV-1) waits on.
- `docs/plan/broker-abstraction/tasks.md` — BA-14/BA-15 are blocked on OE-1 existing; re-check when OE-1 unblocks.
- No `schema.md` — this story does not change DB schema.

## Task overview

- **PV-1** — P&L Visualization Cowork artifact, four panels (MF, Dhan ETFs, Nuvama Bonds, Nuvama Options); not gated on Phase 1.12.
- **ZK-1** — Zerodha / Kite Connect integration; deferred until FinRakshak/ILTS P&L visibility matters.
- **OE-1** — Order Execution Layer (`src/execution/`); hard-blocked on static IP provisioning.
- **PT-1** — `paper_snapshot.py` → Telegram via `build_notifier`; deferred until the file is touched for another reason.

## Definition of done

All four tasks ticked with a real SHA, per their individual done criteria in `tasks.md` "## Story done when." ZK-1/OE-1/PT-1 may remain open indefinitely since each is legitimately gated/deferred —
this story is not required to close as a unit.

## Perspectives not covered

This story was scoped without a security review of the Kite Connect (ZK-1) or Order Execution (OE-1) integrations — both touch live broker credentials and order placement, and should get a dedicated
security/risk pass before implementation starts, not just a `BrokerClient` protocol conformance check.
