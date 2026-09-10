"""Unit tests for position health check formatting."""

import pytest

from src.notifications.formatting import (
    PositionFinding,
    build_position_health_message,
)


def test_scenario_roll_overdue_only():
    findings = [
        PositionFinding(
            "roll_overdue",
            "paper_ic_nifty_v1_weekly",
            "short_call",
            "NSE_FO|48521",
            -50,
            expiry_str="2026-08-25",
            days_overdue=5,
            underlying_symbol="NIFTY",
            strike_price=23000,
            instrument_type="CE",
        ),
        PositionFinding(
            "roll_overdue",
            "paper_csp_nifty_v1",
            "short_put",
            "NSE_FO|48530",
            -25,
            expiry_str="2026-08-18",
            days_overdue=12,
            underlying_symbol="NIFTY",
            strike_price=22500,
            instrument_type="PE",
        ),
    ]
    msg = build_position_health_message(findings)
    # 12 days overdue first, 5 days overdue next
    expected = (
        "⚠️ NIFTYSHIELD: POSITION HEALTH\n"
        "\n"
        "❌ ROLLS OVERDUE \\(2\\):\n"
        "🚨 12d LATE: \\[CSP V1\\] Short 25x NIFTY 22500 PE \\(18 AUG 26\\)\n"
        "🚨 5d LATE: \\[IC V1 Weekly\\] Short 50x NIFTY 23000 CE \\(25 AUG 26\\)"
    )
    assert msg == expected


def test_scenario_unresolved_only():
    findings = [
        PositionFinding(
            "unresolved_instrument",
            "paper_covered_call_v1",
            "overlay_cc",
            "NSE_FO|99999",
            100,
        ),
    ]
    msg = build_position_health_message(findings)
    expected = (
        "⚠️ NIFTYSHIELD: POSITION HEALTH\n"
        "\n"
        "❓ UNMAPPED ASSET \\(1\\):\n"
        "⚠️ \\[Covered Call V1\\] Long 100x \\(Unknown Token: 99999\\)"
    )
    assert msg == expected


def test_scenario_mixed():
    findings = [
        PositionFinding(
            "roll_overdue",
            "paper_ic_nifty_v1_weekly",
            "short_call",
            "NSE_FO|48521",
            -50,
            expiry_str="2026-08-25",
            days_overdue=5,
            underlying_symbol="NIFTY",
            strike_price=23000,
            instrument_type="CE",
        ),
        PositionFinding(
            "roll_overdue",
            "paper_csp_nifty_v1",
            "short_put",
            "NSE_FO|48530",
            -25,
            expiry_str="2026-08-18",
            days_overdue=12,
            underlying_symbol="NIFTY",
            strike_price=22500,
            instrument_type="PE",
        ),
        PositionFinding(
            "unresolved_instrument",
            "paper_covered_call_v1",
            "overlay_cc",
            "NSE_FO|99999",
            100,
        ),
    ]
    msg = build_position_health_message(findings)
    expected = (
        "⚠️ NIFTYSHIELD: POSITION HEALTH\n"
        "\n"
        "❌ ROLLS OVERDUE \\(2\\):\n"
        "🚨 12d LATE: \\[CSP V1\\] Short 25x NIFTY 22500 PE \\(18 AUG 26\\)\n"
        "🚨 5d LATE: \\[IC V1 Weekly\\] Short 50x NIFTY 23000 CE \\(25 AUG 26\\)\n"
        "\n"
        "❓ UNMAPPED ASSET \\(1\\):\n"
        "⚠️ \\[Covered Call V1\\] Long 100x \\(Unknown Token: 99999\\)"
    )
    assert msg == expected


def test_scenario_single_finding():
    findings = [
        PositionFinding(
            "roll_overdue",
            "paper_protective_put_v1",
            "overlay_pp",
            "NSE_FO|48540",
            10,
            expiry_str="2026-08-11",
            days_overdue=1,
            underlying_symbol="NIFTY",
            strike_price=21500,
            instrument_type="PE",
        ),
    ]
    msg = build_position_health_message(findings)
    expected = (
        "⚠️ NIFTYSHIELD: POSITION HEALTH\n"
        "\n"
        "❌ ROLLS OVERDUE \\(1\\):\n"
        "🚨 1d LATE: \\[Protective Put V1\\] Long 10x NIFTY 21500 PE \\(11 AUG 26\\)"
    )
    assert msg == expected


