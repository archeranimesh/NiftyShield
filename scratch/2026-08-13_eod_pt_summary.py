# scratch/2026-08-13_eod_pt_summary.py
"""Scratch: EOD PT Summary — cross-strategy paper-trade summary table.

Throwaway prototype per docs/plan/telegram-markdown-migration/README.md's
message-format-workshop convention — confirm the table shape here before it
gets promoted into real `src/notifications/` code.

Scope: every currently-registered paper strategy with open positions —
IC V1 (weekly/monthly/leaps/yearly), IC V2 (monthly), CSP, CC, PP, Collar,
and the Nifty 3-Track base legs. Not the full IC EOD Audit report
(credit/mark/captured/ROI/margin/alerts/actions) — just the positions
table, per Animesh's "not the complete just the positions" note.

Two strategy_name traps this script had to work around (both confirmed
against the live DB via a direct sqlite3 query, 2026-08-13 — not assumed
from the class-level defaults, which turned out stale for one of them):

  1. 3-Track base legs are NOT one umbrella strategy_name split by leg —
     NiftyTrackComparisonV1.strategy_name ("paper_nifty_3track_v1") is only
     the signal-registration name; TRACK_STRATEGY_NAMES shows each track
     actually persists under its own strategy_name ("paper_nifty_spot" /
     "paper_nifty_futures" / "paper_nifty_proxy"), mapped straight to
     "Nifty Spot"/"Nifty Future"/"Nifty Proxy" rows.
  2. CC/PP/Collar are NOT separate strategy_names either, despite
     cc_overlay_v1.py / pp_overlay_v1.py / collar_overlay_v1.py each
     defaulting `strategy_name` to the standalone STRATEGY_CC_OVERLAY /
     STRATEGY_PP_OVERLAY / STRATEGY_COLLAR_OVERLAY constants — those three
     are stale in this live DB. Per src/paper/constants.py's
     STRATEGY_OVERLAY comment (S1r, 2026-07-29, SHA 8c41cca), all three
     overlay types share one strategy_name, STRATEGY_OVERLAY
     ("paper_nifty_overlay"), distinguished by leg_role prefix instead
     (overlay_cc / overlay_pp / overlay_collar_put / overlay_collar_call).
     This was the actual cause of CC/PP/Collar rows being silently empty
     in the previous version of this script.

Layout, 2026-08-13 revision history (most recent first):
  - Split into 3 SEPARATE Telegram messages instead of 1 combined message with
    3 sections, per Animesh's request — see docs/plan/eod-pt-summary/stories.md
    PT-1 for the full spec. build_summary_parts() now returns list[str] (one
    string per message) instead of build_summary_table()'s single joined
    string; _run() sends each part as its own _send_telegram_markdown() call.
    "Closed Today" is still omitted on days nothing closed (2 messages sent
    instead of 3, never a 3rd message announcing zero closes).
  - Added a "Closed Today" table — same 7-column shape as the open-positions
    table, for legs that fully closed (net_qty back to 0) exactly on
    snap_date, e.g. the "IC closed — CLOSE_FULL" notification Animesh
    pasted. get_positions()/get_trades() only ever surface currently-OPEN
    net positions, so a fully-closed leg is otherwise invisible in this
    script entirely — it just silently drops out of the open table with no
    trace. See _closed_legs_for_strategy()'s docstring for how this replays
    trade history to find it, and its "partial closes are NOT reported
    here" caveat (a partial close still shows in the open table with a
    smaller Qty — only a full round-trip counts as "closed"). Omitted
    entirely from the message when nothing closed that day (most days).
  - Reverted the "subtable per strategy" restructure — Animesh: "previous
    version was better" — back to one flat table with a Strategy column.
    What he actually wanted was a trailing summary section, not the main
    table restructured; see _render_summary() below.
  - Added a trailing "Summary — Strategy P&L / Ann.% on Margin" section:
    one row per strategy with total P&L and annualized % return on margin
    (365 / days_held simple annualization, not compounded). Margin comes
    from PaperStore.get_margin_snapshot() and is only populated for IC
    V1/V2 today — every other strategy shows Margin/Ann.%="N/A" rather
    than guessing (see _render_summary() docstring). Scoped to OPEN
    positions only — today's realized closes are NOT folded into this
    summary's P&L/margin figures, to avoid conflating unrealized
    mark-to-market with realized round-trip P&L under one number.

Main table columns (open AND closed-today, same shape):
    Strategy | Instrument | Qty | Avg | LTP (open) / Exit (closed) | P&L | Chg

Summary section columns:
    Strategy | P&L | Margin | Ann.%

Mapping from PaperStore data:
    - Strategy: friendly label from _STRATEGY_LABELS, keyed by
      PaperPosition.strategy_name. 3-Track splits per-leg by instrument_type
      (EQ → "Nifty Spot", FUT → "Nifty Future") since it holds both under one
      strategy_name.
    - Instrument: "<NIFTY> <strike> <expiry> <CE/PE>" — CE/PE deliberately
      LAST, per Animesh's 2026-08-13 request. This is a one-off deviation
      from the repo-wide standard set by format_leg_label()/
      format_option_label() (src/instruments/lookup.py, TL-1..TL-4
      telegram-leg-labels epic — "<underlying> <strike> <CE/PE> <expiry>",
      used everywhere else: IC audit, close/roll/entry notifications).
      Built locally in _instrument_label() rather than calling the canonical
      helper, since it doesn't expose a field-order option. FUT/EQ legs
      (3-Track) use their own local resolver too, same as before.
    - Qty: PaperPosition.net_qty (signed: negative = net short).
    - Avg: entry price for the position's dominant side — avg_sell_price
      when net_qty < 0 (short), avg_cost when net_qty > 0 (long).
    - LTP: live mark via BrokerClient.get_ltp() — one batched call across
      every open instrument_key in this pass (works uniformly for
      options/futures/equity, unlike a per-strategy option-chain fetch).
    - P&L: signed rupee P&L, price-diff * net_qty directly — net_qty is
      already the raw traded unit count (paper_trades.quantity), not a lot
      count, for every strategy including options/futures, so no separate
      LOT_SIZE multiplier is applied anywhere (see _pnl_rupees docstring for
      why an earlier version of this script got this wrong).
    - Chg: (LTP - Avg) / Avg * 100 — pure price move, not P&L% (verified
      against Animesh's broker screenshot: 330.50 → 247.35 is exactly
      -25.16%, i.e. LTP vs Avg, independent of qty sign).

Non-fatal by design (matches TelegramNotifier.send()'s contract elsewhere
in this repo): a broker fetch failure for one strategy's LTPs degrades that
row to "N/A" rather than aborting the whole summary.

Alignment: Strategy/Instrument stay left-justified (variable-length prose);
Qty/Avg/LTP/P&L/Chg are right-justified (fixed-point numbers read naturally
right-aligned — matches the broker "Positions" screenshot Animesh shared and
standard terminal-table convention).

Sending: prints every part to stdout always. Sends each part as its OWN Telegram
message via a raw aiohttp POST with parse_mode=MarkdownV2 (backbone/ MD-1..MD-5,
the escaping helper + transport switch, hasn't shipped yet — see
docs/plan/telegram-markdown-migration/backbone/), same as the other
message-format-workshop scratch scripts in this folder that already send
MarkdownV2 directly (2026-08-08_eod_paper_summary_format.py,
2026-08-07_ic_eod_audit_v2_telegram_format.py) rather than going through
TelegramGateway.send_notification() (still HTML-only, wrong fence
semantics for a table). escape_markdown()/mdcode() below are inlined
verbatim copies of that pattern per those scripts' own comments ("port
verbatim once backbone/ lands") — each message's table lives inside its own
fenced code block, where MarkdownV2 does not parse entities, so only that
message's title line (outside the fence) needs escaping. Needs
TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID set (.env) or it prints a warning and
skips the send. Each of the (2 or 3) sends is independent — one failing
(e.g. rate-limited) does not block the others.

Run:
    python scratch/2026-08-13_eod_pt_summary.py             # print only
    python scratch/2026-08-13_eod_pt_summary.py --send      # print + send 2-3 Telegram messages
"""

