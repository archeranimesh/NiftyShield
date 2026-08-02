"""Unit tests for CCOverlayV1 backbone strategy.

All tests are offline — no network calls, no DB.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import PaperPosition
from src.strategy.cc_overlay_v1 import CCOverlayV1
from src.strategy.protocol import ApprovedAction, LegClose, SignalEvent

_STRATEGY = "paper_covered_call_v1"
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


def _make_chain(ltp: str, delta: str, strike: str = "23000") -> OptionChain:
    """Build a one-strike OptionChain with the given CE leg."""
    ce = _make_call_leg(ltp=ltp, delta=delta, strike=strike)
    return OptionChain(
        underlying_spot=Decimal("22000"),
        expiry=date(2026, 6, 26),
        strikes={Decimal(strike): OptionChainStrike(ce=ce)},
    )


def _make_empty_chain() -> OptionChain:
    """Build a chain with no strikes."""
    return OptionChain(
        underlying_spot=Decimal("22000"),
        expiry=date(2026, 6, 26),
        strikes={},
    )


def _make_position(
    instrument_key: str = "NSE_FO|NIFTY23000CE",
    avg_sell_price: str = "80",
    net_qty: int = -65,
    leg_role: str = "short_call",
    strategy_name: str = _STRATEGY,
    entry_date: date | None = None,
) -> PaperPosition:
    """Build a PaperPosition for a short-call leg."""
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal(avg_sell_price),
        instrument_key=instrument_key,
        entry_date=entry_date,
    )


def _expiry_key(dte: int) -> str:
    """Build an instrument key whose embedded expiry yields ``dte`` from today."""
    expiry = date.today() + timedelta(days=dte)
    date_str = expiry.strftime("%d%b%Y").upper()
    return f"NSE_FO|NIFTY{date_str}CE"


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def test_no_positions_returns_empty() -> None:
    strategy = CCOverlayV1()
    result = _run(strategy.check_signals(_make_empty_chain(), []))
    assert result == []


def test_filters_out_other_strategy() -> None:
    strategy = CCOverlayV1()
    pos = _make_position(strategy_name=_OTHER_STRATEGY)
    result = _run(strategy.check_signals(_make_chain("40", "0.20"), [pos]))
    assert result == []


def test_long_position_ignored() -> None:
    strategy = CCOverlayV1()
    pos = _make_position(net_qty=65)
    result = _run(strategy.check_signals(_make_chain("40", "0.20"), [pos]))
    assert result == []


def test_profit_target_fires_above_floor() -> None:
    strategy = CCOverlayV1()
    chain = _make_chain(ltp="24.0", delta="0.20")  # 24.0/80 = 30%
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    assert any(e.event_type == "PROFIT_TARGET" and e.severity == "ACTION" for e in events)


def test_below_floor_prevents_profit_target() -> None:
    strategy = CCOverlayV1()
    chain = _make_chain(ltp="3.0", delta="0.20")  # 3/10 = 30% (under 30%)
    pos = _make_position(avg_sell_price="10")  # under 12 floor
    events = _run(strategy.check_signals(chain, [pos]))
    event_types = {e.event_type for e in events}
    assert "BELOW_FLOOR" in event_types
    assert "PROFIT_TARGET" not in event_types


def test_delta_stop_fires_at_0_56() -> None:
    strategy = CCOverlayV1()
    chain = _make_chain(ltp="80", delta="0.56")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    assert any(e.event_type == "DELTA_STOP" and e.severity == "ACTION" for e in events)


def test_loss_stop_fires_at_2_5x() -> None:
    strategy = CCOverlayV1()
    chain = _make_chain(ltp="201", delta="0.30")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    assert any(e.event_type == "LOSS_STOP" and e.severity == "ACTION" for e in events)


def test_dte_close_fires_at_5_dte() -> None:
    # EC-5: TIME_STOP (days_held >= 21) no longer exists in evaluate_cc — replaced
    # by a single ACTION-severity DTE_REVIEW close at dte <= 5, regardless of days_held.
    strategy = CCOverlayV1()
    key = _expiry_key(dte=5)
    chain = _make_chain(ltp="80", delta="0.20", strike="23000")
    entry_date = date.today() - timedelta(days=21)
    pos = _make_position(instrument_key=key, avg_sell_price="80", entry_date=entry_date)
    events = _run(strategy.check_signals(chain, [pos]))
    assert any(e.event_type == "DTE_REVIEW" and e.severity == "ACTION" for e in events)
    assert not any(e.event_type == "TIME_STOP" for e in events)


def test_high_days_held_alone_does_not_close_when_dte_far_out() -> None:
    # Regression for the event-68 shape: high days_held, high dte -> no close.
    strategy = CCOverlayV1()
    key = _expiry_key(dte=38)
    chain = _make_chain(ltp="80", delta="0.20", strike="23000")
    entry_date = date.today() - timedelta(days=21)
    pos = _make_position(instrument_key=key, avg_sell_price="80", entry_date=entry_date)
    events = _run(strategy.check_signals(chain, [pos]))
    assert events == []


def test_check_signals_with_entry_date_none() -> None:
    strategy = CCOverlayV1()
    chain = _make_chain(ltp="80", delta="0.20")
    pos = _make_position(avg_sell_price="80", entry_date=None)
    events = _run(strategy.check_signals(chain, [pos]))
    # No crash, should evaluate as days_held = 0
    assert not any(e.event_type == "TIME_STOP" for e in events)


def test_missing_strike_still_evaluates_premium() -> None:
    strategy = CCOverlayV1()
    pos = _make_position(avg_sell_price="80")
    # Empty chain so lookup fails, but let's mock position key with DTE so DTE check is fine
    events = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    assert (
        events == []
    )  # Not enough info for premium stop/delta, and no DTE review (since empty chain expiry is not matched)


def test_apply_action_close_cc() -> None:
    strategy = CCOverlayV1()
    pos = _make_position()
    action = ApprovedAction(
        action_type="CLOSE_CC",
        legs_to_close=[LegClose(leg_role="short_call")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    result = _run(strategy.apply_action([pos], action))
    assert len(result) == 0


def test_apply_action_invalid_raises() -> None:
    strategy = CCOverlayV1()
    pos = _make_position()
    action = ApprovedAction(
        action_type="ADJUST",
        legs_to_close=[],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    with pytest.raises(ValueError, match="CLOSE_CC"):
        _run(strategy.apply_action([pos], action))


def test_check_signals_payload_auto_execute() -> None:
    strategy = CCOverlayV1()

    # PROFIT_TARGET fires
    chain = _make_chain(ltp="24.0", delta="0.20")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    profit_target_event = next(e for e in events if e.event_type == "PROFIT_TARGET")
    assert profit_target_event.payload.get("auto_execute") is True
    assert profit_target_event.payload.get("auto_action") == "CLOSE_CC"
    assert profit_target_event.payload.get("triggering_signal") == "PROFIT_TARGET"

    # DTE_REVIEW close fires (EC-5: replaces TIME_STOP as the days-held/DTE backstop)
    key = _expiry_key(dte=5)
    pos_dte = _make_position(instrument_key=key, avg_sell_price="80")
    chain_dte = _make_chain(ltp="80", delta="0.20")
    events_dte = _run(strategy.check_signals(chain_dte, [pos_dte]))
    dte_review_event = next(e for e in events_dte if e.event_type == "DTE_REVIEW")
    assert dte_review_event.payload.get("auto_execute") is True
    assert dte_review_event.payload.get("auto_action") == "CLOSE_CC"
    assert dte_review_event.payload.get("triggering_signal") == "DTE_REVIEW"

    # DELTA_WARN fires (no auto_execute)
    chain_warn = _make_chain(ltp="80", delta="0.46")
    pos_warn = _make_position(avg_sell_price="80")
    events_warn = _run(strategy.check_signals(chain_warn, [pos_warn]))
    delta_warn_event = next(e for e in events_warn if e.event_type == "DELTA_WARN")
    assert "auto_execute" not in delta_warn_event.payload


def test_apply_action_triggering_signals() -> None:
    # Set up mock notifier and store
    mock_notifier = AsyncMock()
    mock_store = MagicMock()

    strategy = CCOverlayV1(store=mock_store, notifier=mock_notifier)
    pos = _make_position(avg_sell_price="80", leg_role="short_call")

    # Check that check_reentry is mockable on strategy
    strategy._check_reentry = AsyncMock()

    # 1. PROFIT_TARGET trigger -> check_reentry called
    action_pt = ApprovedAction(
        action_type="CLOSE_CC",
        legs_to_close=[LegClose(leg_role="short_call")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"triggering_signal": "PROFIT_TARGET", "mark": "24.0", "delta": "0.20"},
    )
    _run(strategy.apply_action([pos], action_pt))
    strategy._check_reentry.assert_called_once()
    mock_notifier.send_notification.assert_called_once()

    strategy._check_reentry.reset_mock()
    mock_notifier.send_notification.reset_mock()

    # 2. TIME_STOP trigger -> check_reentry called
    action_ts = ApprovedAction(
        action_type="CLOSE_CC",
        legs_to_close=[LegClose(leg_role="short_call")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"triggering_signal": "TIME_STOP", "mark": "80", "delta": "0.20"},
    )
    _run(strategy.apply_action([pos], action_ts))
    strategy._check_reentry.assert_called_once()
    mock_notifier.send_notification.assert_called_once()

    strategy._check_reentry.reset_mock()
    mock_notifier.send_notification.reset_mock()

    # 3. LOSS_STOP trigger -> check_reentry called
    action_ls = ApprovedAction(
        action_type="CLOSE_CC",
        legs_to_close=[LegClose(leg_role="short_call")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"triggering_signal": "LOSS_STOP", "mark": "201", "delta": "0.30"},
    )
    _run(strategy.apply_action([pos], action_ls))
    strategy._check_reentry.assert_called_once()
    mock_notifier.send_notification.assert_called_once()

    strategy._check_reentry.reset_mock()
    mock_notifier.send_notification.reset_mock()

    # 4. DELTA_STOP trigger -> check_reentry called
    action_ds = ApprovedAction(
        action_type="CLOSE_CC",
        legs_to_close=[LegClose(leg_role="short_call")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"triggering_signal": "DELTA_STOP", "mark": "80", "delta": "0.56"},
    )
    _run(strategy.apply_action([pos], action_ds))
    strategy._check_reentry.assert_called_once()
    mock_notifier.send_notification.assert_called_once()

    strategy._check_reentry.reset_mock()
    mock_notifier.send_notification.reset_mock()

    # 5. DTE_REVIEW trigger -> check_reentry called (EC-5: DTE_REVIEW replaces TIME_STOP
    # as the ACTION-severity close signal; the re-entry allow-list must include it or a
    # DTE-close silently skips re-entry evaluation — regression caught in review)
    action_dr = ApprovedAction(
        action_type="CLOSE_CC",
        legs_to_close=[LegClose(leg_role="short_call")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"triggering_signal": "DTE_REVIEW", "mark": "80", "delta": "0.20"},
    )
    _run(strategy.apply_action([pos], action_dr))
    strategy._check_reentry.assert_called_once()
    mock_notifier.send_notification.assert_called_once()


def test_reentry_gates_unchanged_regardless_of_triggering_signal() -> None:
    """Test that check_reentry is called with correct parameters for bad IVR/DTE,
    proving the gate logic itself didn't change even if the trigger signal did."""
    mock_store = MagicMock()
    strategy = CCOverlayV1(store=mock_store, notifier=None)
    pos = _make_position(
        avg_sell_price="80", leg_role="short_call", instrument_key="NSE_FO|NIFTY26JUN2026CE"
    )

    with patch.object(strategy, "_check_reentry", new_callable=AsyncMock) as mock_check:
        action_ls = ApprovedAction(
            action_type="CLOSE_CC",
            legs_to_close=[LegClose(leg_role="short_call")],
            legs_to_open=[],
            rationale="test",
            council_rank=1,
            metadata={"triggering_signal": "LOSS_STOP"},
        )
        _run(strategy.apply_action([pos], action_ls))
        mock_check.assert_called_once_with(
            expiry=date(2026, 6, 26),
            today=date.today(),
            instrument_key="NSE_FO|NIFTY26JUN2026CE",
            trade_id=0,
        )


