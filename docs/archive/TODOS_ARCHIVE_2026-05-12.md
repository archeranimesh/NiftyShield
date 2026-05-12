# NiftyShield — TODOs Archive (2026-05-10 to 2026-05-11)

> Archived from `TODOS.md` on 2026-05-12.
> For the active task list see `TODOS.md`.
> Earlier archive (2026-05-01 → 2026-05-09): `TODOS_ARCHIVE_2026-05-10.md`

---

## Session Log (2026-05-10 → 2026-05-11)

| Date | What Changed |
|---|---|
| 2026-05-11 | **Paper Trading CLI & UX audit.** Full audit of 6 paper trading scripts (paper_snapshot, paper_3track_snapshot, paper_3track_overlay, paper_3track_overlay_roll, record_paper_trade, find_strike_by_delta). 12 CLI/UX issues catalogued with Antigravity handoff prompts: CLI-1 (dry-run flag unification), CLI-2 (--spot rename), CLI-3 (--index for roll), CLI-4 (--date type), CLI-5 (--track shortcuts), UX-6 (compact P&L table), UX-7 (summary-first ordering), UX-8 (--verbose flag), UX-9 (shared formatting.py), CLI-10 (--overlay filter for roll), CLI-11 (--yes semantics), CLI-12 (--notes surface). No code changed. |
| 2026-05-10 | **Auto-expiry for CSP entry scripts (SHA 21cd505).** `src/instruments/lookup.py`: added `get_expiry_candidates(underlying, today, preference)` — enumerates NIFTY expiries from BOD JSON into monthly (DTE 15–45) / quarterly (46–200) / yearly (201–420) buckets; default preference `["monthly","quarterly","yearly"]` (CSP income); accepts custom order for hedge use. `scripts/find_strike_by_delta.py`: `--expiry` now optional; when omitted, fetches chains for all candidate expiries and cross-ranks strikes by delta→round-100→spread→OI across the merged pool. `scripts/record_paper_trade.py`: wires same auto-expiry path; `--expiry` now an optional override. 6 unit tests in `tests/unit/instruments/test_expiry_candidates.py`. 58 targeted tests passing. |
| 2026-05-10 | **Markdown sweep.** Archived 2026-05-01 to 2026-05-09 session log + completed bhavcopy P1-NEXT section to `docs/archive/TODOS_ARCHIVE_2026-05-10.md`. Restructured TODOS.md (Task 0–3 sequential queue + Phase 1/2 buckets). Updated BACKTEST_PLAN.md completion log. Updated PLANNER.md completed section. Updated CONTEXT.md date + test count. |
