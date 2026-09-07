"""Deterministic SignalProvider for tests and offline runs."""

from decimal import Decimal

from ..models import Direction, MarketSnapshot, SignalResponse


class MockSignalProvider:
    """Deterministic provider for tests and offline runs.

    Returns a fixed :class:`SignalResponse` derived from the direction and
    confidence passed at construction time. Never calls a network API and
    never raises. Used by every unit test that needs a concrete
    ``SignalProvider`` instance.
    """

    provider_name: str

    def __init__(
        self,
        provider_name: str = "mock",
        direction: Direction = Direction.BULLISH,
        confidence: int = 4,
        strike_offset: int = 0,
    ) -> None:
        """Configure the fixed response.

        Args:
            provider_name: Value surfaced on ``SignalResponse.provider``.
            direction: Direction returned by every ``get_signal`` call.
            confidence: Confidence (1-5) returned by every call.
            strike_offset: Offset from ATM for ``recommended_strike``; 0 = ATM,
                -50 = one strike below, +50 = one strike above.
        """
        self.provider_name = provider_name
        self._direction = direction
        self._confidence = confidence
        self._strike_offset = strike_offset

    def __repr__(self) -> str:
        return (
            f"MockSignalProvider(provider_name={self.provider_name!r}, "
            f"direction={self._direction!r}, confidence={self._confidence!r}, "
            f"strike_offset={self._strike_offset!r})"
        )

    async def get_signal(self, snapshot: MarketSnapshot) -> SignalResponse:
        """Return a deterministic ``SignalResponse``; never raises."""
        return SignalResponse(
            trade_date=snapshot.trade_date,
            provider=self.provider_name,
            direction=self._direction,
            confidence=self._confidence,
            recommended_strike=(snapshot.option_chain.atm_strike + self._strike_offset),
            entry_premium_low=Decimal("50"),
            entry_premium_high=Decimal("60"),
            key_reason="mock reason",
            key_risk="mock risk",
            raw_response='{"mock": true}',
        )
