# Phase 2 — Research Pipelines & Integrations (2027+)

**Naming note:** this story's "Phase 2" is **not** the same as `BACKTEST_PLAN_PHASE1.md`'s
internal "Phase 2 — CSP Live + Iron Condor Paper", which is tracked separately at
`docs/plan/backtest-engine/phase2/`. This dir's name (`phase2-integrations`) predates that split
and is being kept as-is rather than renamed, since only this note is needed to disambiguate —
do not confuse the two.

**Status:** Not started. Gated on Phase 1.12 (`docs/plan/backtest-engine/phase1/tasks.md`).
Full specs in `PLANNER.md` and `docs/plan/`. This story bundles the standalone Phase-2 items that
don't already have their own story dir — the Swing/Investment signal pipelines are **not**
duplicated here; they're already tracked under `docs/plan/signals-eval-core/tasks.md` (SE1–SE8,
covering both Track A/swing and Track B/investment).

## Tasks

- [ ] **PV-1** — P&L Visualization (Cowork artifact). ~6 weeks of data available now — buildable if prioritised ahead of the Phase 1.12 gate, since it only reads existing data. Four panels: MF, Dhan ETFs, Nuvama Bonds, Nuvama Options. Panel 5 (Zerodha) blocked on Kite Connect (see ZK-1).
- [ ] **ZK-1** — Zerodha / Kite Connect integration. Defer until FinRakshak/ILTS P&L visibility matters. Evaluate Kite MCP server before writing `src/zerodha/` from scratch.
- [ ] **OE-1** — Order Execution Layer (`src/execution/`). Blocked: static IP not provisioned (`_raise_order_blocked()` in `src/client/upstox_live.py`, per DECISIONS.md). Design already done against `BrokerClient` protocol.
- [ ] **PT-1** — `paper_snapshot.py` → Telegram. Wire `build_notifier`; non-fatal. Defer until the file is touched for another reason (confirmed: no notifier wiring exists in `paper_snapshot.py` yet, as of 2026-07-27).

**Note:** PV-1 does not require the Phase 1.12 gate to clear (read-only over already-collected
data) — it can be pulled forward independently if prioritised. ZK-1/OE-1/PT-1 are genuinely
gated/deferred per their own stated reasons above, not by Phase 1.12 itself.
