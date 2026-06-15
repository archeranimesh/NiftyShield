# src/paper/chain_utils.py
"""Option chain helper utilities for instrument key parsing and leg resolution."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

import structlog

from src.instruments.lookup import InstrumentLookup
from src.models.options import OptionChain, OptionLeg

log = structlog.get_logger(__name__)

# Matches "NIFTY29MAY2026CE23000" or "NIFTY23000CE"
_KEY_EXPIRY_RE = re.compile(r"NIFTY(\d{2})([A-Za-z]{3})(\d{4})(CE|PE)", re.IGNORECASE)
_KEY_STRIKE_RE = re.compile(r"NIFTY(\d+)(CE|PE)", re.IGNORECASE)
# Matches strike that follows the option type in date-embedded keys: "NIFTY29JUL2026PE22500" → "22500"
_KEY_DATE_STRIKE_RE = re.compile(r"NIFTY\d{2}[A-Za-z]{3}\d{4}(?:CE|PE)(\d+)", re.IGNORECASE)

_MONTH_ABBR: dict[str, int] = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def parse_expiry_from_key(instrument_key: str) -> date | None:
    """Return expiry date from instrument key, or None if unparseable."""
    m = _KEY_EXPIRY_RE.search(instrument_key)
    if not m:
        return None
    try:
        day, mon_str, year = int(m.group(1)), m.group(2).upper(), int(m.group(3))
        month = _MONTH_ABBR.get(mon_str)
        return date(year, month, day) if month else None
    except (ValueError, TypeError):
        return None


def parse_strike_from_key(instrument_key: str) -> Decimal | None:
    """Extract strike price from instrument key, or None if unparseable."""
    m = _KEY_STRIKE_RE.search(instrument_key)
    if not m:
        m2 = _KEY_DATE_STRIKE_RE.search(instrument_key)
        if m2:
            try:
                return Decimal(m2.group(1))
            except InvalidOperation:
                pass
        return None
    try:
        return Decimal(m.group(1))
    except InvalidOperation:
        return None


def find_chain_leg(
    chain: OptionChain,
    instrument_key: str,
    option_type: str,
    lookup: InstrumentLookup | None = None,
) -> OptionLeg | None:
    """Look up CE or PE leg from the chain by strike.

    Resolution order:
    1. Parse strike directly from a named key (e.g. 'NIFTY29MAY2026CE23000').
    2. Resolve strike via BOD lookup when ``lookup`` is provided (handles numeric
       keys like 'NSE_FO|71474').

    Args:
        chain: Parsed Nifty option chain.
        instrument_key: Position's instrument key.
        option_type: 'CE' or 'PE'.
        lookup: Optional BOD instrument lookup for resolving numeric keys.

    Returns:
        Matching OptionLeg or None when unavailable.
    """
    strike = parse_strike_from_key(instrument_key)

    # For numeric BOD keys, resolve strike via the instrument lookup.
    if strike is None and lookup is not None:
        inst = lookup.get_by_key(instrument_key)
        if inst is not None:
            raw_strike = inst.get("strike_price")
            if raw_strike is not None:
                try:
                    strike = Decimal(str(raw_strike))
                except Exception:
                    pass

    if strike is not None:
        strike_data = chain.strikes.get(strike)
        if strike_data is not None:
            return strike_data.ce if option_type == "CE" else strike_data.pe

    log.warning(
        "find_chain_leg.strike_not_resolved",
        instrument_key=instrument_key,
    )
    return None
