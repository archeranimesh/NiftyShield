# src/paper/constants.py
"""Shared constants for the 3-Track paper trading framework.

Update LOT_SIZE before each new cycle — NSE revises Nifty lot sizes periodically.
Current value: 65 (effective January 2026, NSE circular dated 2025-11-xx).
"""

LOT_SIZE: int = 65  # 1 Nifty lot = 65 units, effective Jan 2026
