#!/usr/bin/env python3
"""Automated base-leg roll execution for the 3-Track Nifty Long Comparison framework.

Extends `_check_base_expiry()`'s alert-only detection (`paper_3track_snapshot.py`)
into an executing roll: for `base_futures` and `base_ditm_call` legs approaching
expiry, resolves the next-band contract, applies a warn-only liquidity gate, and
persists the close + open as a single atomic `PaperStore.record_trades()` call.

Per-leg roll triggers (S5, confirmed with operator 2026-07-28, see
docs/plan/3track-consolidation/stories.md):
    - base_futures:    DTE <= 1  (capital-efficiency priority over liquidity concern)
    - base_ditm_call:  DTE < 20  (band_min + 5 buffer; thin far-month liquidity)

Liquidity gates are warn-only — a failing gate logs a WARNING but never blocks the
roll (operator decision, matches paper_3track_entry.py's PROXY_OI_MIN/PROXY_SPREAD_MAX
pattern). Futures liquidity uses a relative-OI threshold (next-band contract's OI
must be >= 10% of the current near-month contract's OI); DITM reuses the existing
PROXY_OI_MIN/PROXY_SPREAD_MAX constants (already option-scale).

This script does NOT touch NiftyTrackComparisonV1 or its auto_execute flag —
base-leg rolling is a separate execution path from overlay strategy evaluation.

Usage:
    # Dry-run — print what would roll, no DB writes (default):
    python scripts/strategies/three_track/paper_3track_roll.py --date 2026-07-30

    # Execute rolls and persist to DB:
    python scripts/strategies/three_track/paper_3track_roll.py --date 2026-07-30 --no-dry-run

Cron example (daily, ahead of the EOD snapshot):
    15 10 * * 1-5  cd /path/to/NiftyShield && python scripts/strategies/three_track/paper_3track_roll.py --no-dry-run
"""

from __future__ import annotations

# ruff: noqa: E402
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from dotenv import load_dotenv

load_dotenv()

import argparse
import asyncio
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import structlog

# paper_3track_entry.py defines the OI/spread thresholds this story reuses for the
# DITM leg's liquidity gate (already option-scale, per S5 decision log).
from scripts.strategies.three_track.paper_3track_entry import (
    PROXY_OI_MIN,
    PROXY_SPREAD_MAX,
)

# paper_3track_snapshot.py owns instrument-key -> expiry-date resolution (BOD lookup
# with regex fallbacks for options/futures key formats); reused as-is rather than
# duplicated here.
from scripts.strategies.three_track.paper_3track_snapshot import _get_expiry_date
from src.client.upstox_market import UpstoxMarketClient
from src.instruments.lookup import InstrumentLookup
from src.market_calendar.holidays import is_trading_day
from src.models.portfolio import TradeAction
from src.notifications.telegram import TelegramNotifier, build_notifier
from src.paper.constants import (
    DEFAULT_BOD_PATH,
    DEFAULT_DB_PATH,
    STRATEGY_FUTURES,
    STRATEGY_PROXY,
)
from src.paper.models import PaperPosition, PaperTrade
from src.paper.store import PaperStore
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.strategies.three_track.paper_3track_roll"
logger = structlog.get_logger(_SCRIPT_NAME)

# ── Per-leg roll thresholds (S5 decision log, 2026-07-28) ──────────────────────
# Deliberately two independent constants — never unify into a single shared
# threshold. base_futures rolls on expiry day or the day before (capital
# efficiency); base_ditm_call rolls ~1 week ahead (thin far-month liquidity).
FUTURES_ROLL_DTE = 1
DITM_ROLL_DTE = 20

# Futures liquidity gate: next-band contract's OI must be >= 10% of the current
# near-month contract's OI. Relative, not absolute — futures OI operates on a
# different scale than option OI and self-normalizes as market-wide volume drifts.
FUTURES_OI_RATIO_MIN = 0.10

