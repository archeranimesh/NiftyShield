"""Scratch script — 3-Track BASE POSITION EXPIRY Telegram summary (v2).

Message #8 in docs/plan/telegram-markdown-migration/TODO.md's "Confirmed missing" queue.
Spec: docs/plan/telegram-markdown-migration/strategy-rollout/stories.md ROLL-15 (DRAFT).

Real call site: `scripts/strategies/three_track/paper_3track_snapshot.py:487-501` (inside the
DTE<=5 base-expiry branch, `if notifier: await notifier.send(msg)`). Confirmed via direct read
of the real source, not the TODO.md grep excerpt (which points at the wrong line range).

Original source (real f-string, `scripts/strategies/three_track/paper_3track_snapshot.py:487-495`):
    msg = (
        f"⚠️ *BASE POSITION EXPIRY ALERT*\n"
        f"Strategy: {pos.strategy_name}\n"
        f"Leg: {pos.leg_role}\n"
        f"Expiring Contract: {expiring_symbol} ({dte} DTE)\n"
        f"Next Contract: {next_symbol} (Key: {next_key}){warning_suffix}\n\n"
        f"Settlement Close:\n`{close_cmd}`\n\n"
        f"Roll Open:\n`{roll_cmd}`"
    )
    if notifier:
        await notifier.send(msg)

v2 (THIS VERSION — supersedes v1's straight reformat; Animesh reviewed a hand-drafted
alternative and decided this message should carry a compact summary in Telegram, with the
`close_cmd`/`roll_cmd` shell commands moved to a structured log line instead of the message
body — see ROLL-15's "Design decision" for the operational tradeoff this implies (commands no
longer copy-pasteable straight from Telegram on a phone)):

Shape:
    🚨 Base Position Expiry — <Strategy Display Name>
    Leg: <Leg Display Name> (<DTE> DTE)
    System: ⚠️ BOD data potentially stale        [only when warning_suffix fires in the real source]
    Action Required: Manual Roll
    📤 Close: Long <lot_size>x <Expiring Symbol>
    📥 Open: Long <lot_size>x <Next Symbol>

Direction verb hardcoded `Long`, not derived — `base_futures`/`base_ditm_call` never go short
by strategy design (confirmed by Animesh, 2026-08-11; the `is_short` check present elsewhere
in the same source file is copy-reused entry-price-selection logic shared with genuinely
short-capable legs like `overlay_cc`, not evidence this leg can be short — see ROLL-15's
resolved-direction note for the full reasoning, including the noted-but-not-blocking residual
code gap: nothing currently guards against a negative `net_qty` reaching this branch).

Strategy/leg names rendered as human-readable labels (`Paper 3-Track Nifty V1`, `Base DITM
Call`) rather than the raw `strategy_name`/`leg_role` identifiers, matching this epic's
established "resolve to something readable" direction (ROLL-12/ROLL-13). Fixed lookup tables
below, not derived — an unmapped value raises, same discipline as ROLL-7/ROLL-8/ROLL-12's
label dicts.

Symbol lines use the real source's already-resolved `expiring_symbol`/`next_symbol` values
(trading_symbol strings, e.g. `NIFTY26AUG21500CE`) — condensed to `NIFTY <MON> <strike> <right>`
for readability, matching ROLL-13's leg-line convention, not the literal broker trading symbol
verbatim. When `next_inst` resolution fails (the real source's `warning_suffix` branch), the
Open line falls back to the placeholder text the real source already produces
(`<NEXT_CONTRACT_SYMBOL>`) — never the ad hoc string "Next Contract" Animesh used as shorthand
in his review draft, since the real code can't actually produce that exact string.

`lot_size` is NOT a real field on `PaperPosition` in the real source at this call site — the
existing code only has `pos.net_qty`. Using `abs(pos.net_qty)` here (matches what `close_cmd`/
`roll_cmd`'s `--qty` argument already uses in the original source), not a separate lot_size
lookup.

Escaping: `mdcode()` for identifier-shaped dynamic values (nothing free-form enough here to
need `escape_markdown()` on its own); static parens around `(<DTE> DTE)` are literal
MarkdownV2-reserved punctuation -> explicit `\\(`/`\\)`; the *bold* headline markers are the
intended entity, not escaped.

Log-emit requirement (real implementation, NOT built here — this script is docs/format-only
per the workshop's own rule): `close_cmd`/`roll_cmd` move to a `logger.info(...)` call at the
same call site. Left in SCENARIOS below (unused by build_message) purely so the eventual real
implementation's log-line test fixtures have realistic sample values to start from.

backbone/ (MD-1..MD-5) status as of this session: NOT shipped — confirmed via
`search_graph("mdcode")` returning zero hits under src/notifications/. This script inlines its
own copies of `escape_markdown()`/`mdcode()`, matching MD-1's spec.

Not part of src/notifications/ — purely for iterating on layout before wiring into the real
script. Makes zero DB calls. Sends a real Telegram message (counts against the configured
message budget).

Run from repo root with the project's normal venv active:
    python -m scratch.2026-08-11_3track_settlement_roll_format <scenario> [--send]
    python -m scratch.2026-08-11_3track_settlement_roll_format --list-scenarios
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
    """Wrap a dynamic identifier as an inline code span — mirrors MD-1's mdcode() spec."""
    if "`" in value:
        return f"`{value.replace(chr(96), chr(92) + chr(96))}`"
    return f"`{value}`"


