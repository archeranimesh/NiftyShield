"""Scratch script — IC EOD audit Telegram message formatting experiment.

Not part of src/notifications/. Purely for iterating on layout before
wiring into the real notifier (per src/notifications/CLAUDE.md).

History (2026-08-07):
1. <b>/<code> tags sent through TelegramNotifier.send() — that method
   HTML-escapes the whole body and wraps it in <pre>, so tags rendered
   as literal text.
2. Raw HTML (parse_mode=HTML, no <pre>), payload matching
   TelegramGateway.send_notification() — bold rendered, but lost the
   <pre> tap-to-copy box. Nested <b> inside <pre> isn't reliably
   rendered by Telegram's HTML parser, so both together don't work
   in HTML mode.
3. Plain monospace via TelegramNotifier.send() (no tags at all) —
   copyable, correctly aligned, but no bold/emphasis anywhere.
4. THIS VERSION: Markdown parse_mode instead of HTML. Bold headers
   (*text* — single asterisk; Telegram's legacy Markdown is NOT
   GitHub-flavored, ** produces unbalanced entities and a 400) and
   inline code (`text`) live OUTSIDE a fenced ```code``` block; the leg
   table lives INSIDE the fence, so it keeps its own monospace alignment
   and copy affordance while the surrounding lines get real bold. This
   is the first version that gets bold AND a copyable aligned table in
   the same message — the earlier two options were mutually exclusive
   under HTML parse_mode specifically.

   Uses legacy parse_mode="Markdown" (v1), not MarkdownV2. Content here
   has no literal _, *, `, or [ characters outside the code fence, which
   are the only characters legacy Markdown treats as special — so no
   escaping is needed. MarkdownV2 would additionally require escaping
   . ( ) ! - | which appear throughout (e.g. "(4%)", "82,628") and would
   make this function much noisier for no benefit here. If a future
   version needs italics/strikethrough/spoilers, re-evaluate — those
   aren't in legacy Markdown.

   This bypasses TelegramNotifier.send() (which is hardcoded to
   parse_mode=HTML) — same pattern as version 2's direct-payload
   approach, adapted for Markdown.

   NOT YET A DECISION: which of versions 3 vs 4 becomes the permanent
   convention (copy-safety vs. richer formatting) belongs in
   DECISIONS.md once picked, since notifications/CLAUDE.md's HTML
   parse_mode note would need updating to also cover Markdown.

Read-only w.r.t. the DB — makes zero DB calls. Sends a real Telegram
message (counts against the configured message budget).

Run from repo root with the project's normal venv active:
    python -m scratch.2026-08-07_ic_eod_audit_telegram_format
or:
    python scratch/2026-08-07_ic_eod_audit_telegram_format.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import aiohttp

# Allow running as a plain script (python scratch/foo.py) as well as -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402

data = {
    "strategy_label": "IC EOD (Monthly)",
    "strategy_id": "paper_ic_nifty_v1_monthly",
    "dte": 18,
    "nifty": 24571,
    "ivr": 0.16,
    "legs": [
        {"role": "Short Put", "strike": 23000, "opt_type": "PE", "delta": -0.03,
         "ltp": 9.30, "entry": 71.80},
        {"role": "Long Put", "strike": 22500, "opt_type": "PE", "delta": None,
         "ltp": 6.40, "entry": None},
        {"role": "Short Call", "strike": 25000, "opt_type": "CE", "delta": 0.28,
         "ltp": 100.40, "entry": 70.50},
        {"role": "Long Call", "strike": 25500, "opt_type": "CE", "delta": None,
         "ltp": 19.75, "entry": None},
    ],
    "mark": 83.55,
    "entry_credit": 86.68,
    "pct_captured": 4,
    "roi_amount": 203,
    "margin": 82628,
    "roi_pct": 0.2,
    "signals": ["DELTA_WARN"],
    "intraday_actions": [],
}


def _leg_table(legs: list[dict]) -> str:
    """Fenced monospace table — Act/Strike/Type/Δ/LTP/Entry columns,
    right-aligned numerics. Lives inside a ```code block``` so Markdown
    parse_mode leaves its formatting alone and it stays one tap-to-copy
    unit even though the surrounding message uses bold/emoji.
    """
    rows = []
    for leg in legs:
        badge = "[S]" if leg["role"].startswith("Short") else "[B]"
        delta_str = f"{leg['delta']:+.2f}" if leg["delta"] is not None else "-"
        entry_str = f"{leg['entry']:.1f}" if leg["entry"] is not None else "-"
        rows.append((badge, str(leg["strike"]), leg["opt_type"], delta_str,
                     f"{leg['ltp']:.1f}", entry_str))

    widths = {
        "act": 3,
        "strike": max(len("Strike"), *(len(r[1]) for r in rows)),
        "type": max(len("Type"), *(len(r[2]) for r in rows)),
        "delta": max(len("Δ"), *(len(r[3]) for r in rows)),
        "ltp": max(len("LTP"), *(len(r[4]) for r in rows)),
        "entry": max(len("Entry"), *(len(r[5]) for r in rows)),
    }

    header = (
        f"{'Act':<{widths['act']}} {'Strike':<{widths['strike']}} "
        f"{'Type':<{widths['type']}} {'Δ':>{widths['delta']}} "
        f"{'LTP':>{widths['ltp']}} {'Entry':>{widths['entry']}}"
    )
    lines = [header, "-" * len(header)]
    for act, strike, opt_type, delta_str, ltp_str, entry_str in rows:
        lines.append(
            f"{act:<{widths['act']}} {strike:<{widths['strike']}} "
            f"{opt_type:<{widths['type']}} {delta_str:>{widths['delta']}} "
            f"{ltp_str:>{widths['ltp']}} {entry_str:>{widths['entry']}}"
        )
    return "\n".join(lines)


def build_message(d: dict) -> str:
    captured_credit = d["entry_credit"] - d["mark"]  # credit spread: profit = credit in - cost to close
    # Signal codes (DELTA_WARN, and by the same convention likely
    # GAMMA_RISK / THETA_DECAY / roll-trigger codes elsewhere) always
    # contain underscores. In legacy Markdown a lone `_` outside a code
    # span opens an _italic_ entity; with no matching closing underscore
    # in a single-word code, Telegram 400s with "can't find end of the
    # entity" (confirmed 2026-08-07: byte offset landed inside
    # DELTA_WARN). Wrapping each code in backticks — same treatment as
    # strategy_id — makes it a code span, which Telegram does not parse
    # for entities, so underscores inside are inert regardless of count.
    signals = ", ".join(f"`{s}`" for s in d["signals"]) if d["signals"] else "None"
    # Same underscore risk applies here if action codes ever look like
    # ROLL_DOWN / LOCK_ZONE — empty today, but the wrapping shouldn't
    # depend on today's data staying that way.
    actions = ", ".join(f"`{a}`" for a in d["intraday_actions"]) if d["intraday_actions"] else "None"

    # NOTE: Telegram's legacy Markdown parse_mode uses single asterisks for
    # bold (*text*), not GitHub-style double asterisks (**text**). Sending
    # ** produced unbalanced entities and a 400 "can't parse entities" —
    # this was the actual cause of the earlier send failure, not anything
    # content-specific.
    lines = [
        f"📊 *{d['strategy_label']}* | `{d['strategy_id']}`",
        f"*Nifty:* {d['nifty']:,} | *DTE:* {d['dte']} | *IVR:* {d['ivr']:.2f}",
        "```",
        _leg_table(d["legs"]),
        "```",
        f"💰 *Credit:* ₹{d['entry_credit']:.2f} ➡️ *Mark:* ₹{d['mark']:.2f}",
        f"✅ *Captured:* ₹{captured_credit:.2f} ({d['pct_captured']}%) | "
        f"*ROI:* {d['roi_pct']:.1f}% (₹{d['roi_amount']})",
        f"🏦 *Margin:* ₹{d['margin']:,}",
        f"⚠️ *Alert:* {signals} | *Actions:* {actions}",
    ]
    return "\n".join(lines)


async def send_markdown(bot_token: str, chat_id: str, message: str) -> bool:
    """Send with parse_mode=Markdown (legacy v1) — see module docstring
    for why v1 over MarkdownV2 for this specific message. Not part of
    TelegramNotifier, which is hardcoded to HTML.
    """
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, json=payload) as resp:
                # Don't raise_for_status() before reading the body — Telegram
                # puts the actual parse-error reason in the JSON "description"
                # field even on a 400, and raising first discards it.
                resp_data = await resp.json()
                if not resp_data.get("ok"):
                    print(f"!! Telegram API error ({resp.status}): {resp_data.get('description')}")
                return bool(resp_data.get("ok"))
    except Exception as exc:  # Intentional: isolate all API failures, scratch probe only
        print(f"!! send failed: {exc}")
        return False


async def main() -> None:
    text = build_message(data)
    print(text)

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print(
            "\n!! TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in environment — "
            "cannot send. Aborting without sending anything."
        )
        return

    ok = await send_markdown(settings.telegram_bot_token, settings.telegram_chat_id, text)
    print(f"\nsend_markdown() returned {ok}")
    if not ok:
        print("!! send failed — check logs / credentials before retrying")


if __name__ == "__main__":
    asyncio.run(main())
