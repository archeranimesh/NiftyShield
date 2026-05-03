"""Pure functions for paper trading metrics, NEE calculations, and cost attribution."""

from decimal import Decimal

# NiftyBees tracks Nifty 50 with a beta roughly around 0.92,
# capturing tracking error, dividends, and cash drag.
NIFTYBEES_BETA_TO_NIFTY = Decimal("0.92")


def compute_nee(nifty_spot: Decimal, lot_size: int) -> Decimal:
    """Compute Notional Equivalent Exposure (NEE).
    
    Args:
        nifty_spot: Current Nifty 50 spot price.
        lot_size: Nifty lot size (e.g., 65).
        
    Returns:
        NEE value as a Decimal.
    """
    return nifty_spot * Decimal(str(lot_size))


def compute_return_on_nee(pnl: Decimal, nee: Decimal) -> Decimal:
    """Compute Return on NEE as a percentage.
    
    Args:
        pnl: Absolute P&L.
        nee: Notional Equivalent Exposure.
        
    Returns:
        Percentage return on NEE (e.g. 5.5 for 5.5%). Returns Decimal("0") if NEE is zero.
    """
    if nee == Decimal("0"):
        return Decimal("0")
    return (pnl / nee) * Decimal("100")


def compute_cycle_max_drawdown(
    nav_history: list[Decimal], nee: Decimal
) -> tuple[Decimal, Decimal]:
    """Compute maximum drawdown from a history of NAV/PnL values.
    
    Drawdown is measured as peak-to-trough from the highest point achieved
    (or the starting point if it never goes up).
    
    Args:
        nav_history: List of historical cumulative P&L or NAV values in chronological order.
        nee: Notional Equivalent Exposure.
        
    Returns:
        A tuple of (absolute max drawdown, max drawdown as a percentage of NEE).
        Absolute drawdown is returned as a negative value (e.g. -5000).
        Percentage is returned as a negative percentage (e.g. -2.5).
    """
    if not nav_history:
        return Decimal("0"), Decimal("0")
        
    peak = nav_history[0]
    max_dd = Decimal("0")
    
    for val in nav_history:
        if val > peak:
            peak = val
        
        current_dd = val - peak
        if current_dd < max_dd:
            max_dd = current_dd
            
    if nee == Decimal("0"):
        max_dd_pct = Decimal("0")
    else:
        max_dd_pct = (max_dd / nee) * Decimal("100")
        
    return max_dd, max_dd_pct


def compute_annualised_overlay_cost(premium_paid: Decimal, dte_at_entry: int) -> Decimal:
    """Compute the annualised cost of an overlay premium.
    
    Used to compare the run-rate cost of monthly vs quarterly vs yearly protection.
    
    Args:
        premium_paid: The absolute premium paid for the option(s).
        dte_at_entry: Days to expiry at the time of entry.
        
    Returns:
        Annualised premium cost as a Decimal. Returns Decimal("0") if DTE is 0.
    """
    if dte_at_entry <= 0:
        return Decimal("0")
    
    return (premium_paid / Decimal(str(dte_at_entry))) * Decimal("365")
