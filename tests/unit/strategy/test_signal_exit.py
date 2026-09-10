"""Unit tests for the signals-paper-track exit constants (SPT-3 half)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.strategy.signal_exit import RULESET_VERSION, SL_PCT, TGT_PCT, derive_levels


def test_derive_levels_happy_path() -> None:
    sl, tgt = derive_levels(Decimal("40"))
    assert sl == Decimal("28.0")  # 40 * (1 - 0.30)
    assert tgt == Decimal("60.0")  # 40 * (1 + 0.50)


def test_derive_levels_uses_module_constants() -> None:
    e = Decimal("13.37")
    sl, tgt = derive_levels(e)
    assert sl == e * (Decimal("1") - SL_PCT)
    assert tgt == e * (Decimal("1") + TGT_PCT)
    assert RULESET_VERSION == "v1"


@pytest.mark.parametrize("bad", [Decimal("0"), Decimal("-1.5")])
def test_derive_levels_rejects_non_positive(bad: Decimal) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        derive_levels(bad)
