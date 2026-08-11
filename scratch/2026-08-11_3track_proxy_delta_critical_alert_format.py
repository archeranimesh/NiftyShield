"""Scratch script — Proxy Delta CRITICAL alert Telegram message formatting (production dup).

Message #10 in docs/plan/telegram-markdown-migration/TODO.md's "Confirmed missing" queue —
`scripts/strategies/three_track/paper_3track_snapshot.py::_run`, ~line 1723 (confirmed via
`search_graph` + direct read of `_run`, not the TODO.md grep excerpt alone):

    if snapshot.proxy_delta_alert and "CRITICAL" in snapshot.proxy_delta_alert:
        msg = (
            f"\U0001f6a8 *CRITICAL* Proxy Delta alert — {track_name}\n"
            f"Delta: {snapshot.greeks.net_delta:.3f}\n"
            f"Date: {snap_date}"
        )
        if notifier:
            try:
                await notifier.send(msg)
            except Exception as exc:
                logger.warning("Telegram alert failed: %s", exc)

This is the **known duplicate** flagged (not fixed) in ROLL-10's spec
(`strategy-rollout/stories.md`) and in TODO.md queue item 10: a near-identical "Proxy Delta
CRITICAL" alert to the one ROLL-10 covers (`scripts/dev/paper_track_snapshot.py::main`), reading
the same `TrackSnapshot.proxy_delta_alert` field and the same `"CRITICAL" in ...` check — but
this one lives in the real production EOD cron path (`_run`, the async orchestration entry point
for `paper_3track_snapshot.py`), not the lower-stakes dev/manual script ROLL-10 scoped to. Not
named in `backbone/`'s MD-4 file list or any other `ROLL-*` task before this session.

Unlike ROLL-10's call site, this one already interpolates `track_name` and `snap_date` instead of
`proxy_delta_alert`/a signed-2dp-Greek pairing — and uses legacy-Markdown `*bold*` with no
`parse_mode` set (same already-broken state as ROLL-10's call site: literal asterisks render
today, not a regression introduced by this migration).

**Format decision (confirmed with Animesh, 2026-08-11): reuse ROLL-10's confirmed 3-line shape
verbatim** — not a 4th track/date line. Rationale: this alert only ever fires for STRATEGY_PROXY
in practice (mirrors ROLL-10's own scope note), and keeping both call sites byte-identical sets
up sharing one real message-builder function at implementation time instead of two near-duplicate
ones. `track_name`/`snap_date` are therefore NOT rendered in the confirmed message, same as
ROLL-10 — kept in SCENARIOS below for data-shape fidelity only (this call site's loop can in
principle pass any track_name, though the CRITICAL branch in practice only ever triggers for
STRATEGY_PROXY, same guarantee ROLL-10's site relies on).

**backbone/ (MD-1..MD-5) status as of this session: NOT shipped** — confirmed via
`search_graph("mdcode")` / `search_graph("escape_markdown")`, both returning only scratch/-file
hits, none under `src/`. This script inlines its own copies, matching MD-1's exact spec in
`docs/plan/telegram-markdown-migration/backbone/stories.md` — same inline copies ROLL-10's
reference script (`scratch/2026-08-10_proxy_delta_critical_alert_format.py`) uses, ported
verbatim since the message is identical.

**Confirmed format (2026-08-11, Animesh — reuse of ROLL-10's 2026-08-10 on-device-confirmed
shape, no new elimination trail needed since no new design happened this session):**

    \U0001f6a8 CRITICAL: PROXY DELTA
    \U0001f4d0 Current: \\-0\\.32 \U0001f534
    \U0001f4c9 Rule Breach: CRITICAL \\(<0\\.40, day 3 of 3\\+\\)

Run from repo root with the project's normal venv active:
    python -m scratch.2026-08-11_3track_proxy_delta_critical_alert_format <scenario> [--send]
    python -m scratch.2026-08-11_3track_proxy_delta_critical_alert_format --list-scenarios
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

import aiohttp

# Allow running as a plain script (python scratch/foo.py) as well as -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402

# ── Inline copies of MD-1's helpers (backbone/ not shipped yet — see module docstring) ──
# Ported verbatim from scratch/2026-08-10_proxy_delta_critical_alert_format.py — same message,
# same helpers, do not re-derive.

MARKDOWNV2_RESERVED = "_*[]()~`>#+-=|{}.!"


def escape_markdown(text: str) -> str:
    """Backslash-escape MarkdownV2 reserved characters in free text.

    Mirrors docs/plan/telegram-markdown-migration/backbone/stories.md MD-1 spec exactly —
    inline copy pending the real src/notifications/markdown.py landing.
    """
    out = []
    for ch in text:
        if ch in MARKDOWNV2_RESERVED:
            out.append("\\")
        out.append(ch)
    return "".join(out)


def _fmt_greek(value: Decimal) -> str:
    """Local 2dp-signed formatter — mirrors formatting-rules/ FMT-1's Greeks row
    (2dp, always signed). Inline copy since formatting-rules/ hasn't shipped yet either
    (no format_greek() to import). Note: the real _run call site currently formats net_delta
    at 3dp (":.3f") — the confirmed message uses FMT-1's 2dp rule instead, same as ROLL-10;
    real implementation should drop the 3dp formatting at the call site, not preserve it.
    """
    return f"{value:+.2f}"


# ── Sample data — real (track_name, proxy_delta_alert, net_delta, snap_date) shapes as produced
# by generate_track_snapshot()/ProxyDeltaMonitor.update_and_check() inside _run's per-track loop.
# track_name/snap_date are NOT read by build_message() (see module docstring "Format decision")
# but kept here for data-shape fidelity in case a future revision reintroduces a labeled line. ──

SCENARIOS: dict[str, dict] = {
    "critical_day3": {
        "track_name": "paper_nifty_proxy",
        "snap_date": "2026-08-11",
        "proxy_delta_alert": "CRITICAL (<0.40, day 3 of 3+)",
        "net_delta": Decimal("-0.32"),
    },
    "critical_day5": {
        "track_name": "paper_nifty_proxy",
        "snap_date": "2026-08-11",
        "proxy_delta_alert": "CRITICAL (<0.40, day 5 of 3+)",
        "net_delta": Decimal("-0.18"),
    },
    "critical_positive_delta": {
        # Net delta across all 4 legs can still print positive even while the base DITM call's
        # own delta triggered CRITICAL — the alert is per-base-leg, not per-net-position.
        "track_name": "paper_nifty_proxy",
        "snap_date": "2026-08-11",
        "proxy_delta_alert": "CRITICAL (<0.40, day 3 of 3+)",
        "net_delta": Decimal("0.05"),
    },
}


def build_message(d: dict) -> str:
    """Proxy Delta CRITICAL alert, MarkdownV2-safe — production `_run` call site.

    Shape is ROLL-10's confirmed 3-line format, reused VERBATIM (CONFIRMED 2026-08-11,
    Animesh — see module docstring "Format decision"):
        \U0001f6a8 CRITICAL: PROXY DELTA
        \U0001f4d0 Current: <signed 2dp> \U0001f534
        \U0001f4c9 Rule Breach: <proxy_delta_alert, verbatim>

    No track/date line — this alert only ever fires for STRATEGY_PROXY in practice (same
    guarantee ROLL-10's dev-script call site relies on), so `d["track_name"]`/`d["snap_date"]`
    are intentionally unused here. See ROLL-10's spec (`strategy-rollout/stories.md`) for the
    full elimination trail (escaping bug, dropped Action: line, verbatim Rule Breach: rationale)
    — not repeated here since no new design decision happened this session, only reuse.
    """
    delta_str = escape_markdown(_fmt_greek(d["net_delta"]))
    alert_str = escape_markdown(d["proxy_delta_alert"])

    return "\n".join(
        [
            "🚨 CRITICAL: PROXY DELTA",
            f"📐 Current: {delta_str} 🔴",
            f"📉 Rule Breach: {alert_str}",
        ]
    )


async def send_markdown_v2(bot_token: str, chat_id: str, message: str) -> bool:
    """Send with parse_mode=MarkdownV2 — per epic decision, not legacy Markdown/HTML."""
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "MarkdownV2"}
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, json=payload) as resp:
                # Don't raise_for_status() before reading the body — Telegram puts the
                # actual parse-error reason in the JSON "description" field even on a 400.
                resp_data = await resp.json()
                if not resp_data.get("ok"):
                    print(f"!! Telegram API error ({resp.status}): {resp_data.get('description')}")
                return bool(resp_data.get("ok"))
    except Exception as exc:  # Intentional: isolate all API failures, scratch probe only
        print(f"!! send failed: {exc}")
        return False


async def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "critical_day3"
    if scenario == "--list-scenarios":
        print("\n".join(SCENARIOS.keys()))
        return
    if scenario not in SCENARIOS:
        print(f"!! unknown scenario {scenario!r}; use one of: {', '.join(SCENARIOS)}")
        return

    text = build_message(SCENARIOS[scenario])
    print(f"--- scenario: {scenario} ---")
    print(text)
    print("---")

    if "--send" not in sys.argv:
        print("(print-only; pass --send to actually post to Telegram)")
        return

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print(
            "\n!! TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in environment — "
            "cannot send. Aborting without sending anything."
        )
        return

    ok = await send_markdown_v2(settings.telegram_bot_token, settings.telegram_chat_id, text)
    print(f"\nsend_markdown_v2() returned {ok}")
    if not ok:
        print("!! send failed — check logs / credentials before retrying")


if __name__ == "__main__":
    asyncio.run(main())
