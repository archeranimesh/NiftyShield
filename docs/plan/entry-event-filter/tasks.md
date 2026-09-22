# Entry Event Filter (R4) — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line, top to bottom. That is your only task for this session. Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.

**Origin:** TODOS.md — R4 event filter (Budget/RBI MPC/elections). **DoD per the original item: this story directory (`prompt.md` + `tasks.md`) is itself the deliverable — no code in this creation
pass.** Implementation tasks below are scoped but intentionally left unchecked for a future session; do not start EF-1 until ES12 ships (dependency, see below).

**Dependency:** ES12 must ship first (referenced in the original TODOS.md item — verify ES12's current status via `search_graph`/`TODOS.md` grep before starting EF-1; if ES12 doesn't exist under that
name anymore, find its current equivalent before proceeding).

---

- [x] **EF-0** — Create this story directory (`prompt.md` + `tasks.md`), scope the implementation into tasks below. No code. Docs-only. | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA:
  0e6700d
- [ ] **EF-1** — Design `src/market_calendar/events.yaml` schema — event date, event type (Budget/RBI MPC/election/other), severity/window (days before/after to soft-warn). Depends on ES12. | Owner:
  Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **EF-2** — Implement the loader (`src/market_calendar/`) + tests. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **EF-3** — Wire soft-warning integration into `record_paper_trade.py`, mirroring the `GateViolation` pattern. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **EF-4** — Docs close: `TODOS.md` session log, `CONTEXT.md` module tree entry, `DECISIONS.md` entry if the mechanism diverges. | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **EF-1** — `events.yaml` schema designed and documented, ES12 dependency confirmed shipped.
- **EF-2** — Loader implemented under `src/market_calendar/` with unit tests, no network in tests.
- **EF-3** — Soft-warning wired into `record_paper_trade.py`, logged not blocking, entry unaffected on event-window dates.
- **EF-4** — `TODOS.md`, `CONTEXT.md`, and (if needed) `DECISIONS.md` updated to reflect the shipped feature.
