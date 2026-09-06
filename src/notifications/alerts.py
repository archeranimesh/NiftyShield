"""Shared Telegram message builders."""

from __future__ import annotations

from src.notifications.formatting import format_greek
from src.notifications.markdown import escape_markdown


def build_proxy_critical_alert(net_delta: float, proxy_delta_alert: str | None) -> str:
    """Proxy Delta CRITICAL alert body, MarkdownV2-safe (ROLL-10).

    Confirmed format (2026-08-10 workshop, ref
    ``scratch/2026-08-10_proxy_delta_critical_alert_format.py``)::

        🚨 CRITICAL: PROXY DELTA
        📐 Current: <signed 2dp> 🔴
        📉 Rule Breach: <proxy_delta_alert, verbatim>

    ``proxy_delta_alert`` is rendered verbatim (escaped, never parsed).
    """
    delta_str = escape_markdown(format_greek(net_delta))
    alert_str = escape_markdown(proxy_delta_alert or "")
    return "\n".join(
        [
            "🚨 CRITICAL: PROXY DELTA",
            f"📐 Current: {delta_str} 🔴",
            f"📉 Rule Breach: {alert_str}",
        ]
    )
