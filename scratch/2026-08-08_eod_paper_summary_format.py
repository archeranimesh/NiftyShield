"""Scratch: iterate NiftyShield EOD Paper Summary Telegram message format.

Case: backbone/ (MD-1..MD-5) NOT shipped yet — mdcode()/escape_markdown() do not exist in
src/notifications/markdown.py yet (confirmed via search_graph during this session). This script
therefore inlines local copies of escape_markdown()/mdcode() matching the exact signature/
behavior specified in backbone/stories.md MD-1 and the reserved-char set from that spec, so the
eventual real port is near-verbatim, not a rewrite.

Target message — FINAL, confirmed by Animesh, 2026-08-08 (recorded in
strategy-rollout/stories.md ROLL-6, formatting-rules/stories.md FMT-1d):

    📝 NiftyShield Paper EOD | 07 Aug 2026 | #EOD_SUMMARY
    Activities: 0
    Total P&L : +₹64,615
    📊 Strategy Performance
    Strategy   |      Flt |      Bkd |    Total
    -----------|----------|----------|---------
    CSP V1     |        0 |  +11,024 |  +11,024
    IC V1 Leap |   +4,079 |        0 |   +4,079
    IC V1 Mth  |     +359 |   +3,486 |   +3,846
    IC V1 Wkly |        0 |   +2,759 |   +2,759
    IC V2 Mth  |     +587 |   -1,756 |   -1,169
    Nifty Fut  |     -150 |        0 |     -150
    Nifty Proxy|   -2,971 |   -3,443 |   -6,414
    Nifty Spot |  +50,640 |        0 |  +50,640

Iteration history (kept for context, do not re-litigate):
1. Table cells (2026-08-08): signed integer, comma-sep, no ₹ prefix, no decimals — deviates from
   FMT-1's general money spec (2dp, ₹ prefix) but mirrors build_leg_table's locked-in 1dp
   exception; now recorded as FMT-1d, not a one-off. Total P&L line keeps the sole ₹ symbol.
   Header date "07 Aug 2026" (4-digit year) is intentional, not forced through format_expiry()
   ("dd Mon yy") — this is a daily digest label, not an expiry-relative one.
2. Strategy labels (2026-08-08): changed from raw snake_case ids to human-readable short labels
   (_DISPLAY_NAME dict) — "IC V1 Leap", "IC V1 Mth" ("Mth" = monthly abbreviation), etc.
3. Column headers (2026-08-08): "Unrlzd"/"Realzd" -> "Flt"/"Bkd", reusing ROLL-2's existing
   "Flt P&L (M)" / "Bkd P&L (I)" vocabulary rather than a third set of abbreviations.
4. Hashtag (2026-08-08): #EOD_SUMMARY added to the header line. This is a whole-message tag, not
   per-strategy — considered a per-strategy footer-line tag list (rejected: this message
   aggregates all 8 strategies in one send, unlike the single-strategy IC EOD Audit where a tag
   identifies which one variant a message is about). Escaping "#"/"_" via escape_markdown() does
   not defeat Telegram's hashtag auto-detection on the rendered text — this exact mechanism was
   already confirmed working on-device in FMT-1c, not re-verified from scratch here.

Prefix emoji (📝, 📊) and the strategy display labels are literal display text, not identifiers —
kept in monospace table cells and header line, not wrapped in mdcode() (mdcode is for dynamic
identifier-like values such as strategy_id in log lines / callback payloads, not table row
labels which are already scoped inside a fenced code block where MarkdownV2 does not process
entities).

Run: python scratch/2026-08-08_eod_paper_summary_format.py
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal

# --- inlined MD-1 helpers (backbone/ not shipped yet; port verbatim once it lands) ---

MARKDOWNV2_RESERVED = "_*[]()~`>#+-=|{}.!"


def escape_markdown(text: str) -> str:
    """Backslash-escape MarkdownV2 reserved characters in free text.

    Per backbone/stories.md MD-1: static template text needs escaping too, not just
    interpolated values.
    """
    return "".join(f"\\{ch}" if ch in MARKDOWNV2_RESERVED else ch for ch in text)


def mdcode(value: str) -> str:
    """Wrap a dynamic identifier-like value as an inline code span for safe interpolation.

    Falls back to escape_markdown() if the value itself contains a literal backtick.
    """
    if "`" in value:
        return escape_markdown(value)
    return f"`{value}`"


# --- EOD summary specific formatting ---

# Short-name compaction: strategy_id -> display label used in the table (fits the fixed
# column width without truncating mid-word). Longest label sets the column width.
# Confirmed 2026-08-08: human-readable labels, not snake_case (e.g. "IC V1 Leap" not
# "ic_nifty_v1_leaps"), "Mth" abbreviation for monthly variants.
_DISPLAY_NAME = {
    "paper_csp_nifty_v1": "CSP V1",
    "paper_ic_nifty_v1_leaps": "IC V1 Leap",
    "paper_ic_nifty_v1_monthly": "IC V1 Mth",
    "paper_ic_nifty_v1_weekly": "IC V1 Wkly",
    "paper_ic_nifty_v2_monthly": "IC V2 Mth",
    "paper_nifty_futures": "Nifty Fut",
    "paper_nifty_proxy": "Nifty Proxy",
    "paper_nifty_spot": "Nifty Spot",
}

# Whole-message hashtag — this message aggregates all 8 strategies (unlike the single-strategy
# IC EOD Audit, where the tag identifies which one variant the message is about), so one
# message-level tag is used rather than a per-strategy tag list. Placed in the header line,
# same "| #TAG" style as the IC EOD Audit's confirmed format.
_MESSAGE_HASHTAG = "#EOD_SUMMARY"


@dataclass(frozen=True)
class StrategyRow:
    strategy_id: str
    unrealized: Decimal
    realized: Decimal

    @property
    def total(self) -> Decimal:
        return self.unrealized + self.realized


def _fmt_table_money(value: Decimal) -> str:
    """Signed, comma-separated, no decimals, no currency symbol — table-cell exception.

    Distinct from format_money() (2dp, ₹ prefix) per FMT-1. Sign always shown; zero renders
    as bare "0" (no sign) matching the confirmed target's "0" cells.
    """
    rounded = int(value.to_integral_value(rounding="ROUND_HALF_UP"))
    if rounded == 0:
        return "0"
    sign = "+" if rounded > 0 else "-"
    return f"{sign}{abs(rounded):,}"


def build_strategy_table(rows: list[StrategyRow]) -> str:
    """Fixed-width fenced-ready table: Strategy | Flt | Bkd | Total.

    Flt = floating (unrealized), Bkd = booked (realized) — reuses ROLL-2's "Flt P&L (M)" /
    "Bkd P&L (I)" vocabulary (formatting-rules/stories.md) rather than inventing new terms
    for the same underlying values.
    """
    name_col = max(len("Strategy"), *(len(_DISPLAY_NAME[r.strategy_id]) for r in rows))
    num_col = 9  # fits "+50,640" (7 chars) with 2 pad chars; matches confirmed target width

    header = (
        f"{'Strategy':<{name_col}}|{'Flt':>{num_col}} |{'Bkd':>{num_col}} |"
        f"{'Total':>{num_col}}"
    )
    sep = f"{'-' * name_col}|{'-' * (num_col + 1)}|{'-' * (num_col + 1)}|{'-' * num_col}"

    lines = [header, sep]
    for r in rows:
        label = _DISPLAY_NAME[r.strategy_id]
        lines.append(
            f"{label:<{name_col}}|{_fmt_table_money(r.unrealized):>{num_col}} |"
            f"{_fmt_table_money(r.realized):>{num_col}} |{_fmt_table_money(r.total):>{num_col}}"
        )
    return "\n".join(lines)


def build_message(date_str: str, council_count: int, rows: list[StrategyRow]) -> str:
    """Pure function: sample data -> full MarkdownV2 message text."""
    total_pnl = sum((r.total for r in rows), Decimal("0"))
    total_str = _fmt_table_money(total_pnl)
    # Total line keeps a literal ₹ (only place in the message money appears with the symbol).
    total_line = f"Total P&L : {total_str[0]}₹{total_str[1:]}" if total_str[0] in "+-" else (
        f"Total P&L : ₹{total_str}"
    )

    table = build_strategy_table(rows)

    # escape_markdown covers both '#' and '_' (both in MARKDOWNV2_RESERVED) — the backslash
    # is consumed at render time so Telegram's hashtag-entity scanner still sees a literal
    # "#EOD_SUMMARY" in the rendered text and makes it tappable.
    header_line = escape_markdown(
        f"📝 NiftyShield Paper EOD | {date_str} | {_MESSAGE_HASHTAG}"
    )
    activities_line = escape_markdown(f"Activities: {council_count}")
    total_line_escaped = escape_markdown(total_line)
    section_line = escape_markdown("📊 Strategy Performance")

    return (
        f"{header_line}\n"
        f"{activities_line}\n"
        f"{total_line_escaped}\n"
        f"{section_line}\n"
        f"```\n{table}\n```"
    )


def _sample_rows() -> list[StrategyRow]:
    return [
        StrategyRow("paper_csp_nifty_v1", Decimal("0.00"), Decimal("11024.00")),
        StrategyRow("paper_ic_nifty_v1_leaps", Decimal("4078.75"), Decimal("0.00")),
        StrategyRow("paper_ic_nifty_v1_monthly", Decimal("359.12"), Decimal("3486.44")),
        StrategyRow("paper_ic_nifty_v1_weekly", Decimal("0.00"), Decimal("2759.25")),
        StrategyRow("paper_ic_nifty_v2_monthly", Decimal("586.62"), Decimal("-1756.08")),
        StrategyRow("paper_nifty_futures", Decimal("-149.50"), Decimal("0.00")),
        StrategyRow("paper_nifty_proxy", Decimal("-2970.50"), Decimal("-3443.38")),
        StrategyRow("paper_nifty_spot", Decimal("50640.05"), Decimal("0.00")),
    ]


async def main() -> None:
    msg = build_message("07 Aug 2026", 0, _sample_rows())
    print("--- rendered source (raw MarkdownV2, not what Telegram displays) ---")
    print(msg)
    print("--- end ---")

    try:
        from src.config import settings  # type: ignore

        import aiohttp

        token = settings.telegram_bot_token
        chat_id = settings.telegram_chat_id
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"chat_id": chat_id, "text": msg, "parse_mode": "MarkdownV2"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.json()
                if resp.status != 200:
                    # Surface Telegram's actual `description` field — do not let a bare
                    # raise_for_status() swallow it (cost a full round-trip in the IC EOD
                    # session per message-format-workshop.md).
                    print(f"Telegram send failed ({resp.status}): {body.get('description')}")
                else:
                    print("Sent to Telegram OK.")
    except Exception as exc:  # non-fatal: this is a format-review scratch script
        print(f"(Skipped live send: {exc})")


if __name__ == "__main__":
    asyncio.run(main())
