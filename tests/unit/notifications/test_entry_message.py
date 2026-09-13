"""Tests for the unified entry confirmation renderer (UEM-1)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.notifications.entry_message import EntryMessage, format_entry_message
from src.notifications.formatting import LegRow
from src.notifications.markdown import MARKDOWNV2_RESERVED

_LEGS = [
    LegRow(role="Short", instrument="23500 PE", delta=-0.19, ltp=70.8, entry=103.4),
    LegRow(role="Long", instrument="23000 PE", delta=-0.07, ltp=23.8, entry=21.2),
    LegRow(role="Short", instrument="24500 CE", delta=0.22, ltp=73.5, entry=91.3),
    LegRow(role="Long", instrument="25000 CE", delta=0.06, ltp=17.1, entry=15.4),
]


def _msg(**overrides) -> EntryMessage:
    base = dict(
        headline_label="IC v1",
        expiry_type="weekly",
        expiry=date(2026, 9, 9),
        mode="standalone",
        ivr=0.16,
        dte=4,
        spot=23980.0,
        net_credit=Decimal("103.40"),
        legs=_LEGS,
    )
    base.update(overrides)
    return EntryMessage(**base)


def test_happy_path_full_structure_in_order() -> None:
    out = format_entry_message(_msg()).splitlines()
    assert out[0] == "✅ *IC v1 Entry* — weekly"
    assert out[1] == "*Mode:* standalone"
    assert out[2].startswith("*IVR:* 0") and "*DTE:* 4" in out[2] and "*Exp:* 09 SEP 26" in out[2]
    assert out[3] == ""
    assert out[4] == "```"
    assert out[5].startswith("Act")  # build_leg_table header
    assert out.index("```", 5) > 5  # closing fence present
    assert out[-1].startswith("💰 *Net credit:*")


def test_mode_none_omits_mode_line() -> None:
    out = format_entry_message(_msg(mode=None)).splitlines()
    assert not any(ln.startswith("*Mode:*") for ln in out)
    assert out[0].startswith("✅ ")
    assert out[1].startswith("*IVR:*")  # kv row directly after headline


def test_headline_uses_headline_label() -> None:
    assert format_entry_message(_msg(headline_label="IC v2", expiry_type="monthly")).startswith(
        "✅ *IC v2 Entry* — monthly"
    )
    assert format_entry_message(_msg(headline_label="IC v1", expiry_type="weekly")).startswith(
        "✅ *IC v1 Entry* — weekly"
    )


def test_leg_rows_badge_and_spaced_instrument() -> None:
    out = format_entry_message(_msg())
    fence = out.split("```")[1].splitlines()
    body = [ln for ln in fence if ln.startswith(("[S]", "[B]"))]
    assert len(body) == 4
    assert body[0].startswith("[S] 23500 PE")  # spaced, never bare "23500PE"
    assert body[1].startswith("[B] 23000 PE")
    assert "23500PE" not in out and "24500CE" not in out


def test_delta_via_format_greek_signed_2dp() -> None:
    out = format_entry_message(_msg())
    fence = out.split("```")[1]
    assert "-0.19" in fence and "+0.22" in fence
    assert "0.190" not in fence  # not the old 3dp abs() rendering


def test_net_credit_line_uses_format_money_both_sides() -> None:
    out = format_entry_message(_msg()).splitlines()[-1]
    # ₹103.40/lot  ×65 = ₹6,721.00 — with reserved chars escaped
    assert "/lot" in out and "×65" in out
    assert "6,721" in out.replace("\\", "")
    assert "₹103.40/lot" in out.replace("\\", "")


def test_reserved_chars_escaped_outside_fence() -> None:
    out = format_entry_message(_msg())
    head, _, rest = out.partition("```")
    tail = rest.split("```", 1)[1]
    for segment in (head, tail):
        # strip paired bold markers — the only intentionally-literal reserved char
        assert segment.count("*") % 2 == 0
        stripped = segment.replace("*", "")
        for i, ch in enumerate(stripped):
            if ch in MARKDOWNV2_RESERVED and ch != "*":
                assert i > 0 and stripped[i - 1] == "\\", f"unescaped {ch!r} in {segment!r}"
            if ch == "\\":
                assert i + 1 < len(stripped) and stripped[i + 1] in MARKDOWNV2_RESERVED


def test_empty_legs_raises() -> None:
    with pytest.raises(ValueError):
        format_entry_message(_msg(legs=[]))


def test_single_leg_no_ivr_omits_ivr_segment() -> None:
    msg = _msg(
        headline_label="CSP",
        ivr=None,
        expiry_type=None,
        mode=None,
        legs=[LegRow(role="Short", instrument="23500 PE", delta=-0.19, ltp=70.8, entry=103.4)],
    )
    out = format_entry_message(msg).splitlines()
    assert out[0] == "✅ *CSP Entry*"
    assert "*IVR:*" not in "\n".join(out)

    fence = "\n".join(out).split("```")[1].splitlines()
    body = [ln for ln in fence if ln.startswith(("[S]", "[B]"))]
    assert len(body) == 1
    assert body[0].startswith("[S] 23500 PE")


def test_ivr_present_renders_ivr_segment() -> None:
    msg = _msg(
        headline_label="CSP",
        ivr=0.14,
        expiry_type=None,
        mode=None,
        legs=[LegRow(role="Short", instrument="23500 PE", delta=-0.19, ltp=70.8, entry=103.4)],
    )
    out = format_entry_message(msg).splitlines()
    assert out[0] == "✅ *CSP Entry*"
    # Note: escaped 0.14 is 0\.14
    assert "*IVR:* 0\\.14" in "\n".join(out)


def test_net_debit_line_when_net_credit_negative() -> None:
    out = format_entry_message(_msg(net_credit=Decimal("-25.00"))).splitlines()
    assert out[-1] == "💰 *Net debit:* ₹25\\.00/lot  ×65 \\= ₹1,625\\.00"


def test_net_credit_line_unchanged_for_zero() -> None:
    out = format_entry_message(_msg(net_credit=Decimal("0"))).splitlines()
    assert out[-1] == "💰 *Net credit:* ₹0\\.00/lot  ×65 \\= ₹0\\.00"
