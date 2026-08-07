# Telegram Markdown Migration — Backbone — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/telegram-markdown-migration/backbone/stories.md`.

---

- [ ] **MD-1** — Add `escape_markdown()` / `mdcode()` helpers to `src/notifications/` + tests
- [ ] **MD-2** — Switch `TelegramNotifier.send()` to Markdown parse_mode; update/replace the two
      HTML-specific tests; add an entity-parse regression test | Blocked by: MD-1
- [ ] **MD-3** — Audit + fix strategy close/roll notifications (7 classes) for unescaped dynamic
      values | Blocked by: MD-2
- [ ] **MD-4** — Audit + fix reporting scripts + `send_approval_request` for unescaped dynamic
      values | Blocked by: MD-2
- [ ] **MD-5** — Docs close: `src/notifications/CLAUDE.md`, `DECISIONS.md`, `CONTEXT.md`,
      `TODOS.md` | Blocked by: MD-3, MD-4
