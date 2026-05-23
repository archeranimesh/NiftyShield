"""Unit tests for option model business logic in src/models/options.py.

Includes testing for calculate_otm_pct and rank_overlay_key.
"""

from decimal import Decimal
import pytest

from src.models.options import calculate_otm_pct, rank_overlay_key


# ── calculate_otm_pct ────────────────────────────────────────────────────────


def test_calculate_otm_pct_pe_happy() -> None:
    # PE OTM: (spot - strike) / spot
    strike = Decimal("22000")
    spot = Decimal("22200")
    val = calculate_otm_pct(strike, spot, "PE")
    expected = (spot - strike) / spot
    assert val == expected
    assert val > 0


def test_calculate_otm_pct_ce_happy() -> None:
    # CE OTM: (strike - spot) / spot
    strike = Decimal("22400")
    spot = Decimal("22200")
    val = calculate_otm_pct(strike, spot, "CE")
    expected = (strike - spot) / spot
    assert val == expected
    assert val > 0


def test_calculate_otm_pct_zero_spot_raises() -> None:
    with pytest.raises(ZeroDivisionError):
        calculate_otm_pct(Decimal("22000"), Decimal("0"), "PE")


# ── rank_overlay_key ─────────────────────────────────────────────────────────


def test_rank_overlay_key_happy() -> None:
    # Round strike (22000 % 100 == 0) -> is_non_round = False
    strike = Decimal("22000")
    bid = Decimal("10.0")
    ask = Decimal("12.0")
    oi = 15000
    otm_pct = Decimal("0.02")
    target_otm = Decimal("0.02")

    rk = rank_overlay_key(strike, bid, ask, oi, otm_pct, target_otm)
    # Expected: (is_non_round, spread_bucket, -oi, spread, otm_dist)
    # is_non_round: False
    # spread = 2.0 -> spread_bucket = int(2.0/2) = 1
    # -oi = -15000
    # spread = 2.0
    # otm_dist = 0
    assert rk == (False, 1, -15000, Decimal("2.0"), Decimal("0.0"))


def test_rank_overlay_key_non_round_strike() -> None:
    # Non-round strike (22050 % 100 != 0) -> is_non_round = True
    strike = Decimal("22050")
    bid = Decimal("10.0")
    ask = Decimal("12.0")
    oi = 15000
    otm_pct = Decimal("0.02")
    target_otm = Decimal("0.02")

    rk = rank_overlay_key(strike, bid, ask, oi, otm_pct, target_otm)
    assert rk[0] is True  # is_non_round is True


def test_rank_overlay_key_invalid_spread_fallback() -> None:
    # Bid or Ask <= 0 -> spread = 9999.0, spread_bucket = 4999
    strike = Decimal("22000")
    bid = Decimal("0.0")
    ask = Decimal("12.0")
    oi = 15000
    otm_pct = Decimal("0.02")
    target_otm = Decimal("0.02")

    rk = rank_overlay_key(strike, bid, ask, oi, otm_pct, target_otm)
    assert rk[1] == 4999  # spread_bucket = int(9999.0 / 2) = 4999
    assert rk[3] == Decimal("9999.0")
