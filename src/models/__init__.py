# Shared Pydantic models and dataclasses for NiftyShield.
#
# Domain split:
#   src.models.portfolio  — strategy, legs, snapshots, trades, portfolio summary
#   src.models.mf         — mutual fund transactions, NAV snapshots, holdings
#
# Import directly from the domain submodule for clarity:
#   from src.models.portfolio import Leg, Strategy
#   from src.models.mf import MFTransaction, MFHolding
#
# Or import from this package for convenience (re-exports everything):
#   from src.models import Leg, MFTransaction

from src.models.mf import MFHolding, MFNavSnapshot, MFTransaction, TransactionType
from src.models.portfolio import (
    AssetType,
    DailySnapshot,
    Direction,
    Leg,
    PortfolioSummary,
    ProductType,
    Strategy,
    Trade,
    TradeAction,
)

__all__ = [
    # portfolio models
    "AssetType",
    "DailySnapshot",
    "Direction",
    "Leg",
    "PortfolioSummary",
    "ProductType",
    "Strategy",
    "Trade",
    "TradeAction",
    # mf models
    "MFHolding",
    "MFNavSnapshot",
    "MFTransaction",
    "TransactionType",
]
