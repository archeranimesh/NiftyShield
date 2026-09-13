"""Shared entry-confirmation renderer for paper strategies (IC, CSP, CC, etc.).

ROLL-17 (`docs/plan/telegram-markdown-migration/strategy-rollout/stories.md`). Design closed
2026-09-06 via a `message-format-workshop.md` session; reference implementation
`scratch/2026-09-06_ic_entry_confirmation_format.py`.
Originally built for IC, generalized in UEM-1.

The confirmed message is a fenced `build_leg_table()` table — `LegRow` reused verbatim, no
parallel leg model. Every dynamic value passes through `escape_markdown()`; the fenced block
is emitted literally (never run through whole-body escaping, which would break the fence).

`net_credit` is signed: positive = credit received (IC / CSP / CC / short-call overlays),
negative = debit paid (collar, PP re-entry) — `_credit_line` picks the label from the sign
(OEM-1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from src.notifications.formatting import LegRow, build_leg_table, format_expiry, format_money
from src.notifications.markdown import escape_markdown
from src.paper.constants import LOT_SIZE


@dataclass
class EntryMessage:
    """Data for one entry confirmation, transport-agnostic.

    Attributes:
        headline_label: Rendered in the headline, e.g. ``"IC v1"``, ``"CSP"``, ``"CC"``.
        expiry: Contract expiry date; rendered once in the kv row via ``format_expiry``.
        dte: Days to expiry at entry.
        spot: Nifty spot at entry.
        net_credit: Per-lot net credit (Decimal, monetary).
        ivr: Implied volatility rank at entry. Optional — omitted when not in scope (e.g. CSP entry).
        mode: Optional ``"standalone"`` / ``"concurrent"`` (e.g. IC v1); no ``Mode:`` line when ``None``.
        expiry_type: Optional ``"weekly"`` / ``"monthly"`` — shown after em-dash if present.
        legs: 1..N legs in send order as ``LegRow`` rows.
    """

    headline_label: str
    expiry: date
    dte: int
    spot: float
    net_credit: Decimal
    ivr: float | None = None
    mode: str | None = None
    expiry_type: str | None = None
    legs: list[LegRow] = field(default_factory=list)


def _headline(msg: EntryMessage) -> str:
    """``✅ *<label> Entry*[ — <expiry_type>]`` — bold marker, optional escaped type."""
    out = f"✅ *{escape_markdown(msg.headline_label)} Entry*"
    if msg.expiry_type is not None:
        out += f" — {escape_markdown(msg.expiry_type)}"
    return out


def _kv_row(msg: EntryMessage) -> str:
    """One line: ``[*IVR:* …] *DTE:* … *Nifty:* … *Exp:* …`` (workshop #C)."""
    parts = []
    if msg.ivr is not None:
        parts.append(f"*IVR:* {escape_markdown(f'{msg.ivr:.2f}')}")
    parts.extend(
        [
            f"*DTE:* {escape_markdown(str(msg.dte))}",
            f"*Nifty:* {escape_markdown(f'{msg.spot:,.0f}')}",
            f"*Exp:* {escape_markdown(format_expiry(msg.expiry))}",
        ]
    )
    return "  ".join(parts)


def _credit_line(msg: EntryMessage) -> str:
    """``💰 *Net credit/debit:* ₹X/lot  ×65 = ₹Y`` — sign of ``net_credit`` picks the label (#D)."""
    if msg.net_credit < 0:
        label = "Net debit"
        value = abs(msg.net_credit)
    else:
        label = "Net credit"
        value = msg.net_credit
    per_lot = escape_markdown(format_money(value))
    total = escape_markdown(format_money(value * LOT_SIZE))
    return f"💰 *{label}:* {per_lot}/lot  ×{LOT_SIZE} \\= {total}"


def format_entry_message(msg: EntryMessage) -> str:
    """Render an ``EntryMessage`` to a MarkdownV2 string.

    Layout: bold headline, optional ``*Mode:*`` line, one-line kv row, a blank line, the
    fenced ``build_leg_table()`` block, a blank line, the net-credit line.

    Args:
        msg: The entry data. ``legs`` must be non-empty (``build_leg_table`` raises
            otherwise).

    Returns:
        A MarkdownV2-safe message body. Every interpolated value is backslash-escaped; the
        fenced table is emitted literally.
    """
    head = [_headline(msg)]
    if msg.mode is not None:
        head.append(f"*Mode:* {escape_markdown(msg.mode)}")
    head.append(_kv_row(msg))

    table = ["```", build_leg_table(msg.legs), "```"]
    return "\n".join([*head, "", *table, "", _credit_line(msg)])
