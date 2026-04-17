"""Tests for src/market_calendar/holidays.py.

All tests are fully offline — no network, no live DB. Holiday YAMLs are
written to pytest tmp_path to avoid coupling tests to the real data directory.
The module-level _CACHE is cleared before each test to prevent cross-test
pollution via the cached frozensets.
"""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

import pytest

import src.market_calendar.holidays as _mod
from src.market_calendar.holidays import is_trading_day, load_holidays, prev_trading_day


@pytest.fixture(autouse=True)
def clear_cache():
    """Wipe the module-level holiday cache before every test."""
    _mod._CACHE.clear()
    yield
    _mod._CACHE.clear()


@pytest.fixture()
def holiday_dir(tmp_path: Path) -> Path:
    """Return a tmp dir pre-populated with a minimal nse_2099.yaml.

    April 2099 day map (verified):
        Mon=06,13,20,27  Tue=07,14,21  Wed=01,08,15,22
        Thu=02,09,16,23  Fri=03,10,17,24  Sat=04,11,18,25  Sun=05,12,19,26
    Holidays in fixture: New Year (Wed), Good Friday 2099-04-17 (Fri), Christmas (Wed).
    """
    yaml_content = textwrap.dedent("""\
        holidays:
          - date: "2099-01-01"
            name: "New Year"
          - date: "2099-04-17"
            name: "Good Friday"
          - date: "2099-12-25"
            name: "Christmas"
    """)
    (tmp_path / "nse_2099.yaml").write_text(yaml_content)
    return tmp_path


# ── load_holidays ─────────────────────────────────────────────────────────────


class TestLoadHolidays:
    def test_happy_path_returns_correct_dates(self, holiday_dir: Path) -> None:
        result = load_holidays(2099, data_dir=holiday_dir)
        assert date(2099, 1, 1) in result
        assert date(2099, 4, 17) in result  # Good Friday (Friday in 2099)
        assert date(2099, 12, 25) in result
        assert len(result) == 3

    def test_returns_frozenset(self, holiday_dir: Path) -> None:
        result = load_holidays(2099, data_dir=holiday_dir)
        assert isinstance(result, frozenset)

    def test_missing_file_returns_empty_frozenset(self, tmp_path: Path) -> None:
        result = load_holidays(1900, data_dir=tmp_path)
        assert result == frozenset()

    def test_missing_file_logs_warning(self, tmp_path: Path, caplog) -> None:
        import logging
        with caplog.at_level(logging.WARNING, logger="src.market_calendar.holidays"):
            load_holidays(1900, data_dir=tmp_path)
        assert "fail-open" in caplog.text

    def test_caches_result_on_second_call(self, holiday_dir: Path) -> None:
        first = load_holidays(2099, data_dir=holiday_dir)
        second = load_holidays(2099, data_dir=holiday_dir)
        assert first is second  # same object from cache

    def test_cache_miss_for_missing_file_also_cached(self, tmp_path: Path) -> None:
        load_holidays(1900, data_dir=tmp_path)
        assert 1900 in _mod._CACHE
        assert _mod._CACHE[1900] == frozenset()

    def test_skips_entry_with_no_date_field(self, tmp_path: Path, caplog) -> None:
        import logging
        (tmp_path / "nse_2099.yaml").write_text("holidays:\n  - name: 'Bogus'\n")
        with caplog.at_level(logging.WARNING, logger="src.market_calendar.holidays"):
            result = load_holidays(2099, data_dir=tmp_path)
        assert result == frozenset()
        assert "no date field" in caplog.text

    def test_skips_entry_with_bad_date_format(self, tmp_path: Path, caplog) -> None:
        import logging
        (tmp_path / "nse_2099.yaml").write_text(
            "holidays:\n  - date: 'not-a-date'\n    name: 'Bad'\n"
        )
        with caplog.at_level(logging.WARNING, logger="src.market_calendar.holidays"):
            result = load_holidays(2099, data_dir=tmp_path)
        assert result == frozenset()
        assert "unrecognised date format" in caplog.text

    def test_empty_holidays_list_returns_empty_frozenset(self, tmp_path: Path) -> None:
        (tmp_path / "nse_2099.yaml").write_text("holidays: []\n")
        result = load_holidays(2099, data_dir=tmp_path)
        assert result == frozenset()


# ── is_trading_day ────────────────────────────────────────────────────────────


