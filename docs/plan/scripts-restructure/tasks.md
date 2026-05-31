# Scripts Restructure — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to TODOS.md session log.
> Full story spec + classification rules: `docs/plan/scripts-restructure/stories.md`.
> Cron-sensitive moves (SR7, SR8, SR10): post-market only.
> SS1 must run after SR5 (scripts/dev/ must exist first).

---

## scripts/ restructure (SR series)

- [x] **SR0** — Layout sign-off: resolved 2026-05-29. pipeline/lookup/record axis confirmed. 5 open questions documented in stories.md. | 2026-05-29 discussion closed
- [x] **SR1** — Scaffold all subdirectories with `__init__.py` files; verify no src/→scripts imports | SHA: 72cb528
- [x] **SR2** — Move `pipeline/` scripts (chain snapshots, gamma watch, bhavcopy) | SHA: a6ca253
- [x] **SR3** — Move `lookup/` scripts (find_strike, find_overlay, instrument_lookup) | SHA: 3fac186
- [x] **SR4** — Move `record/` scripts (record_paper_trade, record_trade) | SHA: 5acd9fe
- [x] **SR5** — Move `seed/` and `dev/` scripts; resolve paper_track_snapshot fate | SHA: 16ca1e1, test fix SHA: 66f9edd
- [ ] **SR6** — [LOCKED until SR5] Move `council/` scripts + council_templates/
- [ ] **SR7** — [LOCKED until SR6] Move `intraday/` scripts — post-market only (high cron sensitivity)
- [ ] **SR8** — [LOCKED until SR7] Move `strategies/three_track/` scripts — post-market only (EOD cron)
- [ ] **SR9** — [LOCKED until SR8] Move `strategies/csp/` and `strategies/cc_calibration/` scripts
- [ ] **SR10** — [LOCKED until SR9] Move `portfolio/` scripts — post-market only (EOD cron)
- [ ] **SR11** — Docs close: CONTEXT.md, DECISIONS.md, TODOS.md

---

## src/ restructure (SS series)

- [x] **SS0** — src/ audit complete 2026-05-29. 5 issues identified; SS1–SS4 stories written. | 2026-05-29 discussion closed
- [ ] **SS1** — [LOCKED until SR5] Evict `src/analytics/` and `src/sandbox/` into `scripts/dev/`; fix test_ naming
- [x] **SS2** — Document 5 undocumented files in CONTEXT_TREE.md; fix stale nuvama mock_client entry | 2026-05-29 done
- [ ] **SS3** — [LOCKED until SS2] Audit and resolve `src/portfolio/service.py` and `src/intraday/market_store.py`
- [ ] **SS4** — Write `src/gamma/CLAUDE.md` and `src/nuvama/CLAUDE.md`; codify model placement rule in DECISIONS.md
- [ ] **SS5** — [LOCKED until SS1 + SS3] Sync CONTEXT_TREE.md: remove evicted src/ blocks, verify all remaining files have entries

---

## docs/archive/ restructure (DA series)

- [x] **DA0** — Archive audit complete 2026-05-29. Layout designed; two new subfolders (process/, research/); 8 moves + 2 deletes identified. | 2026-05-29 discussion closed
- [ ] **DA1** — Implement archive restructure: create process/ and research/; move 8 files; delete reco_tracker.md + empty docs/analysis/; evict gamma_implementation_plan.md from live docs/antigravity/
