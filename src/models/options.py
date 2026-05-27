"""Source-agnostic option chain Pydantic models for NiftyShield.

Field names (delta, gamma, iv, …) are standard names.  Translation from
broker response shapes (Upstox, Dhan, …) happens in each client's parser
module — not here.  This keeps the model portable across Phase 0 (Upstox)
and the chain-data story (Upstox live snapshots + future Dhan parser).

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


def calculate_otm_pct(strike: Decimal, spot: Decimal, option_type: str) -> Decimal:
    """Calculate the OTM fraction for a strike relative to spot.

    PE: (spot - strike) / spot   (positive when strike < spot)
    CE: (strike - spot) / spot   (positive when strike > spot)

    Args:
        strike: Option strike price.
        spot: Spot price of the underlying.
        option_type: Option type ("PE" or "CE").

    Returns:
        The OTM fraction as a Decimal.

    Raises:
        ValueError: If option_type is not 'PE' or 'CE'.
    """
    if option_type == "PE":
        return (spot - strike) / spot
    elif option_type == "CE":
        return (strike - spot) / spot
    else:
        raise ValueError(f"Unknown option_type: {option_type}. Expected 'PE' or 'CE'.")


def rank_overlay_key(
    strike: Decimal,
    bid: Decimal,
    ask: Decimal,
    oi: int,
    otm_pct: Decimal,
    target_otm: Decimal,
) -> tuple[bool, int, int, Decimal, Decimal]:
    """5-tuple ranking key for overlay candidates (ascending — lower wins).

    1. is_non_round  — multiples of 100 preferred over 50-increment strikes (bool)
    2. spread_bucket — tighter ₹2 spread tier wins (int)
    3. -oi           — highest OI wins within the same spread tier (int)
    4. spread        — exact spread tiebreaker inside a bucket (Decimal)
    5. otm_dist      — proximity to target OTM — final tiebreaker only (Decimal)

    Args:
        strike: Option strike price.
        bid: Best bid price.
        ask: Best ask price.
        oi: Open interest.
        otm_pct: OTM fraction.
        target_otm: Target OTM fraction.

    Returns:
        A 5-tuple used for sorting/ranking candidates.
    """
    spread = ask - bid if (bid > Decimal("0") and ask > Decimal("0")) else Decimal("9999.0")
    is_non_round = int(strike) % 100 != 0
    spread_bucket = int(spread / Decimal("2"))
    otm_dist = abs(otm_pct - target_otm)
    return (is_non_round, spread_bucket, -oi, spread, otm_dist)