def test_scenario_roll_overdue_futures():
    findings = [
        PositionFinding(
            "roll_overdue",
            "paper_nifty_futures",
            "base_futures",
            "NSE_FO|11111",
            75,
            expiry_str="2026-08-25",
            days_overdue=3,
            underlying_symbol="NIFTY",
            strike_price=0,
            instrument_type="FUT",
        ),
    ]
    msg = build_position_health_message(findings)
    expected = (
        "⚠️ NIFTYSHIELD: POSITION HEALTH\n"
        "\n"
        "❌ ROLLS OVERDUE \\(1\\):\n"
        "🚨 3d LATE: \\[Futures Track\\] Long 75x NIFTY FUT \\(25 AUG 26\\)"
    )
    assert msg == expected


def test_position_health_rolls_overdue_sorted_descending():
    """ascending-insertion fixture renders descending"""
    findings = [
        PositionFinding(
            "roll_overdue",
            "paper_csp_nifty_v1",
            "short_put",
            "NSE_FO|48530",
            -25,
            expiry_str="2026-08-18",
            days_overdue=5,
            underlying_symbol="NIFTY",
            strike_price=22500,
            instrument_type="PE",
        ),
        PositionFinding(
            "roll_overdue",
            "paper_ic_nifty_v1_weekly",
            "short_call",
            "NSE_FO|48521",
            -50,
            expiry_str="2026-08-25",
            days_overdue=12,
            underlying_symbol="NIFTY",
            strike_price=23000,
            instrument_type="CE",
        ),
    ]
    msg = build_position_health_message(findings)
    # The 12-day one must be ordered first
    assert "12d LATE" in msg.splitlines()[3]
    assert "5d LATE" in msg.splitlines()[4]


def test_position_health_futures_leg_no_strike_in_label():
    findings = [
        PositionFinding(
            "roll_overdue",
            "paper_nifty_futures",
            "base_futures",
            "NSE_FO|11111",
            75,
            expiry_str="2026-08-25",
            days_overdue=3,
            underlying_symbol="NIFTY",
            strike_price=0,
            instrument_type="FUT",
        ),
    ]
    msg = build_position_health_message(findings)
    assert "NIFTY FUT" in msg
    assert " 0 " not in msg


def test_position_health_unmapped_asset_omits_expiry_fields():
    findings = [
        PositionFinding(
            "unresolved_instrument",
            "paper_covered_call_v1",
            "overlay_cc",
            "NSE_FO|99999",
            100,
        ),
    ]
    msg = build_position_health_message(findings)
    assert "Unknown Token: 99999" in msg
    assert "LATE" not in msg
    assert "CE" not in msg


def test_position_health_unknown_token_parses_numeric_suffix():
    findings = [
        PositionFinding(
            "unresolved_instrument",
            "paper_covered_call_v1",
            "overlay_cc",
            "NSE_FO|99999",
            100,
        ),
        PositionFinding(
            "unresolved_instrument",
            "paper_covered_call_v1",
            "overlay_cc",
            "BARE_TOKEN",
            100,
        ),
    ]
    msg = build_position_health_message(findings)
    assert "Unknown Token: 99999" in msg
    assert "Unknown Token: BARE\\_TOKEN" in msg


def test_position_health_unmapped_strategy_raises():
    findings = [
        PositionFinding(
            "unresolved_instrument",
            "unknown_strategy_xyz",
            "overlay_cc",
            "NSE_FO|99999",
            100,
        ),
    ]
    with pytest.raises(ValueError):
        build_position_health_message(findings)


def test_position_health_roll_overdue_missing_resolved_fields_raises():
    # BUG-045: _resolved_label must reject a roll_overdue finding whose
    # resolved fields were never populated rather than pass None onward.
    findings = [
        PositionFinding(
            "roll_overdue",
            "paper_csp_nifty_v1",
            "short_put",
            "NSE_FO|48530",
            -25,
            days_overdue=3,
        ),
    ]
    with pytest.raises(ValueError, match="needs a resolved finding"):
        build_position_health_message(findings)


def test_position_health_roll_overdue_missing_strike_raises():
    # BUG-045: an option finding resolved except for strike_price must
    # raise rather than pass None into format_option_label.
    findings = [
        PositionFinding(
            "roll_overdue",
            "paper_csp_nifty_v1",
            "short_put",
            "NSE_FO|48530",
            -25,
            expiry_str="2026-08-18",
            days_overdue=3,
            underlying_symbol="NIFTY",
            instrument_type="PE",
        ),
    ]
    with pytest.raises(ValueError, match="no strike_price"):
        build_position_health_message(findings)
