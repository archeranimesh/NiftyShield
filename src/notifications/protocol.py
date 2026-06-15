"""Notifier protocol — structural interface for Telegram-style notifiers.

Any object that implements ``send_plain_message`` and ``send_approval_request``
satisfies ``NotifierProtocol``.  ``TelegramGateway`` is the canonical implementation;
tests use ``MagicMock`` / ``AsyncMock`` which satisfy this structurally.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.strategy.protocol import SignalEvent


class NotifierProtocol(Protocol):
    """Structural protocol for objects that can send Telegram notifications.

    Both methods are coroutines.  Implementations must be non-fatal — errors
    are logged and suppressed so the caller's control flow is never interrupted.
    """

    async def send_plain_message(self, text: str) -> bool:
        """Send a plain-text Telegram message.

        Args:
            text: The message body.

        Returns:
            True on success, False on any error.
        """
        ...

    async def send_approval_request(
        self,
        event: SignalEvent,
        context_str: str,
    ) -> int | None:
        """Send an inline-keyboard approval message for an ACTION signal.

        Args:
            event: The signal event (provides valid_actions from payload).
            context_str: Human-readable context appended to the message.

        Returns:
            Telegram message_id on success, None on failure.
        """
        ...
