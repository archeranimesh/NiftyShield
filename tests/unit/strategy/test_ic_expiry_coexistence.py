# tests/unit/strategy/test_ic_expiry_coexistence.py
"""IC expiry-type coexistence: weekly, monthly, leaps and yearly books stay distinct.

Story: docs/plan/yearly-overlays/yearly-validation/stories.md -- YV-4.
Offline: a synthetic Tuesday-expiry chain and frozen dates; no network, no DB.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.instruments.lookup import InstrumentLookup
from src.strategy.ic_expiry_config import CONFIGS
from src.strategy.ic_expiry_config_v2 import CONFIGS_V2

_REPO = Path(__file__).resolve().parents[3]
_ALL_TYPES = {"weekly", "monthly", "leaps", "yearly"}


def _tuesday_chain(start: date, end: date) -> InstrumentLookup:
    """Build a lookup whose NIFTY options expire on every Tuesday in [start, end].

    Args:
        start: First day to consider.
        end: Last day to consider.

    Returns:
        InstrumentLookup holding one CE per Tuesday expiry.
    """
    instruments: list[dict[str, Any]] = []
    d = start
    while d <= end:
        if d.weekday() == 1:
            instruments.append(
                {
                    "segment": "NSE_FO",
                    "instrument_type": "CE",
                    "underlying_symbol": "NIFTY",
                    "expiry": d.isoformat(),
                }
            )
        d += timedelta(days=1)
    return InstrumentLookup(instruments)


def _resolve(lookup: InstrumentLookup, expiry_type: str, today: date) -> str | None:
    """Resolve the expiry for one IC type via its configured bucket."""
    bucket = CONFIGS[expiry_type].expiry_bucket
    got = dict(lookup.get_expiry_candidates("NIFTY", today, preference=[bucket]))
    return got.get(bucket)


@pytest.fixture(scope="module")
def chain() -> InstrumentLookup:
    """Tuesday chain covering Oct 2026 through Dec 2027."""
    return _tuesday_chain(date(2026, 10, 1), date(2027, 12, 31))


def test_ic_strategy_names_unique() -> None:
    """Every IC config (v1 and v2) has its own strategy_name and a covered type."""
    assert set(CONFIGS) == _ALL_TYPES
    assert all(k == c.expiry_type for k, c in CONFIGS.items())
    names = [c.strategy_name for c in CONFIGS.values()]
    names += [c.strategy_name for c in CONFIGS_V2.values()]
    assert len(names) == len(set(names))


@pytest.mark.parametrize(
    ("today", "leaps", "yearly"),
    [
        (date(2026, 10, 6), "2026-12-29", "2026-12-29"),
        (date(2026, 12, 30), "2027-03-30", "2027-12-28"),
        (date(2027, 3, 31), "2027-06-29", "2027-12-28"),
    ],
)
def test_leaps_is_quarterly_and_yearly_is_december(
    chain: InstrumentLookup, today: date, leaps: str, yearly: str
) -> None:
    """leaps resolves to a Mar/Jun/Sep/Dec last-Tuesday; yearly to a December one."""
    assert CONFIGS["leaps"].expiry_bucket == "quarterly"
    assert CONFIGS["yearly"].expiry_bucket == "yearly"
    got_leaps = _resolve(chain, "leaps", today)
    got_yearly = _resolve(chain, "yearly", today)
    assert (got_leaps, got_yearly) == (leaps, yearly)
    assert date.fromisoformat(got_leaps).month in (3, 6, 9, 12)
    assert date.fromisoformat(got_yearly).month == 12


def test_shared_december_expiry_allowed_but_distinct_books(chain: InstrumentLookup) -> None:
    """On 2026-10-06 leaps and yearly share Dec 2026 (intended); books stay separate."""
    today = date(2026, 10, 6)
    shared = _resolve(chain, "leaps", today)
    assert shared == _resolve(chain, "yearly", today) == "2026-12-29"
    # Later frozen dates do not share an expiry.
    for later in (date(2026, 12, 30), date(2027, 3, 31)):
        assert _resolve(chain, "leaps", later) != _resolve(chain, "yearly", later)
    assert CONFIGS["leaps"].strategy_name != CONFIGS["yearly"].strategy_name
    # weekly and monthly also resolve on the same day, in their own books.
    assert _resolve(chain, "weekly", today) is not None
    assert _resolve(chain, "monthly", today) is not None


@pytest.mark.parametrize(
    ("script", "pattern"),
    [
        ("scripts/monitor_daemon.py", r"for expiry_type, ic_config in IC_CONFIGS\.items\(\)"),
        (
            "scripts/strategies/ic/paper_ic_snapshot.py",
            r"for expiry_type, config in CONFIGS\.items\(\)",
        ),
    ],
)
def test_daemon_and_snapshot_loops_iterate_all_configs(script: str, pattern: str) -> None:
    """Both consumers loop over the full v1 CONFIGS registry, which holds all four types."""
    text = (_REPO / script).read_text(encoding="utf-8")
    assert re.search(pattern, text), f"{script} no longer loops over the IC registry"
    assert re.search(r"from src\.strategy\.ic_expiry_config import CONFIGS\b", text)
    assert set(CONFIGS) == _ALL_TYPES
