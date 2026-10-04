"""Telegram notification sink for portfolio P&L summaries.

Sends a formatted message to a Telegram chat via the Bot API using an
asynchronous aiohttp POST call — no SDK, no framework.

Configuration (via environment variables):
    TELEGRAM_BOT_TOKEN: Bot token from @BotFather.
    TELEGRAM_CHAT_ID:   Target chat ID (get via getUpdates after messaging
                        the bot, or from @userinfobot for personal chats).

Usage:
    notifier = build_notifier()          # Returns None if env vars absent
    if notifier:
        await notifier.send("Hello from NiftyShield")

Design notes:
    - send() never raises — returns False on failure and logs a WARNING.
      A 400 "can't parse entities" is resent once as plain text (BUG-042).
    - build_notifier() returns None when either env var is missing, so the
      caller can skip notification with a simple `if notifier:` guard.
    - Uses MarkdownV2 parse_mode. send() does NOT auto-escape the message
      text — every caller that interpolates a dynamic value, or writes
      static template prose containing MarkdownV2-reserved punctuation,
      must use `escape_markdown()`/`mdcode()` from
      `src/notifications/markdown.py` (see `src/notifications/CLAUDE.md`).
"""

from __future__ import annotations

import re

import aiohttp
import structlog

logger = structlog.get_logger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_TELEGRAM_PHOTO_API = "https://api.telegram.org/bot{token}/sendPhoto"

# Lower-cased marker in Telegram's 400 body for a MarkdownV2 entity-parse
# rejection — the only failure send() retries (once, as plain text; BUG-042).
_ENTITY_PARSE_ERROR = "can't parse entities"

# Characters that must be escaped in MarkdownV2 plain text regions.
_MDV2_SPECIAL = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def escape_mdv2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2 plain text.

    Args:
        text: Raw text to escape.

    Returns:
        Escaped text safe for use outside code/pre blocks in MarkdownV2.
    """
    return _MDV2_SPECIAL.sub(r"\\\1", text)


async def _read_error_body(resp: aiohttp.ClientResponse, limit: int = 500) -> str:
    """Best-effort read of an HTTP error response body for logging.

    Args:
        resp: The aiohttp response whose status is >= 400.
        limit: Max characters returned.

    Returns:
        The response text truncated to ``limit`` chars, or a placeholder if
        the body cannot be read. Never raises.
    """
    try:
        return (await resp.text())[:limit]
    except Exception:  # Intentional: diagnostics must never mask the send failure
        return "<unreadable body>"


class TelegramNotifier:
    """Fire-and-forget notifier that sends text to a Telegram chat.

    Args:
        bot_token: Telegram bot token from @BotFather.
        chat_id:   Target chat ID (integer or string).
        timeout:   HTTP request timeout in seconds. Default: 10.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        timeout: int = 10,
        budget: int = 10,
    ) -> None:
        self._url = _TELEGRAM_API.format(token=bot_token)
        self._photo_url = _TELEGRAM_PHOTO_API.format(token=bot_token)
        self._chat_id = chat_id
        self._timeout = timeout
        self._budget = budget
        self._messages_sent = 0

    async def send(self, text: str) -> bool:
        """Send a MarkdownV2-formatted message to the configured chat.

        The message text is sent as-authored — it is NOT auto-escaped.
        Callers are responsible for making any interpolated dynamic value
        (and any reserved punctuation in static template text) MarkdownV2-safe
        via `escape_markdown()`/`mdcode()` (`src/notifications/markdown.py`)
        before calling this method. An unescaped reserved character causes
        Telegram to reject the send with a 400 ("can't parse entities"),
        which this method resends exactly once as plain text (same text, no
        ``parse_mode``) after logging an ERROR — the message still arrives,
        markup shown literally. No other failure is retried.

        Args:
            text: MarkdownV2-formatted message content, already escaped by
                  the caller where required.

        Returns:
            True if the API returned ok=True (first attempt or the plain-text
            resend), False on any other outcome — never raises.
        """
        if self._messages_sent >= self._budget:
            logger.warning(
                "Telegram notification budget exceeded (%d messages). Suppressing.", self._budget
            )
            return False

        # Increment before the API call so that network timeouts or HTTP errors
        # still burn a budget slot, preventing rapid retry loops on broken endpoints.
        self._messages_sent += 1
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
        }
        try:
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                ok, rejection = await self._post(session, payload)
                if ok or _ENTITY_PARSE_ERROR not in rejection.lower():
                    return ok
                # BUG-042: an unescaped caller would otherwise lose the message
                # silently. Resend the same text once with no parse_mode (it
                # arrives with its markup shown literally, not escaped) and log
                # loudly so the caller's escaping still gets fixed. No budget
                # slot: same logical message, and the retry is bounded at one.
                logger.error(
                    "telegram.entity_parse_plain_text_fallback",
                    body=rejection,
                    text_head=text[:80],
                )
                ok, _ = await self._post(session, {"chat_id": self._chat_id, "text": text})
                return ok
        except Exception as exc:  # Intentional: isolate all API failures
            logger.warning("Telegram notification failed: %s", exc)
            return False

    async def send_photo(self, png: bytes, *, caption: str = "") -> bool:
        """Send a PNG to the configured chat via the multipart ``sendPhoto`` API.

        Shares the per-session budget with ``send()`` and follows the same
        non-fatal contract: the slot is burned before the call, and any
        failure (non-200, ``ok=False``, transport error) is logged and
        reported as ``False`` — never raised.

        Args:
            png: Raw PNG bytes.
            caption: Optional MarkdownV2 caption, already escaped by the caller.

        Returns:
            True if Telegram accepted the photo, False otherwise.
        """
        if self._messages_sent >= self._budget:
            logger.warning("telegram.send_photo.budget_exceeded", budget=self._budget)
            return False
        self._messages_sent += 1
        form = aiohttp.FormData()
        form.add_field("chat_id", str(self._chat_id))
        form.add_field("photo", png, filename="payoff.png", content_type="image/png")
        if caption:
            form.add_field("caption", caption)
            form.add_field("parse_mode", "MarkdownV2")
        try:
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self._photo_url, data=form) as resp:
                    if resp.status != 200:
                        body = await _read_error_body(resp)
                        logger.warning("telegram.send_photo.failed", status=resp.status, body=body)
                        return False
                    data = await resp.json()
                    if not data.get("ok"):
                        logger.warning(
                            "telegram.send_photo.failed", description=data.get("description")
                        )
                        return False
                    return True
        except Exception as exc:  # Intentional: notifier must never abort the caller
            logger.warning("telegram.send_photo.failed", error=str(exc))
            return False

    async def _post(
        self, session: aiohttp.ClientSession, payload: dict[str, str]
    ) -> tuple[bool, str]:
        """POST one sendMessage payload and classify the outcome.

        Args:
            session: Open aiohttp session.
            payload: sendMessage JSON body.

        Returns:
            ``(ok, rejection_body)`` — ``rejection_body`` is Telegram's response
            body for an HTTP 400 (where the "can't parse entities" reason
            lives), else ``""``. Transport errors propagate; ``send()`` catches.
        """
        async with session.post(self._url, json=payload) as resp:
            if resp.status >= 400:
                # raise_for_status() discards Telegram's JSON body, which
                # carries the "can't parse entities ... byte offset N"
                # reason (BUG-042); capture it before the context exits.
                body = await _read_error_body(resp)
                logger.warning(
                    "Telegram notification rejected: status=%s body=%s", resp.status, body
                )
                return False, body if resp.status == 400 else ""
            resp.raise_for_status()
            data = await resp.json()
            if not data.get("ok"):
                logger.warning("Telegram API error: %s", data.get("description"))
                return False, ""
            return True, ""


