"""Tests for src.mvp.tracker."""

from decimal import Decimal

from src.mvp.models import Category, CategoryStats, Pick, PickStatus
from src.mvp.tracker import (
    CategoryRollup,
    MVPEvent,
    ProviderRollup,
    build_category_rollup,
    build_eod_table,
    category_short_code,
    check_prices,
    compute_overall_inception_pct,
    format_eod_summary,
    format_hourly_summary,
)

_NOW = "2026-09-23T00:00:00"


def _make_category(
    *,
    category_id: str = "cat-1",
    provider_id: str = "prov-1",
    slug: str = "value_picks",
    display_name: str = "Value Picks",
) -> Category:
    return Category(
        category_id=category_id,
        provider_id=provider_id,
        slug=slug,
        display_name=display_name,
        created_at=_NOW,
    )


def _make_stats(
    *,
    closed_count: int = 3,
    wins: int = 2,
    losses: int = 1,
    win_rate: Decimal | None = Decimal("0.6667"),
    inception_pnl: Decimal = Decimal("5000"),
    invested: Decimal = Decimal("100000"),
    current: Decimal = Decimal("110000"),
    inception_pct: Decimal | None = Decimal("15"),
) -> CategoryStats:
    return CategoryStats(
        closed_count=closed_count,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        avg_win=Decimal("3000"),
        avg_loss=Decimal("-1000"),
        inception_pnl=inception_pnl,
        invested=invested,
        current=current,
        inception_pct=inception_pct,
    )


def _make_rollup(
    *,
    display_name: str = "Value Picks",
    short_code: str = "VP",
    invested: Decimal = Decimal("100000"),
    current: Decimal = Decimal("110000"),
    realized_pnl: Decimal = Decimal("5000"),
    day_chg_pct: Decimal | None = Decimal("1.5"),
    win_pct: Decimal | None = Decimal("67"),
    win_closed_count: int = 3,
    inception_pct: Decimal = Decimal("15"),
    high_pct: Decimal | None = Decimal("20"),
    low_pct: Decimal | None = Decimal("-5"),
    open_count: int = 2,
    pending_count: int = 1,
    closed_count: int = 3,
) -> CategoryRollup:
    return CategoryRollup(
        display_name=display_name,
        short_code=short_code,
        invested=invested,
        current=current,
        realized_pnl=realized_pnl,
        day_chg_pct=day_chg_pct,
        win_pct=win_pct,
        win_closed_count=win_closed_count,
        inception_pct=inception_pct,
        high_pct=high_pct,
        low_pct=low_pct,
        open_count=open_count,
        pending_count=pending_count,
        closed_count=closed_count,
    )


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


def test_category_short_code_multi_word_slug_uses_initials() -> None:
    assert category_short_code("value_picks") == "VP"


def test_category_short_code_single_word_slug_truncates() -> None:
    assert category_short_code("multibagger") == "MUL"


def test_category_short_code_hyphen_separated_slug() -> None:
    assert category_short_code("long-term-picks") == "LTP"


def test_category_short_code_single_char_slug() -> None:
    assert category_short_code("a") == "A"


def test_build_eod_table_empty_providers_returns_empty_string() -> None:
    assert build_eod_table([]) == ""
    empty_provider = ProviderRollup(provider_name="DSIJ", short_code="DSIJ", categories=[])
    assert build_eod_table([empty_provider]) == ""


def test_build_category_rollup_happy_path() -> None:
    category = _make_category()
    stats = _make_stats()
    rollup = build_category_rollup(
        category,
        stats,
        day_chg_pct=Decimal("1.5"),
        high_low=(Decimal("20"), Decimal("-5")),
        open_count=2,
        pending_count=1,
        closed_count=3,
    )
    assert rollup.short_code == "VP"
    assert rollup.win_pct == Decimal("66.67")
    assert rollup.high_pct == Decimal("20")
    assert rollup.low_pct == Decimal("-5")
    assert rollup.inception_pct == Decimal("15")


def test_build_category_rollup_none_day_change_and_high_low() -> None:
    category = _make_category()
    stats = _make_stats(closed_count=0, wins=0, losses=0, win_rate=None, inception_pnl=Decimal("0"))
    rollup = build_category_rollup(
        category,
        stats,
        day_chg_pct=None,
        high_low=None,
        open_count=1,
        pending_count=0,
        closed_count=0,
    )
    assert rollup.day_chg_pct is None
    assert rollup.win_pct is None
    assert rollup.high_pct is None
    assert rollup.low_pct is None


def test_build_eod_table_renders_dashes_for_missing_high_low() -> None:
    rollup = _make_rollup(win_pct=None, win_closed_count=0, high_pct=None, low_pct=None)
    table = build_eod_table(
        [ProviderRollup(provider_name="DSIJ", short_code="DSIJ", categories=[rollup])]
    )
    row = table.splitlines()[2]
    assert "— (0)" in row
    # win_str's "—" plus one each for the High/Low columns
    assert row.count("—") == 3


def test_format_eod_summary_empty_providers_returns_empty_string() -> None:
    assert format_eod_summary([], "2026-09-24", Decimal("0")) == ""


def test_format_eod_summary_happy_path_includes_table_and_footer() -> None:
    providers = [
        ProviderRollup(provider_name="DSIJ", short_code="DSIJ", categories=[_make_rollup()])
    ]
    summary = format_eod_summary(providers, "2026-09-24", Decimal("15"))
    assert "*MVP EOD Summary*" in summary
    assert "VP" in summary
    assert "*Since inception:* \\+15\\.0%" in summary
    assert "Open: 2   Pending: 1   Closed: 3" in summary


def test_format_eod_summary_day_chg_none_when_no_category_has_one() -> None:
    providers = [
        ProviderRollup(
            provider_name="DSIJ", short_code="DSIJ", categories=[_make_rollup(day_chg_pct=None)]
        )
    ]
    summary = format_eod_summary(providers, "2026-09-24", Decimal("15"))
    assert "*Day chg:* —" in summary


def test_compute_overall_inception_pct_zero_deployed_returns_zero() -> None:
    assert compute_overall_inception_pct([_make_rollup()], Decimal("0")) == Decimal("0")


def test_compute_overall_inception_pct_happy_path() -> None:
    # rollup: current-invested + realized = (110000-100000)+5000 = 15000
    result = compute_overall_inception_pct([_make_rollup()], Decimal("100000"))
    assert result == Decimal("15")
