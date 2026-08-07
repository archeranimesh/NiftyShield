"""Scratch script — IC Monthly Comparison (V1 vs V2) Telegram message format.

Not part of src/notifications/. Reference for ROLL-2's real port once
backbone/formatting-rules ship — see scratch/2026-08-07_ic_eod_audit_v2_
telegram_format.py's module docstring for the general "inline until
backbone ships" pattern this follows identically; not re-explained here.

History (2026-08-07): user provided real comparison data (below) plus a
separately-sourced mockup for the desired VISUAL structure (bold header,
side-by-side metric table, Legs row, Bkd/Flt month-vs-inception split,
Edge line). The mockup's own numbers (DTE 19, Captured -21%/-1%, Edge
+₹58) do not match the real data (DTE 18, Captured 4%/3%, Edge +₹286) —
clearly a generic placeholder render, not real figures. This script uses
the mockup's STRUCTURE with the REAL numbers, and explicitly does NOT
fabricate two fields the mockup showed but the real data never supplied:

1. Legs row (V1 Legs: 4/4 | V2 Legs: 3/4 with a 🔴 for <4) — no leg-count
   data was given for either strategy. Showing a fabricated "3/4 🔴" would
   misrepresent portfolio state (implies a missing leg needing attention)
   with zero evidence. OMITTED from this render pending real leg-count
   data — see ROLL-2's stories.md TGFMT-2 carry-forward note, `open_pos`
   from build_stats() is the real source once wired.
2. Flt P&L (M) and Bkd P&L (I) — per ROLL-2's TGFMT-3 carry-forward note,
   Flt(M) is "a genuinely new calculation" (month-start delta on
   unrealized_pnl) not yet built anywhere, and Bkd(I) needs
   paper_nav_snapshots.realized_pnl's cumulative-inception value, which
   was never supplied. Both render as "N/A" here, not guessed numbers.

Read-only w.r.t. the DB — makes zero DB calls. Sends a real Telegram
message (counts against the configured message budget) when run as
__main__ with --send.

Run from repo root with the project's normal venv active:
    python -m scratch.2026-08-07_ic_monthly_comparison_telegram_format
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402

# Real data as given by the user, 2026-08-07. Bkd P&L (I) / Flt P&L (M)
# deliberately absent (None) — see module docstring point 2.
data = {
    "as_of": "2026-08-07",
    "columns": ["V1", "V2"],
    "dte": (18, 18),
    "credit": (Decimal("87"), Decimal("129")),
    "captured_pct": (4.0, 3.0),
    "put_delta": (-0.03, -0.23),
    "call_delta": (0.28, 0.23),
    "flt_pnl_m": (None, None),  # Flt (M) — not yet computed anywhere, see docstring
    "bkd_pnl_m": (Decimal("0"), Decimal("58")),
    "flt_pnl_i": (Decimal("359"), Decimal("587")),
    "bkd_pnl_i": (None, None),  # Bkd (I) — cumulative-inception field not supplied
    "lock_zone": ("N/A", "None"),
    "adjustments": ("0R", "0R, 0L"),
    "signals": ("None", "None"),
    "edge_amount": Decimal("286"),
    "edge_leader": "V2",
}


# --- Inlined MD-1 helpers (src/notifications/markdown.py, not yet shipped) ---

MARKDOWNV2_RESERVED = "_*[]()~`>#+-=|{}.!"


def escape_markdown(text: str) -> str:
    """Backslash-escape MarkdownV2 reserved characters. See MD-1 in
    backbone/stories.md — inlined here only because that module doesn't
    exist yet this session.
    """
    return "".join(f"\\{ch}" if ch in MARKDOWNV2_RESERVED else ch for ch in text)


def mdcode(value: str) -> str:
    """Wrap a dynamic identifier-like value as a code span. See MD-1."""
    if "`" in value:
        return escape_markdown(value)
    return f"`{value}`"


# --- Inlined FMT-2 formatters (subset needed here) ---


def format_money(value: Decimal | None) -> str:
    """2dp, comma thousands, ₹ prefix, sign before symbol. 'N/A' for None
    (not a Greek — this table's own missing-data convention, since '-'
    is already used inside the leg table for a different meaning).
    """
    if value is None:
        return "N/A"
    sign = "-" if value < 0 else ""
    return f"{sign}₹{abs(value):,.0f}"


def format_pct_signed(value: float) -> str:
    """Signed 1dp percent, no trailing .0 on whole numbers — matches
    FMT-1's percent rule, extended with an explicit sign since this
    table can show a negative Captured% (loss state), unlike the IC EOD
    audit message where Captured% always reads as "how much of credit
    consumed" and pnl_emoji carries the sign separately.
    """
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.0f}%" if value == int(value) else f"{sign}{value:.1f}%"


def format_delta(value: float) -> str:
    """2dp, always signed — same convention as FMT-2's format_greek."""
    return f"{value:+.2f}"


# --- Table builder (FMT-3-style, generic 2-column comparison rows) ---


