# src/paper/constants.py
"""Shared constants for the 3-Track and CSP paper trading frameworks.

Update LOT_SIZE before each new cycle — NSE revises Nifty lot sizes periodically.
Current value: 65 (effective January 2026, NSE circular dated 2025-11-xx).
"""

from decimal import Decimal
from math import floor
from pathlib import Path

# Common Paths
DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")
DEFAULT_BOD_PATH = Path("data/instruments/NSE.json.gz")

# Instrument Keys & Identifiers
NIFTY_UNDERLYING = "NSE_INDEX|Nifty 50"
NIFTYBEES_KEY = "NSE_EQ|INF204KB14I2"
LOT_SIZE: int = 65  # 1 Nifty lot = 65 units, effective Jan 2026

# Strategy Names (T1-C verification: paper trading strategies must start with paper_)
STRATEGY_SPOT = "paper_nifty_spot"
STRATEGY_FUTURES = "paper_nifty_futures"
STRATEGY_PROXY = "paper_nifty_proxy"
STRATEGY_CSP = "paper_csp_nifty_v1"
STRATEGY_CC_OVERLAY = "paper_covered_call_v1"
STRATEGY_PP_OVERLAY = "paper_protective_put_v1"
STRATEGY_COLLAR_OVERLAY = "paper_collar_v1"
STRATEGY_IC = "paper_ic_nifty_v1"

# Per-expiry IC variants
STRATEGY_IC_WEEKLY  = "paper_ic_nifty_v1_weekly"
STRATEGY_IC_MONTHLY = "paper_ic_nifty_v1_monthly"
STRATEGY_IC_LEAPS   = "paper_ic_nifty_v1_leaps"
STRATEGY_IC_YEARLY  = "paper_ic_nifty_v1_yearly"

# 3-Track Targeting Thresholds (Extracted from paper_3track_overlay.py)
PP_OTM_MIN = 0.08
PP_OTM_MAX = 0.10
PP_TARGET_OTM = 0.09

CC_OTM_MIN = 0.03
CC_OTM_MAX = 0.05
CC_TARGET_OTM = 0.04


def compute_max_lots(
    niftybees_units: int,
    nifty_spot: Decimal,
    niftybees_ltp: Decimal,
    lot_size: int = LOT_SIZE,
) -> int:
    """Return the maximum number of CC lots coverable by pledged NiftyBees units.

    Args:
        niftybees_units: Total NiftyBees units currently pledged as margin collateral.
        nifty_spot: Current Nifty 50 spot price.
        niftybees_ltp: Current NiftyBees ETF LTP.
        lot_size: Nifty lot size (default: LOT_SIZE from constants).

    Returns:
        Maximum lots as a non-negative integer (floored). Zero if holding is insufficient.

    Formula from covered_call_overlay_v1.md:
        max_lots = floor(niftybees_units / (nifty_spot / niftybees_ltp × lot_size))

    Recompute at each annual NiftyBees leg reset. At ~5,725 units and current
    Nifty/NiftyBees ratio, this returns 1 lot.
    """
    if nifty_spot <= 0 or niftybees_ltp <= 0 or lot_size <= 0:
        return 0
    units_per_lot = (nifty_spot / niftybees_ltp) * lot_size
    return floor(niftybees_units / units_per_lot)


# Roll Logic
OVERLAY_ROLL_DTE = 5
SPREAD_PCT_MAX = 3.0