ROLLABLE_LEG_ROLES = {"base_futures", "base_ditm_call"}


# ── Pure trigger/gate logic (no I/O — unit-testable in isolation) ──────────────


def should_roll_futures(dte: int) -> bool:
    """True when a base_futures leg is due to roll (DTE <= FUTURES_ROLL_DTE)."""
    return dte <= FUTURES_ROLL_DTE


def should_roll_ditm(dte: int) -> bool:
    """True when a base_ditm_call leg is due to roll (DTE < DITM_ROLL_DTE)."""
    return dte < DITM_ROLL_DTE


def check_futures_liquidity_gate(next_oi: int | None, near_oi: int | None) -> bool:
    """Warn-only relative-OI gate for the futures roll target.

    Returns True (pass) when the next-band contract's OI is at least
    FUTURES_OI_RATIO_MIN of the current near-month contract's OI. Returns False
    (warn) when OI data is missing or the ratio isn't met — callers must roll
    regardless of the return value; this is diagnostic only, never blocking
    (operator decision, S5).
    """
    if next_oi is None or near_oi is None or near_oi <= 0:
        return False
    return next_oi >= FUTURES_OI_RATIO_MIN * near_oi


def check_ditm_liquidity_gate(oi: int, bid: float, ask: float) -> bool:
    """Warn-only liquidity gate for the DITM roll target, reusing PROXY_* constants.

    Returns True (pass) when OI >= PROXY_OI_MIN and spread <= PROXY_SPREAD_MAX.
    Never blocks the roll — same warn-only contract as check_futures_liquidity_gate.
    """
    spread = ask - bid if (ask > 0 and bid > 0) else float("inf")
    return oi >= PROXY_OI_MIN and spread <= PROXY_SPREAD_MAX


def next_trading_date(today: date) -> date:
    """First trading day strictly after `today`."""
    candidate = today + timedelta(days=1)
    while not is_trading_day(candidate):
        candidate += timedelta(days=1)
    return candidate


def build_roll_trades(
    *,
    strategy_name: str,
    leg_role: str,
    old_instrument_key: str,
    new_instrument_key: str,
    quantity: int,
    close_price: Decimal,
    open_price: Decimal,
    close_date: date,
    open_date: date,
) -> tuple[PaperTrade, PaperTrade]:
    """Build the (close, open) PaperTrade pair for a base-leg roll.

    Base legs (base_futures, base_ditm_call) are always long — close is a SELL
    on the expiring instrument, open is a BUY on the next-band instrument.
    """
    close_trade = PaperTrade(
        strategy_name=strategy_name,
        leg_role=leg_role,
        instrument_key=old_instrument_key,
        trade_date=close_date,
        action=TradeAction.SELL,
        quantity=quantity,
        price=close_price,
        notes=f"S5 auto-roll: close ahead of expiry, replaced by {new_instrument_key}",
    )
    open_trade = PaperTrade(
        strategy_name=strategy_name,
        leg_role=leg_role,
        instrument_key=new_instrument_key,
        trade_date=open_date,
        action=TradeAction.BUY,
        quantity=quantity,
        price=open_price,
        notes=f"S5 auto-roll: opened to replace {old_instrument_key}",
    )
    return close_trade, open_trade


# ── Orchestration (I/O — broker/store/notifier all injected for testability) ───


