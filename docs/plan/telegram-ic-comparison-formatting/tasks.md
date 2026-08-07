# Telegram IC Comparison Formatting — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session. Tick the box
> and append `| SHA: <sha>` when done. Add one line to `TODOS.md`. Full story spec for each task:
> `stories.md` in this directory.

---

- [ ] **TGFMT-1** — Fix `build_comparison_report()` alignment: replace hand-counted literal
  spacing with dynamic label/column widths, right-aligned value columns. Regression test with an
  artificially long label. **Owner: Claude** (financial-report formatting, low ambiguity, mechanical
  once the scratch script's proven approach is ported).
- [ ] **TGFMT-2** — Add "Legs" row (open leg count out of 4, 🔴 if < 4) to `ICMonthlyStats` and the
  report. No new data dependency — `build_stats()` already computes `open_pos`. Can run in
  parallel with or right after TGFMT-1. **Owner: Claude.**
- [ ] **TGFMT-3** — Add `Bkd (I)` (realized since inception, new `_get_inception_realized_pnl()`
  reading `paper_nav_snapshots`); rename `Unrealized P&L` to `Flt` and drop the (M)/(I) split for
  it (unrealized is a point-in-time mark, not month-scoped — a split would always show identical
  values). Blocked by TGFMT-1 (land on a stable layout first). **Owner: Claude** — financial-logic
  gate applies (real `@code-reviewer` substitution per `REVIEW.md`, documented in commit message).

---

## Notes for whoever picks this up

- Approved format (confirmed via real Telegram sends from
  `scratch/2026-08-07_telegram_ic_comparison_format_repro.py`, 2026-08-07) is reproduced in full in
  `stories.md`'s header — use it as the byte-for-byte target for TGFMT-1's happy-path test.
- This story is independent of `docs/plan/paper-ic-daily-snapshot/` (SNAP-1..4) — it reads
  `paper_nav_snapshots` (already populated for every IC variant + CSP), not `paper_leg_snapshots`
  (the table SNAP-2 fixes). Do not block this story on that one, or vice versa.
- TGFMT-3 corrects a placeholder mistake made while iterating in the scratch script (`Flt (M)` /
  `Flt (I)` as two rows) — do not carry that duplication into the real fix. Only `Bkd` (realized)
  gets a month/inception split; `Flt` (unrealized) does not.
- The scratch script (`scratch/2026-08-07_telegram_ic_comparison_format_repro.py`) sends real
  Telegram messages and counts against the message budget — do not add it to any cron; it's a
  throwaway diagnostic, not a production entrypoint.
