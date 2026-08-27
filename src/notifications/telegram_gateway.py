"""TelegramGateway — approval-request sender, inbound poller, and timeout scanner.

Wraps TelegramNotifier for plain text and adds:
- Inline-keyboard approval request via sendMessage.
- Long-polling loop for CallbackQuery events (button presses).
- Auth guard: drops callbacks from senders not matching the configured chat_id.
- Timeout scanner: background asyncio task that expires stale pending_approvals rows.

Non-fatal contract: all Telegram API calls are wrapped in try/except.
Failures return False / None and log WARNING. Never raise.

Approval flow (council-free):
  SignalEvent.payload["valid_actions"] carries the list of allowed action_type
  strings for this signal.  send_approval_request builds one keyboard button per
  action — no LLM call, no CouncilOutput required.
"""

from __future__ import annotations

import asyncio
import datetime
from collections.abc import Awaitable, Callable
from pathlib import Path

import aiohttp
import structlog

from src.db import connect
from src.notifications.markdown import escape_markdown
from src.notifications.telegram import TelegramNotifier
from src.strategy.protocol import SignalEvent

logger = structlog.get_logger(__name__)

_SCANNER_INTERVAL_SECONDS = 300  # 5 minutes


class TelegramGateway:
    """Approval-flow gateway over the Telegram Bot API.

    Wraps TelegramNotifier for plain messages and extends it with:
    - send_approval_request: posts an inline-keyboard message for direct
      action selection (no council/LLM call).
    - start_polling: long-polling loop that dispatches CallbackQuery events
      to registered callbacks.
    - scan_expired_approvals: marks stale pending_approvals rows as EXPIRED;
      called automatically every 5 minutes from start_polling.

    Non-fatal contract: every Telegram API call is wrapped in try/except.
    Failures return False / None and log WARNING. Never raise.

    Args:
        bot_token: Telegram bot token from @BotFather.
        chat_id: Authorised chat ID. Inbound callbacks from any other ID
            are silently dropped after logging a WARNING.
        db_path: Filesystem path to the shared SQLite database (used by
            the timeout scanner to update pending_approvals).
    """

    def __init__(self, bot_token: str, chat_id: str, db_path: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._db_path = Path(db_path)
        self._notifier = TelegramNotifier(bot_token, chat_id)
        self._base_url = f"https://api.telegram.org/bot{bot_token}"

    async def send_plain_message(self, text: str) -> bool:
        """Delegate to TelegramNotifier.send. Non-fatal.

        Args:
            text: Message content.

        Returns:
            True on success, False on any failure.
        """
        try:
            return await self._notifier.send(text)
        except Exception as exc:  # Intentional: isolate all API failures
            logger.warning("send_plain_message error: %s", exc)
            return False

    async def send_approval_request(
        self,
        event: SignalEvent,
        context_str: str,
    ) -> int | None:
        """Send an inline-keyboard message listing valid actions for a signal.

        One button per action_type drawn from
        ``event.payload["valid_actions"]``, plus a "Reject All" button.
        callback_data for action buttons is ``approve:{rank}`` (1-indexed);
        for reject: ``reject``.

        No LLM or council call is made — actions are fixed per strategy and
        embedded in the signal payload by the emitting strategy.

        The caller should record the returned message_id as the approval
        identifier in the pending_approvals table.

        Args:
            event: Signal that triggered the request.  Must carry
                ``valid_actions`` in its payload (list of action_type strings).
            context_str: Plain-text context block from
                ``strategy.describe_context()``; escaped and rendered as plain
                MarkdownV2 text (not a code block — arbitrary strategy context
                may contain backticks, which would break a fenced span).

        Returns:
            Telegram message_id on success, None on any failure.
        """
        valid_actions: list[str] = event.payload.get("valid_actions") or []
        if not valid_actions:
            logger.error(
                "send_approval_request: no valid_actions in payload for event_type=%s — cannot build keyboard",
                event.event_type,
            )
            return None
        header = (
            f"*⚡ Action required — {escape_markdown(event.event_type)}*\n"
            f"Severity: {escape_markdown(event.severity)}\n"
            f"{escape_markdown(event.description)}\n\n"
            f"*Context:*\n"
            f"{escape_markdown(context_str[:400])}"
        )
        keyboard = _build_keyboard(valid_actions)
        payload: dict = {
            "chat_id": self._chat_id,
            "text": header,
            "parse_mode": "MarkdownV2",
            "reply_markup": {"inline_keyboard": keyboard},
        }
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(f"{self._base_url}/sendMessage", json=payload) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    if not data.get("ok"):
                        logger.warning("send_approval_request failed: %s", data.get("description"))
                        return None
                    return int(data["result"]["message_id"])
        except Exception as exc:  # Intentional: isolate all API failures
            logger.warning("send_approval_request error: %s", exc)
            return None

    async def start_polling(
        self,
        on_approved: Callable[[int, int], Awaitable[None]],
        on_rejected: Callable[[int], Awaitable[None]],
    ) -> None:
        """Start async long-polling loop for Telegram CallbackQuery events.

        Routes button presses to on_approved or on_rejected callbacks based
        on callback_data. Auth guard silently drops callbacks from unknown
        senders. Starts a background timeout scanner task. Runs until
        the calling task is cancelled.

        Args:
            on_approved: Coroutine called with (message_id, rank) when a
                council action button is pressed. message_id identifies the
                pending_approvals record.
            on_rejected: Coroutine called with (message_id,) when Reject All
                is pressed.
        """
        scanner_task = asyncio.create_task(self._run_scanner())
        offset = 0
        try:
            while True:
                updates = await self._get_updates(offset)
                for update in updates:
                    offset = update["update_id"] + 1
                    cq = update.get("callback_query")
                    if cq is None:
                        continue
                    await self._handle_callback(cq, on_approved, on_rejected)
        finally:
            scanner_task.cancel()
            try:
                await scanner_task
            except asyncio.CancelledError:
                pass

    async def scan_expired_approvals(self) -> None:
        """Expire pending_approvals rows whose expires_at has passed.

        Sets status = 'EXPIRED' and resolved_at = now (UTC ISO-8601) for
        every row where status = 'PENDING' and expires_at < now.

        Non-fatal: logs WARNING on any error and returns without raising.
        Table may not exist yet (added in PB1.6); that case is also handled
        gracefully.
        """
        try:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            with connect(self._db_path) as conn:
                conn.execute(
                    """
                    UPDATE pending_approvals
                       SET status = 'EXPIRED',
                           resolved_at = ?
                     WHERE status = 'PENDING'
                       AND expires_at < ?
                    """,
                    (now_iso, now_iso),
                )
        except Exception as exc:  # Intentional: non-fatal; table may not exist yet (PB1.6)
            logger.warning("Timeout scanner error: %s", exc)

    async def send_notification(self, message: str) -> None:
        """Send plain MarkdownV2 informational message; no keyboard. Non-fatal.

        Args:
            message: MarkdownV2 formatted message.
        """
        payload = {
            "chat_id": self._chat_id,
            "text": message,
            "parse_mode": "MarkdownV2",
        }
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(f"{self._base_url}/sendMessage", json=payload) as resp:
                    resp.raise_for_status()
        except Exception as exc:
            logger.warning("send_notification error: %s", exc)

    # ── Private helpers ──────────────────────────────────────────────

    async def _get_updates(self, offset: int) -> list[dict]:
        """Fetch updates from the getUpdates long-polling endpoint.

        Args:
            offset: Update ID to start from (exclusive).

        Returns:
            List of update dicts, empty on any error.
        """
        params: dict = {
            "offset": offset,
            "timeout": 30,
            "allowed_updates": ["callback_query"],
        }
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=40)) as session:
                async with session.get(f"{self._base_url}/getUpdates", params=params) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    if not data.get("ok"):
                        logger.warning("getUpdates error: %s", data.get("description"))
                        return []
                    return list(data.get("result", []))
        except asyncio.CancelledError:
            raise
        except (
            Exception
        ) as exc:  # Intentional: isolate transient network failures; retry after delay
            logger.warning("getUpdates failed: %s", exc)
            await asyncio.sleep(5)
            return []

    async def _handle_callback(
        self,
        cq: dict,
        on_approved: Callable[[int, int], Awaitable[None]],
        on_rejected: Callable[[int], Awaitable[None]],
    ) -> None:
        """Route a single CallbackQuery to the appropriate callback.

        Auth guard: drops updates whose sender id differs from the
        configured chat_id. Only the identity of the button-presser
        matters — chat membership is not a valid substitute, since any
        member of a group chat the bot is added to could otherwise
        approve/reject real trading decisions.

        Args:
            cq: Raw callback_query dict from Telegram.
            on_approved: Callback for approve button presses.
            on_rejected: Callback for reject button presses.
        """
        sender_id = str(cq.get("from", {}).get("id", ""))
        if sender_id != self._chat_id:
            logger.warning(
                "Auth guard: dropping callback from sender=%s",
                sender_id,
            )
            return

        message_id: int = cq["message"]["message_id"]
        data: str = cq.get("data", "")

        if data.startswith("approve:"):
            try:
                rank = int(data.split(":")[1])
            except (IndexError, ValueError):
                logger.warning("Malformed approve callback_data: %s", data)
                return
            try:
                await on_approved(message_id, rank)
            except Exception as exc:  # Intentional: isolate caller callback; polling must continue
                logger.warning("on_approved callback raised: %s", exc)
        elif data == "reject":
            try:
                await on_rejected(message_id)
            except Exception as exc:  # Intentional: isolate caller callback; polling must continue
                logger.warning("on_rejected callback raised: %s", exc)
        else:
            logger.warning("Unknown callback_data: %s", data)

    async def _run_scanner(self) -> None:
        """Background loop: call scan_expired_approvals every 5 minutes."""
        while True:
            await asyncio.sleep(_SCANNER_INTERVAL_SECONDS)
            await self.scan_expired_approvals()


# ── Module-level helpers ──────────────────────────────────────────


def _build_keyboard(actions: list[str]) -> list[list[dict]]:
    """Build a Telegram inline_keyboard from a list of action_type strings.

    Each action produces one row with a single button labelled by the
    action_type string.  A final "Reject All" row is appended unconditionally.
    callback_data for action buttons is ``approve:{rank}`` (1-indexed);
    for reject: ``reject``.

    Args:
        actions: Ordered list of action_type strings, e.g.
            ``["CLOSE_FULL"]`` or
            ``["CLOSE_FULL", "CLOSE_CALL_SPREAD", "CLOSE_PUT_SPREAD"]``.

    Returns:
        Telegram inline_keyboard structure: list of button rows.
    """
    rows: list[list[dict]] = []
    for rank, action_type in enumerate(actions, start=1):
        rows.append([{"text": action_type, "callback_data": f"approve:{rank}"}])
    rows.append([{"text": "❌ Reject All", "callback_data": "reject"}])
    return rows
