"""Per-(source, capability) health with bounded recovery probes.

A capability is a free-form label such as ``"chain"``; this module never names a
concrete broker, so a new source or capability adds no edit here. State is
in-process only. An unhealthy pair is skipped until a recovery probe is due;
probes are spaced by a doubling interval that is capped, so a dead source is
never hammered.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog

from src.models.contract import SourceId

logger = structlog.get_logger(__name__)

AlertCallback = Callable[[str], Awaitable[object]]


@dataclass
class _State:
    reason: str
    next_probe_at: float
    probes: int = 0


class SourceHealth:
    """Tracks which ``(SourceId, capability)`` pairs may be called now."""

    def __init__(
        self,
        alert: AlertCallback | None = None,
        clock: Callable[[], float] = time.monotonic,
        probe_interval_s: float = 60.0,
        max_probe_interval_s: float = 900.0,
    ) -> None:
        """Build a tracker.

        Args:
            alert: Optional async callback taking a message. Failures inside it
                are logged and suppressed (alerts are never fatal).
            clock: Monotonic seconds source (injected for tests).
            probe_interval_s: Gap before the first recovery probe.
            max_probe_interval_s: Cap on the doubling probe gap.
        """
        self._alert = alert
        self._clock = clock
        self._base = probe_interval_s
        self._cap = max_probe_interval_s
        self._unhealthy: dict[tuple[SourceId, str], _State] = {}

    def is_unhealthy(self, source: SourceId, capability: str) -> bool:
        """Whether the pair is currently marked unhealthy (probe due or not)."""
        return (source, capability) in self._unhealthy

    def allow(self, source: SourceId, capability: str) -> bool:
        """Whether the pair may be called now.

        Healthy pairs are always allowed. An unhealthy pair is allowed only
        when a recovery probe is due; granting one schedules the next probe at
        a doubled (capped) interval.
        """
        state = self._unhealthy.get((source, capability))
        if state is None:
            return True
        now = self._clock()
        if now < state.next_probe_at:
            return False
        state.probes += 1
        state.next_probe_at = now + min(self._base * 2**state.probes, self._cap)
        logger.info("source_health.probe", source=source.value, capability=capability)
        return True

    def record_success(self, source: SourceId, capability: str) -> None:
        """Mark the pair healthy again (a successful probe closes the circuit)."""
        if self._unhealthy.pop((source, capability), None) is not None:
            logger.info("source_health.recovered", source=source.value, capability=capability)

    async def mark_unhealthy(
        self, source: SourceId, capability: str, reason: str, *, alert: bool
    ) -> None:
        """Mark the pair unhealthy; alert only on the healthy-to-unhealthy edge.

        Args:
            source: The failing source.
            capability: The capability label.
            reason: Short human-readable cause.
            alert: Send the alert callback on the first transition.
        """
        key = (source, capability)
        first = key not in self._unhealthy
        state = self._unhealthy.setdefault(
            key, _State(reason=reason, next_probe_at=self._clock() + self._base)
        )
        state.reason = reason
        logger.warning(
            "source_health.unhealthy", source=source.value, capability=capability, reason=reason
        )
        if first and alert and self._alert is not None:
            await self._send(f"{capability} on {source.value} unhealthy: {reason}")

    async def _send(self, message: str) -> None:
        try:
            await self._alert(message)  # type: ignore[misc]  # callers only reach _send when self._alert is set
        except Exception as exc:  # noqa: BLE001 - alerts must never break routing
            logger.error("source_health.alert_failed", error=str(exc))
