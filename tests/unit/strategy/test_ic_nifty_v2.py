import asyncio
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from structlog.testing import capture_logs

from src.models.portfolio import TradeAction
from src.notifications.telegram_gateway import TelegramGateway
from src.paper.models import PaperPosition, PaperTrade
from src.strategy.ic_nifty_v2 import IronCondorV2


@pytest.fixture
def base_positions():
    return [
        PaperPosition(
            strategy_name="paper_test_strat",
            instrument_key="NIFTY26JAN10000PE",
            net_qty=-50,
            avg_sell_price=Decimal("100"),
            avg_cost=Decimal("0"),
            leg_role="short_put",
            entry_date=date(2026, 1, 1),
            option_type="PE",
        )
    ]


@pytest.fixture
def base_trades():
    return [
        PaperTrade(
            strategy_name="paper_test_strat",
            trade_date=date(2026, 1, 10),
            instrument_key="NIFTY26JAN10000PE",
            action=TradeAction.BUY,
            quantity=50,
            price=Decimal("50"),
            leg_role="short_put",
        )
    ]


@pytest.mark.asyncio
async def test_ic_v2_send_close_notification_happy_path(base_positions, base_trades) -> None:
    notifier = AsyncMock(spec=TelegramGateway)
    store = MagicMock()

    margin_mock = MagicMock()
    margin_mock.final_margin = Decimal("50000")
    store.get_margin_snapshot.return_value = margin_mock

    ic = IronCondorV2(broker=None, store=store, notifier=notifier)

    with patch("src.strategy.ic_nifty_v2.ensure_registered") as mock_ensure:
        with patch(
            "src.strategy.ic_nifty_v2.send_payoff_chart", new_callable=AsyncMock
        ) as mock_send:
            await ic._send_close_notification(
                action_type="CLOSE_FULL",
                triggering_signal="TEST_SIGNAL",
                closed_trades=base_trades,
                positions=base_positions,
            )

            assert mock_ensure.call_count == 1
            assert mock_send.call_count == 1
            args, kwargs = mock_send.call_args

            assert args[0] == notifier
            assert args[1] == ic.strategy_name
            assert args[2].positions == base_positions
            assert kwargs["current_pnl"] == Decimal("2500")  # (100 - 50) * 50
            assert kwargs["margin"] == Decimal("50000")


@pytest.mark.asyncio
async def test_ic_v2_send_close_notification_error_path(base_positions, base_trades) -> None:
    notifier = AsyncMock(spec=TelegramGateway)
    ic = IronCondorV2(broker=None, store=None, notifier=notifier)

    with (
        patch("src.strategy.ic_nifty_v2.ensure_registered"),
        patch(
            "src.strategy.ic_nifty_v2.send_payoff_chart",
            new_callable=AsyncMock,
            side_effect=Exception("Test Exception"),
        ),
    ):
        with capture_logs() as cap_logs:
            await ic._send_close_notification(
                action_type="CLOSE_FULL",
                triggering_signal="TEST_SIGNAL",
                closed_trades=base_trades,
                positions=base_positions,
            )

            # Verify it handled the exception without crashing
            assert any(
                log.get("event") == "ic_nifty_v2.send_payoff_chart_failed" for log in cap_logs
            )


@pytest.mark.asyncio
async def test_ic_v2_send_close_notification_no_chart_when_notifier_none_or_no_trades(
    base_positions, base_trades
) -> None:
    # Case 1: No notifier
    ic1 = IronCondorV2(broker=None, store=None, notifier=None)
    with patch("src.strategy.ic_nifty_v2.send_payoff_chart", new_callable=AsyncMock) as mock_send1:
        await ic1._send_close_notification(
            action_type="CLOSE_FULL",
            triggering_signal="TEST_SIGNAL",
            closed_trades=base_trades,
            positions=base_positions,
        )
        mock_send1.assert_not_called()

    # Case 2: Notifier present but no trades
    notifier = AsyncMock(spec=TelegramGateway)
    ic2 = IronCondorV2(broker=None, store=None, notifier=notifier)
    with patch("src.strategy.ic_nifty_v2.send_payoff_chart", new_callable=AsyncMock) as mock_send2:
        await ic2._send_close_notification(
            action_type="CLOSE_FULL",
            triggering_signal="TEST_SIGNAL",
            closed_trades=[],
            positions=base_positions,
        )
        mock_send2.assert_not_called()

    # Case 3: Notifier present, trades closed, but positions=[]
    notifier3 = AsyncMock(spec=TelegramGateway)
    ic3 = IronCondorV2(broker=None, store=None, notifier=notifier3)
    with patch("src.strategy.ic_nifty_v2.send_payoff_chart", new_callable=AsyncMock) as mock_send3:
        await ic3._send_close_notification(
            action_type="CLOSE_FULL",
            triggering_signal="TEST_SIGNAL",
            closed_trades=base_trades,
            positions=[],
        )
        mock_send3.assert_not_called()


def test_v2_close_notification_overlapped_legs_use_own_entry_price() -> None:
    """BUG-074: two open rows under one role are matched to their own entry by instrument_key."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from src.models.portfolio import TradeAction
    from src.paper.models import PaperPosition, PaperTrade

    notifier = MagicMock()
    notifier.send_notification = AsyncMock()
    strat = IronCondorV2(notifier=notifier)  # store=None
    entries = {"NSE_FO|A21500": Decimal("29.1"), "NSE_FO|B21550": Decimal("40.6")}
    exits = {"NSE_FO|A21500": Decimal("39.0"), "NSE_FO|B21550": Decimal("40.6")}
    positions = [
        PaperPosition(
            strategy_name="paper_test_strat",
            leg_role="long_put_hedge",
            net_qty=65,
            avg_cost=cost,
            avg_sell_price=Decimal("0"),
            instrument_key=key,
            entry_date=date(2026, 10, 1) if key.startswith("NSE_FO|A") else date(2026, 10, 5),
        )
        for key, cost in entries.items()
    ]
    closed = [
        PaperTrade(
            strategy_name="paper_test_strat",
            leg_role="long_put_hedge",
            instrument_key=key,
            trade_date=date(2026, 10, 8),
            action=TradeAction.SELL,
            quantity=65,
            price=price,
            notes="close",
        )
        for key, price in exits.items()
    ]

    with patch("src.strategy.ic_nifty_v2.format_exit_message", return_value="msg") as fmt:
        asyncio.run(
            strat._send_close_notification("CLOSE_FULL", "PROFIT_TARGET", closed, positions)
        )

    msg = fmt.call_args.args[0]
    assert [r.entry for r in msg.legs] == [Decimal("29.1"), Decimal("40.6")]
    assert [r.pnl for r in msg.legs] == [Decimal("643.5"), Decimal("0.0")]
    assert msg.this_exit_pnl == Decimal("643.5")
    assert msg.held_days == 7
