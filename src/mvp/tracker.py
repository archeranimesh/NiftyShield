"""Pure MVP pick tracking logic: price-breach detection."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from src.mvp.models import Pick, PickStatus
from src.notifications.formatting import format_pct
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


def _format_row(pick: Pick, ltp_map: dict[str, Decimal]) -> str:
    """One fenced-table row: SYMBOL entry->ltp pct% T:target (away% away) SL:sl."""
    ltp = ltp_map.get(pick.instrument_key) if pick.instrument_key is not None else None

    parts = [pick.symbol, f"{_format_num(pick.entry_price)}→{_format_num(ltp)}"]

    entry = pick.entry_price
    if ltp is not None and entry is not None and entry != 0:
        pct = (ltp - entry) / entry * 100
        sign = "+" if pct > 0 else ""
        parts.append(f"{sign}{format_pct(float(pct))}")
    else:
        parts.append("—")

    if pick.target_price is not None:
        if ltp is not None and ltp != 0:
            away = abs((pick.target_price - ltp) / ltp * 100)
            away_str = format_pct(float(away))
            parts.append(f"T:{_format_num(pick.target_price)} ({away_str} away)")
        else:
            parts.append(f"T:{_format_num(pick.target_price)}")

    if pick.stop_loss is not None:
        parts.append(f"SL:{_format_num(pick.stop_loss)}")

    return "  " + "  ".join(parts)


def format_telegram_summary(
    picks: list[Pick],
    ltp_map: dict[str, Decimal],
    providers: dict[str, str],
    categories: dict[str, str],
    run_time: str,
) -> str:
    """Build the hourly MVP watch summary as a MarkdownV2 message body.

    Args:
        picks: Picks to consider. OPEN picks with an entry_price and a
            category are grouped into fenced tables; PENDING picks and any
            pick missing a category or entry_price fall into the trailing
            "Unassigned (PENDING)" block, listed by symbol only. Any other
            status is excluded.
        ltp_map: Last traded price keyed by instrument_key. A pick whose
            instrument_key is absent (or None) renders "—" for ltp and P&L —
            this pure function has no snapshot history to fall back to.
        providers: provider_id -> display_name. Not consulted directly:
            `categories` values are the caller-joined "Provider / Category"
            label, kept only for interface parity.
        categories: category_id -> display_name (caller-joined "Provider /
            Category" label), used as the group header.
        run_time: Display string for the run header, e.g. "11:00 AM".

    Returns:
        A MarkdownV2-formatted message body, escaped outside fences per
        FORMATTING.md §6 (row content sits inside fences and is left
        verbatim). Empty string if `picks` is empty or nothing qualifies.
        Pure function: no I/O.
    """
    del providers

    groups: dict[str, list[Pick]] = defaultdict(list)
    unassigned: list[Pick] = []

    for pick in picks:
        if pick.status not in (PickStatus.OPEN, PickStatus.PENDING):
            continue
        if (
            pick.status == PickStatus.PENDING
            or pick.entry_price is None
            or pick.category_id is None
        ):
            unassigned.append(pick)
        else:
            groups[pick.category_id].append(pick)

    if not groups and not unassigned:
        return ""

    lines = [f"\U0001f4ca *MVP Watch — {escape_markdown(run_time)}*", ""]

    for category_id, group_picks in groups.items():
        header = categories.get(category_id, category_id)
        lines.append(f"*{escape_markdown(header)}*")
        lines.append("```")
        lines.extend(_format_row(pick, ltp_map) for pick in group_picks)
        lines.append("```")
        lines.append("")

    if unassigned:
        lines.append(f"*{escape_markdown('Unassigned (PENDING)')}*")
        lines.append(f"  {escape_markdown(', '.join(pick.symbol for pick in unassigned))}")
        lines.append("")

    return "\n".join(lines).rstrip("\n")
