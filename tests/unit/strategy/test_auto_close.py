"""Unit tests for the EOD auto-close module."""

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import ExitSignal, PaperTrade, TradeAction
from src.paper.store import PaperStore
from src.strategy.auto_close import (
    _is_loss_stop_signal,
    auto_close_overlay,
    evaluate_pp_reentry_eod,
)
from src.strategy.executor import PaperFillSimulator


@pytest.fixture
def store(tmp_path) -> PaperStore:
    return PaperStore(tmp_path / "test_auto_close.db")


@pytest.fixture
def simulator() -> PaperFillSimulator:
    return PaperFillSimulator()


@pytest.fixture
def chain() -> OptionChain:
    return OptionChain(
        underlying_spot=Decimal("23000.0"),
        expiry=date(2026, 6, 25),
        strikes={},
    )


def test_is_loss_stop_signal_detection(store: PaperStore) -> None:
    # Set up events
    ev_loss = store.create_exit_event(
        strategy_name="test_strat",
        leg_name="overlay_cc",
        trade_id="t1",
        event_time=datetime.now(timezone.utc),
        detected_by="EOD",
        exit_signal=ExitSignal.LOSS_STOP,
        severity="ACTION",
        entry_price=Decimal("10.0"),
    )
    ev_profit = store.create_exit_event(
        strategy_name="test_strat",
        leg_name="overlay_cc",
        trade_id="t1",
        event_time=datetime.now(timezone.utc),
        detected_by="EOD",
        exit_signal=ExitSignal.PROFIT_TARGET,
        severity="ACTION",
        entry_price=Decimal("10.0"),
    )

    assert _is_loss_stop_signal(store, ev_loss) is True
    assert _is_loss_stop_signal(store, ev_profit) is False
    assert _is_loss_stop_signal(store, 99999) is False


@pytest.mark.asyncio
async def test_auto_close_overlay_cc_profit_target(
    store: PaperStore, simulator: PaperFillSimulator, chain: OptionChain
) -> None:
    # Seed trade and event
    store.record_trade(
        PaperTrade(
            strategy_name="paper_nifty_spot",
            leg_role="overlay_cc",
            instrument_key="NSE_FO|NIFTY23000CE",
            trade_date=date.today(),
            action=TradeAction.SELL,
            quantity=65,
            price=Decimal("100.0"),
            is_paper=True,
        )
    )
    event_id = store.create_exit_event(
        strategy_name="paper_nifty_spot",
        leg_name="overlay_cc",
        trade_id="NSE_FO|NIFTY23000CE",
        event_time=datetime.now(timezone.utc),
        detected_by="EOD",
        exit_signal=ExitSignal.PROFIT_TARGET,
        severity="ACTION",
        entry_price=Decimal("100.0"),
    )

    notifier = AsyncMock()

    # Stub finding chain leg
    option_leg = OptionLeg(
        instrument_key="NSE_FO|NIFTY23000CE",
        option_type="CE",
        strike_price=Decimal("23000.0"),
        ltp=Decimal("30.0"),
        delta=Decimal("-0.15"),
        bid=Decimal("29.5"),
        ask=Decimal("30.5"),
        oi=1000,
        volume=500,
        gamma=Decimal("0.001"),
        theta=Decimal("-5.0"),
        vega=Decimal("10.0"),
        iv=Decimal("15.0"),
        strike=Decimal("23000.0"),
    )
    chain.strikes[Decimal("23000.0")] = OptionChainStrike(ce=option_leg, pe=None)

    # Resolve position
    pos = store.get_position("paper_nifty_spot", "overlay_cc")
    assert pos.net_qty == -65

    lookup = MagicMock()
    lookup.get_by_key.return_value = {
        "instrument_type": "CE",
        "strike_price": 23000,
        "expiry": "2026-06-25",
        "underlying_symbol": "NIFTY",
    }

    # Run auto-close
    with patch(
        "src.paper.chain_utils.find_chain_leg",
        return_value=option_leg,
    ):
        success = await auto_close_overlay(
            store=store,
            simulator=simulator,
            pos=pos,
            event_id=event_id,
            chain=chain,
            notifier=notifier,
            lookup=lookup,
            vix=15.0,
            exit_signal="PROFIT_TARGET",
        )

    assert success is True
    # Verify status is ACTED
    event = store.get_exit_event(event_id)
    assert event["status"] == "ACTED"

    # Verify positions is now flat
    pos_after = store.get_position("paper_nifty_spot", "overlay_cc")
    assert pos_after.net_qty == 0

    # Wait for notification task to complete
    await asyncio.sleep(0.1)
    notifier.send.assert_called_once()
    msg = notifier.send.call_args[0][0]
    assert "CC CLOSED" in msg
    assert "NIFTY 23000 CE 25 JUN 26" in msg
    assert "NSE_FO|NIFTY23000CE" not in msg


