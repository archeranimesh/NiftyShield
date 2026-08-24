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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.client.protocol import BrokerClient
from src.market_calendar.holidays import market_today
from src.paper.models import PaperPosition, TradeAction
from src.paper.store import PaperStore
from src.strategy.ic_close_executor import (
    _NIFTY_SPOT_KEY,
    _OTM_EXPIRY_PRICE,
    close_ic_legs,
    roll_ic_legs,
)
from src.strategy.protocol import LegSpec

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
    """LTP absent + instrument not found in BOD (not expired) → entry-price fallback."""
    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(return_value={})  # nothing resolved
    positions = [_make_position("short_put", "NSE_FO|51348", net_qty=-65, avg_sell_price="6.68")]

    mock_lookup = MagicMock()
    mock_lookup.get_by_key.return_value = None  # not in BOD → can't tell it's expired
    with patch(
        "src.strategy.ic_close_executor.InstrumentLookup.from_file",
        return_value=mock_lookup,
    ):
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
    broker.get_ltp.assert_called_once()  # only the option-leg batch call, no spot fetch


def test_broker_ltp_fetch_raises_falls_back_to_entry_price(mock_store: MagicMock) -> None:
    """broker.get_ltp raising is non-fatal — still closes at fallback price."""
    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(side_effect=RuntimeError("upstox down"))
    positions = [_make_position("long_put_hedge", "NSE_FO|51340", net_qty=65, avg_cost="4.12")]

    mock_lookup = MagicMock()
    mock_lookup.get_by_key.return_value = None
    with patch(
        "src.strategy.ic_close_executor.InstrumentLookup.from_file",
        return_value=mock_lookup,
    ):
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


# ── Post-expiry settlement fallback ─────────────────────────────────────────


def _mock_bod_inst(strike_price: float, instrument_type: str, expiry: str) -> dict[str, object]:
    return {"strike_price": strike_price, "instrument_type": instrument_type, "expiry": expiry}


def test_post_expiry_itm_call_settles_at_intrinsic_value(mock_store: MagicMock) -> None:
    """Expired short_call, strike below spot (ITM) → settle at spot - strike."""
    broker = MagicMock(spec=BrokerClient)
    # First call: option-leg LTP batch, empty (expired, no LTP). Second call: spot.
    broker.get_ltp = AsyncMock(side_effect=[{}, {_NIFTY_SPOT_KEY: Decimal("24150.00")}])
    positions = [_make_position("short_call", "NSE_FO|51405", net_qty=-65, avg_sell_price="17.12")]

    mock_lookup = MagicMock()
    mock_lookup.get_by_key.return_value = _mock_bod_inst(24000, "CE", "2026-07-14")
    with patch(
        "src.strategy.ic_close_executor.InstrumentLookup.from_file",
        return_value=mock_lookup,
    ):
        inserted = _run(
            close_ic_legs(
                broker=broker,
                store=mock_store,
                positions=positions,
                closed_roles={"short_call"},
                strategy_name=_STRATEGY,
                notes="expiry settlement test",
            )
        )

    assert len(inserted) == 1
    assert inserted[0].price == Decimal("150.00")  # 24150 - 24000
    assert inserted[0].action == TradeAction.BUY
    assert broker.get_ltp.call_count == 2
    broker.get_ltp.assert_any_call([_NIFTY_SPOT_KEY])


def test_post_expiry_otm_put_settles_at_tick_floor(mock_store: MagicMock) -> None:
    """Expired long_put_hedge, strike below spot (OTM for a put) → settle at 0.05."""
    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(side_effect=[{}, {_NIFTY_SPOT_KEY: Decimal("24150.00")}])
    positions = [_make_position("long_put_hedge", "NSE_FO|51340", net_qty=65, avg_cost="4.12")]

    mock_lookup = MagicMock()
    mock_lookup.get_by_key.return_value = _mock_bod_inst(23500, "PE", "2026-07-14")
    with patch(
        "src.strategy.ic_close_executor.InstrumentLookup.from_file",
        return_value=mock_lookup,
    ):
        inserted = _run(
            close_ic_legs(
                broker=broker,
                store=mock_store,
                positions=positions,
                closed_roles={"long_put_hedge"},
                strategy_name=_STRATEGY,
                notes="expiry settlement test",
            )
        )

    assert len(inserted) == 1
    assert inserted[0].price == _OTM_EXPIRY_PRICE
    assert inserted[0].action == TradeAction.SELL


