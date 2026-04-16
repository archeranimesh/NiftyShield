"""Indian numbering system formatting utilities.

The Indian system groups digits as: ...XX,XX,XXX (last 3 from the right,
then pairs). For example:

    139127900  →  13,91,27,900
    1391279    →  13,91,279
    100000     →  1,00,000   (1 lakh)
    10000000   →  1,00,00,000 (1 crore)

Public API:
    fmt_inr(value, *, decimals=0, sign=False, width=0) -> str
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def fmt_inr(
    value: Decimal | float | int,
    *,
    decimals: int = 0,
    sign: bool = False,
    width: int = 0,
) -> str:
    """Format *value* using the Indian numbering system (Lakhs/Crores).

    Groups the integer part as: last-3 digits, then pairs leftward — matching
    the standard Indian convention for displaying Rupee amounts.

    Args:
        value: Numeric value to format. Accepts ``Decimal``, ``float``, or
            ``int``. ``float`` inputs are converted via ``str()`` to avoid
            IEEE 754 rounding surprises.
        decimals: Number of decimal places to show (default 0 for rupees).
        sign: When ``True``, prefix positive values with ``'+'``
            (default False).
        width: Minimum total field width; result is right-aligned with spaces
            (default 0 = no padding).

    Returns:
        Formatted string, e.g. ``"1,39,12,790"`` or ``"+2,42,531"``.

    Raises:
        ValueError: If *value* cannot be interpreted as a valid decimal number.

    Examples:
        >>> fmt_inr(1391279)
        '13,91,279'
        >>> fmt_inr(Decimal("100000"))
        '1,00,000'
        >>> fmt_inr(Decimal("-242531"), sign=True)
        '-2,42,531'
        >>> fmt_inr(Decimal("80000"), sign=True, width=12)
        '     +80,000'
    """
    try:
        # Normalise: float → str → Decimal avoids IEEE 754 drift.
        d: Decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"fmt_inr: cannot convert {value!r} to Decimal") from exc

    negative = d < 0
    d_abs = abs(d)

    # Quantise to the requested number of decimal places.
    quant = Decimal(10) ** -decimals if decimals > 0 else Decimal(1)
    quantised = d_abs.quantize(quant)

    # Split into integer and fractional string parts.
    s = str(quantised)
    if "." in s:
        int_str, frac_str = s.split(".")
    else:
        int_str, frac_str = s, ""

    # Build Indian-grouped integer string: last 3 digits, then pairs leftward.
    grouped = _group_indian(int_str)

    result = f"{grouped}.{frac_str}" if decimals > 0 else grouped

    # Sign prefix.
    if negative:
        result = "-" + result
    elif sign:
        result = "+" + result

    # Right-align to minimum width.
    if width > 0:
        result = result.rjust(width)

    return result


def _group_indian(digits: str) -> str:
    """Return *digits* (non-negative integer string) grouped in Indian style.

    Args:
        digits: A string of decimal digits (no sign, no decimal point).

    Returns:
        Comma-separated string: last 3 digits as first group, then pairs.

    Examples:
        >>> _group_indian("1391279")
        '13,91,279'
        >>> _group_indian("100")
        '100'
        >>> _group_indian("1000")
        '1,000'
    """
    if len(digits) <= 3:
        return digits

    grouped = digits[-3:]
    remainder = digits[:-3]
    while remainder:
        grouped = remainder[-2:] + "," + grouped
        remainder = remainder[:-2]
    return grouped
