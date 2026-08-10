"""Scratch script — Proxy Delta CRITICAL alert Telegram message formatting.

Message #4 in docs/plan/telegram-markdown-migration/TODO.md's "Confirmed missing" queue —
`scripts/dev/paper_track_snapshot.py::main`, lines 185-190 (confirmed via `search_graph` +
direct read, not the TODO.md grep excerpt alone):

    if track_name == STRATEGY_PROXY and snapshot.proxy_delta_alert:
        print(f"  ALERT  : Proxy Delta State -> {snapshot.proxy_delta_alert}")
        if "CRITICAL" in snapshot.proxy_delta_alert:
            await notifier.send(
                f"🚨 **CRITICAL**: Proxy Delta Monitor triggered: {snapshot.proxy_delta_alert}"
                f"\nDelta: {snapshot.greeks.net_delta:.2f}"
            )

Only the CRITICAL branch ever calls `notifier.send()` — the print() lines (ALERT/WARNING/OK
states) are console-only and out of scope for this Telegram-message workshop. Note this script
already used `**bold**` (legacy-Markdown-style asterisks) with no `parse_mode` at all set on
`notifier.send()` at the call site shown here — i.e. this message was *already* broken/silently
rendering literal asterisks before this epic's MarkdownV2 migration ever starts; not a new bug
introduced by this task, just confirming the current state is not something to preserve.

**`proxy_delta_alert`'s real value at CRITICAL, confirmed via `src/paper/track_snapshot.py`
(generate_track_snapshot, ~line 349):**

    proxy_alert = f"CRITICAL (<0.40, day {consecutive} of 3+)"

Contains `(`, `<`, `.`, `+`, `)` — several MarkdownV2-reserved characters in a single dynamic
string, a good exercise for `escape_markdown()`.

**Known duplicate — flagged, not fixed in this task.** `scripts/strategies/three_track/
paper_3track_snapshot.py::_run` (~line 1639) sends a near-identical "Proxy Delta CRITICAL"
Telegram alert independently:

    msg = (
        f"🚨 *CRITICAL* Proxy Delta alert — {track_name}\n"
        f"Delta: {snapshot.greeks.net_delta:.3f}\n"
        f"Date: {snap_date}"
    )

That is the *production* cron path (`paper_3track_snapshot.py` is the real EOD script;
`scripts/dev/paper_track_snapshot.py` is a lower-stakes dev/manual-run script per TODO.md's own
note). Both read the same `TrackSnapshot.proxy_delta_alert` field and fire on the same
"CRITICAL" substring check. This task's scope is the TODO.md-named dev script only, per the
missing-message-workshop-prompt's "do not batch multiple items" rule — but the duplication is
worth surfacing explicitly: `paper_3track_snapshot.py`'s version is NOT itself named anywhere in
this epic's backbone/MD-4 file list or any ROLL task, and is arguably higher-priority than this
dev script precisely because it's the one that actually fires in production. Flagging for a
follow-up TODO.md queue entry, not fixing here (would violate "do not skip ahead"/"do not batch"
this session).

**backbone/ (MD-1..MD-5) status as of this session: NOT shipped** — confirmed via
`search_graph("mdcode")` / `search_graph("escape_markdown")` both returning zero results. This
script inlines its own copies, matching MD-1's exact spec in
`docs/plan/telegram-markdown-migration/backbone/stories.md`.

**Confirmed format (2026-08-10, Animesh, after one on-device round-trip via `--send`):**

    🚨 CRITICAL: PROXY DELTA
    📐 Current: \-0\.32 🔴
    📉 Rule Breach: CRITICAL \(<0\.40, day 3 of 3\+\)

**Elimination trail:**
1. Initial draft (`🚨 PROXY DELTA CRITICAL — Proxy Track` / `Delta: -0.32` / raw alert string)
   — sent live, Telegram 400'd: `Character '-' is reserved and must be escaped`. Root cause:
   `Delta:` line's `_fmt_greek()` output ("-0.32") was interpolated raw, only the headline's
   literal `-` had been escaped. Fixed by running `escape_markdown()` over the whole formatted
   delta string (covers the sign AND the decimal point, both reserved) — same discipline every
   other numeric field in this epic already follows.
2. Animesh counter-proposed a 4-line emoji-labeled shape (`📐 Current:` / `📉 Rule Breach:` /
   `🤖 Action: REQUIRED / PENDING / AUTO-HEDGING`) after the escaping fix. The `🤖 Action:` line
   was dropped — no action/remediation-state field exists anywhere upstream of this alert
   (`ProxyDeltaMonitor`/`TrackSnapshot` compute no such value); rendering one would fabricate
   data, same anti-pattern `FMT-1b`/`ROLL-8` already rejected for their own severity/action
   fields. Confirmed: plan for a real action signal only once one is actually wired up, not in
   this workshop session.
3. `📉 Rule Breach:` renders `proxy_delta_alert` VERBATIM rather than splitting the threshold
   (0.40) and day-count (3) into their own labeled sub-fields — those aren't passed to this call
   site as separate values today, only pre-baked into the one string
   (`src/paper/track_snapshot.py::generate_track_snapshot`, ~line 349). Splitting it now would
   repeat the exact brittle string-parsing pattern `ROLL-7` rejected for `_check_reentry`'s
   `blocked_reason`. Confirmed with Animesh: plan the `TrackSnapshot`/`generate_track_snapshot`
   data-plumbing (expose `consecutive_days` as its own field, currently discarded after being
   folded into the string) at real-implementation time, not in this formatting-only session.
4. The original strategy-label headline (`— Proxy Track`) and `STRATEGY_LABELS` lookup were
   dropped — this alert only ever fires for `STRATEGY_PROXY`, and the confirmed shape has no
   line that needs a display-name lookup at all.

Run from repo root with the project's normal venv active:
    python -m scratch.2026-08-10_proxy_delta_critical_alert_format <scenario> [--send]
    python -m scratch.2026-08-10_proxy_delta_critical_alert_format --list-scenarios
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
    (no format_greek() to import)."""
    return f"{value:+.2f}"


