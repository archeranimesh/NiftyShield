# Paper Exit Codification — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/paper-exit-codification/stories.md`.

---

- [ ] **EC-1** — Fix TIME_STOP / DTE_REVIEW priority ordering in `evaluate_cc` (q11 gap) + tests
- [ ] **EC-2** — Add two observability log lines to `StrategyMonitor` (q12 ruling) + tests
- [ ] **EC-4** — Fix TIME_STOP to gate on DTE-remaining, not days-held, in `evaluate_cc`/`evaluate_time_stop_csp` + tests (spawned from TODOS.md, event 68 2026-06-30 — see stories.md). Depends on EC-1 landing first.
- [ ] **EC-3** — Docs close: TODOS.md session log entry, confirm DECISIONS.md already updated — no code. Run only after EC-1, EC-2, EC-4 are all complete.
