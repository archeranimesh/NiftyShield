"""Unit tests for CollarOverlayV1 backbone strategy.

All tests are offline — no network calls, no DB.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import PaperPosition
from src.strategy.collar_overlay_v1 import CollarOverlayV1
from src.strategy.protocol import ApprovedAction, LegClose, SignalEvent

_STRATEGY = "paper_collar_v1"
_OTHER_STRATEGY = "paper_other_v1"


def _make_call_leg(
    ltp: str,
    delta: str,
    strike: str = "24500",
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
    strike: str = "21500",
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
    leg_role: str = "overlay_collar_call",
    strategy_name: str = _STRATEGY,
    entry_date: date | None = None,
) -> PaperPosition:
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal(avg_sell_price),
        instrument_key=instrument_key,
        entry_date=entry_date or date.today(),
    )


def _make_long_put_position(
    instrument_key: str = "NSE_FO|NIFTY21500PE",
    avg_cost: str = "50",
    net_qty: int = 65,
    leg_role: str = "overlay_collar_put",
    strategy_name: str = _STRATEGY,
    entry_date: date | None = None,
) -> PaperPosition:
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal(avg_cost),
        avg_sell_price=Decimal("0"),
        instrument_key=instrument_key,
        entry_date=entry_date or date.today(),
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
    result = _run(strategy.check_signals(_make_chain("20", "0.20", "20", "-0.20"), [pos1]))
    assert result == []


def test_profit_target_fires_for_short_call() -> None:
    strategy = CollarOverlayV1()
    # profit target: ltp <= 30% of entry 80 (24) AND entry >= 15
    chain = _make_chain("24", "0.15", "30", "-0.10")
    pos1 = _make_short_call_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos1]))
    assert any(
        e.event_type == "PROFIT_TARGET"
        and e.severity == "ACTION"
        and e.payload.get("auto_execute") is True
        for e in events
    )


def test_loss_stop_fires_for_short_call() -> None:
    strategy = CollarOverlayV1()
    # loss stop: ltp >= 2.5x of 80 (200)
    chain = _make_chain("200", "0.40", "30", "-0.10")
    pos1 = _make_short_call_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos1]))
    assert any(
        e.event_type == "LOSS_STOP"
        and e.severity == "ACTION"
        and e.payload.get("auto_execute") is True
        for e in events
    )


def test_delta_stop_fires_for_short_call() -> None:
    strategy = CollarOverlayV1()
    # delta stop: delta >= 0.55
    chain = _make_chain("100", "0.56", "30", "-0.10")
    pos1 = _make_short_call_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos1]))
    assert any(
        e.event_type == "DELTA_STOP"
        and e.severity == "ACTION"
        and e.payload.get("auto_execute") is True
        for e in events
    )


def test_delta_warn_fires_for_short_call() -> None:
    strategy = CollarOverlayV1()
    # delta warn: delta >= 0.45 but < 0.55
    chain = _make_chain("100", "0.48", "30", "-0.10")
    pos1 = _make_short_call_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos1]))
    assert any(
        e.event_type == "DELTA_WARN" and e.severity == "WARN" and "auto_execute" not in e.payload
        for e in events
    )


def test_dte_close_fires_for_short_call() -> None:
    # EC-5: TIME_STOP (days_held >= 21) is gone from evaluate_cc — collar short call
    # shares evaluate_cc with CC, so it now auto-closes at dte <= 5 regardless of
    # days_held, and no longer at days_held >= 21 alone.
    strategy = CollarOverlayV1()
    chain = _make_chain("50", "0.20", "30", "-0.10")
    key = _expiry_key(dte=5, option_type="CE")
    pos1 = _make_short_call_position(
        instrument_key=key, avg_sell_price="80", entry_date=date.today() - timedelta(days=21)
    )
    events = _run(strategy.check_signals(chain, [pos1]))
    assert any(
        e.event_type == "DTE_REVIEW"
        and e.severity == "ACTION"
        and e.payload.get("auto_execute") is True
        for e in events
    )
    assert not any(e.event_type == "TIME_STOP" for e in events)


def test_high_days_held_alone_does_not_close_short_call_when_dte_far_out() -> None:
    # Regression for the event-68 shape on the collar short call leg.
    strategy = CollarOverlayV1()
    chain = _make_chain("50", "0.20", "30", "-0.10")
    key = _expiry_key(dte=38, option_type="CE")
    pos1 = _make_short_call_position(
        instrument_key=key, avg_sell_price="80", entry_date=date.today() - timedelta(days=21)
    )
    events = _run(strategy.check_signals(chain, [pos1]))
    assert events == []


def test_apply_action_valid() -> None:
    strategy = CollarOverlayV1()
    pos1 = _make_short_call_position()
    pos2 = _make_long_put_position()

    action = ApprovedAction(
        action_type="CLOSE_COLLAR",
        legs_to_close=[
            LegClose(leg_role="overlay_collar_call"),
            LegClose(leg_role="overlay_collar_put"),
        ],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    result = _run(strategy.apply_action([pos1, pos2], action))
    assert len(result) == 0


def test_apply_action_invalid_raises() -> None:
    strategy = CollarOverlayV1()
    pos1 = _make_short_call_position()
    action = ApprovedAction(
        action_type="CLOSE_CALL_ONLY",
        legs_to_close=[],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    with pytest.raises(ValueError, match="CollarOverlayV1 only accepts CLOSE_COLLAR"):
        _run(strategy.apply_action([pos1], action))


def test_describe_context() -> None:
    strategy = CollarOverlayV1()
    chain = _make_chain("40", "0.20", "20", "-0.10")
    pos1 = _make_short_call_position()
    pos2 = _make_long_put_position()
    event = SignalEvent(
        event_type="PROFIT_TARGET",
        severity="ACTION",
        description="test",
        payload={},
    )
    ctx = strategy.describe_context(event, chain, [pos1, pos2])
    assert "paper_collar_v1" in ctx
    assert "PROFIT_TARGET" in ctx


def test_apply_action_records_both_legs_atomically() -> None:
    """CLOSE_COLLAR must write trades using record_trades."""
    mock_store = MagicMock()
    strategy = CollarOverlayV1(store=mock_store)

    call_pos = _make_short_call_position(avg_sell_price="80")
    put_pos = _make_long_put_position(avg_cost="50")
    action = ApprovedAction(
        action_type="CLOSE_COLLAR",
        legs_to_close=[
            LegClose(leg_role="overlay_collar_call"),
            LegClose(leg_role="overlay_collar_put"),
        ],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"mark": "30.0"},
    )
    result = _run(strategy.apply_action([call_pos, put_pos], action))

    assert result == []
    mock_store.record_trades.assert_called_once()
    trades = mock_store.record_trades.call_args[0][0]
    assert len(trades) == 2
    assert any(
        t.action.value == "BUY"
        and t.leg_role == "overlay_collar_call"
        and t.price == Decimal("30.0")
        for t in trades
    )
    assert any(
        t.action.value == "SELL"
        and t.leg_role == "overlay_collar_put"
        and t.price == Decimal("50.0")
        for t in trades
    )


def test_apply_action_handles_missing_put_leg_gracefully() -> None:
    """If put leg is missing, only record the call close and do not raise."""
    mock_store = MagicMock()
    strategy = CollarOverlayV1(store=mock_store)

    call_pos = _make_short_call_position(avg_sell_price="80")
    action = ApprovedAction(
        action_type="CLOSE_COLLAR",
        legs_to_close=[LegClose(leg_role="overlay_collar_call")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"mark": "30.0"},
    )
    result = _run(strategy.apply_action([call_pos], action))

    assert result == []
    mock_store.record_trades.assert_called_once()
    trades = mock_store.record_trades.call_args[0][0]
    assert len(trades) == 1
    assert trades[0].action.value == "BUY"
    assert trades[0].leg_role == "overlay_collar_call"


def test_apply_action_no_store_does_not_raise() -> None:
    strategy = CollarOverlayV1(store=None)
    call_pos = _make_short_call_position()
    action = ApprovedAction(
        action_type="CLOSE_COLLAR",
        legs_to_close=[LegClose(leg_role="overlay_collar_call")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    result = _run(strategy.apply_action([call_pos], action))
    assert result == []


def test_apply_action_calls_check_reentry_for_eligible_signals() -> None:
    from unittest.mock import AsyncMock, patch

    mock_store = MagicMock()
    strategy = CollarOverlayV1(store=mock_store)

    call_pos = _make_short_call_position(avg_sell_price="80")
    action = ApprovedAction(
        action_type="CLOSE_COLLAR",
        legs_to_close=[LegClose(leg_role="overlay_collar_call")],
        legs_to_open=[],
        rationale="profit target",
        council_rank=1,
        metadata={"triggering_signal": "PROFIT_TARGET", "mark": "24"},
    )

    with patch.object(strategy, "_check_reentry", new=AsyncMock()) as mock_reentry:
        _run(strategy.apply_action([call_pos], action))
        mock_reentry.assert_awaited_once()


def test_reentry_check_called_for_loss_stop() -> None:
    """Collar3a: LOSS_STOP is ACTION-severity and dispatches CLOSE_COLLAR — must
    trigger re-entry, same as PROFIT_TARGET/TIME_STOP/DTE_REVIEW."""
    from unittest.mock import AsyncMock, patch

    mock_store = MagicMock()
    strategy = CollarOverlayV1(store=mock_store)

    call_pos = _make_short_call_position(avg_sell_price="80")
    action = ApprovedAction(
        action_type="CLOSE_COLLAR",
        legs_to_close=[LegClose(leg_role="overlay_collar_call")],
        legs_to_open=[],
        rationale="loss stop",
        council_rank=1,
        metadata={"triggering_signal": "LOSS_STOP", "mark": "200"},
    )

    with patch.object(strategy, "_check_reentry", new=AsyncMock()) as mock_reentry:
        _run(strategy.apply_action([call_pos], action))
        mock_reentry.assert_awaited_once()


def test_reentry_check_called_for_delta_stop() -> None:
    """Collar3a: DELTA_STOP is ACTION-severity and dispatches CLOSE_COLLAR — must
    trigger re-entry, mirroring CC3's shipped trigger set for CCOverlayV1."""
    from unittest.mock import AsyncMock, patch

    mock_store = MagicMock()
    strategy = CollarOverlayV1(store=mock_store)

    call_pos = _make_short_call_position(avg_sell_price="80")
    action = ApprovedAction(
        action_type="CLOSE_COLLAR",
        legs_to_close=[LegClose(leg_role="overlay_collar_call")],
        legs_to_open=[],
        rationale="delta stop",
        council_rank=1,
        metadata={"triggering_signal": "DELTA_STOP", "mark": "60"},
    )

    with patch.object(strategy, "_check_reentry", new=AsyncMock()) as mock_reentry:
        _run(strategy.apply_action([call_pos], action))
        mock_reentry.assert_awaited_once()


