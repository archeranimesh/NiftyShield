"""Pre-call Dhan token check feeding the chain health state (alert only).

A missing or expired token is detected from the token's own claims before the
Dhan chain call, marks ``chain`` on Dhan unhealthy through ``SourceHealth``
(which alerts once per incident, on the healthy-to-unhealthy edge) and raises
``AuthenticationError`` so the router falls back. Renewal is out of scope
(``ds-router-migration`` DSR-4). The token value is never logged or alerted.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

import structlog

from src.auth.dhan_token import TokenStatus, inspect_token
from src.client.chain_source import CHAIN_CAPABILITY, ChainSource
from src.client.exceptions import AuthenticationError
from src.client.source_health import AlertCallback, SourceHealth
from src.models.contract import ChainSnapshot, SourceId
from src.notifications.markdown import escape_markdown

logger = structlog.get_logger(__name__)


class PlainSender(Protocol):
    """The slice of ``NotifierProtocol`` used here (importing the full protocol drags strategy types in)."""

    async def send_plain_message(self, text: str) -> bool: ...


def notifier_alert(notifier: PlainSender) -> AlertCallback:
    """Adapt a non-fatal notifier to the ``SourceHealth`` alert callback.

    Args:
        notifier: Any ``NotifierProtocol`` (only ``send_plain_message`` is used); its send must not raise.

    Returns:
        An async callback that escapes the text for MarkdownV2 and sends it.
    """

    async def _alert(message: str) -> object:
        # Escape the dynamic text only; the emoji prefix is static and safe.
        return await notifier.send_plain_message(f"⚠️ {escape_markdown(message)}")

    return _alert


class DhanTokenGuard:
    """Checks the configured Dhan token and reports an unusable one."""

    def __init__(
        self,
        health: SourceHealth,
        token_provider: Callable[[], str | None],
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Build a guard.

        Args:
            health: Shared chain health tracker (owns the alert callback).
            token_provider: Returns the current raw token (read each call so a
                renewed token is picked up without a restart).
            clock: Timezone-aware now (injected for tests).
        """
        self._health = health
        self._token_provider = token_provider
        self._clock = clock

    def status(self) -> TokenStatus:
        """Token validity and age now (no token material)."""
        return inspect_token(self._token_provider(), self._clock())

    async def ensure_usable(self) -> None:
        """Raise ``AuthenticationError`` (after marking Dhan unhealthy) if unusable."""
        status = self.status()
        if status.usable:
            return
        reason = status.describe()
        logger.warning("dhan_token.unusable", state=status.state.value)
        await self._health.mark_unhealthy(SourceId.DHAN, CHAIN_CAPABILITY, reason, alert=True)
        raise AuthenticationError(reason)


class TokenGuardedChainSource:
    """A Dhan ``ChainSource`` that checks the token before every call."""

    def __init__(self, inner: ChainSource, guard: DhanTokenGuard) -> None:
        self._inner = inner
        self._guard = guard

    async def get_chain(self, underlying: str, expiry: str) -> ChainSnapshot:
        await self._guard.ensure_usable()
        return await self._inner.get_chain(underlying, expiry)
