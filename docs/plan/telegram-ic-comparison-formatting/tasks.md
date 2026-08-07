# Telegram IC Comparison Formatting — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session. Tick the box
> and append `| SHA: <sha>` when done. Add one line to `TODOS.md`. Full story spec for each task:
> `stories.md` in this directory.

---

- [x] **TGFMT-1** — Fix `build_comparison_report()` alignment: replace hand-counted literal
  spacing with dynamic label/column widths, right-aligned value columns. Regression test with an
  artificially long label. **Owner: Claude** (financial-report formatting, low ambiguity, mechanical
  once the scratch script's proven approach is ported). | SHA: PENDING
- [ ] **TGFMT-2** — Add "Legs" row (open leg count out of 4, 🔴 if < 4) to `ICMonthlyStats` and the
  report. No new data dependency — `build_stats()` already computes `open_pos`. Can run in
  parallel with or right after TGFMT-1. **Owner: Claude.**
- [ ] **TGFMT-3** — Add `Bkd (I)` (realized since inception, new `_get_inception_realized_pnl()`)
  and `Flt (M)` (unrealized P&L change since month start, new
  `_get_unrealized_pnl_month_change()` — a real delta calc, not a copy of `Flt (I)`); rename
  `Unrealized P&L` to `Flt (I)`. Revised 2026-08-07: original spec dropped the M/I split for
  unrealized; user asked for the split back with a real month-delta calc instead. Blocked by
  TGFMT-1 (land on a stable layout first). **Owner: Claude** — financial-logic gate applies (real
  `@code-reviewer` substitution per `REVIEW.md`, documented in commit message).

---

- [ ] **TGFMT-4** — Extract `format_table()`/`column_width()` into `src/notifications/table_format.py`;
  refactor `build_comparison_report()` (post-TGFMT-1) to use it, behavior-preserving. Run *after*
  TGFMT-1 lands. **Owner: Claude.**
- [ ] **TGFMT-5** — Fix `_format_combined_summary` (`src/portfolio/formatting.py`, feeds
  `daily_snapshot.py`) using `format_table()`. Blocked by TGFMT-4. **Owner: Claude.**
- [ ] **TGFMT-6** — Fix `_send_close_notification` (`src/strategy/auto_close.py`) alignment using
  `format_table()`. Blocked by TGFMT-4. Financial-logic gate applies (real `@code-reviewer`
  substitution per `REVIEW.md`, documented in commit message — capital-affecting close path).
  **Owner: Claude.**
- [ ] **TGFMT-7** — Fix 4 three-track/dev snapshot table prints (`paper_3track_snapshot.py`,
  `paper_3track_overlay_entry.py`, `paper_3track_entry.py`, `paper_track_snapshot.py`) using
  `format_table()`. Blocked by TGFMT-4. **Owner: Claude.**
- [ ] **TGFMT-8** — Fold "Tabular Message Formatting" standard into `src/notifications/CLAUDE.md`
  + trigger row in root `CLAUDE.md`. No new files. Blocked by TGFMT-4..7 (or run once all code
  changes are in). **Owner: Claude.**
- [ ] **TGFMT-9** — Docs close: `CONTEXT.md`, `CONTEXT_TREE.md`, `TODOS.md`, `DECISIONS.md`,
  `docs/plan/README.md` updates. No further code changes. **Owner: Claude.**

---

## Notes for whoever picks this up

- Approved format (confirmed via real Telegram sends from
  `scratch/2026-08-07_telegram_ic_comparison_format_repro.py`, 2026-08-07) is reproduced in full in
  `stories.md`'s header — use it as the byte-for-byte target for TGFMT-1's happy-path test.
- This story is independent of `docs/plan/paper-ic-daily-snapshot/` (SNAP-1..4) — it reads
  `paper_nav_snapshots` (already populated for every IC variant + CSP), not `paper_leg_snapshots`
  (the table SNAP-2 fixes). Do not block this story on that one, or vice versa.
- TGFMT-3 (revised 2026-08-07): both `Bkd` and `Flt` get a month/inception split. `Bkd (M)`/
  `Bkd (I)` come nearly free from `paper_nav_snapshots.realized_pnl` (cumulative field). `Flt (M)`
  is a **real new calculation** (month-start delta on `unrealized_pnl`, a point-in-time field) —
  do not implement it as a copy of `Flt (I)`; the two are expected to differ and a test asserts
  that.
- The scratch script (`scratch/2026-08-07_telegram_ic_comparison_format_repro.py`) sends real
  Telegram messages and counts against the message budget — do not add it to any cron; it's a
  throwaway diagnostic, not a production entrypoint.
- **Scope extension (same day):** TGFMT-4 onward generalize TGFMT-1's fix into a shared
  `format_table()` helper and retrofit it to 6 other message builders found broken in a
  repo-wide survey (`src/portfolio/formatting.py`, `src/strategy/auto_close.py`, and 4
  three-track/dev snapshot printers). See `stories.md`'s "Scope extension" section for the full
  survey table and per-story specs. Do not start TGFMT-4 before TGFMT-1..3 land.