def test_apply_action_null_dependencies() -> None:
    # notifier = None, store = None -> execute without crash
    strategy = CCOverlayV1(store=None, notifier=None)
    pos = _make_position()
    action = ApprovedAction(
        action_type="CLOSE_CC",
        legs_to_close=[LegClose(leg_role="short_call")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"triggering_signal": "PROFIT_TARGET"},
    )
    # This should run without raising any exceptions
    result = _run(strategy.apply_action([pos], action))
    assert len(result) == 0


def test_describe_context() -> None:
    strategy = CCOverlayV1()
    chain = _make_chain(ltp="38.4", delta="0.20")
    pos = _make_position(avg_sell_price="80")
    event = SignalEvent(
        event_type="PROFIT_TARGET",
        severity="ACTION",
        description="test",
        payload={},
    )
    ctx = strategy.describe_context(event, chain, [pos])
    assert "paper_covered_call_v1" in ctx
    assert "PROFIT_TARGET" in ctx


# ---------------------------------------------------------------------------
# DBI-2: record_close_trade tests
# ---------------------------------------------------------------------------


def test_apply_action_records_closing_trade_to_store() -> None:
    """apply_action(CLOSE_CC) must write a BUY closing trade to the store."""
    mock_store = MagicMock()
    mock_store.record_trade.return_value = True
    strategy = CCOverlayV1(store=mock_store, notifier=None)
    strategy._check_reentry = AsyncMock()

    pos = _make_position(avg_sell_price="80", leg_role="short_call", net_qty=-65)
    action = ApprovedAction(
        action_type="CLOSE_CC",
        legs_to_close=[LegClose(leg_role="short_call")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"mark": "25.0"},
    )
    _run(strategy.apply_action([pos], action))

    mock_store.record_trade.assert_called_once()
    trade = mock_store.record_trade.call_args[0][0]
    assert trade.action.value == "BUY"
    assert trade.quantity == 65
    assert trade.price == Decimal("25.0")
    assert trade.leg_role == "short_call"