def build_notifier() -> TelegramNotifier | None:
    """Build a TelegramNotifier from environment variables.

    Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from the environment.
    Reads TELEGRAM_MESSAGE_BUDGET (default 10) for the per-session cap.
    Returns None (silently) when either variable is absent — callers
    guard with ``if notifier:`` and skip notification without error.

    Deliberately bypasses the ``settings`` singleton's ``_DynamicSettings``
    cache and constructs a fresh, uncached ``Settings(_env_file=None)`` on
    every call. This function's return value gates whether a real Telegram
    message is sent, so it cannot depend on cache-invalidation correctness
    across the process lifetime — see BUG-011 (docs/bugs/bugs.md): a stale
    cached ``Settings`` instance surviving past a test's ``monkeypatch.delenv``
    made this return a live notifier instead of None under `pytest -n auto`
    full-suite runs, never in isolation. A fresh instance per call removes
    that dependency entirely, independent of whatever the exact staleness
    trigger turns out to be.

    Returns:
        Configured TelegramNotifier, or None if env vars are not set.
    """
    from src.config import Settings

    fresh = Settings(_env_file=None)  # type: ignore[call-arg]
    token = (fresh.telegram_bot_token or "").strip()
    chat_id = (fresh.telegram_chat_id or "").strip()
    if not token or not chat_id:
        return None

    budget = fresh.telegram_message_budget

    return TelegramNotifier(bot_token=token, chat_id=chat_id, budget=budget)


# ── Internal helpers ──────────────────────────────────────────────


def _html_escape(text: str) -> str:
    """Escape HTML special characters for safe embedding inside <pre>.

    Args:
        text: Raw text.

    Returns:
        Text with &, <, > replaced by HTML entities.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
