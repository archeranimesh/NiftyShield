"""Unit tests for CollarOverlayV1 backbone strategy.

All tests are offline — no network calls, no DB.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import PaperPosition
from src.strategy.collar_overlay_v1 import CollarOverlayV1
from src.strategy.protocol import ApprovedAction, SignalEvent

_STRATEGY = "paper_collar_v1"
_OTHER_STRATEGY = "paper_other_v1"


def _make_call_leg(
    ltp: str,
    delta: str,
    strike: str = "23000",
    iv: str = "15.0",
) -> OptionLeg:
    """Build a minimal CE OptionLeg."""
    return OptionLeg(
        ltp=Decimal(ltp),
        bid=Decimal(ltp),
        ask=Decimal(ltp),
        oi=1000,
        volume=500,
        delta=Decimal(delta),
        gamma=Decimal("0.001"),
        theta=Decimal("-5"),
        vega=Decimal("10"),
        iv=Decimal(iv),
        strike=Decimal(strike),
    )


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
    call_ltp: str,
    call_delta: str,
    put_ltp: str,
    put_delta: str,
    put_bid: str | None = None,
    put_ask: str | None = None,
    call_strike: str = "24500",
    put_strike: str = "21500",
) -> OptionChain:
    """Build a two-strike OptionChain with call and put legs."""
    ce = _make_call_leg(ltp=call_ltp, delta=call_delta, strike=call_strike)
    pe = _make_put_leg(ltp=put_ltp, delta=put_delta, bid=put_bid, ask=put_ask, strike=put_strike)
    return OptionChain(
        underlying_spot=Decimal("23000"),
        expiry=date(2026, 6, 26),
        strikes={
            Decimal(call_strike): OptionChainStrike(ce=ce),
            Decimal(put_strike): OptionChainStrike(pe=pe),
        },
    )


def _make_empty_chain() -> OptionChain:
    """Build a chain with no strikes."""
    return OptionChain(
        underlying_spot=Decimal("23000"),
        expiry=date(2026, 6, 26),
        strikes={},
    )


def _make_short_call_position(
    instrument_key: str = "NSE_FO|NIFTY24500CE",
    avg_sell_price: str = "80",
    net_qty: int = -65,
    leg_role: str = "collar_short_call",
    strategy_name: str = _STRATEGY,
) -> PaperPosition:
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal(avg_sell_price),
        instrument_key=instrument_key,
        entry_date=None,
    )


def _make_long_put_position(
    instrument_key: str = "NSE_FO|NIFTY21500PE",
    avg_cost: str = "50",
    net_qty: int = 65,
    leg_role: str = "collar_long_put",
    strategy_name: str = _STRATEGY,
) -> PaperPosition:
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal(avg_cost),
        avg_sell_price=Decimal("0"),
        instrument_key=instrument_key,
        entry_date=None,
    )


def _expiry_key(dte: int, option_type: str = "CE") -> str:
    expiry = date.today() + timedelta(days=dte)
    date_str = expiry.strftime("%d%b%Y").upper()
    return f"NSE_FO|NIFTY{date_str}{option_type}"


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def test_no_positions_returns_empty() -> None:
    strategy = CollarOverlayV1()
    result = _run(strategy.check_signals(_make_empty_chain(), []))
    assert result == []


def test_filters_out_other_strategy() -> None:
    strategy = CollarOverlayV1()
    pos1 = _make_short_call_position(strategy_name=_OTHER_STRATEGY)
    pos2 = _make_long_put_position(strategy_name=_OTHER_STRATEGY)
    result = _run(strategy.check_signals(_make_chain("20", "0.20", "20", "-0.20"), [pos1, pos2]))
    assert result == []


def test_decay_fires_for_short_call() -> None:
    strategy = CollarOverlayV1()
    # mark 19 <= 25% of 80 (20)
    chain = _make_chain("19", "0.15", "30", "-0.10")
    pos1 = _make_short_call_position(avg_sell_price="80")
    pos2 = _make_long_put_position(avg_cost="50")
    events = _run(strategy.check_signals(chain, [pos1, pos2]))
    assert any(e.event_type == "COLLAR_CALL_DECAY" and e.severity == "ACTION" for e in events)


def test_decay_does_not_fire_above_25_pct() -> None:
    strategy = CollarOverlayV1()
    # mark 21 > 25% of 80 (20)
    chain = _make_chain("21", "0.15", "30", "-0.10")
    pos1 = _make_short_call_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos1]))
    assert not any(e.event_type == "COLLAR_CALL_DECAY" for e in events)


def test_residual_value_fires_decay() -> None:
    strategy = CollarOverlayV1()
    # mark 2 <= 3
    chain = _make_chain("2.5", "0.05", "30", "-0.10")
    pos1 = _make_short_call_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos1]))
    assert any(e.event_type == "COLLAR_CALL_DECAY" and e.severity == "ACTION" for e in events)


def test_collar_call_warn_fires() -> None:
    strategy = CollarOverlayV1()
    chain = _make_chain("100", "0.56", "30", "-0.10")
    pos1 = _make_short_call_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos1]))
    assert any(e.event_type == "COLLAR_CALL_WARN" and e.severity == "WARN" for e in events)
    assert not any(e.event_type == "COLLAR_CALL_WARN" and e.severity == "ACTION" for e in events)


def test_collar_put_crash_fires() -> None:
    strategy = CollarOverlayV1()
    chain = _make_chain(
        "10", "0.10", "260", "-0.85", put_bid="255", put_ask="265"
    )  # put value 260 >= 5x of 50
    pos1 = _make_short_call_position()
    pos2 = _make_long_put_position(avg_cost="50")
    events = _run(strategy.check_signals(chain, [pos1, pos2]))
    assert any(e.event_type == "COLLAR_PUT_CRASH" and e.severity == "ACTION" for e in events)


def test_dte_forced_fires_for_short_call() -> None:
    strategy = CollarOverlayV1()
    chain = _make_chain("100", "0.55", "30", "-0.10")
    key = _expiry_key(dte=4, option_type="CE")
    pos1 = _make_short_call_position(instrument_key=key, avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos1]))
    assert any(e.event_type == "DTE_FORCED" and e.severity == "ACTION" for e in events)


def test_apply_action_valid() -> None:
    strategy = CollarOverlayV1()
    pos1 = _make_short_call_position()
    pos2 = _make_long_put_position()

    action1 = ApprovedAction(
        action_type="CLOSE_CALL_ONLY",
        legs_to_close=["collar_short_call"],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    result1 = _run(strategy.apply_action([pos1, pos2], action1))
    assert len(result1) == 1
    assert result1[0].leg_role == "collar_long_put"

    action2 = ApprovedAction(
        action_type="CLOSE_ALL_OVERLAY",
        legs_to_close=["collar_short_call", "collar_long_put"],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    result2 = _run(strategy.apply_action([pos1, pos2], action2))
    assert len(result2) == 0


def test_apply_action_invalid_raises() -> None:
    strategy = CollarOverlayV1()
    pos1 = _make_short_call_position()
    action = ApprovedAction(
        action_type="ROLL_COLLAR",
        legs_to_close=[],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    with pytest.raises(ValueError, match="CollarOverlayV1 only accepts actions"):
        _run(strategy.apply_action([pos1], action))


def test_describe_context() -> None:
    strategy = CollarOverlayV1()
    chain = _make_chain("40", "0.20", "20", "-0.10")
    pos1 = _make_short_call_position()
    pos2 = _make_long_put_position()
    event = SignalEvent(
        event_type="COLLAR_CALL_DECAY",
        severity="ACTION",
        description="test",
        payload={},
    )
    ctx = strategy.describe_context(event, chain, [pos1, pos2])
    assert "paper_collar_v1" in ctx
    assert "COLLAR_CALL_DECAY" in ctx
