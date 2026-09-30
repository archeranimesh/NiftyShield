"""Tests for the pure corporate-action multiplier."""

from datetime import date
from decimal import Decimal

from src.mvp.adjustment import cumulative_multiplier
from src.mvp.models import CorporateAction, CorporateActionType


def _action(ex_date: str, new: int, old: int, ident: str = "a") -> CorporateAction:
    return CorporateAction(
        action_id=ident,
        symbol="X",
        ex_date=ex_date,
        action_type=CorporateActionType.SPLIT,
        new_shares=new,
        old_shares=old,
        source="test",
        created_at="2026-09-30T00:00:00Z",
    )


def test_no_actions_is_one() -> None:
    assert cumulative_multiplier([], date(2025, 1, 1), date(2026, 1, 1)) == Decimal("1")


def test_single_split_applies_after_ex_date() -> None:
    acts = [_action("2025-12-15", 5, 1)]
    assert cumulative_multiplier(acts, date(2025, 9, 8), date(2026, 1, 1)) == Decimal("5")


def test_actions_compound() -> None:
    acts = [_action("2025-12-15", 5, 1, "a"), _action("2026-03-02", 3, 2, "b")]
    assert cumulative_multiplier(acts, date(2025, 9, 8), date(2026, 4, 1)) == Decimal("7.5")


def test_reverse_split_below_one() -> None:
    acts = [_action("2025-12-15", 1, 5)]
    assert cumulative_multiplier(acts, date(2025, 9, 8), date(2026, 1, 1)) == Decimal("0.2")


def test_boundaries_from_exclusive_as_of_inclusive() -> None:
    acts = [_action("2025-12-15", 5, 1)]
    assert cumulative_multiplier(acts, date(2025, 12, 15), date(2026, 1, 1)) == Decimal("1")
    assert cumulative_multiplier(acts, date(2025, 9, 8), date(2025, 12, 14)) == Decimal("1")
    assert cumulative_multiplier(acts, date(2025, 9, 8), date(2025, 12, 15)) == Decimal("5")


def test_price_and_qty_invariant() -> None:
    acts = [_action("2025-12-15", 5, 1), _action("2026-03-02", 3, 2, "b")]
    m = cumulative_multiplier(acts, date(2025, 9, 8), date(2026, 4, 1))
    price_old, qty_old = Decimal("1418"), 10
    price_new, qty_new = price_old / m, qty_old * m
    assert price_old / m == price_new and qty_old * m == qty_new
    assert price_new * qty_new == price_old * qty_old
