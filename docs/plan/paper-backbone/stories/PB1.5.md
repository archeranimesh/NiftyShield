# PB1.5 — `src/notifications/telegram_gateway.py`: TelegramGateway + tests

**Files to change:**
- `src/notifications/telegram_gateway.py` — `TelegramGateway`
- `tests/unit/notifications/test_telegram_gateway.py` — new test file

**Before implementing:** Read `src/notifications/CLAUDE.md` — confirm the non-fatal contract.

**What to implement:**

`TelegramGateway` wraps (does not inherit) `TelegramNotifier`. Added capabilities:

```python
class TelegramGateway:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        db_path: str,
    ) -> None:
        self._notifier = TelegramNotifier(bot_token, chat_id)
        ...

    def send_plain_message(self, text: str) -> bool:
        """Delegate to TelegramNotifier.send. Non-fatal."""

    async def send_approval_request(
        self,
        council_output: CouncilOutput,
        event: SignalEvent,
        strategy_name: str,
    ) -> int | None:
        """
        Send inline-keyboard message with council-ranked actions.
        Keyboard buttons: one per ApprovedAction (labelled by action_type + rationale[:40]).
        Plus a "Reject All" button.
        Returns Telegram message_id on success, None on failure. Non-fatal.
        """

    async def start_polling(
        self,
        on_approved: Callable[[int, int], Awaitable[None]],   # (approval_id, rank)
        on_rejected: Callable[[int], Awaitable[None]],        # (approval_id,)
    ) -> None:
        """
        Async long-polling loop for CallbackQuery events (button presses).
        Auth guard: silently drop any update not from TELEGRAM_CHAT_ID.
        Routes button press to on_approved or on_rejected callbacks.
        Runs until cancelled.
        """
```

**Timeout scanner** — background asyncio task started inside `start_polling`:
Checks `pending_approvals` every 5 minutes. Rows with `status = 'PENDING'` and
`expires_at < now` → set `status = 'EXPIRED'`, set `resolved_at = now`.
Non-fatal: exception in scanner logs WARNING, loop continues.

**Auth guard** — every inbound `CallbackQuery` handler checks that `from.id` or
`chat.id` matches `TELEGRAM_CHAT_ID`. Unknown senders → log WARNING, no callback fired.

**Non-fatal contract** — all Telegram API calls wrapped in `try/except Exception`.
Return `False` / `None` on failure. Never raise.

**Tests (`tests/unit/notifications/test_telegram_gateway.py`):**

Mock `aiohttp.ClientSession` (no real HTTP calls).

- `send_plain_message` succeeds → returns `True`.
- `send_plain_message` raises network error → returns `False`, no exception propagated.
- `send_approval_request` with 2 actions → message sent with inline keyboard containing 3
  buttons (2 actions + Reject All).
- `send_approval_request` API failure → returns `None`, no exception.
- Auth guard: `CallbackQuery` from unknown chat_id → `on_approved` callback NOT called.
- Auth guard: `CallbackQuery` from correct chat_id → `on_approved` callback called with
  correct `(approval_id, rank)`.
- Timeout scanner: `pending_approvals` row with `expires_at` in the past → status set to
  `EXPIRED`.

**Commit:** `feat(notifications): add TelegramGateway with approval flow and inbound polling`

---

## Pre-baked Context

> Graph queries pre-run 2026-05-31. Skip "Before any code" graph calls — use these directly.

**`TelegramNotifier`** — `src/notifications/telegram.py:56`.
Import: `from src.notifications.telegram import TelegramNotifier`.
Constructor: `TelegramNotifier(bot_token: str, chat_id: str, timeout: int = 10, budget: int = 10)`.
Key method: `async def send(self, text: str) -> bool` — wraps text in `<pre>` HTML block.
Note: method is `send`, NOT `send_message`. Non-fatal — returns `False` on any error.

**`build_notifier`** — `src/notifications/telegram.py:121`.
Returns `TelegramNotifier | None`. Guards: checks `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` from settings.
Pattern for callers: `if notifier: await notifier.send(text)`.

**`CouncilOutput`** — defined in `src/council/models.py` (PB1.4).
Fields: `actions: list[ApprovedAction]`, `chairman_rationale: str`, `dissenting_notes: str | None`,
`stage1_responses: list[PersonaResponse]`, `latency_ms: int`.

**`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`** — in `src/config.py` `Settings` as
`telegram_bot_token: str | None` and `telegram_chat_id: str | None`.

**DB connect** — `from src.db import connect`. Context manager: `with connect(db_path) as conn:`.
Used to query/update `pending_approvals` in the timeout scanner (table added in PB1.6).
