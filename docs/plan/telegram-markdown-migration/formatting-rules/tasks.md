# Telegram Markdown Migration — Formatting Rules — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/telegram-markdown-migration/formatting-rules/stories.md`.

---

- [ ] **FMT-1** — Write the decimal/alignment formatting spec (per-parameter-type rules) —
      docs only, no code | Blocked by: none
- [ ] **FMT-2** — Add `src/notifications/formatting.py` value formatters
      (`format_money`, `format_greek`, `format_strike`, `format_pct`) + tests |
      Blocked by: FMT-1, `backbone/` MD-1
- [ ] **FMT-3** — Add table-builder helpers (`build_kv_table`, `build_side_by_side_kv_table`,
      `build_leg_table`) to the same module + tests | Blocked by: FMT-2
- [ ] **FMT-4** — Docs close: `src/notifications/CLAUDE.md`, `CONTEXT.md`, `TODOS.md` |
      Blocked by: FMT-3
