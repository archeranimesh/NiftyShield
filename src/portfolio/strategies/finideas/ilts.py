"""Finideas ILTS (Intelligent Long-Term Strategy) definition.

Structure: Bond ETF + synthetic Nifty exposure via options.
- EBBETF0431 (Bharat Bond ETF Apr 2031) — fixed income base
- Long NIFTY DEC 23000 PE — long-dated hedge
- Long NIFTY JUN 23000 CE — equity upside via call
- Short NIFTY JUN 23000 PE — funds the CE purchase

Entry date: 01 April 2026.
"""

from datetime import date

from src.models.portfolio import (
    AssetType,
    Direction,
    Leg,
    ProductType,
    Strategy,
)

FINIDEAS_ILTS = Strategy(
    name="finideas_ilts",
    description=(
        "Finideas ILTS: Bharat Bond ETF + synthetic Nifty via options. "
        "Bond ETF provides fixed income; options create leveraged Nifty exposure "
        "with defined risk via the long-dated protective put."
    ),
    legs=[
        Leg(
            instrument_key="NSE_EQ|INF754K01LE1",
            display_name="EBBETF0431 (Bharat Bond ETF Apr 2031)",
            asset_type=AssetType.EQUITY,
            direction=Direction.BUY,
            quantity=438,
            lot_size=1,
            entry_price=1388.12,
            entry_date=date(2026, 4, 1),
            expiry=None,
            strike=None,
            product_type=ProductType.CNC,
        ),
        Leg(
            instrument_key="NSE_FO|37810",
            display_name="NIFTY DEC 23000 PE",
            asset_type=AssetType.PE,
            direction=Direction.BUY,
            quantity=65,
            lot_size=65,
            entry_price=975.0,
            entry_date=date(2026, 4, 1),
            expiry=date(2026, 12, 29),
            strike=23000.0,
            product_type=ProductType.NRML,
        ),
        Leg(
            instrument_key="NSE_FO|37799",
            display_name="NIFTY JUN 23000 CE",
            asset_type=AssetType.CE,
            direction=Direction.BUY,
            quantity=65,
            lot_size=65,
            entry_price=1082.0,
            entry_date=date(2026, 4, 1),
            expiry=date(2026, 6, 30),
            strike=23000.0,
            product_type=ProductType.NRML,
        ),
        Leg(
            instrument_key="NSE_FO|37805",
            display_name="NIFTY JUN 23000 PE",
            asset_type=AssetType.PE,
            direction=Direction.SELL,
            quantity=65,
            lot_size=65,
            entry_price=840.0,
            entry_date=date(2026, 4, 1),
            expiry=date(2026, 6, 30),
            strike=23000.0,
            product_type=ProductType.NRML,
        ),
    ],
)
