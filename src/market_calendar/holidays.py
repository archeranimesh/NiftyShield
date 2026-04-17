"""NSE market holiday detection for the equity segment.

Holiday data is loaded from a YAML file in data/market_holidays/nse_{year}.yaml,
seeded annually from the NSE published equity holiday calendar. No live API
call is made at runtime — the list is deterministic for the whole year.

Fail-open contract: if the YAML file for the requested year is missing,
is_trading_day() logs a WARNING and returns True. A missing file must never
silently block a valid trading day.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Final

import yaml

logger = logging.getLogger(__name__)

# Resolved once at import time; all callers share the same anchor.
# YAMLs live alongside the module in src/market_calendar/data/ — version-controlled
# config, not runtime data (data/ is gitignored for the live SQLite DB).
_DATA_DIR: Final[Path] = Path(__file__).resolve().parent / "data"

# Module-level cache: year → frozenset[date]. Avoids re-parsing on repeat calls
# within the same process (e.g. intraday tracker calling every 5 minutes).
_CACHE: dict[int, frozenset[date]] = {}


def load_holidays(year: int, data_dir: Path = _DATA_DIR) -> frozenset[date]:
    """Load NSE equity holidays for a given year from the YAML file.

    Results are cached in _CACHE so the file is only read once per process.
    Returns an empty frozenset if the file does not exist, after logging a
    WARNING — fail-open so a missing file never blocks a valid trading day.

    Args:
        year: The calendar year to load holidays for (e.g. 2026).
        data_dir: Directory containing nse_{year}.yaml files. Defaults to
            data/market_holidays/ relative to the project root.

    Returns:
        frozenset of date objects representing NSE non-trading days for year.
    """
    if year in _CACHE:
        return _CACHE[year]

    yaml_path = data_dir / f"nse_{year}.yaml"
    if not yaml_path.exists():
        logger.warning(
            "market_calendar: holiday file not found for year=%d path=%s — "
            "fail-open, treating every weekday as a trading day",
            year,
            yaml_path,
        )
        _CACHE[year] = frozenset()
        return _CACHE[year]

    with yaml_path.open() as fh:
        data = yaml.safe_load(fh)

    entries = data.get("holidays", [])
    holidays: set[date] = set()
    for entry in entries:
        raw = entry.get("date")
        if not raw:
            logger.warning("market_calendar: skipping entry with no date field: %s", entry)
            continue
        try:
            holidays.add(date.fromisoformat(str(raw)))
        except ValueError:
            logger.warning("market_calendar: unrecognised date format '%s' — skipping", raw)

    _CACHE[year] = frozenset(holidays)
    logger.debug("market_calendar: loaded %d holidays for year=%d", len(holidays), year)
    return _CACHE[year]


def is_trading_day(d: date, *, data_dir: Path = _DATA_DIR) -> bool:
    """Return True if d is a weekday and not an NSE equity holiday.

    Weekends (Saturday=5, Sunday=6) are always non-trading days. Holidays are
    loaded from the YAML for d.year — fail-open if the file is absent.

    Args:
        d: The date to check.
        data_dir: Override for the holiday YAML directory (used in tests).

    Returns:
        True if the exchange is open on d, False otherwise.
    """
    if d.weekday() >= 5:  # Saturday or Sunday
        return False
    holidays = load_holidays(d.year, data_dir=data_dir)
    return d not in holidays


def prev_trading_day(d: date, *, data_dir: Path = _DATA_DIR) -> date:
    """Return the most recent trading day strictly before d.

    Walks backwards one day at a time until a trading day is found.
    Guaranteed to terminate — there is always a trading day within 7 days.

    Args:
        d: Reference date. The result is strictly before d.
        data_dir: Override for the holiday YAML directory (used in tests).

    Returns:
        The nearest prior trading day.
    """
    candidate = d - timedelta(days=1)
    while not is_trading_day(candidate, data_dir=data_dir):
        candidate -= timedelta(days=1)
    return candidate