# fmt: off
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import aiohttp
import structlog
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.client.factory import create_client
from src.config import settings
from src.instruments.lookup import InstrumentLookup, parse_expiry
from src.models.portfolio import TradeAction
from src.paper.constants import (
    DEFAULT_BOD_PATH,
    DEFAULT_DB_PATH,
    STRATEGY_OVERLAY,
)
from src.paper.store import PaperPosition, PaperStore
from src.strategy.csp_nifty_v1 import CSPNiftyV1
from src.strategy.ic_expiry_config import CONFIGS as IC_V1_CONFIGS
from src.strategy.ic_expiry_config_v2 import CONFIGS_V2 as IC_V2_CONFIGS
from src.strategy.nifty_track_comparison_v1 import NiftyTrackComparisonV1
from src.utils.logging import setup_logging

load_dotenv()

_SCRIPT_NAME = "scratch.eod_pt_summary"
logger = structlog.get_logger(_SCRIPT_NAME)

# --- inlined MD-1 helpers (backbone/ not shipped yet; port verbatim once it lands —
# same inline copy pattern used by 2026-08-08_eod_paper_summary_format.py) ---

MARKDOWNV2_RESERVED = "_*[]()~`>#+-=|{}.!"


def escape_markdown(text: str) -> str:
    """Backslash-escape MarkdownV2 reserved characters in free text (header/footer prose only —
    never applied inside the fenced table, where MarkdownV2 does not parse entities)."""
    return "".join(f"\\{ch}" if ch in MARKDOWNV2_RESERVED else ch for ch in text)


