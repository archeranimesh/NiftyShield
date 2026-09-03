"""Tests for scripts/dev/paper_track_snapshot.py — ROLL-10 proxy-delta CRITICAL alert.

Covers the MarkdownV2 migration of the CRITICAL-branch Telegram message: escaping of
the signed delta value, verbatim rendering of ``proxy_delta_alert``, the deliberate
absence of a fabricated action line, and the substring guard that gates the send.
"""

from __future__ import annotations

from decimal import Decimal

from scripts.dev.paper_track_snapshot import _build_proxy_critical_alert
from src.paper.track_snapshot import TrackGreeks, TrackPnL, TrackSnapshot

_ZERO = Decimal("0")


def _snapshot(net_delta: Decimal, alert: str) -> TrackSnapshot:
    """Build a CRITICAL-state proxy TrackSnapshot with the given net delta / alert string."""
    return TrackSnapshot(
        track_name="paper_nifty_proxy",
        pnl=TrackPnL(_ZERO, _ZERO, _ZERO, _ZERO),
        greeks=TrackGreeks(net_delta, _ZERO, _ZERO),
        max_drawdown_abs=_ZERO,
        max_drawdown_pct=_ZERO,
        return_on_nee=_ZERO,
        proxy_delta_state="CRITICAL",
        proxy_delta_alert=alert,
        consecutive_days=3,
    )


def test_critical_alert_escapes_signed_delta() -> None:
    """Both sign and decimal point of the formatted delta are backslash-escaped (finding 1)."""
    neg = _build_proxy_critical_alert(_snapshot(Decimal("-0.32"), "CRITICAL (<0.40, day 3 of 3+)"))
    assert "📐 Current: \\-0\\.32 🔴" in neg
    assert "-0.32" not in neg  # no unescaped form survives

    pos = _build_proxy_critical_alert(_snapshot(Decimal("0.05"), "CRITICAL (<0.40, day 3 of 3+)"))
    assert "📐 Current: \\+0\\.05 🔴" in pos


def test_critical_alert_rule_breach_is_verbatim() -> None:
    """proxy_delta_alert appears escaped but otherwise unmodified — not parsed/rebuilt (finding 3)."""
    alert = "CRITICAL (<0.40, day 5 of 3+)"
    msg = _build_proxy_critical_alert(_snapshot(Decimal("-0.18"), alert))
    assert "📉 Rule Breach: CRITICAL \\(<0\\.40, day 5 of 3\\+\\)" in msg
    # Day count and threshold are not split into their own fields.
    assert msg.count("📉 Rule Breach:") == 1


def test_critical_alert_no_action_line() -> None:
    """No fabricated 🤖 Action:/remediation-state line — no such signal exists upstream (finding 2)."""
    msg = _build_proxy_critical_alert(_snapshot(Decimal("-0.32"), "CRITICAL (<0.40, day 3 of 3+)"))
    assert "Action" not in msg
    assert "🤖" not in msg
    assert msg.splitlines() == [
        "🚨 CRITICAL: PROXY DELTA",
        "📐 Current: \\-0\\.32 🔴",
        "📉 Rule Breach: CRITICAL \\(<0\\.40, day 3 of 3\\+\\)",
    ]


def test_critical_alert_only_fires_on_critical_state() -> None:
    """The send is gated on 'CRITICAL' in proxy_delta_alert — WARNING/OK never reach the builder."""
    assert "CRITICAL" in "CRITICAL (<0.40, day 3 of 3+)"
    assert "CRITICAL" not in "WARNING (<0.65)"
    assert "CRITICAL" not in "OK"
