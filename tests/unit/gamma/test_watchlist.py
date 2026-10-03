"""Unit tests for the pure watchlist rules in src/gamma/watchlist.py."""

from __future__ import annotations

import datetime
from decimal import Decimal

from src.gamma.models import GammaChainSnapshot, GammaWatchlistEntry
from src.gamma.watchlist import evaluate_watchlist

TODAY = datetime.date(2026, 5, 26)
EXPIRY = datetime.date(2026, 5, 29)
D1 = datetime.date(2026, 5, 25)
D2 = datetime.date(2026, 5, 22)
D3 = datetime.date(2026, 5, 21)


def _snap(
    day: datetime.date = TODAY,
    strike: int = 25000,
    dte: int = 3,
    distance: str | None = "0.02",
    gearing: str | None = "4.0",
    oi: int | None = 5000,
    oi_change: str | None = "0.05",
    expiry: datetime.date = EXPIRY,
) -> GammaChainSnapshot:
    return GammaChainSnapshot(
        snapshot_date=day,
        snapshot_time="15:20",
        expiry_date=expiry,
        strike=strike,
        option_type="CE",
        dte_calendar=dte,
        nifty_spot=Decimal("25000"),
        nifty_futures=None,
        india_vix=None,
        delta_val=None,
        gamma_val=None,
        vega_val=None,
        theta_val=None,
        iv_val=None,
        gamma_gearing=Decimal(gearing) if gearing is not None else None,
        distance_pct=Decimal(distance) if distance is not None else None,
        best_bid=None,
        best_ask=None,
        bid_ask_spread=None,
        oi=oi,
        oi_change_1d=Decimal(oi_change) if oi_change is not None else None,
        volume_day=None,
        strike_iv_pctile_20d=None,
        gamma_gearing_pctile_dte=None,
        created_at=datetime.datetime(2026, 5, 26, 9, 50, tzinfo=datetime.timezone.utc),
    )


def _entry(
    expiry: datetime.date = EXPIRY, strike: int = 25000, added: datetime.date = D1
) -> GammaWatchlistEntry:
    return GammaWatchlistEntry(
        expiry_date=expiry,
        strike=strike,
        option_type="CE",
        added_date=added,
        last_seen_date=D1,
        removed_date=None,
        removal_reason=None,
        distance_pct=Decimal("0.02"),
        gamma_gearing=Decimal("4.0"),
        oi=5000,
        oi_change_1d=Decimal("0"),
        days_on_watchlist=1,
        elevated=False,
        elevation_reason=None,
    )


def test_watchlist_add_qualifying_strike() -> None:
    d = evaluate_watchlist([_snap()], [], [], TODAY)
    assert [(e.strike, e.added_date) for e in d.add] == [(25000, TODAY)]
    assert d.retain == () and d.remove == () and d.elevate == ()


def test_watchlist_skip_low_gearing() -> None:
    d = evaluate_watchlist([_snap(gearing="2.5")], [], [], TODAY)
    assert d.add == ()


def test_watchlist_skip_none_gearing_oi_but_none_oi_change_passes() -> None:
    assert evaluate_watchlist([_snap(gearing=None)], [], [], TODAY).add == ()
    assert evaluate_watchlist([_snap(oi=None)], [], [], TODAY).add == ()
    assert len(evaluate_watchlist([_snap(oi_change=None)], [], [], TODAY).add) == 1


def test_watchlist_skip_dte_outside_window() -> None:
    assert evaluate_watchlist([_snap(dte=1)], [], [], TODAY).add == ()
    assert evaluate_watchlist([_snap(dte=7)], [], [], TODAY).add == ()


def test_watchlist_retains_entry_that_stops_qualifying() -> None:
    snap = _snap(dte=1, gearing="1.0")
    d = evaluate_watchlist([snap], [], [_entry()], TODAY)
    assert d.add == () and d.remove == ()
    (kept,) = d.retain
    assert kept.last_seen_date == TODAY and kept.added_date == D1
    assert kept.gamma_gearing == Decimal("1.0") and kept.days_on_watchlist == 2


def test_watchlist_removal_spot_moved_two_days() -> None:
    today = _snap(distance="0.06")
    hist = [_snap(day=D1, distance="0.07")]
    d = evaluate_watchlist([today], hist, [_entry()], TODAY)
    assert [r.removal_reason for r in d.remove] == ["spot_moved_away"]
    assert d.retain == ()


def test_watchlist_no_removal_on_single_day_breach() -> None:
    d = evaluate_watchlist(
        [_snap(distance="0.06")], [_snap(day=D1, distance="0.04")], [_entry()], TODAY
    )
    assert d.remove == () and len(d.retain) == 1


def test_watchlist_no_removal_when_yesterday_missing() -> None:
    hist = [_snap(day=D1, strike=25100, distance="0.07")]
    d = evaluate_watchlist([_snap(distance="0.06")], hist, [_entry()], TODAY)
    assert d.remove == ()


def test_watchlist_removal_oi_unwinding_two_days() -> None:
    d = evaluate_watchlist(
        [_snap(oi_change="-0.25")], [_snap(day=D1, oi_change="-0.30")], [_entry()], TODAY
    )
    assert [r.removal_reason for r in d.remove] == ["oi_unwinding"]


def test_watchlist_expired_removal_covers_entries_without_snapshot() -> None:
    old = _entry(expiry=datetime.date(2026, 5, 19), strike=24900)
    d = evaluate_watchlist([_snap()], [], [old], TODAY)
    assert [(r.strike, r.removal_reason) for r in d.remove] == [(24900, "expired")]


def test_watchlist_entry_for_other_live_expiry_without_snapshot_untouched() -> None:
    other = _entry(expiry=datetime.date(2026, 6, 2), strike=24900)
    d = evaluate_watchlist([], [], [other], TODAY)
    assert d.remove == () and d.retain == ()


def _elevation_history(gearing: str = "3.0") -> list[GammaChainSnapshot]:
    return [
        _snap(day=D1, distance="0.025", gearing=gearing),
        _snap(day=D2, distance="0.03", gearing=gearing),
        _snap(day=D3, distance="0.03", gearing=gearing),
    ]


def test_watchlist_elevation() -> None:
    d = evaluate_watchlist([_snap(oi_change="0.15")], _elevation_history(), [], TODAY)
    assert len(d.add) == 1 and d.add[0].elevated and d.elevate == d.add


def test_watchlist_no_elevation_without_three_prior_dates() -> None:
    d = evaluate_watchlist([_snap(oi_change="0.15")], _elevation_history()[:2], [], TODAY)
    assert len(d.add) == 1 and d.elevate == ()


def test_watchlist_no_elevation_when_oi_change_none_or_gearing_flat() -> None:
    assert (
        evaluate_watchlist([_snap(oi_change=None)], _elevation_history(), [], TODAY).elevate == ()
    )
    flat = evaluate_watchlist(
        [_snap(gearing="3.0", oi_change="0.15")], _elevation_history(), [], TODAY
    )
    assert flat.elevate == ()


def test_watchlist_elevation_is_recomputed_not_sticky() -> None:
    prev = _entry()
    d = evaluate_watchlist([_snap(oi_change="0.05")], _elevation_history(), [prev], TODAY)
    assert len(d.retain) == 1 and not d.retain[0].elevated