# strategy_name -> friendly label. IC V1/V2 entries added below from their
# CONFIGS dicts so the expiry_type wording stays a single source of truth.
_STRATEGY_LABELS: dict[str, str] = {
    cfg.strategy_name: f"IC V1 {cfg.expiry_type.title()}" if cfg.expiry_type != "monthly" else "IC V1"
    for cfg in IC_V1_CONFIGS.values()
}
_STRATEGY_LABELS.update(
    {cfg.strategy_name: "IC V2" for cfg in IC_V2_CONFIGS.values()}
)
_STRATEGY_LABELS[CSPNiftyV1.strategy_name] = "CSP"

# 3-Track base legs are NOT stored under NiftyTrackComparisonV1.strategy_name
# (that's just the umbrella name used for signal registration) — each track
# writes to its own strategy_name per TRACK_STRATEGY_NAMES. Map those directly.
_STRATEGY_LABELS["paper_nifty_spot"] = "Nifty Spot"
_STRATEGY_LABELS["paper_nifty_futures"] = "Nifty Future"
_STRATEGY_LABELS["paper_nifty_proxy"] = "Nifty Proxy"
assert set(NiftyTrackComparisonV1.TRACK_STRATEGY_NAMES) == {
    "paper_nifty_spot",
    "paper_nifty_futures",
    "paper_nifty_proxy",
}, "TRACK_STRATEGY_NAMES changed upstream — update the label map above."

# CC/PP/Collar are NOT separate strategy_names despite cc_overlay_v1.py /
# pp_overlay_v1.py / collar_overlay_v1.py each defaulting `strategy_name` to
# the standalone STRATEGY_CC_OVERLAY/STRATEGY_PP_OVERLAY/STRATEGY_COLLAR_OVERLAY
# constants in src/paper/constants.py — those three are stale for this live DB.
# Per src/paper/constants.py's STRATEGY_OVERLAY comment (S1r, 2026-07-29, SHA
# 8c41cca): all three overlay types share one strategy_name, STRATEGY_OVERLAY
# ("paper_nifty_overlay"), distinguished by leg_role prefix instead
# (overlay_cc / overlay_pp / overlay_collar_put / overlay_collar_call).
# Confirmed against the live DB directly (sqlite3 paper_trades query,
# 2026-08-13) — this data-vs-constants mismatch is why CC/PP/Collar rows
# were silently empty in the previous version of this script.
_OVERLAY_LEG_PREFIX_LABELS = {
    "overlay_cc": "CC",
    "overlay_pp": "PP",
    "overlay_collar": "Collar",  # covers both overlay_collar_put / overlay_collar_call
}