async def check_and_roll_leg(
    pos: PaperPosition,
    instruments: InstrumentLookup,
    store: PaperStore,
    broker: Any,
    notifier: TelegramNotifier | None,
    today: date,
    dry_run: bool,
) -> dict[str, Any] | None:
    """Evaluate one base-leg position and execute its roll if due.

    Returns a summary dict when a roll fired (or would fire, in dry-run), else
    None when the leg isn't due to roll yet or couldn't be resolved.
    """
    if pos.leg_role not in ROLLABLE_LEG_ROLES or pos.net_qty == 0:
        return None

    expiry_date = _get_expiry_date(pos.instrument_key, instruments)
    if expiry_date is None:
        logger.warning("paper_3track_roll.expiry_not_found", instrument_key=pos.instrument_key)
        return None

    dte = (expiry_date - today).days
    is_futures = pos.leg_role == "base_futures"
    due = should_roll_futures(dte) if is_futures else should_roll_ditm(dte)
    if not due:
        return None

    next_inst = (
        instruments.get_next_contract(pos.instrument_key)
        if is_futures
        else instruments.get_next_contract_in_band(pos.instrument_key, today)
    )
    if not next_inst:
        logger.warning(
            "paper_3track_roll.next_contract_not_found",
            instrument_key=pos.instrument_key,
            leg_role=pos.leg_role,
        )
        return None

    next_key = next_inst.get("instrument_key")
    if not next_key:
        logger.warning("paper_3track_roll.next_contract_missing_key", next_inst=next_inst)
        return None

    ltp_map = await broker.get_ltp([pos.instrument_key, next_key])
    close_price = ltp_map.get(pos.instrument_key)
    open_price = ltp_map.get(next_key)
    if close_price is None or open_price is None:
        logger.warning(
            "paper_3track_roll.ltp_unavailable",
            instrument_key=pos.instrument_key,
            next_key=next_key,
        )
        return None

    gate_passed = _run_liquidity_gate(pos, next_key, broker)
    if not gate_passed:
        logger.warning(
            "paper_3track_roll.liquidity_gate_warn",
            leg_role=pos.leg_role,
            instrument_key=pos.instrument_key,
            next_key=next_key,
        )

    qty = abs(pos.net_qty)
    open_date = next_trading_date(today)
    close_trade, open_trade = build_roll_trades(
        strategy_name=pos.strategy_name,
        leg_role=pos.leg_role,
        old_instrument_key=pos.instrument_key,
        new_instrument_key=next_key,
        quantity=qty,
        close_price=close_price,
        open_price=open_price,
        close_date=today,
        open_date=open_date,
    )

    summary = {
        "strategy_name": pos.strategy_name,
        "leg_role": pos.leg_role,
        "old_key": pos.instrument_key,
        "new_key": next_key,
        "dte": dte,
        "liquidity_gate_passed": gate_passed,
    }

    if dry_run:
        return summary

    inserted, skipped = store.record_trades([close_trade, open_trade])
    summary["inserted"] = len(inserted)
    summary["skipped"] = len(skipped)

    # Mirror BUG-035/BUG-037: transition the closed leg's opening row to
    # CLOSED so it stops re-appearing as flat-but-OPEN/DEFENDED. Only fire
    # when the close side of this roll actually landed (record_trades skips
    # exact duplicates rather than raising) — the open side is a different
    # instrument_key and must not affect this leg's own state transition.
    if close_trade in inserted:
        store.mark_trade_closed(pos.strategy_name, pos.leg_role, pos.instrument_key)
    # Both legs of a roll must land together. `record_trades` skips exact
    # duplicates (ON CONFLICT DO NOTHING) rather than raising, so a partial
    # roll (e.g. close persisted, open skipped as a stale duplicate from a
    # prior partial run) would otherwise look identical to a clean roll in
    # the log/notification — Telegram is the only visibility mechanism left
    # once this pipeline runs unattended, so a half-open roll must be loud.
    partial = len(inserted) != 2
    summary["partial"] = partial
    if partial:
        logger.error(
            "paper_3track_roll.partial_roll",
            strategy_name=pos.strategy_name,
            leg_role=pos.leg_role,
            inserted=len(inserted),
            skipped=len(skipped),
        )

    if notifier:
        status_line = (
            "🚨 PARTIAL ROLL — VERIFY POSITIONS MANUALLY"
            if partial
            else f"Liquidity gate: {'✅ PASS' if gate_passed else '⚠️ WARN'}"
        )
        msg = (
            f"🔄 BASE LEG ROLLED\n"
            f"Strategy: {pos.strategy_name}\n"
            f"Leg: {pos.leg_role}\n"
            f"Closed: {pos.instrument_key} @ ₹{close_price}\n"
            f"Opened: {next_key} @ ₹{open_price}\n"
            f"{status_line}"
        )
        try:
            await notifier.send(msg)
        except Exception as exc:  # non-fatal — notification failure never blocks the roll
            logger.warning("paper_3track_roll.notify_failed", error=str(exc))

    return summary


