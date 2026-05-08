"""IV Rank (IVR) utility for India VIX.

IVR measures where today's VIX sits within its trailing 252-day range:
    ivr = (vix_today - vix_252d_low) / (vix_252d_high - vix_252d_low)

Result is clamped to [0.0, 1.0] to handle brief excursions outside the
historical window (e.g. sudden volatility spikes on low-VIX regimes).
"""

from __future__ import annotations

import pandas as pd


def compute_ivr(vix_today: float, vix_series: pd.Series) -> float | None:
    """Compute IV Rank (IVR) for a given VIX reading against a 252-day window.

    Args:
        vix_today: Today's India VIX closing value.
        vix_series: Daily VIX closes, most recent value last. Only the trailing
            252 values are used; the series must contain at least 252 points.

    Returns:
        IVR in [0.0, 1.0], or None if the series has fewer than 252 points.
        Returns 0.5 when the window is flat (high == low) to signal ambiguity
        rather than raising ZeroDivisionError.
    """
    if len(vix_series) < 252:
        return None

    window = vix_series.iloc[-252:]
    vix_low = float(window.min())
    vix_high = float(window.max())

    if vix_high == vix_low:
        return 0.5

    raw = (vix_today - vix_low) / (vix_high - vix_low)
    return float(max(0.0, min(1.0, raw)))