def build_compare_table(groups: list[list[tuple[str, str, str]]], columns: tuple[str, str]) -> str:
    """Fenced-code-block-ready comparison table, one or more row groups
    separated by a dashed rule (mirrors the mockup's 3-section layout:
    entry metrics / P&L metrics / status metrics).

    Args:
        groups: list of row-groups; each row is (label, v1_str, v2_str).
        columns: the two column headers (e.g. ("V1", "V2")).

    Width is computed as max(len(x) for x in ...) across ALL rows in ALL
    groups, never a hand-counted constant — this is the exact bug class
    FMT-3's stories.md flags from build_comparison_report()'s pre-fix
    history (hand-counted 20-char budget broke on a longer label).
    """
    all_rows = [row for group in groups for row in group]
    label_w = max(len("Metric"), *(len(r[0]) for r in all_rows))
    v1_w = max(len(columns[0]), *(len(r[1]) for r in all_rows))
    v2_w = max(len(columns[1]), *(len(r[2]) for r in all_rows))

    header = f"{'Metric':<{label_w}} {columns[0]:>{v1_w}} {columns[1]:>{v2_w}}"
    rule = "-" * len(header)

    lines = [header, rule]
    for i, group in enumerate(groups):
        for label, v1, v2 in group:
            lines.append(f"{label:<{label_w}} {v1:>{v1_w}} {v2:>{v2_w}}")
        if i < len(groups) - 1:
            lines.append(rule)
    lines.append(rule)
    return "\n".join(lines)


def build_message(d: dict) -> str:
    """Confirmed-structure IC Monthly Comparison message (2026-08-07).

    Legs row deliberately OMITTED — see module docstring point 1. When
    real leg-count data is wired in (ROLL-2's TGFMT-2 carry-forward),
    re-add it as the second line, matching the mockup's
    "🔹 *V1 Legs:* n/4 | *V2 Legs:* n/4 [🔴]" shape.
    """
    v1, v2 = d["columns"]
    date_str = escape_markdown(d["as_of"])

    groups = [
        [
            ("DTE", str(d["dte"][0]), str(d["dte"][1])),
            (
                "Credit",
                format_money(d["credit"][0]),
                format_money(d["credit"][1]),
            ),
            (
                "Captured",
                format_pct_signed(d["captured_pct"][0]),
                format_pct_signed(d["captured_pct"][1]),
            ),
            (
                "Put Δ",
                format_delta(d["put_delta"][0]),
                format_delta(d["put_delta"][1]),
            ),
            (
                "Call Δ",
                format_delta(d["call_delta"][0]),
                format_delta(d["call_delta"][1]),
            ),
        ],
        [
            ("Flt P&L (M)", format_money(d["flt_pnl_m"][0]), format_money(d["flt_pnl_m"][1])),
            ("Bkd P&L (M)", format_money(d["bkd_pnl_m"][0]), format_money(d["bkd_pnl_m"][1])),
            ("Flt P&L (I)", format_money(d["flt_pnl_i"][0]), format_money(d["flt_pnl_i"][1])),
            ("Bkd P&L (I)", format_money(d["bkd_pnl_i"][0]), format_money(d["bkd_pnl_i"][1])),
        ],
        [
            ("Lock Zone", d["lock_zone"][0], d["lock_zone"][1]),
            ("Adjustments", d["adjustments"][0], d["adjustments"][1]),
            ("Signals", d["signals"][0], d["signals"][1]),
        ],
    ]
    table = build_compare_table(groups, (v1, v2))

    # Raw (unescaped) text, deliberately — this goes into mdcode()'s code
    # span next, which Telegram never parses for entities, so escaping it
    # first would make the backslashes render literally instead of being
    # invisible. escape_markdown() is only for text going into PLAIN
    # (non-code-span) MarkdownV2 text — mixing the two up here was an
    # actual bug in this script's first draft, caught before testing.
    edge_str = f"{d['edge_leader']} (+{format_money(d['edge_amount'])} vs V1)"

    lines = [
        f"⚖️ *IC Monthly \\(V1 vs V2\\)* \\| {date_str}",
        "```text",
        table,
        "```",
        f"\U0001f3c6 *Edge so far:* {mdcode(edge_str)}",
    ]
    return "\n".join(lines)


async def send_markdown_v2(bot_token: str, chat_id: str, message: str) -> bool:
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "MarkdownV2"}
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, json=payload) as resp:
                resp_data = await resp.json()
                if not resp_data.get("ok"):
                    print(f"!! Telegram API error ({resp.status}): {resp_data.get('description')}")
                return bool(resp_data.get("ok"))
    except Exception as exc:  # Intentional: isolate all API failures, scratch probe only
        print(f"!! send failed: {exc}")
        return False


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="IC Monthly Comparison (V1 vs V2) Telegram message format probe."
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send to Telegram (default: print only). Requires "
        "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID in the environment.",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    text = build_message(data)
    print(text)
    print(
        "\n(Note: printed text above is raw MarkdownV2 source — asterisks/"
        "backslashes are literal here. Check the actual rendering on-device "
        "after sending, not this console output. Flt P&L (M) and Bkd P&L (I) "
        "render as N/A — real data was never supplied for those two fields, "
        "see module docstring.)"
    )

    if not args.send:
        print("\n(--send not passed — nothing sent.)")
        return

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print("\n!! TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — cannot send.")
        return

    ok = await send_markdown_v2(settings.telegram_bot_token, settings.telegram_chat_id, text)
    print(f"\nsend_markdown_v2() returned {ok}")


if __name__ == "__main__":
    asyncio.run(main())
