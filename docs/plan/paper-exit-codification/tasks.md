# Paper Exit Codification — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/paper-exit-codification/stories.md`.

---

- [ ] ~~**EC-1** — Fix TIME_STOP / DTE_REVIEW priority ordering in `evaluate_cc` (q11 gap) + tests~~ **Superseded for CC 2026-08-01 by EC-5** — operator decision reverses q11's WARN-only ruling; do not implement EC-1's priority-suppression design for CC as originally written, see EC-5. (EC-1 as written may still apply to non-CC evaluators if any are found to share the same gap — confirm before assuming fully retired.)
- [ ] **EC-2** — Add two observability log lines to `StrategyMonitor` (q12 ruling) + tests
- [ ] ~~**EC-4** — Fix TIME_STOP to gate on DTE-remaining, not days-held, in `evaluate_cc`/`evaluate_time_stop_csp` + tests (spawned from TODOS.md, event 68 2026-06-30 — see stories.md). Depends on EC-1 landing first.~~ **Narrowed for CC 2026-08-01 by EC-5** — per-expiry-type floor design (≤7/≤14/≤21) replaced with a flat DTE≤5 close for CC specifically, see EC-5. EC-4's original scope still stands for `evaluate_time_stop_csp` (CSP) — not decided, not touched by EC-5, implement separately if/when CSP gets the same treatment.
- [ ] **EC-5** — (2026-08-01, operator decision, arising from `3track-consolidation` CC1/CC4 strike-selection sessions) CC-only: collapse `TIME_STOP` (`days_held >= 21`) and `DTE_REVIEW` (`dte <= 5`, WARN) into a single ACTION-severity close at `dte <= 5` in `evaluate_cc`. Supersedes EC-1's priority-suppression design (which kept DTE_REVIEW as WARN, non-closing) and narrows EC-4's per-expiry-type floor design to a flat number for CC. Depends on: none technically, but land after EC-2 is resolved one way or the other so this doesn't reopen `tasks.md` ordering questions. Blocks: `3track-consolidation` CC1/CC3 (dry-run posture), see that folder's CC5 cross-link task.
- [ ] **EC-3** — Docs close: TODOS.md session log entry, confirm DECISIONS.md already updated — no code. Run only after EC-2, EC-5 are complete (EC-1/EC-4 superseded/narrowed, not blocking).
