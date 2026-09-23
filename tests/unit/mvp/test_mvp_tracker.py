"""Tests for src.mvp.tracker."""

from decimal import Decimal

from src.mvp.models import Pick, PickStatus
from src.mvp.tracker import MVPEvent, check_prices

_NOW = "2026-09-23T00:00:00"


def _make_pick(
    *,
    pick_id: str = "P1",
    symbol: str = "TCS",
    instrument_key: str | None = "NSE_EQ|TCS",
    status: PickStatus = PickStatus.OPEN,
    target_price: Decimal | None = Decimal("100"),
    stop_loss: Decimal | None = Decimal("50"),
    entry_price: Decimal | None = Decimal("75"),
) -> Pick:
    return Pick(
        pick_id=pick_id,
        symbol=symbol,
        instrument_key=instrument_key,
        entry_price=entry_price,
        pick_date="2026-09-01",
        target_price=target_price,
        stop_loss=stop_loss,
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
    )


def test_check_prices_target_hit() -> None:
    pick = _make_pick()
    events = check_prices([pick], {"NSE_EQ|TCS": Decimal("100")})

    assert events == [
        MVPEvent(
            pick_id="P1",
            symbol="TCS",
            event_type=PickStatus.TARGET_HIT,
            trigger_price=Decimal("100"),
            entry_price=Decimal("75"),
        )
    ]


def test_check_prices_sl_hit() -> None:
    pick = _make_pick()
    events = check_prices([pick], {"NSE_EQ|TCS": Decimal("50")})

    assert events == [
        MVPEvent(
            pick_id="P1",
            symbol="TCS",
            event_type=PickStatus.SL_HIT,
            trigger_price=Decimal("50"),
            entry_price=Decimal("75"),
        )
    ]


def test_check_prices_no_breach() -> None:
    pick = _make_pick()
    events = check_prices([pick], {"NSE_EQ|TCS": Decimal("75")})

    assert events == []


def test_check_prices_null_target_evaluates_sl_only() -> None:
    pick = _make_pick(target_price=None, stop_loss=Decimal("50"))
    events = check_prices([pick], {"NSE_EQ|TCS": Decimal("50")})

    assert len(events) == 1
    assert events[0].event_type == PickStatus.SL_HIT


def test_check_prices_null_sl_evaluates_target_only() -> None:
    pick = _make_pick(target_price=Decimal("100"), stop_loss=None)
    events = check_prices([pick], {"NSE_EQ|TCS": Decimal("100")})

    assert len(events) == 1
    assert events[0].event_type == PickStatus.TARGET_HIT


def test_check_prices_both_null_no_events() -> None:
    pick = _make_pick(target_price=None, stop_loss=None)
    events = check_prices([pick], {"NSE_EQ|TCS": Decimal("1000")})

    assert events == []


def test_check_prices_pending_pick_excluded() -> None:
    pick = _make_pick(status=PickStatus.PENDING)
    events = check_prices([pick], {"NSE_EQ|TCS": Decimal("100")})

    assert events == []


def test_check_prices_instrument_key_not_in_ltp_map_skipped() -> None:
    pick = _make_pick(instrument_key="NSE_EQ|OTHER")
    events = check_prices([pick], {"NSE_EQ|TCS": Decimal("100")})

    assert events == []


def test_check_prices_null_instrument_key_skipped() -> None:
    pick = _make_pick(instrument_key=None)
    events = check_prices([pick], {"NSE_EQ|TCS": Decimal("100")})

    assert events == []
