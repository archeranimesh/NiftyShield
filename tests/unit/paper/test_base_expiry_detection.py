from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import scripts.strategies.three_track.paper_3track_snapshot as snap_mod
from src.instruments.lookup import InstrumentLookup
from src.paper.models import PaperPosition
from src.paper.store import PaperStore


def _make_store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "test.db")


def test_get_next_contract() -> None:
    instruments = [
        {
            "instrument_key": "NSE_FO|NIFTY26JUNFUT",
            "underlying_symbol": "NIFTY",
            "instrument_type": "FUT",
            "expiry": "2026-06-25",
        },
        {
            "instrument_key": "NSE_FO|NIFTY26JULFUT",
            "underlying_symbol": "NIFTY",
            "instrument_type": "FUT",
            "expiry": "2026-07-30",
        },
        {
            "instrument_key": "NSE_FO|NIFTY26AUGFUT",
            "underlying_symbol": "NIFTY",
            "instrument_type": "FUT",
            "expiry": "2026-08-27",
        },
        {
            "instrument_key": "NSE_FO|NIFTY26JUN23000CE",
            "underlying_symbol": "NIFTY",
            "instrument_type": "CE",
            "strike_price": 23000.0,
            "expiry": "2026-06-25",
        },
        {
            "instrument_key": "NSE_FO|NIFTY26JUL23000CE",
            "underlying_symbol": "NIFTY",
            "instrument_type": "CE",
            "strike_price": 23000.0,
            "expiry": "2026-07-30",
        },
    ]
    lookup = InstrumentLookup(instruments)

    # FUT happy path
    next_fut = lookup.get_next_contract("NSE_FO|NIFTY26JUNFUT")
    assert next_fut is not None
    assert next_fut["instrument_key"] == "NSE_FO|NIFTY26JULFUT"

    # Option happy path (same strike)
    next_ce = lookup.get_next_contract("NSE_FO|NIFTY26JUN23000CE")
    assert next_ce is not None
    assert next_ce["instrument_key"] == "NSE_FO|NIFTY26JUL23000CE"

    # Current contract not found
    assert lookup.get_next_contract("NSE_FO|INVALID") is None

    # Next contract not found
    assert lookup.get_next_contract("NSE_FO|NIFTY26AUGFUT") is None


