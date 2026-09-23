"""Tests for src.mvp.tracker."""

from decimal import Decimal

from src.mvp.models import Pick, PickStatus
from src.mvp.tracker import MVPEvent, check_prices, format_telegram_summary

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
    category_id: str | None = None,
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
        category_id=category_id,
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


def test_format_telegram_summary_empty_picks_returns_empty_string() -> None:
    assert format_telegram_summary([], {}, {}, {}, "11:00 AM") == ""


def test_format_telegram_summary_groups_two_picks_same_category() -> None:
    pick_a = _make_pick(
        pick_id="P1", symbol="RELIANCE", instrument_key="NSE_EQ|RELIANCE", category_id="C1"
    )
    pick_b = _make_pick(pick_id="P2", symbol="TCS", instrument_key="NSE_EQ|TCS", category_id="C1")
    ltp_map = {"NSE_EQ|RELIANCE": Decimal("100"), "NSE_EQ|TCS": Decimal("100")}
    categories = {"C1": "DSIJ / Value Picks"}

    summary = format_telegram_summary([pick_a, pick_b], ltp_map, {}, categories, "11:00 AM")

    assert "DSIJ / Value Picks" in summary
    fence_body = summary.split("```")[1]
    assert "RELIANCE" in fence_body
    assert "TCS" in fence_body


def test_format_telegram_summary_pending_pick_in_unassigned_block() -> None:
    pick = _make_pick(status=PickStatus.PENDING, entry_price=None, symbol="HDFC")

    summary = format_telegram_summary([pick], {}, {}, {}, "11:00 AM")

    assert "Unassigned" in summary
    assert "HDFC" in summary


def test_format_telegram_summary_positive_pnl_has_plus_prefix() -> None:
    pick = _make_pick(
        symbol="TCS", instrument_key="NSE_EQ|TCS", entry_price=Decimal("100"), category_id="C1"
    )
    summary = format_telegram_summary(
        [pick], {"NSE_EQ|TCS": Decimal("120")}, {}, {"C1": "Cat"}, "11:00 AM"
    )

    assert "+20" in summary


def test_format_telegram_summary_negative_pnl_has_minus_prefix() -> None:
    pick = _make_pick(
        symbol="TCS", instrument_key="NSE_EQ|TCS", entry_price=Decimal("100"), category_id="C1"
    )
    summary = format_telegram_summary(
        [pick], {"NSE_EQ|TCS": Decimal("80")}, {}, {"C1": "Cat"}, "11:00 AM"
    )

    assert "-20" in summary


def test_format_telegram_summary_pending_with_entry_and_category_still_unassigned() -> None:
    pick = _make_pick(
        status=PickStatus.PENDING,
        symbol="HDFC",
        entry_price=Decimal("100"),
        category_id="C1",
    )

    summary = format_telegram_summary([pick], {}, {}, {"C1": "DSIJ / Value Picks"}, "11:00 AM")

    assert "Unassigned" in summary
    assert "HDFC" in summary
    assert "DSIJ / Value Picks" not in summary


def test_format_telegram_summary_null_target_omits_target_line() -> None:
    pick = _make_pick(
        symbol="TCS",
        instrument_key="NSE_EQ|TCS",
        entry_price=Decimal("100"),
        target_price=None,
        stop_loss=None,
        category_id="C1",
    )
    summary = format_telegram_summary(
        [pick], {"NSE_EQ|TCS": Decimal("100")}, {}, {"C1": "Cat"}, "11:00 AM"
    )

    assert "T:" not in summary