def _overlay_strategy_label(leg_role: str) -> str:
    for prefix, label in _OVERLAY_LEG_PREFIX_LABELS.items():
        if leg_role.startswith(prefix):
            return label
    logger.warning("eod_pt_summary.unknown_overlay_leg_role", leg_role=leg_role)
    return "Overlay (?)"


_SIMPLE_STRATEGY_NAMES = list(_STRATEGY_LABELS)


def _entry_price(pos: PaperPosition) -> Decimal:
    """Entry price to display/compare against LTP.

    Short (net_qty < 0) → avg_sell_price. Long (net_qty > 0) → avg_cost.
    """
    return pos.avg_sell_price if pos.net_qty < 0 else pos.avg_cost


def _pnl_rupees(pos: PaperPosition, ltp: Decimal | None) -> Decimal | None:
    """Signed rupee P&L.

    No LOT_SIZE multiplier here, for any instrument type — net_qty is already
    the raw traded unit count straight off paper_trades.quantity, not a lot
    count. Confirmed directly against the live DB (2026-08-13): a 1-lot IC/
    overlay/futures/proxy leg is stored as quantity=65 (LOT_SIZE), i.e.
    net_qty=±65 already, and NIFTYBEES equity legs store actual share counts
    (e.g. 5735). A previous version of this function multiplied by LOT_SIZE
    on top of net_qty for every non-equity row — that inflated P&L by
    LOT_SIZE (65x) across IC/CC/PP/Collar/CSP/Future/Proxy, not just
    Future/Proxy as originally flagged. IronCondorV2._compute_combined_pnl's
    own `* LOT_SIZE` (paper_ic_snapshot.py) is not the same computation: that
    path sums *per-unit* prices across legs (never multiplies by qty) and
    assumes exactly one lot per leg, so it needs `* LOT_SIZE` once at the end
    — it doesn't generalize to this function, which starts from net_qty
    directly. Do not reintroduce a LOT_SIZE multiplier here.
    """
    if ltp is None:
        return None
    entry = _entry_price(pos)
    if pos.net_qty < 0:
        return (entry - ltp) * abs(pos.net_qty)
    return (ltp - entry) * pos.net_qty


def _chg_pct(entry: Decimal, ltp: Decimal | None) -> Decimal | None:
    """Price change % of LTP vs entry (not P&L%)."""
    if ltp is None or entry == 0:
        return None
    return (ltp - entry) / entry * Decimal("100")


def _fmt_money(val: Decimal | None) -> str:
    return f"{val:,.2f}" if val is not None else "N/A"


def _fmt_pct(val: Decimal | None) -> str:
    return f"{val:+.2f}%" if val is not None else "N/A"


def _fmt_qty(qty: int) -> str:
    """Signed net_qty with comma thousands-sep, matching Avg/LTP/P&L's grouping.

    Consistency fix (2026-08-17, workshop cross-check against
    docs/plan/telegram-markdown-migration/ ROLL-1): net_qty was previously
    rendered via bare str(pos.net_qty), which drops the thousands separator
    every other numeric column in this table already has (e.g. "5735" next
    to "24,655.00") — this makes the >=1,000-share NIFTYBEES row misaligned
    in spirit with its neighbors even though the columns still line up
    character-for-character. Does not change sign display (net_qty is
    already negative for short positions via Python's default str()).
    """
    return f"{qty:,}"


