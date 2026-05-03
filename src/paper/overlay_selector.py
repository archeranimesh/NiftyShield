"""Overlay expiry selector to find the most cost-efficient protection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from src.client.protocol import BrokerClient
from src.client.upstox_market import parse_upstox_option_chain
from src.models.options import OptionChain


@dataclass(frozen=True)
class LegSpreadProfile:
    expiry: str
    spread_pct: Decimal | None
    oi: int | None


@dataclass(frozen=True)
class CollarSpreadProfile:
    expiry: str
    put_spread_pct: Decimal | None
    call_spread_pct: Decimal | None
    put_oi: int | None
    call_oi: int | None


@dataclass(frozen=True)
class OverlaySelection:
    chosen_expiry: str | None
    profiles: list[LegSpreadProfile | CollarSpreadProfile]
    fallback_reason: str | None


def _find_strike_by_delta(chain: OptionChain, side: Literal["CE", "PE"], target_delta: Decimal) -> Decimal | None:
    """Find the strike closest to the target absolute delta."""
    target_abs = abs(target_delta)
    best_strike = None
    min_diff = Decimal("1000")
    
    for strike_price, strike_data in chain.strikes.items():
        leg = strike_data.ce if side == "CE" else strike_data.pe
        if leg is None:
            continue
            
        leg_abs_delta = abs(leg.delta)
        # Assuming delta 0 means missing or bad data in most cases unless deep OTM
        if leg_abs_delta == Decimal("0"):
            continue
            
        diff = abs(leg_abs_delta - target_abs)
        if diff < min_diff:
            min_diff = diff
            best_strike = strike_price
            
    return best_strike


def _compute_spread_pct(bid: Decimal, ask: Decimal, mid: Decimal) -> Decimal | None:
    if mid <= Decimal("0") or bid <= Decimal("0") or ask <= Decimal("0"):
        return None
    return ((ask - bid) / mid) * Decimal("100")


async def select_overlay_expiry(
    broker: BrokerClient,
    underlying_key: str,
    candidate_expiries: list[str],
    option_type: Literal["CE", "PE", "COLLAR"],
    put_target_strike: Decimal | None = None,
    put_target_delta: Decimal | None = None,
    call_target_strike: Decimal | None = None,
    call_target_delta: Decimal | None = None,
    timeout_sec: float = 10.0
) -> OverlaySelection:
    """Find the most cost-efficient expiry based on bid-ask spreads.
    
    Applies a <= 3% spread gate. Candidate expiries should be ordered from most
    preferred to least preferred (e.g. quarterly -> yearly -> monthly).
    
    For collars, the gate is applied to max(put_spread_pct, call_spread_pct).
    
    Args:
        broker: BrokerClient to fetch option chains.
        underlying_key: The underlying instrument key.
        candidate_expiries: List of expiry strings in YYYY-MM-DD.
        option_type: "CE", "PE", or "COLLAR".
        put_target_strike: Target strike for put.
        put_target_delta: Target delta for put (used to find strike if strike is None).
        call_target_strike: Target strike for call.
        call_target_delta: Target delta for call (used to find strike if strike is None).
        timeout_sec: Timeout for API calls.
        
    Returns:
        OverlaySelection containing the chosen expiry (or None), all profiles evaluated,
        and an optional fallback reason.
    """
    profiles: list[LegSpreadProfile | CollarSpreadProfile] = []
    
    for expiry in candidate_expiries:
        try:
            # We enforce timeout on the broker call using asyncio.wait_for
            raw_chain = await asyncio.wait_for(
                broker.get_option_chain(underlying_key, expiry),
                timeout=timeout_sec
            )
            chain = parse_upstox_option_chain(raw_chain)
        except Exception:
            # If fetch fails, append empty profile and continue
            if option_type == "COLLAR":
                profiles.append(CollarSpreadProfile(expiry, None, None, None, None))
            else:
                profiles.append(LegSpreadProfile(expiry, None, None))
            continue
            
        # Determine actual strikes
        p_strike = put_target_strike
        if p_strike is None and put_target_delta is not None:
            p_strike = _find_strike_by_delta(chain, "PE", put_target_delta)
            
        c_strike = call_target_strike
        if c_strike is None and call_target_delta is not None:
            c_strike = _find_strike_by_delta(chain, "CE", call_target_delta)
            
        if option_type == "COLLAR":
            put_spread = None
            put_oi = None
            if p_strike is not None and p_strike in chain.strikes and chain.strikes[p_strike].pe is not None:
                leg = chain.strikes[p_strike].pe
                mid = (leg.bid + leg.ask) / Decimal("2") if leg.bid > Decimal("0") and leg.ask > Decimal("0") else leg.ltp
                put_spread = _compute_spread_pct(leg.bid, leg.ask, mid)
                put_oi = leg.oi

            call_spread = None
            call_oi = None
            if c_strike is not None and c_strike in chain.strikes and chain.strikes[c_strike].ce is not None:
                leg = chain.strikes[c_strike].ce
                mid = (leg.bid + leg.ask) / Decimal("2") if leg.bid > Decimal("0") and leg.ask > Decimal("0") else leg.ltp
                call_spread = _compute_spread_pct(leg.bid, leg.ask, mid)
                call_oi = leg.oi
                
            profiles.append(CollarSpreadProfile(expiry, put_spread, call_spread, put_oi, call_oi))
        
        else: # CE or PE
            target_strike = c_strike if option_type == "CE" else p_strike
            spread = None
            oi = None
            
            if target_strike is not None and target_strike in chain.strikes:
                leg = chain.strikes[target_strike].ce if option_type == "CE" else chain.strikes[target_strike].pe
                if leg is not None:
                    mid = (leg.bid + leg.ask) / Decimal("2") if leg.bid > Decimal("0") and leg.ask > Decimal("0") else leg.ltp
                    spread = _compute_spread_pct(leg.bid, leg.ask, mid)
                    oi = leg.oi
            
            profiles.append(LegSpreadProfile(expiry, spread, oi))

    # Evaluate against gate
    GATE = Decimal("3.0")
    for i, profile in enumerate(profiles):
        if isinstance(profile, CollarSpreadProfile):
            if profile.put_spread_pct is not None and profile.call_spread_pct is not None:
                max_spread = max(profile.put_spread_pct, profile.call_spread_pct)
                if max_spread <= GATE:
                    reason = f"Gate passed ({max_spread:.2f}% <= 3%) at preference rank {i+1}" if i > 0 else None
                    return OverlaySelection(profile.expiry, profiles, reason)
        else:
            if profile.spread_pct is not None:
                if profile.spread_pct <= GATE:
                    reason = f"Gate passed ({profile.spread_pct:.2f}% <= 3%) at preference rank {i+1}" if i > 0 else None
                    return OverlaySelection(profile.expiry, profiles, reason)
                    
    # Fallback to the last available expiry (monthly)
    fallback_expiry = candidate_expiries[-1] if candidate_expiries else None
    return OverlaySelection(fallback_expiry, profiles, "All candidate expiries failed the 3% spread gate.")
