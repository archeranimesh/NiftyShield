# tests/unit/paper/test_cc_roll.py
"""Unit tests for the manual Covered Call roll triggers in paper_cc_roll.py."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from scripts.strategies.cc_calibration.paper_cc_roll import (
    delta_stop_hit,
    loss_stop_hit,
    profit_target_hit,
    time_stop_hit,
)


def test_profit_target_hit() -> None:
    # 70% captured: current_ltp <= entry_credit * 0.30
    # Entry credit >= 15 is required
    assert profit_target_hit(Decimal("62"), Decimal("18.60")) is True  # exact boundary (18.60)
    assert profit_target_hit(Decimal("62"), Decimal("18.61")) is False  # just above
    assert profit_target_hit(Decimal("62"), Decimal("0")) is True  # expired worthless
    assert profit_target_hit(Decimal("14"), Decimal("3")) is False  # entry < 15 floor
    assert (
        profit_target_hit(Decimal("15"), Decimal("4.50")) is True
    )  # entry = 15 boundary, exact 30%


def test_time_stop_hit() -> None:
    entry = date(2026, 5, 1)
    assert time_stop_hit(entry, date(2026, 5, 22)) is True  # 21 days
    assert time_stop_hit(entry, date(2026, 5, 21)) is False  # 20 days
    assert time_stop_hit(entry, date(2026, 5, 1)) is False  # same day
    assert time_stop_hit(entry, date(2026, 6, 1)) is True  # 31 days


def test_delta_stop_hit() -> None:
    assert delta_stop_hit(0.55) is True  # exactly at limit
    assert delta_stop_hit(0.56) is True  # above limit
    assert delta_stop_hit(0.54) is False  # below limit
    assert delta_stop_hit(0.15) is False  # healthy CC delta


def test_loss_stop_hit() -> None:
    # 2.5x multiplier
    assert loss_stop_hit(Decimal("62"), Decimal("155.00")) is True  # exact boundary (155.0)
    assert loss_stop_hit(Decimal("62"), Decimal("154.99")) is False  # just below
    assert loss_stop_hit(Decimal("62"), Decimal("200")) is True  # well above
    assert loss_stop_hit(Decimal("62"), Decimal("62")) is False  # flat at entry


def test_get_close_price() -> None:
    from scripts.strategies.cc_calibration.paper_cc_roll import _get_close_price

    assert _get_close_price(Decimal("10.50")) == Decimal("10.50")
    assert _get_close_price(Decimal("0.00")) == Decimal("0.01")
    assert _get_close_price(Decimal("-5.00")) == Decimal("0.01")


@pytest.mark.asyncio
async def test_run_script_flow_no_open_leg() -> None:
    from unittest.mock import MagicMock, patch

    from scripts.strategies.cc_calibration.paper_cc_roll import STRATEGY_CC_OVERLAY, _run
    from src.paper.models import PaperPosition

    mock_store = MagicMock()
    # Return zero positions or net_qty = 0
    mock_store.get_position.return_value = PaperPosition(
        strategy_name=STRATEGY_CC_OVERLAY,
        leg_role="covered_call",
        net_qty=0,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("0"),
        instrument_key="",
    )
    mock_store.get_trades.return_value = []

    args = MagicMock()
    args.date = date(2026, 6, 7)
    args.db_path = "dummy_db"
    args.bod_path = "dummy_bod"
    args.force = False

    with patch(
        "scripts.strategies.cc_calibration.paper_cc_roll.PaperStore", return_value=mock_store
    ):
        with patch("builtins.print") as mock_print:
            await _run(args)
            mock_print.assert_any_call("No open covered_call leg for paper_covered_call_v1.")


@pytest.mark.asyncio
async def test_run_script_flow_trigger_profit_target_dry_run() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    from scripts.strategies.cc_calibration.paper_cc_roll import STRATEGY_CC_OVERLAY, _run
    from src.models.portfolio import TradeAction
    from src.paper.models import PaperPosition, PaperTrade

    mock_store = MagicMock()
    # Return open position net_qty = -50
    mock_store.get_position.return_value = PaperPosition(
        strategy_name=STRATEGY_CC_OVERLAY,
        leg_role="covered_call",
        net_qty=-50,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("62.00"),
        instrument_key="NSE_FO|NIFTY26JUN2026CE24500",
    )
    open_trade = PaperTrade(
        strategy_name=STRATEGY_CC_OVERLAY,
        leg_role="covered_call",
        instrument_key="NSE_FO|NIFTY26JUN2026CE24500",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("62.00"),
    )
    mock_store.get_trades.return_value = [open_trade]

    # Setup broker mock
    mock_broker = MagicMock()
    mock_broker.get_ltp = AsyncMock(return_value={"NSE_FO|NIFTY26JUN2026CE24500": Decimal("18.00")})
    # Mock get_option_chain response
    from src.models.options import OptionChain, OptionChainStrike, OptionLeg

    ce_leg = OptionLeg(
        ltp=Decimal("18.00"),  # <= 30% of 62.00 -> profit target hit
        bid=Decimal("17.50"),
        ask=Decimal("18.50"),
        oi=1000,
        volume=100,
        delta=Decimal("0.38"),
        gamma=Decimal("0.0001"),
        theta=Decimal("-1.0"),
        vega=Decimal("2.0"),
        iv=Decimal("12.0"),
        strike=Decimal("24500"),
    )
    chain = OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={Decimal("24500"): OptionChainStrike(ce=ce_leg)},
    )
    mock_broker.get_option_chain = AsyncMock(return_value=chain)

    args = MagicMock()
    args.date = date(2026, 6, 7)
    args.db_path = "dummy_db"
    args.bod_path = "dummy_bod"
    args.force = False
    args.dry_run = True
    args.yes = False

    with (
        patch(
            "scripts.strategies.cc_calibration.paper_cc_roll.PaperStore", return_value=mock_store
        ),
        patch(
            "scripts.strategies.cc_calibration.paper_cc_roll.create_client",
            return_value=mock_broker,
        ),
        patch(
            "scripts.strategies.cc_calibration.paper_cc_roll.parse_upstox_option_chain",
            return_value=chain,
        ),
    ):
        with patch("builtins.print") as mock_print:
            await _run(args)
            # Verify printed report contains hit status (note: it prints entry_credit * 0.3 which is 18.60)
            mock_print.assert_any_call(
                "Profit target:  ✅ HIT   (LTP ₹18.00 ≤ 30% of entry ₹18.60)"
            )
            mock_store.record_trade.assert_not_called()
