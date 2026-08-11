"""Scratch script — 3-Track BASE POSITION EXPIRY (settlement-close / roll-open command) message.

Message #8 in docs/plan/telegram-markdown-migration/TODO.md's "Confirmed missing" queue.

Real call site: `scripts/strategies/three_track/paper_3track_snapshot.py`, ~lines 450-501
(inside the DTE<=5 base-expiry branch, `if notifier: await notifier.send(msg)`). Confirmed via
direct read of the real source this session (not the TODO.md grep excerpt alone) — the excerpt's
line numbers (497-503) point at the `if notifier:` send block; the actual `msg = (...)` f-string
build starts at line 487. Fires once per expiring base leg (`base_futures` / `base_ditm_call`)
when `dte <= 5`, posting two copyable `record_paper_trade.py` shell commands (settlement-close +
roll-open) in one message — more structurally involved than items 1-7b: two distinct multi-line
code blocks, not a status line or flat kv-pairs.

**backbone/ (MD-1..MD-5) status as of this session: NOT shipped** — confirmed via
`search_graph("mdcode")` / `search_graph("escape_markdown")` returning zero hits under
src/notifications/ (same check as every prior scratch script this epic; `src/notifications/`
currently only has `telegram.py`/`telegram_gateway.py`/`protocol.py`, no `markdown.py`). This
script inlines its own copies of `escape_markdown()` / `mdcode()`, matching MD-1's spec exactly
(see backbone/stories.md MD-1).

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

v1 (THIS VERSION — first draft this session, pending Animesh's confirmation/live-send before
being written back, same discipline as every prior ROLL-N draft in this epic):

Kept the original's overall shape (headline, 4 kv-context lines, optional stale-BOD warning,
then two labeled code blocks) rather than restructuring — per ROLL-3's "match the format to
what the message needs" guidance, this message's job is "here are two commands, copy them,"
which the original's shape already serves well; the only real work is MarkdownV2-safing it.

Escaping applied:
  - `pos.strategy_name` / `pos.leg_role` / `expiring_symbol` / `next_symbol` / `next_key`: all
    identifier-shaped dynamic values -> `mdcode()` (renders monospace, inert to any reserved
    char inside, matches ROLL-12/ROLL-13's "identifier -> mdcode()" convention).
  - `dte`: an int, not free text, but still rendered via `escape_markdown(str(dte))` for
    consistency with the rest of this epic's int-interpolation handling (no reserved chars in
    a plain integer, but the epic's own convention wraps every interpolated value, not just the
    ones that happen to contain reserved characters in a given sample).
  - Static template punctuation: the parens around `({dte} DTE)` and `(Key: {next_key})`, and
    the bold-marker asterisks around `BASE POSITION EXPIRY ALERT`, are the ONLY static
    characters needing escaping. The asterisks are deliberately NOT escaped -- they're the
    intended `*bold*` entity, not literal text (this is the one line in the message that should
    render bold, per the original's intent). The parens ARE literal template punctuation and
    MarkdownV2-reserved -> `\\(` / `\\)`.
  - `warning_suffix`: static text (`"\\n\\n⚠️ WARNING: BOD may be stale"`) built in the
    real source, not user data -- the colon in "WARNING:" is not MarkdownV2-reserved, so no
    escaping needed there; kept as a plain conditional line, not run through escape_markdown()
    since it's already a controlled literal, matching how ROLL-11/ROLL-12 treated their own
    fixed warning strings.
  - `close_cmd` / `roll_cmd`: these are shell commands wrapped in a code span (`` ` ``) in the
    original, and stay that way here -- MarkdownV2 does not parse entities inside a code span,
    so the only characters that need escaping inside one are a literal backtick or backslash
    (neither occurs in a `record_paper_trade.py` invocation). Left as raw f-strings, matching
    the original -- NOT run through `escape_markdown()`, which would incorrectly stack backslash
    escapes in front of every `--flag` hyphen and break copy-paste. This mirrors MD-1's
    `mdcode()` docstring guidance (code-span content is inert) even though these two are built
    as bare backtick-wrapped f-strings rather than via `mdcode()` itself, since they're
    multi-line command text, not a single identifier value.

Placeholder values (`<SETTLEMENT_LTP>`, `<ROLL_LTP>`) inside the commands are intentional --
they're filled in by hand after checking the actual settlement/roll LTP, not computed here; kept
verbatim from the real source.

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
    """Wrap a dynamic identifier as an inline code span — mirrors MD-1's mdcode() spec.

    Falls back to a backtick-escaped form if value itself contains a literal backtick (none of
    this message's sample identifiers do, but the fallback is included for parity with MD-1's
    documented contract).
    """
    if "`" in value:
        return f"`{value.replace(chr(96), chr(92) + chr(96))}`"
    return f"`{value}`"


# ── Sample data — mirrors real PaperPosition / instrument fields (confirmed via read of
# paper_3track_snapshot.py:400-495 this session). ──

SCENARIOS: dict[str, dict] = {
    "base_futures_expiring": {
        "strategy_name": "paper_3track_nifty_v1",
        "leg_role": "base_futures",
        "expiring_symbol": "NIFTY26AUGFUT",
        "next_symbol": "NIFTY26SEPFUT",
        "next_key": "NSE_FO|54321",
        "dte": 4,
        "warning_suffix": "",
        "close_cmd": (
            "python scripts/record/record_paper_trade.py "
            "--strategy paper_3track_nifty_v1 "
            "--leg base_futures "
            "--action SELL "
            "--qty 65 "
            "--key NSE_FO|48213 "
            "--price <SETTLEMENT_LTP> "
            "--date 2026-08-25 "
            "--no-dry-run"
        ),
        "roll_cmd": (
            "python scripts/record/record_paper_trade.py "
            "--strategy paper_3track_nifty_v1 "
            "--leg base_futures "
            "--action BUY "
            "--qty 65 "
            "--key NSE_FO|54321 "
            "--price <ROLL_LTP> "
            "--date 2026-08-26 "
            "--no-dry-run"
        ),
    },
    "base_ditm_call_expiring_stale_bod": {
        "strategy_name": "paper_3track_nifty_v1",
        "leg_role": "base_ditm_call",
        "expiring_symbol": "NIFTY26AUG21500CE",
        "next_symbol": "<NEXT_CONTRACT_SYMBOL>",
        "next_key": "<NEXT_CONTRACT_KEY>",
        "dte": 2,
        "warning_suffix": "\n\n⚠️ WARNING: BOD may be stale",
        "close_cmd": (
            "python scripts/record/record_paper_trade.py "
            "--strategy paper_3track_nifty_v1 "
            "--leg base_ditm_call "
            "--action SELL "
            "--qty 65 "
            "--key NSE_FO|91020 "
            "--price <SETTLEMENT_LTP> "
            "--date 2026-08-25 "
            "--no-dry-run"
        ),
        "roll_cmd": (
            "python scripts/record/record_paper_trade.py "
            "--strategy paper_3track_nifty_v1 "
            "--leg base_ditm_call "
            "--action BUY "
            "--qty 65 "
            "--key <NEXT_CONTRACT_KEY> "
            "--price <ROLL_LTP> "
            "--date 2026-08-26 "
            "--no-dry-run"
        ),
    },
}


def build_message(d: dict) -> str:
    """v1 layout for paper_3track_snapshot.py's BASE POSITION EXPIRY notify block, MarkdownV2-safe.

    See module docstring for the full derivation notes and escaping discipline. Not yet
    Animesh-confirmed — first draft this session, pending live-send review.
    """
    strategy = mdcode(d["strategy_name"])
    leg = mdcode(d["leg_role"])
    expiring_symbol = mdcode(d["expiring_symbol"])
    next_symbol = mdcode(d["next_symbol"])
    next_key = mdcode(d["next_key"])
    dte = escape_markdown(str(d["dte"]))

    lines = [
        "⚠️ *BASE POSITION EXPIRY ALERT*",
        f"Strategy: {strategy}",
        f"Leg: {leg}",
        f"Expiring Contract: {expiring_symbol} \\({dte} DTE\\)",
        f"Next Contract: {next_symbol} \\(Key: {next_key}\\){d['warning_suffix']}",
        "",
        f"Settlement Close:\n`{d['close_cmd']}`",
        "",
        f"Roll Open:\n`{d['roll_cmd']}`",
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
