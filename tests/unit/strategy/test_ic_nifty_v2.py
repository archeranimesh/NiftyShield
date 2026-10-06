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
