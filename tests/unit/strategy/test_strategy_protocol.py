from dataclasses import FrozenInstanceError

import pytest

from src.models.options import OptionChain
from src.paper.models import PaperPosition
from src.strategy.protocol import ApprovedAction, LegSpec, PaperStrategy, SignalEvent


class MockStrategy:
    """A strategy class implementing the PaperStrategy protocol for testing."""

    strategy_name: str = "paper_mock_strategy"

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        return []

    def describe_context(
        self,
        event: SignalEvent,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> str:
        return "mock_context"

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        return positions


class MissingMethodStrategy:
    """A strategy class that is missing check_signals method."""

    strategy_name: str = "paper_invalid_strategy"

    def describe_context(
        self,
        event: SignalEvent,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> str:
        return "mock_context"

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        return positions


def test_protocol_conformance():
    """Test runtime_checkable conformance of PaperStrategy."""
    mock_strategy = MockStrategy()
    assert isinstance(mock_strategy, PaperStrategy)
    assert hasattr(mock_strategy, "strategy_name"), (
        "PaperStrategy must have strategy_name attribute"
    )
    assert mock_strategy.strategy_name.startswith("paper_"), (
        "strategy_name must start with 'paper_' prefix"
    )

    invalid_strategy = MissingMethodStrategy()
    assert not isinstance(invalid_strategy, PaperStrategy)


def test_leg_spec_model():
    """Test LegSpec model initialization and immutability."""
    leg = LegSpec(
        instrument_key="NSE_EQ|INE123",
        action="BUY",
        quantity=50,
        leg_role="short_put",
        notes="Hedge leg",
    )
    assert leg.instrument_key == "NSE_EQ|INE123"
    assert leg.action == "BUY"
    assert leg.quantity == 50
    assert leg.leg_role == "short_put"
    assert leg.notes == "Hedge leg"

    with pytest.raises(FrozenInstanceError):
        leg.quantity = 100


def test_signal_event_model():
    """Test SignalEvent model initialization and immutability."""
    event = SignalEvent(
        event_type="REGIME_CHANGE",
        severity="INFO",
        description="Regime changed to bullish",
        payload={"vix": 12.5},
    )
    assert event.event_type == "REGIME_CHANGE"
    assert event.severity == "INFO"
    assert event.description == "Regime changed to bullish"
    assert event.payload == {"vix": 12.5}

    with pytest.raises(FrozenInstanceError):
        event.severity = "WARN"


def test_approved_action_model():
    """Test ApprovedAction model initialization and immutability."""
    action = ApprovedAction(
        action_type="ROLL_OVER",
        legs_to_close=["short_put"],
        legs_to_open=[
            LegSpec(
                instrument_key="NSE_EQ|INE456",
                action="SELL",
                quantity=100,
                leg_role="new_short_put",
            )
        ],
        rationale="Roll DTE 5",
        council_rank=1,
    )
    assert action.action_type == "ROLL_OVER"
    assert action.legs_to_close == ["short_put"]
    assert len(action.legs_to_open) == 1
    assert action.legs_to_open[0].leg_role == "new_short_put"
    assert action.rationale == "Roll DTE 5"
    assert action.council_rank == 1

    with pytest.raises(FrozenInstanceError):
        action.rationale = "New rationale"


def test_approved_action_empty():
    """Test ApprovedAction with empty lists."""
    action = ApprovedAction(
        action_type="NO_OP",
        legs_to_close=[],
        legs_to_open=[],
        rationale="Do nothing",
        council_rank=2,
    )
    assert action.legs_to_close == []
    assert action.legs_to_open == []