@pytest.mark.asyncio
async def test_auto_close_overlay_cc_unresolvable_key_falls_back_to_raw(
    store: PaperStore, simulator: PaperFillSimulator, chain: OptionChain
) -> None:
    """format_leg_label fallback: unresolvable key still renders + notifies (non-fatal)."""
    store.record_trade(
        PaperTrade(
            strategy_name="paper_nifty_spot",
            leg_role="overlay_cc",
            instrument_key="NSE_FO|NIFTY23000CE",
            trade_date=date.today(),
            action=TradeAction.SELL,
            quantity=65,
            price=Decimal("100.0"),
            is_paper=True,
        )
    )
    event_id = store.create_exit_event(
        strategy_name="paper_nifty_spot",
        leg_name="overlay_cc",
        trade_id="NSE_FO|NIFTY23000CE",
        event_time=datetime.now(timezone.utc),
        detected_by="EOD",
        exit_signal=ExitSignal.PROFIT_TARGET,
        severity="ACTION",
        entry_price=Decimal("100.0"),
    )

    notifier = AsyncMock()

    option_leg = OptionLeg(
        instrument_key="NSE_FO|NIFTY23000CE",
        option_type="CE",
        strike_price=Decimal("23000.0"),
        ltp=Decimal("30.0"),
        delta=Decimal("-0.15"),
        bid=Decimal("29.5"),
        ask=Decimal("30.5"),
        oi=1000,
        volume=500,
        gamma=Decimal("0.001"),
        theta=Decimal("-5.0"),
        vega=Decimal("10.0"),
        iv=Decimal("15.0"),
        strike=Decimal("23000.0"),
    )
    chain.strikes[Decimal("23000.0")] = OptionChainStrike(ce=option_leg, pe=None)

    pos = store.get_position("paper_nifty_spot", "overlay_cc")

    lookup = MagicMock()
    lookup.get_by_key.return_value = None  # unresolvable in BOD JSON

    with patch(
        "src.paper.chain_utils.find_chain_leg",
        return_value=option_leg,
    ):
        success = await auto_close_overlay(
            store=store,
            simulator=simulator,
            pos=pos,
            event_id=event_id,
            chain=chain,
            notifier=notifier,
            lookup=lookup,
            vix=15.0,
            exit_signal="PROFIT_TARGET",
        )

    assert success is True
    await asyncio.sleep(0.1)
    # Notification still sends (non-fatal contract) with the raw key as fallback.
    notifier.send.assert_called_once()
    assert "NSE_FO|NIFTY23000CE" in notifier.send.call_args[0][0]


