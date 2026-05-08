"""Tests for src/backtest/ivr.py — compute_ivr()."""

import numpy as np
import pandas as pd
import pytest

from src.backtest.ivr import compute_ivr


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_ivr_midpoint() -> None:
    """VIX exactly at midpoint of a known range → IVR == 0.5."""
    series = pd.Series(np.linspace(10.0, 30.0, 252))  # low=10, high=30
    ivr = compute_ivr(vix_today=20.0, vix_series=series)
    assert ivr == pytest.approx(0.5)


def test_ivr_at_low() -> None:
    """VIX at the 252-day low → IVR == 0.0."""
    series = pd.Series(np.linspace(10.0, 30.0, 252))
    ivr = compute_ivr(vix_today=10.0, vix_series=series)
    assert ivr == pytest.approx(0.0)


def test_ivr_at_high() -> None:
    """VIX at the 252-day high → IVR == 1.0."""
    series = pd.Series(np.linspace(10.0, 30.0, 252))
    ivr = compute_ivr(vix_today=30.0, vix_series=series)
    assert ivr == pytest.approx(1.0)


def test_ivr_formula_known_values() -> None:
    """Verify formula numerically: vix_today=22, low=10, high=30 → (22-10)/(30-10) = 0.6."""
    series = pd.Series(np.linspace(10.0, 30.0, 252))
    ivr = compute_ivr(vix_today=22.0, vix_series=series)
    assert ivr == pytest.approx(0.6)


def test_ivr_uses_only_trailing_252_points() -> None:
    """Series longer than 252 — only the last 252 values define the range."""
    # First 100 values span [50, 100] — should be excluded from the window.
    # Last 252 values span [10, 30].
    low_noise = pd.Series(np.linspace(50.0, 100.0, 100))
    window = pd.Series(np.linspace(10.0, 30.0, 252))
    series = pd.concat([low_noise, window], ignore_index=True)

    ivr = compute_ivr(vix_today=20.0, vix_series=series)
    assert ivr == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_ivr_returns_none_for_short_series() -> None:
    """Series with fewer than 252 points → None."""
    series = pd.Series(np.linspace(10.0, 30.0, 251))
    assert compute_ivr(vix_today=20.0, vix_series=series) is None


def test_ivr_returns_none_for_empty_series() -> None:
    """Empty series → None."""
    assert compute_ivr(vix_today=20.0, vix_series=pd.Series([], dtype=float)) is None


def test_ivr_clamps_above_high() -> None:
    """VIX today above the 252-day high → clamped to 1.0, not >1."""
    series = pd.Series(np.linspace(10.0, 30.0, 252))
    ivr = compute_ivr(vix_today=50.0, vix_series=series)
    assert ivr == pytest.approx(1.0)


def test_ivr_clamps_below_low() -> None:
    """VIX today below the 252-day low → clamped to 0.0, not negative."""
    series = pd.Series(np.linspace(10.0, 30.0, 252))
    ivr = compute_ivr(vix_today=5.0, vix_series=series)
    assert ivr == pytest.approx(0.0)


def test_ivr_flat_series_returns_half() -> None:
    """All 252 values identical (high == low) → no divide-by-zero; returns 0.5."""
    series = pd.Series([15.0] * 252)
    ivr = compute_ivr(vix_today=15.0, vix_series=series)
    assert ivr == pytest.approx(0.5)


def test_ivr_exactly_252_points_accepted() -> None:
    """Series of exactly 252 points is the minimum valid length."""
    series = pd.Series(np.linspace(10.0, 30.0, 252))
    ivr = compute_ivr(vix_today=20.0, vix_series=series)
    assert ivr is not None
