# PaperStore Position Granularity — Task Checklist

> Antigravity: find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/paper-store-position-granularity/stories.md`.

---

- [x] **PG-1** — Fix `PaperStore.get_positions()` to group by `(strategy_name, leg_role, instrument_key)` + update `PaperPosition` model + tests | SHA: c89b0d8
- [ ] **PG-2** — Audit and fix all callers of `get_positions()` that assumed one position per leg role (snapshot scripts, delta tracker, strategy monitor, executor)
- [ ] **PG-3** — Docs close: TODOS.md session log entry, DECISIONS.md entry, CONTEXT.md model tree update — no code
