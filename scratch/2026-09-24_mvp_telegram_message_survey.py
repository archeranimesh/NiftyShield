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
    plus what the caller already has on the Pick/event."""

    symbol: str
    event_type: PickStatus
    label: str
    held_days: int | None
    entry_price: Decimal | None
    exit_price: Decimal
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


def _alert_table(alert: MVPAlert) -> str:
    entry = f"{alert.entry_price:,.2f}" if alert.entry_price is not None else "—"
    exit_ = f"{alert.exit_price:,.2f}"
    pnl = format_money(alert.realized_pnl, signed=True) if alert.realized_pnl is not None else "—"
    header = f"{'Entry':<10}{'Exit':<10}{'P&L':>14}"
    row = f"{entry:<10}{exit_:<10}{pnl:>14}"
    sep = "-" * max(len(header), len(row))
    return "\n".join([header, sep, row])


def _alert_footer(alert: MVPAlert) -> str:
    lines = ["━" * 24]
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
        return_str = escape_markdown(f"{sign}{format_pct(float(return_pct))}")
    else:
        return_str = escape_markdown("—")
    qty_str = escape_markdown(str(alert.total_qty)) if alert.total_qty else escape_markdown("—")
    deployed_str = (
        escape_markdown(format_money(alert.deployed_capital))
        if alert.deployed_capital is not None
        else escape_markdown("—")
    )
    sep = escape_markdown("   ")
    lines.append(
        f"\U0001f4c8 *Return:* {return_str}{sep}*Qty:* {qty_str}{sep}*Deployed:* {deployed_str}"
    )
    return "\n".join(lines)


def format_mvp_alert(alert: MVPAlert) -> str:
    """M10 prototype: headline -> kv row -> fenced Entry/Exit/P&L table -> footer."""
    head = [_alert_headline(alert), _alert_kv_row(alert), ""]
    table = ["```", _alert_table(alert), "```"]
    footer = [_alert_footer(alert)]
    return "\n".join(head + table + footer)


# --- M12: hourly summary — final shape, confirmed 2026-09-24 ---------------
#
# Single flat table (no category grouping), [O]/[P] status badge folded in,
# broker-holdings-style value columns, bottom totals footer. "Day chg%" is
# deliberately excluded — no previous-close baseline exists in MVP today.


def _holdings_value_cells(pick: Pick, ltp: Decimal | None) -> tuple[str, ...]:
    """Qty / Avg cost / LTP / Cur val / P&L / Net chg% for an OPEN pick."""
    qty = str(pick.total_qty) if pick.total_qty else "—"
    avg_cost = format_money(pick.avg_cost) if pick.avg_cost is not None else "—"
    ltp_str = format_money(ltp) if ltp is not None else "—"

    if ltp is not None and pick.total_qty:
        cur_val = format_money(ltp * pick.total_qty)
    else:
        cur_val = "—"

    if ltp is not None and pick.avg_cost is not None and pick.total_qty:
        pnl = format_money((ltp - pick.avg_cost) * pick.total_qty, signed=True)
    else:
        pnl = "—"

    if ltp is not None and pick.avg_cost is not None and pick.avg_cost != 0:
        chg = (ltp - pick.avg_cost) / pick.avg_cost * 100
        sign = "+" if chg > 0 else ""
        net_chg = f"{sign}{chg:.1f}%"
    else:
        net_chg = "—"

    return (qty, avg_cost, ltp_str, cur_val, pnl, net_chg)


def format_holdings_row(pick: Pick, ltp: Decimal | None) -> tuple[str, ...]:
    """One row's cells: [status badge], Instrument, Qty, Avg cost, LTP, Cur val, P&L, Net chg%."""
    badge = "[O]" if pick.status == PickStatus.OPEN else "[P]"
    if pick.status != PickStatus.OPEN:
        return (badge, pick.symbol, "—", "—", "—", "—", "—", "—")
    return (badge, pick.symbol, *_holdings_value_cells(pick, ltp))


def build_holdings_table(rows: list[tuple[str, ...]]) -> str:
    """Column-aligned fenced table, same per-column-max-width pattern as
    src/notifications/formatting.py's build_close_leg_table."""
    headers = ("", "Instrument", "Qty", "Avg cost", "LTP", "Cur val", "P&L", "Net chg%")
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]
    aligns = ["<", "<", ">", ">", ">", ">", ">", ">"]

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


def format_hourly_summary(picks: list[Pick], ltp_map: dict[str, Decimal], run_time: str) -> str:
    """M12 final shape: 'MVP Open positions | <time>' headline (colored by net
    P&L) -> flat table w/ [O]/[P] badges -> Invested/Current/P&L on three
    lines -> Open/Pending counts."""
    open_picks = [p for p in picks if p.status == PickStatus.OPEN]
    pending_picks = [p for p in picks if p.status == PickStatus.PENDING]
    relevant = open_picks + pending_picks
    if not relevant:
        return ""

    rows = [format_holdings_row(pick, ltp_map.get(pick.instrument_key)) for pick in relevant]
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
        symbol="RELIANCE",
        instrument_key="NSE_EQ|RELIANCE",
        total_qty=83,
        avg_cost=Decimal("1203.00"),
    )
    missing_ltp_pick = _pick(
        pick_id="pick-13",
        symbol="TCS",
        instrument_key="NSE_EQ|TCS",
        total_qty=29,
        avg_cost=Decimal("3408.50"),
    )
    loss_pick = _pick(
        pick_id="pick-14",
        symbol="WIPRO",
        instrument_key="NSE_EQ|WIPRO",
        total_qty=210,
        avg_cost=Decimal("468.00"),
    )
    pending_pick = _pick(
        pick_id="pick-15",
        symbol="INFY",
        status=PickStatus.PENDING,
        entry_price=None,
        total_qty=0,
        avg_cost=None,
    )
    ltp_map = {
        "NSE_EQ|RELIANCE": Decimal("1401.00"),
        "NSE_EQ|WIPRO": Decimal("402.15"),
        # NSE_EQ|TCS intentionally absent -> "—" row
    }
    show(
        "Hourly summary (M12 final): [O]/[P] badges + bottom totals footer",
        format_hourly_summary(
            [normal_pick, missing_ltp_pick, loss_pick, pending_pick], ltp_map, "11:00 AM"
        ),
    )


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
