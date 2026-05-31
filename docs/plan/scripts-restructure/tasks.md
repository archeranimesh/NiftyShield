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
- [x] **SR6** — Move `council/` scripts + council_templates/ | SHA: 55bb02c
- [x] **SR7** — Move `intraday/` scripts — post-market only (high cron sensitivity) | SHA: 20b3834
- [x] **SR8** — Move `strategies/three_track/` scripts — post-market only (EOD cron) | SHA: 28894d2
- [x] **SR9** — Move `strategies/csp/` and `strategies/cc_calibration/` scripts | SHA: e161cc9
- [x] **SR10** — Move `portfolio/` scripts — post-market only (EOD cron) | SHA: 13b7285
- [x] **SR11** — Docs close: CONTEXT.md, DECISIONS.md, TODOS.md | SHA: 4777759

---

## src/ restructure (SS series)

- [x] **SS0** — src/ audit complete 2026-05-29. 5 issues identified; SS1–SS4 stories written. | 2026-05-29 discussion closed
- [x] **SS1** — [LOCKED until SR5] Evict `src/analytics/` and `src/sandbox/` into `scripts/dev/`; fix test_ naming | SHA: 4fd2e19
- [x] **SS2** — Document 5 undocumented files in CONTEXT_TREE.md; fix stale nuvama mock_client entry | 2026-05-29 done
- [x] **SS3** — [LOCKED until SS2] Audit and resolve `src/portfolio/service.py` and `src/intraday/market_store.py` | SHA: 5986948 (service.py: SnapshotServiceProtocol added; market_store.py: callers confirmed, tests green, CONTEXT_TREE documented)
- [ ] **SS4** — Write `src/gamma/CLAUDE.md` and `src/nuvama/CLAUDE.md`; codify model placement rule in DECISIONS.md
- [ ] **SS5** — [LOCKED until SS1 + SS3] Sync CONTEXT_TREE.md: remove evicted src/ blocks, verify all remaining files have entries

---

## docs/archive/ restructure (DA series)

- [x] **DA0** — Archive audit complete 2026-05-29. Layout designed; two new subfolders (process/, research/); 8 moves + 2 deletes identified. | 2026-05-29 discussion closed
- [ ] **DA1** — Implement archive restructure: create process/ and research/; move 8 files; delete reco_tracker.md + empty docs/analysis/; evict gamma_implementation_plan.md from live docs/antigravity/
