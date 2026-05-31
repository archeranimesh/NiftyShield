"""Unit tests for scripts/gamma_daily_watch.py."""

from __future__ import annotations

import sys
from datetime import date
from unittest.mock import patch

from scripts.pipeline.gamma_daily_watch import main, resolve_expiries


def test_resolve_expiries_mid_week() -> None:
    """On Monday, resolve_expiries returns this Thursday and next Thursday."""
    # 2026-04-20 is Monday
    # 2026-04-23 is Thursday
    # 2026-04-30 is Thursday
    today = date(2026, 4, 20)

    with patch("scripts.pipeline.gamma_daily_watch.is_trading_day", return_value=True):
        curr_exp, next_exp = resolve_expiries(today)
        assert curr_exp == date(2026, 4, 23)
        assert next_exp == date(2026, 4, 30)


def test_resolve_expiries_on_thursday_open() -> None:
    """On Thursday when market is open, resolve_expiries returns today and next Thursday."""
    # 2026-04-23 is Thursday
    # 2026-04-30 is Thursday
    today = date(2026, 4, 23)

    with patch("scripts.pipeline.gamma_daily_watch.is_trading_day", return_value=True):
        curr_exp, next_exp = resolve_expiries(today)
        assert curr_exp == date(2026, 4, 23)
        assert next_exp == date(2026, 4, 30)


def test_resolve_expiries_on_thursday_holiday() -> None:
    """On Thursday when market is closed, resolve_expiries returns next Thursday and week after next Thursday."""
    # 2026-04-02 is Thursday (holiday)
    # 2026-04-09 is Thursday
    # 2026-04-16 is Thursday
    today = date(2026, 4, 2)

    def mock_is_trading_day(d: date) -> bool:
        if d == date(2026, 4, 2):
            return False
        return True

    with patch(
        "scripts.pipeline.gamma_daily_watch.is_trading_day", side_effect=mock_is_trading_day
    ):
        curr_exp, next_exp = resolve_expiries(today)
        assert curr_exp == date(2026, 4, 9)
        assert next_exp == date(2026, 4, 16)


def test_resolve_expiries_thursday_is_holiday_adjusted() -> None:
    """If Thursday is a holiday, the expiry is adjusted to Wednesday (or preceding trading day)."""
    # 2026-04-02 is Thursday (holiday)
    # 2026-04-01 is Wednesday (trading day)
    # today is 2026-03-30 (Monday)
    today = date(2026, 3, 30)

    def mock_is_trading_day(d: date) -> bool:
        # April 2 is holiday
        if d == date(2026, 4, 2):
            return False
        return True

    with patch(
        "scripts.pipeline.gamma_daily_watch.is_trading_day", side_effect=mock_is_trading_day
    ):
        curr_exp, next_exp = resolve_expiries(today)
        assert curr_exp == date(2026, 4, 1)  # adjusted from April 2 to April 1
        assert next_exp == date(2026, 4, 9)


def test_resolve_expiries_friday_weekend() -> None:
    """On Friday or weekend, resolve_expiries returns next Thursday and week after next Thursday."""
    # Friday 2026-04-24 -> current-week expiry is next Thursday 2026-04-30
    # Next-week expiry is Thursday after next 2026-05-07
    today_fri = date(2026, 4, 24)
    today_sat = date(2026, 4, 25)
    today_sun = date(2026, 4, 26)

    with patch("scripts.pipeline.gamma_daily_watch.is_trading_day", return_value=True):
        for today in [today_fri, today_sat, today_sun]:
            curr_exp, next_exp = resolve_expiries(today)
            assert curr_exp == date(2026, 4, 30)
            assert next_exp == date(2026, 5, 7)


def test_resolve_expiries_multi_day_holiday_rollback() -> None:
    """If Thursday and Wednesday are holidays, expiry rolls back to Tuesday."""
    # Thursday 2026-04-02 is holiday
    # Wednesday 2026-04-01 is holiday
    # Tuesday 2026-03-31 is open
    today = date(2026, 3, 30)

    def mock_is_trading_day(d: date) -> bool:
        if d in {date(2026, 4, 2), date(2026, 4, 1)}:
            return False
        return True

    with patch(
        "scripts.pipeline.gamma_daily_watch.is_trading_day", side_effect=mock_is_trading_day
    ):
        curr_exp, next_exp = resolve_expiries(today)
        assert curr_exp == date(2026, 3, 31)  # adjusted past Wednesday to Tuesday
        assert next_exp == date(2026, 4, 9)


def test_morning_flag_skips_watchlist() -> None:
    """If --morning is passed, _update_watchlist is not called."""
    test_args = ["gamma_daily_watch.py", "--morning"]

    with patch.object(sys, "argv", test_args):
        with patch(
            "scripts.pipeline.gamma_daily_watch._fetch_and_snapshot", return_value=[]
        ) as mock_fetch:
            with patch("scripts.pipeline.gamma_daily_watch._update_watchlist") as mock_update:
                main()
                mock_fetch.assert_called_once()
                mock_update.assert_not_called()


def test_dry_run_flag_propagates() -> None:
    """If --dry-run is passed, dry_run=True flows into _fetch_and_snapshot and _update_watchlist."""
    test_args = ["gamma_daily_watch.py", "--dry-run"]

    with patch.object(sys, "argv", test_args):
        with patch(
            "scripts.pipeline.gamma_daily_watch._fetch_and_snapshot", return_value=[]
        ) as mock_fetch:
            with patch("scripts.pipeline.gamma_daily_watch._update_watchlist") as mock_update:
                main()
                mock_fetch.assert_called_once()
                # Check dry_run=True was passed in kwargs
                assert mock_fetch.call_args[1]["dry_run"] is True
                mock_update.assert_called_once()
                assert mock_update.call_args[1]["dry_run"] is True


def test_date_override_option() -> None:
    """If --date is passed, it override today reference date."""
    test_args = ["gamma_daily_watch.py", "--date", "2026-05-15"]

    with patch.object(sys, "argv", test_args):
        with patch(
            "scripts.pipeline.gamma_daily_watch.resolve_expiries",
            return_value=(date(2026, 5, 21), date(2026, 5, 28)),
        ) as mock_resolve:
            with patch(
                "scripts.pipeline.gamma_daily_watch._fetch_and_snapshot", return_value=[]
            ) as mock_fetch:
                with patch("scripts.pipeline.gamma_daily_watch._update_watchlist"):
                    main()
                    mock_resolve.assert_called_once_with(date(2026, 5, 15))
                    mock_fetch.assert_called_once()
                    assert mock_fetch.call_args[1]["today"] == date(2026, 5, 15)
