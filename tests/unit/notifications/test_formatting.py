from datetime import date
from decimal import Decimal

import pytest

from src.notifications.formatting import (
    LegRow,
    alert_emoji,
    build_compare_table,
    build_kv_table,
    build_leg_table,
    build_side_by_side_kv_table,
    format_expiry,
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


def test_format_expiry_uppercase_leading_zero_kept():
    assert format_expiry(date(2026, 8, 25)) == "25 AUG 26"


def test_format_expiry_single_digit_day_keeps_leading_zero():
    assert format_expiry(date(2026, 7, 7)) == "07 JUL 26"


def test_build_compare_table_happy_path_single_group():
    table = build_compare_table([[("DTE", "18", "18")]], ("V1", "V2"))
    assert table == "Metric V1 V2\n------------\nDTE    18 18\n------------"


def test_build_compare_table_multiple_groups_dashed_rule_between():
    groups = [
        [("DTE", "18", "18"), ("Credit", "₹87", "₹129")],
        [("Lock Zone", "N/A", "None")],
    ]
    table = build_compare_table(groups, ("V1", "V2"))
    lines = table.split("\n")
    # header, rule, 2 rows, rule (between groups), 1 row, rule (final)
    assert lines[0] == "Metric     V1   V2"
    assert lines[1] == lines[4] == lines[-1]  # every rule line is identical
    assert lines[1] == "-" * len(lines[0])
    assert lines[-2] == "Lock Zone N/A None"


def test_build_compare_table_empty_groups_raises():
    with pytest.raises(ValueError, match="at least one group"):
        build_compare_table([], ("V1", "V2"))


def test_build_compare_table_empty_group_raises():
    with pytest.raises(ValueError, match="must each be non-empty"):
        build_compare_table([[]], ("V1", "V2"))


def test_build_compare_table_confirmed_narrow_glyphs_no_extra_padding():
    # ₹ (rupee) and Δ (delta) are individually confirmed narrow
    # (FORMATTING.md §7) -- they must not inflate column width the way an
    # unconfirmed non-ASCII character would. Column widths here are driven
    # entirely by plain-ASCII cells ("Credit"/"Put Δ" at 6 chars, "-0.03"/
    # "-0.23" at 5 chars) -- ₹87/₹129 fit inside that budget with room to
    # spare, confirming they cost only 1 display column each, not 2.
    table = build_compare_table(
        [[("Credit", "₹87", "₹129"), ("Put Δ", "-0.03", "-0.23")]], ("V1", "V2")
    )
    header, rule, credit_row, delta_row, _ = table.split("\n")
    assert header == "Metric    V1    V2"
    assert credit_row == "Credit   ₹87  ₹129"
    assert delta_row == "Put Δ  -0.03 -0.23"


def test_build_compare_table_unconfirmed_wide_glyph_gets_extra_column_width():
    # 🔴 is NOT in the confirmed-narrow set (confirmed to render
    # double-width on-device, 2026-08-26 ROLL-2a pre-check) -- the V1
    # column must widen to 6 display columns (len("3/4 🔴") == 5
    # characters but 6 display columns), not 5. If width were computed via
    # len() instead of _display_width, v1_w would be 5, not 6, and the
    # column would render one display-column too narrow on Telegram.
    table = build_compare_table([[("Legs", "3/4 🔴", "4/4")]], ("V1", "V2"))
    assert table == ("Metric     V1  V2\n-----------------\nLegs   3/4 🔴 4/4\n-----------------")


def test_build_compare_table_wide_glyph_row_display_width_matches_header():
    # The real regression this exists to catch: every rendered line must
    # occupy the same number of DISPLAY columns as the header/rule, even
    # when a row's CHARACTER count differs because of a double-width
    # glyph -- len()-based alignment (the pre-ROLL-2a bug shape) would
    # make this row one display column short.
    from src.notifications.formatting import _display_width

    table = build_compare_table([[("Legs", "3/4 🔴", "4/4"), ("DTE", "18", "18")]], ("V1", "V2"))
    lines = table.split("\n")
    header_width = _display_width(lines[0])
    for line in lines:
        assert _display_width(line) == header_width
