from dataclasses import dataclass
from decimal import Decimal
import numpy as np

from src.payoff.core import StrategyPayoff
from src.notifications.formatting import format_strike

def x_range(payoff: StrategyPayoff, spot: Decimal | None) -> tuple[float, float]:
    """Chart x-range: key spots padded by 0.4x span, widened to include spot, floored at 0."""
    pts = list(payoff.key_spots) or ([spot] if spot is not None else [])
    if not pts:
        pts = [payoff.legs[0].entry_price]
        
    lo, hi = min(pts), max(pts)
    span = float(hi - lo)
    
    if span == 0:
        span = float(spot if spot is not None else lo) * 0.1
        
    lo_f, hi_f = float(lo) - 0.4 * span, float(hi) + 0.4 * span
    
    if spot is not None:
        lo_f, hi_f = min(lo_f, float(spot)), max(hi_f, float(spot))
        
    return max(0.0, lo_f), hi_f

def sample_xs(payoff: StrategyPayoff, lo: float, hi: float, n: int = 240) -> np.ndarray:
    """linspace unioned with every strike and breakeven, sorted, unique."""
    xs = np.linspace(lo, hi, n)
    extra = []
    for leg in payoff.legs:
        if leg.strike is not None:
            extra.append(float(leg.strike))
    for be in payoff.breakevens:
        extra.append(float(be))
        
    return np.unique(np.concatenate([xs, np.array(extra)]))

@dataclass(frozen=True)
class StrikeTick:
    x: float
    text: str
    short: bool

def strike_ticks(payoff: StrategyPayoff, span: float) -> list[StrikeTick]:
    """One per option strike, ascending. Staggers close neighbours."""
    legs = [leg for leg in payoff.legs if leg.strike is not None]
    legs.sort(key=lambda leg: leg.strike)
    
    ticks = []
    last_x = None
    last_lowered = False
    
    for leg in legs:
        x_val = float(leg.strike)
        strike_str = format_strike(leg.strike)
        side = "SELL" if leg.qty < 0 else "BUY"
        base_text = f"{strike_str} {leg.kind}\n{side}"
        
        lowered = False
        if last_x is not None and (x_val - last_x) < 0.14 * span:
            if not last_lowered:
                lowered = True
                
        text = "\n" + base_text if lowered else base_text
        ticks.append(StrikeTick(x=x_val, text=text, short=leg.qty < 0))
        
        last_x = x_val
        last_lowered = lowered
        
    return ticks
