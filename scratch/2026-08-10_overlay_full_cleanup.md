# 2026-08-10 — Full overlay (CC/PP/Collar) data cleanup

Session note, not a permanent doc — kept in `scratch/` per project convention.
Supersedes the narrower BUG-028 Phase 3 relabel approach for this specific
cleanup; the Phase 3 migration script (`scripts/dev/migrate_overlay_pnl_attribution.py`)
still exists and is still the *documented, re-runnable* fix if a future DB
ever has the same legacy-attribution problem — this doc records why, on
2026-08-10, Animesh chose a full wipe instead for the *current* DB.

## Decision

Delete every CC/PP/Collar overlay reference from `data/portfolio/portfolio.sqlite`
— both the legacy pre-S2r misattributed rows (spot/futures/proxy strategy_names)
**and** the one live, correctly-attributed `paper_nifty_overlay` PP position —
rather than repairing/relabeling the legacy rows in place.

## Why a full wipe instead of BUG-028 Phase 3's relabel

1. BUG-028 Phase 3 (council-ruled 2026-08-10, `docs/council/2026-08-10_overlay-pnl-reporting-track-independence.md`)
   only covers `paper_overlay_pnl_snapshots` — 12 rows. A full-DB inventory
   (this session) found the real footprint was much larger: 308 rows in
   `paper_leg_snapshots` (going back to 2026-05-11), 50 rows in
   `paper_exit_events`, 5 dates in `paper_protection_recovery_snapshots`.
2. Some of the legacy `paper_overlay_pnl_snapshots` rows are not safe to
   mechanically relabel — the `collar` values genuinely disagree across the
   three legacy strategy_names on the same date (e.g. 2026-08-03: futures
   -36955.75, proxy -22587.50, spot -42466.45 — not one number copied three
   times). Root cause: pre-Phase-1, each track's `generate_track_snapshot()`
   computed its *own* version of the shared overlay's P&L using that track's
   own basis. There's no principled way to pick one as canonical after the
   fact.
3. Animesh's call: don't try to reconstruct/arbitrate the old numbers — just
   remove all of it and let the (already-fixed, as of today's BUG-028 Phase 1/2
   commits) pipeline start clean.
4. Confirmed safe to include the one live PP trade: `paper_3track_overlay_entry
   --auto-pp` runs every weekday 10:30 IST (`logs/cron.log`) and self-selects
   "no open `overlay_pp` → bootstrap a fresh entry." Deleting today's live PP
   position just resets the clock; tomorrow's cron re-enters it, this time
   correctly attributed to `STRATEGY_OVERLAY` from the start. CC/Collar have no
   live position currently (confirmed — PP was the only open overlay leg), so
   there's no Wednesday-only re-entry gap to worry about.

## What was found (full inventory, read-only verification)

| Table | Scope | Rows | Date range |
|---|---|---|---|
| `paper_trades` | legacy (spot/futures/proxy), overlay leg_role | 0 | — |
| `paper_trades` | `paper_nifty_overlay` (live PP) | 1 | 2026-08-10 |
| `paper_overlay_pnl_snapshots` | legacy | 12 | 2026-08-03 → 08-04 |
| `paper_leg_snapshots` | legacy + live, `overlay_*` leg_role | 308 (11 groups × 28) | 2026-05-11 → 08-04 |
| `paper_leg_snapshots` | legacy, **bare** `cc`/`pp`/`collar` leg_role (pre-S7 naming, no prefix — separate from the row above, found on a second pass) | 168 (6 groups × 28) | 2026-05-11 → 08-04 |
| `paper_exit_events` | legacy, overlay leg_name | 50 (4 groups) | — |
| `paper_action_audit` | `paper_nifty_overlay` | 0 | — |
| `paper_protection_recovery_snapshots` | any non-null cc/pp/collar column | 5 | 2026-08-03, 08-04, 08-05, 08-07, 08-10 |

**Total: 539 rows deleted, 5 rows updated.**

No `strategy_name` column on `paper_protection_recovery_snapshots` — it also
carries real `niftybees_pnl_1d`/`niftybees_pnl_inception` per row, so those 5
rows are updated (overlay columns nulled) rather than deleted.