def _fmt_expiry_label(expiry_iso: str | None) -> str:
    """"2026-08-25" -> "25 AUG 26", matching format_option_label()'s date style."""
    if not expiry_iso:
        return ""
    try:
        return date.fromisoformat(expiry_iso).strftime("%d %b %y").upper()
    except ValueError:
        return expiry_iso


def _instrument_label(instrument_key: str, lookup: InstrumentLookup) -> tuple[str, str]:
    """Human label + strategy-override for one instrument_key.

    Returns (label, type_hint) where type_hint is "" for options/unresolved,
    "equity" or "future" for the 3-Track base legs. type_hint is currently
    unused by the P&L math (net_qty needs no per-type multiplier — see
    _pnl_rupees) but is kept for any future per-type display formatting.

    CE/PE order note: this deliberately does NOT call the canonical
    format_leg_label()/format_option_label() (src/instruments/lookup.py) for
    CE/PE legs — those produce "<underlying> <strike> <CE/PE> <expiry>"
    (telegram-leg-labels epic standard, used everywhere else in this repo:
    IC audit reports, close/roll/entry notifications). Per Animesh's
    2026-08-13 request, this table puts CE/PE last instead: "<underlying>
    <strike> <expiry> <CE/PE>". That means this script's option labels will
    read differently from every other Telegram message in the codebase —
    fine for this scratch table, but flag it if this ever gets promoted into
    real src/notifications/ code, since it'd be a deliberate one-off
    deviation from the repo-wide standard, not an oversight.
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
            # Same fallback contract as format_leg_label(): degrade to the raw key
            # rather than emit a label missing its strike.
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


_Row = tuple[str, str, str, str, str, str, str, "Decimal | None"]

# Per-strategy rollup for the trailing summary section: raw rupee P&L, the actual
# DB strategy_name + entry_date to key a margin lookup off of (NOT the friendly
# _STRATEGY_LABELS value — margin snapshots are stored under the real strategy_name,
# and CC/PP/Collar all share STRATEGY_OVERLAY despite having 3 different friendly
# labels), and whether any leg in the group had a missing LTP (pnl=None skipped
# from the P&L sum, so the P&L total itself may be understated).
_StrategyMeta = tuple[Decimal, str, "date | None", bool]


async def _collect_rows(
    store: PaperStore,
    broker: Any,
    lookup: InstrumentLookup,
) -> tuple[list[_Row], Decimal, bool, dict[str, _StrategyMeta]]:
    """Gather one row per open leg across every registered paper strategy."""
    entries: list[tuple[str, PaperPosition, str, str]] = []  # (strategy_label, pos, label, type_hint)

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
        strategy_label = _overlay_strategy_label(pos.leg_role)
        entries.append((strategy_label, pos, label, type_hint))

    if not entries:
        return [], Decimal("0"), False, {}

    all_keys = sorted({pos.instrument_key for _, pos, _, _ in entries})
    try:
        ltp_map = await broker.get_ltp(all_keys)
    except Exception as exc:  # Intentional: fail-safe LTP fetch, non-fatal
        logger.error("eod_pt_summary.ltp_fetch_failed", error=str(exc))
        ltp_map = {}

    # 8th element is the raw Decimal|None P&L (not printed directly — _line() only
    # ever indexes the first 7 cells against `headers`) kept alongside the formatted
    # string so the summary section can sum per-strategy totals without re-parsing text.
    rows: list[tuple[str, str, str, str, str, str, str, Decimal | None]] = []
    total_pnl = Decimal("0")
    any_pnl_missing = False
    # strategy_label -> (pnl_sum, raw_strategy_name, entry_date, group_pnl_missing).
    # raw_strategy_name/entry_date are taken from the first leg seen for that label —
    # every leg of one entry cycle shares the same entry_date (PG-1), and CC/PP/Collar's
    # shared STRATEGY_OVERLAY name is what get_margin_snapshot() actually needs, not the
    # friendly per-leg-role label.
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
    """Replay full trade history for one strategy and find legs that fully closed
    (net_qty returned to 0) exactly on snap_date.

    Animesh's example ("IC closed — CLOSE_FULL", short_put BUY 65 @ 8.10 etc.) shows
    a full 4-leg close, which is what this detects — a leg's opening trades (a run of
    SELLs for a short leg, BUYs for a long hedge) fully offset by closing trades on
    the same day. get_positions()/get_trades() only ever return currently-OPEN net
    positions, so a leg that closed today is invisible there by definition — this
    replays store.get_trades(strategy_name) (ALL trades, not just open ones) and does
    the same net_qty-cycle accounting get_positions() does internally (PG-1: grouped
    by (leg_role, instrument_key), cycle resets whenever net_qty hits 0), but keeps
    the cycle instead of discarding it once closed, and flags any cycle whose closing
    trade landed on snap_date.

    Partial closes (net_qty reduced but not to exactly 0) are intentionally NOT
    reported here — they're still an open position (visible in the main table with a
    smaller Qty) and only the fully-realized round-trip belongs in "closed today".

    Returns:
        List of (leg_role, instrument_key, qty_signed, entry_price, exit_price,
        close_date) — qty_signed carries the direction the position was held in
        (negative = was short), matching PaperPosition.net_qty's sign convention so
        the same P&L-sign formula applies.
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
                # Starting a fresh cycle — reset accumulators (same reset point
                # PaperStore.get_positions() uses for PG-1 cycle tracking).
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
                closed.append(
                    (leg_role, instrument_key, qty_signed, entry_price, exit_price, cycle_start_date)
                )

    return closed


