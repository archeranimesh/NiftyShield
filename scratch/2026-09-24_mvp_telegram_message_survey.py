#!/usr/bin/env python3
"""Prototype: MVP watch message redesign — final shapes, prior to M10/M12.

One-off review script (not a repeatable op) — prototype for M10 (per-alert
message) and M12 (hourly summary table) in docs/plan/mvp/tasks.md, before
touching src/mvp/tracker.py or scripts/mvp_watch.py for real. Prints each
variant's raw MarkdownV2 text; with --send, also posts the non-empty ones to
the live Telegram chat.

Per-alert messages (M10): headline -> kv row -> fenced Entry/Exit/P&L table
-> separator -> return/qty/deployed footer, inspired by
src/notifications/exit_message.py's IC-close layout, using the real ₹
realized_pnl/total_qty/deployed_capital/avg_cost that close_pick() already
computes (M9) but the old alert message never surfaced.

Hourly summary (M12, confirmed by Animesh 2026-09-24 — this is the final
shape, prior variants removed): single flat table (no category grouping),
[O]/[P] status badge folded into the table, broker-holdings-style columns
(Instrument/Qty/Avg cost/LTP/Cur val/P&L/Net chg%), bottom totals footer
(Invested/Current/P&L, Open/Pending counts). "Day chg%" deliberately
excluded — MVP has no previous-close baseline today (see chat 2026-09-24).

Covers, per the alert format:
  - TARGET_HIT with a normal fill
  - SL_HIT with a normal fill (negative P&L)
  - a breach with no fill (avg_cost/total_qty None -> pnl/qty/deployed as "—")
  - a breach with no resolvable label (category missing)

Covers, per the hourly summary format:
  - multiple OPEN picks, one with no ltp in the map ("—" row)
  - a PENDING pick ([P] badge, all value columns "—")
  - the totals footer arithmetic
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src.mvp.models import Pick, PickStatus  # noqa: E402
from src.notifications.formatting import format_money, format_pct  # noqa: E402
from src.notifications.markdown import escape_markdown  # noqa: E402
from src.notifications.telegram import build_notifier  # noqa: E402


def _pick(**overrides) -> Pick:
    defaults = dict(
        pick_id="pick-1",
        category_id="cat-1",
        symbol="RELIANCE",
        instrument_key="NSE_EQ|RELIANCE",
        pick_date="2026-06-12",
        entry_price=Decimal("1200"),
        target_price=Decimal("1500"),
        stop_loss=Decimal("1100"),
        status=PickStatus.OPEN,
        created_at="2026-06-12T00:00:00+00:00",
        updated_at="2026-06-12T00:00:00+00:00",
    )
    defaults.update(overrides)
    return Pick(**defaults)


# --- M10: real ₹ P&L in the per-alert message --------------------------
#
# Mirrors exit_message.py's building blocks (_headline / _kv_row / fenced
# table / separator / footer) at MVP's smaller scale — single instrument, no
# legs, no cycles. Prototype only: this logic belongs in
# src/mvp/tracker.py once M10 is actually implemented.


@dataclass(frozen=True)
class MVPAlert:
    """Prototype shape for the M10 redesign — what close_pick() should return
    plus what the caller already has on the Pick/event.

    planned_price added 2026-09-24 — the pick's original target_price (on a
    TARGET_HIT) or stop_loss (on an SL_HIT), both already on the Pick row at
    close time, no new data needed. Without it the alert only ever showed
    the actual fill price, with no way to tell a clean hit from a slipped
    one (e.g. target ₹1500, filled at ₹1401 — a real 6.6% miss)."""

    symbol: str
    event_type: PickStatus
    label: str
    held_days: int | None
    entry_price: Decimal | None
    exit_price: Decimal
    planned_price: Decimal | None
    avg_cost: Decimal | None
    total_qty: int | None
    deployed_capital: Decimal | None
    realized_pnl: Decimal | None


def _held_days(pick_date_str: str, as_of: date) -> int:
    return (as_of - date.fromisoformat(pick_date_str)).days


def _alert_headline(alert: MVPAlert) -> str:
    emoji = "\U0001f3af" if alert.event_type == PickStatus.TARGET_HIT else "\U0001f6d1"
    verb = "Target Hit" if alert.event_type == PickStatus.TARGET_HIT else "SL Hit"
    symbol = escape_markdown(alert.symbol)
    return f"{emoji} *MVP {verb}* — {symbol}"


def _alert_kv_row(alert: MVPAlert) -> str:
    label = escape_markdown(alert.label) if alert.label else escape_markdown("Unassigned")
    held = (
        escape_markdown(str(alert.held_days))
        if alert.held_days is not None
        else escape_markdown("—")
    )
    return f"{label}   *Held:* {held}d"


def _alert_slippage_line(alert: MVPAlert) -> str | None:
    """Planned (target/SL) vs actual fill — added 2026-09-24, see MVPAlert
    docstring. Returns None (no line) when planned_price is unavailable, e.g.
    the no-fill breach case."""
    if alert.planned_price is None or alert.planned_price == 0:
        return None
    verb = "Target" if alert.event_type == PickStatus.TARGET_HIT else "SL"
    slip_pct = (alert.exit_price - alert.planned_price) / alert.planned_price * 100
    sign = "+" if slip_pct > 0 else ""
    planned_str = escape_markdown(format_money(alert.planned_price))
    slip_str = escape_markdown(f"{sign}{slip_pct:.1f}%")
    return f"{verb}: {planned_str}   *Fill vs plan:* {slip_str}"


def _alert_table(alert: MVPAlert) -> str:
    """Entry / Exit / Qty / P&L / Return, all via format_money for a
    consistent ₹-prefixed money column (2026-09-24 fix — Entry/Exit
    previously skipped format_money and rendered bare "1,200.00" next to a
    ₹-prefixed P&L). Qty and Return (renamed from Chg%) folded into the
    table 2026-09-24 — they no longer need a separate prose footer line."""
    entry = format_money(alert.entry_price) if alert.entry_price is not None else "—"
    exit_ = format_money(alert.exit_price)
    qty_str = str(alert.total_qty) if alert.total_qty else "—"
    pnl = format_money(alert.realized_pnl, signed=True) if alert.realized_pnl is not None else "—"
    if (
        alert.realized_pnl is not None
        and alert.deployed_capital is not None
        and alert.deployed_capital != 0
    ):
        return_pct = alert.realized_pnl / alert.deployed_capital * 100
        sign = "+" if return_pct > 0 else ""
        # NOTE: FORMATTING.md documents format_pct_signed() for this exact case
        # (prose, signed percent) but that function doesn't exist in
        # src/notifications/formatting.py — every real caller (e.g.
        # tracker.py's _format_row) manually prefixes the sign instead, so
        # this prototype matches the existing pattern rather than the doc.
        return_str = f"{sign}{format_pct(float(return_pct))}"
    else:
        return_str = "—"

    cells = (entry, exit_, qty_str, pnl, return_str)
    headers = ("Entry", "Exit", "Qty", "P&L", "Return")
    widths = [max(len(headers[i]), len(cells[i])) for i in range(5)]
    header = "  ".join(f"{headers[i]:>{widths[i]}}" for i in range(5))
    row = "  ".join(f"{cells[i]:>{widths[i]}}" for i in range(5))
    sep = "-" * max(len(header), len(row))
    return "\n".join([header, sep, row])


def _alert_footer(alert: MVPAlert) -> list[str]:
    """Invested/Current/P&L, scoped to this one closed pick — same three-line
    shape as M12's _totals_lines, single-row instead of aggregated across
    picks. Replaces the old Return/Qty/Deployed prose line (Qty and Return
    moved into the table; Deployed is renamed Invested to match M12's
    wording)."""
    if alert.realized_pnl is None or alert.deployed_capital is None or alert.total_qty is None:
        return [escape_markdown("Invested: —   Current: —   P&L: —")]
    invested = alert.deployed_capital
    current = invested + alert.realized_pnl
    return _totals_lines(invested, current, alert.realized_pnl)


def format_mvp_alert(alert: MVPAlert) -> str:
    """M10 prototype: headline -> kv row -> slippage line (planned vs fill)
    -> fenced Entry/Exit/Qty/P&L/Return table -> Invested/Current/P&L footer
    (scoped to this pick)."""
    head = [_alert_headline(alert), _alert_kv_row(alert)]
    slippage = _alert_slippage_line(alert)
    if slippage is not None:
        head.append(slippage)
    head.append("")
    table = ["```", _alert_table(alert), "```"]
    footer = _alert_footer(alert)
    return "\n".join(head + table + footer)


# --- M12: hourly summary — final shape, confirmed 2026-09-24 ---------------
#
# Single flat table (no category grouping), [O]/[P] status badge folded in,
# broker-holdings-style value columns, bottom totals footer. "Day chg%" is
# deliberately excluded — no previous-close baseline exists in MVP today.


def _next_level_str(pick: Pick, ltp: Decimal | None) -> str:
    """Distance to whichever of target/stop-loss is nearer, e.g. "T +7.1%" or
    "SL -3.4%". Re-added 2026-09-24 — the entire reason M12 rewrote
    _format_row was that the old "T:1500 (7.1% away)" compound cell broke
    column alignment; the rewrite fixed alignment but dropped this
    information outright instead of reformatting it. This restores it as its
    own column using real Pick.target_price/stop_loss (no new data needed)."""
    if ltp is None or ltp == 0:
        return "—"
    candidates = []
    if pick.target_price is not None:
        candidates.append(("T", (pick.target_price - ltp) / ltp * 100))
    if pick.stop_loss is not None:
        candidates.append(("SL", (ltp - pick.stop_loss) / ltp * 100))
    if not candidates:
        return "—"
    label, pct = min(candidates, key=lambda c: abs(c[1]))
    sign = "+" if pct > 0 else ""
    return f"{label} {sign}{pct:.1f}%"


def _holdings_value_cells(pick: Pick, ltp: Decimal | None) -> tuple[str, ...]:
    """LTP / P&L / Next for an OPEN pick.

    Svc/Qty/Avg cost/Chg% all dropped 2026-09-24 (50-char mobile-width
    budget, confirmed via _width_ruler() — every 2-optional-column
    combination that keeps Next also keeps the table over budget; Next
    alone was the co-investor's pick over Svc+Qty, AvgCost, or Chg% since
    it's the regression-restore column, not a nice-to-have). "Cur val"
    dropped earlier the same session — it's just Qty x LTP, recoverable
    from the other columns, and was the widest cell.
    "Next" (target/SL proximity) — see _next_level_str.
    """
    ltp_str = format_money(ltp) if ltp is not None else "—"

    if ltp is not None and pick.avg_cost is not None and pick.total_qty:
        pnl = format_money((ltp - pick.avg_cost) * pick.total_qty, signed=True)
    else:
        pnl = "—"

    return (ltp_str, pnl, _next_level_str(pick, ltp))


def format_holdings_row(
    pick: Pick, ltp: Decimal | None, category_label: str = "—"
) -> tuple[str, ...]:
    """One row's cells: [status badge], Sym, LTP, P&L, Next. `category_label`
    kept as a parameter (unused in the row itself, 2026-09-24 — see
    build_holdings_table's docstring) so callers/tests don't need to change.

    A PENDING row's LTP cell shows its trigger price (reco_price, prefixed
    "->") instead of a bare "—" — added 2026-09-24, so a pending pick isn't
    a total black box about what price converts it to OPEN."""
    del category_label
    badge = "[O]" if pick.status == PickStatus.OPEN else "[P]"
    if pick.status != PickStatus.OPEN:
        trigger = f"→{format_money(pick.reco_price)}" if pick.reco_price is not None else "—"
        return (badge, pick.symbol, trigger, "—", "—")
    return (badge, pick.symbol, *_holdings_value_cells(pick, ltp))


def build_holdings_table(rows: list[tuple[str, ...]]) -> str:
    """Column-aligned fenced table, same per-column-max-width pattern as
    src/notifications/formatting.py's build_close_leg_table. Header renamed
    "Instrument" -> "Sym" 2026-09-24 (mobile-width fix) — "Instrument" (10
    chars) was wider than every actual symbol, so the header itself was
    driving the column wide; the symbol value is shown in full (checked
    2026-09-24: NSE/Yahoo/Google Finance all use the same full ticker, e.g.
    "RELIANCE" — "RIL" is a colloquial company abbreviation, not a real
    shorter exchange symbol, so truncating the real ticker was reverted).

    Svc/Qty/Avg cost/Chg% dropped 2026-09-24 (50-char mobile-width budget,
    co-investor's final pick was Next over the other optional columns —
    see _holdings_value_cells's docstring for the full width comparison)."""
    headers = ("", "Sym", "LTP", "P&L", "Next")
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]
    aligns = ["<", "<", ">", ">", ">"]

    def _line(cells: tuple[str, ...]) -> str:
        return "  ".join(f"{cell:{aligns[i]}{widths[i]}}" for i, cell in enumerate(cells))

    lines = [_line(headers), "-" * len(_line(headers))]
    lines.extend(_line(row) for row in rows)
    return "\n".join(lines)


def _open_positions_totals(
    open_picks: list[Pick], ltp_map: dict[str, Decimal]
) -> tuple[Decimal, Decimal, Decimal]:
    """(invested, current, pnl) across OPEN picks only — unrealized, mark-to-market.

    Deliberately excludes realized_pnl from already-closed picks (confirmed
    2026-09-24) — this is a live-positions view, not an inception summary.
    """
    invested = Decimal("0")
    current = Decimal("0")
    for pick in open_picks:
        if pick.avg_cost is None or not pick.total_qty:
            continue
        ltp = ltp_map.get(pick.instrument_key)
        invested += pick.avg_cost * pick.total_qty
        if ltp is not None:
            current += ltp * pick.total_qty
        else:
            current += pick.avg_cost * pick.total_qty  # no ltp -> flat, not a loss/gain
    return invested, current, current - invested


def _totals_lines(invested: Decimal, current: Decimal, pnl: Decimal) -> list[str]:
    """Three separate bold-label lines: Invested / Current / P&L, IC-style."""
    invested_str = escape_markdown(format_money(invested))
    current_str = escape_markdown(format_money(current))
    pnl_str = escape_markdown(format_money(pnl, signed=True))
    if invested != 0:
        pct = pnl / invested * 100
        sign = "+" if pct > 0 else ""
        pct_str = escape_markdown(f"{sign}{pct:.1f}%")
        pnl_value = f"{pnl_str} \\({pct_str}\\)"
    else:
        pnl_value = pnl_str
    return [
        f"\U0001f4b0 *Invested:* {invested_str}",
        f"\U0001f4ca *Current:* {current_str}",
        f"\U0001f4c8 *P&L:* {pnl_value}",
    ]


def _headline_emoji(pnl: Decimal) -> str:
    """Net-P&L color signal: green/red/white circle — outside the fence, so
    FORMATTING.md's fence-width rejection of 🔴 (ROLL-2a) doesn't apply here."""
    if pnl > 0:
        return "\U0001f7e2"  # 🟢
    if pnl < 0:
        return "\U0001f534"  # 🔴
    return "⚪"  # ⚪


def format_hourly_summary(
    picks: list[Pick],
    ltp_map: dict[str, Decimal],
    run_time: str,
    category_labels: dict[str, str] | None = None,
) -> str:
    """M12 final shape: 'MVP Open positions | <time>' headline (colored by net
    P&L) -> flat table w/ [O]/[P] badges -> Invested/Current/P&L on three
    lines -> Open/Pending counts.

    category_labels: pick.category_id -> short display tag (e.g. "VP" for
    DSIJ/Value Picks). Kept as a parameter for callers/tests, but 2026-09-24's
    column-budget decision dropped the Svc cell that displayed it — see
    format_holdings_row/build_holdings_table for the width tradeoff."""
    category_labels = category_labels or {}
    open_picks = [p for p in picks if p.status == PickStatus.OPEN]
    pending_picks = [p for p in picks if p.status == PickStatus.PENDING]
    relevant = open_picks + pending_picks
    if not relevant:
        return ""

    rows = [
        format_holdings_row(
            pick, ltp_map.get(pick.instrument_key), category_labels.get(pick.category_id, "—")
        )
        for pick in relevant
    ]
    invested, current, pnl = _open_positions_totals(open_picks, ltp_map)
    emoji = _headline_emoji(pnl)
    time_str = escape_markdown(run_time)

    lines = [f"{emoji} *MVP Open positions* \\| {time_str}", ""]
    lines.append("```")
    lines.append(build_holdings_table(rows))
    lines.append("```")
    lines.append("")
    lines.extend(_totals_lines(invested, current, pnl))
    lines.append(escape_markdown(f"Open: {len(open_picks)}   Pending: {len(pending_picks)}"))
    return "\n".join(lines)


# --- EOD summary — prototype, first pass 2026-09-24 -------------------
#
# Grouped by provider -> category (DSIJ: Value Picks / Multibagger / TAS),
# one aggregated row per category, then an all-recommendations footer with
# P&L, day change, and inception return. day_chg_pct/inception_pct are
# fixture inputs here — no MVPStore aggregate query computes them yet
# (would need yesterday's-EOD-vs-today's-EOD snapshot diff per pick, and a
# since-inception rollup across open + closed picks); real implementation
# is new store work, not covered by this scratch prototype.


@dataclass(frozen=True)
class CategoryRollup:
    """One category's EOD aggregate row under a provider.

    realized_pnl/win_pct/win_closed_count/inception_pct/high_pct/low_pct are
    placeholder fixture fields — no MVPStore query computes them today
    (realized_pnl and win rate both need a closed-picks aggregate; inception
    needs a since-first-pick rollup across open + closed picks — both M11's
    scope). high_pct/low_pct are a bigger gap than M11: they need a running
    cumulative-P&L-over-time series per category (high-water-mark /
    max-drawdown style), not just current state — no snapshot-history rollup
    like this exists yet; scope not sized, likely its own task after M11.
    See the docs/plan/mvp/tasks.md M11/M13 entries and their open items."""

    display_name: str
    short_code: str  # e.g. "VP" — same short-code convention as M12's Svc column
    invested: Decimal
    current: Decimal
    realized_pnl: Decimal  # booked P&L from this category's already-closed picks
    day_chg_pct: Decimal  # vs. yesterday's EOD close, category-weighted
    win_pct: Decimal | None  # None -> "—" (no closed picks yet)
    win_closed_count: int  # closed-picks sample size behind win_pct
    inception_pct: Decimal  # since this category's first pick, realized + unrealized
    high_pct: Decimal  # running high-water-mark since inception, % return
    low_pct: Decimal  # running max-drawdown point since inception, % return
    open_count: int  # cheap — pure arithmetic over existing Pick.status, no new query
    pending_count: int
    closed_count: int


@dataclass(frozen=True)
class ProviderRollup:
    provider_name: str
    short_code: str  # e.g. "DSIJ" — used in the merged table's Prv column
    categories: list[CategoryRollup]


def _rollup_pnl(rollup: CategoryRollup) -> Decimal:
    """Realized + unrealized — booked P&L from closed picks plus mark-to-market
    on this category's currently open positions. Category rows and the
    all-recs footer total both use this same combined definition (2026-09-24,
    Animesh's call) so the rows actually sum to the footer, unlike M12's
    deliberately open-only P&L."""
    return (rollup.current - rollup.invested) + rollup.realized_pnl


def build_eod_table(providers: list[ProviderRollup]) -> str:
    """Cat / P&L / Win% / Incep% / High / Low — ONE shared fenced table
    across every provider (2026-09-24, replaces a separate table per
    provider). Animesh's phone showed a single-category provider's own
    3-line block (header/separator/1 row) rendering in a visibly larger font
    than the wider multi-row DSIJ block, wrapping despite having FEWER
    characters per line — looks like Telegram auto-scales very short code
    blocks. Merging into one shared table removes the short-block case
    entirely: every provider's rows now share the same column widths and
    line count, so a single-category provider like FinnovationZ no longer
    gets its own tiny block.

    Prv column dropped 2026-09-24 (Animesh's call) — category short_codes
    (VP/MB/TAS/IKA) don't collide across providers, so the extra column
    wasn't needed to disambiguate rows, and cutting it also helps close the
    remaining gap to the confirmed 50-char mobile-safe width. If a category
    short_code ever collides across two providers, this needs revisiting.

    Invested/Current dropped 2026-09-24 (Animesh's call) — this is a
    per-service scorecard, not a position-level view (M12 already covers
    that); P&L + Win% + Incep% says whether a service is performing without
    duplicating M12. Win% shows the closed-picks sample size alongside it (a
    100% win rate on 1 closed pick reads very differently from 100% on 20).
    High/Low are the category's since-inception running high-water-mark /
    max-drawdown return%, not today's best/worst pick."""
    headers = ("Cat", "P&L", "Win%", "Incep%", "High", "Low")
    rows = []
    for provider in providers:
        for cat in provider.categories:
            pnl = _rollup_pnl(cat)
            if cat.win_pct is None:
                # still show the (0) count so a "—" reads as "no closed
                # picks yet" rather than looking like a broken computation.
                win_str = f"— ({cat.win_closed_count})"
            else:
                win_str = f"{cat.win_pct:.0f}% ({cat.win_closed_count})"
            incep_sign = "+" if cat.inception_pct > 0 else ""
            high_sign = "+" if cat.high_pct > 0 else ""
            low_sign = "+" if cat.low_pct > 0 else ""
            rows.append(
                (
                    cat.short_code,
                    format_money(pnl, signed=True),
                    win_str,
                    f"{incep_sign}{cat.inception_pct:.1f}%",
                    f"{high_sign}{cat.high_pct:.1f}%",
                    f"{low_sign}{cat.low_pct:.1f}%",
                )
            )
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(6)]
    aligns = ["<", ">", ">", ">", ">", ">"]

    def _line(cells: tuple[str, ...]) -> str:
        return "  ".join(f"{cell:{aligns[i]}{widths[i]}}" for i, cell in enumerate(cells))

    lines = [_line(headers), "-" * len(_line(headers))]
    lines.extend(_line(row) for row in rows)
    return "\n".join(lines)


