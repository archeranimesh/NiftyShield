# src/strategy/_price_utils.py
"""Shared price-resolution utilities for overlay_closer and executor."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

import structlog

from src.models.options import OptionChain, OptionLeg

log = structlog.get_logger(__name__)

# Matches keys like "NSE_FO|NIFTY23000PE" → group 1 = "23000", group 2 = "PE"
_STRIKE_RE = re.compile(r"NIFTY(\d+)(PE|CE)", re.IGNORECASE)


def find_option_leg(instrument_key: str, market: OptionChain) -> OptionLeg | None:
    """Locate an option leg in the chain by instrument key.

    Parses the strike and option type from the key, then looks up the
    matching leg in the chain.

    Args:
        instrument_key: Upstox instrument key (e.g. ``NSE_FO|NIFTY23000PE``).
        market: Current option chain snapshot.

    Returns:
        Matching ``OptionLeg``, or ``None`` if the strike/type is absent from
        the chain or the key cannot be parsed.
    """
    m = _STRIKE_RE.search(instrument_key)
    if not m:
        log.warning("find_option_leg.key_not_parseable", key=instrument_key)
        return None
    try:
        strike = Decimal(m.group(1))
        option_type = m.group(2).upper()
        strike_data = market.strikes.get(strike)
        if strike_data is None:
            return None
        return strike_data.ce if option_type == "CE" else strike_data.pe
    except (InvalidOperation, KeyError) as exc:
        log.warning("find_option_leg.lookup_failed", key=instrument_key, error=str(exc))
        return None


def resolve_price(leg: OptionLeg) -> Decimal:
    """Return the best-available price for an option leg.

    Uses ``(bid + ask) / 2`` when both are positive; falls back to LTP.

    Args:
        leg: Option leg with current market data.

    Returns:
        Resolved price as ``Decimal``.

    Raises:
        ValueError: When neither bid/ask nor LTP yields a positive price.
            Callers must not proceed with a zero-price fill on this error.
    """
    if leg.bid > 0 and leg.ask > 0:
        return (leg.bid + leg.ask) / 2
    if leg.ltp > 0:
        return leg.ltp
    raise ValueError(
        f"No valid price for leg: bid={leg.bid} ask={leg.ask} ltp={leg.ltp}"
    )
