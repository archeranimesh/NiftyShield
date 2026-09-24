"""Tests for src.mvp.tracker."""

from decimal import Decimal

from src.mvp.models import Pick, PickStatus
from src.mvp.tracker import MVPEvent, check_prices, format_hourly_summary

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
    reco_price: Decimal | None = None,
    avg_cost: Decimal | None = None,
    total_qty: int = 0,
) -> Pick:
    return Pick(
        pick_id=pick_id,
        symbol=symbol,
        instrument_key=instrument_key,
        entry_price=entry_price,
        reco_price=reco_price,
        pick_date="2026-09-01",
        target_price=target_price,
        stop_loss=stop_loss,
        status=status,
        category_id=category_id,
        avg_cost=avg_cost,
        total_qty=total_qty,
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


def test_format_hourly_summary_empty_picks_returns_empty_string() -> None:
    assert format_hourly_summary([], {}, "11:00 AM") == ""


def test_format_hourly_summary_open_pick_pnl_and_next_columns() -> None:
    pick = _make_pick(
        symbol="RELIANCE",
        instrument_key="NSE_EQ|RELIANCE",
        avg_cost=Decimal("1200"),
        total_qty=83,
        target_price=Decimal("1500"),
        stop_loss=Decimal("1100"),
    )
    ltp_map = {"NSE_EQ|RELIANCE": Decimal("1401")}

    summary = format_hourly_summary([pick], ltp_map, "11:00 AM")

    assert "[O]" in summary
    fence_body = summary.split("```")[1]
    assert "RELIANCE" in fence_body
    assert "+16683" in fence_body  # (1401-1200)*83
    assert "Open: 1   Pending: 0" in summary


def test_format_hourly_summary_pending_pick_shows_trigger_and_dashes() -> None:
    pick = _make_pick(
        status=PickStatus.PENDING,
        symbol="INFY",
        entry_price=None,
        reco_price=Decimal("1750"),
    )

    summary = format_hourly_summary([pick], {}, "11:00 AM")

    assert "[P]" in summary
    fence_body = summary.split("```")[1]
    assert "INFY" in fence_body
    assert "→1750" in fence_body
    assert "Open: 0   Pending: 1" in summary


def test_format_hourly_summary_negative_pnl_shown_unsigned_prefix() -> None:
    pick = _make_pick(
        symbol="WIPRO",
        instrument_key="NSE_EQ|WIPRO",
        avg_cost=Decimal("468"),
        total_qty=210,
    )
    ltp_map = {"NSE_EQ|WIPRO": Decimal("402.15")}

    summary = format_hourly_summary([pick], ltp_map, "11:00 AM")

    fence_body = summary.split("```")[1]
    assert "-13828.5" in fence_body  # (402.15-468)*210
    assert "🔴" in summary


def test_format_hourly_summary_missing_ltp_renders_dashes() -> None:
    pick = _make_pick(
        symbol="TCS",
        instrument_key="NSE_EQ|TCS",
        avg_cost=Decimal("3408.50"),
        total_qty=29,
    )

    summary = format_hourly_summary([pick], {}, "11:00 AM")

    fence_body = summary.split("```")[1]
    row = [line for line in fence_body.splitlines() if "TCS" in line][0]
    assert row.count("—") == 3  # LTP, P&L, Next all unresolvable

    # no ltp -> current falls back flat to invested, so P&L footer reads ₹0.00
    assert "*P&L:* ₹0\\.00" in summary
