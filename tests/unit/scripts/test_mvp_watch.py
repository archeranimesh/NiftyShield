"""Tests for scripts/mvp_watch.py's category win-rate/inception stats line (M11)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from scripts.mvp_watch import _category_stats_line, _format_alert_message
from src.mvp.models import CategoryStats, ClosePickResult, Pick, PickStatus
from src.mvp.tracker import MVPEvent


def _make_pick() -> Pick:
    return Pick(
        pick_id="pick-1",
        category_id="cat-1",
        symbol="TCS",
        pick_date=(date.today() - timedelta(days=3)).isoformat(),
        created_at="2026-09-22T00:00:00Z",
        updated_at="2026-09-22T00:00:00Z",
    )


def _make_event() -> MVPEvent:
    return MVPEvent(
        pick_id="pick-1",
        symbol="TCS",
        event_type=PickStatus.TARGET_HIT,
        trigger_price=Decimal("3800"),
        entry_price=Decimal("3508.75"),
    )


def _make_close() -> ClosePickResult:
    return ClosePickResult(
        realized_pnl=Decimal("7000"),
        total_qty=28,
        deployed_capital=Decimal("98000"),
        avg_cost=Decimal("3508.75"),
    )


def _make_stats(closed_count: int = 5, wins: int = 3, losses: int = 2) -> CategoryStats:
    return CategoryStats(
        closed_count=closed_count,
        wins=wins,
        losses=losses,
        win_rate=Decimal("0.6"),
        avg_win=Decimal("5000"),
        avg_loss=Decimal("-2000"),
        inception_pnl=Decimal("11000"),
    )


def test_category_stats_line_shown_at_five_closed() -> None:
    line = _category_stats_line(_make_stats(closed_count=5))

    assert line is not None
    assert "60%" in line
    assert "3W" in line and "2L" in line


def test_category_stats_line_hidden_below_five_closed() -> None:
    assert _category_stats_line(_make_stats(closed_count=4, wins=2, losses=2)) is None


def test_category_stats_line_hidden_when_stats_none() -> None:
    assert _category_stats_line(None) is None


def test_format_alert_message_appends_stats_line_when_present() -> None:
    message = _format_alert_message(
        _make_event(), _make_pick(), _make_close(), "DSIJ / Value Picks", _make_stats()
    )

    assert "Win rate" in message


def test_format_alert_message_omits_stats_line_when_none() -> None:
    message = _format_alert_message(
        _make_event(), _make_pick(), _make_close(), "DSIJ / Value Picks", None
    )

    assert "Win rate" not in message
