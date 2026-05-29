# Scripts Restructure — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to TODOS.md session log.
> Full story spec + classification rules: `docs/plan/scripts-restructure/stories.md`.
> Cron-sensitive moves (SR7, SR8, SR10): post-market only.

---

- [x] **SR0** — Layout sign-off: resolved 2026-05-29. pipeline/lookup/record axis confirmed. 5 open questions documented in stories.md. | 2026-05-29 discussion closed
- [ ] **SR1** — Scaffold all subdirectories with `__init__.py` files; verify no src/→scripts imports
- [ ] **SR2** — [LOCKED until SR1] Move `pipeline/` scripts (chain snapshots, gamma watch, bhavcopy)
- [ ] **SR3** — [LOCKED until SR2] Move `lookup/` scripts (find_strike, find_overlay, instrument_lookup)
- [ ] **SR4** — [LOCKED until SR3] Move `record/` scripts (record_paper_trade, record_trade)
- [ ] **SR5** — [LOCKED until SR4] Move `seed/` and `dev/` scripts; resolve paper_track_snapshot fate
- [ ] **SR6** — [LOCKED until SR5] Move `council/` scripts + council_templates/
- [ ] **SR7** — [LOCKED until SR6] Move `intraday/` scripts — post-market only (high cron sensitivity)
- [ ] **SR8** — [LOCKED until SR7] Move `strategies/three_track/` scripts — post-market only (EOD cron)
- [ ] **SR9** — [LOCKED until SR8] Move `strategies/csp/` and `strategies/cc_calibration/` scripts
- [ ] **SR10** — [LOCKED until SR9] Move `portfolio/` scripts — post-market only (EOD cron)
- [ ] **SR11** — Docs close: CONTEXT.md, DECISIONS.md, TODOS.md
