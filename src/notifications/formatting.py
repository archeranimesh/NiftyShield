"""Value formatters for notifications."""

from decimal import Decimal


def format_money(value: Decimal) -> str:
    """2dp, comma thousands, ₹ prefix, sign before ₹ on negatives.
    
    Never accepts float — a float argument must raise TypeError, not silently coerce.
    Decimal("82628") -> "₹82,628.00", Decimal("86.68") -> "₹86.68",
    Decimal("-11.08") -> "-₹11.08".
    """
    if isinstance(value, float):
        raise TypeError("format_money requires Decimal, not float")
    
    if not isinstance(value, Decimal):
        value = Decimal(value)

    is_negative = value < 0
    abs_val = abs(value)
    
    formatted_num = f"{abs_val:,.2f}"
    
    if is_negative:
        return f"-₹{formatted_num}"
    return f"₹{formatted_num}"


def format_greek(value: float | None, *, width: int | None = None) -> str:
    """2dp, always signed, '-' placeholder for None (not-applicable, not zero).
    
    width: optional right-align width for FMT-3's build_leg_table to reuse later.
    -0.03 -> "-0.03", 0.28 -> "+0.28", None -> "-".
    """
    if value is None:
        base_str = "-"
    else:
        base_str = f"{value:+.2f}"
        
    if width is not None:
        return f"{base_str:>{width}}"
    return base_str


def format_strike(value: float | int) -> str:
    """Integer string, no decimal, no thousands separator (identifier, not quantity).
    
    23000.0 -> "23000". Reuse format_option_label's existing strike convention
    (src/instruments/lookup.py) rather than inventing a new one.
    """
    if not float(value).is_integer():
        raise ValueError(f"format_strike requires an integer or whole-number float, got {value}")
    return str(int(value))


def format_pct(value: float) -> str:
    """1dp; value is a plain number where 4 means 4%, not 0.04.
    
    Whole numbers print bare (no trailing .0): 4 -> "4%".
    """
    if float(value).is_integer():
        return f"{int(value)}%"
    return f"{value:.1f}%"
