"""Shared exit-confirmation renderer for paper strategies (IC, CSP, CC, etc.).

UXM-2 (`docs/plan/telegram-message-unification/unified-exit-message/stories.md`). Mirrors
`entry_message.py`'s design — a typed dataclass + a pure `format_*` function, every dynamic
value passed through `escape_markdown()`, the fenced table emitted literally.

Carries three P&L levels: this-exit (legs closed in this action), cycle (the just-closed
round trip, via `src.paper.cycle_pnl.Cycle` / `cycle_stats`), and inception
(`get_strategy_realized_pnl`) — see the story's prompt.md for why these differ and which one
drives the headline number.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from src.notifications.formatting import CloseLegRow, build_close_leg_table, format_money
from src.notifications.markdown import escape_markdown
from src.paper.constants import LOT_SIZE
from src.paper.cycle_pnl import CycleStats


class ExitKind(str, Enum):
    """Maps to the headline emoji/verb in format_exit_message."""

    CLOSE = "close"
    ROLL = "roll"
    CRASH_MONETIZE = "crash_monetize"
    WAITING = "waiting"


_HEADLINE_EMOJI = {
    ExitKind.CLOSE: "✅",
    ExitKind.ROLL: "🔄",
    ExitKind.CRASH_MONETIZE: "💰",
    ExitKind.WAITING: "⛔",
}

_HEADLINE_VERB = {
    ExitKind.CLOSE: "Closed",
    ExitKind.ROLL: "Rolled",
    ExitKind.CRASH_MONETIZE: "Closed",
    ExitKind.WAITING: "Closed — waiting",
}


@dataclass(frozen=True)
class ExitMessage:
    """Data for one close confirmation, transport-agnostic.

    Attributes:
        headline_label: Rendered in the headline, e.g. "IC v1", "CSP", "CC".
        kind: Picks the headline emoji/verb.
        signal: Free-text exit reason, escaped.
        dte: Days to expiry at close.
        held_days: Days this action's leg(s) were held.
        legs: 1..N legs closed in this action, as CloseLegRow rows.
        this_exit_pnl: Realized P&L for the leg(s) closed in this action.
        per_lot: When True, also show `this_exit_pnl` as a per-lot figure.
        cycle_pnl: Realized P&L of the just-closed round-trip cycle, or None
            for a partial close where no cycle closed.
        cycle_index: The closed cycle's index, or None.
        cycle_decay_pct: Gross-short-premium decay % for the cycle, or None
            for a pure-long cycle with no short leg (PP).
        cycle_short_credit: Gross short credit per unit for the cycle, or None.
        cycle_short_buyback: Gross short buyback per unit for the cycle, or None.
        cycle_held_days: Days held over the whole cycle, or None.
        inception_pnl: Strategy-lifetime realized P&L (get_strategy_realized_pnl).
        stats: Win-rate/P&L stats over closed cycles; the win-rate row renders
            only when stats is not None and stats.closed_count >= 5.
        overlay_total_pnl: Overlay-strategy total realized P&L, or None to omit
            the row (non-overlay strategies).
        state_line: Optional trailing `-> *State:* ...` line (e.g. PP
            crash-monetize's RE_ENTRY_PENDING note).
    """

    headline_label: str
    kind: ExitKind
    signal: str
    dte: int
    held_days: int
    legs: list[CloseLegRow]
    this_exit_pnl: Decimal
    per_lot: bool = False
    cycle_pnl: Decimal | None = None
    cycle_index: int | None = None
    cycle_decay_pct: Decimal | None = None
    cycle_short_credit: Decimal | None = None
    cycle_short_buyback: Decimal | None = None
    cycle_held_days: int | None = None
    inception_pnl: Decimal = Decimal("0")
    stats: CycleStats | None = None
    overlay_total_pnl: Decimal | None = None
    state_line: str | None = None

    def __post_init__(self) -> None:
        if self.cycle_pnl is not None:
            if self.cycle_index is None or self.cycle_held_days is None:
                raise ValueError(
                    "cycle_index and cycle_held_days are required when cycle_pnl is set"
                )
        if self.cycle_decay_pct is not None:
            if self.cycle_short_credit is None or self.cycle_short_buyback is None:
                raise ValueError(
                    "cycle_short_credit and cycle_short_buyback are required when "
                    "cycle_decay_pct is set"
                )


def _headline(msg: ExitMessage) -> str:
    """``{emoji} *<label> <Verb>* — <signal>`` — bold marker, escaped signal."""
    emoji = _HEADLINE_EMOJI[msg.kind]
    verb = _HEADLINE_VERB[msg.kind]
    label = escape_markdown(msg.headline_label)
    signal = escape_markdown(msg.signal)
    return f"{emoji} *{label} {verb}* — {signal}"


def _kv_row(msg: ExitMessage) -> str:
    """One line: ``*Signal:* ... *DTE:* ... *Held:* ...d``."""
    signal = escape_markdown(msg.signal)
    dte = escape_markdown(str(msg.dte))
    held = escape_markdown(str(msg.held_days))
    return f"*Signal:* {signal}   *DTE:* {dte}   *Held:* {held}d"


def _this_exit_line(msg: ExitMessage) -> str:
    """``💰 *This exit:* {+₹x}   [(₹y/lot)]`` — dropped when collapsed into the cycle line."""
    value = escape_markdown(format_money(msg.this_exit_pnl, signed=True))
    out = f"💰 *This exit:* {value}"
    if msg.per_lot:
        per_lot_value = escape_markdown(format_money(msg.this_exit_pnl / LOT_SIZE, signed=True))
        out += f"   \\({per_lot_value}/lot\\)"
    return out


def _cycle_line(msg: ExitMessage) -> str | None:
    """``🔁 *Cycle #{i}:* {+₹cycle}  ·  ₹{credit} → ₹{buyback}  ·  {d}% decay  ·  {h}d``.

    None when there is no closed cycle (partial close). Drops the credit/buyback/decay
    segment when cycle_decay_pct is None (pure-long cycle, e.g. PP).
    """
    if msg.cycle_pnl is None:
        return None

    idx = escape_markdown(str(msg.cycle_index))
    pnl = escape_markdown(format_money(msg.cycle_pnl, signed=True))
    held = escape_markdown(str(msg.cycle_held_days))

    if msg.cycle_decay_pct is None:
        return f"🔁 *Cycle \\#{idx}:* {pnl}  ·  {held}d"

    credit = escape_markdown(format_money(msg.cycle_short_credit))
    buyback = escape_markdown(format_money(msg.cycle_short_buyback))
    decay = escape_markdown(f"{msg.cycle_decay_pct:.0f}")
    return f"🔁 *Cycle \\#{idx}:* {pnl}  ·  {credit} → {buyback}  ·  {decay}% decay  ·  {held}d"


def _win_rate_line(stats: CycleStats) -> str | None:
    """``🎯 *Win rate:* {r}%  ({W}W / {L}L)   [{D}% avg decay]   avg {+₹aw} / {-₹al}``.

    None when stats.closed_count < 5 (caller gates this — kept here as a defensive no-op).
    """
    if stats.closed_count < 5 or stats.win_rate is None:
        return None

    rate = escape_markdown(f"{stats.win_rate * 100:.0f}")
    wins = escape_markdown(str(stats.wins))
    losses = escape_markdown(str(stats.losses))
    avg_win = escape_markdown(format_money(stats.avg_win, signed=True))
    avg_loss = escape_markdown(format_money(stats.avg_loss, signed=True))

    out = f"🎯 *Win rate:* {rate}%  \\({wins}W / {losses}L\\)"
    if stats.avg_decay_pct is not None:
        decay = escape_markdown(f"{stats.avg_decay_pct:.0f}")
        out += f"   {decay}% avg decay"
    out += f"   avg {avg_win} / {avg_loss}"
    return out


def format_exit_message(msg: ExitMessage) -> str:
    """Render an ``ExitMessage`` to a MarkdownV2 string.

    Layout: bold headline, kv row, a blank line, the fenced
    ``build_close_leg_table()`` block, a divider, then the this-exit / cycle /
    inception / win-rate / overlay-total / state footer lines.

    Args:
        msg: The exit data. ``legs`` must be non-empty (``build_close_leg_table``
            raises otherwise).

    Returns:
        A MarkdownV2-safe message body. Every interpolated value is
        backslash-escaped; the fenced table is emitted literally.
    """
    head = [_headline(msg), _kv_row(msg)]
    table = ["```", build_close_leg_table(msg.legs), "```"]

    footer: list[str] = ["━━━━━━━━━━━━━━━━━━━━━━━━"]
    cycle_line = _cycle_line(msg)
    collapse = (
        cycle_line is not None
        and msg.cycle_pnl is not None
        and abs(msg.this_exit_pnl - msg.cycle_pnl) < Decimal("1")
    )
    if not collapse:
        footer.append(_this_exit_line(msg))
    if cycle_line is not None:
        footer.append(cycle_line)

    inception = escape_markdown(format_money(msg.inception_pnl, signed=True))
    footer.append(f"📈 *Inception:* {inception}")

    if msg.stats is not None:
        win_rate_line = _win_rate_line(msg.stats)
        if win_rate_line is not None:
            footer.append(win_rate_line)

    if msg.overlay_total_pnl is not None:
        overlay = escape_markdown(format_money(msg.overlay_total_pnl, signed=True))
        footer.append(f"📊 *Overlay P&L \\(total realized\\):* {overlay}")

    if msg.state_line is not None:
        footer.append(f"→ *State:* {escape_markdown(msg.state_line)}")

    return "\n".join([*head, "", *table, "", *footer])
