"""Scratch script — Generic strategy WARN event alert Telegram message formatting.

Message #2 in docs/plan/telegram-markdown-migration/TODO.md's "Confirmed missing" queue —
`StrategyMonitor._route_event`'s WARN branch (src/strategy/monitor.py:366-367):

    text = f"[{strategy.strategy_name}] {event.event_type}: {event.description}"
    await self._notifier.send_plain_message(text)

One f-string line, generic across every monitored strategy/event type (not just IC/CSP —
this is the shared WARN dispatch path every `PaperStrategy.check_signals()` implementation
routes through, already deduped OFF->ON by `warn_signal_state`/`is_warn_active` before this
text is even built — see `_route_event`'s full docstring). Distinct from
`send_approval_request` (ROLL-4, same file, ACTION-severity path) and from the 7 strategies'
own `_send_close_notification` methods (ROLL-3) — this is the one generic line every
`SignalEvent` with severity="WARN" produces, regardless of which strategy or signal fired.

**backbone/ (MD-1..MD-5) status as of this session: NOT shipped** — confirmed via
`search_graph("mdcode")` / `search_graph("escape_markdown")` both returning zero results.
This script inlines its own copies, matching MD-1's exact spec in
`docs/plan/telegram-markdown-migration/backbone/stories.md`.

Format (Animesh-confirmed, 2026-08-08, `message-format-workshop.md` session — "kv-line,
ROLL-7 style" option): reuses ROLL-7's kv-line convention (bold strategy label headline,
`mdcode()`-wrapped identifier, escaped free-text body) rather than inventing a new shape for
this message specifically — same rationale ROLL-7 itself gives for preferring a shared
epic-wide pattern over a bespoke one-off:

    ⚠️ *<strategy label>*
    Event: `<event_type>`
    <description, escaped>

`STRATEGY_LABELS` below is the SAME fuller-form 12-id -> human-label table ROLL-7's reference
script (`scratch/2026-08-08_reentry_notice_format.py`) defines — duplicated here rather than
imported, since neither script is real `src/` code yet (both are pre-`ROLL-*` scratch
references). ROLL-7's own docstring already flags this as a real "revisit once one of these
ships" duplication point, not a NEW one introduced by this script — see that script's module
docstring point 1. `event_type` is an identifier-like value (`DELTA_BREACH`, `TIME_STOP`,
`ROLL_ELIGIBLE`, ...) so it's `mdcode()`-wrapped, not `escape_markdown()`'d as prose — matches
how ROLL-1 treats `strategy_id` and ROLL-7 treats `script_hint`. `description` is genuinely
free-form prose (`event.description`, built by whichever `ExitSignalEngine`/strategy method
emitted the `SignalEvent`) and may contain punctuation MarkdownV2 reserves (parentheses,
periods, `=`, `-`) — `escape_markdown()`'d, not `mdcode()`'d, since it's not an identifier.

An unmapped `strategy_name` raises loudly (`ValueError`), same discipline ROLL-6/ROLL-7 both
require for their own label lookups — a new strategy needs an explicit label added here (and
eventually in the real `STRATEGY_LABELS`/`formatting.py`) before it can WARN through this path.

Not part of src/notifications/ — purely for iterating on layout before wiring into the real
`_route_event`. Read-only w.r.t. the DB — makes zero DB calls. Sends a real Telegram message
(counts against the configured message budget).

Run from repo root with the project's normal venv active:
    python -m scratch.2026-08-08_strategy_event_alert_format <scenario> [--send]
    python -m scratch.2026-08-08_strategy_event_alert_format --list-scenarios
"""

from __future__ import annotations

import asyncio
import sys
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


def mdcode(value: str) -> str:
    """Wrap a dynamic identifier-like value as an inline code span.

    Mirrors MD-1's spec: falls back to escape_markdown() if value itself contains a
    backtick, rather than emitting a broken/nested code span.
    """
    if "`" in value:
        return escape_markdown(value)
    return f"`{value}`"


