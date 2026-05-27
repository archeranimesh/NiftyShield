# MVP — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/mvp/mvp_stories.md`.

---

- [ ] **M1.1** — `src/mvp/models.py`: Provider, Category, Pick, MVPSnapshot Pydantic models + tests
- [ ] **M1.2** — `src/mvp/store.py`: init_db + provider/category CRUD + tests
- [ ] **M1.3** — `src/mvp/store.py`: pick CRUD + snapshot methods + tests
- [ ] **M2.1** — `src/mvp/tracker.py`: MVPEvent + check_prices pure logic + tests
- [ ] **M2.2** — `src/mvp/tracker.py`: format_telegram_summary + tests
- [ ] **M3.1** — `scripts/mvp.py`: provider + category subcommands
- [ ] **M3.2** — `scripts/mvp.py`: add + update + close subcommands (with instrument resolution)
- [ ] **M3.3** — `scripts/mvp.py`: list + summary subcommands
- [ ] **M4.1** — `scripts/mvp_watch.py`: LTP fetch + snapshot recording + auto-close
- [ ] **M4.2** — `scripts/mvp_watch.py`: Telegram per-alert + consolidated hourly summary
- [ ] **M5** — Docs close: CONTEXT.md tree, DECISIONS.md entry, TODOS.md session log
