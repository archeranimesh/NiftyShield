"""IC entry confirmation message — one MarkdownV2 fenced-table renderer for v1 and v2.

ROLL-17 (`docs/plan/telegram-markdown-migration/strategy-rollout/stories.md`). Design closed
2026-09-06 via a `message-format-workshop.md` session; reference implementation
`scratch/2026-09-06_ic_entry_confirmation_format.py`.

Before ROLL-17, `paper_ic_entry.py` and `paper_ic_entry_v2.py` each hand-rolled the "✅ …
Entry" success message as an independent f-string that had drifted apart in both content and
layout (v1 had a `Mode:` line, v2 none; v1 used `format_option_label()`, v2 a bare
`{int(strike)}PE` — a live violation of `src/notifications/CLAUDE.md` §"Instrument Label
Formatting"). This module is the single renderer both scripts now call.

The confirmed message is a fenced `build_leg_table()` table — `LegRow` reused verbatim, no
parallel leg model. Every dynamic value passes through `escape_markdown()`; the fenced block
is emitted literally (never run through whole-body escaping, which would break the fence).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from src.notifications.formatting import LegRow, build_leg_table, format_expiry, format_money
from src.notifications.markdown import escape_markdown
from src.paper.constants import LOT_SIZE


@dataclass
class ICEntryMessage:
    """Data for one IC entry confirmation, transport-agnostic.

    Attributes:
        strategy_name: Full strategy id (e.g. ``paper_ic_nifty_v2_monthly``); only used to
            derive the ``v1``/``v2`` headline marker (``"v2" in strategy_name``).
        expiry_type: ``"weekly"`` / ``"monthly"`` — shown after the em-dash in the headline.
        expiry: Contract expiry date; rendered once in the kv row via ``format_expiry``.
        ivr: Implied volatility rank at entry.
        dte: Days to expiry at entry.
        spot: Nifty spot at entry.
        net_credit: Per-lot net credit (Decimal, monetary).
        mode: ``"standalone"`` / ``"concurrent"`` for v1, or ``None`` for v2 (no ``Mode:``
            line emitted when ``None``).
        legs: The four IC legs as ``LegRow`` rows, in send order (short put, long put,
            short call, long call).
    """

    strategy_name: str
    expiry_type: str
    expiry: date
    ivr: float
    dte: int
    spot: float
    net_credit: Decimal
    mode: str | None = None
    legs: list[LegRow] = field(default_factory=list)


def _headline(msg: ICEntryMessage) -> str:
    """``✅ *IC v1 Entry* — {expiry_type}`` — bold marker, escaped type (workshop #E)."""
    ver = "v2" if "v2" in msg.strategy_name else "v1"
    return f"✅ *IC {ver} Entry* — {escape_markdown(msg.expiry_type)}"


def _kv_row(msg: ICEntryMessage) -> str:
    """One line: ``*IVR:* … *DTE:* … *Nifty:* … *Exp:* …`` (workshop #C)."""
    return "  ".join(
        [
            f"*IVR:* {escape_markdown(f'{msg.ivr:.2f}')}",
            f"*DTE:* {escape_markdown(str(msg.dte))}",
            f"*Nifty:* {escape_markdown(f'{msg.spot:,.0f}')}",
            f"*Exp:* {escape_markdown(format_expiry(msg.expiry))}",
        ]
    )


def _credit_line(msg: ICEntryMessage) -> str:
    """``💰 *Net credit:* ₹X/lot  ×65 = ₹Y`` — both values via ``format_money`` (#D)."""
    per_lot = escape_markdown(format_money(msg.net_credit))
    total = escape_markdown(format_money(msg.net_credit * LOT_SIZE))
    return f"💰 *Net credit:* {per_lot}/lot  ×{LOT_SIZE} \\= {total}"


def format_ic_entry_message(msg: ICEntryMessage) -> str:
    """Render an ``ICEntryMessage`` to a MarkdownV2 string.

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
