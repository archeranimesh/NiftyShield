# Telegram Callback Auth Guard Fix — Story

**Source:** `docs/plan/full-repo-review/findings/FR-7_synthesis.md`, FR-7 row 9 (ERROR) — FR-6 S-2.

## T1

Locate the callback auth check in `src/notifications/telegram_gateway.py` (per `src/notifications/CLAUDE.md`'s module map) and change the guard to a single identity check:
`sender_id != self._chat_id` (the identity of the button-presser is what matters, not chat membership).
Add a regression test that simulates a callback from a non-allowlisted `sender_id` in the same chat and confirms it is rejected.

**Files touched:** `src/notifications/telegram_gateway.py`, `tests/unit/notifications/test_telegram_gateway.py`

**Tests:** happy-path + error/edge-case per CLAUDE.md Step 4, in the files listed above.