@pytest.mark.asyncio
async def test_auto_close_overlay_collar_put_pnl_uses_preclose_qty(
    store: PaperStore, simulator: PaperFillSimulator, chain: OptionChain
) -> None:
    """Regression: collar close must not report the put leg's P&L as zero.

    close_collar_all() writes both legs' closing trades atomically, so a
    get_position() call for the put leg made *after* it returns sees
    net_qty already flattened to 0. auto_close_overlay() must snapshot the
    put leg's qty/entry *before* invoking close_collar_all(), matching what
    it already does for the call leg via the pre-close `pos` parameter.
    Bug found analyzing a real Telegram COLLAR CLOSED message that showed
    the put leg's realized loss as "₹-0".
    """
    call_key = "NSE_FO|NIFTY65900CE"
    put_key = "NSE_FO|NIFTY65894PE"

    store.record_trade(
        PaperTrade(
            strategy_name="paper_nifty_futures",
            leg_role="overlay_collar_call",
            instrument_key=call_key,
            trade_date=date.today(),
            action=TradeAction.SELL,
            quantity=65,
            price=Decimal("543.90"),
            is_paper=True,
        )
    )
    store.record_trade(
        PaperTrade(
            strategy_name="paper_nifty_futures",
            leg_role="overlay_collar_put",
            instrument_key=put_key,
            trade_date=date.today(),
            action=TradeAction.BUY,
            quantity=65,
            price=Decimal("141.90"),
            is_paper=True,
        )
    )
    event_id = store.create_exit_event(
        strategy_name="paper_nifty_futures",
        leg_name="overlay_collar_call",
        trade_id=call_key,
        event_time=datetime.now(timezone.utc),
        detected_by="EOD",
        exit_signal=ExitSignal.DELTA_STOP,
        severity="ACTION",
        entry_price=Decimal("543.90"),
    )

    notifier = AsyncMock()

    call_leg = OptionLeg(
        instrument_key=call_key,
        option_type="CE",
        strike_price=Decimal("65900"),
        ltp=Decimal("757.55"),
        delta=Decimal("0.60"),
        bid=Decimal("757.00"),
        ask=Decimal("758.00"),
        oi=1000,
        volume=500,
        gamma=Decimal("0.001"),
        theta=Decimal("-5.0"),
        vega=Decimal("10.0"),
        iv=Decimal("15.0"),
        strike=Decimal("65900"),
    )
    put_leg = OptionLeg(
        instrument_key=put_key,
        option_type="PE",
        strike_price=Decimal("65894"),
        ltp=Decimal("26.15"),
        delta=Decimal("-0.05"),
        bid=Decimal("25.90"),
        ask=Decimal("26.40"),
        oi=1000,
        volume=500,
        gamma=Decimal("0.001"),
        theta=Decimal("-1.0"),
        vega=Decimal("2.0"),
        iv=Decimal("18.0"),
        strike=Decimal("65894"),
    )
    chain.strikes[Decimal("65900")] = OptionChainStrike(ce=call_leg, pe=None)
    chain.strikes[Decimal("65894")] = OptionChainStrike(ce=None, pe=put_leg)

    pos = store.get_position("paper_nifty_futures", "overlay_collar_call")
    assert pos.net_qty == -65

    def _find_leg(chain_, instrument_key, option_type, lookup):
        return call_leg if instrument_key == call_key else put_leg

    with patch("src.paper.chain_utils.find_chain_leg", side_effect=_find_leg):
        success = await auto_close_overlay(
            store=store,
            simulator=simulator,
            pos=pos,
            event_id=event_id,
            chain=chain,
            notifier=notifier,
            lookup=None,
            vix=15.0,
            exit_signal="DELTA_STOP",
        )

    assert success is True
    assert store.get_position("paper_nifty_futures", "overlay_collar_put").net_qty == 0

    notifier.send.assert_called_once()
    msg = notifier.send.call_args[0][0]
    assert "COLLAR CLOSED" in msg
    # Put leg lost ~(26.15-141.90)*65 = -7,523.75 -> displayed as -7,524.
    # Before the fix this rendered as "→ ₹-0".
    assert "₹-7,524" in msg
    assert "₹-0\n" not in msg