def format_eod_summary(
    providers: list[ProviderRollup],
    run_date: str,
    inception_pct: Decimal,
    benchmark_pct: Decimal | None = None,
) -> str:
    """EOD summary: headline -> one shared fenced category-rollup table
    across every provider (see build_eod_table) -> all-recommendations
    footer (P&L / Day chg / Inception / vs Nifty / Open-Pending-Closed
    counts).

    benchmark_pct: MVP's since-inception return minus Nifty's over the same
    window (alpha). Optional/None -> line omitted. Fixture-only today — see
    the module docstring's Known gaps: MVPSnapshot.benchmark_close is
    captured by backfill.py but scripts/mvp_watch.py never populates it on a
    live hourly/EOD run, so no real index-return series exists to diff
    against yet. Wiring that up is new work, not sized."""
    all_categories = [cat for p in providers for cat in p.categories]
    if not all_categories:
        return ""

    total_invested = sum((cat.invested for cat in all_categories), Decimal("0"))
    total_pnl = sum((_rollup_pnl(cat) for cat in all_categories), Decimal("0"))
    # day change weighted by each category's invested capital
    day_chg_pct = (
        sum((cat.day_chg_pct * cat.invested for cat in all_categories), Decimal("0"))
        / total_invested
        if total_invested
        else Decimal("0")
    )
    emoji = _headline_emoji(total_pnl)
    date_str = escape_markdown(run_date)

    lines = [f"{emoji} *MVP EOD Summary* \\| {date_str}", ""]
    lines.append("```")
    lines.append(build_eod_table(providers))
    lines.append("```")
    lines.append("")

    # No signed % shown alongside P&L here (unlike M12's open-only P&L, which
    # has a clean "pnl / invested" base): once realized_pnl from closed picks
    # is folded in, total_invested is no longer the right denominator — the
    # capital already returned by closed picks isn't counted in it. Since
    # inception %, below, is the relative-return figure for this combined
    # realized+unrealized scope.
    day_sign = "+" if day_chg_pct > 0 else ""
    incep_sign = "+" if inception_pct > 0 else ""
    lines.append(
        f"\U0001f4b0 *All recs P&L:* {escape_markdown(format_money(total_pnl, signed=True))}"
    )
    lines.append(f"\U0001f4c5 *Day chg:* {escape_markdown(f'{day_sign}{day_chg_pct:.1f}%')}")
    lines.append(
        f"\U0001f680 *Since inception:* {escape_markdown(f'{incep_sign}{inception_pct:.1f}%')}"
    )
    if benchmark_pct is not None:
        bench_sign = "+" if benchmark_pct > 0 else ""
        lines.append(f"⚖️ *vs Nifty:* {escape_markdown(f'{bench_sign}{benchmark_pct:.1f}%')}")

    total_open = sum(cat.open_count for cat in all_categories)
    total_pending = sum(cat.pending_count for cat in all_categories)
    total_closed = sum(cat.closed_count for cat in all_categories)
    lines.append(
        escape_markdown(f"Open: {total_open}   Pending: {total_pending}   Closed: {total_closed}")
    )
    return "\n".join(lines)