# ── Display-label table — SAME fuller-form set as ROLL-7's reference script
# (scratch/2026-08-08_reentry_notice_format.py::STRATEGY_LABELS). Duplicated, not imported —
# neither script is real src/ code yet. See module docstring for the "revisit once one ships"
# flag this duplication carries (already raised by ROLL-7, not new here). ──

STRATEGY_LABELS: dict[str, str] = {
    "paper_nifty_futures": "Futures Track",
    "paper_nifty_proxy": "Proxy Track",
    "paper_nifty_spot": "Spot Track",
    "paper_ic_nifty_v1_weekly": "IC V1 Weekly",
    "paper_ic_nifty_v1_monthly": "IC V1 Monthly",
    "paper_ic_nifty_v1_leaps": "IC V1 Leaps",
    "paper_ic_nifty_v1_yearly": "IC V1 Yearly",
    "paper_ic_nifty_v2_monthly": "IC V2 Monthly",
    "paper_collar_v1": "Collar V1",
    "paper_covered_call_v1": "Covered Call V1",
    "paper_protective_put_v1": "Protective Put V1",
    "paper_csp_nifty_v1": "CSP V1",
}


def _label_strategy(strategy_name: str) -> str:
    """Explicit-mapping lookup; unmapped id raises loudly rather than silently falling back
    to the raw id — same discipline ROLL-6/ROLL-7 both require for their own label tables."""
    try:
        return STRATEGY_LABELS[strategy_name]
    except KeyError:
        raise ValueError(f"no display label mapped for strategy_name={strategy_name!r}") from None


# ── Sample data — real (event_type, description) shapes as emitted by SignalEvent producers
# (ExitSignalEngine / ReEntryMixin-adjacent strategies) reaching _route_event's WARN branch. ──

SCENARIOS: dict[str, dict] = {
    "delta_warn": {
        "strategy_name": "paper_ic_nifty_v1_monthly",
        "event_type": "DELTA_BREACH",
        "description": "short put delta -0.42 exceeds threshold -0.40 (review roll candidates).",
    },
    "proxy_delta_warn": {
        "strategy_name": "paper_nifty_proxy",
        "event_type": "PROXY_DELTA_WARN",
        "description": "base_ditm_call delta 0.61 < 0.65 warn band (not yet critical).",
    },
    "roll_base_first_warn": {
        "strategy_name": "paper_covered_call_v1",
        "event_type": "ROLL_BASE_FIRST",
        "description": "base_dte=8 <= 10 — roll the base leg before the overlay_cc leg.",
    },
    "underscore_regression": {
        "strategy_name": "paper_csp_nifty_v1",
        "event_type": "DELTA_WARN",
        "description": "signal_code=DELTA_WARN (the exact bug that started this epic).",
    },
}


def build_message(d: dict) -> str:
    """kv-line port of _route_event's WARN branch text, MarkdownV2-safe.

    Shape (Animesh-confirmed, "kv-line, ROLL-7 style"):
        ⚠️ *<strategy label>*
        Event: `<event_type>`
        <description, escaped>

    strategy_name -> looked up via STRATEGY_LABELS, then escape_markdown()'d (labels are
    curated plain text, escaped anyway on principle, same as ROLL-7). event_type ->
    mdcode() (identifier/signal code, kept copyable — matches ROLL-1's strategy_id and
    ROLL-7's script_hint treatment). description -> escape_markdown() (free-form prose from
    whichever strategy/engine emitted the SignalEvent, may contain '.'/'('/')'/'-'/'=').
    """
    strategy_label = escape_markdown(_label_strategy(d["strategy_name"]))
    event_code = mdcode(d["event_type"])
    description = escape_markdown(d["description"])

    lines = [
        f"⚠️ *{strategy_label}*",
        f"Event: {event_code}",
        description,
    ]
    return "\n".join(lines)


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
    scenario = sys.argv[1] if len(sys.argv) > 1 else "delta_warn"
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
