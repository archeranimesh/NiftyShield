# Telegram Callback Auth Guard Fix — Tasks

> Find the first unchecked box below. That is the only task for this session.

- [ ] **T1** — Locate the callback auth check in `src/notifications/telegram_gateway.py` (per `src/notifications/CLAUDE.md`'s module map) and change the guard to a single identity check: `sender_id != self._chat_id`

---

**Source:** `docs/plan/full-repo-review/findings/FR-7_synthesis.md`, FR-7 row 9 (ERROR) — FR-6 S-2.
