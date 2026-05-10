# src/paper/constants.py
"""Shared constants for the 3-Track and CSP paper trading frameworks.

Update LOT_SIZE before each new cycle — NSE revises Nifty lot sizes periodically.
Current value: 65 (effective January 2026, NSE circular dated 2025-11-xx).
"""

from pathlib import Path

# Common Paths
DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")
DEFAULT_BOD_PATH = Path("data/instruments/NSE.json.gz")

# Instrument Keys & Identifiers
NIFTY_UNDERLYING = "NSE_INDEX|Nifty 50"
NIFTYBEES_KEY = "NSE_EQ|INF204KB14I2"
LOT_SIZE: int = 65  # 1 Nifty lot = 65 units, effective Jan 2026

# 3-Track Targeting Thresholds (Extracted from paper_3track_overlay.py)
PP_OTM_MIN = 0.08
PP_OTM_MAX = 0.10
PP_TARGET_OTM = 0.09

CC_OTM_MIN = 0.03
CC_OTM_MAX = 0.05
CC_TARGET_OTM = 0.04

# Roll Logic
OVERLAY_ROLL_DTE = 5
SPREAD_PCT_MAX = 3.0
