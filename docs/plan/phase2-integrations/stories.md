# Phase 2 — Research Pipelines & Integrations — Stories

Full spec per task, since these four items are small and independent enough to spec directly
here (no separate detail doc to point at, unlike `docs/plan/backtest-engine/phase1/`).

## PV-1 — P&L Visualization (Cowork artifact)

**Not gated on Phase 1.12** — read-only over data that already exists, so it can be pulled
forward independently of the rest of this story if prioritised.

- Build a Cowork artifact (see the artifacts convention in the assistant's own tooling docs, not
  a `src/` module) with four panels: MF (via `src/mf/`), Dhan ETFs, Nuvama Bonds, Nuvama Options.
- Each panel reads from existing store/tracker code — `src/mf/tracker.py`,
  `src/portfolio/store.py`, and whatever Dhan/Nuvama read paths already exist. **Before writing
  any panel:** `search_graph` for the relevant tracker/store class to confirm its current method
  signatures — do not assume from memory.
- Panel 5 (Zerodha) is out of scope for this task — blocked on ZK-1 below. Build the artifact so
  a fifth panel can be added later without restructuring the first four.
- ~6 weeks of data available as of 2026-07-27 — confirm current data depth via
  `SELECT MIN(date), MAX(date) FROM ...` (aggregate query, per Rule 1 bash discipline) before
  building, since it will have grown since this was written.
- No test suite requirement in the traditional sense (it's a visualization artifact, not `src/`
  code) — but any new read-path helper functions added to support it still need tests per the
  Python Standards.

## ZK-1 — Zerodha / Kite Connect integration

**Deferred** — until FinRakshak/ILTS P&L visibility actually matters (i.e. until PV-1's Panel 5
gap is a real pain point, not preemptively).

- Before writing any code: evaluate whether a Kite MCP server already exists and is usable,
  rather than building `src/zerodha/` from scratch. Check the MCP registry
  (`mcp__mcp-registry__search_mcp_registry`, if working in Cowork) for a Kite/Zerodha connector.
- If a from-scratch client is still needed: follow the `BrokerClient` protocol
  (`src/client/protocol.py`) exactly, same as the other three implementations. `factory.py` is
  the sole composition root that may import it directly.
- No task breakdown beyond this until the decision (MCP vs. from-scratch) is made — that decision
  itself should be a short written note in `DECISIONS.md` before any code is written.

## OE-1 — Order Execution Layer (`src/execution/`)

**Hard-blocked** — static IP not provisioned for Upstox order placement. Do not start
implementation; `_raise_order_blocked()` in the live client is the current chokepoint and stays
in place until the IP is provisioned (see `DECISIONS.md` and `CLAUDE.md`'s AutoTrigger table
note on this gate).

- Design already exists against the `BrokerClient` protocol — no new design work needed when this
  unblocks, just implementation.
- When this task is picked up: re-check `DECISIONS.md` for the current state of the static-IP
  provisioning before writing any code — it may have changed since this note was written.
- Also re-check `docs/plan/broker-abstraction/tasks.md` BA-14/BA-15 — those are explicitly
  blocked on this task existing; unblocking OE-1 unblocks them too.

## PT-1 — `paper_snapshot.py` → Telegram

**Deferred** — until the file is touched for another reason (not a standalone task to pick up
proactively).

- Wire `build_notifier()` (see `src/notifications/` — non-fatal contract, returns `None` if not
  configured, HTML `parse_mode`) into `scripts/portfolio/paper_snapshot.py`.
- Confirmed via grep (2026-07-27): no notifier wiring exists in that file yet — this is still
  accurate as of the last check; re-verify with `search_code("build_notifier")` before assuming
  it's still unwired, since the file may have been touched for an unrelated reason since then.
- If picked up: follow the non-fatal contract exactly — a notifier failure must never break the
  snapshot itself. One happy-path test (message sent) + one edge-case test (notifier raises,
  snapshot still completes).