@pytest.mark.asyncio
async def test_auto_close_overlay_collar_write_failure_sends_failed_not_closed(
    store: PaperStore, simulator: PaperFillSimulator, chain: OptionChain
) -> None:
    """Regression: close_collar_all() returning False must not be reported as a close.

    Before this fix, close_collar_all() swallowed a record_trades() write
    failure internally (log + notify via its own always-None notifier) and
    returned None either way. auto_close_overlay() never checked a return
    value, so it unconditionally proceeded to compute pre-close P&L and send
    a plausible-looking "COLLAR CLOSED" message even though the DB write
    failed and both legs were still open. This is worse than the ₹-0 bug it
    replaced: a real-looking loss for a close that never happened.
    """
    call_key = "NSE_FO|NIFTY65900CE"
    put_key = "NSE_FO|NIFTY65894PE"

    store.record_trade(
        PaperTrade(
            strategy_name="paper_nifty_futures",
            leg_role="overlay_collar_call",
            instrument_key=call_key,
            trade_date=date.today(),
            action=TradeAction.SELL,
            quantity=65,
            price=Decimal("543.90"),
            is_paper=True,
        )
    )
    store.record_trade(
        PaperTrade(
            strategy_name="paper_nifty_futures",
            leg_role="overlay_collar_put",
            instrument_key=put_key,
            trade_date=date.today(),
            action=TradeAction.BUY,
            quantity=65,
            price=Decimal("141.90"),
            is_paper=True,
        )
    )
    event_id = store.create_exit_event(
        strategy_name="paper_nifty_futures",
        leg_name="overlay_collar_call",
        trade_id=call_key,
        event_time=datetime.now(timezone.utc),
        detected_by="EOD",
        exit_signal=ExitSignal.DELTA_STOP,
        severity="ACTION",
        entry_price=Decimal("543.90"),
    )

    notifier = AsyncMock()

    call_leg = OptionLeg(
        instrument_key=call_key,
        option_type="CE",
        strike_price=Decimal("65900"),
        ltp=Decimal("757.55"),
        delta=Decimal("0.60"),
        bid=Decimal("757.00"),
        ask=Decimal("758.00"),
        oi=1000,
        volume=500,
        gamma=Decimal("0.001"),
        theta=Decimal("-5.0"),
        vega=Decimal("10.0"),
        iv=Decimal("15.0"),
        strike=Decimal("65900"),
    )
    put_leg = OptionLeg(
        instrument_key=put_key,
        option_type="PE",
        strike_price=Decimal("65894"),
        ltp=Decimal("26.15"),
        delta=Decimal("-0.05"),
        bid=Decimal("25.90"),
        ask=Decimal("26.40"),
        oi=1000,
        volume=500,
        gamma=Decimal("0.001"),
        theta=Decimal("-1.0"),
        vega=Decimal("2.0"),
        iv=Decimal("18.0"),
        strike=Decimal("65894"),
    )
    chain.strikes[Decimal("65900")] = OptionChainStrike(ce=call_leg, pe=None)
    chain.strikes[Decimal("65894")] = OptionChainStrike(ce=None, pe=put_leg)

    pos = store.get_position("paper_nifty_futures", "overlay_collar_call")
    assert pos.net_qty == -65

    def _find_leg(chain_, instrument_key, option_type, lookup):
        return call_leg if instrument_key == call_key else put_leg

    with (
        patch("src.paper.chain_utils.find_chain_leg", side_effect=_find_leg),
        patch(
            "src.strategy.auto_close.OverlayCloser.close_collar_all",
            return_value=False,
        ),
    ):
        success = await auto_close_overlay(
            store=store,
            simulator=simulator,
            pos=pos,
            event_id=event_id,
            chain=chain,
            notifier=notifier,
            lookup=None,
            vix=15.0,
            exit_signal="DELTA_STOP",
        )

    assert success is False
    # Both legs must still be reported as open — no phantom close.
    assert store.get_position("paper_nifty_futures", "overlay_collar_call").net_qty == -65
    assert store.get_position("paper_nifty_futures", "overlay_collar_put").net_qty == 65

    notifier.send.assert_called_once()
    msg = notifier.send.call_args[0][0]
    assert "AUTO-CLOSE FAILED" in msg
    assert "COLLAR CLOSED" not in msg


@pytest.mark.asyncio
async def test_evaluate_pp_reentry_eligible(
    store: PaperStore, simulator: PaperFillSimulator, chain: OptionChain
) -> None:
    # No positions seeded -> eligible if IVR passes
    notifier = AsyncMock()

    # Mock VIX series load to return trailing history showing low VIX / low IVR
    vix_series = MagicMock()
    vix_series.empty = False
    vix_series.iloc = ["15.0"] * 300
    vix_series.__len__ = MagicMock(return_value=300)

    with (
        patch("src.strategy.auto_close.load_vix_series", return_value=vix_series),
        patch("src.strategy.auto_close.compute_ivr", return_value=0.45),
    ):
        await evaluate_pp_reentry_eod(
            store=store,
            simulator=simulator,
            chain=chain,
            lookup=None,
            notifier=notifier,
            vix_data_dir=None,
            today=date.today(),
        )

    # Re-entry should be flagged as ELIGIBLE and send notification
    notifier.send.assert_called_once()
    msg = notifier.send.call_args[0][0]
    assert "PP RE-ENTRY ELIGIBLE" in msg
    assert "standalone overlay" in msg


