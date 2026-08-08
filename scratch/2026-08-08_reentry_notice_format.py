"""Scratch script — Re-entry blocked/allowed notice Telegram message formatting.

Message #1 in docs/plan/telegram-markdown-migration/TODO.md's "Confirmed missing" queue —
`ReEntryMixin._check_reentry` (src/strategy/reentry_mixin.py:189-210). TODO.md's line only
named the BLOCKED half; the real code has two branches (ELIGIBLE and BLOCKED) sharing one
code path, both covered here as the two message scenarios.

**backbone/ (MD-1..MD-5) status as of this session: NOT shipped** — confirmed via
`search_graph("mdcode")` returning zero results. This script inlines its own copies of
`escape_markdown()` / `mdcode()`, matching MD-1's exact spec in
`docs/plan/telegram-markdown-migration/backbone/stories.md`.

Iteration history:
- v1 (first pass this session): ported the real code's status_line + free-form notes
  near-verbatim — one packed line (emoji + raw strategy_id + raw leg_role + verb) plus the
  existing prose `notes` string escaped wholesale.
- v2 (THIS VERSION, per Animesh's kv-line counter-proposal): multi-line kv shape
  (`RE-ENTRY BLOCKED: <label>` / `Leg: <label>` / `Reason: <short> (<detail>)`), matching this
  epic's established pattern of a human-readable label as the primary identifier (see ROLL-1's
  header design — plain label first, raw id kept separately only where audit/copy matters).
  Two things v1 didn't need that v2 does, both resolved here rather than left implicit:

  1. **Strategy display label.** `ReEntryMixin.strategy_name` is the raw id
     (`paper_csp_nifty_v1`), not "CSP V1". No generic id->label mapping exists anywhere in
     `src/strategy/` yet — the only precedent is ROLL-6's `_DISPLAY_NAME` table
     (`strategy-rollout/stories.md` ROLL-6), but that one is scoped to fit a narrow table
     column ("V1 Mth", "Fut") and reads badly as a standalone headline ("RE-ENTRY BLOCKED: V1
     Mth"). `STRATEGY_LABELS` below is therefore a SEPARATE, fuller-form mapping — same 12
     strategy_ids, different (longer) label text — not a reuse of ROLL-6's table. If ROLL-6
     ships first, worth revisiting whether one shared id->{short,long} label struct replaces
     both, rather than maintaining two independent label tables long-term; flagged here, not
     resolved.
  2. **Structured block reason**, not string-split prose. The real `_check_reentry` currently
     builds one free-text `blocked_reason` string per gate (e.g.
     "DTE=9 < 14 — too close to expiry for re-entry"). Splitting that on the em dash at
     render time to get "DTE=9 < 14" + "(Too close to expiry)" would be brittle — a future
     gate's reason might have no em dash, or a different shape. The honest fix (and the one
     assumed by this script's data) is for `_check_reentry`'s three gates to each return a
     `(short_reason, detail)` pair instead of one prose string — this is real production-logic
     scope beyond escaping, in bounds for a ROLL-* task (strategy-rollout is allowed to reword,
     per ROLL-3's charter), out of bounds for MD-3 (escaping-only). The real port must add this
     refactor, not fake it with string-splitting.

  `Leg:` labels use an explicit dict (`LEG_ROLE_LABELS`), not `.title()` — `"overlay_cc".title()`
  produces "Overlay Cc", not "Overlay CC"; CC/PP/IC acronyms need the same explicit treatment
  this epic already gives them elsewhere (FMT-1c's IC/V1/V2 badges, ROLL-6's CC/PP display
  names) rather than programmatic casing.

  Open question, not resolved in v2: the raw `strategy_id` (kept as its own `` `code span` ``
  line in ROLL-1's IC audit header, for exact-string copy/grep) is dropped entirely here, per
  Animesh's example. If exact-id grep-ability against logs turns out to matter for this
  message too, add it back as a third line — flagging, not deciding, since the example
  explicitly omitted it.

Not part of src/notifications/ — purely for iterating on layout before wiring into the real
mixin. Read-only w.r.t. the DB — makes zero DB calls. Sends a real Telegram message (counts
against the configured message budget).

Run from repo root with the project's normal venv active:
    python -m scratch.2026-08-08_reentry_notice_format <scenario> [--send]
    python -m scratch.2026-08-08_reentry_notice_format --list-scenarios
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


# ── Display-label tables (new for v2 — see module docstring point 1) ──
# Same 12 real strategy_ids as ROLL-6's _DISPLAY_NAME table (strategy-rollout/stories.md), but
# a separate, fuller-form label set — ROLL-6's abbreviations ("V1 Mth", "Fut") are sized for a
# narrow table column, not a standalone headline.

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

# leg_role values actually used as `reentry_leg_role` across the concrete strategies
# (CSPNiftyV1, CCOverlayV1, CollarOverlayV1 — the three ReEntryMixin subclasses per CONTEXT.md).
LEG_ROLE_LABELS: dict[str, str] = {
    "short_put": "Short Put",
    "short_call": "Short Call",
    "overlay_cc": "Overlay CC",
    "overlay_pp": "Overlay PP",
    "overlay_collar_call": "Overlay Collar Call",
    "overlay_collar_put": "Overlay Collar Put",
}


def _label_strategy(strategy_name: str) -> str:
    """Explicit-mapping lookup; unmapped id raises loudly rather than silently falling back
    to the raw id — a future new strategy needs an explicit label added here, same discipline
    ROLL-6 requires for its own bucket mapping."""
    try:
        return STRATEGY_LABELS[strategy_name]
    except KeyError:
        raise ValueError(f"no display label mapped for strategy_name={strategy_name!r}") from None


def _label_leg(leg_role: str) -> str:
    try:
        return LEG_ROLE_LABELS[leg_role]
    except KeyError:
        raise ValueError(f"no display label mapped for leg_role={leg_role!r}") from None


# ── Sample data — structured (short_reason, detail) pairs, not prose to be string-split.
# See module docstring point 2: the real _check_reentry must be refactored to emit these
# directly per gate, this is not derived by splitting the current free-text `notes`. ──

SCENARIOS: dict[str, dict] = {
    "eligible": {
        "strategy_name": "paper_csp_nifty_v1",
        "leg_role": "short_put",
        "script_hint": "scripts/record/record_paper_trade.py",
        "signal": "eligible",
    },
    "blocked_dte": {
        "strategy_name": "paper_ic_nifty_v1_monthly",
        "leg_role": "short_call",
        "signal": "blocked",
        "short_reason": "DTE=9 < 14",
        "detail": "Too close to expiry",
    },
    "blocked_ivr": {
        "strategy_name": "paper_covered_call_v1",
        "leg_role": "overlay_cc",
        "signal": "blocked",
        "short_reason": "IVR=0.19 < 0.25",
        "detail": "Low vol, skip cycle",
    },
    "blocked_open_position": {
        "strategy_name": "paper_csp_nifty_v1",
        "leg_role": "short_put",
        "signal": "blocked",
        "short_reason": "Position already active",
        "detail": None,
    },
}


def build_message(d: dict) -> str:
    """kv-line port of ReEntryMixin._check_reentry's status, MarkdownV2-safe.

    Shape (Animesh-confirmed counter-proposal, v2):
        BLOCKED:
            ⛔ RE\\-ENTRY BLOCKED: <strategy label>
            Leg: <leg label>
            Reason: <short_reason> \\(<detail>\\)          [detail omitted -> just short_reason]

        ELIGIBLE:
            ✅ RE\\-ENTRY ELIGIBLE: <strategy label>
            Leg: <leg label>
            Status: All Gates Passed
            Execute:
            `<script_hint>`

    strategy_name/leg_role -> looked up via the explicit label dicts, then escape_markdown()'d
    (labels are curated plain text, but escaped anyway on principle — cheap insurance against
    a future label containing '.'/'('/')'). short_reason/detail -> escape_markdown() (may
    contain '='/'<'/'.' from the real gate values). script_hint -> mdcode() (identifier/path,
    kept copyable).
    """
    strategy_label = escape_markdown(_label_strategy(d["strategy_name"]))
    leg_label = escape_markdown(_label_leg(d["leg_role"]))

    if d["signal"] == "eligible":
        script = mdcode(d["script_hint"])
        lines = [
            f"✅ RE\\-ENTRY ELIGIBLE: {strategy_label}",
            f"Leg: {leg_label}",
            "Status: All Gates Passed",
            "Execute:",
            script,
        ]
        return "\n".join(lines)

    short_reason = escape_markdown(d["short_reason"])
    detail = d.get("detail")
    reason_line = (
        f"Reason: {short_reason} \\({escape_markdown(detail)}\\)"
        if detail
        else f"Reason: {short_reason}"
    )
    lines = [
        f"⛔ RE\\-ENTRY BLOCKED: {strategy_label}",
        f"Leg: {leg_label}",
        reason_line,
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
    scenario = sys.argv[1] if len(sys.argv) > 1 else "blocked_dte"
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
