"""Unit tests for PPOverlayV1 backbone strategy.

All tests are offline — no network calls, no DB.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import PaperPosition
from src.strategy.pp_overlay_v1 import PPOverlayV1
from src.strategy.protocol import ApprovedAction, SignalEvent

_STRATEGY = "paper_protective_put_v1"
_OTHER_STRATEGY = "paper_other_v1"


def _make_put_leg(
    ltp: str,
    delta: str,
    bid: str | None = None,
    ask: str | None = None,
    strike: str = "23000",
    iv: str = "15.0",
) -> OptionLeg:
    """Build a minimal PE OptionLeg."""
    bid_val = Decimal(bid) if bid is not None else Decimal(ltp)
    ask_val = Decimal(ask) if ask is not None else Decimal(ltp)
    return OptionLeg(
        ltp=Decimal(ltp),
        bid=bid_val,
        ask=ask_val,
        oi=1000,
        volume=500,
        delta=Decimal(delta),
        gamma=Decimal("0.001"),
        theta=Decimal("-5"),
        vega=Decimal("10"),
        iv=Decimal(iv),
        strike=Decimal(strike),
    )


def _make_chain(
    ltp: str,
    delta: str,
    bid: str | None = None,
    ask: str | None = None,
    strike: str = "23000",
) -> OptionChain:
    """Build a one-strike OptionChain with the given PE leg."""
    pe = _make_put_leg(ltp=ltp, delta=delta, bid=bid, ask=ask, strike=strike)
    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={Decimal(strike): OptionChainStrike(pe=pe)},
    )


def _make_empty_chain() -> OptionChain:
    """Build a chain with no strikes."""
    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={},
    )


def _make_position(
    instrument_key: str = "NSE_FO|NIFTY23000PE",
    avg_cost: str = "80",
    net_qty: int = 65,  # long protective put
    leg_role: str = "protective_put",
    strategy_name: str = _STRATEGY,
    entry_date: date | None = None,
) -> PaperPosition:
    """Build a PaperPosition for a long-put leg."""
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal(avg_cost),
        avg_sell_price=Decimal("0"),
        instrument_key=instrument_key,
        entry_date=entry_date,
    )


def _expiry_key(dte: int) -> str:
    """Build an instrument key whose embedded expiry yields ``dte`` from today."""
    expiry = date.today() + timedelta(days=dte)
    date_str = expiry.strftime("%d%b%Y").upper()
    return f"NSE_FO|NIFTY{date_str}PE"


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def test_no_positions_returns_empty() -> None:
    strategy = PPOverlayV1()
    result = _run(strategy.check_signals(_make_empty_chain(), []))
    assert result == []


def test_filters_out_other_strategy() -> None:
    strategy = PPOverlayV1()
    pos = _make_position(strategy_name=_OTHER_STRATEGY)
    result = _run(strategy.check_signals(_make_chain("40", "-0.20"), [pos]))
    assert result == []


def test_short_position_ignored() -> None:
    strategy = PPOverlayV1()
    pos = _make_position(net_qty=-65)
    result = _run(strategy.check_signals(_make_chain("40", "-0.20"), [pos]))
    assert result == []


def test_crash_monetize_fires_delta() -> None:
    strategy = PPOverlayV1()
    chain = _make_chain(ltp="400", delta="-0.85")
    pos = _make_position(avg_cost="80")
    events = _run(strategy.check_signals(chain, [pos]))
    assert len(events) == 1
    assert events[0].event_type == "CRASH_MONETIZE"
    assert events[0].severity == "ACTION"
    assert events[0].payload["valid_actions"] == ["MONETIZE_PP"]
    assert events[0].payload["auto_execute"] is True
    assert events[0].payload["auto_action"] == "MONETIZE_PP"


def test_crash_monetize_fires_value() -> None:
    strategy = PPOverlayV1()
    chain = _make_chain(ltp="405", delta="-0.50")  # 405/80 > 5x
    pos = _make_position(avg_cost="80")
    events = _run(strategy.check_signals(chain, [pos]))
    assert len(events) == 1
    assert events[0].event_type == "CRASH_MONETIZE"
    assert events[0].severity == "ACTION"
    assert events[0].payload["valid_actions"] == ["MONETIZE_PP"]


def test_roll_eligible_fires_at_dte_4() -> None:
    strategy = PPOverlayV1()
    key = _expiry_key(dte=4)
    pos = _make_position(instrument_key=key)
    events = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    assert len(events) == 1
    assert events[0].event_type == "ROLL_ELIGIBLE"
    assert events[0].severity == "ACTION"
    assert events[0].payload["valid_actions"] == ["ROLL_PP"]
    assert events[0].payload["auto_execute"] is True
    assert events[0].payload["auto_action"] == "ROLL_PP"


def test_apply_action_monetize_pp() -> None:
    mock_store = MagicMock()
    mock_notifier = AsyncMock()
    strategy = PPOverlayV1(store=mock_store, notifier=mock_notifier)
    strategy._check_reentry = AsyncMock()

    # Using DTE=15
    key = _expiry_key(dte=15)
    pos = _make_position(instrument_key=key)
    action = ApprovedAction(
        action_type="MONETIZE_PP",
        legs_to_close=["protective_put"],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    result = _run(strategy.apply_action([pos], action))
    assert len(result) == 0
    strategy._check_reentry.assert_awaited_once()
    mock_notifier.send_notification.assert_called_once()
    assert "💰 <b>PP: MONETIZE_PP</b>" in mock_notifier.send_notification.call_args[0][0]


def test_apply_action_roll_pp() -> None:
    mock_store = MagicMock()
    mock_notifier = AsyncMock()
    strategy = PPOverlayV1(store=mock_store, notifier=mock_notifier)
    strategy._check_reentry = AsyncMock()

    pos = _make_position()
    action = ApprovedAction(
        action_type="ROLL_PP",
        legs_to_close=["protective_put"],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    result = _run(strategy.apply_action([pos], action))
    assert len(result) == 0
    # Rolling shouldn't trigger check_reentry
    strategy._check_reentry.assert_not_called()
    mock_notifier.send_notification.assert_called_once()
    assert "🔄 <b>PP: ROLL_PP</b>" in mock_notifier.send_notification.call_args[0][0]


def test_apply_action_invalid_raises() -> None:
    strategy = PPOverlayV1()
    pos = _make_position()
    action = ApprovedAction(
        action_type="CLOSE_FULL",
        legs_to_close=[],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    with pytest.raises(ValueError, match="MONETIZE_PP and ROLL_PP"):
        _run(strategy.apply_action([pos], action))


def test_describe_context() -> None:
    strategy = PPOverlayV1()
    chain = _make_chain(ltp="40", delta="-0.20")
    pos = _make_position(avg_cost="80")
    event = SignalEvent(
        event_type="CRASH_MONETIZE",
        severity="ACTION",
        description="test",
        payload={},
    )
    ctx = strategy.describe_context(event, chain, [pos])
    assert "paper_protective_put_v1" in ctx
    assert "CRASH_MONETIZE" in ctx