def test_post_expiry_but_spot_unavailable_falls_back_to_entry_price(
    mock_store: MagicMock,
) -> None:
    """Expired leg but spot fetch itself fails → degrade to entry-price fallback."""
    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(side_effect=[{}, RuntimeError("spot fetch down")])
    positions = [_make_position("short_call", "NSE_FO|51405", net_qty=-65, avg_sell_price="17.12")]

    mock_lookup = MagicMock()
    mock_lookup.get_by_key.return_value = _mock_bod_inst(24000, "CE", "2026-07-14")
    with patch(
        "src.strategy.ic_close_executor.InstrumentLookup.from_file",
        return_value=mock_lookup,
    ):
        inserted = _run(
            close_ic_legs(
                broker=broker,
                store=mock_store,
                positions=positions,
                closed_roles={"short_call"},
                strategy_name=_STRATEGY,
                notes="expiry settlement test",
            )
        )

    assert len(inserted) == 1
    assert inserted[0].price == Decimal("17.12")  # entry-price fallback, not settlement


def test_expiry_is_today_still_settles_at_intrinsic_value(mock_store: MagicMock) -> None:
    """Boundary case: expiry == today (same-day close) must use settlement, not entry price.

    This is the dominant real-world trigger — the daemon almost always
    detects a dead leg on expiry day itself, once the exchange stops
    quoting it. A strict `<` here would silently reintroduce the exact
    P&L-zeroing bug this module was written to fix.
    """
    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(side_effect=[{}, {_NIFTY_SPOT_KEY: Decimal("24150.00")}])
    positions = [_make_position("short_call", "NSE_FO|51405", net_qty=-65, avg_sell_price="17.12")]

    mock_lookup = MagicMock()
    today_str = market_today().isoformat()
    mock_lookup.get_by_key.return_value = _mock_bod_inst(24000, "CE", today_str)
    with patch(
        "src.strategy.ic_close_executor.InstrumentLookup.from_file",
        return_value=mock_lookup,
    ):
        inserted = _run(
            close_ic_legs(
                broker=broker,
                store=mock_store,
                positions=positions,
                closed_roles={"short_call"},
                strategy_name=_STRATEGY,
                notes="same-day expiry test",
            )
        )

    assert len(inserted) == 1
    assert inserted[0].price == Decimal("150.00")  # settlement, NOT entry price (17.12)
    assert broker.get_ltp.call_count == 2  # spot fetch must have been triggered


def test_not_yet_expired_missing_ltp_uses_entry_price_not_settlement(
    mock_store: MagicMock,
) -> None:
    """LTP missing but BOD expiry is still in the future → transient gap, not expiry."""
    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(return_value={})
    positions = [_make_position("short_call", "NSE_FO|51405", net_qty=-65, avg_sell_price="17.12")]

    mock_lookup = MagicMock()
    mock_lookup.get_by_key.return_value = _mock_bod_inst(24000, "CE", "2099-01-01")
    with patch(
        "src.strategy.ic_close_executor.InstrumentLookup.from_file",
        return_value=mock_lookup,
    ):
        inserted = _run(
            close_ic_legs(
                broker=broker,
                store=mock_store,
                positions=positions,
                closed_roles={"short_call"},
                strategy_name=_STRATEGY,
                notes="not expired test",
            )
        )

    assert len(inserted) == 1
    assert inserted[0].price == Decimal("17.12")
    broker.get_ltp.assert_called_once()  # no spot fetch — not post-expiry


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


# ── roll_ic_legs ─────────────────────────────────────────────────────────────


def test_roll_happy_path_writes_close_and_open_legs_atomically(
    mock_broker: MagicMock, mock_store: MagicMock
) -> None:
    """Roll: old short_call closed, new short_call opened, single record_trades call."""
    positions = [_make_position("short_call", "NSE_FO|51405", net_qty=-65, avg_sell_price="17.12")]
    open_legs = [
        LegSpec(
            instrument_key="NSE_FO|51999",
            action="SELL",
            quantity=65,
            leg_role="short_call",
            notes="roll_open_short delta=0.15",
            price=Decimal("12.50"),
        )
    ]

    inserted = _run(
        roll_ic_legs(
            broker=mock_broker,
            store=mock_store,
            close_positions=positions,
            closed_roles={"short_call"},
            open_legs=open_legs,
            strategy_name=_STRATEGY,
            notes="test roll",
        )
    )

    assert len(inserted) == 2
    mock_store.record_trades.assert_called_once()
    (written,), _ = mock_store.record_trades.call_args
    assert len(written) == 2
    close_trade = next(t for t in written if t.instrument_key == "NSE_FO|51405")
    open_trade = next(t for t in written if t.instrument_key == "NSE_FO|51999")
    assert close_trade.action == TradeAction.BUY
    assert close_trade.price == Decimal("38.50")  # from mock_broker LTP
    assert open_trade.action == TradeAction.SELL
    assert open_trade.price == Decimal("12.50")
    assert open_trade.quantity == 65
    for t in written:
        assert t.notes == "test roll"


