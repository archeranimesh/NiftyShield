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
            lookup=None,
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
    assert "CC CLOSED" in notifier.send.call_args[0][0]


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
    assert "PP RE-ENTRY ELIGIBLE" in notifier.send.call_args[0][0]
