from typing import Protocol, runtime_checkable

from .models import MarketSnapshot, SignalResponse


@runtime_checkable
class SignalProvider(Protocol):
    """
    Contract for all signal providers (Grok, GPT-4o, Gemini, Mock).

    Constructor injection only — factory.py is the sole composition root.
    Implementations must be safe to call concurrently via asyncio.gather.
    """

    provider_name: str

    async def get_signal(self, snapshot: MarketSnapshot) -> SignalResponse:
        """Call the LLM with snapshot context, parse structured response."""
        ...