VARIANTS: list[tuple[str, str]] = []


def show(title: str, message: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")
    print(message if message else "(empty string — no message sent)")
    VARIANTS.append((title, message))


async def send_all(title_filter: str | None = None) -> None:
    """Send collected variants to the live Telegram chat, in order.

    Args:
        title_filter: When set, only send variants whose title contains this
            substring (case-insensitive) instead of every variant.
    """
    notifier = build_notifier()
    if notifier is None:
        print(
            "\nbuild_notifier() returned None — TELEGRAM_BOT_TOKEN/CHAT_ID not set. Nothing sent."
        )
        return
    for title, message in VARIANTS:
        if title_filter and title_filter.lower() not in title.lower():
            continue
        if not message:
            print(f"skip (empty): {title}")
            continue
        await notifier.send(message)
        print(f"sent: {title}")


def _width_ruler() -> str:
    """Calibration probe (2026-09-24) — a fenced block with one ruled line per
    width, 30 to 80 chars in steps of 5, each line ending in its own char
    count so whichever one is the LAST to render on one line (no wrap) on the
    actual device tells us the real mobile-safe width. Needed because every
    "~55-65 char safe zone" figure used earlier this session was an estimate,
    never confirmed on-device the way FORMATTING.md's `₹`/`🔴` checks were.

    RESULT (confirmed on Animesh's device, 2026-09-24): 50 chars is the real
    mobile-safe width. M10's alert table (33-34 chars) and M13's EOD tables
    (44-49 chars) both already pass. M12's hourly table (77 chars as of this
    session) does NOT — needs a real column cut, not just header renames."""
    lines = []
    for width in range(30, 81, 5):
        suffix = f" ({width})"
        dashes = "-" * (width - len(suffix))
        lines.append(dashes + suffix)
    return "```\n" + "\n".join(lines) + "\n```"


def main() -> None:
    as_of = date(2026, 7, 27)  # 45 days after the fixture pick_date, for a round Held: 45d

    # --- Per-alert messages (M10) ---------------------------------------
    show(
        "Alert: TARGET_HIT, normal fill, with label",
        format_mvp_alert(
            MVPAlert(
                symbol="RELIANCE",
                event_type=PickStatus.TARGET_HIT,
                label="DSIJ / Value Picks",
                held_days=_held_days("2026-06-12", as_of),
                entry_price=Decimal("1200"),
                exit_price=Decimal("1401"),
                planned_price=Decimal("1500"),
                avg_cost=Decimal("1203.00"),
                total_qty=83,
                deployed_capital=Decimal("99849.00"),
                realized_pnl=Decimal("16447.42"),
            )
        ),
    )

    show(
        "Alert: SL_HIT, normal fill, with label (negative P&L)",
        format_mvp_alert(
            MVPAlert(
                symbol="TCS",
                event_type=PickStatus.SL_HIT,
                label="DSIJ / Value Picks",
                held_days=_held_days("2026-06-01", as_of),
                entry_price=Decimal("3400"),
                exit_price=Decimal("3098"),
                planned_price=Decimal("3100"),
                avg_cost=Decimal("3408.50"),
                total_qty=29,
                deployed_capital=Decimal("98846.50"),
                realized_pnl=Decimal("-9187.28"),
            )
        ),
    )

    show(
        "Alert: breach on a pick with no fill (avg_cost/qty/deployed None)",
        format_mvp_alert(
            MVPAlert(
                symbol="INFY",
                event_type=PickStatus.TARGET_HIT,
                label="DSIJ / Value Picks",
                held_days=None,
                entry_price=None,
                exit_price=Decimal("1800"),
                planned_price=None,
                avg_cost=None,
                total_qty=None,
                deployed_capital=None,
                realized_pnl=None,
            )
        ),
    )

    show(
        "Alert: TARGET_HIT, no label (category unresolvable)",
        format_mvp_alert(
            MVPAlert(
                symbol="HDFCBANK",
                event_type=PickStatus.TARGET_HIT,
                label="",
                held_days=_held_days("2026-05-10", as_of),
                entry_price=Decimal("1500"),
                exit_price=Decimal("1700"),
                planned_price=Decimal("1690"),
                avg_cost=Decimal("1504.50"),
                total_qty=66,
                deployed_capital=Decimal("99297.00"),
                realized_pnl=Decimal("12660.87"),
            )
        ),
    )

    # --- Hourly summary (M12 final shape) --------------------------------
    normal_pick = _pick(
        pick_id="pick-12",
        category_id="cat-value-picks",
        symbol="RELIANCE",
        instrument_key="NSE_EQ|RELIANCE",
        total_qty=83,
        avg_cost=Decimal("1203.00"),
        target_price=Decimal("1500"),
        stop_loss=Decimal("1100"),
    )
    missing_ltp_pick = _pick(
        pick_id="pick-13",
        category_id="cat-value-picks",
        symbol="TCS",
        instrument_key="NSE_EQ|TCS",
        total_qty=29,
        avg_cost=Decimal("3408.50"),
        target_price=Decimal("3900"),
        stop_loss=Decimal("3100"),
    )
    loss_pick = _pick(
        pick_id="pick-14",
        category_id="cat-multibagger",
        symbol="WIPRO",
        instrument_key="NSE_EQ|WIPRO",
        total_qty=210,
        avg_cost=Decimal("468.00"),
        target_price=Decimal("620"),
        stop_loss=Decimal("400"),
    )
    pending_pick = _pick(
        pick_id="pick-15",
        category_id="cat-tas",
        symbol="INFY",
        status=PickStatus.PENDING,
        entry_price=None,
        total_qty=0,
        avg_cost=None,
        reco_price=Decimal("1750"),
    )
    ltp_map = {
        "NSE_EQ|RELIANCE": Decimal("1401.00"),
        "NSE_EQ|WIPRO": Decimal("402.15"),
        # NSE_EQ|TCS intentionally absent -> "—" row
    }
    category_labels = {
        "cat-value-picks": "VP",
        "cat-multibagger": "MB",
        "cat-tas": "TAS",
    }
    show(
        "Hourly summary (M12 final): [O]/[P] badges + bottom totals footer",
        format_hourly_summary(
            [normal_pick, missing_ltp_pick, loss_pick, pending_pick],
            ltp_map,
            "11:00 AM",
            category_labels,
        ),
    )

    # --- EOD summary (prototype, first pass) -----------------------------
    dsij = ProviderRollup(
        provider_name="DSIJ",
        short_code="DSIJ",
        categories=[
            CategoryRollup(
                display_name="Value Picks",
                short_code="VP",
                invested=Decimal("150000"),
                current=Decimal("162300"),
                realized_pnl=Decimal("4100"),
                day_chg_pct=Decimal("1.2"),
                win_pct=Decimal("67"),
                win_closed_count=3,
                inception_pct=Decimal("11.2"),
                high_pct=Decimal("18.4"),
                low_pct=Decimal("-6.7"),
                open_count=4,
                pending_count=1,
                closed_count=3,
            ),
            CategoryRollup(
                display_name="Multibagger",
                short_code="MB",
                invested=Decimal("80000"),
                current=Decimal("95400"),
                realized_pnl=Decimal("0"),
                day_chg_pct=Decimal("0.8"),
                win_pct=Decimal("100"),
                win_closed_count=1,
                inception_pct=Decimal("22.5"),
                high_pct=Decimal("22.5"),
                low_pct=Decimal("-2.1"),
                open_count=2,
                pending_count=0,
                closed_count=1,
            ),
            CategoryRollup(
                display_name="TAS",
                short_code="TAS",
                invested=Decimal("40000"),
                current=Decimal("38200"),
                realized_pnl=Decimal("-950"),
                day_chg_pct=Decimal("-0.5"),
                win_pct=None,
                win_closed_count=0,
                inception_pct=Decimal("-3.1"),
                high_pct=Decimal("4.2"),
                low_pct=Decimal("-8.9"),
                open_count=1,
                pending_count=1,
                closed_count=0,
            ),
        ],
    )
    finnovationz = ProviderRollup(
        provider_name="FinnovationZ",
        short_code="FinnZ",
        categories=[
            CategoryRollup(
                display_name="Ikashi",
                short_code="IKA",
                invested=Decimal("60000"),
                current=Decimal("57900"),
                realized_pnl=Decimal("1800"),
                day_chg_pct=Decimal("-0.3"),
                win_pct=Decimal("40"),
                win_closed_count=5,
                inception_pct=Decimal("2.9"),
                high_pct=Decimal("9.6"),
                low_pct=Decimal("-5.4"),
                open_count=3,
                pending_count=0,
                closed_count=5,
            ),
        ],
    )
    show(
        "EOD summary (prototype): provider -> category rollups + all-recs footer",
        format_eod_summary(
            [dsij], "24 Sep 2026", inception_pct=Decimal("9.7"), benchmark_pct=Decimal("2.3")
        ),
    )
    show(
        "EOD summary (prototype): two providers, one single-category (FinnovationZ)",
        format_eod_summary(
            [dsij, finnovationz],
            "24 Sep 2026",
            inception_pct=Decimal("8.1"),
            benchmark_pct=Decimal("1.4"),
        ),
    )

    # --- Width calibration probe (2026-09-24) ----------------------------
    show("Width calibration ruler (30-80 chars)", _width_ruler())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--send",
        action="store_true",
        help="Also send every non-empty variant to the live Telegram chat.",
    )
    parser.add_argument(
        "--send-only",
        metavar="SUBSTRING",
        help="With --send, only send variants whose title contains this substring.",
    )
    args = parser.parse_args()

    main()

    if args.send:
        asyncio.run(send_all(args.send_only))
