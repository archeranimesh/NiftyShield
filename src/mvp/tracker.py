"""Pure MVP pick tracking logic: price-breach detection."""

import re
from dataclasses import dataclass
from decimal import Decimal

from src.mvp.models import Category, CategoryStats, Pick, PickStatus
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


def category_short_code(slug: str) -> str:
    """Short EOD-table code derived from ``Category.slug`` (no dedicated
    schema column — 2026-09-24, Animesh's call).

    Multi-word slugs (hyphen/underscore separated) use each word's first
    letter, uppercased, capped at 4 chars: "value_picks" -> "VP". A single
    word is truncated to its first 3 letters: "multibagger" -> "MUL". Not
    guaranteed unique across categories under the same provider.
    """
    words = [w for w in re.split(r"[-_]", slug) if w]
    if len(words) > 1:
        return "".join(w[0] for w in words)[:4].upper()
    return slug[:3].upper()


@dataclass(frozen=True)
class CategoryRollup:
    """One category's EOD aggregate row under a provider.

    ``day_chg_pct``/``high_pct``/``low_pct`` are ``None`` when the
    underlying store query has nothing to report yet (fewer than two
    snapshot days / no snapshot history) — rendered as "—" by
    ``build_eod_table``, not silently zeroed. ``win_pct`` is a plain
    percent (already ``* 100``), ``None`` when the category has no closed
    picks.
    """

    display_name: str
    short_code: str
    invested: Decimal
    current: Decimal
    realized_pnl: Decimal
    day_chg_pct: Decimal | None
    win_pct: Decimal | None
    win_closed_count: int
    inception_pct: Decimal
    high_pct: Decimal | None
    low_pct: Decimal | None
    open_count: int
    pending_count: int
    closed_count: int


@dataclass(frozen=True)
class ProviderRollup:
    """One provider's categories, grouped for the EOD table."""

    provider_name: str
    short_code: str
    categories: list[CategoryRollup]


def build_category_rollup(
    category: Category,
    stats: CategoryStats,
    day_chg_pct: Decimal | None,
    high_low: tuple[Decimal, Decimal] | None,
    open_count: int,
    pending_count: int,
    closed_count: int,
) -> CategoryRollup:
    """Assemble one category's EOD rollup from already-fetched MVPStore
    outputs (``get_category_stats``/``get_category_day_change``/
    ``get_category_high_low``, M13.1-13.3) plus pure pick-status counts.
    No I/O.
    """
    high_pct, low_pct = high_low if high_low is not None else (None, None)
    win_pct = stats.win_rate * 100 if stats.win_rate is not None else None
    return CategoryRollup(
        display_name=category.display_name,
        short_code=category_short_code(category.slug),
        invested=stats.invested,
        current=stats.current,
        realized_pnl=stats.inception_pnl,
        day_chg_pct=day_chg_pct,
        win_pct=win_pct,
        win_closed_count=stats.closed_count,
        inception_pct=stats.inception_pct if stats.inception_pct is not None else Decimal("0"),
        high_pct=high_pct,
        low_pct=low_pct,
        open_count=open_count,
        pending_count=pending_count,
        closed_count=closed_count,
    )


def _rollup_pnl(rollup: CategoryRollup) -> Decimal:
    """Realized + unrealized — booked P&L from closed picks plus
    mark-to-market on this category's currently open positions. Category
    rows and the all-recs footer total both use this same combined
    definition so the rows actually sum to the footer, unlike M12's
    deliberately open-only P&L."""
    return (rollup.current - rollup.invested) + rollup.realized_pnl


def compute_overall_inception_pct(
    categories: list[CategoryRollup], total_deployed: Decimal
) -> Decimal:
    """Since-inception % across every rec, realized + unrealized combined,
    over all-time deployed capital (not just currently-invested — closed
    picks' capital counts too). ``0`` when nothing has ever been deployed.
    """
    if not total_deployed:
        return Decimal("0")
    total_pnl = sum((_rollup_pnl(cat) for cat in categories), Decimal("0"))
    return total_pnl / total_deployed * 100


def build_eod_table(providers: list[ProviderRollup]) -> str:
    """Cat / P&L / Win% / Incep% / High / Low — one shared fenced table
    across every provider (category short_codes don't collide across
    providers, so no separate provider column is needed). Invested/Current
    deliberately excluded — this is a per-service scorecard, not a
    position-level view (``format_hourly_summary`` already covers that).
    """
    headers = ("Cat", "P&L", "Win%", "Incep%", "High", "Low")
    rows = []
    if not any(provider.categories for provider in providers):
        return ""
    for provider in providers:
        for cat in provider.categories:
            pnl = _rollup_pnl(cat)
            if cat.win_pct is None:
                win_str = f"— ({cat.win_closed_count})"
            else:
                win_str = f"{cat.win_pct:.0f}% ({cat.win_closed_count})"
            incep_sign = "+" if cat.inception_pct > 0 else ""
            if cat.high_pct is None:
                high_str = "—"
            else:
                high_sign = "+" if cat.high_pct > 0 else ""
                high_str = f"{high_sign}{cat.high_pct:.1f}%"
            if cat.low_pct is None:
                low_str = "—"
            else:
                low_sign = "+" if cat.low_pct > 0 else ""
                low_str = f"{low_sign}{cat.low_pct:.1f}%"
            rows.append(
                (
                    cat.short_code,
                    format_money(pnl, signed=True),
                    win_str,
                    f"{incep_sign}{cat.inception_pct:.1f}%",
                    high_str,
                    low_str,
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
    across every provider (see ``build_eod_table``) -> all-recommendations
    footer (P&L / Day chg / Inception / vs Nifty / Open-Pending-Closed
    counts).

    Args:
        benchmark_pct: MVP's since-inception return minus Nifty's over the
            same window (alpha). ``None`` omits the line — no live
            index-return series is wired up yet.

    Returns:
        Empty string if ``providers`` has no categories.
    """
    all_categories = [cat for p in providers for cat in p.categories]
    if not all_categories:
        return ""

    total_pnl = sum((_rollup_pnl(cat) for cat in all_categories), Decimal("0"))
    # Weighted only over categories with a day_chg_pct — a category with no
    # day-over-day figure yet (fewer than two snapshot days) must not pull
    # the average toward 0.
    weighted_day_chg = sum(
        (cat.day_chg_pct * cat.invested for cat in all_categories if cat.day_chg_pct is not None),
        Decimal("0"),
    )
    day_chg_weight = sum(
        (cat.invested for cat in all_categories if cat.day_chg_pct is not None), Decimal("0")
    )
    day_chg_pct = weighted_day_chg / day_chg_weight if day_chg_weight else None

    emoji = _headline_emoji(total_pnl)
    date_str = escape_markdown(run_date)

    lines = [f"{emoji} *MVP EOD Summary* \\| {date_str}", ""]
    lines.append("```")
    lines.append(build_eod_table(providers))
    lines.append("```")
    lines.append("")

    # No signed % shown alongside P&L here (unlike format_hourly_summary's
    # open-only P&L, which has a clean "pnl / invested" base): once
    # realized_pnl from closed picks is folded in, invested capital alone
    # is no longer the right denominator. Since inception %, below, is the
    # relative-return figure for this combined realized+unrealized scope.
    incep_sign = "+" if inception_pct > 0 else ""
    lines.append(
        f"\U0001f4b0 *All recs P&L:* {escape_markdown(format_money(total_pnl, signed=True))}"
    )
    if day_chg_pct is None:
        lines.append("\U0001f4c5 *Day chg:* —")
    else:
        day_sign = "+" if day_chg_pct > 0 else ""
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
