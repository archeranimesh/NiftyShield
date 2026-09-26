"""Scratch: iterate the daily-snapshot waterfall Telegram message format.

Case: parse_mode NOT yet MarkdownV2 — `backbone/` (MD-1..MD-5) has not shipped
(search_graph("mdcode") / search_graph("escape_markdown") both returned 0 hits
in the graph on 2026-08-08). This message is also not one of the ROLL-1..4
tasks in strategy-rollout/tasks.md — it's the combined portfolio snapshot
(`src/portfolio/formatting._format_combined_summary`, waterfall/has_deltas
path, lines ~130-230), a candidate for a new ROLL-N once a target format is
confirmed here.

This script does NOT reproduce the real function's dataclass plumbing
(PortfolioSummary / DhanPortfolioSummary / NuvamaBondSummary / etc pulled
from live stores) — that requires DB + broker fixtures out of scope for a
formatting scratch. Instead `build_message(d)` re-implements the exact
waterfall formatting logic from `_format_combined_summary` against a plain
dict, seeded with the numbers from Animesh's pasted message (2026-08-07),
so layout changes can be iterated and eyeballed without touching real code.

`fmt_inr` is ported verbatim (Indian digit grouping, sign, width) from
src/utils/number_formatting.py so the alignment behavior matches production.

Known issue already surfaced in this session (do not treat as a bug to fix
in this script): "Derivatives" is a *day-delta* rollup, but its children
"Finideas P&L" / "Nuvama P&L" show *cumulative* P&L — inconsistent with the
Equity/Bonds siblings, whose children are day deltas. Preserved as-is here
so the reformatting iteration can decide how to resolve it (relabel vs.
recompute) rather than silently "fixing" it out from under the discussion.

Sends via real Telegram credentials from src.config.settings when run
directly, non-fatal on failure, surfaces Telegram's actual `description`
field on a 400 rather than letting `raise_for_status()` swallow it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date as _date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

import aiohttp

# Repo root = two levels up from scratch/this_file.py. Needed because running
# `python3 scratch/foo.py` puts scratch/ on sys.path, not the repo root, so
# `import src...` fails with "No module named 'src'" otherwise. Matches the
# sys.path fix used by scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings  # noqa: E402


# ── fmt_inr, ported verbatim from src/utils/number_formatting.py ──────────
def _group_indian(int_str: str) -> str:
    if len(int_str) <= 3:
        return int_str
    last3, rest = int_str[-3:], int_str[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return ",".join(parts) + "," + last3


def fmt_inr(
    value: Decimal | float | int,
    *,
    decimals: int = 0,
    sign: bool = False,
    width: int = 0,
) -> str:
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"fmt_inr: cannot convert {value!r} to Decimal") from exc

    negative = d < 0
    d_abs = abs(d)
    quant = Decimal(10) ** -decimals if decimals > 0 else Decimal(1)
    quantised = d_abs.quantize(quant)
    s = str(quantised)
    int_str, frac_str = s.split(".") if "." in s else (s, "")
    grouped = _group_indian(int_str)
    result = f"{grouped}.{frac_str}" if decimals > 0 else grouped
    if negative:
        result = "-" + result
    elif sign:
        result = "+" + result
    if width > 0:
        result = result.rjust(width)
    return result


# ── Sample data: Animesh's pasted 2026-08-07 message, reverse-engineered ──
SAMPLE = {
    "snap_date": "2026-08-07",
    "total_day_delta": Decimal("-17924"),
    "total_value": Decimal("12794372"),
    "total_pnl": Decimal("2830403"),
    "total_pnl_pct": Decimal("28.41"),
    "mf_available": True,
    "mf_day_delta": Decimal("-19985"),
    "etf_day_delta": Decimal("391"),
    "dhan_available": False,  # "[unavailable]" in Bonds + NOTE line
    "nuvama_available": True,
    "nuvama_bonds_value": Decimal("1"),  # >0 so the Nuvama Bonds line prints
    "nuvama_bonds_day_delta": Decimal("1279"),
    "options_pnl": Decimal("24804"),  # Finideas cumulative P&L (label says P&L, not delta)
    "options_day_delta": Decimal("391"),  # Derivatives *day* rollup — see docstring note
    "nuvama_options_available": True,
    "nuvama_options_net_pnl": Decimal("-1758"),
    "nuvama_options_total_unrealized_pnl": Decimal("-1758"),
    "nuvama_options_intraday_high": Decimal("-211"),
    "nuvama_options_intraday_low": Decimal("-3071"),
    "nuvama_options_total_realized_pnl_today": Decimal("0"),
    "nuvama_options_monthly_realized_pnl": Decimal("-7274"),
    "nuvama_options_cumulative_realized_pnl": Decimal("72929"),
    "finrakshak_day_delta": Decimal("0"),
    # Dhan intraday block (always shown today, all-zero)
    "dhan_intraday_today_pnl": Decimal("0"),
    "dhan_intraday_today_cost": Decimal("0"),
    "dhan_intraday_today_chg": Decimal("0"),
    "dhan_intraday_today_brk": Decimal("0"),
    "dhan_intraday_month_pnl": Decimal("0"),
    "dhan_intraday_month_cost": Decimal("0"),
    "dhan_intraday_month_chg": Decimal("0"),
    "dhan_intraday_month_brk": Decimal("0"),
    "dhan_intraday_positions": 0,
    # Equity's day-delta as originally pasted (-19,595) is $1 off from
    # mf_day_delta + etf_day_delta (-19,985 + 391 = -19,594) — a rounding
    # drift already present in the original message's own more-precise
    # sub-total, not something introduced by this reverse-engineering.
    # Kept as an explicit override so v3 matches the confirmed target
    # string exactly rather than silently drifting by ₹1.
    "equity_day_delta_display": Decimal("-19595"),
}


def build_message(d: dict) -> str:
    """Reproduce the current (as-shipped) waterfall message, for baseline diffing.

    Mirrors _format_combined_summary's has_deltas=True branch line-for-line
    against SAMPLE's shape. This is the "from" message for the workshop —
    edit/replace this function (or add build_message_v2 etc.) to iterate the
    "to" target, keep this one intact as the confirmed-current baseline.
    """
    status_emoji = "🟢" if d["total_day_delta"] >= 0 else "🔴"
    SEP = "  " + "─" * 34
    lines: list[str] = [f"{status_emoji} NiftyShield | {d['snap_date']}"]

    eq_day = d["mf_day_delta"] + d["etf_day_delta"]
    bd_day = d["nuvama_bonds_day_delta"]
    options_day = d["options_day_delta"]

    lines += ["", f"📊 Today: {fmt_inr(d['total_day_delta'], sign=True)}", ""]
    lines.append(
        f"  {'Equity':<14} {fmt_inr(eq_day, sign=True, width=12)}"
        f"  {'▲' if eq_day >= 0 else '▼'}  71%"
    )
    lines.append(f"  {'├ MF':<14} {fmt_inr(d['mf_day_delta'], sign=True, width=12)}")
    lines.append(f"  {'├ ETF':<14} {fmt_inr(d['etf_day_delta'], sign=True, width=12)}")
    lines.append(
        f"  {'Bonds':<14} {fmt_inr(bd_day, sign=True, width=12)}"
        f"  {'▲' if bd_day >= 0 else '▼'}  28%"
    )
    lines.append(
        f"  {'├ Nuvama Bonds':<14} {fmt_inr(d['nuvama_bonds_day_delta'], sign=True, width=12)}"
    )
    lines.append("  └ Dhan Bonds          [unavailable]")
    lines.append(
        f"  {'Derivatives':<14} {fmt_inr(options_day, sign=True, width=12)}"
        f"  {'▲' if options_day >= 0 else '▼'}"
    )
    lines.append(f"  {'├ Finideas P&L':<14} {fmt_inr(d['options_pnl'], sign=True, width=12)}")
    lines.append(
        f"  {'└ Nuvama P&L':<14} {fmt_inr(d['nuvama_options_net_pnl'], sign=True, width=12)}"
    )
    lines.append(SEP)
    lines.append(
        f"  {'Net':<14} {fmt_inr(d['total_day_delta'], sign=True, width=12)}  {status_emoji}"
    )

    net = d["mf_day_delta"] + d["finrakshak_day_delta"]
    verdict = "✅ Protected" if net >= 0 else "⚠️  Exposed"
    lines += [
        "",
        "🛡 Hedge (FinRakshak)",
        f"  MF Δ        {fmt_inr(d['mf_day_delta'], sign=True, width=14)}",
        f"  Hedge Δ     {fmt_inr(d['finrakshak_day_delta'], sign=True, width=14)}",
        SEP,
        f"  Net         {fmt_inr(net, sign=True, width=14)}  {verdict}",
    ]

    lines.append("")
    lines.append(
        f"  Nuvama M2M P&L      "
        f"{fmt_inr(d['nuvama_options_total_unrealized_pnl'], sign=True, width=14)}"
    )
    hl_str = (
        f"{fmt_inr(d['nuvama_options_intraday_high'], sign=True)} / "
        f"{fmt_inr(d['nuvama_options_intraday_low'], sign=True)}"
    )
    lines.append(f"   ├ M2M High/Low   {hl_str:>16}")
    lines.append(
        f"  Today P&L           "
        f"{fmt_inr(d['nuvama_options_total_realized_pnl_today'], sign=True, width=14)}"
    )
    lines.append(
        f"  Month P&L           "
        f"{fmt_inr(d['nuvama_options_monthly_realized_pnl'], sign=True, width=14)}"
    )
    n_realized = (
        d["nuvama_options_total_realized_pnl_today"] + d["nuvama_options_cumulative_realized_pnl"]
    )
    lines.append(f"  Nuvama Realized     {fmt_inr(n_realized, sign=True, width=14)}")

    lines += [
        "",
        f"💰 Total: ₹{fmt_inr(d['total_value'])}  |  "
        f"P&L {fmt_inr(d['total_pnl'], sign=True)} ({d['total_pnl_pct']:+}%) all-time",
        "  NOTE: Dhan unavailable — Dhan values excluded from total",
    ]

    # ── Dhan Options (Intraday) — separate always-appended block ──
    lines += [
        "",
        "📊 Dhan Options (Intraday)",
        f"Today P&L:    {fmt_inr(d['dhan_intraday_today_pnl'], sign=True)}  gross",
        f"Today Cost:   {fmt_inr(d['dhan_intraday_today_cost'])}  "
        f"(chg: {fmt_inr(d['dhan_intraday_today_chg'])}  brk: {fmt_inr(d['dhan_intraday_today_brk'])})",
        f"Today Net:    {fmt_inr(d['dhan_intraday_today_pnl'], sign=True)}",
        f"Month P&L:    {fmt_inr(d['dhan_intraday_month_pnl'], sign=True)}  gross",
        f"Month Cost:   {fmt_inr(d['dhan_intraday_month_cost'])}  "
        f"(chg: {fmt_inr(d['dhan_intraday_month_chg'])}  brk: {fmt_inr(d['dhan_intraday_month_brk'])})",
        f"Month Net:    {fmt_inr(d['dhan_intraday_month_pnl'], sign=True)}",
        f"Positions:   {d['dhan_intraday_positions']}",
    ]

    return "\n".join(lines)


# ── v2 proposal: MarkdownV2, fixes the issues flagged earlier this session ──
#
# Backbone (mdcode()/escape_markdown()) still hasn't shipped (see module
# docstring) — inlined here matching MD-1's spec, same pattern as
# scratch/2026-08-07_ic_eod_audit_v2_telegram_format.py, so the eventual
# real port is verbatim, not a rewrite.
#
# What changed vs. build_message() (v1, kept intact above as the baseline):
#   1. Derivatives' children (Finideas/Nuvama P&L) are cumulative, not day
#      deltas, unlike Equity/Bonds' children — v1 left this unlabeled and
#      misleading. v2 tags both explicitly "(cum)" and the parent "(day Δ)"
#      instead of silently recomputing them into fake day-deltas we don't
#      actually have broken out for Nuvama options.
#   2. Dropped the undefined ▲/▼ + bare percentage decorations (71%, 28%) —
#      no legend anywhere for what they mean; a decoration nobody can
#      interpret is worse than none.
#   3. Hedge section no longer repeats MF Δ (already shown once under
#      Equity → MF) — only Hedge Δ and Net exposure, which is the actually
#      new information in that section.
#   4. Money figures live inside fenced ``` code blocks — Telegram doesn't
#      parse entities inside code spans/blocks, so none of the reserved
#      MarkdownV2 punctuation in ₹ figures (`.`, `-`, `,`) needs per-value
#      escaping, matching FMT-3's leg-table rationale. Only the handful of
#      bold headers/labels outside the fences need escape_markdown().
#   5. Dhan Options (Intraday) block is omitted entirely when there are zero
#      positions, instead of always appending an all-zero block.
MARKDOWNV2_RESERVED = "_*[]()~`>#+-=|{}.!"


def escape_markdown(text: str) -> str:
    """Backslash-escape MarkdownV2 reserved characters in free text."""
    return "".join(f"\\{ch}" if ch in MARKDOWNV2_RESERVED else ch for ch in text)


def mdcode(value: str) -> str:
    """Wrap a dynamic identifier-like value as an inline code span."""
    if "`" in value:
        return escape_markdown(value)
    return f"`{value}`"


def build_message_v2(d: dict) -> str:
    """Proposed optimized format — MarkdownV2, addresses issues 1-5 above.

    Structure: bold header, bold Today line, fenced waterfall table, bold
    Hedge header + fenced Hedge table, bold Nuvama M2M header + fenced
    table (only if nuvama_options_available), bold Total line + NOTE(s)
    directly beneath it, Dhan Options block only when positions > 0.
    """
    status_emoji = "🔴" if d["total_day_delta"] < 0 else "🟢"
    W = 10  # column width inside fenced tables

    eq_day = d["mf_day_delta"] + d["etf_day_delta"]
    bd_day = d["nuvama_bonds_day_delta"]
    options_day = d["options_day_delta"]

    lines: list[str] = [
        f"{status_emoji} *NiftyShield* \\| {escape_markdown(d['snap_date'])}",
        "",
        f"📊 *Today:* {escape_markdown(fmt_inr(d['total_day_delta'], sign=True))}",
        "",
        "```",
        f"Equity         {fmt_inr(eq_day, sign=True, width=W)}",
        f" MF            {fmt_inr(d['mf_day_delta'], sign=True, width=W)}",
        f" ETF           {fmt_inr(d['etf_day_delta'], sign=True, width=W)}",
        f"Bonds          {fmt_inr(bd_day, sign=True, width=W)}",
        f" Nuvama Bonds  {fmt_inr(d['nuvama_bonds_day_delta'], sign=True, width=W)}",
        f" Dhan Bonds    {'n/a' if not d['dhan_available'] else fmt_inr(Decimal('0'), sign=True, width=W):>{W}}",
        f"Derivatives    {fmt_inr(options_day, sign=True, width=W)}  (day Δ)",
        f" Finideas P&L  {fmt_inr(d['options_pnl'], sign=True, width=W)}  (cum)",
        f" Nuvama P&L    {fmt_inr(d['nuvama_options_net_pnl'], sign=True, width=W)}  (cum)",
        "-" * 30,
        f"Net            {fmt_inr(d['total_day_delta'], sign=True, width=W)}",
        "```",
    ]

    net = d["mf_day_delta"] + d["finrakshak_day_delta"]
    verdict = "Protected" if net >= 0 else "Exposed"
    lines += [
        "",
        "\U0001f6e1 *Hedge \\(FinRakshak\\)*",
        "```",
        f"Hedge Δ         {fmt_inr(d['finrakshak_day_delta'], sign=True, width=W)}",
        "-" * 30,
        f"Net exposure   {fmt_inr(net, sign=True, width=W)}  {verdict}",
        "```",
    ]

    if d["nuvama_options_available"]:
        hl_str = (
            f"{fmt_inr(d['nuvama_options_intraday_high'], sign=True)} / "
            f"{fmt_inr(d['nuvama_options_intraday_low'], sign=True)}"
        )
        n_realized = (
            d["nuvama_options_total_realized_pnl_today"]
            + d["nuvama_options_cumulative_realized_pnl"]
        )
        lines += [
            "",
            "*Nuvama Options M2M*",
            "```",
            f"M2M P&L        {fmt_inr(d['nuvama_options_total_unrealized_pnl'], sign=True, width=W)}",
            f" Hi/Lo         {hl_str:>{W}}",
            f"Today realized {fmt_inr(d['nuvama_options_total_realized_pnl_today'], sign=True, width=W)}",
            f"Month realized {fmt_inr(d['nuvama_options_monthly_realized_pnl'], sign=True, width=W)}",
            f"Cum realized   {fmt_inr(n_realized, sign=True, width=W)}",
            "```",
        ]

    lines += [
        "",
        f"\U0001f4b0 *Total:* ₹{escape_markdown(fmt_inr(d['total_value']))}  \\| "
        f"P&L {escape_markdown(fmt_inr(d['total_pnl'], sign=True))} "
        f"\\({escape_markdown(str(d['total_pnl_pct']))}%\\) all\\-time",
    ]
    if not d["dhan_available"]:
        lines.append(escape_markdown("  NOTE: Dhan unavailable — Dhan values excluded from total"))

    if d["dhan_intraday_positions"] > 0:
        lines += [
            "",
            "\U0001f4ca *Dhan Options \\(Intraday\\)*",
            "```",
            f"Today P&L   {fmt_inr(d['dhan_intraday_today_pnl'], sign=True, width=W)}",
            f"Month P&L   {fmt_inr(d['dhan_intraday_month_pnl'], sign=True, width=W)}",
            f"Positions   {d['dhan_intraday_positions']:>{W}}",
            "```",
        ]

    return "\n".join(lines)


# ── v3: Animesh's exact compact spec (2026-08-08) ──────────────────────────
#
# Plain text, no MarkdownV2 — this format doesn't need bold/tables, so there's
# no reason to take on MarkdownV2's escaping burden for it. Column alignment
# is fixed-width label-field-then-right-justified-value, ported directly from
# the literal example: label padded to 8 chars + ":" + " " + value right-
# justified to 7 chars (matches "Equity  : -19,595" / "Bonds   :  +1,279").
#
# Semantic note (flagging once, implemented as specified): "Derivs" in the
# Sectors block is a CUMULATIVE net (Finideas +24,804 cum P&L + Nuvama
# -1,758 cum P&L = +23,046), not a day-delta like its Equity/Bonds siblings.
# That's a real change in what the row means row-to-row within the same
# block — arguably the more useful number for an options book (running P&L
# vs. one day's blip on a position that isn't priced the same way daily),
# but worth being deliberate about, not implicit.


def _signed_or_zero(value: Decimal) -> str:
    """fmt_inr with sign=True, except a literal zero prints bare '0'."""
    return "0" if value == 0 else fmt_inr(value, sign=True)


def _fmt_k(value: Decimal) -> str:
    """Sign + value; abbreviates |value| >= 1000 to nearest thousand + 'k'.

    -211 -> "-211" (below threshold, full precision).
    -3071 -> "-3k" (rounds to nearest 1000, half-up).
    """
    if abs(value) >= 1000:
        k = (value / Decimal(1000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        sign = "+" if k >= 0 else ""
        return f"{sign}{int(k)}k"
    return fmt_inr(value, sign=True)


def build_message_v3(d: dict) -> str:
    """Compact plain-text format, confirmed against Animesh's literal spec
    (2026-08-08). No MarkdownV2 — see module note above for why.
    """
    status_emoji = "🔴" if d["total_day_delta"] < 0 else "🟢"
    snap_date = _date.fromisoformat(d["snap_date"]).strftime("%d %b %Y")

    def row(label: str, value: str) -> str:
        return f"{label:<8}: {value:>7}"

    lines = [
        f"{status_emoji} NiftyShield | {snap_date}",
        row("AUM", f"₹{fmt_inr(d['total_value'])}"),
        row("All-Time", f"{fmt_inr(d['total_pnl'], sign=True)} ({d['total_pnl_pct']:+.1f}%)"),
        row("Net Dly", fmt_inr(d["total_day_delta"], sign=True)),
        "📊 Sectors",
        row("Equity", fmt_inr(d["equity_day_delta_display"], sign=True)),
        row("Bonds", fmt_inr(d["nuvama_bonds_day_delta"], sign=True)),
        row("Derivs", fmt_inr(d["options_pnl"] + d["nuvama_options_net_pnl"], sign=True)),
    ]

    hedge_net = d["mf_day_delta"] + d["finrakshak_day_delta"]
    hedge_icon = "⚠️" if hedge_net < 0 else "✅"
    hedge_word = "EXPOSED" if hedge_net < 0 else "PROTECTED"
    lines += [
        f"🛡️ Hedge: {hedge_icon} {hedge_word}",
        row("MF Δ", fmt_inr(d["mf_day_delta"], sign=True)),
        row("Hedge Δ", _signed_or_zero(d["finrakshak_day_delta"])),
    ]

    if d["nuvama_options_available"]:
        hl_str = (
            f"{fmt_inr(d['nuvama_options_intraday_high'], sign=True)} / "
            f"{_fmt_k(d['nuvama_options_intraday_low'])}"
        )
        n_realized = (
            d["nuvama_options_total_realized_pnl_today"]
            + d["nuvama_options_cumulative_realized_pnl"]
        )
        # Note: unlike the AUM/Sectors/Hedge blocks above, these three rows
        # are NOT right-justified to a fixed value width (row()) — confirmed
        # against the literal spec, "Month   : -7,274" has a single space,
        # not padded to align with "Realized: +72,929"'s 7-char value.
        lines += [
            "📉 Nuvama M2M",
            f"{'Today':<8}: "
            f"{fmt_inr(d['nuvama_options_total_unrealized_pnl'], sign=True)} (H/L: {hl_str})",
            f"{'Month':<8}: {fmt_inr(d['nuvama_options_monthly_realized_pnl'], sign=True)}",
            f"{'Realized':<8}: {fmt_inr(n_realized, sign=True)}",
        ]

    footer_parts = []
    if not d["dhan_available"]:
        footer_parts.append("Dhan API offline.")
    if d["dhan_intraday_positions"] == 0:
        footer_parts.append("Intraday Options flat.")
    if footer_parts:
        lines.append(f"📌 {' '.join(footer_parts)}")

    return "\n".join(lines)


async def send_markdown_v2(bot_token: str, chat_id: str, message: str) -> bool:
    """Send with parse_mode=MarkdownV2 — for build_message_v2() only."""
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


async def send_plain(bot_token: str, chat_id: str, message: str) -> bool:
    """Send with no parse_mode — this message is still plain text in prod
    (backbone/MarkdownV2 migration hasn't shipped for it, see module
    docstring), matching what _format_combined_summary's real caller does
    today via TelegramNotifier.send().

    Reads the JSON body's "description" field on a non-ok response before
    deciding pass/fail — raise_for_status()-first swallows that field and
    cost a full debugging round-trip in the original IC EOD scratch session
    (2026-08-07); same trap applies here even without parse_mode involved.
    """
    payload = {"chat_id": chat_id, "text": message}
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
        description="Daily-snapshot waterfall Telegram message format probe."
    )
    parser.add_argument(
        "--version",
        default="v1",
        choices=["v1", "v2", "v3"],
        help="v1 = current shipped plain-text format (baseline). "
        "v2 = fenced-table MarkdownV2 proposal. "
        "v3 = compact plain-text format per Animesh's 2026-08-08 spec. "
        "(default: v1)",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send to Telegram (default: print only, never sends). "
        "Requires TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID in the environment.",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    builders = {"v1": build_message, "v2": build_message_v2, "v3": build_message_v3}
    text = builders[args.version](SAMPLE)
    print(f"--- version: {args.version} ---")
    print(text)
    print(f"\n--- {len(text)} chars ---")
    if args.version == "v2":
        print(
            "\n(Note: printed text above is raw MarkdownV2 source — asterisks/"
            "backslashes are literal here. Check the actual rendering on-device "
            "after sending, not this console output.)"
        )

    if not args.send:
        print("\n(--send not passed — nothing sent. Pass --send to actually post to Telegram.)")
        return

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print(
            "\n!! TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in environment — "
            "cannot send. Aborting without sending anything. Check .env exists at "
            "repo root and both keys are present (src/config.py's Settings loads "
            "it automatically; a fresh Settings() re-read is what build_notifier() "
            "does, but the module-level `settings` singleton imported above is "
            "what the reference IC scratch script uses and is checked here to "
            "match it)."
        )
        return

    if args.version == "v2":
        ok = await send_markdown_v2(settings.telegram_bot_token, settings.telegram_chat_id, text)
        print(f"\nsend_markdown_v2() returned {ok}")
    else:
        ok = await send_plain(settings.telegram_bot_token, settings.telegram_chat_id, text)
        print(f"\nsend_plain() returned {ok}")
    if not ok:
        print("!! send failed — check logs / credentials before retrying")


if __name__ == "__main__":
    asyncio.run(main())
