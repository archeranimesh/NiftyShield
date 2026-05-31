"""Hypothesis property tests for compute_ivr."""

import math

import hypothesis.strategies as st
import pandas as pd
from hypothesis import given, settings

from src.backtest.ivr import compute_ivr


@settings(max_examples=200)
@given(
    vix_today=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    series=st.lists(
        st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=251,
    ),
)
def test_ivr_short_series_returns_none(vix_today, series):
    result = compute_ivr(vix_today, pd.Series(series))
    assert result is None


@settings(max_examples=200)
@given(
    vix_today=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    series=st.lists(
        st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=252,
        max_size=400,
    ).filter(lambda s: max(s[-252:]) > min(s[-252:])),  # non-flat window
)
def test_ivr_sufficient_series_bounded(vix_today, series):
    result = compute_ivr(vix_today, pd.Series(series))
    assert result is not None
    assert 0.0 <= result <= 1.0


@settings(max_examples=200)
@given(
    vix_value=st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
    vix_today=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    extra=st.lists(
        st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=100,
    ),
)
def test_ivr_flat_window_returns_half(vix_value, vix_today, extra):
    # Build a series where the last 252 bars are all identical
    flat_window = [vix_value] * 252
    series = pd.Series(extra + flat_window)
    result = compute_ivr(vix_today, series)
    assert result == 0.5


@settings(max_examples=200)
@given(
    series=st.lists(
        st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=252,
        max_size=300,
    ).filter(lambda s: max(s[-252:]) > min(s[-252:])),
)
def test_ivr_below_min_clamps_to_zero(series):
    window_min = min(series[-252:])
    vix_today = window_min - 1.0  # strictly below min
    result = compute_ivr(vix_today, pd.Series(series))
    assert result == 0.0


@settings(max_examples=200)
@given(
    series=st.lists(
        st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=252,
        max_size=300,
    ).filter(lambda s: max(s[-252:]) > min(s[-252:])),
)
def test_ivr_above_max_clamps_to_one(series):
    window_max = max(series[-252:])
    vix_today = window_max + 1.0  # strictly above max
    result = compute_ivr(vix_today, pd.Series(series))
    assert result == 1.0


@settings(max_examples=200)
@given(
    vix_today=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    series=st.lists(
        st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=400,
    ),
)
def test_ivr_return_type(vix_today, series):
    result = compute_ivr(vix_today, pd.Series(series))
    assert result is None or (isinstance(result, float) and not math.isnan(result))
