"""Tests for the Nifty calendar Telegram message builders (CM-6)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.nifty_calendar.payoff import compute_metrics
from src.notifications.calendar_messages import (
    build_calendar_entry_message,
    build_calendar_exit_message,
    format_recentre_message,
)
from src.notifications.entry_message import format_entry_message
from src.notifications.exit_message import format_exit_message
from src.notifications.formatting import CloseLegRow
from src.notifications.markdown import MARKDOWNV2_RESERVED
from tests.unit.nifty_calendar.test_payoff import _make_video_fixture

TODAY = date(2026, 10, 7)


def _entry():
    structure, spot, carry, lot = _make_video_fixture()
    metrics = compute_metrics(structure, spot, far_carry=carry, lot_size=lot)
    return build_calendar_entry_message(structure, metrics, spot, TODAY), metrics


def _legs() -> list[CloseLegRow]:
    return [
        CloseLegRow("Short Call", "22700 CE", Decimal("310"), Decimal("200"), Decimal("7150")),
        CloseLegRow("Long Put", "22100 PE", Decimal("225"), Decimal("180"), Decimal("-2925")),
    ]


def _exit(**kw):
    base = dict(
        signal="Target hit (+₹3,000)",
        near_dte=20,
        held_days=7,
        legs=_legs(),
        cycle_pnl=Decimal("4225"),
        cycle_index=3,
        inception_pnl=Decimal("9000"),
    )
    return build_calendar_exit_message(**{**base, **kw})


def test_calendar_entry_message_renders_two_expiries() -> None:
    msg, metrics = _entry()
    out = format_entry_message(msg).replace("\\", "")
    assert out.startswith("✅ *Cal M Entry*")
    assert "*DTE:* 20/48" in out and "27 OCT 26/24 NOV 26" in out
    fence = out.split("```")[1]
    assert [ln[:3] for ln in fence.splitlines() if ln.startswith(("[S]", "[B]"))] == [
        "[S]",
        "[S]",
        "[B]",
        "[B]",
    ]
    assert "Δ +0.04" in out and "BE 22,1" in out and "R:R" in out
    assert msg.net_credit == metrics.net_credit_per_unit


def test_markdownv2_escaping() -> None:
    """Outside fences, every reserved char other than the bold markers is backslash-escaped."""
    msg, _ = _entry()
    exit_msg = _exit()
    text = format_recentre_message(exit_msg, msg)
    outside = "".join(text.split("```")[0::2])
    for i, ch in enumerate(outside):
        if ch in MARKDOWNV2_RESERVED and ch != "*":
            assert outside[i - 1] == "\\", f"unescaped {ch!r} at {i}"
    assert outside.count("*") % 2 == 0


def test_close_message_shows_net_cycle_pnl_without_short_decay() -> None:
    out = format_exit_message(_exit()).replace("\\", "")
    assert "Cycle P&L (#3)" in out and "+₹4,225.00" in out
    assert "decay" not in out
    assert "Closed" in out and "*DTE:* 20" in out


def test_recentre_is_one_message_with_close_then_entry() -> None:
    msg, _ = _entry()
    text = format_recentre_message(_exit(recentre=True), msg)
    assert text.startswith("🔄 *Cal M Re\\-centre*")
    assert text.index("Rolled") < text.index("Cal M Entry")


def test_biweekly_label_renders() -> None:
    from src.nifty_calendar.config import BIWEEKLY

    structure, spot, carry, lot = _make_video_fixture()
    metrics = compute_metrics(structure, spot, far_carry=carry, lot_size=lot)
    msg = build_calendar_entry_message(
        structure, metrics, spot, TODAY, headline_label=BIWEEKLY.label
    )
    assert format_entry_message(msg).replace("\\", "").startswith("✅ *Cal BW Entry*")
    assert "Cal BW" in format_exit_message(_exit(headline_label=BIWEEKLY.label)).replace("\\", "")