@pytest.mark.asyncio
async def test_evaluate_pp_reentry_suppressed_when_active(
    store: PaperStore, simulator: PaperFillSimulator, chain: OptionChain
) -> None:
    """No notification when an overlay_pp leg is already open under STRATEGY_OVERLAY."""
    from src.paper.constants import STRATEGY_OVERLAY

    # Seed an open overlay_pp BUY under the standalone overlay book
    store.record_trade(
        PaperTrade(
            strategy_name=STRATEGY_OVERLAY,
            leg_role="overlay_pp",
            instrument_key="NSE_FO|63848",
            trade_date=date.today(),
            action=TradeAction.BUY,
            quantity=65,
            price=Decimal("15.40"),
            is_paper=True,
        )
    )

    notifier = AsyncMock()
    vix_series = MagicMock()
    vix_series.empty = False
    vix_series.iloc = ["15.0"] * 300
    vix_series.__len__ = MagicMock(return_value=300)

    with (
        patch("src.strategy.auto_close.load_vix_series", return_value=vix_series),
        patch("src.strategy.auto_close.compute_ivr", return_value=0.20),
    ):
        await evaluate_pp_reentry_eod(
            store=store,
            simulator=simulator,
            chain=chain,
            lookup=None,
            notifier=notifier,
            vix_data_dir=None,
            today=date.today(),
        )

    # Active position detected — no notification should fire
    notifier.send.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_pp_reentry_realized_pnl_reads_overlay_book_only(
    store: PaperStore, simulator: PaperFillSimulator, chain: OptionChain
) -> None:
    """Realized P&L in the eligibility message is STRATEGY_OVERLAY's alone.

    BUG-028 Phase 4: pre-fix, this summed the three base tracks' realized P&L
    and mislabeled it as overlay P&L. Post-fix it must read only from
    STRATEGY_OVERLAY, and a closed round-trip on a base track (noise) must
    not leak into the figure.
    """
    from src.paper.constants import STRATEGY_OVERLAY, STRATEGY_SPOT

    # Closed round-trip under the standalone overlay book: BUY 65 @ 10, SELL 65 @ 15
    # -> realized P&L = 65 * (15 - 10) = 325
    for action, price in ((TradeAction.BUY, "10.00"), (TradeAction.SELL, "15.00")):
        store.record_trade(
            PaperTrade(
                strategy_name=STRATEGY_OVERLAY,
                leg_role="overlay_pp",
                instrument_key="NSE_FO|63848",
                trade_date=date.today(),
                action=action,
                quantity=65,
                price=Decimal(price),
                is_paper=True,
            )
        )

    # Distractor closed round-trip under a base track with a very different P&L —
    # must NOT be included in the message's realized-P&L figure.
    for action, price in ((TradeAction.BUY, "100.00"), (TradeAction.SELL, "50.00")):
        store.record_trade(
            PaperTrade(
                strategy_name=STRATEGY_SPOT,
                leg_role="base_spot",
                instrument_key="NSE_EQ|niftybees",
                trade_date=date.today(),
                action=action,
                quantity=100,
                price=Decimal(price),
                is_paper=True,
            )
        )

    notifier = AsyncMock()
    vix_series = MagicMock()
    vix_series.empty = False
    vix_series.iloc = ["15.0"] * 300
    vix_series.__len__ = MagicMock(return_value=300)

    with (
        patch("src.strategy.auto_close.load_vix_series", return_value=vix_series),
        patch("src.strategy.auto_close.compute_ivr", return_value=0.45),
    ):
        await evaluate_pp_reentry_eod(
            store=store,
            simulator=simulator,
            chain=chain,
            lookup=None,
            notifier=notifier,
            vix_data_dir=None,
            today=date.today(),
        )

    notifier.send.assert_called_once()
    msg = notifier.send.call_args[0][0]
    assert "₹+325" in msg
    assert "₹-5,000" not in msg
    assert "₹-4,675" not in msg  # would be the (wrong) summed figure
