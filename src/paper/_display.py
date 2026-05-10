# src/paper/_display.py
from decimal import Decimal

# Standardised labels for 3-Track comparison
BASE_LABELS = {
    "paper_nifty_spot": "NiftyBees (Spot)",
    "paper_nifty_futures": "Nifty Futures",
    "paper_nifty_proxy": "Proxy DITM CE",
}

OVERLAY_LABELS = {
    "overlay_pp": "PP",
    "overlay_cc": "CC",
    "overlay_collar_put": "Collar",
    "overlay_collar_call": "Collar",
}

def fmt_decimal(value: Decimal | None, precision: int = 0) -> str:
    """Format a Decimal with comma separators and a sign for non-zero values."""
    if value is None:
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.{precision}f}"

def delta_arrow(delta: Decimal | None) -> str:
    """Return a coloured delta-from-yesterday arrow string."""
    if delta is None:
        return "  (no prior)"
    if delta > 0:
        return f"  Δ {fmt_decimal(delta)} ▲"
    if delta < 0:
        return f"  Δ {fmt_decimal(delta)} ▼"
    return "  Δ ±0"

def hedge_verdict(base: Decimal, overlay_total: Decimal) -> str:
    """Return a human-readable effectiveness verdict for a hedge overlay."""
    if base < 0:
        if overlay_total > 0:
            absorbed_pct = abs(overlay_total) / abs(base) * 100
            if abs(base + overlay_total) < abs(base):
                return f"✅ Protected ({absorbed_pct:.0f}% absorbed)"
            return f"⚠️ Partial ({absorbed_pct:.0f}% absorbed)"
        return "❌ No protection"
    # base >= 0
    if overlay_total < 0:
        return "⚠️ Cost (overlay drag on up-move)"
    return "✅ Protected"