def test_reentry_check_not_called_for_below_floor() -> None:
    """Regression guard: BELOW_FLOOR is INFO-severity in evaluate_cc() and never
    dispatches CLOSE_COLLAR, so there is no close event to re-enter after."""
    from unittest.mock import AsyncMock, patch

    mock_store = MagicMock()
    strategy = CollarOverlayV1(store=mock_store)

    call_pos = _make_short_call_position(avg_sell_price="80")
    action = ApprovedAction(
        action_type="CLOSE_COLLAR",
        legs_to_close=[LegClose(leg_role="overlay_collar_call")],
        legs_to_open=[],
        rationale="below floor",
        council_rank=1,
        metadata={"triggering_signal": "BELOW_FLOOR", "mark": "40"},
    )

    with patch.object(strategy, "_check_reentry", new=AsyncMock()) as mock_reentry:
        _run(strategy.apply_action([call_pos], action))
        mock_reentry.assert_not_awaited()


def test_reentry_check_not_called_for_delta_warn() -> None:
    """Regression guard: WARN-severity signals never close the position, so no
    re-entry check should fire for them."""
    from unittest.mock import AsyncMock, patch

    mock_store = MagicMock()
    strategy = CollarOverlayV1(store=mock_store)

    call_pos = _make_short_call_position(avg_sell_price="80")
    action = ApprovedAction(
        action_type="CLOSE_COLLAR",
        legs_to_close=[LegClose(leg_role="overlay_collar_call")],
        legs_to_open=[],
        rationale="delta warn",
        council_rank=1,
        metadata={"triggering_signal": "DELTA_WARN", "mark": "50"},
    )

    with patch.object(strategy, "_check_reentry", new=AsyncMock()) as mock_reentry:
        _run(strategy.apply_action([call_pos], action))
        mock_reentry.assert_not_awaited()


