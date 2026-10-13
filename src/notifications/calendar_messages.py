"""Telegram message builders for the Nifty calendar (entry, close, re-centre).

Pure functions over the shared ``EntryMessage`` / ``ExitMessage`` renderers: no parallel leg
model and no escaping of their own, so every value is escaped at the one boundary those
renderers own. ``src.nifty_calendar`` stays a leaf; this module reads its models, not the
reverse.

Which P&L the close message shows: the **net** four-leg figure. ``ExitMessage`` is built with
``cycle_decay_pct=None``, so the cycle line is net realized P&L and days held only; the
short-straddle-only decay (``short_decay_pct``) excludes the long wings and would overstate
the result, so it is deliberately not passed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.nifty_calendar.models import CalendarLeg, CalendarStructure, StructureMetrics
from src.notifications.entry_message import EntryMessage, format_entry_message
from src.notifications.exit_message import ExitKind, ExitMessage, format_exit_message
from src.notifications.formatting import (
    CloseLegRow,
    LegRow,
    format_greek,
    format_pct_signed,
    format_strike,
)
from src.notifications.markdown import escape_markdown
from src.paper.cycle_pnl import CycleStats


def leg_role(leg: CalendarLeg) -> str:
    """Display role such as ``"Short Call"`` (the ``Short``/``Long`` prefix drives the badge)."""
    side = "Short" if leg.side.value == "SELL" else "Long"
    return f"{side} {'Call' if leg.option_type.value == 'CE' else 'Put'}"


def leg_instrument(strike: Decimal, option_type: str) -> str:
    """``"22700 CE"`` via ``format_strike`` (identifier: no separator, no decimals)."""
    return f"{format_strike(int(strike))} {option_type}"


def build_calendar_entry_message(
    structure: CalendarStructure,
    metrics: StructureMetrics,
    spot: Decimal,
    today: date,
    *,
    ltps: dict[str, Decimal] | None = None,
    headline_label: str = "Cal M",
) -> EntryMessage:
    """Build the two-expiry entry confirmation for a calendar structure.

    Args:
        structure: The entered four-leg structure.
        metrics: Its ``compute_metrics`` result (delta, vega, breakevens, risk-reward).
        spot: Nifty spot at entry.
        today: Entry date; DTE is counted from it to each expiry.
        ltps: Optional ``instrument_key`` to last price; defaults to the entry price.
        headline_label: Strategy label shown in the headline.

    Returns:
        An ``EntryMessage`` with ``far_expiry`` / ``far_dte`` and the detail lines set.
    """
    ltps = ltps or {}
    rows = [
        LegRow(
            role=leg_role(leg),
            instrument=leg_instrument(leg.strike, leg.option_type.value),
            delta=float(leg.delta),
            ltp=float(ltps.get(leg.instrument_key, leg.entry_price)),
            entry=float(leg.entry_price),
        )
        for leg in structure.legs
    ]
    return EntryMessage(
        headline_label=headline_label,
        expiry=structure.near_expiry,
        dte=(structure.near_expiry - today).days,
        far_expiry=structure.far_expiry,
        far_dte=(structure.far_expiry - today).days,
        spot=float(spot),
        net_credit=metrics.net_credit_per_unit,
        legs=rows,
        detail_lines=_detail_lines(metrics),
    )


def _detail_lines(m: StructureMetrics) -> list[str]:
    """Greeks, breakevens with signed % distance, and risk-reward as plain lines."""
    low_pct = format_pct_signed(-float(m.breakeven_low_pct))
    high_pct = format_pct_signed(float(m.breakeven_high_pct))
    return [
        f"Δ {format_greek(float(m.net_delta))}  ν {format_greek(float(m.net_vega))}",
        f"BE {m.breakeven_low:,.0f} ({low_pct})  {m.breakeven_high:,.0f} ({high_pct})",
        f"R:R {m.risk_reward:.2f}",
    ]


def build_calendar_exit_message(
    *,
    signal: str,
    near_dte: int,
    held_days: int,
    legs: list[CloseLegRow],
    cycle_pnl: Decimal,
    cycle_index: int,
    inception_pnl: Decimal,
    stats: CycleStats | None = None,
    recentre: bool = False,
    headline_label: str = "Cal M",
) -> ExitMessage:
    """Build the close confirmation, reusing ``ExitMessage`` unchanged.

    ``signal`` is the ``ExitDecision`` reason; ``near_dte`` is the near-expiry DTE (the
    convention for a two-expiry structure). The cycle line shows the net four-leg P&L.

    Args:
        signal: Exit reason text.
        near_dte: Days to the near expiry at close.
        held_days: Days the cycle was held.
        legs: One ``CloseLegRow`` per closed leg.
        cycle_pnl: Net realized P&L of the just-closed four-leg cycle.
        cycle_index: The closed cycle's index.
        inception_pnl: Strategy-lifetime realized P&L.
        stats: Closed-cycle stats for the win-rate row.
        recentre: True renders the headline as a roll rather than a close.
        headline_label: Strategy label shown in the headline.
    """
    return ExitMessage(
        headline_label=headline_label,
        kind=ExitKind.ROLL if recentre else ExitKind.CLOSE,
        signal=signal,
        dte=near_dte,
        held_days=held_days,
        legs=legs,
        this_exit_pnl=sum((r.pnl for r in legs), Decimal("0")),
        cycle_pnl=cycle_pnl,
        cycle_index=cycle_index,
        cycle_held_days=held_days,
        inception_pnl=inception_pnl,
        stats=stats,
    )


def format_recentre_message(close: ExitMessage, entry: EntryMessage) -> str:
    """One MarkdownV2 message showing the close and the new entry, not two unrelated ones."""
    rule = escape_markdown("─" * 14)
    return "\n".join(
        [
            f"🔄 *{escape_markdown(entry.headline_label)} Re\\-centre*",
            "",
            format_exit_message(close),
            "",
            rule,
            "",
            format_entry_message(entry),
        ]
    )
