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

Format — **REVISED v2, 2026-08-08 (same session, cause->effect compact counter-proposal from
Animesh, superseding the v1 kv-line draft below).** v1 shape (superseded, kept here for the
elimination trail):

    ⚠️ *<strategy label>*
    Event: `<event_type>`
    <description, escaped>

v2 (THIS VERSION) folds the event identifier into the headline and adds a `Leg:` line, while
deliberately NOT decomposing `description` into separate Metric/Limit/Action fields the way
Animesh's first pasted mockup did — that mockup's per-field breakdown isn't representable from
what `_route_event`'s WARN branch actually has in scope (`strategy_name`, `event_type`,
`event.description` as one pre-built prose string; no separate numeric delta/threshold/action
fields anywhere upstream). Getting real Metric/Action fields would require every
`check_signals()` emitter to start passing structured payload fields instead of prose — out of
scope for this task, and splitting the existing string by parsing it would be the same
brittle move ROLL-7 already rejected for `_check_reentry`'s `blocked_reason`. Two things ARE
free and genuinely used here (not invented):

    ⚠️ DELTA BREACH — <strategy label>
    Leg: <leg role label>
    <description, escaped>

1. **`event_type` humanized via mechanical `.replace("_", " ")` only** — `DELTA_BREACH` ->
   `DELTA BREACH`. This is a plain reformat of the real identifier, not a new vocabulary — the
   first mockup's `ROLL_BASE_FIRST` -> "SEQUENCE LOCK" would have been an invented rename, not a
   reformat; rejected for that reason, not used here.
2. **`Leg:` line from `event.payload.get("leg_role", "")`** — this field is already read by
   `_route_event` itself (used in the WARN dedup key), so it's real, in-scope, no refactor
   needed. Omitted entirely when absent/empty (some event types carry no leg_role) rather than
   printing a blank line — same "optional line" rule this task's story spec already states.