def test_roll_open_leg_missing_price_aborts_entire_roll(
    mock_broker: MagicMock, mock_store: MagicMock
) -> None:
    """Open leg with price=None must abort the roll — no partial write."""
    positions = [_make_position("short_call", "NSE_FO|51405", net_qty=-65, avg_sell_price="17.12")]
    open_legs = [
        LegSpec(
            instrument_key="NSE_FO|51999",
            action="SELL",
            quantity=65,
            leg_role="short_call",
            notes="roll_open_short delta=0.15",
            price=None,
        )
    ]

    inserted = _run(
        roll_ic_legs(
            broker=mock_broker,
            store=mock_store,
            close_positions=positions,
            closed_roles={"short_call"},
            open_legs=open_legs,
            strategy_name=_STRATEGY,
            notes="test roll",
        )
    )

    assert inserted == []
    mock_store.record_trades.assert_not_called()


def test_roll_open_leg_non_positive_price_aborts_entire_roll(
    mock_broker: MagicMock, mock_store: MagicMock
) -> None:
    """Open leg with price<=0 must abort the roll — same as price=None."""
    positions = [_make_position("short_call", "NSE_FO|51405", net_qty=-65, avg_sell_price="17.12")]
    open_legs = [
        LegSpec(
            instrument_key="NSE_FO|51999",
            action="SELL",
            quantity=65,
            leg_role="short_call",
            notes="roll_open_short delta=0.15",
            price=Decimal("0"),
        )
    ]

    inserted = _run(
        roll_ic_legs(
            broker=mock_broker,
            store=mock_store,
            close_positions=positions,
            closed_roles={"short_call"},
            open_legs=open_legs,
            strategy_name=_STRATEGY,
            notes="test roll",
        )
    )

    assert inserted == []
    mock_store.record_trades.assert_not_called()


def test_roll_open_only_when_closed_roles_match_nothing_returns_empty(
    mock_broker: MagicMock, mock_store: MagicMock
) -> None:
    """BUG-025 W1: closed_roles matches zero live positions but open_legs is
    non-empty — must fail-closed (return [], write nothing) instead of writing
    an orphan open leg with nothing closed."""
    # short_call is flat (net_qty=0) so it never matches closed_roles below —
    # mirrors a stale role / already-closed leg from a race.
    positions = [_make_position("short_call", "NSE_FO|51405", net_qty=0)]
    open_legs = [
        LegSpec(
            instrument_key="NSE_FO|51999",
            action="SELL",
            quantity=65,
            leg_role="short_call",
            notes="roll_open_short delta=0.15",
            price=Decimal("12.50"),
        )
    ]

    inserted = _run(
        roll_ic_legs(
            broker=mock_broker,
            store=mock_store,
            close_positions=positions,
            closed_roles={"short_call"},
            open_legs=open_legs,
            strategy_name=_STRATEGY,
            notes="test roll",
        )
    )

    assert inserted == []
    mock_store.record_trades.assert_not_called()


def test_roll_close_only_still_writes_when_to_close_nonempty(
    mock_broker: MagicMock, mock_store: MagicMock
) -> None:
    """Sanity check for the B025.2 guard's boundary: a close-only roll (no
    open_legs) must still write — only open-only writes are rejected."""
    positions = [_make_position("short_call", "NSE_FO|51405", net_qty=-65, avg_sell_price="17.12")]

    inserted = _run(
        roll_ic_legs(
            broker=mock_broker,
            store=mock_store,
            close_positions=positions,
            closed_roles={"short_call"},
            open_legs=[],
            strategy_name=_STRATEGY,
            notes="test roll",
        )
    )

    assert len(inserted) == 1
    mock_store.record_trades.assert_called_once()


def test_roll_nothing_to_close_and_nothing_to_open_returns_empty(
    mock_broker: MagicMock, mock_store: MagicMock
) -> None:
    """No open positions for the requested roles and no legs to open → no-op."""
    positions = [_make_position("short_call", "NSE_FO|51405", net_qty=0)]

    inserted = _run(
        roll_ic_legs(
            broker=mock_broker,
            store=mock_store,
            close_positions=positions,
            closed_roles={"short_call"},
            open_legs=[],
            strategy_name=_STRATEGY,
            notes="nothing to roll",
        )
    )

    assert inserted == []
    mock_store.record_trades.assert_not_called()