async def _collect_closed_rows(
    store: PaperStore,
    lookup: InstrumentLookup,
    snap_date: date,
) -> tuple[list[_Row], Decimal]:
    """Same row shape as _collect_rows(), but for legs closed exactly on snap_date.

    No live broker/LTP dependency — entry/exit prices are both realized (already in
    paper_trades), so P&L here is exact, not mark-to-market. `_Row`'s 5th field is
    the exit price rather than a live LTP (see _render_table's value_header param).
    """
    rows: list[_Row] = []
    total_pnl = Decimal("0")

    def _closed_row(strategy_label: str, leg: tuple) -> None:
        nonlocal total_pnl
        _leg_role, instrument_key, qty_signed, entry, exit_price, _close_date = leg
        label, _type_hint = _instrument_label(instrument_key, lookup)
        pnl = (entry - exit_price) * abs(qty_signed) if qty_signed < 0 else (exit_price - entry) * qty_signed
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


def _render_table(
    rows: list[_Row],
    total_pnl: Decimal,
    any_pnl_missing: bool,
    title: str,
    empty_message: str,
    value_header: str = "LTP",
) -> str:
    """Flat single table, one row per leg — reverted 2026-08-13 per Animesh's
    "previous version was better" call (the per-strategy breakdown he actually wanted
    lives in _render_summary() as a trailing section, not a main-table restructure).

    Shared by both the open-positions table and the closed-today table added the same
    day — same 7-column shape (Strategy/Instrument/Qty/Avg/<value_header>/P&L/Chg),
    just with value_header="Exit" and realized entry/exit prices instead of live LTP
    for the closed case. `title`/`empty_message` let each caller supply its own
    header line and no-rows message rather than hardcoding "EOD PT Summary" here.
    """
    if not rows:
        return f"{title} — {empty_message}"

    headers = ("Strategy", "Instrument", "Qty", "Avg", value_header, "P&L", "Chg")
    # Strategy/Instrument are variable-length prose -> left-justify. Qty/Avg/<value>/P&L/Chg
    # are fixed-point numbers -> right-justify so decimal points line up column-wise,
    # matching the broker "Positions" screenshot Animesh shared.
    right_align = (False, False, True, True, True, True, True)

    # Total row: blank everywhere except the P&L column, so the total lands directly
    # under the per-leg P&L figures instead of as a separate line below the table.
    total_row = ("", "TOTAL", "", "", "", _fmt_money(total_pnl), "")

    display_rows = [row[:7] for row in rows] + [total_row]
    widths = [max(len(headers[i]), *(len(r[i]) for r in display_rows)) for i in range(len(headers))]

    def _line(cells: tuple[str, ...]) -> str:
        return "  ".join(
            cells[i].rjust(widths[i]) if right_align[i] else cells[i].ljust(widths[i])
            for i in range(len(cells))
        )

    sep = _line(tuple("-" * w for w in widths))
    lines = [
        title,
        "",
        _line(headers),
        sep,
    ]
    lines.extend(_line(row[:7]) for row in rows)
    lines.append(sep)
    lines.append(_line(total_row))
    if any_pnl_missing:
        lines.append("")
        lines.append("(partial — some legs missing LTP)")

    return "\n".join(lines)