@pytest.mark.asyncio
async def test_check_base_expiry_alerts(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    today = date(2026, 6, 21)

    instruments = [
        {
            "instrument_key": "NSE_FO|NIFTY26JUNFUT",
            "underlying_symbol": "NIFTY",
            "instrument_type": "FUT",
            "expiry": "2026-06-25",
            "trading_symbol": "NIFTY JUN FUT",
        },
        {
            "instrument_key": "NSE_FO|NIFTY26JULFUT",
            "underlying_symbol": "NIFTY",
            "instrument_type": "FUT",
            "expiry": "2026-07-30",
            "trading_symbol": "NIFTY JUL FUT",
        },
        {
            "instrument_key": "NSE_FO|NIFTY26JUN23000CE",
            "underlying_symbol": "NIFTY",
            "instrument_type": "CE",
            "strike_price": 23000.0,
            "expiry": "2026-06-25",
            "trading_symbol": "NIFTY JUN 23000 CE",
        },
        {
            "instrument_key": "NSE_FO|NIFTY26JUL23000CE",
            "underlying_symbol": "NIFTY",
            "instrument_type": "CE",
            "strike_price": 23000.0,
            "expiry": "2026-07-30",
            "trading_symbol": "NIFTY JUL 23000 CE",
        },
    ]
    lookup = InstrumentLookup(instruments)

    # 1. Base futures at 4 DTE (today=June 21, expiry=June 25 -> 4 DTE) -> Alert fires
    pos_fut = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JUNFUT",
    )

    # 2. Base ditm call at 4 DTE -> Alert fires
    pos_ce = PaperPosition(
        strategy_name="paper_nifty_proxy",
        leg_role="base_ditm_call",
        net_qty=50,
        avg_cost=Decimal("1000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JUN23000CE",
    )

    # 3. Base futures at 9 DTE -> No alert
    pos_fut_far = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",  # expiry is July 30 -> 39 DTE
    )

    # 4. ETF leg -> Excluded
    pos_etf = PaperPosition(
        strategy_name="paper_nifty_spot",
        leg_role="base_etf",
        net_qty=100,
        avg_cost=Decimal("240.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_EQ|NIFTYBEES",
    )

    notifier = MagicMock()
    notifier.send = AsyncMock()

    positions = [pos_fut, pos_ce, pos_fut_far, pos_etf]
    await snap_mod._check_base_expiry(
        positions=positions,
        instruments=lookup,
        today=today,
        store=store,
        notifier=notifier,
    )

    # Verify events in DB
    events = store.get_open_exit_events()
    assert len(events) == 2
    signals = [e["exit_signal"] for e in events]
    assert all(s == "BASE_EXPIRY_ALERT" for s in signals)

    # Verify notifier was called twice
    assert notifier.send.call_count == 2
    calls = [c.args[0] for c in notifier.send.call_args_list]
    assert any("base_futures" in c for c in calls)
    assert any("base_ditm_call" in c for c in calls)


@pytest.mark.asyncio
async def test_check_base_expiry_ditm_call_skips_weekly(tmp_path: Path) -> None:
    """base_ditm_call must roll to the next monthly, not the intervening weekly."""
    store = _make_store(tmp_path)
    today = date(2026, 6, 21)

    instruments = [
        {
            "instrument_key": "NSE_FO|NIFTY26JUN23000CE",
            "underlying_symbol": "NIFTY",
            "instrument_type": "CE",
            "strike_price": 23000.0,
            "expiry": "2026-06-25",  # expiring, 4 DTE
            "trading_symbol": "NIFTY JUN 23000 CE",
            "segment": "NSE_FO",
        },
        {
            "instrument_key": "NSE_FO|NIFTY26JUN30W23000CE",
            "underlying_symbol": "NIFTY",
            "instrument_type": "CE",
            "strike_price": 23000.0,
            "expiry": "2026-06-30",  # weekly, same strike — must NOT be selected
            "trading_symbol": "NIFTY JUN30 23000 CE",
            "segment": "NSE_FO",
        },
        {
            "instrument_key": "NSE_FO|NIFTY26JUL23000CE",
            "underlying_symbol": "NIFTY",
            "instrument_type": "CE",
            "strike_price": 23000.0,
            "expiry": "2026-07-30",  # next monthly — correct pick
            "trading_symbol": "NIFTY JUL 23000 CE",
            "segment": "NSE_FO",
        },
    ]
    lookup = InstrumentLookup(instruments)

    pos_ce = PaperPosition(
        strategy_name="paper_nifty_proxy",
        leg_role="base_ditm_call",
        net_qty=50,
        avg_cost=Decimal("1000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JUN23000CE",
    )

    notifier = MagicMock()
    notifier.send = AsyncMock()

    await snap_mod._check_base_expiry(
        positions=[pos_ce],
        instruments=lookup,
        today=today,
        store=store,
        notifier=notifier,
    )

    assert notifier.send.call_count == 1
    alert_msg = notifier.send.call_args[0][0]
    assert "NSE_FO|NIFTY26JUL23000CE" in alert_msg
    assert "NSE_FO|NIFTY26JUN30W23000CE" not in alert_msg


@pytest.mark.asyncio
async def test_check_base_expiry_idempotency(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    today = date(2026, 6, 21)
    instruments = [
        {
            "instrument_key": "NSE_FO|NIFTY26JUNFUT",
            "underlying_symbol": "NIFTY",
            "instrument_type": "FUT",
            "expiry": "2026-06-25",
        }
    ]
    lookup = InstrumentLookup(instruments)
    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JUNFUT",
    )

    notifier = MagicMock()
    notifier.send = AsyncMock()

    # First check -> alert written
    await snap_mod._check_base_expiry([pos], lookup, today, store, notifier)
    assert len(store.get_open_exit_events()) == 1
    assert notifier.send.call_count == 1

    # Second check same day -> skipped (idempotent)
    await snap_mod._check_base_expiry([pos], lookup, today, store, notifier)
    assert len(store.get_open_exit_events()) == 1
    assert notifier.send.call_count == 1


@pytest.mark.asyncio
async def test_check_base_expiry_next_contract_not_found(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    today = date(2026, 6, 21)
    # Only the expiring contract in BOD
    instruments = [
        {
            "instrument_key": "NSE_FO|NIFTY26JUNFUT",
            "underlying_symbol": "NIFTY",
            "instrument_type": "FUT",
            "expiry": "2026-06-25",
        }
    ]
    lookup = InstrumentLookup(instruments)
    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JUNFUT",
    )

    notifier = MagicMock()
    notifier.send = AsyncMock()

    await snap_mod._check_base_expiry([pos], lookup, today, store, notifier)

    assert len(store.get_open_exit_events()) == 1
    assert notifier.send.call_count == 1
    alert_msg = notifier.send.call_args[0][0]
    assert "WARNING: BOD may be stale" in alert_msg
    assert "<NEXT_CONTRACT_KEY>" in alert_msg


@pytest.mark.asyncio
async def test_check_base_expiry_notifier_failure(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    today = date(2026, 6, 21)
    instruments = [
        {
            "instrument_key": "NSE_FO|NIFTY26JUNFUT",
            "underlying_symbol": "NIFTY",
            "instrument_type": "FUT",
            "expiry": "2026-06-25",
        }
    ]
    lookup = InstrumentLookup(instruments)
    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JUNFUT",
    )

    notifier = MagicMock()
    notifier.send = AsyncMock(side_effect=Exception("Telegram down"))

    # Notifier raises -> event still written, does not propagate error
    await snap_mod._check_base_expiry([pos], lookup, today, store, notifier)
    assert len(store.get_open_exit_events()) == 1
