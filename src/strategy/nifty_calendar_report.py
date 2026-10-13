"""EOD audit report for an open Nifty calendar (pure; the snapshot script sends it)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.nifty_calendar.cycle import EntryPlan
from src.nifty_calendar.selector import mid
from src.notifications.calendar_messages import leg_instrument, leg_role
from src.notifications.formatting import (
    LegRow,
    build_leg_table,
    format_expiry,
    format_greek,
    format_money,
    format_pct,
    pnl_emoji,
)
from src.notifications.markdown import escape_markdown, mdcode
from src.paper.models import MarginSnapshot
from src.strategy.nifty_calendar_state import ROLES, CalendarView


def leg_rows(view: CalendarView) -> list[LegRow]:
    """Leg-table rows in canonical role order: LTP is the mid, entry the recorded fill."""
    by_key = {leg.instrument_key: leg for leg in view.structure.legs}
    by_role = {role: by_key[view.legs[role].position.instrument_key] for role in ROLES}
    return [
        LegRow(
            role=leg_role(by_role[role]),
            instrument=leg_instrument(by_role[role].strike, by_role[role].option_type.value),
            delta=float(by_role[role].delta),
            ltp=float(mid(view.quotes[role])),
            entry=float(by_role[role].entry_price),
        )
        for role in ROLES
    ]


def build_eod_report(
    view: CalendarView,
    *,
    label: str,
    strategy_name: str,
    snap_date: date,
    spot: Decimal,
    held_days: int,
    plan: EntryPlan | None,
    target: Decimal,
    margin: MarginSnapshot | None,
) -> str:
    """Render the MarkdownV2 EOD report: legs, LTP, entry, net Δ/ν, P&L, days held, exit dates.

    ``view.pnl`` is the executable P&L (buy at ask, sell at bid) in rupees. ROI divides it by
    the entry ``final_margin`` and is ``N/A`` without a margin snapshot.

    Args:
        view: The structure rebuilt at current quotes.
        label: Strategy label for the title (``Cal M``).
        strategy_name: DB strategy name.
        snap_date: Report date; DTE counts from it.
        spot: Nifty spot.
        held_days: Calendar days since the cycle's entry.
        plan: The cycle's original plan (None if it cannot be resolved).
        target: Profit target in rupees for the open lots.
        margin: Entry margin snapshot, if captured.
    """
    near_dte = (view.near_expiry - snap_date).days
    exits = (
        f"{format_expiry(plan.planned_exit_date)} (hard {format_expiry(plan.hard_exit_date)})"
        if plan is not None
        else "N/A"
    )
    if margin is not None and margin.final_margin > Decimal("0"):
        roi = escape_markdown(format_pct(float(view.pnl / margin.final_margin * 100)))
        margin_line = (
            f"🏦 *Margin:* {escape_markdown(format_money(margin.final_margin))} \\| *ROI:* {roi}"
        )
    else:
        margin_line = "🏦 *Margin:* N/A \\| *ROI:* N/A"
    m = view.metrics
    lines = [
        f"📋 *{escape_markdown(label)} EOD Audit*",
        mdcode(strategy_name),
        (
            f"*Expiry:* {escape_markdown(format_expiry(view.near_expiry))} / "
            f"{escape_markdown(format_expiry(view.far_expiry))} \\| *DTE:* {near_dte} \\| "
            f"*Nifty:* {escape_markdown(f'{spot:,.0f}')}"
        ),
        (
            f"*Net Δ:* {escape_markdown(format_greek(float(m.net_delta)))} \\| "
            f"*Net ν:* {escape_markdown(format_greek(float(m.net_vega)))}"
        ),
        f"*Held:* {held_days}d \\| *Exit:* {escape_markdown(exits)}",
        "```",
        build_leg_table(leg_rows(view)),
        "```",
        (
            f"{pnl_emoji(view.pnl)} *P&L:* {escape_markdown(format_money(view.pnl, signed=True))} "
            f"➡️ *Target:* {escape_markdown(format_money(target))}"
        ),
        margin_line,
    ]
    return "\n".join(lines)