def test_reentry_gates_unchanged_regardless_of_triggering_signal() -> None:
    """The ReEntryMixin's own DTE/IVR/open-position gate logic doesn't change —
    only which triggering signals invoke _check_reentry. Verify _check_reentry
    is invoked with the same argument shape for both an old and a newly-added
    trigger."""
    from unittest.mock import AsyncMock, patch

    mock_store = MagicMock()
    strategy = CollarOverlayV1(store=mock_store)

    fixed_today = date(2026, 8, 3)
    for signal in ("PROFIT_TARGET", "LOSS_STOP"):
        call_pos = _make_short_call_position(avg_sell_price="80")
        action = ApprovedAction(
            action_type="CLOSE_COLLAR",
            legs_to_close=[LegClose(leg_role="overlay_collar_call")],
            legs_to_open=[],
            rationale=signal,
            council_rank=1,
            metadata={"triggering_signal": signal, "mark": "30"},
        )
        with (
            patch.object(strategy, "_check_reentry", new=AsyncMock()) as mock_reentry,
            patch("src.strategy.collar_overlay_v1.market_today", return_value=fixed_today),
        ):
            _run(strategy.apply_action([call_pos], action))
            mock_reentry.assert_awaited_once_with(
                expiry=strategy._parse_expiry(call_pos.instrument_key),
                today=fixed_today,
                instrument_key=call_pos.instrument_key,
                trade_id=0,
            )