def _run_liquidity_gate(pos: PaperPosition, next_key: str, broker: Any) -> bool:
    """Dispatch to the futures or DITM liquidity gate. Best-effort — missing OI/quote
    data is treated as a gate failure (warn), never raises, never blocks the roll."""
    try:
        if pos.leg_role == "base_futures":
            near_oi = _fetch_oi(broker, pos.instrument_key)
            next_oi = _fetch_oi(broker, next_key)
            return check_futures_liquidity_gate(next_oi, near_oi)
        oi, bid, ask = _fetch_oi_bid_ask(broker, next_key)
        if oi is None or bid is None or ask is None:
            return False
        return check_ditm_liquidity_gate(oi, bid, ask)
    except Exception as exc:
        logger.warning("paper_3track_roll.liquidity_gate_fetch_failed", error=str(exc))
        return False


def _fetch_oi(broker: Any, instrument_key: str) -> int | None:
    """Best-effort OI lookup. Returns None if the broker has no OI-capable method —
    the caller treats that as a gate failure (warn, never blocks)."""
    fetch = getattr(broker, "get_open_interest", None)
    if fetch is None:
        return None
    try:
        return fetch(instrument_key)
    except Exception:
        return None


def _fetch_oi_bid_ask(
    broker: Any, instrument_key: str
) -> tuple[int | None, float | None, float | None]:
    """Best-effort OI+bid+ask lookup for a single option instrument."""
    fetch = getattr(broker, "get_market_depth", None)
    if fetch is None:
        return (None, None, None)
    try:
        quote = fetch(instrument_key)
        return (quote.get("oi"), quote.get("bid"), quote.get("ask"))
    except Exception:
        return (None, None, None)


async def run_roll_check(
    store: PaperStore,
    instruments: InstrumentLookup,
    broker: Any,
    notifier: TelegramNotifier | None,
    today: date,
    dry_run: bool,
) -> list[dict[str, Any]]:
    """Check both 3-track base legs (Futures, DITM) for due rolls and execute them."""
    results: list[dict[str, Any]] = []
    for strategy_name in (STRATEGY_FUTURES, STRATEGY_PROXY):
        for pos in store.get_positions(strategy_name):
            summary = await check_and_roll_leg(
                pos, instruments, store, broker, notifier, today, dry_run
            )
            if summary is not None:
                results.append(summary)
    return results


# ── CLI ──────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=str, default=None, help="Override today's date (YYYY-MM-DD)")
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Print what would roll, no DB writes (default)",
    )
    parser.add_argument(
        "--no-dry-run", dest="dry_run", action="store_false", help="Execute rolls and persist to DB"
    )
    return parser.parse_args(argv)


async def _amain(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    today = date.fromisoformat(args.date) if args.date else date.today()

    store = PaperStore(DEFAULT_DB_PATH)
    instruments = InstrumentLookup.from_file(DEFAULT_BOD_PATH)
    broker = UpstoxMarketClient()
    notifier = build_notifier() if not args.dry_run else None

    results = await run_roll_check(store, instruments, broker, notifier, today, args.dry_run)

    if not results:
        logger.info("paper_3track_roll.no_rolls_due", date=today.isoformat())
        return

    for r in results:
        logger.info("paper_3track_roll.result", **r)


def main() -> None:
    setup_logging()
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
