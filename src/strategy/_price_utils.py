# src/strategy/_price_utils.py
"""Shared price-resolution utilities for overlay_closer and executor."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import structlog

from src.models.options import OptionChain, OptionLeg

if TYPE_CHECKING:
    from src.instruments.lookup import InstrumentLookup

log = structlog.get_logger(__name__)

# Matches keys like "NSE_FO|NIFTY23000PE" → group 1 = "23000", group 2 = "PE"
# Only synthetic/symbolic keys (test fixtures) look like this. Real Upstox
# instrument keys are opaque numeric tokens (e.g. "NSE_FO|65900") that carry
# no strike/type information — those must be resolved via BOD JSON lookup
# instead (see `_resolve_via_bod`).
_STRIKE_RE = re.compile(r"NIFTY(\d+)(PE|CE)", re.IGNORECASE)


def find_option_leg(
    instrument_key: str,
    market: OptionChain,
    lookup: InstrumentLookup | None = None,
) -> OptionLeg | None:
    """Locate an option leg in the chain by instrument key.

    Tries to parse the strike and option type directly from the key first
    (cheap, no I/O — matches synthetic symbolic keys used in tests). Real
    Upstox instrument keys are numeric-only and never match that pattern; for
    those, falls back to ``lookup`` (BOD JSON) to resolve strike/type when
    provided.

    Args:
        instrument_key: Upstox instrument key (e.g. ``NSE_FO|NIFTY23000PE``
            for symbolic/test keys, or ``NSE_FO|65900`` for real production
            keys).
        market: Current option chain snapshot.
        lookup: Optional ``InstrumentLookup`` (BOD JSON) used to resolve
            strike/type for real numeric instrument keys that the regex
            cannot parse. If omitted, only symbolic keys resolve.

    Returns:
        Matching ``OptionLeg``, or ``None`` if the strike/type is absent from
        the chain or the key cannot be resolved by either path.
    """
    resolved = _resolve_from_regex(instrument_key, market)
    if resolved is not None:
        return resolved
    if lookup is not None:
        return _resolve_via_bod(instrument_key, market, lookup)
    log.warning("find_option_leg.key_not_parseable", key=instrument_key)
    return None


def _resolve_from_regex(instrument_key: str, market: OptionChain) -> OptionLeg | None:
    """Resolve strike/type for symbolic keys like ``NSE_FO|NIFTY23000PE``."""
    m = _STRIKE_RE.search(instrument_key)
    if not m:
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


def _resolve_via_bod(
    instrument_key: str, market: OptionChain, lookup: InstrumentLookup
) -> OptionLeg | None:
    """Resolve strike/type for real numeric Upstox keys via BOD JSON."""
    inst = lookup.get_by_key(instrument_key)
    if inst is None:
        log.warning("find_option_leg.bod_lookup_failed", key=instrument_key)
        return None
    option_type = inst.get("instrument_type")
    option_type = option_type.upper() if isinstance(option_type, str) else option_type
    strike_price = inst.get("strike_price")
    if option_type not in ("CE", "PE") or strike_price is None:
        log.warning(
            "find_option_leg.bod_not_an_option",
            key=instrument_key,
            instrument_type=option_type,
        )
        return None
    try:
        strike = Decimal(str(strike_price))
    except InvalidOperation:
        log.warning("find_option_leg.bod_bad_strike", key=instrument_key, strike=strike_price)
        return None
    strike_data = market.strikes.get(strike)
    if strike_data is None:
        return None
    return strike_data.ce if option_type == "CE" else strike_data.pe


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
    raise ValueError(f"No valid price for leg: bid={leg.bid} ask={leg.ask} ltp={leg.ltp}")