**Severity emoji is fixed `⚠️`, deliberately not tiered per event_type (e.g. not `🚨` for
"breach" vs `⚠️` for "warn").** Confirmed during this session: `_route_event`'s WARN branch is
the ONLY severity that ever reaches this text-building code at all — ACTION-severity events
either auto-execute or become a `send_approval_request` call (`ROLL-4`'s territory), never this
line; INFO just logs. So every message through this code path IS a WARN by construction — a
tiered emoji here would misrepresent severity, not just be an unimplemented nice-to-have. A
single `⚠️` is the accurate signal, not a compromise. (This also reuses FMT-1b's already-settled
objection to selecting emoji by matching against the event_type/signal-code string — same
anti-pattern, just applied to a `🚨`-vs-`⚠️` choice instead of `alert_emoji`'s presence check.)

`STRATEGY_LABELS` below is the SAME fuller-form 12-id -> human-label table ROLL-7's reference
script (`scratch/2026-08-08_reentry_notice_format.py`) defines — kept as the fuller form here
too (Animesh confirmed 2026-08-08: NOT switching to ROLL-6's abbreviated table-column form
("IC V1 Mth") for this standalone headline, despite an earlier draft using that shorter form —
the fuller "IC V1 Monthly" reads better outside a table). Duplicated here rather than imported,
since neither script is real `src/` code yet (both are pre-`ROLL-*` scratch references). ROLL-7's
own docstring already flags this as a real "revisit once one of these ships" duplication point,
not a NEW one introduced by this script. `event.description` is genuinely free-form prose (built
by whichever `ExitSignalEngine`/strategy method emitted the `SignalEvent`) and may contain
punctuation MarkdownV2 reserves (parentheses, periods, `=`, `-`) — `escape_markdown()`'d, kept as
a single line, not decomposed.

An unmapped `strategy_name` raises loudly (`ValueError`), same discipline ROLL-6/ROLL-7 both
require for their own label lookups — a new strategy needs an explicit label added here (and
eventually in the real `STRATEGY_LABELS`/`formatting.py`) before it can WARN through this path.
`LEG_ROLE_LABELS` mirrors ROLL-7's own dict (explicit mapping, not `.title()` — same CC/PP
acronym-casing reasoning) — duplicated here for the same not-yet-real-code reason.

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


# leg_role values actually used across strategies emitting WARN-severity SignalEvents
# (CSP/CC/PP/Collar's own leg roles, plus the 3-track base roles) — same dict shape as
# ROLL-7's LEG_ROLE_LABELS, duplicated here for the same not-yet-real-code reason.
LEG_ROLE_LABELS: dict[str, str] = {
    "short_put": "Short Put",
    "short_call": "Short Call",
    "overlay_cc": "Overlay CC",
    "overlay_pp": "Overlay PP",
    "overlay_collar_call": "Overlay Collar Call",
    "overlay_collar_put": "Overlay Collar Put",
    "base_ditm_call": "Base DITM Call",
    "base_futures": "Base Futures",
}


def _label_strategy(strategy_name: str) -> str:
    """Explicit-mapping lookup; unmapped id raises loudly rather than silently falling back
    to the raw id — same discipline ROLL-6/ROLL-7 both require for their own label tables."""
    try:
        return STRATEGY_LABELS[strategy_name]
    except KeyError:
        raise ValueError(f"no display label mapped for strategy_name={strategy_name!r}") from None


def _label_leg(leg_role: str) -> str:
    """Same explicit-mapping discipline as _label_strategy. Callers must skip this entirely
    (no Leg: line) when leg_role is absent/empty — see build_message()'s guard — rather than
    calling this with an empty string and getting a spurious raise."""
    try:
        return LEG_ROLE_LABELS[leg_role]
    except KeyError:
        raise ValueError(f"no display label mapped for leg_role={leg_role!r}") from None


# ── Sample data — real (event_type, leg_role, description) shapes as emitted by SignalEvent
# producers (ExitSignalEngine / strategy check_signals()) reaching _route_event's WARN branch.
# leg_role empty string models the real event.payload.get("leg_role", "") default — some event
# types carry no leg_role. ──

SCENARIOS: dict[str, dict] = {
    "delta_breach": {
        "strategy_name": "paper_ic_nifty_v1_monthly",
        "event_type": "DELTA_BREACH",
        "leg_role": "short_put",
        "description": "short put delta -0.42 exceeds threshold -0.40 (review roll candidates).",
    },
    "proxy_delta_warn": {
        "strategy_name": "paper_nifty_proxy",
        "event_type": "PROXY_DELTA_WARN",
        "leg_role": "base_ditm_call",
        "description": "base_ditm_call delta 0.61 < 0.65 warn band (not yet critical).",
    },
    "roll_base_first_warn": {
        "strategy_name": "paper_covered_call_v1",
        "event_type": "ROLL_BASE_FIRST",
        "leg_role": "overlay_cc",
        "description": "base_dte=8 <= 10 — roll the base leg before the overlay_cc leg.",
    },
    "underscore_regression": {
        "strategy_name": "paper_csp_nifty_v1",
        "event_type": "DELTA_WARN",
        "leg_role": "short_put",
        "description": "signal_code=DELTA_WARN (the exact bug that started this epic).",
    },
    "no_leg_role": {
        "strategy_name": "paper_nifty_spot",
        "event_type": "TRACKING_ERROR_WARN",
        "leg_role": "",
        "description": "tracking error 1.8% exceeds 1.5% band vs Nifty spot since entry.",
    },
}


def build_message(d: dict) -> str:
    """Cause->effect compact port of _route_event's WARN branch text, MarkdownV2-safe.

    Shape (Animesh-confirmed v2, 2026-08-08 — supersedes the v1 kv-line draft in this
    module's docstring):
        ⚠️ DELTA BREACH - <strategy label>
        Leg: <leg role label>              [omitted entirely when leg_role absent/empty]
        <description, escaped>

    event_type -> mechanical `.replace("_", " ")` only (real identifier reformatted, not
    renamed — see module docstring point 1). strategy_name -> STRATEGY_LABELS lookup,
    escape_markdown()'d (fuller-form table, confirmed kept over ROLL-6's abbreviated one).
    leg_role -> LEG_ROLE_LABELS lookup, escape_markdown()'d, line omitted when absent.
    description -> escape_markdown() as a single line, deliberately not decomposed into
    separate Metric/Action fields — see module docstring for why that's out of scope.
    """
    event_headline = escape_markdown(d["event_type"].replace("_", " "))
    strategy_label = escape_markdown(_label_strategy(d["strategy_name"]))
    description = escape_markdown(d["description"])

    lines = [f"⚠️ {event_headline} \\- {strategy_label}"]
    leg_role = d.get("leg_role", "")
    if leg_role:
        lines.append(f"Leg: {escape_markdown(_label_leg(leg_role))}")
    lines.append(description)
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
    scenario = sys.argv[1] if len(sys.argv) > 1 else "delta_breach"
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
