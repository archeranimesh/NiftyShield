"""Pure MVP pick tracking logic: price-breach detection."""

from dataclasses import dataclass
from decimal import Decimal

from src.mvp.models import Pick, PickStatus
from src.notifications.formatting import format_money, format_pct
from src.notifications.markdown import escape_markdown


@dataclass(frozen=True)
class MVPEvent:
    """A target or stop-loss breach detected for a pick."""

    pick_id: str
    symbol: str
    event_type: PickStatus
    trigger_price: Decimal
    entry_price: Decimal | None


def check_prices(
    picks: list[Pick],
    ltp_map: dict[str, Decimal],
) -> list[MVPEvent]:
    """Detect target/stop-loss breaches for open picks.

    Args:
        picks: Picks to evaluate.
        ltp_map: Last traded price keyed by instrument_key.

    Returns:
        MVPEvent list, one per breach. Empty if none.
    """
    events: list[MVPEvent] = []
    for pick in picks:
        if pick.status != PickStatus.OPEN:
            continue
        if pick.instrument_key is None or pick.instrument_key not in ltp_map:
            continue
        ltp = ltp_map[pick.instrument_key]

        if pick.target_price is not None and ltp >= pick.target_price:
            events.append(
                MVPEvent(
                    pick_id=pick.pick_id,
                    symbol=pick.symbol,
                    event_type=PickStatus.TARGET_HIT,
                    trigger_price=ltp,
                    entry_price=pick.entry_price,
                )
            )
        elif pick.stop_loss is not None and ltp <= pick.stop_loss:
            events.append(
                MVPEvent(
                    pick_id=pick.pick_id,
                    symbol=pick.symbol,
                    event_type=PickStatus.SL_HIT,
                    trigger_price=ltp,
                    entry_price=pick.entry_price,
                )
            )

    return events


def _format_num(value: Decimal | None) -> str:
    """Plain decimal string, no currency symbol, no thousands separator.

    "—" for None. Trailing zeros trimmed: Decimal("1200.00") -> "1200".
    """
    if value is None:
        return "—"
    text = format(value.quantize(Decimal("0.01")), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _next_level_str(pick: Pick, ltp: Decimal | None) -> str:
    """Distance to whichever of target/stop-loss is nearer, e.g. "T +7.1%" or "SL -3.4%"."""
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
    return f"{label} {sign}{format_pct(float(pct))}"


def format_holdings_row(pick: Pick, ltp: Decimal | None) -> tuple[str, str, str, str, str]:
    """One row's cells: [status badge], Sym, LTP, P&L, Next.

    A PENDING row shows its trigger price (reco_price, prefixed "->") in the
    LTP cell instead of a bare "—", and "—" for P&L/Next (no fill yet).
    Only OPEN and PENDING picks are valid inputs (matches format_hourly_summary's
    filter) — any other status raises ValueError rather than mislabeling.
    """
    if pick.status == PickStatus.OPEN:
        badge = "[O]"
    elif pick.status == PickStatus.PENDING:
        badge = "[P]"
    else:
        raise ValueError(f"format_holdings_row: unsupported pick status {pick.status!r}")

    if pick.status != PickStatus.OPEN:
        trigger = f"→{_format_num(pick.reco_price)}" if pick.reco_price is not None else "—"
        return (badge, pick.symbol, trigger, "—", "—")

    ltp_str = _format_num(ltp)
    if ltp is not None and pick.avg_cost is not None and pick.total_qty:
        pnl_val = (ltp - pick.avg_cost) * pick.total_qty
        sign = "+" if pnl_val > 0 else ""
        pnl = f"{sign}{_format_num(pnl_val)}"
    else:
        pnl = "—"
    return (badge, pick.symbol, ltp_str, pnl, _next_level_str(pick, ltp))


def build_holdings_table(rows: list[tuple[str, str, str, str, str]]) -> str:
    """Column-aligned fenced table: [badge] Sym LTP P&L Next.

    Per-column max width, same pattern as `build_close_leg_table`
    (`src/notifications/formatting.py`). `rows` must be non-empty — the sole
    caller, format_hourly_summary, never calls this with an empty list.
    """
    if not rows:
        raise ValueError("build_holdings_table requires at least one row")
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

    Deliberately excludes realized_pnl from already-closed picks — this is a
    live-positions view, not an inception summary.
    """
    invested = Decimal("0")
    current = Decimal("0")
    for pick in open_picks:
        if pick.avg_cost is None or not pick.total_qty:
            continue
        ltp = ltp_map.get(pick.instrument_key) if pick.instrument_key is not None else None
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
        pct_str = escape_markdown(f"{sign}{format_pct(float(pct))}")
        pnl_value = f"{pnl_str} \\({pct_str}\\)"
    else:
        pnl_value = pnl_str
    return [
        f"\U0001f4b0 *Invested:* {invested_str}",
        f"\U0001f4ca *Current:* {current_str}",
        f"\U0001f4c8 *P&L:* {pnl_value}",
    ]


def _headline_emoji(pnl: Decimal) -> str:
    """Net-P&L color signal: green/red/white circle. Sits outside any fence,
    so FORMATTING.md's fence-width rejection of red-circle doesn't apply."""
    if pnl > 0:
        return "\U0001f7e2"
    if pnl < 0:
        return "\U0001f534"
    return "⚪"


def format_hourly_summary(
    picks: list[Pick],
    ltp_map: dict[str, Decimal],
    run_time: str,
) -> str:
    """Build the hourly MVP watch summary as a MarkdownV2 message body.

    Single flat table (no category grouping), OPEN and PENDING picks in one
    table with a leading [O]/[P] status badge per row.

    Args:
        picks: Picks to consider. OPEN and PENDING picks are rendered as
            table rows; any other status is excluded.
        ltp_map: Last traded price keyed by instrument_key. A pick whose
            instrument_key is absent (or None) renders "—" for LTP/P&L/Next.
        run_time: Display string for the run header, e.g. "11:00 AM".

    Returns:
        A MarkdownV2-formatted message body: colored headline -> fenced
        [badge]/Sym/LTP/P&L/Next table -> Invested/Current/P&L footer (OPEN
        picks only, unrealized) -> Open/Pending counts. Empty string if no
        OPEN or PENDING picks. Pure function: no I/O.
    """
    open_picks = [p for p in picks if p.status == PickStatus.OPEN]
    pending_picks = [p for p in picks if p.status == PickStatus.PENDING]
    relevant = open_picks + pending_picks
    if not relevant:
        return ""

    rows = [
        format_holdings_row(
            pick, ltp_map.get(pick.instrument_key) if pick.instrument_key is not None else None
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
