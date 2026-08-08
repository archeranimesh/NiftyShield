"""Scratch: iterate NiftyShield EOD Paper Summary Telegram message format.

Case: backbone/ (MD-1..MD-5) NOT shipped yet — mdcode()/escape_markdown() do not exist in
src/notifications/markdown.py yet (confirmed via search_graph during this session). This script
therefore inlines local copies of escape_markdown()/mdcode() matching the exact signature/
behavior specified in backbone/stories.md MD-1 and the reserved-char set from that spec, so the
eventual real port is near-verbatim, not a rewrite.

Target message — FINAL, confirmed by Animesh, 2026-08-08 (recorded in
strategy-rollout/stories.md ROLL-6, formatting-rules/stories.md FMT-1d/FMT-1e):

    📝 NiftyShield Paper EOD | 07 Aug 2026
    Activities: 0 | Net P&L: +₹65,404 ✅
    STRATEGY       |      FLT |      BKD |    TOTAL
    ===============|==========|==========|=========
    > TRACK TOTAL  |  +47,520 |   -3,443 |  +44,077
     Fut           |     -150 |        - |     -150
     Proxy         |   -2,971 |   -3,443 |   -6,414
     Spot          |  +50,640 |        - |  +50,640
    ---------------|----------|----------|---------
    > IC TOTAL     |   +5,144 |   +4,490 |   +9,634
     V1 Wkly       |        - |   +2,759 |   +2,759
     V1 Mth        |     +359 |   +3,486 |   +3,846
     V1 Leap       |   +4,079 |        - |   +4,079
     V1 Yrly       |     +120 |        - |     +120
     V2 Mth        |     +587 |   -1,756 |   -1,169
    ---------------|----------|----------|---------
    > OVERLAY TOTAL|     +115 |     +555 |     +669
     Collar        |     +210 |      -86 |     +125
     CC            |        - |     +640 |     +640
     PP            |      -95 |        - |      -95
    ---------------|----------|----------|---------
    > CSP TOTAL    |        - |  +11,024 |  +11,024
     V1            |        - |  +11,024 |  +11,024
    #EOD_SUMMARY

Iteration history (kept for context, do not re-litigate):
1. Table cells (v1, 2026-08-08): signed integer, comma-sep, no ₹ prefix, no decimals —
   deviates from FMT-1's general money spec (2dp, ₹ prefix) but mirrors build_leg_table's
   locked-in 1dp exception; recorded as FMT-1d, not a one-off. Net P&L line keeps the sole ₹
   symbol in the whole message. Header date "07 Aug 2026" (4-digit year) is intentional, not
   forced through format_expiry() ("dd Mon yy") — this is a daily digest label, not an
   expiry-relative one.
2. Strategy labels (v2, 2026-08-08): revised twice. v1 used bucket-prefixed labels
   ("IC V1 Leap", "Nifty Fut", "CSP V1" — inconsistent, CSP kept its prefix, IC/Track didn't).
   v2 drops the bucket prefix uniformly ("V1 Leap", "Fut", "V1") since the bucket's own total
   row now establishes context (see point 5 below) — repeating it per row is redundant once
   rows are visually grouped under that row. "Mth" = monthly abbreviation throughout.
3. Column headers: "Unrlzd"/"Realzd" -> "Flt"/"Bkd" -> "FLT"/"BKD" (ALL CAPS in v2, matching
   the table's overall ALL-CAPS-for-structure convention), reusing ROLL-2's existing
   "Flt P&L (M)" / "Bkd P&L (I)" vocabulary rather than a third set of abbreviations.
4. Hashtag: v1 put #EOD_SUMMARY on the header line. v2 moves it to its own line AFTER the
   closing fence — MarkdownV2 doesn't parse entities (including auto-hashtag-detection) inside
   a fenced block, so it could never live inside the table; moving it off the header line also
   keeps that line shorter. Still a whole-message tag, not per-strategy — this message
   aggregates 12 strategies in one send, unlike the single-strategy IC EOD Audit where the tag
   identifies which one variant a message is about. Escaping "#"/"_" via escape_markdown() does
   not defeat Telegram's hashtag auto-detection on the rendered text — confirmed on-device in
   FMT-1c, not re-verified from scratch here.
5. Bucket grouping + totals-first (v2, 2026-08-08): added Overlay (Collar/CC/PP) and CSP
   buckets alongside Track/IC (v1 had no bucketing at all — flat 8-row list). Each bucket's
   subtotal row renders ABOVE its member rows, prefixed "> BUCKET TOTAL" (plain ASCII ">", see
   FMT-1e below for why not "▶"). This is a scan-speed trade-off vs. the more familiar
   components-then-sum order (confirmed intentional for this specific daily-glance message,
   not a pattern to generalize elsewhere in the epic without asking again) — and the total row
   doubles as the section label, so no separate "-- BUCKET --" header row is needed above it.
6. pnl_emoji (v2, 2026-08-08): added to the Net P&L summary line only (prose, outside the
   fence) — reuses FMT-1b's existing >0/<0/==0 spec rather than inventing a fourth emoji
   convention.
7. Zero cells (v2, 2026-08-08): render as a bare "-" (accounting-dash convention), not "0" —
   less visual noise for strategies/legs that haven't booked or marked anything yet.
8. "▶" -> ">" (v2 fix, 2026-08-08): on-device testing showed Telegram renders "▶" via its
   emoji-presentation glyph (auto-appended variation selector) even inside a fenced code
   block — double-width, breaks column alignment. Recorded as new FMT-1e: this risk applies to
   ANY Unicode symbol with an emoji-presentation variant, not just literal emoji — plain ASCII
   is the only fully safe choice inside a fence.

Prefix emoji (📝, ✅/🔻/➖ via pnl_emoji) and the strategy display labels are literal display
text, not identifiers — the header/summary-line emoji sit in prose (safe), never inside the
fenced table (see FMT-1e). Table row labels are not wrapped in mdcode() (mdcode is for dynamic
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
#
# Revised 2026-08-08 (v2, totals-first layout): labels no longer repeat the bucket name
# ("V1 Wkly" not "IC V1 Wkly", "Fut" not "Nifty Fut", "V1" not "CSP V1") — the bucket's own
# "-- IC --" / "-- Track --" / etc. label row already establishes context, so repeating it on
# every member row is redundant once rows are visually grouped under a bucket header. v1 of
# this table (kept in git history, not reproduced here) had this inconsistent: IC/Track already
# dropped the prefix, CSP didn't — fixed uniformly here.
#
# Real strategy_id values confirmed via src/paper/constants.py (Track/CSP/Overlay) and
# src/strategy/ic_expiry_config_v2.py / ic_nifty_v2.py (IC V2 naming pattern) — not assumed.
_DISPLAY_NAME = {
    # Track
    "paper_nifty_futures": "Fut",
    "paper_nifty_proxy": "Proxy",
    "paper_nifty_spot": "Spot",
    # IC (5 variants: V1 weekly/monthly/leaps/yearly + V2 monthly)
    "paper_ic_nifty_v1_weekly": "V1 Wkly",
    "paper_ic_nifty_v1_monthly": "V1 Mth",
    "paper_ic_nifty_v1_leaps": "V1 Leap",
    "paper_ic_nifty_v1_yearly": "V1 Yrly",
    "paper_ic_nifty_v2_monthly": "V2 Mth",
    # Overlay
    "paper_collar_v1": "Collar",
    "paper_covered_call_v1": "CC",
    "paper_protective_put_v1": "PP",
    # CSP
    "paper_csp_nifty_v1": "V1",
}

# Bucket grouping (confirmed 2026-08-08) — order matters, rendered top to bottom. Each bucket
# gets a plain dashed label row ("-- Track --") and a subtotal row at the end, in addition to
# the grand Total P&L line at the top of the message.
_BUCKETS: list[tuple[str, list[str]]] = [
    ("Track", ["paper_nifty_futures", "paper_nifty_proxy", "paper_nifty_spot"]),
    (
        "IC",
        [
            "paper_ic_nifty_v1_weekly",
            "paper_ic_nifty_v1_monthly",
            "paper_ic_nifty_v1_leaps",
            "paper_ic_nifty_v1_yearly",
            "paper_ic_nifty_v2_monthly",
        ],
    ),
    ("Overlay", ["paper_collar_v1", "paper_covered_call_v1", "paper_protective_put_v1"]),
    ("CSP", ["paper_csp_nifty_v1"]),
]

# Whole-message hashtag — this message aggregates all 8 strategies (unlike the single-strategy
# IC EOD Audit, where the tag identifies which one variant the message is about), so one
# message-level tag is used rather than a per-strategy tag list. Placed in the header line,
# same "| #TAG" style as the IC EOD Audit's confirmed format.
_MESSAGE_HASHTAG = "#EOD_SUMMARY"


@dataclass(frozen=True)
class StrategyRow:
    """One strategy's Flt/Bkd figures for the EOD summary table.

    unrealized: point-in-time mark-to-market (latest paper_nav_snapshots.unrealized_pnl row).

    realized: **since-inception, survives close/reopen cycles** (confirmed with Animesh,
    2026-08-08) — real implementation must source this from
    get_strategy_realized_pnl(store, strategy_name) in src/paper/tracker.py (sums from the
    append-only paper_trades ledger), NOT from paper_nav_snapshots.realized_pnl's latest row.
    The raw snapshot column resets to 0 on a full open->close->reopen cycle (confirmed live for
    paper_nifty_futures on 2026-08-05, per CONTEXT.md SNAP-1) — using it here would silently
    undercount exactly the Track-bucket strategies most likely to have cycled. This mirrors the
    same correction ROLL-2's spec needed for its Bkd (I) field; apply uniformly across all 12
    strategies here too, not just Track.
    """

    strategy_id: str
    unrealized: Decimal
    realized: Decimal

    @property
    def total(self) -> Decimal:
        return self.unrealized + self.realized


def _fmt_table_money(value: Decimal) -> str:
    """Signed, comma-separated, no decimals, no currency symbol — table-cell exception.

    Distinct from format_money() (2dp, ₹ prefix) per FMT-1. Sign always shown.

    Revised 2026-08-08 (v2): zero renders as a bare "-" (accounting-dash convention), not "0" —
    reduces visual noise from strategies/legs that haven't booked or marked anything yet. This
    is a v2-specific choice; v1's "0" rendering is kept in git history for reference, not
    reproduced here.
    """
    rounded = int(value.to_integral_value(rounding="ROUND_HALF_UP"))
    if rounded == 0:
        return "-"
    sign = "+" if rounded > 0 else "-"
    return f"{sign}{abs(rounded):,}"


def pnl_emoji(amount: Decimal) -> str:
    """>0 -> '✅', <0 -> '🔻', ==0 -> '➖'.

    Reuses FMT-1b's exact spec (formatting-rules/stories.md) rather than inventing a new
    convention — applied here only to the message-level Net P&L line (prose text, outside the
    fenced table), never inside the table itself. Emoji are double-width in most renderers and
    will break monospace column alignment inside a fenced code block — this is the same
    constraint FMT-3 already documents for build_leg_table's plain-text [S]/[B] badges.
    """
    if amount > 0:
        return "✅"
    if amount < 0:
        return "🔻"
    return "➖"


def build_strategy_table(rows: list[StrategyRow]) -> str:
    """Fixed-width fenced-ready table, grouped into buckets: STRATEGY | FLT | BKD | TOTAL.

    Flt = floating (unrealized), Bkd = booked (realized) — reuses ROLL-2's "Flt P&L (M)" /
    "Bkd P&L (I)" vocabulary (formatting-rules/stories.md) rather than inventing new terms
    for the same underlying values.

    Revised 2026-08-08 (v2, confirmed on-device):
    totals-first — each bucket's subtotal row (prefixed "> ", ALL CAPS "TOTAL" wording, never
    abbreviated) renders ABOVE its member rows, not below. The prefix is a plain ASCII ">", not
    "▶" — confirmed on-device 2026-08-08 that Telegram renders "▶" using its emoji-presentation
    glyph (auto-appended variation selector) even inside a fenced code block, making it
    double-width and breaking column alignment exactly like FMT-3 already warns emoji do inside
    build_leg_table. This applies to ANY Unicode symbol with an emoji-presentation variant, not
    just literal emoji characters — plain ASCII is the only fully safe choice inside a fence
    (new FMT-1e).

    Totals-first is a scan-speed trade-off, not a strict improvement over v1's totals-last: it
    optimizes for "which bucket needs attention" fast-scanning (a dashboard read), at the cost
    of the more familiar "components then sum" itemized-statement order ROLL-2's comparison
    table and most accounting statements use. Confirmed as the intended trade-off for THIS
    message specifically (a daily glance, not a reconciliation document) — do not generalize to
    other tables in this epic without asking. It also means the subtotal row doubles as the
    bucket's section label, so no separate "-- BUCKET --" header row is needed above it.

    "====" (double rule) separates the header from the first bucket; "----" (single rule)
    separates buckets from each other — two visual weights, not one, so the eye can distinguish
    "this is the whole table's start" from "this is just a bucket boundary."

    Buckets (see _BUCKETS): Track, IC, Overlay, CSP. Member row labels never repeat the bucket
    name (fixed 2026-08-08 — v1 had this inconsistent, see _DISPLAY_NAME's note). A strategy_id
    present in `rows` but not in any bucket raises — silently dropping a strategy from the
    summary is worse than a loud failure at message-build time.
    """
    by_id = {r.strategy_id: r for r in rows}
    bucketed_ids = {sid for _, ids in _BUCKETS for sid in ids}
    unassigned = set(by_id) - bucketed_ids
    if unassigned:
        raise ValueError(f"strategy_id(s) not assigned to any bucket: {sorted(unassigned)}")

    all_labels = [_DISPLAY_NAME[sid] for sid in bucketed_ids] + [
        f"> {name.upper()} TOTAL" for name, _ in _BUCKETS
    ]
    name_col = max(len("STRATEGY"), *(len(x) for x in all_labels))
    num_col = 9  # fits "+50,640" (7 chars) with 2 pad chars; matches confirmed target width

    header = (
        f"{'STRATEGY':<{name_col}}|{'FLT':>{num_col}} |{'BKD':>{num_col}} |{'TOTAL':>{num_col}}"
    )
    double_rule = f"{'=' * name_col}|{'=' * (num_col + 1)}|{'=' * (num_col + 1)}|{'=' * num_col}"
    single_rule = f"{'-' * name_col}|{'-' * (num_col + 1)}|{'-' * (num_col + 1)}|{'-' * num_col}"

    def _row(label: str, unrealized: Decimal, realized: Decimal) -> str:
        total = unrealized + realized
        return (
            f"{label:<{name_col}}|{_fmt_table_money(unrealized):>{num_col}} |"
            f"{_fmt_table_money(realized):>{num_col}} |{_fmt_table_money(total):>{num_col}}"
        )

    lines = [header, double_rule]
    for i, (bucket_name, ids) in enumerate(_BUCKETS):
        present = [by_id[sid] for sid in ids if sid in by_id]
        if not present:
            continue
        if i > 0:
            lines.append(single_rule)
        bucket_flt = sum((r.unrealized for r in present), Decimal("0"))
        bucket_bkd = sum((r.realized for r in present), Decimal("0"))
        lines.append(_row(f"> {bucket_name.upper()} TOTAL", bucket_flt, bucket_bkd))
        for r in present:
            lines.append(_row(f" {_DISPLAY_NAME[r.strategy_id]}", r.unrealized, r.realized))
    return "\n".join(lines)


def build_message(date_str: str, council_count: int, rows: list[StrategyRow]) -> str:
    """Pure function: sample data -> full MarkdownV2 message text.

    Revised 2026-08-08 (v2 layout, suggested as an enhancement over the totals-last v1):
    - Header stays a single line (no change).
    - Activities + Net P&L merged onto one line (was two) with a pnl_emoji() glance-indicator —
      the ONLY emoji in the message besides the header's 📝, and deliberately outside the fenced
      table (see pnl_emoji's docstring for why emoji can't safely go inside the table itself).
    - The "📊 Strategy Performance" section label is dropped — the fenced table follows directly,
      redundant given the table is self-evidently what it is.
    - #EOD_SUMMARY hashtag moves from the header line to its own line AFTER the closing fence,
      not before/inside it. Two reasons: (1) MarkdownV2 does not parse entities (including
      Telegram's auto-hashtag-detection) inside a fenced code block, so it could never have
      lived inside the table; (2) keeping it out of the header keeps that line shorter and
      lets the tag read as a standalone, tappable "file this message under" tag rather than
      competing with the date for attention on one line.
    """
    total_pnl = sum((r.total for r in rows), Decimal("0"))
    total_str = _fmt_table_money(total_pnl)
    # Net P&L line keeps the sole ₹ symbol in the whole message.
    net_str = f"{total_str[0]}₹{total_str[1:]}" if total_str[0] in "+-" else f"₹{total_str}"

    table = build_strategy_table(rows)

    header_line = escape_markdown(f"📝 NiftyShield Paper EOD | {date_str}")
    summary_line = escape_markdown(
        f"Activities: {council_count} | Net P&L: {net_str} {pnl_emoji(total_pnl)}"
    )
    # escape_markdown covers both '#' and '_' (both in MARKDOWNV2_RESERVED) — the backslash
    # is consumed at render time so Telegram's hashtag-entity scanner still sees a literal
    # "#EOD_SUMMARY" in the rendered text and makes it tappable. Confirmed working on-device
    # for this exact escaped-hashtag pattern already in FMT-1c, not re-verified from scratch.
    hashtag_line = escape_markdown(_MESSAGE_HASHTAG)

    return f"{header_line}\n{summary_line}\n```\n{table}\n```\n{hashtag_line}"


def _sample_rows() -> list[StrategyRow]:
    return [
        # Track
        StrategyRow("paper_nifty_futures", Decimal("-149.50"), Decimal("0.00")),
        StrategyRow("paper_nifty_proxy", Decimal("-2970.50"), Decimal("-3443.38")),
        StrategyRow("paper_nifty_spot", Decimal("50640.05"), Decimal("0.00")),
        # IC
        StrategyRow("paper_ic_nifty_v1_weekly", Decimal("0.00"), Decimal("2759.25")),
        StrategyRow("paper_ic_nifty_v1_monthly", Decimal("359.12"), Decimal("3486.44")),
        StrategyRow("paper_ic_nifty_v1_leaps", Decimal("4078.75"), Decimal("0.00")),
        # NOTE: yearly/V2-monthly figures below are placeholder scratch values, not real
        # portfolio data — no live paper position exists yet for these two as of 2026-08-08.
        # Flag this explicitly to whoever wires the real ROLL-6 implementation.
        StrategyRow("paper_ic_nifty_v1_yearly", Decimal("120.00"), Decimal("0.00")),
        StrategyRow("paper_ic_nifty_v2_monthly", Decimal("586.62"), Decimal("-1756.08")),
        # Overlay — placeholder scratch values, same caveat as above.
        StrategyRow("paper_collar_v1", Decimal("210.00"), Decimal("-85.50")),
        StrategyRow("paper_covered_call_v1", Decimal("0.00"), Decimal("640.00")),
        StrategyRow("paper_protective_put_v1", Decimal("-95.25"), Decimal("0.00")),
        # CSP
        StrategyRow("paper_csp_nifty_v1", Decimal("0.00"), Decimal("11024.00")),
    ]


async def main() -> None:
    msg = build_message("07 Aug 2026", 0, _sample_rows())
    print("--- rendered source (raw MarkdownV2, not what Telegram displays) ---")
    print(msg)
    print("--- end ---")

    try:
        import aiohttp

        from src.config import settings  # type: ignore

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
