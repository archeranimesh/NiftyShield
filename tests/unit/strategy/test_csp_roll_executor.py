"""Unit tests for extracted csp_roll_executor logic."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.client.protocol import BrokerClient
from src.instruments.lookup import InstrumentLookup
from src.paper.models import PaperTrade, TradeAction
from src.paper.store import PaperStore
from src.strategy.csp_roll_executor import close_csp_leg, open_new_csp_leg, roll_csp


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


@pytest.fixture()
def mock_broker() -> MagicMock:
    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(return_value={"NSE_FO|NIFTY23000PE": Decimal("10.50")})
    return broker


@pytest.fixture()
def mock_store() -> MagicMock:
    store = MagicMock(spec=PaperStore)
    return store


@pytest.fixture()
def mock_lookup() -> MagicMock:
    lookup = MagicMock(spec=InstrumentLookup)
    lookup.get_expiry_candidates = MagicMock(return_value=[("monthly", "2026-06-26")])
    return lookup


def test_close_csp_leg_dry_run(mock_broker: MagicMock, mock_store: MagicMock) -> None:
    existing = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|NIFTY23000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("80.00"),
    )

    close_trade = _run(
        close_csp_leg(mock_broker, mock_store, existing, date(2026, 6, 5), dry_run=True)
    )

    assert close_trade.price == Decimal("10.50")
    assert close_trade.action == TradeAction.BUY
    assert close_trade.quantity == 50
    mock_store.record_trade.assert_not_called()


def test_close_csp_leg_live(mock_broker: MagicMock, mock_store: MagicMock) -> None:
    existing = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|NIFTY23000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("80.00"),
    )

    close_trade = _run(
        close_csp_leg(mock_broker, mock_store, existing, date(2026, 6, 5), dry_run=False)
    )

    assert close_trade.price == Decimal("10.50")
    mock_store.record_trade.assert_called_once_with(close_trade)


def test_open_new_csp_leg_dry_run(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    # Set up option chain matching filter_strikes_by_delta expectations
    mock_broker.get_option_chain = AsyncMock(
        return_value=[
            {
                "strike_price": 22800.0,
                "put_options": {
                    "instrument_key": "NSE_FO|NIFTY22800PE",
                    "option_greeks": {
                        "delta": -0.22,
                        "iv": 15.0,
                    },
                    "market_data": {
                        "ltp": 45.50,
                        "bid_price": 45.0,
                        "ask_price": 46.0,
                        "oi": 50000.0,
                    },
                },
            }
        ]
    )

    new_trade = _run(
        open_new_csp_leg(
            mock_broker,
            mock_store,
            mock_lookup,
            strategy="paper_csp_nifty_v1",
            roll_date=date(2026, 6, 5),
            dry_run=True,
            quantity=50,
        )
    )

    assert new_trade.instrument_key == "NSE_FO|NIFTY22800PE"
    assert new_trade.price == Decimal("45.50")
    mock_store.record_trade.assert_not_called()


def test_roll_csp_success(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    existing = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|NIFTY23000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("80.00"),
    )

    mock_broker.get_option_chain = AsyncMock(
        return_value=[
            {
                "strike_price": 22800.0,
                "put_options": {
                    "instrument_key": "NSE_FO|NIFTY22800PE",
                    "option_greeks": {
                        "delta": -0.22,
                        "iv": 15.0,
                    },
                    "market_data": {
                        "ltp": 45.50,
                        "bid_price": 45.0,
                        "ask_price": 46.0,
                        "oi": 50000.0,
                    },
                },
            }
        ]
    )

    res = _run(
        roll_csp(
            mock_broker,
            mock_store,
            mock_lookup,
            existing,
            roll_date=date(2026, 6, 5),
            dry_run=False,
        )
    )

    assert res.old_instrument_key == "NSE_FO|NIFTY23000PE"
    assert res.close_price == Decimal("10.50")
    assert res.new_instrument_key == "NSE_FO|NIFTY22800PE"
    assert res.new_price == Decimal("45.50")
    assert res.cycle_pnl == (Decimal("80.00") - Decimal("10.50")) * 50
    assert mock_store.record_trade.call_count == 2


def test_roll_csp_rollback_on_failure(
    mock_broker: MagicMock, mock_store: MagicMock, mock_lookup: MagicMock
) -> None:
    existing = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|NIFTY23000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=50,
        price=Decimal("80.00"),
    )

    # Make chain fetch fail to trigger error in open_new_csp_leg
    mock_broker.get_option_chain = AsyncMock(return_value=[])

    with pytest.raises(ValueError, match="No option chain data returned"):
        _run(
            roll_csp(
                mock_broker,
                mock_store,
                mock_lookup,
                existing,
                roll_date=date(2026, 6, 5),
                dry_run=False,
            )
        )

    # Check close trade was recorded and then deleted
    assert mock_store.record_trade.call_count == 1
    mock_store.delete_trade.assert_called_once()
