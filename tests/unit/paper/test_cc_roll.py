# tests/unit/paper/test_cc_roll.py
"""Unit tests for the manual Covered Call roll triggers in paper_cc_roll.py."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from scripts.strategies.cc_calibration.paper_cc_roll import (
    delta_stop_hit,
    loss_stop_hit,
    profit_target_hit,
    time_stop_hit,
)


def test_profit_target_hit() -> None:
    # 70% captured: current_ltp <= entry_credit * 0.30
    # Entry credit >= 15 is required
    assert profit_target_hit(Decimal("62"), Decimal("18.60")) is True  # exact boundary (18.60)
    assert profit_target_hit(Decimal("62"), Decimal("18.61")) is False  # just above
    assert profit_target_hit(Decimal("62"), Decimal("0")) is True  # expired worthless
    assert profit_target_hit(Decimal("14"), Decimal("3")) is False  # entry < 15 floor
    assert (
        profit_target_hit(Decimal("15"), Decimal("4.50")) is True
    )  # entry = 15 boundary, exact 30%


def test_time_stop_hit() -> None:
    entry = date(2026, 5, 1)
    assert time_stop_hit(entry, date(2026, 5, 22)) is True  # 21 days
    assert time_stop_hit(entry, date(2026, 5, 21)) is False  # 20 days
    assert time_stop_hit(entry, date(2026, 5, 1)) is False  # same day
    assert time_stop_hit(entry, date(2026, 6, 1)) is True  # 31 days


def test_delta_stop_hit() -> None:
    assert delta_stop_hit(0.55) is True  # exactly at limit
    assert delta_stop_hit(0.56) is True  # above limit
    assert delta_stop_hit(0.54) is False  # below limit
    assert delta_stop_hit(0.15) is False  # healthy CC delta


def test_loss_stop_hit() -> None:
    # 2.5x multiplier
    assert loss_stop_hit(Decimal("62"), Decimal("155.00")) is True  # exact boundary (155.0)
    assert loss_stop_hit(Decimal("62"), Decimal("154.99")) is False  # just below
    assert loss_stop_hit(Decimal("62"), Decimal("200")) is True  # well above
    assert loss_stop_hit(Decimal("62"), Decimal("62")) is False  # flat at entry
