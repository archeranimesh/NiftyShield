# Phase 2 — Research Pipelines & Integrations (2027+) — tasks

**Naming note:** this story's "Phase 2" is **not** the same as `BACKTEST_PLAN_PHASE1.md`'s internal "Phase 2 — CSP Live + Iron Condor Paper", which is tracked separately at
`docs/plan/backtest-engine/phase2/`. This dir's name (`phase2-integrations`) predates that split and is being kept as-is rather than renamed, since only this note is needed to disambiguate — do not
confuse the two.

**Status:** Not started. Gated on Phase 1.12 (`docs/plan/backtest-engine/phase1/tasks.md`). Full specs in `PLANNER.md` and `docs/plan/`. This story bundles the standalone Phase-2 items that don't
already have their own story dir — the Swing/Investment signal pipelines are **not** duplicated here; they're already tracked under `docs/plan/signals-eval-core/tasks.md` (SE1–SE8, covering both Track
A/swing and Track B/investment).

**Open: PV-1, ZK-1, OE-1, PT-1.**

**Note:** PV-1 does not require the Phase 1.12 gate to clear (read-only over already-collected data) — it can be pulled forward independently if prioritised. ZK-1/OE-1/PT-1 are genuinely
gated/deferred per their own stated reasons (see `stories.md`), not by Phase 1.12 itself.

- [ ] **PV-1** — P&L Visualization (Cowork artifact); 4 panels (MF, Dhan ETFs, Nuvama Bonds, Nuvama Options); not gated on Phase 1.12 | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer |
  SHA: —
- [ ] **ZK-1** — Zerodha / Kite Connect integration; deferred until FinRakshak/ILTS P&L visibility matters | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **OE-1** — Order Execution Layer (`src/execution/`); hard-blocked on static IP provisioning | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **PT-1** — `paper_snapshot.py` → Telegram via `build_notifier`; deferred until the file is touched for another reason | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer
  | SHA: —

## Story done when

- **PV-1** — Cowork artifact renders all four panels from existing store/tracker read paths, leaves room for a fifth (Zerodha) panel without restructuring.
- **ZK-1** — Kite MCP server evaluated (used if viable); otherwise `src/zerodha/` implements `BrokerClient` per `src/client/protocol.py`.
- **OE-1** — `src/execution/` implemented against the existing `BrokerClient`-protocol design; `_raise_order_blocked()` in `src/client/upstox_live.py` removed once the static IP is provisioned.
- **PT-1** — `paper_snapshot.py` sends a Telegram notification via `build_notifier`, non-fatal on notifier failure.
