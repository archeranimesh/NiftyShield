# Entry Event Filter (R4) — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line, top to bottom. That is your only task
> for this session. Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.

**Origin:** TODOS.md — R4 event filter (Budget/RBI MPC/elections). **DoD per the original item:
this story directory (`prompt.md` + `tasks.md`) is itself the deliverable — no code in this
creation pass.** Implementation tasks below are scoped but intentionally left unchecked for a
future session; do not start EF-1 until ES12 ships (dependency, see below).

**Dependency:** ES12 must ship first (referenced in the original TODOS.md item — verify ES12's
current status via `search_graph`/`TODOS.md` grep before starting EF-1; if ES12 doesn't exist
under that name anymore, find its current equivalent before proceeding).

---

- [x] **EF-0** — Create this story directory (`prompt.md` + `tasks.md`), scope the
  implementation into tasks below. No code. Docs-only.
- [ ] **EF-1** — Design `src/market_calendar/events.yaml` schema — event date, event type
  (Budget/RBI MPC/election/other), severity/window (days before/after to soft-warn). Depends on
  ES12.
- [ ] **EF-2** — Implement the loader (`src/market_calendar/` — check existing module structure
  via `get_code_snippet`/`search_graph("market_calendar")` first; likely a sibling to the
  existing holiday-calendar loader, not a new pattern) + tests.
- [ ] **EF-3** — Wire soft-warning integration into `record_paper_trade.py` — a soft warning
  (logged, does not block entry) when entry date falls inside an event window. Mirrors the
  existing THRESHOLD-gate pattern (`GateViolation`, logged not blocking) rather than inventing a
  new warning mechanism — check `src/paper/models.py::GateViolation` and
  `scripts/strategies/ic/ic_entry_gates.py` for the established pattern before building a new
  one.
- [ ] **EF-4** — Docs close: `TODOS.md` session log, `CONTEXT.md` module tree entry for
  `events.yaml` + loader, `DECISIONS.md` entry if the soft-warning mechanism diverges from the
  existing `GateViolation` pattern.
