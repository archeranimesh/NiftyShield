# src/paper/formatting.py
"""Shared output formatting utilities for paper trading scripts."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def fmt_inr(value: Decimal, sign_always: bool = False) -> str:
    """Format a Decimal as an INR string with a rupee symbol.

    Args:
        value: The monetary value to format.
        sign_always: If True, always include the + or - sign.

    Returns:
        Formatted string, e.g., "₹1,234" or "₹+1,234".
    """
    if value is None:
        return "₹-"

    fmt = "+," if sign_always else ","
    return f"₹{value:{fmt}.0f}"


def format_pnl_table(rows: list[dict[str, Any]], title: str = "", is_dry_run: bool = False) -> str:
    """Render a compact P&L table: Strategy | Unrealized | Realized | Total P&L.

    Args:
        rows: List of dicts with keys: 'strategy', 'unrealized', 'realized', 'total'.
        title: Optional title for the table.
        is_dry_run: If True, prefix the title with [DRY RUN].

    Returns:
        Formatted table string.
    """
    lines = []

    # Title line
    prefix = "[DRY RUN] " if is_dry_run else ""
    if title:
        lines.append(f"{prefix}{title}")

    # Header
    # Column widths: strategy 30, others 14
    header = f"{'Strategy':<30} {'Unrealized':>14} {'Realized':>14} {'Total P&L':>14}"
    lines.append(header)
    lines.append("─" * len(header))

    if not rows:
        lines.append("No active strategies found.")
        return "\n".join(lines)

    for row in rows:
        strategy = row.get("strategy", "Unknown")[:30]
        unrealized = fmt_inr(row.get("unrealized", Decimal("0")), sign_always=True)
        realized = fmt_inr(row.get("realized", Decimal("0")), sign_always=True)
        total = fmt_inr(row.get("total", Decimal("0")), sign_always=True)

        lines.append(f"{strategy:<30} {unrealized:>14} {realized:>14} {total:>14}")

    return "\n".join(lines)


_PERIOD_HEADERS: dict[str, tuple[str, str, str]] = {
    "daily": ("Day Base", "Day Overlay", "Day Net"),
    "inception": ("Base P&L", "Overlay", "Net P&L"),
}


def format_track_summary(
    rows: list[dict[str, Any]],
    title: str = "",
    is_dry_run: bool = False,
    period: str = "inception",
) -> str:
    """Render the 3-track cross-comparison summary table.

    Args:
        rows: List of dicts with keys: 'track', 'base_pnl', 'overlay_pnl', 'net_pnl',
            'return_on_nee'.
        title: Optional title line printed above the table.
        is_dry_run: If True, prefix the title with [DRY RUN].
        period: Display period — 'daily' shows 1-day delta headers; 'inception' shows
            since-inception totals (default).

    Returns:
        Formatted table string.
    """
    W = 88
    h_base, h_overlay, h_net = _PERIOD_HEADERS.get(period, _PERIOD_HEADERS["inception"])
    lines = []
    if title:
        prefix = "[DRY RUN] " if is_dry_run else ""
        lines.append(f"{prefix}{title}")
    lines.append("═" * W)
    lines.append(f"  {'Track':<28} {h_base:>12} {h_overlay:>12} {h_net:>12} {'Ret/NEE':>9}")
    lines.append(f"  {'─' * (W - 4)}")

    for row in rows:
        label = row.get("track", row.get("label", "Unknown"))[:28]
        base_pnl = fmt_inr(row.get("base_pnl", Decimal("0")))
        overlay_pnl = fmt_inr(row.get("overlay_pnl", Decimal("0")))
        net_pnl = fmt_inr(row.get("net_pnl", Decimal("0")))
        ret_nee = row.get("return_on_nee", 0.0)

        lines.append(
            f"  {label:<28} {base_pnl:>12} {overlay_pnl:>12} {net_pnl:>12} {ret_nee:>8.2f}%"
        )

    lines.append("═" * W)
    return "\n".join(lines)