async def _render_summary(
    store: PaperStore,
    strategy_meta: dict[str, _StrategyMeta],
    total_pnl: Decimal,
    snap_date: date,
) -> str:
    """Strategy-wise P&L + annualized % return on margin — Animesh's 2026-08-13 request.

    Annualized % = (pnl / final_margin) * (365 / days_held) * 100 — standard simple
    annualization, not compounded (consistent with paper_ic_snapshot.py's ROI line,
    which reports a single-period %, not annualized; this adds the annualization on
    top of the same final_margin source).

    Margin availability: PaperStore.paper_margin_snapshots is only populated for IC
    V1/V2 entries today (confirmed via direct sqlite3 query, 2026-08-13) — CSP,
    CC/PP/Collar (STRATEGY_OVERLAY), and the 3-Track base legs have never had a
    margin-calculator call wired up to persist one. Those strategies show "N/A" for
    Margin/Ann.% rather than guessing a margin figure — never silently substitute
    required_margin or a hardcoded estimate.
    """
    if not strategy_meta:
        return ""

    headers = ("Strategy", "P&L", "Margin", "Ann.%")
    right_align = (False, True, True, True)
    rows: list[tuple[str, str, str, str]] = []

    for strategy_label, (pnl, strategy_name, entry_date, group_pnl_missing) in strategy_meta.items():
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
                    ann_pct = (pnl / snapshot.final_margin) * (Decimal("365") / days_held) * Decimal("100")
                    ann_str = _fmt_pct(ann_pct)
                # days_held <= 0 (same-day entry, or a clock/date mismatch) -> leave
                # "N/A" rather than divide by a near-zero holding period and print a
                # meaningless four-digit annualized number.

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
    if any(g for _, (_, _, _, g) in strategy_meta.items()):
        lines.append("")
        lines.append("(* — partial: one or more legs missing LTP, P&L understated)")

    return "\n".join(lines)


async def build_summary_parts(
    store: PaperStore, broker: Any, lookup: InstrumentLookup, snap_date: date
) -> list[str]:
    """Build the 3 message bodies as separate strings — one per Telegram message.

    Split into 3 sends (not 1 combined message) per Animesh's 2026-08-13 request:
    "EOD PT Summary", "Closed Today", "Summary — Strategy P&L / Ann.% on Margin".
    Each becomes its own Telegram message rather than sections of one — see
    docs/plan/eod-pt-summary/stories.md PT-1 for why (readability once the open
    table alone regularly runs 8+ strategies; each message stays independently
    forwardable/searchable in Telegram's history).

    "Closed Today" is omitted from the returned list entirely on days nothing
    closed (same non-fatal "no noise" contract as before) — the caller ends up
    sending 2 messages instead of 3, not a 3rd message announcing zero closes.
    """
    rows, total_pnl, any_pnl_missing, strategy_meta = await _collect_rows(store, broker, lookup)
    open_table = _render_table(
        rows,
        total_pnl,
        any_pnl_missing,
        title=f"EOD PT Summary — {snap_date.isoformat()}",
        empty_message="no open positions across any paper strategy.",
    )

    parts = [open_table]

    closed_rows, closed_total_pnl = await _collect_closed_rows(store, lookup, snap_date)
    if closed_rows:
        parts.append(
            _render_table(
                closed_rows,
                closed_total_pnl,
                any_pnl_missing=False,
                title=f"Closed Today — {snap_date.isoformat()}",
                empty_message="",
                value_header="Exit",
            )
        )

    summary = await _render_summary(store, strategy_meta, total_pnl, snap_date)
    if summary:
        parts.append(summary)

    return parts


