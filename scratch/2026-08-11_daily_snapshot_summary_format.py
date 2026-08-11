"""Scratch: iterate the Daily Portfolio Snapshot Telegram message format.

Item 9 in `docs/plan/telegram-markdown-migration/TODO.md`'s "Confirmed missing" queue —
`src/portfolio/formatting._format_combined_summary` (called from
`scripts/portfolio/daily_snapshot.py:739`, `_async_main`) PLUS the separately-appended
`format_options_section` (`src/dhan/positions.py:287`) — both land in the same Telegram send
(`summary_text = summary_text + "\\n\\n" + dhan_options_section`, daily_snapshot.py:723) so both
are in scope for this pass, even though they're two different source functions.

Two structurally distinct `_format_combined_summary` layouts, gated on
`has_deltas = summary.total_day_delta is not None`:

  - **Waterfall** (has_deltas=True, ships daily once a prior snapshot exists): header ->
    today's-change waterfall by segment (Equity/Bonds/Derivatives with per-source children,
    ▲/▼ + % decorators on Equity/Bonds) -> Hedge (FinRakshak) block, including the Nuvama M2M
    sub-block (M2M P&L, M2M High/Low, Nifty High/Low, Today P&L, Month P&L, Nuvama Realized) ->
    context line (total value + all-time P&L).
  - **Fallback** (has_deltas=False, first-run-only / after a DB wipe): header ->
    Equity/Bonds/Derivatives/Total sections showing absolute values + P&L%, no day-over-day
    deltas.

`backbone/` (MD-1..MD-5) status as of this session: NOT shipped. This script inlines local
copies of `escape_markdown`/`mdcode` matching MD-1's spec, same as every prior scratch here.

**Design decisions confirmed with Animesh, 2026-08-11 (this session), superseding the earlier,
unfinished `scratch/2026-08-08_daily_snapshot_waterfall_format.py` v1/v2 drafts** (never
written back — item 9 was still unchecked when this session started):

1. **Both layouts in this one pass** (waterfall AND fallback), not waterfall-only.
2. **Drop fixed-width column alignment / box-drawing (`├ └ ▲ ▼ ─ ═`) — redesign as plain
   kv-lines with a hierarchy marker.** MarkdownV2 plain text is proportional-width and strips
   leading whitespace outside a fenced code block — confirmed broken on-device this session
   (v1 of this script used 2-space indents; the live send flattened Equity's MF/ETF/Dhan
   Equity children into visual siblings). Fixed in v2 by replacing leading-whitespace indent
   with explicit non-whitespace prefixes: `- ` for depth-1 children, `-- ` for depth-2
   (nested P&L-under-a-value lines in the fallback layout) — same dash convention already used
   elsewhere in this epic (ROLL-9/13), no leading whitespace anywhere so nothing can be
   stripped. The alternative (wrap the body in a fenced code block, ROLL-6-style) was
   considered and rejected: a code block can't carry the header's status emoji or any bold
   emphasis, and this message's real content is a list of labeled figures, not a table someone
   needs to eyeball column-by-column.
3. The ▲/▼ + `{pct}%` decorators on Equity/Bonds ARE real production content (confirmed by
   reading the actual current-baseline message Animesh pasted, 2026-08-11) — v1 of this script
   dropped them without asking (mistakenly reused a note from the abandoned 2026-08-08 draft
   that argued for dropping them as "undefined decorations"; that critique doesn't apply once
   they're confirmed as the real shipped content, not a scratch invention). v2 restores them.
4. **Live send** — this script sends real test messages via `src.config.settings` credentials.
   Note: this Cowork cloud session's network egress to `api.telegram.org` is blocked outright
   (connection refused) and the linked device's `.venv` is a broken symlink (Mac-only Anaconda
   path, unusable from the Linux device-bridge VM) — confirmed 2026-08-11, same class of
   limitation as ROLL-11/12's "no working venv" note, different cause. Live send only works
   run directly on Animesh's machine (`.venv/bin/python scratch/...  --send`), not from either
   session side.

Known pre-existing issue (still true, NOT fixed here — flagging for the real ROLL-16 port): in
the waterfall layout, "Derivatives" is a *day-delta* rollup but its children "Finideas P&L" /
"Nuvama P&L" are *cumulative* P&L, unlike the Equity/Bonds siblings whose children are day
deltas. Labeled "(cum)" here so it's at least visible, not silently recomputed into fake
day-deltas that don't exist for Nuvama options.

Run: python scratch/2026-08-11_daily_snapshot_summary_format.py [--send]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402

# ── Inline copies of MD-1's helpers (backbone/ not shipped yet) ──

MARKDOWNV2_RESERVED = "_*[]()~`>#+-=|{}.!"


def escape_markdown(text: str) -> str:
    """Backslash-escape MarkdownV2 reserved characters in free text."""
    return "".join(f"\\{ch}" if ch in MARKDOWNV2_RESERVED else ch for ch in text)


def mdcode(value: str) -> str:
    """Wrap a dynamic identifier-like value as an inline code span."""
    if "`" in value:
        return escape_markdown(value)
    return f"`{value}`"


# ── Ported from src/utils/number_formatting.py (verbatim behavior, not import — this script
#    deliberately stays DB/broker-fixture-free, matching every prior scratch here). ──


def fmt_inr(value: Decimal, *, sign: bool = False) -> str:
    """Indian digit grouping (Lakhs/Crores), optional leading '+' on positive values."""
    d = value
    neg = d < 0
    d = abs(d)
    int_part = str(int(d.to_integral_value(rounding="ROUND_HALF_UP")))
    if len(int_part) > 3:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        int_part = ",".join(groups) + "," + last3
    out = f"₹{int_part}"
    if neg:
        return f"-{out}"
    if sign:
        return f"+{out}"
    return out


# ── Sample data — flat Decimals/bools standing in for the real nested dataclasses
#    (PortfolioSummary / DhanPortfolioSummary / NuvamaBondSummary / NuvamaOptionsSummary /
#    DhanOptionsSummary). Values below mirror the actual baseline message Animesh pasted
#    2026-08-11 (waterfall path), not arbitrary placeholders. ──


@dataclass
class Sample:
    date_str: str = "2026-08-11"
    has_deltas: bool = True

    total_value: Decimal = Decimal("12807999")
    total_pnl: Decimal = Decimal("2847462")
    total_pnl_pct: Decimal = Decimal("28.58")
    total_invested: Decimal = Decimal("9960537")
    total_day_delta: Decimal | None = Decimal("20776")

    mf_available: bool = True
    mf_day_delta: Decimal | None = Decimal("11338")
    mf_value: Decimal = Decimal("8000000")
    mf_pnl: Decimal = Decimal("300000")
    mf_pnl_pct: Decimal | None = Decimal("3.9")

    etf_day_delta: Decimal | None = Decimal("-121")
    etf_value: Decimal = Decimal("3000000")
    etf_basis: Decimal = Decimal("2900000")

    dhan_available: bool = False  # matches baseline: "Dhan unavailable" NOTE line present
    dhan_equity_value: Decimal = Decimal("0")
    dhan_equity_day_delta: Decimal | None = Decimal("0")
    dhan_equity_pnl: Decimal = Decimal("0")
    dhan_equity_pnl_pct: Decimal | None = None
    dhan_bond_value: Decimal = Decimal("0")
    dhan_bond_day_delta: Decimal | None = Decimal("0")
    dhan_bond_pnl: Decimal = Decimal("0")
    dhan_bond_pnl_pct: Decimal | None = None

    nuvama_available: bool = True
    nuvama_bonds_value: Decimal = Decimal("2500000")
    nuvama_bonds_day_delta: Decimal | None = Decimal("9680")
    nuvama_bonds_pnl: Decimal = Decimal("80000")
    nuvama_bonds_pnl_pct: Decimal | None = Decimal("3.2")

    options_day_delta: Decimal | None = Decimal("-121")
    options_pnl: Decimal = Decimal("24618")  # Finideas — cumulative, see docstring note

    nuvama_options_available: bool = True
    nuvama_options_net_pnl: Decimal = Decimal("1674")  # cumulative
    nuvama_m2m_pnl: Decimal = Decimal("296")
    nuvama_m2m_high: Decimal | None = Decimal("1908")
    nuvama_m2m_low: Decimal | None = Decimal("-451")
    nuvama_nifty_high: Decimal | None = None  # absent in baseline paste — omitted when None
    nuvama_nifty_low: Decimal | None = None
    nuvama_today_pnl: Decimal = Decimal("1378")
    nuvama_month_pnl: Decimal = Decimal("-5896")
    nuvama_realized: Decimal = Decimal("74307")

    finrakshak_day_delta: Decimal | None = Decimal("0")

    # Dhan Options (Intraday) — format_options_section, src/dhan/positions.py:287
    dhan_opts_realized: Decimal = Decimal("0")
    dhan_opts_charges: Decimal = Decimal("0")
    dhan_opts_brokerage: Decimal = Decimal("0")
    dhan_opts_unrealized: Decimal = Decimal("0")
    dhan_opts_position_count: int = 0
    dhan_opts_month_pnl: Decimal = Decimal("0")
    dhan_opts_month_charges: Decimal = Decimal("0")
    dhan_opts_month_brokerage: Decimal = Decimal("0")


def _pct_arrow(pct: int) -> str:
    return "up" if pct >= 0 else "down"  # ASCII-only, see FMT-1e (▲/▼ risk unverified here)


def build_message(d: Sample) -> str:
    """Pure function: Sample -> full MarkdownV2 message text (kv-line + dash-hierarchy layout)."""
    status_emoji = "🟢" if (d.total_day_delta if d.has_deltas else d.total_pnl) >= 0 else "🔴"
    lines: list[str] = [f"{status_emoji} NiftyShield | {d.date_str}", ""]

    if d.has_deltas:
        assert d.total_day_delta is not None
        eq_day = (d.mf_day_delta or Decimal("0")) + (d.etf_day_delta or Decimal("0"))
        if d.dhan_available:
            eq_day += d.dhan_equity_day_delta or Decimal("0")
        bd_day = Decimal("0")
        if d.dhan_available:
            bd_day += d.dhan_bond_day_delta or Decimal("0")
        if d.nuvama_available:
            bd_day += d.nuvama_bonds_day_delta or Decimal("0")

        mf_value = d.mf_value if d.mf_available else Decimal("0")
        eq_subtotal = (
            mf_value + d.etf_value + (d.dhan_equity_value if d.dhan_available else Decimal("0"))
        )
        bonds_subtotal = (d.dhan_bond_value if d.dhan_available else Decimal("0")) + (
            d.nuvama_bonds_value if d.nuvama_available else Decimal("0")
        )
        equity_pct = int(eq_subtotal / d.total_value * 100) if d.total_value else 0
        bonds_pct = int(bonds_subtotal / d.total_value * 100) if d.total_value else 0

        lines.append(f"Today: {fmt_inr(d.total_day_delta, sign=True)}")
        lines.append("")
        lines.append(f"Equity: {fmt_inr(eq_day, sign=True)} ({_pct_arrow(eq_day)}, {equity_pct}%)")
        lines.append(
            f"- MF: {fmt_inr(d.mf_day_delta, sign=True)}"
            if d.mf_available and d.mf_day_delta is not None
            else "- MF: [failed]"
        )
        lines.append(f"- ETF: {fmt_inr(d.etf_day_delta or Decimal('0'), sign=True)}")
        if d.dhan_available and d.dhan_equity_value > 0:
            lines.append(
                f"- Dhan Equity: {fmt_inr(d.dhan_equity_day_delta or Decimal('0'), sign=True)}"
            )
        lines.append(f"Bonds: {fmt_inr(bd_day, sign=True)} ({_pct_arrow(bd_day)}, {bonds_pct}%)")
        if d.nuvama_available and d.nuvama_bonds_value > 0:
            lines.append(
                f"- Nuvama Bonds: {fmt_inr(d.nuvama_bonds_day_delta or Decimal('0'), sign=True)}"
            )
        elif not d.nuvama_available:
            lines.append("- Nuvama Bonds: [unavailable]")
        if d.dhan_available and d.dhan_bond_value > 0:
            lines.append(
                f"- Dhan Bonds: {fmt_inr(d.dhan_bond_day_delta or Decimal('0'), sign=True)}"
            )
        elif not d.dhan_available:
            lines.append("- Dhan Bonds: [unavailable]")
        options_day = d.options_day_delta or Decimal("0")
        lines.append(f"Derivatives: {fmt_inr(options_day, sign=True)} ({_pct_arrow(options_day)})")
        lines.append(f"- Finideas P&L (cum): {fmt_inr(d.options_pnl, sign=True)}")
        if d.nuvama_options_available:
            lines.append(f"- Nuvama P&L (cum): {fmt_inr(d.nuvama_options_net_pnl, sign=True)}")
        else:
            lines.append("- Nuvama P&L (cum): [unavailable]")
        lines.append(f"Net: {fmt_inr(d.total_day_delta, sign=True)} {status_emoji}")

        if d.mf_day_delta is not None and d.finrakshak_day_delta is not None:
            net = d.mf_day_delta + d.finrakshak_day_delta
            verdict = "Protected ✅" if net >= 0 else "Exposed ⚠️"
            lines += [
                "",
                "Hedge (FinRakshak)",
                f"- MF Δ: {fmt_inr(d.mf_day_delta, sign=True)}",
                f"- Hedge Δ: {fmt_inr(d.finrakshak_day_delta, sign=True)}",
                f"- Net: {fmt_inr(net, sign=True)} — {verdict}",
            ]
            if d.nuvama_options_available:
                lines.append("")
                lines.append(f"Nuvama M2M P&L: {fmt_inr(d.nuvama_m2m_pnl, sign=True)}")
                if d.nuvama_m2m_high is not None and d.nuvama_m2m_low is not None:
                    lines.append(
                        f"- M2M High/Low: {fmt_inr(d.nuvama_m2m_high, sign=True)} / "
                        f"{fmt_inr(d.nuvama_m2m_low, sign=True)}"
                    )
                if d.nuvama_nifty_high is not None and d.nuvama_nifty_low is not None:
                    lines.append(
                        f"- Nifty High/Low: {d.nuvama_nifty_high:,.0f} / {d.nuvama_nifty_low:,.0f}"
                    )
                lines.append(f"- Today P&L: {fmt_inr(d.nuvama_today_pnl, sign=True)}")
                lines.append(f"- Month P&L: {fmt_inr(d.nuvama_month_pnl, sign=True)}")
                lines.append(f"- Nuvama Realized: {fmt_inr(d.nuvama_realized, sign=True)}")

        lines += [
            "",
            f"Total: {fmt_inr(d.total_value)} | P&L {fmt_inr(d.total_pnl, sign=True)} "
            f"({d.total_pnl_pct:+}%) all-time",
        ]
        if not d.mf_available:
            lines.append("- NOTE: MF fetch failed — MF value excluded from total")
        if not d.dhan_available:
            lines.append("- NOTE: Dhan unavailable — Dhan values excluded from total")
        if not d.nuvama_available:
            lines.append("- NOTE: Nuvama unavailable — Nuvama bonds excluded from total")

    else:
        eq_subtotal = d.mf_value + d.etf_value
        if d.dhan_available:
            eq_subtotal += d.dhan_equity_value
        bonds_subtotal = Decimal("0")
        if d.dhan_available:
            bonds_subtotal += d.dhan_bond_value
        if d.nuvama_available:
            bonds_subtotal += d.nuvama_bonds_value

        lines.append("Equity")
        if d.mf_available:
            lines.append(f"- MF: {fmt_inr(d.mf_value)}")
            pct = f" ({d.mf_pnl_pct:+}%)" if d.mf_pnl_pct is not None else ""
            lines.append(f"-- P&L: {fmt_inr(d.mf_pnl, sign=True)}{pct}")
        else:
            lines.append("- MF: [failed]")
        lines.append(f"- Finideas ETF: {fmt_inr(d.etf_value)} (basis {fmt_inr(d.etf_basis)})")
        if d.dhan_available and d.dhan_equity_value > 0:
            lines.append(f"- Dhan Equity: {fmt_inr(d.dhan_equity_value)}")
            pct = f" ({d.dhan_equity_pnl_pct:+}%)" if d.dhan_equity_pnl_pct is not None else ""
            lines.append(f"-- P&L: {fmt_inr(d.dhan_equity_pnl, sign=True)}{pct}")
        lines.append(f"- Equity subtotal: {fmt_inr(eq_subtotal)}")

        lines.append("")
        lines.append("Bonds")
        has_bonds = False
        if d.dhan_available and d.dhan_bond_value > 0:
            lines.append(f"- Dhan Bonds: {fmt_inr(d.dhan_bond_value)}")
            pct = f" ({d.dhan_bond_pnl_pct:+}%)" if d.dhan_bond_pnl_pct is not None else ""
            lines.append(f"-- P&L: {fmt_inr(d.dhan_bond_pnl, sign=True)}{pct}")
            has_bonds = True
        elif not d.dhan_available:
            lines.append("- Dhan Bonds: [unavailable]")
        if d.nuvama_available and d.nuvama_bonds_value > 0:
            lines.append(f"- Nuvama Bonds: {fmt_inr(d.nuvama_bonds_value)}")
            pct = f" ({d.nuvama_bonds_pnl_pct:+}%)" if d.nuvama_bonds_pnl_pct is not None else ""
            lines.append(f"-- P&L: {fmt_inr(d.nuvama_bonds_pnl, sign=True)}{pct}")
            has_bonds = True
        elif not d.nuvama_available:
            lines.append("- Nuvama Bonds: [unavailable]")
        if has_bonds:
            lines.append(f"- Bonds subtotal: {fmt_inr(bonds_subtotal)}")
        elif d.dhan_available and d.nuvama_available:
            lines.append("- (no bond holdings)")

        lines.append("")
        lines.append("Derivatives")
        lines.append(f"- Upstox options P&L: {fmt_inr(d.options_pnl, sign=True)}")
        if d.nuvama_options_available:
            lines.append(f"- Nuvama options P&L: {fmt_inr(d.nuvama_options_net_pnl, sign=True)}")

        lines.append("")
        lines.append("Total")
        lines.append(f"- Total value: {fmt_inr(d.total_value)}")
        lines.append(f"- Total invested: {fmt_inr(d.total_invested)}")
        lines.append(f"- Total P&L: {fmt_inr(d.total_pnl, sign=True)} ({d.total_pnl_pct:+}%)")
        if not d.mf_available:
            lines.append("- NOTE: MF fetch failed — MF value excluded from total")
        if not d.dhan_available:
            lines.append("- NOTE: Dhan unavailable — Dhan values excluded from total")
        if not d.nuvama_available:
            lines.append("- NOTE: Nuvama unavailable — Nuvama bonds excluded from total")

    # ── Dhan Options (Intraday) — format_options_section port, appended after a blank line
    #    (matches "summary_text + '\n\n' + dhan_options_section", daily_snapshot.py:723). ──
    today_cost = d.dhan_opts_charges + d.dhan_opts_brokerage
    month_cost = d.dhan_opts_month_charges + d.dhan_opts_month_brokerage
    lines += [
        "",
        "Dhan Options (Intraday)",
        f"Today P&L: {fmt_inr(d.dhan_opts_realized, sign=True)} gross",
        f"Today Cost: {fmt_inr(-today_cost, sign=True)} "
        f"(chg: {fmt_inr(-d.dhan_opts_charges, sign=True)} "
        f"brk: {fmt_inr(-d.dhan_opts_brokerage, sign=True)})",
        f"Today Net: {fmt_inr(d.dhan_opts_realized - today_cost, sign=True)}",
        f"Month P&L: {fmt_inr(d.dhan_opts_month_pnl, sign=True)} gross",
        f"Month Cost: {fmt_inr(-month_cost, sign=True)} "
        f"(chg: {fmt_inr(-d.dhan_opts_month_charges, sign=True)} "
        f"brk: {fmt_inr(-d.dhan_opts_month_brokerage, sign=True)})",
        f"Month Net: {fmt_inr(d.dhan_opts_month_pnl - month_cost, sign=True)}",
        f"Positions: {d.dhan_opts_position_count}",
    ]
    if d.dhan_opts_unrealized != Decimal("0"):
        lines.append(f"WARNING Unrealized: {fmt_inr(d.dhan_opts_unrealized, sign=True)}")

    # Whole message is prose (no fenced block, decision #2) — escape wholesale, same
    # convention as every prior kv-line script in this epic (reentry/strategy-event/etc.).
    return escape_markdown("\n".join(lines))


async def _send(msg: str, label: str) -> None:
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        print(f"[{label}] (skipped send: TELEGRAM_BOT_TOKEN/CHAT_ID not configured)")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json={"chat_id": chat_id, "text": msg, "parse_mode": "MarkdownV2"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.json()
            if resp.status != 200:
                print(f"[{label}] Telegram send failed ({resp.status}): {body.get('description')}")
            else:
                print(f"[{label}] Sent to Telegram OK.")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Also send both variants live")
    args = parser.parse_args()

    waterfall = build_message(Sample(has_deltas=True))
    fallback = build_message(Sample(has_deltas=False, total_day_delta=None))

    for label, msg in [("waterfall", waterfall), ("fallback", fallback)]:
        print(f"--- {label} (raw MarkdownV2) ---")
        print(msg)
        print("--- end ---\n")

    if args.send:
        await _send(waterfall, "waterfall")
        await _send(fallback, "fallback")


if __name__ == "__main__":
    asyncio.run(main())
