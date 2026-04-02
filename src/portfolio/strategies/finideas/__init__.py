"""Finideas strategy definitions (ILTS, FinRakshak)."""

from src.portfolio.strategies.finideas.finrakshak import FINRAKSHAK
from src.portfolio.strategies.finideas.ilts import FINIDEAS_ILTS

FINIDEAS_STRATEGIES = [FINIDEAS_ILTS, FINRAKSHAK]

__all__ = ["FINIDEAS_ILTS", "FINRAKSHAK", "FINIDEAS_STRATEGIES"]
