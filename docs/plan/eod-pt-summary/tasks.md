# EOD PT Summary — Task Checklist

> Find the first unchecked box below. That is the only task for the session. See `prompt.md`
> for session-start protocol; see `stories.md` for the full spec of each task.

- [ ] **PT-1** — Document/formalize the 3-message Telegram split (open positions / closed
      today / strategy P&L + Ann.% summary) already implemented and validated in
      `scratch/2026-08-13_eod_pt_summary.py` (`build_summary_parts()`, `_PART_EMOJI`,
      `_send_telegram_markdown()`). No behavior change — this task is about capturing the
      confirmed spec (column layout, CE/PE-last instrument label, per-message emoji headers,
      MarkdownV2 fencing, non-fatal send contract) as the reference for PT-2. | SHA: n/a
- [ ] **PT-2** — Promote the scratch script's data-collection and rendering logic into tested
      `src/` code plus a real cron script (`scripts/eod_pt_summary.py`), after resolving the
      coordination question with Animesh on `scripts/eod_summary.py` /
      `scripts/reporting/paper_pnl_report.py` overlap (see `prompt.md` and this task's story for
      the exact question to ask). Blocked on that answer — do not write `src/` code until
      Animesh has confirmed how the three reports should coexist. | SHA: n/a
- [ ] **PT-3** — Docs close: update `CONTEXT.md`/`DECISIONS.md`/`TODOS.md` per repo convention,
      add this epic's entry to `docs/plan/README.md` "Active Stories" (already added manually
      2026-08-13 — verify it's still accurate and mark this done), archive scratch script
      reference note. | SHA: n/a
