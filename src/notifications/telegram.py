"""Telegram notification sink for portfolio P&L summaries.

Sends a formatted message to a Telegram chat via the Bot API using a
simple requests.post() call — no SDK, no framework.

Configuration (via environment variables):
    TELEGRAM_BOT_TOKEN: Bot token from @BotFather.
    TELEGRAM_CHAT_ID:   Target chat ID (get via getUpdates after messaging
                        the bot, or from @userinfobot for personal chats).

Usage:
    notifier = build_notifier()          # Returns None if env vars absent
    if notifier:
        notifier.send("Hello from NiftyShield")

Design notes:
    - send() never raises — returns False on failure and logs a WARNING.
    - build_notifier() returns None when either env var is missing, so the
      caller can skip notification with a simple `if notifier:` guard.
    - Uses MarkdownV2 parse_mode for clean formatting; the escape() helper
      handles the strict MarkdownV2 character set.
    - Message content is sent in a <pre> HTML block so monospace alignment
      in the P&L summary is preserved on mobile (HTML parse_mode used for
      code blocks since MarkdownV2 code blocks require backtick escaping).
"""

from __future__ import annotations

import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

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
    ) -> None:
        self._url = _TELEGRAM_API.format(token=bot_token)
        self._chat_id = chat_id
        self._timeout = timeout

    def send(self, text: str) -> bool:
        """Send a plain-text message to the configured chat.

        The message is wrapped in a <pre> block so monospace formatting
        (e.g. the P&L alignment) renders correctly on mobile.

        Args:
            text: Message content. HTML-unsafe characters are escaped
                  automatically before wrapping in <pre>.

        Returns:
            True if the API returned ok=True, False on any error.
        """
        html_text = _html_escape(text)
        payload = {
            "chat_id": self._chat_id,
            "text": f"<pre>{html_text}</pre>",
            "parse_mode": "HTML",
        }
        try:
            resp = requests.post(self._url, json=payload, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.warning("Telegram API error: %s", data.get("description"))
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram notification failed: %s", exc)
            return False


def build_notifier() -> TelegramNotifier | None:
    """Build a TelegramNotifier from environment variables.

    Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from the environment.
    Returns None (silently) when either variable is absent — callers
    guard with ``if notifier:`` and skip notification without error.

    Returns:
        Configured TelegramNotifier, or None if env vars are not set.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return None
    return TelegramNotifier(bot_token=token, chat_id=chat_id)


# ── Internal helpers ──────────────────────────────────────────────


def _html_escape(text: str) -> str:
    """Escape HTML special characters for safe embedding inside <pre>.

    Args:
        text: Raw text.

    Returns:
        Text with &, <, > replaced by HTML entities.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
