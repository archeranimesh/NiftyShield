"""Tests for the overnight-gap ratio matcher."""

from datetime import date
from decimal import Decimal

import pytest

from src.mvp.detection import detect_overnight_gap, format_gap_warning, match_split_factor
from src.mvp.models import CorporateAction, CorporateActionType, MVPSnapshot


def _snap(day: str, ltp: str, hour: str = "04:00:00") -> MVPSnapshot:
    return MVPSnapshot(pick_id="p", ltp=Decimal(ltp), captured_at=f"{day}T{hour}Z")


@pytest.mark.parametrize(
    "ratio,label",
    [
        ("0.20", "5:1"),
        ("0.205", "5:1"),  # within 3%
        ("0.50", "2:1"),
        ("0.10", "10:1"),
        ("0.6667", "1.5:1"),
        ("5", "1:5"),
    ],
)
def test_match_split_factor_hits(ratio: str, label: str) -> None:
    match = match_split_factor(Decimal("1000"), Decimal("1000") * Decimal(ratio))
    assert match is not None and match.label == label


@pytest.mark.parametrize("ratio", ["0.95", "0.80", "0.73", "1.00", "1.10", "0.28"])
def test_match_split_factor_organic_moves_do_not_match(ratio: str) -> None:
    assert match_split_factor(Decimal("1000"), Decimal("1000") * Decimal(ratio)) is None


def test_match_split_factor_nonpositive_inputs() -> None:
    assert match_split_factor(Decimal("0"), Decimal("10")) is None
    assert match_split_factor(Decimal("10"), Decimal("0")) is None


def test_detect_gap_first_tick_matches_and_suppresses() -> None:
    snaps = [_snap("2026-09-24", "1000", "09:00:00")]
    match = detect_overnight_gap(snaps, date(2026, 9, 25), Decimal("201"))
    assert match is not None and match.label == "5:1"
    assert "5:1 pattern" in format_gap_warning("XYZ", match)


def test_detect_gap_later_tick_uses_todays_first_snapshot() -> None:
    snaps = [
        _snap("2026-09-24", "1000"),
        _snap("2026-09-25", "200"),
        _snap("2026-09-25", "205", "05:00:00"),
    ]
    # Current LTP looks organic vs. today's open, but the day's verdict is unchanged.
    assert detect_overnight_gap(snaps, date(2026, 9, 25), Decimal("205")) is not None


def test_detect_gap_organic_drop_does_not_suppress() -> None:
    snaps = [_snap("2026-09-24", "1000")]
    assert detect_overnight_gap(snaps, date(2026, 9, 25), Decimal("880")) is None


def test_detect_gap_no_prior_snapshot() -> None:
    assert detect_overnight_gap([], date(2026, 9, 25), Decimal("200")) is None
    assert (
        detect_overnight_gap([_snap("2026-09-25", "200")], date(2026, 9, 25), Decimal("200"))
        is None
    )


def test_detect_gap_skipped_once_action_recorded() -> None:
    action = CorporateAction(
        action_id="a",
        symbol="XYZ",
        ex_date="2026-09-25",
        action_type=CorporateActionType.SPLIT,
        new_shares=5,
        old_shares=1,
        source="t",
        created_at="2026-09-25T00:00:00Z",
    )
    snaps = [_snap("2026-09-24", "1000")]
    assert detect_overnight_gap(snaps, date(2026, 9, 25), Decimal("200"), [action]) is None
