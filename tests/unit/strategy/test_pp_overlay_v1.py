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
from src.strategy.protocol import ApprovedAction, LegClose, SignalEvent

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
        legs_to_close=[LegClose(leg_role="protective_put")],
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
        legs_to_close=[LegClose(leg_role="protective_put")],
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


def test_apply_action_send_plain_message_fallback() -> None:
    mock_store = MagicMock()
    mock_notifier = AsyncMock()
    del mock_notifier.send_notification  # Remove send_notification to force fallback
    mock_notifier.send_plain_message = AsyncMock()

    strategy = PPOverlayV1(store=mock_store, notifier=mock_notifier)
    strategy._check_reentry = AsyncMock()

    pos = _make_position()
    action = ApprovedAction(
        action_type="ROLL_PP",
        legs_to_close=[LegClose(leg_role="protective_put")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    result = _run(strategy.apply_action([pos], action))
    assert len(result) == 0
    mock_notifier.send_plain_message.assert_called_once()
    assert "🔄 <b>PP: ROLL_PP</b>" in mock_notifier.send_plain_message.call_args[0][0]


def test_apply_action_notifier_missing_methods_non_fatal() -> None:
    mock_store = MagicMock()

    # A dummy object with neither send_notification nor send_plain_message
    class StubbierNotifier:
        pass

    strategy = PPOverlayV1(store=mock_store, notifier=StubbierNotifier())
    strategy._check_reentry = AsyncMock()

    pos = _make_position()
    action = ApprovedAction(
        action_type="ROLL_PP",
        legs_to_close=[LegClose(leg_role="protective_put")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    # This should not raise any exceptions
    result = _run(strategy.apply_action([pos], action))
    assert len(result) == 0


def test_apply_action_dte_float_casting() -> None:
    mock_store = MagicMock()
    mock_notifier = AsyncMock()
    strategy = PPOverlayV1(store=mock_store, notifier=mock_notifier)
    strategy._check_reentry = AsyncMock()

    pos = _make_position()
    action = ApprovedAction(
        action_type="ROLL_PP",
        legs_to_close=[LegClose(leg_role="protective_put")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"dte": "4.5", "mark": "40.0"},
    )
    result = _run(strategy.apply_action([pos], action))
    assert len(result) == 0
    mock_notifier.send_notification.assert_called_once()
    assert "DTE 4" in mock_notifier.send_notification.call_args[0][0]


# ---------------------------------------------------------------------------
# DBI-2: record_close_trade tests
# ---------------------------------------------------------------------------


def test_apply_action_records_closing_trade_to_store() -> None:
    """apply_action(MONETIZE_PP) must write a SELL closing trade to the store."""
    mock_store = MagicMock()
    mock_store.record_trade.return_value = True
    strategy = PPOverlayV1(store=mock_store, notifier=None)
    strategy._check_reentry = AsyncMock()

    key = _expiry_key(dte=15)
    pos = _make_position(instrument_key=key, avg_cost="50", net_qty=65)
    action = ApprovedAction(
        action_type="MONETIZE_PP",
        legs_to_close=[LegClose(leg_role="protective_put")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"mark": "210.0"},
    )
    _run(strategy.apply_action([pos], action))

    mock_store.record_trade.assert_called_once()
    trade = mock_store.record_trade.call_args[0][0]
    assert trade.action.value == "SELL"
    assert trade.quantity == 65
    assert trade.price == Decimal("210.0")
    assert trade.leg_role == "protective_put"


def test_apply_action_recording_idempotent_on_duplicate() -> None:
    """store.record_trade returning False must not raise."""
    mock_store = MagicMock()
    mock_store.record_trade.return_value = False
    strategy = PPOverlayV1(store=mock_store, notifier=None)
    strategy._check_reentry = AsyncMock()

    pos = _make_position(instrument_key=_expiry_key(15))
    action = ApprovedAction(
        action_type="MONETIZE_PP",
        legs_to_close=[LegClose(leg_role="protective_put")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"mark": "50.0"},
    )
    result = _run(strategy.apply_action([pos], action))
    assert result == []


def test_apply_action_no_store_does_not_raise() -> None:
    """store=None must not raise."""
    strategy = PPOverlayV1(store=None, notifier=None)
    strategy._check_reentry = AsyncMock()

    pos = _make_position()
    action = ApprovedAction(
        action_type="MONETIZE_PP",
        legs_to_close=[LegClose(leg_role="protective_put")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    result = _run(strategy.apply_action([pos], action))
    assert result == []


def test_apply_action_monetize_pp_matches_instrument_key_during_overlap() -> None:
    """Roll overlap: two positions share leg_role with different instrument_keys.

    Only the instrument identified by LegClose.instrument_key should be
    removed / recorded as closed — the other (still-open) instrument must
    survive in the returned positions list (PG-4d, mirrors PG-4b/PG-4c).
    """
    mock_store = MagicMock()
    mock_store.record_trade.return_value = True
    strategy = PPOverlayV1(store=mock_store, notifier=None)
    strategy._check_reentry = AsyncMock()

    old_pos = _make_position(
        instrument_key="NSE_FO|NIFTY26JUN2026PE",
        leg_role="protective_put",
        avg_cost="80",
        net_qty=65,
        entry_date=date(2026, 5, 1),
    )
    new_pos = _make_position(
        instrument_key="NSE_FO|NIFTY31JUL2026PE",
        leg_role="protective_put",
        avg_cost="90",
        net_qty=65,
        entry_date=date(2026, 6, 1),
    )
    action = ApprovedAction(
        action_type="MONETIZE_PP",
        legs_to_close=[
            LegClose(leg_role="protective_put", instrument_key="NSE_FO|NIFTY26JUN2026PE")
        ],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
        metadata={"mark": "210.0"},
    )
    result = _run(strategy.apply_action([old_pos, new_pos], action))

    assert result == [new_pos]
    trade = mock_store.record_trade.call_args[0][0]
    assert trade.instrument_key == "NSE_FO|NIFTY26JUN2026PE"


def test_record_close_trade_falls_back_to_avg_cost_when_mark_missing() -> None:
    """No mark in metadata → closing trade priced at avg_cost."""
    mock_store = MagicMock()
    mock_store.record_trade.return_value = True
    strategy = PPOverlayV1(store=mock_store, notifier=None)
    strategy._check_reentry = AsyncMock()

    pos = _make_position(avg_cost="50")
    action = ApprovedAction(
        action_type="MONETIZE_PP",
        legs_to_close=[LegClose(leg_role="protective_put")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    _run(strategy.apply_action([pos], action))

    trade = mock_store.record_trade.call_args[0][0]
    assert trade.price == Decimal("50")


# ── MC-4: _find_put_leg BOD-fallback routing ──────────────────────────────


class _FakeLookup:
    """Minimal stand-in for InstrumentLookup.get_by_key()."""

    def __init__(self, instruments: dict[str, dict[str, object]]) -> None:
        self._instruments = instruments

    def get_by_key(self, instrument_key: str) -> dict[str, object] | None:
        return self._instruments.get(instrument_key)


def test_find_put_leg_resolves_real_numeric_key_via_bod_lookup() -> None:
    """Real Upstox keys (e.g. NSE_FO|65900) carry no strike/type in the key
    string and must resolve via the shared BOD-fallback utility, not a blind
    chain walk."""
    market = _make_chain(ltp="50", delta="-0.20", strike="21000")
    lookup = _FakeLookup({"NSE_FO|65900": {"instrument_type": "PE", "strike_price": 21000.0}})
    strategy = PPOverlayV1(instrument_lookup=lookup)

    leg = strategy._find_put_leg(market, "NSE_FO|65900")

    assert leg is not None
    assert leg.strike == Decimal("21000")


def test_find_put_leg_chain_walk_fallback_is_gone() -> None:
    """Old behaviour: an unresolvable key silently walked the chain and
    returned the first PE with positive LTP — the wrong strike. New
    behaviour: an unresolvable key (no lookup, no regex match) returns None."""
    market = _make_chain(ltp="50", delta="-0.20", strike="21000")
    strategy = PPOverlayV1()  # no instrument_lookup injected

    leg = strategy._find_put_leg(market, "NSE_FO|65900")

    assert leg is None