# Fixed strategy_name -> display label lookup. Unmapped raises, matching ROLL-7/ROLL-8/
# ROLL-12's label-dict discipline.
STRATEGY_LABELS: dict[str, str] = {
    "paper_3track_nifty_v1": "Paper 3-Track Nifty V1",
}

# Fixed leg_role -> display label lookup.
LEG_LABELS: dict[str, str] = {
    "base_futures": "Base Futures",
    "base_ditm_call": "Base DITM Call",
}


def _label(table: dict[str, str], key: str, table_name: str) -> str:
    try:
        return table[key]
    except KeyError:
        raise ValueError(f"no display mapping for {table_name}={key!r}") from None


# ── Sample data — mirrors real PaperPosition / instrument fields (confirmed via read of
# paper_3track_snapshot.py:379-495 this session). close_cmd/roll_cmd kept for the eventual
# real log-emit implementation's test fixtures; unused by build_message() below. ──

SCENARIOS: dict[str, dict] = {
    "base_futures_expiring": {
        "strategy_name": "paper_3track_nifty_v1",
        "leg_role": "base_futures",
        "net_qty": 65,
        "expiring_symbol": "NIFTY26AUGFUT",
        "next_symbol": "NIFTY26SEPFUT",
        "next_key": "NSE_FO|54321",
        "dte": 4,
        "warning_suffix": "",
        "close_cmd": (
            "python scripts/record/record_paper_trade.py "
            "--strategy paper_3track_nifty_v1 --leg base_futures --action SELL "
            "--qty 65 --key NSE_FO|48213 --price <SETTLEMENT_LTP> "
            "--date 2026-08-25 --no-dry-run"
        ),
        "roll_cmd": (
            "python scripts/record/record_paper_trade.py "
            "--strategy paper_3track_nifty_v1 --leg base_futures --action BUY "
            "--qty 65 --key NSE_FO|54321 --price <ROLL_LTP> "
            "--date 2026-08-26 --no-dry-run"
        ),
    },
    "base_ditm_call_expiring_stale_bod": {
        "strategy_name": "paper_3track_nifty_v1",
        "leg_role": "base_ditm_call",
        "net_qty": 65,
        "expiring_symbol": "NIFTY26AUG21500CE",
        "next_symbol": "<NEXT_CONTRACT_SYMBOL>",
        "next_key": "<NEXT_CONTRACT_KEY>",
        "dte": 2,
        "warning_suffix": "\n\n⚠️ WARNING: BOD may be stale",
        "close_cmd": (
            "python scripts/record/record_paper_trade.py "
            "--strategy paper_3track_nifty_v1 --leg base_ditm_call --action SELL "
            "--qty 65 --key NSE_FO|91020 --price <SETTLEMENT_LTP> "
            "--date 2026-08-25 --no-dry-run"
        ),
        "roll_cmd": (
            "python scripts/record/record_paper_trade.py "
            "--strategy paper_3track_nifty_v1 --leg base_ditm_call --action BUY "
            "--qty 65 --key <NEXT_CONTRACT_KEY> --price <ROLL_LTP> "
            "--date 2026-08-26 --no-dry-run"
        ),
    },
}


def build_message(d: dict) -> str:
    """v2 layout for paper_3track_snapshot.py's BASE POSITION EXPIRY notify block — summary
    only, no commands. See module docstring for full derivation notes. Direction hardcoded
    Long (Animesh-confirmed). Not yet live-send confirmed — pending review.
    """
    strategy = escape_markdown(_label(STRATEGY_LABELS, d["strategy_name"], "strategy_name"))
    leg = escape_markdown(_label(LEG_LABELS, d["leg_role"], "leg_role"))
    dte = escape_markdown(str(d["dte"]))
    qty = escape_markdown(str(abs(d["net_qty"])))
    expiring_symbol = mdcode(d["expiring_symbol"])
    next_symbol = mdcode(d["next_symbol"])

    lines = [
        f"🚨 *Base Position Expiry* — {strategy}",
        f"Leg: {leg} \\({dte} DTE\\)",
    ]
    if d["warning_suffix"]:
        lines.append("System: ⚠️ BOD data potentially stale")
    lines.append("Action Required: Manual Roll")
    lines.append(f"📤 Close: Long {qty}x {expiring_symbol}")
    lines.append(f"📥 Open: Long {qty}x {next_symbol}")

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
    scenario = sys.argv[1] if len(sys.argv) > 1 else "base_futures_expiring"
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
