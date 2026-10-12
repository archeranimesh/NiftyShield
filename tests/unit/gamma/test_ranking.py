"""Tests for Phase B candidate ranking."""

from __future__ import annotations

from decimal import Decimal as D

from src.gamma.ranking import rank_candidates, rank_score
from tests.unit.gamma.test_signals import make


def test_score_formula_hit_and_non_hit() -> None:
    assert rank_score(make(gamma_gearing=D("1000"), watchlist_hit=False)) == D("700.0")
    assert rank_score(make(gamma_gearing=D("1000"), watchlist_hit=True)) == D("1000.0")


def test_score_none_without_gearing() -> None:
    assert rank_score(make(gamma_gearing=None)) is None


def test_orders_by_gearing_with_watchlist_boost() -> None:
    hi = make(gamma_gearing=D("1000"))  # 700
    boosted = make(gamma_gearing=D("800"), watchlist_hit=True)  # 800
    lo = make(gamma_gearing=D("500"), watchlist_hit=True)  # 500
    assert rank_candidates([lo, hi, boosted]) == [boosted, hi, lo]


def test_boost_does_not_beat_much_higher_gearing() -> None:
    big = make(gamma_gearing=D("1500"))  # 1050
    boosted = make(gamma_gearing=D("1000"), watchlist_hit=True)  # 1000
    assert rank_candidates([boosted, big])[0] is big


def test_tie_breaks_hit_then_ask_then_distance_then_type() -> None:
    # equal score 700: non-hit 1000 vs hit gearing 700 / 1.0 = 700
    plain = make(gamma_gearing=D("1000"))
    hit = make(gamma_gearing=D("700"), watchlist_hit=True)
    assert rank_candidates([plain, hit]) == [hit, plain]
    cheap = make(ask=D("4"))
    dear = make(ask=D("5"))
    assert rank_candidates([dear, cheap]) == [cheap, dear]
    near = make(distance_pct=D("0.01"))
    far = make(distance_pct=D("0.02"))
    assert rank_candidates([far, near]) == [near, far]
    ce, pe = make(option_type="CE"), make(option_type="PE")
    assert rank_candidates([pe, ce]) == [ce, pe]


def test_full_tie_is_stable_and_input_untouched() -> None:
    a, b = make(), make()
    src = [a, b]
    assert rank_candidates(src) == [a, b]
    assert rank_candidates(src)[0] is a
    assert src == [a, b]


def test_none_gearing_ranks_last_and_empty_ok() -> None:
    none = make(gamma_gearing=None)
    real = make(gamma_gearing=D("1"))
    assert rank_candidates([none, real]) == [real, none]
    assert rank_candidates([]) == []