**Gap caught before execution:** the first version of the cleanup script only
matched `leg_role LIKE 'overlay_%'` in `paper_leg_snapshots`, missing 168 rows
recorded under the older, pre-S7 (2026-08-01) collapsed display-label naming
— literally `leg_role = 'cc'` / `'pp'` / `'collar'`, no prefix (`CONTEXT.md`'s
S7 entry: `_save_leg_snapshots()` used to persist the collapsed display dict
before being fixed to use `raw_overlay_pnls`' real keys). Confirmed via direct
query that `paper_trades` and `paper_exit_events` only ever used the `overlay_*`
naming — no bare-label rows there — so the gap was isolated to
`paper_leg_snapshots`. Fixed in the script before running for real; base legs
(`base_futures`, `base_ditm_call`, `base_etf`) were verified untouched by
either version of the filter.

## What was run

`scratch/2026-08-10_overlay_full_cleanup.py` — dry-run by default, `--execute`
backs up `portfolio.sqlite` (timestamped sibling file) then deletes/updates the
tables above, scoped to `strategy_name IN (paper_nifty_spot, paper_nifty_futures,
paper_nifty_proxy, paper_nifty_overlay)` + `leg_role`/`leg_name LIKE 'overlay_%'`.
No other strategy's data is touched.

**Execution record:**

- First attempt (`--execute`) failed mid-run: `sqlite3.IntegrityError: NOT NULL
  constraint failed: paper_protection_recovery_snapshots.cc_pnl_1d`. Root
  cause: this DB's `paper_protection_recovery_snapshots` was still on the
  pre-BUG-028-Phase-2 schema (`PRAGMA table_info` confirmed `notnull=1` on
  `cc_pnl_1d`) — the Phase 2 rebuild migration lives inside
  `PaperStore.__init__()` and only runs when something instantiates
  `PaperStore`; this script used a bare `sqlite3.connect()`, so it never
  triggered. No data was lost — the failure happened before the script's one
  `conn.commit()` call, so nothing had actually been written yet (verified:
  all row counts unchanged, schema still `notnull=1` after the failed run).
  Backup `portfolio.bak_20260810T213317.sqlite` from that attempt is
  harmless/redundant, left in place.
- Fixed by inlining the exact Phase 2 rebuild SQL from
  `src/paper/store.py::PaperStore.__init__` directly into the cleanup script
  (`_apply_protection_recovery_migration_if_needed()`) rather than importing
  the full `PaperStore` module — the sandbox used to develop this script
  lacked `structlog`/deps needed to import it, and a throwaway script
  shouldn't need that import chain anyway. Migration runs only in
  `--execute` mode, after the backup, never during dry-run.
- Dry-run re-verified unchanged (539/5, schema still `notnull=1`) before
  re-running `--execute`.
- Second `--execute` run succeeded: backup
  `portfolio.bak_20260810T213551.sqlite`, schema migration applied, then all
  539 deletes + 5 updates committed in one transaction.
- Post-run verification (direct DB query, not just the script's own report):
  zero overlay rows remain in any of the 5 tables; all three base tracks'
  `paper_leg_snapshots` rows (59 each — `base_futures`/`base_ditm_call`/
  `base_etf`) intact; `paper_nav_snapshots` unchanged at 284 rows.
- **Still outstanding:** confirm tomorrow (2026-08-11) that the 10:30 IST
  `--auto-pp` cron bootstraps a fresh `overlay_pp` entry cleanly under
  `paper_nifty_overlay` (see Follow-up below).

## Follow-up

- Confirm tomorrow (2026-08-11) that `pp_entry.log` shows a clean bootstrap
  entry under `paper_nifty_overlay`, not an error from the now-missing prior
  position.
- `scripts/dev/migrate_overlay_pnl_attribution.py` (BUG-028 Phase 3) is now
  moot for *this* DB (nothing left to relabel) but stays in the repo as the
  documented fix for any other environment that hits the same legacy-attribution
  issue without opting for a full wipe.
