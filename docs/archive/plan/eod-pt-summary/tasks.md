# EOD PT Summary — Task Checklist

> Find the first unchecked box below. That is the only task for the session. See `prompt.md`
> for session-start protocol; see `stories.md` for the full spec of each task.

- [x] **PT-1** — Document/formalize the 3-message Telegram split (open positions / closed
      today / strategy P&L + Ann.% summary) already implemented and validated in
      `scratch/2026-08-13_eod_pt_summary.py` (`build_summary_parts()`, `_PART_EMOJI`,
      `_send_telegram_markdown()`). No behavior change — this task is about capturing the
      confirmed spec (column layout, CE/PE-last instrument label, per-message emoji headers,
      MarkdownV2 fencing, non-fatal send contract) as the reference for PT-2. | SHA: d1ae760
- [x] **PT-2** — Promote the scratch script's data-collection and rendering logic into tested
      `src/` code (`src/reporting/eod_pt_summary.py`) plus a real cron script
      (`scripts/eod_pt_summary.py`). Coordination question resolved with Animesh 2026-09-07: the
      new report runs **alongside** `scripts/eod_summary.py` (not a replacement);
      `scripts/reporting/paper_pnl_report.py` is a no-cron/no-send analysis helper and is
      untouched. See DECISIONS.md §P&L & Reporting. | SHA: 77dc160
- [x] **PT-3** — Docs close: update `CONTEXT.md`/`DECISIONS.md`/`TODOS.md` per repo convention,
      add this epic's entry to `docs/plan/README.md` "Active Stories" (already added manually
      2026-08-13 — verify it's still accurate and mark this done), archive scratch script
      reference note. CONTEXT.md (792fa79) / DECISIONS.md §P&L & Reporting / TODOS.md already
      landed piecemeal; README row refreshed to ✅ Shipped; scratch script marked SUPERSEDED.
      Docs-only. | SHA: n/a
