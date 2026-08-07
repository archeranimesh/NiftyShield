# Telegram Markdown Migration — Formatting Rules — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/telegram-markdown-migration/formatting-rules/stories.md`.

---

- [ ] **FMT-1** — Write the decimal/alignment formatting spec (per-parameter-type rules) —
      docs only, no code | Blocked by: none
- [ ] **FMT-1b** — Add `pnl_emoji`/`alert_emoji` dynamic status-emoji helpers + tests
      (presence/sign-based, not substring-matched — see stories.md for the rejected design) |
      Blocked by: FMT-1, `backbone/` MD-1
- [ ] **FMT-1c** — Add IC EOD audit timeframe color/emoji header + hashtag
      (`weekly`/`monthly`/`leaps`/`yearly` × V1/V2 — color+emoji encode timeframe only, version
      is a separate text badge; hashtag must not be code-span-wrapped) | Blocked by: FMT-1,
      `backbone/` MD-1 — file location (IC-specific vs. `src/notifications/formatting.py`) is an
      implementation-time judgment call, see stories.md
- [ ] **FMT-2** — Add `src/notifications/formatting.py` value formatters
      (`format_money`, `format_greek`, `format_strike`, `format_pct`) + tests |
      Blocked by: FMT-1, `backbone/` MD-1
- [ ] **FMT-3** — Add table-builder helpers (`build_kv_table`, `build_side_by_side_kv_table`,
      `build_leg_table`) to the same module + tests | Blocked by: FMT-2
- [ ] **FMT-4** — Docs close: `src/notifications/CLAUDE.md`, `CONTEXT.md`, `TODOS.md` |
      Blocked by: FMT-3
