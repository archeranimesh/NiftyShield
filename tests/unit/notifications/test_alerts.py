"""Tests for notification alert builders.

The `only_fires_on_critical_state` test was dropped during the ROLL-16
refactor, as the gate logic ("CRITICAL" in proxy_delta_alert) is handled
by the pre-existing call-site logic in the respective scripts.
"""

from src.notifications.alerts import build_proxy_critical_alert


def test_critical_alert_escapes_signed_delta():
    """Both sign and decimal point of the formatted delta are backslash-escaped (finding 1)."""
    # Negative delta
    out_neg = build_proxy_critical_alert(-0.32, "CRITICAL (<0.40, day 3 of 3+)")
    assert "📐 Current: \\-0\\.32 🔴" in out_neg
    assert "-0.32" not in out_neg

    # Positive delta
    out_pos = build_proxy_critical_alert(0.05, "CRITICAL (<0.40, day 3 of 3+)")
    assert "📐 Current: \\+0\\.05 🔴" in out_pos


def test_critical_alert_no_action_line():
    """No fabricated 🤖 Action:/remediation-state line — no such signal exists upstream (finding 2)."""
    out = build_proxy_critical_alert(-0.32, "CRITICAL (<0.40, day 3 of 3+)")

    assert "Action" not in out
    assert "🤖" not in out

    # Assert exact 3-line shape
    lines = out.splitlines()
    assert len(lines) == 3
    assert lines[0] == "🚨 CRITICAL: PROXY DELTA"
    assert lines[1] == "📐 Current: \\-0\\.32 🔴"
    assert lines[2] == "📉 Rule Breach: CRITICAL \\(<0\\.40, day 3 of 3\\+\\)"


def test_critical_alert_rule_breach_is_verbatim():
    """proxy_delta_alert appears escaped but otherwise unmodified — not parsed/rebuilt (finding 3)."""
    out = build_proxy_critical_alert(-0.18, "CRITICAL (<0.40, day 5 of 3+)")

    assert "📉 Rule Breach: CRITICAL \\(<0\\.40, day 5 of 3\\+\\)" in out
    # Day count and threshold are not split into their own fields.
    assert out.count("📉 Rule Breach:") == 1