def test_close_collar_all_atomicity_unchanged() -> None:
    """Regression guard: this story only widens the re-entry trigger set — the
    already-correct two-leg atomic close (both legs written via a single
    store.record_trades([...]) call) and missing-put-leg-warning behavior must
    not be disturbed."""
    mock_store = MagicMock()
    strategy = CollarOverlayV1(store=mock_store)

    call_pos = _make_short_call_position(avg_sell_price="80")
    put_pos = _make_long_put_position(avg_cost="40")
    action = ApprovedAction(
        action_type="CLOSE_COLLAR",
        legs_to_close=[
            LegClose(leg_role="overlay_collar_call"),
            LegClose(leg_role="overlay_collar_put"),
        ],
        legs_to_open=[],
        rationale="loss stop",
        council_rank=1,
        metadata={"triggering_signal": "LOSS_STOP", "mark": "200"},
    )

    result = _run(strategy.apply_action([call_pos, put_pos], action))

    assert result == []
    mock_store.record_trades.assert_called_once()
    trades = mock_store.record_trades.call_args[0][0]
    assert len(trades) == 2


def test_apply_action_roll_overlap_closes_only_matched_instrument() -> None:
    """PG-4e: two short-call positions share overlay_collar_call during a roll
    overlap (old expiring contract not yet closed, new contract already open).

    When the ApprovedAction's LegClose carries the specific instrument_key
    (as the old contract being closed), apply_action must close only that
    instrument and leave the other (still-open, different instrument_key)
    position untouched in the returned list — not drop both under a blind
    leg_role-only match.
    """
    mock_store = MagicMock()
    strategy = CollarOverlayV1(store=mock_store)

    old_call = _make_short_call_position(
        instrument_key="NSE_FO|NIFTY29MAY2026CE", avg_sell_price="80"
    )
    new_call = _make_short_call_position(
        instrument_key="NSE_FO|NIFTY26JUN2026CE", avg_sell_price="90"
    )

    action = ApprovedAction(
        action_type="CLOSE_COLLAR",
        legs_to_close=[
            LegClose(leg_role="overlay_collar_call", instrument_key=old_call.instrument_key)
        ],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"mark": "30.0"},
    )

    result = _run(strategy.apply_action([old_call, new_call], action))

    # Only the old (matched) instrument was closed; the new one survives.
    assert result == [new_call]
    mock_store.record_trades.assert_called_once()
    trades = mock_store.record_trades.call_args[0][0]
    assert len(trades) == 1
    assert trades[0].instrument_key == old_call.instrument_key