# title-line prefix -> emoji, purely cosmetic (matches the emoji style of every
# other Telegram message in this repo, e.g. paper_ic_snapshot.py's "📋 IC EOD Audit").
_PART_EMOJI = {
    "EOD PT Summary": "📝",
    "Closed Today": "✅",
    "Summary —": "📊",
}


def _part_emoji(title_line: str) -> str:
    for prefix, emoji in _PART_EMOJI.items():
        if title_line.startswith(prefix):
            return emoji
    return "📋"


async def _send_telegram_markdown(bot_token: str, chat_id: str, part: str) -> bool:
    """Send one message part as MarkdownV2: emoji+title escaped outside the fence,
    everything after the title line inside a fenced code block. Returns True on a
    confirmed 200 from Telegram, False on any failure (never raises — non-fatal)."""
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
                    # Surface Telegram's actual `description` — a bare raise_for_status()
                    # swallows it (same lesson 2026-08-08_eod_paper_summary_format.py notes).
                    print(f"!! Telegram send failed ({resp.status}): {body_json.get('description')}")
                    logger.warning(
                        "eod_pt_summary.telegram_failed",
                        status=resp.status,
                        description=body_json.get("description"),
                        title=title_line,
                    )
                    return False
                print(f"Sent to Telegram OK: {title_line}")
                logger.info("eod_pt_summary.telegram_sent", title=title_line)
                return True
    except Exception as exc:  # Intentional: fail-safe delivery, non-fatal
        logger.warning("eod_pt_summary.telegram_failed", error=str(exc), title=title_line)
        return False


async def _run(args: argparse.Namespace) -> None:
    setup_logging()
    snap_date: date = args.date or date.today()

    store = PaperStore(args.db_path)
    lookup = InstrumentLookup.from_file(args.bod_path)

    try:
        broker = create_client(settings.upstox_env)
    except ValueError:
        if not args.dry_run:
            logger.error("eod_pt_summary.broker_init_failed")
            sys.exit(1)
        logger.warning("eod_pt_summary.broker_init_failed_mock_fallback")

        class _MockBroker:
            async def get_ltp(self, keys: list[str]) -> dict[str, Decimal]:
                return {k: Decimal("0.0") for k in keys}

        broker = _MockBroker()

    parts = await build_summary_parts(store, broker, lookup, snap_date)
    for part in parts:
        print(f"\n{part}\n")

    if not args.send:
        print(
            f"(--send not passed — nothing sent. {len(parts)} message(s) would be sent "
            "with --send.)"
        )
        return

    bot_token = settings.telegram_bot_token or ""
    chat_id = settings.telegram_chat_id or ""
    if not (bot_token and chat_id):
        print(
            "!! TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — cannot send. "
            "Check .env at repo root."
        )
        logger.warning("eod_pt_summary.telegram_not_configured")
        return

    # 3 independent sends (Animesh, 2026-08-13), not 1 message with 3 sections — a
    # failure on one (e.g. rate-limited) must not block the others, so each is its
    # own try/except inside _send_telegram_markdown rather than one shared block.
    for part in parts:
        await _send_telegram_markdown(bot_token, chat_id, part)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Scratch: EOD PT Summary — cross-strategy paper-trade summary table.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--date",
        default=None,
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="Snapshot date (default: today).",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Falls back to a mock broker if live client init fails (default: on).",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send to Telegram (default: print only, never sends). "
        "Requires TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID in the environment.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite DB path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD_PATH,
        help=f"BOD instruments JSON path (default: {DEFAULT_BOD_PATH})",
    )

    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
