"""Source-agnostic option chain Pydantic models for NiftyShield.

Field names (delta, gamma, iv, …) are standard names.  Translation from
broker response shapes (Upstox, Dhan, …) happens in each client's parser
module — not here.  This keeps the model portable across Phase 0 (Upstox)
and Phase 1.10 (Dhan primary chain source).

All monetary/Greek fields are Decimal.  Models are frozen (immutable after
construction) so they can be safely cached or passed across async tasks.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class OptionLeg(BaseModel, frozen=True):
    """Market data and Greeks for one side (CE or PE) of a strike.

    All monetary fields are Decimal.  Null or non-numeric values from the
    broker response are coerced to Decimal("0") by the parser — consumers
    can treat missing data as zero without special-casing.

    Attributes:
        ltp: Last traded price.
        bid: Best bid price.
        ask: Best ask price.
        oi: Open interest (contracts).
        volume: Traded volume (contracts) for the session.
        delta: Option delta (signed; PE deltas are negative).
        gamma: Option gamma.
        theta: Option theta (daily decay; typically negative).
        vega: Option vega.
        iv: Implied volatility (annualised, as a percentage, e.g. 27.4).
        strike: Strike price.
    """

    ltp: Decimal
    bid: Decimal
    ask: Decimal
    oi: int
    volume: int
    delta: Decimal
    gamma: Decimal
    theta: Decimal
    vega: Decimal
    iv: Decimal
    strike: Decimal


class OptionChainStrike(BaseModel, frozen=True):
    """CE and PE legs for a single strike price.

    Either side may be None when the broker response omits that leg
    (e.g. deep OTM strikes with no market data).

    Attributes:
        ce: Call side; None if absent in the broker response.
        pe: Put side; None if absent in the broker response.
    """

    ce: OptionLeg | None = None
    pe: OptionLeg | None = None


class OptionChain(BaseModel, frozen=True):
    """Full option chain snapshot for an underlying + expiry.

    ``strikes`` is keyed by Decimal strike price.  Nifty strikes are
    always integer values, but using Decimal avoids float equality traps
    when looking up ``Decimal(str(leg.strike))`` at runtime.

    Attributes:
        underlying_spot: Spot price of the underlying at snapshot time.
        expiry: Option expiry date.
        strikes: Per-strike data, keyed by Decimal strike price.
    """

    underlying_spot: Decimal
    expiry: date
    strikes: dict[Decimal, OptionChainStrike]
