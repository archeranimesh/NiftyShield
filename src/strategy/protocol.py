from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from src.models.options import OptionChain
from src.paper.models import PaperPosition


@dataclass(frozen=True)
class LegSpec:
    """Describes one leg to open as part of an ApprovedAction."""

    instrument_key: str
    action: Literal["BUY", "SELL"]
    quantity: int
    leg_role: str  # e.g. "short_put", "long_put_hedge"
    notes: str = ""


@dataclass(frozen=True)
class SignalEvent:
    """Emitted by a strategy when it detects something worth acting on."""

    event_type: str
    severity: Literal["INFO", "WARN", "ACTION"]
    description: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ApprovedAction:
    """An action approved by the council and user via Telegram."""

    action_type: str
    legs_to_close: list[
        str
    ]  # leg_role values of positions to close. NOTE: leg_role must be unique within a position to be unambiguous.
    legs_to_open: list[LegSpec]
    rationale: str
    council_rank: int  # 1 = top pick (Note: rank could be decoupled from action if multi-action objects are supported)


@runtime_checkable
class PaperStrategy(Protocol):
    """Contract every pluggable strategy must satisfy.

    The StrategyMonitor calls check_signals() on every tick for
    every registered strategy. Only ACTION severity events trigger
    council consultation + Telegram approval. WARN events send a
    plain Telegram message with no approval flow. INFO events are
    logged silently.
    """

    strategy_name: str  # must start with "paper_" prefix (enforced by convention/tests)

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Return [] if nothing to act on.

        Return events to trigger council or alerts.

        Args:
            market: The current market options chain.
            positions: The current open paper positions.

        Returns:
            A list of detected signal events.
        """
        ...

    def describe_context(
        self,
        event: SignalEvent,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> str:
        """Structured context string for the council prompt.

        Plain text, no HTML.

        Args:
            event: The signal event that triggered the context request.
            market: The current market options chain.
            positions: The current open paper positions.

        Returns:
            A string describing context.
        """
        ...

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """Apply an approved action.

        Args:
            positions: The current open paper positions.
            action: The approved action to apply.

        Returns:
            The updated list of paper positions.
        """
        ...
