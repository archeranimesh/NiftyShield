"""FinRakshak protective put strategy definition.

Structure: Single long-dated protective put on Nifty.
- Long NIFTY DEC 23000 PE — portfolio hedge

Entry date: 01 April 2026.
"""

from datetime import date

from src.portfolio.models import (
    AssetType,
    Direction,
    Leg,
    ProductType,
    Strategy,
)

FINRAKSHAK = Strategy(
    name="finrakshak",
    description=(
        "FinRakshak: Long-dated Nifty protective put. "
        "Standalone portfolio hedge — insures against a Nifty drawdown below 23000."
    ),
    legs=[
        Leg(
            instrument_key="NSE_FO|37810",
            display_name="NIFTY DEC 23000 PE",
            asset_type=AssetType.PE,
            direction=Direction.BUY,
            quantity=65,
            lot_size=65,
            entry_price=962.15,
            entry_date=date(2026, 4, 1),
            expiry=date(2026, 12, 29),
            strike=23000.0,
            product_type=ProductType.NRML,
        ),
    ],
)
