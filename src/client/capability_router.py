"""Ordered-source fallback with health, shared across capabilities.

``CapabilityRouter`` knows nothing about options or brokers: sources are opaque
objects keyed by ``SourceId``, the call is an injected coroutine factory, and
"is this result usable" is an injected predicate. The chain router passes
``has_usable_delta``; quote and candle routers reuse this core.

Failure taxonomy (council 2026-10-07, Q2):
    rate limit (805)        sleep the floor, re-raise; never flip, never tight-loop
    auth / not subscribed   mark the pair unhealthy, alert, try the next source
    unusable result         try the next source for THIS call only; no health change
    transport failure       one retry, then a temporary circuit and the next source
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Generic, TypeVar

import structlog

from src.client.exceptions import (
    AuthenticationError,
    DataFetchError,
    NotSubscribedError,
    RateLimitError,
)
from src.client.source_health import SourceHealth
from src.models.contract import SourceId

logger = structlog.get_logger(__name__)

S = TypeVar("S")
R = TypeVar("R")


class CapabilityRouter(Generic[S, R]):
    """Routes one capability across an ordered list of sources.

    Results of type ``R`` must never be ``None``: ``None`` marks "no usable result" internally.
    """

    def __init__(
        self,
        capability: str,
        sources: Sequence[tuple[SourceId, S]],
        is_usable: Callable[[R], bool],
        health: SourceHealth,
        rate_limit_backoff_s: float = 4.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Build a router.

        Args:
            capability: Health key label, e.g. ``"chain"``.
            sources: Ordered ``(SourceId, source)`` pairs; first is preferred.
            is_usable: Whether a successful result is good enough to return.
            health: Shared health tracker.
            rate_limit_backoff_s: Pause after a rate-limit error before it is
                re-raised. The caller passes the configured floor (the 4 s
                default is the documented Dhan chain floor).
            sleep: Awaitable sleep (injected for tests).
        """
        self._capability = capability
        self._sources = list(sources)
        self._is_usable = is_usable
        self._health = health
        self._backoff = rate_limit_backoff_s
        self._sleep = sleep

    async def call(self, fetch: Callable[[S], Awaitable[R]], **ctx: object) -> R:
        """Return the first usable result, trying sources in order.

        Args:
            fetch: Coroutine factory invoked with each candidate source.
            **ctx: Extra log fields (e.g. underlying, expiry).

        Raises:
            RateLimitError: A source was rate limited (not retried elsewhere).
            DataFetchError: No source produced a usable result.
        """
        reasons: list[str] = []
        for source_id, source in self._sources:
            if not self._health.allow(source_id, self._capability):
                reasons.append(f"{source_id.value}: unhealthy")
                continue
            result = await self._try(source_id, source, fetch, reasons, ctx)
            if result is not None:
                return result
        raise DataFetchError(f"No usable {self._capability} from any source: {'; '.join(reasons)}")

    async def _try(
        self,
        source_id: SourceId,
        source: S,
        fetch: Callable[[S], Awaitable[R]],
        reasons: list[str],
        ctx: dict[str, object],
    ) -> R | None:
        cap = self._capability
        try:
            result = await self._fetch_with_retry(source_id, source, fetch, ctx)
        except RateLimitError:
            logger.warning("capability.rate_limited", source=source_id.value, capability=cap, **ctx)
            await self._sleep(self._backoff)
            raise
        except (AuthenticationError, NotSubscribedError) as exc:
            await self._health.mark_unhealthy(source_id, cap, type(exc).__name__, alert=True)
            reasons.append(f"{source_id.value}: {type(exc).__name__}")
            return None
        except DataFetchError as exc:
            await self._health.mark_unhealthy(source_id, cap, f"transport: {exc}", alert=False)
            reasons.append(f"{source_id.value}: {exc}")
            return None
        self._health.record_success(source_id, cap)
        if self._is_usable(result):
            logger.info("capability.served", source=source_id.value, capability=cap, **ctx)
            return result
        logger.info("capability.unusable", source=source_id.value, capability=cap, **ctx)
        reasons.append(f"{source_id.value}: unusable")
        return None

    async def _fetch_with_retry(
        self,
        source_id: SourceId,
        source: S,
        fetch: Callable[[S], Awaitable[R]],
        ctx: dict[str, object],
    ) -> R:
        try:
            return await fetch(source)
        except RateLimitError:
            raise
        except DataFetchError as exc:
            logger.warning(
                "capability.transport_retry",
                source=source_id.value,
                capability=self._capability,
                error=str(exc),
                **ctx,
            )
            return await fetch(source)
