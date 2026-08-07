# Telegram Leg Labels — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA: <sha>` when done. Add one line to `TODOS.md`.
> Full story spec for each task: `docs/plan/telegram-leg-labels/stories.md`.

---

- [x] **TL-1** — Add `format_option_label` + `format_leg_label` to `src/instruments/lookup.py` + tests | SHA: 698e047
- [x] **TL-2** — Wire into the four overlay close-notification builders (`auto_close.py`, `cc_overlay_v1.py`, `collar_overlay_v1.py`, `pp_overlay_v1.py`) + tests | SHA: 34b16e9
- [x] **TL-3** — Wire into `scripts/strategies/ic/paper_ic_entry.py` entry-preview message text only (commands untouched) + tests | SHA: 271d6ae
- [x] **TL-4** — Add instrument-label formatting standard directly to `src/notifications/CLAUDE.md` + wire a trigger row into root `CLAUDE.md` (no new files) — no code, docs only | SHA: a81ea59
- [x] **TL-5** — Docs close: CONTEXT.md `format_leg_label` mention, TODOS.md session log entry — no further code