class TestIsTradingDay:
    def test_regular_wednesday_is_trading_day(self, holiday_dir: Path) -> None:
        # 2099-04-15 is a Wednesday, not in the fixture holiday list
        assert is_trading_day(date(2099, 4, 15), data_dir=holiday_dir) is True

    def test_saturday_is_not_trading_day(self, holiday_dir: Path) -> None:
        # 2099-04-18 is a Saturday
        assert is_trading_day(date(2099, 4, 18), data_dir=holiday_dir) is False

    def test_sunday_is_not_trading_day(self, holiday_dir: Path) -> None:
        # 2099-04-19 is a Sunday
        assert is_trading_day(date(2099, 4, 19), data_dir=holiday_dir) is False

    def test_good_friday_is_not_trading_day(self, holiday_dir: Path) -> None:
        # 2099-04-17 is Friday and in the fixture holiday list — weekday but a holiday
        assert is_trading_day(date(2099, 4, 17), data_dir=holiday_dir) is False

    def test_christmas_is_not_trading_day(self, holiday_dir: Path) -> None:
        # 2099-12-25 is a Wednesday (weekday) and in fixture holiday list
        assert is_trading_day(date(2099, 12, 25), data_dir=holiday_dir) is False

    def test_new_years_day_is_not_trading_day(self, holiday_dir: Path) -> None:
        # 2099-01-01 is a Wednesday (weekday) and in fixture holiday list
        assert is_trading_day(date(2099, 1, 1), data_dir=holiday_dir) is False

    def test_fail_open_when_yaml_missing(self, tmp_path: Path) -> None:
        # No YAML for year 1900 → fail-open, should return True for a weekday
        monday = date(1900, 4, 16)  # a Monday
        assert is_trading_day(monday, data_dir=tmp_path) is True

    def test_fail_open_does_not_raise(self, tmp_path: Path) -> None:
        # Must never raise regardless of missing file
        try:
            is_trading_day(date(1900, 1, 2), data_dir=tmp_path)
        except Exception as exc:
            pytest.fail(f"is_trading_day raised unexpectedly: {exc}")


# ── prev_trading_day ──────────────────────────────────────────────────────────


class TestPrevTradingDay:
    def test_prev_from_wednesday_returns_tuesday(self, holiday_dir: Path) -> None:
        # 2099-04-15 Wednesday → prev should be 2099-04-14 Tuesday
        result = prev_trading_day(date(2099, 4, 15), data_dir=holiday_dir)
        assert result == date(2099, 4, 14)

    def test_prev_from_monday_skips_weekend(self, holiday_dir: Path) -> None:
        # 2099-04-13 Monday → prev should skip Sun(12) + Sat(11) → 2099-04-10 Friday
        result = prev_trading_day(date(2099, 4, 13), data_dir=holiday_dir)
        assert result == date(2099, 4, 10)

    def test_prev_from_saturday_skips_weekend_and_holiday(
        self, holiday_dir: Path
    ) -> None:
        # 2099-04-18 Sat → candidate=Fri(17, holiday) → skip → Thu(16) ✓
        result = prev_trading_day(date(2099, 4, 18), data_dir=holiday_dir)
        assert result == date(2099, 4, 16)

    def test_prev_skips_weekend_and_friday_holiday(self, holiday_dir: Path) -> None:
        # 2099-04-20 Monday → skip Sun(19) + Sat(18) + Good Friday(17) → Thu(16) ✓
        result = prev_trading_day(date(2099, 4, 20), data_dir=holiday_dir)
        assert result == date(2099, 4, 16)

    def test_result_strictly_before_input(self, holiday_dir: Path) -> None:
        d = date(2099, 6, 10)
        result = prev_trading_day(d, data_dir=holiday_dir)
        assert result < d

    def test_fail_open_missing_yaml_still_skips_weekends(self, tmp_path: Path) -> None:
        # No YAML → holidays = frozenset() → only weekends blocked
        # 2099-04-13 Monday, no holidays → prev skips Sun(12)+Sat(11) → Fri(10)
        result = prev_trading_day(date(2099, 4, 13), data_dir=tmp_path)
        assert result == date(2099, 4, 10)  # skips Sat/Sun


# ── Real 2026 YAML sanity check ───────────────────────────────────────────────


class TestReal2026Yaml:
    """Smoke-tests against the actual data/market_holidays/nse_2026.yaml.

    These tests use the real file from the repo, not a tmp_path fixture.
    They verify the file is loadable and contains expected key holidays.
    """

    def test_republic_day_is_holiday(self) -> None:
        holidays = load_holidays(2026)
        assert date(2026, 1, 26) in holidays

    def test_good_friday_is_holiday(self) -> None:
        holidays = load_holidays(2026)
        assert date(2026, 4, 3) in holidays

    def test_christmas_is_holiday(self) -> None:
        holidays = load_holidays(2026)
        assert date(2026, 12, 25) in holidays

    def test_independence_day_is_holiday(self) -> None:
        holidays = load_holidays(2026)
        assert date(2026, 8, 15) in holidays

    def test_regular_tuesday_april_7_is_trading_day(self) -> None:
        # 2026-04-07 is a Tuesday, not a holiday
        assert is_trading_day(date(2026, 4, 7)) is True

    def test_good_friday_april_3_is_not_trading_day(self) -> None:
        assert is_trading_day(date(2026, 4, 3)) is False

    def test_ambedkar_jayanti_april_14_is_not_trading_day(self) -> None:
        assert is_trading_day(date(2026, 4, 14)) is False

    def test_holiday_count_is_reasonable(self) -> None:
        # NSE typically declares 14–18 equity holidays per year
        holidays = load_holidays(2026)
        assert 12 <= len(holidays) <= 20
