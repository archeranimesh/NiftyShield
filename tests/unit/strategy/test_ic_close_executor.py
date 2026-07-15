"""Unit tests for close_ic_legs (src/strategy/ic_close_executor.py).

Covers the fix for the silent auto-close no-op: IronCondorV1/V2's
apply_action used to filter closed legs in memory without ever writing
the closing fills to paper_trades, so store.get_positions() kept
reporting the position open on every subsequent tick and the same exit
signal re-fired forever. close_ic_legs is the shared helper that now
persists those closes atomically.

All tests are offline — broker and store are mocked, no network, no DB.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.client.protocol import BrokerClient
from src.paper.models import PaperPosition, TradeAction
from src.paper.store import PaperStore
from src.strategy.ic_close_executor import close_ic_legs

_STRATEGY = "paper_ic_nifty_v1_weekly"


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _make_position(
    leg_role: str,
    instrument_key: str,
    net_qty: int,
    avg_sell_price: str = "0",
    avg_cost: str = "0",
) -> PaperPosition:
    return PaperPosition(
        strategy_name=_STRATEGY,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal(avg_cost),
        avg_sell_price=Decimal(avg_sell_price),
        instrument_key=instrument_key,
    )


def _make_ic_positions() -> list[PaperPosition]:
    """Standard 4-leg IC, all open — mirrors a real post-entry state."""
    return [
        _make_position("short_put", "NSE_FO|51348", net_qty=-65, avg_sell_price="6.68"),
        _make_position("long_put_hedge", "NSE_FO|51340", net_qty=65, avg_cost="4.12"),
        _make_position("short_call", "NSE_FO|51405", net_qty=-65, avg_sell_price="17.12"),
        _make_position("long_call_hedge", "NSE_FO|51417", net_qty=65, avg_cost="6.68"),
    ]


@pytest.fixture()
def mock_broker() -> MagicMock:
    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|51348": Decimal("42.00"),
            "NSE_FO|51340": Decimal("1.10"),
            "NSE_FO|51405": Decimal("38.50"),
            "NSE_FO|51417": Decimal("2.25"),
        }
    )
    return broker


@pytest.fixture()
def mock_store() -> MagicMock:
    store = MagicMock(spec=PaperStore)
    store.record_trades = MagicMock(side_effect=lambda trades: (trades, []))
    return store


# ── Happy path ────────────────────────────────────────────────────────────────


def test_close_full_persists_all_four_legs_with_opposite_action(
    mock_broker: MagicMock, mock_store: MagicMock
) -> None:
    """CLOSE_FULL: all 4 legs get an opposite-action closing trade, written atomically."""
    positions = _make_ic_positions()
    closed_roles = {"short_put", "long_put_hedge", "short_call", "long_call_hedge"}

    inserted = _run(
        close_ic_legs(
            broker=mock_broker,
            store=mock_store,
            positions=positions,
            closed_roles=closed_roles,
            strategy_name=_STRATEGY,
            notes="test close",
        )
    )

    assert len(inserted) == 4
    mock_store.record_trades.assert_called_once()
    (written,), _ = mock_store.record_trades.call_args
    by_role = {t.leg_role: t for t in written}

    # Shorts (net_qty < 0) close via BUY; longs (net_qty > 0) close via SELL.
    assert by_role["short_put"].action == TradeAction.BUY
    assert by_role["short_put"].price == Decimal("42.00")
    assert by_role["short_put"].quantity == 65
    assert by_role["short_call"].action == TradeAction.BUY
    assert by_role["short_call"].price == Decimal("38.50")
    assert by_role["long_put_hedge"].action == TradeAction.SELL
    assert by_role["long_put_hedge"].price == Decimal("1.10")
    assert by_role["long_call_hedge"].action == TradeAction.SELL
    assert by_role["long_call_hedge"].price == Decimal("2.25")
    for t in written:
        assert t.strategy_name == _STRATEGY
        assert t.notes == "test close"


def test_close_call_spread_only_touches_call_legs(
    mock_broker: MagicMock, mock_store: MagicMock
) -> None:
    """CLOSE_CALL_SPREAD: only short_call + long_call_hedge are written."""
    positions = _make_ic_positions()
    closed_roles = {"short_call", "long_call_hedge"}

    inserted = _run(
        close_ic_legs(
            broker=mock_broker,
            store=mock_store,
            positions=positions,
            closed_roles=closed_roles,
            strategy_name=_STRATEGY,
            notes="test spread close",
        )
    )

    assert {t.leg_role for t in inserted} == {"short_call", "long_call_hedge"}


# ── Fallback / degraded-mode behaviour ──────────────────────────────────────


def test_missing_ltp_falls_back_to_entry_price(mock_store: MagicMock) -> None:
    """LTP absent for an instrument → fall back to the leg's own entry price."""
    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(return_value={})  # nothing resolved
    positions = [_make_position("short_put", "NSE_FO|51348", net_qty=-65, avg_sell_price="6.68")]

    inserted = _run(
        close_ic_legs(
            broker=broker,
            store=mock_store,
            positions=positions,
            closed_roles={"short_put"},
            strategy_name=_STRATEGY,
            notes="fallback test",
        )
    )

    assert len(inserted) == 1
    assert inserted[0].price == Decimal("6.68")
    assert inserted[0].action == TradeAction.BUY


def test_broker_ltp_fetch_raises_falls_back_to_entry_price(mock_store: MagicMock) -> None:
    """broker.get_ltp raising is non-fatal — still closes at fallback price."""
    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(side_effect=RuntimeError("upstox down"))
    positions = [_make_position("long_put_hedge", "NSE_FO|51340", net_qty=65, avg_cost="4.12")]

    inserted = _run(
        close_ic_legs(
            broker=broker,
            store=mock_store,
            positions=positions,
            closed_roles={"long_put_hedge"},
            strategy_name=_STRATEGY,
            notes="broker error test",
        )
    )

    assert len(inserted) == 1
    assert inserted[0].price == Decimal("4.12")
    assert inserted[0].action == TradeAction.SELL


# ── Edge cases ───────────────────────────────────────────────────────────────


def test_nothing_open_for_requested_roles_returns_empty(
    mock_broker: MagicMock, mock_store: MagicMock
) -> None:
    """Requested roles already flat (net_qty == 0) → no trades written."""
    positions = [_make_position("short_put", "NSE_FO|51348", net_qty=0)]

    inserted = _run(
        close_ic_legs(
            broker=mock_broker,
            store=mock_store,
            positions=positions,
            closed_roles={"short_put"},
            strategy_name=_STRATEGY,
            notes="already flat",
        )
    )

    assert inserted == []
    mock_store.record_trades.assert_not_called()


def test_store_write_failure_returns_empty_and_does_not_raise(
    mock_broker: MagicMock, mock_store: MagicMock
) -> None:
    """store.record_trades raising is caught — caller sees [] rather than an exception."""
    mock_store.record_trades = MagicMock(side_effect=RuntimeError("db locked"))
    positions = _make_ic_positions()

    inserted = _run(
        close_ic_legs(
            broker=mock_broker,
            store=mock_store,
            positions=positions,
            closed_roles={"short_put", "long_put_hedge", "short_call", "long_call_hedge"},
            strategy_name=_STRATEGY,
            notes="write failure",
        )
    )

    assert inserted == []
