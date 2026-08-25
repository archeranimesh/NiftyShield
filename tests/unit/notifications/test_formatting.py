from decimal import Decimal

import pytest

from src.notifications.formatting import (
    LegRow,
    alert_emoji,
    build_kv_table,
    build_leg_table,
    build_side_by_side_kv_table,
    format_greek,
    format_money,
    format_pct,
    format_strike,
    pnl_emoji,
)


def test_format_money_happy_path():
    assert format_money(Decimal("86.68")) == "₹86.68"


def test_format_money_edge_zero():
    assert format_money(Decimal("0")) == "₹0.00"


def test_format_money_raises_type_error_on_float():
    with pytest.raises(TypeError, match="format_money requires Decimal, not float"):
        format_money(86.68)  # type: ignore


def test_format_greek_happy_path_positive():
    assert format_greek(0.28) == "+0.28"


def test_format_greek_happy_path_negative():
    assert format_greek(-0.03) == "-0.03"


def test_format_greek_edge_none():
    assert format_greek(None) == "-"


def test_format_strike_happy_path():
    assert format_strike(23000.0) == "23000"


def test_format_strike_edge_zero():
    assert format_strike(0) == "0"


def test_format_strike_raises_value_error_on_fractional():
    with pytest.raises(ValueError, match="format_strike requires an integer or whole-number float"):
        format_strike(23000.5)


def test_format_pct_happy_path_whole():
    assert format_pct(4.0) == "4%"


def test_format_pct_edge_zero():
    assert format_pct(0.0) == "0%"


def test_build_kv_table_happy_path():
    result = build_kv_table(
        "Snapshot",
        [("DTE", "18"), ("IVR", "0.16"), ("Nifty", "24,571")],
    )
    lines = result.split("\n")
    assert lines[0] == "Snapshot"
    assert "DTE" in result and "18" in result
    assert "Nifty" in result and "24,571" in result
    # every non-title row (header/border/data) shares one width
    row_lines = [ln for ln in lines[1:] if ln]
    assert len({len(ln) for ln in row_lines}) == 1


def test_build_kv_table_computes_width_from_longest_label():
    # guards against the hand-counted-width bug class (FMT-3 stories.md)
    result = build_kv_table(
        "Comparison",
        [("Realized (inception)", "₹1,204"), ("DTE", "18")],
    )
    lines = result.split("\n")
    data_lines = [ln for ln in lines if ln.startswith("Realized") or ln.startswith("DTE")]
    assert len({len(ln) for ln in data_lines}) == 1
    assert "Realized (inception)" in result


def test_build_kv_table_raises_on_empty_rows():
    with pytest.raises(ValueError, match="build_kv_table requires at least one row"):
        build_kv_table("Empty", [])


def test_build_side_by_side_kv_table_mismatched_row_counts_pads():
    result = build_side_by_side_kv_table(
        "V1",
        [("DTE", "18"), ("IVR", "0.16"), ("Nifty", "24,571"), ("Margin", "82,628")],
        "V2",
        [("DTE", "19"), ("IVR", "0.20")],
    )
    lines = result.split("\n")
    # both sides must produce the same number of output lines
    assert len({len(ln.split(" | ")) for ln in lines}) == 1
    for ln in lines:
        left, right = ln.split(" | ")
        assert len(left) == len(lines[0].split(" | ")[0])
        assert len(right) == len(lines[0].split(" | ")[1])
    assert "Margin" in result and "82,628" in result


def test_build_side_by_side_kv_table_equal_row_counts_no_padding():
    result = build_side_by_side_kv_table(
        "V1",
        [("DTE", "18"), ("IVR", "0.16")],
        "V2",
        [("DTE", "19"), ("IVR", "0.20")],
    )
    lines = result.split("\n")
    assert all(" | " in ln for ln in lines)
    assert "18" in result and "19" in result


def test_build_leg_table_happy_path_mixed_legs():
    legs = [
        LegRow(role="Short Put", instrument="23000 PE", delta=-0.03, ltp=9.30, entry=71.80),
        LegRow(role="Long Put", instrument="22500 PE", delta=None, ltp=6.40, entry=None),
        LegRow(role="Short Call", instrument="25000 CE", delta=0.28, ltp=100.40, entry=70.50),
    ]
    result = build_leg_table(legs)
    lines = result.split("\n")
    assert lines[0].startswith("Act")
    assert "[S]" in result and "[B]" in result
    assert "-0.03" in result and "+0.28" in result
    # None delta/entry render as "-"
    long_put_line = next(ln for ln in lines if "22500 PE" in ln)
    assert long_put_line.rstrip().endswith("-")
    # all rows share one width
    data_lines = lines[2:]
    assert len({len(ln) for ln in data_lines}) == 1


def test_build_leg_table_single_leg():
    legs = [LegRow(role="Short Put", instrument="23000 PE", delta=-0.03, ltp=9.30, entry=71.80)]
    result = build_leg_table(legs)
    assert "23000 PE" in result
    assert "[S]" in result


def test_build_leg_table_raises_on_empty_legs():
    with pytest.raises(ValueError, match="build_leg_table requires at least one leg"):
        build_leg_table([])


def test_pnl_emoji_positive():
    assert pnl_emoji(Decimal("3.52")) == "\u2705"


def test_pnl_emoji_negative():
    assert pnl_emoji(Decimal("-3.52")) == "\U0001f53b"


def test_pnl_emoji_zero():
    assert pnl_emoji(Decimal("0")) == "\u2796"


def test_alert_emoji_empty_list():
    assert alert_emoji([]) == "\U0001f7e2"


def test_alert_emoji_single_signal():
    assert alert_emoji(["DELTA_WARN"]) == "\u26a0\ufe0f"


def test_alert_emoji_multiple_signals():
    assert alert_emoji(["DELTA_WARN", "TIME_STOP"]) == "\u26a0\ufe0f"


def test_alert_emoji_not_substring_matched():
    # A signal code without "WARN" in it must still trigger the warning
    # emoji -- alert_emoji is presence-based, never a substring match on
    # the signal code name (see FMT-1b's rejected design).
    assert alert_emoji(["GAMMA_RISK_ACTION"]) == "\u26a0\ufe0f"