# NOTE: an earlier draft carried a STRATEGY_LABELS/_label_strategy lookup for a headline
# "— Proxy Track" suffix (ROLL-7/ROLL-8-style). Dropped per the confirmed format (see module
# docstring, Elimination trail #4) — this alert only ever fires for STRATEGY_PROXY
# ("paper_nifty_proxy"), and the confirmed 3-line shape has no line needing a display-name
# lookup at all. `track_name` is kept in SCENARIOS below for data-shape fidelity even though
# build_message() no longer reads it, in case a future revision reintroduces a labeled line.

# ── Sample data — real (track_name, proxy_delta_alert, net_delta) shapes as produced by
# generate_track_snapshot()/ProxyDeltaMonitor.update_and_check(). Only the CRITICAL state ever
# reaches notifier.send() (see module docstring) — WARNING/OK scenarios included anyway so the
# escaping helper gets exercised against every real proxy_delta_alert string shape, even though
# only "critical_day3"/"critical_day5" are the actually-sent scenarios. ──

SCENARIOS: dict[str, dict] = {
    "critical_day3": {
        "track_name": "paper_nifty_proxy",
        "proxy_delta_alert": "CRITICAL (<0.40, day 3 of 3+)",
        "net_delta": Decimal("-0.32"),
    },
    "critical_day5": {
        "track_name": "paper_nifty_proxy",
        "proxy_delta_alert": "CRITICAL (<0.40, day 5 of 3+)",
        "net_delta": Decimal("-0.18"),
    },
    "critical_positive_delta": {
        # Net delta across all 4 legs can still print positive even while the base DITM call's
        # own delta triggered CRITICAL — the alert is per-base-leg, not per-net-position.
        "track_name": "paper_nifty_proxy",
        "proxy_delta_alert": "CRITICAL (<0.40, day 3 of 3+)",
        "net_delta": Decimal("0.05"),
    },
}


def build_message(d: dict) -> str:
    """Proxy Delta CRITICAL alert, MarkdownV2-safe.

    Shape (CONFIRMED 2026-08-10, Animesh, after one on-device round-trip that
    caught the unescaped '-' bug — see module docstring "Elimination trail"):
        🚨 CRITICAL: PROXY DELTA
        📐 Current: <signed 2dp> 🔴
        📉 Rule Breach: <proxy_delta_alert, verbatim>

    An `🤖 Action:` line was proposed and explicitly dropped this session — no
    action/remediation-state field exists anywhere upstream of this alert
    (ProxyDeltaMonitor/TrackSnapshot compute no such value), so rendering one
    would fabricate data, the same anti-pattern FMT-1b/ROLL-8 already rejected
    for their own severity/action fields. Revisit only once a real auto-hedge
    or action-required signal is actually wired to this path.

    `Rule Breach:` deliberately renders `proxy_delta_alert` VERBATIM, not split
    into separate threshold/day-count fields — the threshold (0.40) and
    consecutive-day count are not passed to this call site as their own
    values, only pre-baked into this one string
    (`src/paper/track_snapshot.py`'s `generate_track_snapshot`, ~line 349).
    Parsing them back out would repeat the exact brittle string-split pattern
    ROLL-7 rejected for `_check_reentry`'s `blocked_reason`. Getting real
    separate fields needs `TrackSnapshot`/`generate_track_snapshot` to also
    expose `consecutive_days` (currently computed by
    `ProxyDeltaMonitor.update_and_check` then discarded after folding into the
    string) — deferred to the real ROLL-10 implementation, not done here
    (confirmed with Animesh: plan for the data-plumbing at implementation
    time, not in this formatting-only workshop session).

    The strategy-label headline line from the original draft was also dropped
    in favor of Animesh's counter-proposal shape above — kept only in the
    Elimination trail below for the record.
    """
    # _fmt_greek's output ("-0.32", "+0.05") contains a sign character AND a
    # decimal point — both MarkdownV2-reserved. Escaping only the sign (the
    # first bug found live on-device, 2026-08-10: Telegram 400'd on the
    # unescaped '-') was not sufficient on its own; escape_markdown() the
    # whole formatted string so the '.' is covered too, same discipline every
    # other numeric field in this epic already follows (see ROLL-1's
    # Expiry/Credit/Mark lines).
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