def test_apply_action_recording_idempotent_on_duplicate() -> None:
    """store.record_trade returning False (duplicate) must not raise."""
    mock_store = MagicMock()
    mock_store.record_trade.return_value = False  # second call = duplicate
    strategy = CCOverlayV1(store=mock_store, notifier=None)
    strategy._check_reentry = AsyncMock()

    pos = _make_position(avg_sell_price="80")
    action = ApprovedAction(
        action_type="CLOSE_CC",
        legs_to_close=[LegClose(leg_role="short_call")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"mark": "25.0"},
    )
    # Should not raise even when store says duplicate
    result = _run(strategy.apply_action([pos], action))
    assert result == []


def test_apply_action_no_store_does_not_raise() -> None:
    """store=None must not raise — write is skipped silently."""
    strategy = CCOverlayV1(store=None, notifier=None)
    strategy._check_reentry = AsyncMock()

    pos = _make_position()
    action = ApprovedAction(
        action_type="CLOSE_CC",
        legs_to_close=[LegClose(leg_role="short_call")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    result = _run(strategy.apply_action([pos], action))
    assert result == []


def test_apply_action_close_cc_matches_instrument_key_during_overlap() -> None:
    """Roll overlap: two positions share leg_role with different instrument_keys.

    Only the instrument identified by LegClose.instrument_key should be
    removed / recorded as closed — the other (still-open) instrument must
    survive in the returned positions list (PG-4c, mirrors PG-4b).
    """
    mock_store = MagicMock()
    mock_store.record_trade.return_value = True
    strategy = CCOverlayV1(store=mock_store, notifier=None)
    strategy._check_reentry = AsyncMock()

    old_pos = _make_position(
        instrument_key="NSE_FO|NIFTY26JUN2026CE",
        leg_role="short_call",
        avg_sell_price="80",
        net_qty=-65,
        entry_date=date(2026, 5, 1),
    )
    new_pos = _make_position(
        instrument_key="NSE_FO|NIFTY31JUL2026CE",
        leg_role="short_call",
        avg_sell_price="90",
        net_qty=-65,
        entry_date=date(2026, 6, 1),
    )
    action = ApprovedAction(
        action_type="CLOSE_CC",
        legs_to_close=[LegClose(leg_role="short_call", instrument_key="NSE_FO|NIFTY26JUN2026CE")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"mark": "5.0"},
    )
    result = _run(strategy.apply_action([old_pos, new_pos], action))

    assert result == [new_pos]
    trade = mock_store.record_trade.call_args[0][0]
    assert trade.instrument_key == "NSE_FO|NIFTY26JUN2026CE"


def test_record_close_trade_falls_back_to_avg_sell_price_when_mark_missing() -> None:
    """No mark in metadata → closing trade priced at avg_sell_price."""
    mock_store = MagicMock()
    mock_store.record_trade.return_value = True
    strategy = CCOverlayV1(store=mock_store, notifier=None)
    strategy._check_reentry = AsyncMock()

    pos = _make_position(avg_sell_price="80")
    action = ApprovedAction(
        action_type="CLOSE_CC",
        legs_to_close=[LegClose(leg_role="short_call")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    _run(strategy.apply_action([pos], action))

    trade = mock_store.record_trade.call_args[0][0]
    assert trade.price == Decimal("80")
