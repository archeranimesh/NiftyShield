"""EOD PT Summary — cross-strategy paper-trade summary as 1-3 Telegram messages.

Promoted from ``scratch/2026-08-13_eod_pt_summary.py`` (PT-2,
``docs/plan/eod-pt-summary/``). Function boundaries and every per-cell
derivation are unchanged from that validated prototype — this module only adds
type hints, docstrings and tests. Where this code and the story spec disagree,
the prototype (and therefore this port) wins.

The report runs *alongside* ``scripts/eod_summary.py`` (a coarser
``paper_nav_snapshots``-based digest), not as a replacement — the two read
different sources by design (Animesh, 2026-09-07).

``build_summary_parts`` returns 1, 2, or 3 strings, one per Telegram message:

1. ``EOD PT Summary`` — open positions across every registered paper strategy
   (always present; renders an empty-book line when there are none).
2. ``Closed Today`` — legs that fully closed (net_qty back to 0) on ``snap_date``;
   omitted entirely when nothing closed.
3. ``Summary — Strategy P&L / Ann.% on Margin`` — per-strategy P&L and annualized
   % on entry margin; present only when there was at least one open leg.

Non-fatal by contract: a broker LTP-fetch failure degrades affected rows to
``N/A`` rather than aborting, and a Telegram send failure on one message never
blocks the others or raises past the caller.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Protocol

import aiohttp
import structlog

from src.instruments.lookup import InstrumentLookup, parse_expiry
from src.models.portfolio import TradeAction
from src.notifications.formatting import build_position_table
from src.notifications.markdown import escape_markdown
from src.paper.constants import STRATEGY_OVERLAY
from src.paper.models import PaperPosition
from src.paper.store import PaperStore
from src.strategy.csp_nifty_v1 import CSPNiftyV1
from src.strategy.ic_expiry_config import CONFIGS as IC_V1_CONFIGS
from src.strategy.ic_expiry_config_v2 import CONFIGS_V2 as IC_V2_CONFIGS
from src.strategy.nifty_track_comparison_v1 import NiftyTrackComparisonV1

logger = structlog.get_logger(__name__)


class LtpProvider(Protocol):
    """The single broker surface this report needs — a batched last-traded-price fetch.

    ``BrokerClient`` / ``MarketDataProvider`` both satisfy this; so does the cron's
    zero-LTP mock fallback, without having to implement the wider protocol.
    """

    async def get_ltp(self, instruments: list[str]) -> dict[str, Decimal]: ...


# --- strategy_name -> friendly label -------------------------------------------------

# IC V1/V2 entries come from their CONFIGS dicts so the expiry_type wording stays a
# single source of truth.
_STRATEGY_LABELS: dict[str, str] = {
    cfg.strategy_name: (
        f"IC V1 {cfg.expiry_type.title()}" if cfg.expiry_type != "monthly" else "IC V1"
    )
    for cfg in IC_V1_CONFIGS.values()
}
_STRATEGY_LABELS.update({cfg.strategy_name: "IC V2" for cfg in IC_V2_CONFIGS.values()})
_STRATEGY_LABELS[CSPNiftyV1.strategy_name] = "CSP"

# 3-Track base legs persist under their own per-track strategy_name (not
# NiftyTrackComparisonV1.strategy_name, which is only the signal-registration
# umbrella). Confirmed against the live DB 2026-08-13.
_STRATEGY_LABELS["paper_nifty_spot"] = "Nifty Spot"
_STRATEGY_LABELS["paper_nifty_futures"] = "Nifty Future"
_STRATEGY_LABELS["paper_nifty_proxy"] = "Nifty Proxy"
if set(NiftyTrackComparisonV1.TRACK_STRATEGY_NAMES) != {
    "paper_nifty_spot",
    "paper_nifty_futures",
    "paper_nifty_proxy",
}:  # pragma: no cover - upstream-drift guard
    raise RuntimeError(
        "NiftyTrackComparisonV1.TRACK_STRATEGY_NAMES changed upstream — "
        "update the label map in src/reporting/eod_pt_summary.py."
    )

# CC/PP/Collar are NOT separate strategy_names — all three share STRATEGY_OVERLAY
# ("paper_nifty_overlay") and are split by leg_role prefix. The standalone
# STRATEGY_CC/PP/COLLAR_OVERLAY constants are stale for the live DB (S1r, 2026-07-29).
_OVERLAY_LEG_PREFIX_LABELS = {
    "overlay_cc": "CC",
    "overlay_pp": "PP",
    "overlay_collar": "Collar",  # covers overlay_collar_put / overlay_collar_call
}

_SIMPLE_STRATEGY_NAMES = list(_STRATEGY_LABELS)

# title-line prefix -> emoji (cosmetic, matches the repo's other Telegram messages).
_PART_EMOJI = {
    "EOD PT Summary": "📝",
    "Closed Today": "✅",
    "Summary —": "📊",
}

# (strategy, instrument, qty, avg, value, pnl, chg) formatted cells + raw P&L.
_Row = tuple[str, str, str, str, str, str, str, "Decimal | None"]
# Per-strategy rollup for the summary section: (pnl_sum, real_strategy_name,
# entry_date, any_leg_missing_ltp). real_strategy_name/entry_date key the margin
# lookup (CC/PP/Collar all key off STRATEGY_OVERLAY, not the friendly label).
_StrategyMeta = tuple[Decimal, str, "date | None", bool]


def _overlay_strategy_label(leg_role: str) -> str:
    """Friendly label for an overlay leg, by its ``leg_role`` prefix."""
    for prefix, label in _OVERLAY_LEG_PREFIX_LABELS.items():
        if leg_role.startswith(prefix):
            return label
    logger.warning("eod_pt_summary.unknown_overlay_leg_role", leg_role=leg_role)
    return "Overlay (?)"


def _part_emoji(title_line: str) -> str:
    """Emoji prefix for a message, matched on its title line."""
    for prefix, emoji in _PART_EMOJI.items():
        if title_line.startswith(prefix):
            return emoji
    return "📋"


def _entry_price(pos: PaperPosition) -> Decimal:
    """Entry price to display and compare against LTP.

    Short (``net_qty < 0``) uses ``avg_sell_price``; long uses ``avg_cost``.
    """
    return pos.avg_sell_price if pos.net_qty < 0 else pos.avg_cost


def _pnl_rupees(pos: PaperPosition, ltp: Decimal | None) -> Decimal | None:
    """Signed rupee P&L for one open leg, or ``None`` when LTP is missing.

    No ``LOT_SIZE`` multiplier for any instrument type — ``net_qty`` is already
    the raw traded unit count off ``paper_trades.quantity`` (a 1-lot leg is
    stored as 65). An earlier prototype multiplied by ``LOT_SIZE`` on top and
    inflated P&L 65x across every non-equity row; do not reintroduce it.

    Args:
        pos: The open position.
        ltp: Live mark, or ``None`` if the fetch failed.

    Returns:
        Signed P&L in rupees, or ``None`` when ``ltp`` is ``None``.
    """
    if ltp is None:
        return None
    entry = _entry_price(pos)
    if pos.net_qty < 0:
        return (entry - ltp) * abs(pos.net_qty)
    return (ltp - entry) * pos.net_qty


def _chg_pct(entry: Decimal, ltp: Decimal | None) -> Decimal | None:
    """Price move of ``ltp`` vs ``entry`` as a percent (not P&L%, qty-sign independent).

    Returns ``None`` when ``ltp`` is missing or ``entry`` is zero.
    """
    if ltp is None or entry == 0:
        return None
    return (ltp - entry) / entry * Decimal("100")


def _fmt_money(val: Decimal | None) -> str:
    """``1,234.50`` grouping, or ``N/A`` for ``None``."""
    return f"{val:,.2f}" if val is not None else "N/A"


def _fmt_pct(val: Decimal | None) -> str:
    """``+1.23%`` (signed), or ``N/A`` for ``None``."""
    return f"{val:+.2f}%" if val is not None else "N/A"


def _fmt_qty(qty: int) -> str:
    """Signed ``net_qty`` with comma thousands separators, matching the other columns."""
    return f"{qty:,}"


def _fmt_expiry_label(expiry_iso: str | None) -> str:
    """``"2026-08-25"`` -> ``"25 AUG 26"``; a non-ISO value passes through unchanged."""
    if not expiry_iso:
        return ""
    try:
        return date.fromisoformat(expiry_iso).strftime("%d %b %y").upper()
    except ValueError:
        return expiry_iso


def _instrument_label(instrument_key: str, lookup: InstrumentLookup) -> tuple[str, str]:
    """Human label + type hint for one ``instrument_key``.

    Returns ``(label, type_hint)`` where ``type_hint`` is ``""`` for
    options/unresolved, ``"equity"`` or ``"future"`` for 3-Track base legs.

    Options render ``"<underlying> <strike> <expiry> <CE/PE>"`` — CE/PE **last**.
    This is a deliberate one-off deviation from the repo-wide
    ``format_option_label()`` order (``<underlying> <strike> <CE/PE> <expiry>``);
    the canonical helper has no field-order option, so the label is built here.
    A missing strike logs a warning and degrades to the raw key (same fallback
    contract as ``format_leg_label``).
    """
    inst = lookup.get_by_key(instrument_key)
    if inst is None:
        return instrument_key, ""

    instrument_type = inst.get("instrument_type")
    if instrument_type in ("CE", "PE"):
        underlying = inst.get("underlying_symbol") or inst.get("name") or "NIFTY"
        strike = inst.get("strike_price")
        strike_str = ""
        if strike is not None:
            strike_dec = Decimal(str(strike))
            strike_str = (
                str(int(strike_dec))
                if strike_dec == strike_dec.to_integral_value()
                else str(strike_dec)
            )
        expiry_str = _fmt_expiry_label(parse_expiry(inst.get("expiry")))
        if not strike_str:
            logger.warning("eod_pt_summary.missing_strike", instrument_key=instrument_key)
            return instrument_key, ""
        return f"{underlying} {strike_str} {expiry_str} {instrument_type}", ""

    if instrument_type == "FUT":
        underlying = inst.get("underlying_symbol") or inst.get("name") or "NIFTY"
        expiry_str = _fmt_expiry_label(parse_expiry(inst.get("expiry")))
        return f"{underlying} FUT {expiry_str}", "future"

    if instrument_type == "EQ":
        symbol = inst.get("trading_symbol") or inst.get("underlying_symbol") or instrument_key
        return str(symbol), "equity"

    return instrument_key, ""


async def _collect_rows(
    store: PaperStore,
    broker: LtpProvider,
    lookup: InstrumentLookup,
) -> tuple[list[_Row], Decimal, bool, dict[str, _StrategyMeta]]:
    """Gather one row per open leg across every registered paper strategy.

    Returns ``(rows, total_pnl, any_pnl_missing, strategy_meta)``. A single
    batched ``broker.get_ltp`` call covers every open key; a fetch exception is
    logged and leaves every LTP ``None`` (rows degrade to ``N/A``, non-fatal).
    """
    entries: list[tuple[str, PaperPosition, str, str]] = []

    for strategy_name in _SIMPLE_STRATEGY_NAMES:
        for pos in store.get_positions(strategy_name):
            if pos.net_qty == 0:
                continue
            label, type_hint = _instrument_label(pos.instrument_key, lookup)
            entries.append((_STRATEGY_LABELS[strategy_name], pos, label, type_hint))

    for pos in store.get_positions(STRATEGY_OVERLAY):
        if pos.net_qty == 0:
            continue
        label, type_hint = _instrument_label(pos.instrument_key, lookup)
        entries.append((_overlay_strategy_label(pos.leg_role), pos, label, type_hint))

    if not entries:
        return [], Decimal("0"), False, {}

    all_keys = sorted({pos.instrument_key for _, pos, _, _ in entries})
    try:
        ltp_map = await broker.get_ltp(all_keys)
    except Exception as exc:  # Intentional: fail-safe LTP fetch, non-fatal
        logger.error("eod_pt_summary.ltp_fetch_failed", error=str(exc))
        ltp_map = {}

    rows: list[_Row] = []
    total_pnl = Decimal("0")
    any_pnl_missing = False
    strategy_meta: dict[str, _StrategyMeta] = {}

    for strategy_label, pos, label, _type_hint in entries:
        ltp = ltp_map.get(pos.instrument_key)
        entry = _entry_price(pos)
        pnl = _pnl_rupees(pos, ltp)
        chg = _chg_pct(entry, ltp)

        if pnl is None:
            any_pnl_missing = True
        else:
            total_pnl += pnl

        rows.append(
            (
                strategy_label,
                label,
                _fmt_qty(pos.net_qty),
                _fmt_money(entry),
                _fmt_money(ltp),
                _fmt_money(pnl),
                _fmt_pct(chg),
                pnl,
            )
        )

        prev_pnl, prev_name, prev_entry_date, prev_missing = strategy_meta.get(
            strategy_label, (Decimal("0"), pos.strategy_name, pos.entry_date, False)
        )
        strategy_meta[strategy_label] = (
            prev_pnl + (pnl if pnl is not None else Decimal("0")),
            prev_name,
            prev_entry_date,
            prev_missing or pnl is None,
        )

    return rows, total_pnl, any_pnl_missing, strategy_meta


def _closed_legs_for_strategy(
    store: PaperStore, strategy_name: str, snap_date: date
) -> list[tuple[str, str, int, Decimal, Decimal, date]]:
    """Replay full trade history for one strategy; find legs that fully closed on ``snap_date``.

    ``get_positions()`` only surfaces currently-open net positions, so a leg that
    closed today is otherwise invisible. This groups all trades by
    ``(leg_role, instrument_key)``, runs the same net_qty-cycle accounting
    ``get_positions()`` does internally (cycle resets when ``net_qty`` hits 0),
    and emits a row for any cycle whose closing trade landed on ``snap_date`` and
    returned ``net_qty`` to exactly 0. Partial closes are not reported — a
    reduced-but-nonzero ``net_qty`` is still an open position.

    Returns:
        ``(leg_role, instrument_key, qty_signed, entry_price, exit_price,
        close_date)`` per closed cycle; ``qty_signed`` is negative when the
        position was short, matching ``PaperPosition.net_qty``'s sign convention.
    """
    trades = store.get_trades(strategy_name)
    by_leg: dict[tuple[str, str], list] = defaultdict(list)
    for t in trades:
        by_leg[(t.leg_role, t.instrument_key)].append(t)

    closed: list[tuple[str, str, int, Decimal, Decimal, date]] = []

    for (leg_role, instrument_key), leg_trades in by_leg.items():
        net_qty = 0
        opening_action: TradeAction | None = None
        cycle_start_date: date | None = None
        buy_qty = 0
        buy_cost = Decimal("0")
        sell_qty = 0
        sell_cost = Decimal("0")

        for t in leg_trades:  # already ordered by trade_date, id (PaperStore.get_trades)
            if net_qty == 0:
                opening_action = t.action
                cycle_start_date = t.trade_date
                buy_qty, buy_cost, sell_qty, sell_cost = 0, Decimal("0"), 0, Decimal("0")

            if t.action == TradeAction.BUY:
                net_qty += t.quantity
                buy_qty += t.quantity
                buy_cost += t.price * t.quantity
            else:
                net_qty -= t.quantity
                sell_qty += t.quantity
                sell_cost += t.price * t.quantity

            if net_qty == 0 and t.trade_date == snap_date and (buy_qty or sell_qty):
                if opening_action == TradeAction.SELL:  # was short
                    entry_price = sell_cost / sell_qty if sell_qty else Decimal("0")
                    exit_price = buy_cost / buy_qty if buy_qty else Decimal("0")
                    qty_signed = -sell_qty
                else:  # was long
                    entry_price = buy_cost / buy_qty if buy_qty else Decimal("0")
                    exit_price = sell_cost / sell_qty if sell_qty else Decimal("0")
                    qty_signed = buy_qty
                assert cycle_start_date is not None  # set on cycle open above
                closed.append(
                    (
                        leg_role,
                        instrument_key,
                        qty_signed,
                        entry_price,
                        exit_price,
                        cycle_start_date,
                    )
                )

    return closed


def _collect_closed_rows(
    store: PaperStore,
    lookup: InstrumentLookup,
    snap_date: date,
) -> tuple[list[_Row], Decimal]:
    """Same row shape as ``_collect_rows``, for legs closed exactly on ``snap_date``.

    No broker dependency — entry/exit are both realized prices already in
    ``paper_trades``, so P&L here is exact. The 5th cell is the realized exit
    price rather than a live LTP.
    """
    rows: list[_Row] = []
    total_pnl = Decimal("0")

    def _closed_row(strategy_label: str, leg: tuple[str, str, int, Decimal, Decimal, date]) -> None:
        nonlocal total_pnl
        _leg_role, instrument_key, qty_signed, entry, exit_price, _close_date = leg
        label, _type_hint = _instrument_label(instrument_key, lookup)
        pnl = (
            (entry - exit_price) * abs(qty_signed)
            if qty_signed < 0
            else (exit_price - entry) * qty_signed
        )
        chg = _chg_pct(entry, exit_price)
        total_pnl += pnl
        rows.append(
            (
                strategy_label,
                label,
                _fmt_qty(qty_signed),
                _fmt_money(entry),
                _fmt_money(exit_price),
                _fmt_money(pnl),
                _fmt_pct(chg),
                pnl,
            )
        )

    for strategy_name in _SIMPLE_STRATEGY_NAMES:
        for leg in _closed_legs_for_strategy(store, strategy_name, snap_date):
            _closed_row(_STRATEGY_LABELS[strategy_name], leg)

    for leg in _closed_legs_for_strategy(store, STRATEGY_OVERLAY, snap_date):
        _closed_row(_overlay_strategy_label(leg[0]), leg)

    return rows, total_pnl


def _render_summary(
    store: PaperStore,
    strategy_meta: dict[str, _StrategyMeta],
    total_pnl: Decimal,
    snap_date: date,
) -> str:
    """Render the per-strategy P&L / annualized-%-on-margin table.

    ``ann_pct = (pnl / final_margin) * (365 / days_held) * 100`` — simple
    annualization. ``paper_margin_snapshots`` is populated for IC V1/V2 only, so
    CSP, the overlays and 3-Track render ``N/A`` for Margin/Ann.% (never a
    substituted estimate). Ann.% is also ``N/A`` when ``final_margin <= 0`` or
    ``days_held <= 0``. Returns ``""`` when there were no open legs.
    """
    if not strategy_meta:
        return ""

    headers = ("Strategy", "P&L", "Margin", "Ann.%")
    right_align = (False, True, True, True)
    rows: list[tuple[str, str, str, str]] = []

    for strategy_label, (
        pnl,
        strategy_name,
        entry_date,
        group_pnl_missing,
    ) in strategy_meta.items():
        margin_str = "N/A"
        ann_str = "N/A"

        if entry_date is not None:
            try:
                snapshot = store.get_margin_snapshot(strategy_name, entry_date)
            except Exception as exc:  # Intentional: fail-safe margin lookup, non-fatal
                logger.warning(
                    "eod_pt_summary.margin_lookup_failed",
                    strategy_name=strategy_name,
                    error=str(exc),
                )
                snapshot = None

            if snapshot is not None and snapshot.final_margin > Decimal("0"):
                margin_str = _fmt_money(snapshot.final_margin)
                days_held = (snap_date - entry_date).days
                if days_held > 0:
                    ann_pct = (
                        (pnl / snapshot.final_margin)
                        * (Decimal("365") / days_held)
                        * Decimal("100")
                    )
                    ann_str = _fmt_pct(ann_pct)

        pnl_str = _fmt_money(pnl) + ("*" if group_pnl_missing else "")
        rows.append((strategy_label, pnl_str, margin_str, ann_str))

    total_row = ("TOTAL", _fmt_money(total_pnl), "", "")
    display_rows = [*rows, total_row]
    widths = [max(len(headers[i]), *(len(r[i]) for r in display_rows)) for i in range(len(headers))]

    def _line(cells: tuple[str, ...]) -> str:
        return "  ".join(
            cells[i].rjust(widths[i]) if right_align[i] else cells[i].ljust(widths[i])
            for i in range(len(cells))
        )

    sep = _line(tuple("-" * w for w in widths))
    lines = ["Summary — Strategy P&L / Ann.% on Margin", "", _line(headers), sep]
    lines.extend(_line(r) for r in rows)
    lines.append(sep)
    lines.append(_line(total_row))
    if any(missing for _, (_, _, _, missing) in strategy_meta.items()):
        lines.append("")
        lines.append("(* — partial: one or more legs missing LTP, P&L understated)")

    return "\n".join(lines)


async def build_summary_parts(
    store: PaperStore,
    broker: LtpProvider,
    lookup: InstrumentLookup,
    snap_date: date,
) -> list[str]:
    """Build the 1-3 message bodies, one string per Telegram message.

    Message 1 (open positions) is always present. Message 2 (``Closed Today``) is
    included only when at least one leg fully closed on ``snap_date``. Message 3
    (the P&L/Ann.% summary) is included only when there was at least one open leg.
    """
    rows, total_pnl, any_pnl_missing, strategy_meta = await _collect_rows(store, broker, lookup)
    parts = [
        build_position_table(
            rows,
            total_pnl,
            any_pnl_missing,
            title=f"EOD PT Summary — {snap_date.isoformat()}",
            empty_message="no open positions across any paper strategy.",
        )
    ]

    closed_rows, closed_total_pnl = _collect_closed_rows(store, lookup, snap_date)
    if closed_rows:
        parts.append(
            build_position_table(
                closed_rows,
                closed_total_pnl,
                any_pnl_missing=False,
                title=f"Closed Today — {snap_date.isoformat()}",
                empty_message="",
                value_header="Exit",
            )
        )

    summary = _render_summary(store, strategy_meta, total_pnl, snap_date)
    if summary:
        parts.append(summary)

    return parts


async def send_telegram_markdown(bot_token: str, chat_id: str, part: str) -> bool:
    """Send one message part as MarkdownV2 and return whether Telegram confirmed it.

    The title line (with an emoji prefix) is escaped and kept outside the fence;
    everything after it goes inside a fenced code block, where MarkdownV2 does not
    parse entities. A non-200 response logs Telegram's ``description`` and returns
    ``False``; any exception is logged and returns ``False``. Never raises past
    the caller — the repo-wide non-fatal Telegram contract.

    Raw ``aiohttp`` POST rather than ``TelegramGateway`` (HTML-only, wrong fence
    semantics for a table).

    TODO(telegram-markdown-migration): replace with the shared transport helper
    once ``backbone/`` ships one for raw MarkdownV2 sends.
    """
    title_line, _, body = part.partition("\n")
    header = escape_markdown(f"{_part_emoji(title_line)} {title_line}")
    md_message = f"{header}\n```{body}\n```"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(
                url,
                json={"chat_id": chat_id, "text": md_message, "parse_mode": "MarkdownV2"},
            ) as resp:
                body_json = await resp.json()
                if resp.status != 200:
                    logger.warning(
                        "eod_pt_summary.telegram_failed",
                        status=resp.status,
                        description=body_json.get("description"),
                        title=title_line,
                    )
                    return False
                logger.info("eod_pt_summary.telegram_sent", title=title_line)
                return True
    except Exception as exc:  # Intentional: fail-safe delivery, non-fatal
        logger.warning("eod_pt_summary.telegram_failed", error=str(exc), title=title_line)
        return False
