"""Strategy registry — aggregates all provider packages.

Add new provider folders as siblings to finideas/ and import here.
"""

from src.portfolio.strategies.finideas import (
    FINIDEAS_ILTS,
    FINIDEAS_STRATEGIES,
    FINRAKSHAK,
)

ALL_STRATEGIES = [
    *FINIDEAS_STRATEGIES,
]

__all__ = ["ALL_STRATEGIES", "FINIDEAS_ILTS", "FINRAKSHAK"]
