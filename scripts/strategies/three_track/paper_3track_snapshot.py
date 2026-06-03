#!/usr/bin/env python3
"""Canonical daily snapshot for the 3-Track Nifty Long Comparison framework.

Combines base vs protection P&L, per-leg delta-from-yesterday tracking, and
proxy delta monitoring into a single terminal report. Writes both
``paper_nav_snapshots`` (strategy-level) and ``paper_leg_snapshots`` (per-leg)
by default; use ``--dry-run`` for a dry-run inspection (default: on).

Replaces ``paper_track_snapshot.py`` as the canonical cron snapshot script.
``paper_track_snapshot.py`` is preserved for backward-compatible operator use.

Usage:
    # Live fetch — save snapshots:
    python scripts/paper_3track_snapshot.py --date 2026-05-07 --no-dry-run

    # Dry-run — print report only, no DB writes (default):
    python scripts/paper_3track_snapshot.py --date 2026-05-07

    # Restrict to specific tracks:
    python scripts/paper_3track_snapshot.py --date 2026-05-07 --tracks spot proxy --no-dry-run

Cron example (daily at 15:35 IST):
    35 10 * * 1-5  cd /path/to/NiftyShield && python scripts/paper_3track_snapshot.py --no-dry-run

Diagnostics:
    LOG_LEVEL=DEBUG python scripts/paper_3track_snapshot.py --date 2026-05-07
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
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import structlog

from src.client.upstox_market import UpstoxMarketClient, parse_upstox_option_chain
from src.config import settings
from src.instruments.lookup import InstrumentLookup, parse_expiry
from src.models.options import OptionChain, OptionLeg
from src.notifications.telegram import TelegramNotifier
from src.paper._display import (
    BASE_LABELS,
    OVERLAY_LABELS,
)
from src.paper._display import (
    delta_arrow as _delta_arrow,
)
from src.paper._display import (
    fmt_decimal as _fmt,
)
from src.paper._display import (
    hedge_verdict as _hedge_verdict,
)
from src.paper.constants import (
    DEFAULT_BOD_PATH,
    DEFAULT_DB_PATH,
    LOT_SIZE,
    STRATEGY_FUTURES,
    STRATEGY_PROXY,
    STRATEGY_SPOT,
)
from src.paper.formatting import format_track_summary
from src.paper.metrics import compute_nee
from src.paper.models import ExitSignal, PaperLegSnapshot, PaperNavSnapshot, PaperPosition
from src.paper.proxy_monitor import ProxyDeltaMonitor
from src.paper.store import PaperStore
from src.paper.track_snapshot import TrackSnapshot, generate_track_snapshot
from src.strategy.exit_signals import ExitSignalEngine
from src.utils.logging import setup_logging

# ── Constants ─────────────────────────────────────────────────────────────────

ALL_TRACKS = [STRATEGY_SPOT, STRATEGY_FUTURES, STRATEGY_PROXY]


_SCRIPT_NAME = "scripts.strategies.three_track.paper_3track_snapshot"
logger = structlog.get_logger(_SCRIPT_NAME)

_CSP_STRATEGY = "paper_csp_nifty_v1"

# leg_role → option type (CE/PE) for chain lookups
_OVERLAY_OPTION_TYPE: dict[str, str] = {
    "overlay_cc": "CE",
    "overlay_collar_call": "CE",
    "overlay_pp": "PE",
    "overlay_collar_put": "PE",
}

# Instrument key parsing — matches "NIFTY29MAY2026CE23000" or "NIFTY23000CE"
_KEY_EXPIRY_RE = re.compile(r"NIFTY(\d{2})([A-Za-z]{3})(\d{4})(CE|PE)", re.IGNORECASE)
_KEY_STRIKE_RE = re.compile(r"NIFTY(\d+)(CE|PE)", re.IGNORECASE)
_MONTH_ABBR: dict[str, int] = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def _parse_expiry_from_key(instrument_key: str) -> date | None:
    """Return expiry date from instrument key, or None if unparseable."""
    m = _KEY_EXPIRY_RE.search(instrument_key)
    if not m:
        return None
    try:
        day, mon_str, year = int(m.group(1)), m.group(2).upper(), int(m.group(3))
        month = _MONTH_ABBR.get(mon_str)
        return date(year, month, day) if month else None
    except (ValueError, TypeError):
        return None


def _compute_dte(instrument_key: str, today: date) -> int | None:
    """Return days-to-expiry for the key's embedded expiry, or None."""
    expiry = _parse_expiry_from_key(instrument_key)
    return (expiry - today).days if expiry is not None else None


def _parse_strike_from_key(instrument_key: str) -> Decimal | None:
    """Extract strike price from instrument key, or None if unparseable.

    Matches 'NIFTY23000CE' style keys.  Date-embedded keys like
    'NIFTY29MAY2026CE23000' are NOT matched (alpha chars break the digit run).
    Returns None for numeric-ID keys like 'NSE_FO|47196'.
    """
    m = _KEY_STRIKE_RE.search(instrument_key)
    if not m:
        return None
    try:
        return Decimal(m.group(1))
    except InvalidOperation:
        return None


def _find_chain_leg(
    chain: OptionChain,
    instrument_key: str,
    option_type: str,
) -> OptionLeg | None:
    """Look up CE or PE leg from the chain by strike parsed from instrument_key.

    Falls back to scanning all strikes for the first leg with non-zero LTP when
    the key carries no parseable strike (e.g. numeric BOD IDs like 'NSE_FO|47196').

    Args:
        chain: Parsed Nifty option chain.
        instrument_key: Position's instrument key.
        option_type: 'CE' or 'PE'.

    Returns:
        Matching OptionLeg or None when unavailable.
    """
    strike = _parse_strike_from_key(instrument_key)
    if strike is not None:
        strike_data = chain.strikes.get(strike)
        if strike_data is not None:
            return strike_data.ce if option_type == "CE" else strike_data.pe

    # Fallback: scan all strikes for first leg with non-zero LTP
    for strike_data in chain.strikes.values():
        leg = strike_data.ce if option_type == "CE" else strike_data.pe
        if leg is not None and leg.ltp > 0:
            return leg

    return None


def _dispatch_evaluate(
    pos: PaperPosition,
    chain: OptionChain,
    underlying_price: float,
    today: date,
) -> list:
    """Dispatch a position to the correct ExitSignalEngine.evaluate_* method.

    Returns [] for positions that are not signal-eligible (base legs, closed,
    or unrecognised strategy/role combinations).

    Args:
        pos: Open paper position.
        chain: Current Nifty option chain.
        underlying_price: Nifty spot price as float.
        today: Evaluation date (for DTE and days_held calculations).

    Returns:
        List of ExitSignalResult objects (may be empty).
    """
    role = pos.leg_role
    dte = _compute_dte(pos.instrument_key, today) or 9999

    if pos.strategy_name == _CSP_STRATEGY and pos.net_qty < 0:
        # Short put — CSP
        leg = _find_chain_leg(chain, pos.instrument_key, "PE")
        delta = float(leg.delta) if leg is not None else None
        current_mark = float(leg.ltp) if leg is not None else 0.0
        days_held = (today - pos.entry_date).days if pos.entry_date else 0
        return ExitSignalEngine.evaluate_csp(
            entry_price=float(pos.avg_sell_price),
            current_mark=current_mark,
            delta=delta,
            days_held=days_held,
            dte=dte,
        )

    if role == "overlay_cc" and pos.net_qty < 0:
        leg = _find_chain_leg(chain, pos.instrument_key, "CE")
        strike = _parse_strike_from_key(pos.instrument_key)
        return ExitSignalEngine.evaluate_cc(
            entry_price=float(pos.avg_sell_price),
            current_mark=float(leg.ltp) if leg is not None else 0.0,
            delta=float(leg.delta) if leg is not None else None,
            dte=dte,
            underlying_price=underlying_price,
            strike_price=float(strike) if strike is not None else 0.0,
        )

    if role == "overlay_pp" and pos.net_qty > 0:
        leg = _find_chain_leg(chain, pos.instrument_key, "PE")
        return ExitSignalEngine.evaluate_pp(
            entry_price=float(pos.avg_cost),
            current_mark=float(leg.ltp) if leg is not None else 0.0,
            delta=float(leg.delta) if leg is not None else None,
            dte=dte,
            bid=float(leg.bid) if leg is not None else None,
            ask=float(leg.ask) if leg is not None else None,
        )

    if role == "overlay_collar_call" and pos.net_qty < 0:
        leg = _find_chain_leg(chain, pos.instrument_key, "CE")
        strike = _parse_strike_from_key(pos.instrument_key)
        return ExitSignalEngine.evaluate_collar_call(
            entry_price=float(pos.avg_sell_price),
            current_mark=float(leg.ltp) if leg is not None else 0.0,
            delta=float(leg.delta) if leg is not None else None,
            dte=dte,
            underlying_price=underlying_price,
            strike_price=float(strike) if strike is not None else 0.0,
        )

    if role == "overlay_collar_put" and pos.net_qty > 0:
        leg = _find_chain_leg(chain, pos.instrument_key, "PE")
        return ExitSignalEngine.evaluate_collar_put(
            entry_price=float(pos.avg_cost),
            current_mark=float(leg.ltp) if leg is not None else 0.0,
            delta=float(leg.delta) if leg is not None else None,
            dte=dte,
            bid=float(leg.bid) if leg is not None else None,
            ask=float(leg.ask) if leg is not None else None,
        )

    return []

    return []


def _get_expiry_date(instrument_key: str, instruments: InstrumentLookup) -> date | None:
    """Resolve the expiry date of an instrument from BOD or by parsing its key."""
    inst = instruments.get_by_key(instrument_key)
    if inst:
        exp_str = inst.get("expiry")
        if exp_str:
            expiry_str = parse_expiry(exp_str)
            if expiry_str:
                try:
                    return date.fromisoformat(expiry_str)
                except ValueError:
                    pass

    # Fallback: parse options style keys, e.g. NSE_FO|NIFTY29MAY2026PE or NSE_FO|NIFTY26JUN23000CE
    m = re.search(r"NIFTY(\d{2})([A-Z]{3})(\d{4})", instrument_key, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        mon_str = m.group(2).upper()
        year = int(m.group(3))
        month = _MONTH_ABBR.get(mon_str)
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    # Fallback: parse futures style keys, e.g. NSE_FO|NIFTY26JUNFUT or NSE_FO|NIFTYJUN2026FUT
    m = re.search(r"NIFTY(\d{2})([A-Z]{3})FUT", instrument_key, re.IGNORECASE)
    if m:
        try:
            yy = int(m.group(1))
            mon_str = m.group(2).upper()
            month = _MONTH_ABBR.get(mon_str)
            if month:
                import calendar

                last_day = calendar.monthrange(2000 + yy, month)[1]
                d = date(2000 + yy, month, last_day)
                while d.weekday() != 3:  # Thursday
                    d -= timedelta(days=1)
                return d
        except (ValueError, IndexError):
            pass

    m = re.search(r"NIFTY([A-Z]{3})(\d{4})FUT", instrument_key, re.IGNORECASE)
    if m:
        try:
            mon_str = m.group(1).upper()
            year = int(m.group(2))
            month = _MONTH_ABBR.get(mon_str)
            if month:
                import calendar

                last_day = calendar.monthrange(year, month)[1]
                d = date(year, month, last_day)
                while d.weekday() != 3:  # Thursday
                    d -= timedelta(days=1)
                return d
        except (ValueError, IndexError):
            pass

    return None


async def _check_base_expiry(
    positions: list[PaperPosition],
    instruments: InstrumentLookup,
    today: date,
    store: PaperStore,
    notifier: TelegramNotifier | None,
) -> None:
    """Check base futures/DITM options expiry within 5 DTE, log to DB and notify."""
    # Build dedup set from already-open events dated today
    today_iso = today.isoformat()
    existing_events = {
        (ev["trade_id"], ev["exit_signal"])
        for ev in store.get_open_exit_events()
        if ev["event_time"][:10] == today_iso
    }

    for pos in positions:
        if pos.leg_role not in {"base_futures", "base_ditm_call"}:
            continue
        if pos.net_qty == 0:
            continue

        # Check idempotency
        if (pos.instrument_key, "BASE_EXPIRY_ALERT") in existing_events:
            logger.debug(
                "base_expiry.dedup_skip",
                trade_id=pos.instrument_key,
                exit_signal="BASE_EXPIRY_ALERT",
            )
            continue

        expiry_date = _get_expiry_date(pos.instrument_key, instruments)
        if expiry_date is None:
            logger.warning("base_expiry.expiry_not_found", instrument_key=pos.instrument_key)
            continue

        dte = (expiry_date - today).days
        if dte > 5:
            continue

        # DTE <= 5: Base position is expiring!
        next_inst = instruments.get_next_contract(pos.instrument_key)
        warning_suffix = ""
        if not next_inst:
            logger.warning("base_expiry.next_contract_not_found", instrument_key=pos.instrument_key)
            warning_suffix = "\n\n⚠️ WARNING: BOD may be stale"
            next_key = "<NEXT_CONTRACT_KEY>"
            next_symbol = "<NEXT_CONTRACT_SYMBOL>"
        else:
            next_key = next_inst.get("instrument_key", "<NEXT_CONTRACT_KEY>")
            next_symbol = next_inst.get("trading_symbol", "<NEXT_CONTRACT_SYMBOL>")

        # Record event in paper_exit_events
        event_time = datetime.combine(today, datetime.min.time())
        is_short = pos.net_qty < 0
        entry_price = pos.avg_sell_price if is_short else pos.avg_cost

        try:
            store.create_exit_event(
                strategy_name=pos.strategy_name,
                leg_name=pos.leg_role,
                trade_id=pos.instrument_key,
                event_time=event_time,
                detected_by="EOD",
                exit_signal=ExitSignal("BASE_EXPIRY_ALERT"),
                severity="WARNING",
                entry_price=entry_price,
                snapshot_id=None,
                ltp=None,
                bid=None,
                ask=None,
                delta=None,
                dte=dte,
                threshold_value=5.0,
                notes=f"Next contract: {next_symbol} ({next_key})",
            )
        except Exception as exc:
            logger.warning("base_expiry.db_write_failed", error=str(exc))

        # Calculate next trading day
        from src.market_calendar.holidays import is_trading_day

        next_trading_date = today + timedelta(days=1)
        while not is_trading_day(next_trading_date):
            next_trading_date += timedelta(days=1)

        # Pre-computed commands
        close_cmd = (
            f"python scripts/record/record_paper_trade.py "
            f"--strategy {pos.strategy_name} "
            f"--leg {pos.leg_role} "
            f"--action SELL "
            f"--qty {abs(pos.net_qty)} "
            f"--key {pos.instrument_key} "
            f"--price <SETTLEMENT_LTP> "
            f"--date {today.isoformat()} "
            f"--no-dry-run"
        )

        roll_cmd = (
            f"python scripts/record/record_paper_trade.py "
            f"--strategy {pos.strategy_name} "
            f"--leg {pos.leg_role} "
            f"--action BUY "
            f"--qty {abs(pos.net_qty)} "
            f"--key {next_key} "
            f"--price <ROLL_LTP> "
            f"--date {next_trading_date.isoformat()} "
            f"--no-dry-run"
        )

        expiring_inst = instruments.get_by_key(pos.instrument_key)
        expiring_symbol = (
            expiring_inst.get("trading_symbol", pos.instrument_key)
            if expiring_inst
            else pos.instrument_key
        )

        msg = (
            f"⚠️ *BASE POSITION EXPIRY ALERT*\n"
            f"Strategy: {pos.strategy_name}\n"
            f"Leg: {pos.leg_role}\n"
            f"Expiring Contract: {expiring_symbol} ({dte} DTE)\n"
            f"Next Contract: {next_symbol} (Key: {next_key}){warning_suffix}\n\n"
            f"Settlement Close:\n`{close_cmd}`\n\n"
            f"Roll Open:\n`{roll_cmd}`"
        )

        if notifier:
            try:
                await notifier.send(msg)
            except Exception as exc:
                logger.warning("base_expiry.notification_failed", error=str(exc))


async def compute_and_record_exit_signals(
    store: PaperStore,
    positions: list[PaperPosition],
    chain: OptionChain,
    snapshot_id: int | None,
    engine: type[ExitSignalEngine],
    today: date,
    notifier: TelegramNotifier | None = None,
    *,
    save: bool = True,
) -> None:
    """Evaluate exit signals for all open positions and persist ACTION/WARN events.

    Dispatches each open position to the correct ``ExitSignalEngine.evaluate_*``
    method by ``leg_role`` / ``strategy_name``.  Writes ACTION and WARN results
    to ``paper_exit_events`` with ``detected_by='EOD'``.  INFO signals are
    engine-internal only — never persisted.

    Deduplication: skips insert when an OPEN row already exists for the same
    ``(trade_id, exit_signal)`` dated today.

    Telegram: ACTION → one message per signal; WARN → batched per strategy;
    no signals → silence.  Notifier failures are logged but never propagate.

    Args:
        store: PaperStore for reads/writes.
        positions: All open paper positions across all strategies.
        chain: Parsed Nifty option chain (for delta, bid, ask, LTP lookups).
        snapshot_id: Optional NAV snapshot row id to link events.
        engine: ExitSignalEngine class (all methods are classmethods).
        today: Evaluation date.
        notifier: Optional TelegramNotifier; None suppresses Telegram alerts.
        save: When False (dry-run), skip DB writes and Telegram entirely.
    """
    if not save:
        return

    # Build dedup set from already-open events dated today
    today_iso = today.isoformat()
    existing: set[tuple[str, str]] = {
        (ev["trade_id"], ev["exit_signal"])
        for ev in store.get_open_exit_events()
        if ev["event_time"][:10] == today_iso
    }

    underlying_price = float(chain.underlying_spot)
    event_time = datetime.combine(today, datetime.min.time())

    action_messages: list[str] = []
    warn_by_strategy: dict[str, list[str]] = {}

    for pos in positions:
        if pos.net_qty == 0:
            continue

        results = _dispatch_evaluate(pos, chain, underlying_price, today)

        for result in results:
            if result.severity == "INFO":
                # INFO is engine-internal only — not written to DB
                continue

            key = (pos.instrument_key, result.exit_signal)
            if key in existing:
                logger.debug(
                    "exit_signal.dedup_skip",
                    trade_id=pos.instrument_key,
                    exit_signal=result.exit_signal,
                )
                continue

            is_short = pos.net_qty < 0
            entry_price = pos.avg_sell_price if is_short else pos.avg_cost
            opt_type = _OVERLAY_OPTION_TYPE.get(pos.leg_role, "PE" if is_short else "CE")
            opt_leg = _find_chain_leg(chain, pos.instrument_key, opt_type)

            # ExitSignalResult uses "WARN"; create_exit_event expects "WARNING"
            severity_store = "WARNING" if result.severity == "WARN" else result.severity

            try:
                event_id = store.create_exit_event(
                    strategy_name=pos.strategy_name,
                    leg_name=pos.leg_role,
                    trade_id=pos.instrument_key,
                    event_time=event_time,
                    detected_by="EOD",
                    exit_signal=ExitSignal(result.exit_signal),
                    severity=severity_store,
                    entry_price=entry_price,
                    snapshot_id=snapshot_id,
                    ltp=float(opt_leg.ltp) if opt_leg is not None else None,
                    bid=float(opt_leg.bid) if opt_leg is not None else None,
                    ask=float(opt_leg.ask) if opt_leg is not None else None,
                    delta=float(opt_leg.delta) if opt_leg is not None else None,
                    dte=_compute_dte(pos.instrument_key, today),
                    threshold_value=result.threshold_value,
                    delta_stop_would_fire=(
                        int(result.delta_stop_would_fire)
                        if result.delta_stop_would_fire is not None
                        else None
                    ),
                    premium_stop_would_fire=(
                        int(result.premium_stop_would_fire)
                        if result.premium_stop_would_fire is not None
                        else None
                    ),
                    actual_rule_used=result.actual_rule_used,
                    notes=result.notes,
                )
            # Intentional broad catch: DB write failure must not crash the snapshot.
            except Exception as exc:
                logger.error(
                    "exit_signal.db_write_failed",
                    strategy=pos.strategy_name,
                    leg=pos.leg_role,
                    signal=result.exit_signal,
                    error=str(exc),
                )
                continue

            existing.add(key)
            logger.info(
                "exit_signal.written",
                event_id=event_id,
                strategy=pos.strategy_name,
                leg=pos.leg_role,
                signal=result.exit_signal,
                severity=result.severity,
            )

            msg = (
                f"🚨 EXIT SIGNAL [{result.severity}] — {pos.strategy_name} / {pos.leg_role}\n"
                f"Signal: {result.exit_signal}\n"
                f"{result.notes or ''}"
            )
            if result.severity == "ACTION":
                action_messages.append(msg)
            else:  # WARN
                warn_by_strategy.setdefault(pos.strategy_name, []).append(
                    f"  • {pos.leg_role}: {result.exit_signal} — {result.notes or ''}"
                )

    if notifier is None:
        return

    for msg in action_messages:
        try:
            await notifier.send(msg)
        except Exception as exc:
            logger.warning("exit_signal.telegram_action_failed", error=str(exc))

    for strategy_name, warns in warn_by_strategy.items():
        batch = f"⚠️ EXIT WARN — {strategy_name}\n" + "\n".join(warns)
        try:
            await notifier.send(batch)
        except Exception as exc:
            logger.warning(
                "exit_signal.telegram_warn_failed",
                strategy=strategy_name,
                error=str(exc),
            )


# ── Per-leg delta calculation ─────────────────────────────────────────────────


def _leg_delta(
    store: PaperStore,
    strategy: str,
    leg_role: str,
    today_pnl: Decimal,
    today: date,
) -> Decimal | None:
    """Return today_pnl minus the prior day's total_pnl, or None if no prior snap.

    Synchronous — PaperStore calls are SQLite-backed, not async.
    """
    prev = store.get_prev_leg_snapshot(strategy, leg_role, before_date=today)
    if prev is None:
        return None
    return today_pnl - prev.total_pnl


# ── Display blocks ────────────────────────────────────────────────────────────


def _print_track_block(
    track_name: str,
    snapshot: TrackSnapshot,
    leg_deltas: dict[str, Decimal | None],
    today: date,
) -> None:
    """Print the full track block to stdout."""
    W = 88
    label = BASE_LABELS.get(track_name, track_name)
    pnl = snapshot.pnl

    # Merge collar legs
    grouped_overlay: dict[str, Decimal] = {}
    for role, amount in pnl.overlay_pnls.items():
        display = OVERLAY_LABELS.get(role, role)
        grouped_overlay[display] = grouped_overlay.get(display, Decimal("0")) + amount

    overlay_total = sum(grouped_overlay.values()) if grouped_overlay else Decimal("0")

    print(f"\n  {'─' * (W - 4)}")
    print(f"  {track_name.upper():<40} {label}")
    print(f"  {'─' * (W - 4)}")

    # Base leg
    base_delta = leg_deltas.get(_base_leg_role(track_name))
    print(
        f"  {'Base':<20} {_fmt(pnl.base_pnl):>12}"
        f"   unrealized={_fmt(pnl.unrealized_pnl)}  realized={_fmt(pnl.realized_pnl)}"
        f"{_delta_arrow(base_delta)}"
    )

    # Overlay legs
    if grouped_overlay:
        for display, amount in grouped_overlay.items():
            # Sum per-leg deltas for merged groups (collar)
            overlay_delta_sum: Decimal | None = None
            for role, _role_pnl in pnl.overlay_pnls.items():
                if OVERLAY_LABELS.get(role, role) == display:
                    rd = leg_deltas.get(role)
                    if rd is not None:
                        overlay_delta_sum = (overlay_delta_sum or Decimal("0")) + rd
            print(f"  {display:<20} {_fmt(amount):>12}{_delta_arrow(overlay_delta_sum)}")
        print(f"  {'─' * 38}")
        verdict = _hedge_verdict(pnl.base_pnl, overlay_total)
        print(f"  {'Net':<20} {_fmt(pnl.net_pnl):>12}   {verdict}")
    else:
        print(f"  {'Net':<20} {_fmt(pnl.net_pnl):>12}   (no overlay)")

    # Greeks + metrics
    g = snapshot.greeks
    print(f"  Greeks : Δ={g.net_delta:.3f}  Θ={g.net_theta:.2f}  V={g.net_vega:.2f}")
    print(
        f"  Metrics: MaxDD={snapshot.max_drawdown_pct:.2f}%"
        f"  (₹{snapshot.max_drawdown_abs:,.0f})"
        f"  Ret/NEE={snapshot.return_on_nee:.2f}%"
    )

    if snapshot.proxy_delta_alert:
        print(f"  ALERT  : {snapshot.proxy_delta_alert}")


def _base_leg_role(track_name: str) -> str:
    """Return the base leg_role for a track."""
    return {
        STRATEGY_SPOT: "base_etf",
        STRATEGY_FUTURES: "base_futures",
        STRATEGY_PROXY: "base_ditm_call",
    }.get(track_name, "base_etf")


def _overlay_roles_for_track(store: PaperStore, track_name: str, snap_date: date) -> list[str]:
    """Return all overlay leg_roles that have open or recently closed positions."""
    trades = store.get_trades(track_name)
    roles = {t.leg_role for t in trades if t.leg_role.startswith("overlay_")}
    return sorted(roles)


# ── Persistence ───────────────────────────────────────────────────────────────


def _save_nav_snapshot(
    store: PaperStore,
    track_name: str,
    snapshot: TrackSnapshot,
    snap_date: date,
    nifty_spot: Decimal,
) -> None:
    """Persist strategy-level NAV snapshot (paper_nav_snapshots table)."""
    pnl = snapshot.pnl
    nav = PaperNavSnapshot(
        strategy_name=track_name,
        snapshot_date=snap_date,
        unrealized_pnl=pnl.unrealized_pnl,
        realized_pnl=pnl.realized_pnl,
        total_pnl=pnl.net_pnl,
        underlying_price=nifty_spot,
    )
    store.record_nav_snapshot(nav)
    logger.info("NAV snapshot saved: %s %s total_pnl=%s", track_name, snap_date, pnl.net_pnl)


def _save_leg_snapshots(
    store: PaperStore,
    track_name: str,
    snapshot: TrackSnapshot,
    snap_date: date,
    ltp_map: dict[str, Decimal],
) -> None:
    """Persist per-leg snapshots (paper_leg_snapshots table) for all open legs."""
    pnl = snapshot.pnl

    # Base leg
    base_role = _base_leg_role(track_name)
    base_unrealized = pnl.unrealized_pnl - sum(pnl.overlay_pnls.values())
    # realized for base leg — approximation: realized_pnl minus overlay realized
    # (overlay realized is 0 while open; once closed it's tracked via overlay_pnls)
    base_realized = pnl.realized_pnl  # overlay realized captured separately below
    base_total = base_unrealized + base_realized

    pos = store.get_position(track_name, base_role)
    base_ltp = ltp_map.get(pos.instrument_key) if pos else None

    leg_snap = PaperLegSnapshot(
        strategy_name=track_name,
        leg_role=base_role,
        snapshot_date=snap_date,
        unrealized_pnl=base_unrealized,
        realized_pnl=base_realized,
        total_pnl=base_total,
        ltp=base_ltp,
    )
    store.record_leg_snapshot(leg_snap)

    # Overlay legs (one snapshot per leg_role)
    for role, overlay_pnl in pnl.overlay_pnls.items():
        overlay_pos = store.get_position(track_name, role)
        overlay_ltp = ltp_map.get(overlay_pos.instrument_key) if overlay_pos else None
        snap = PaperLegSnapshot(
            strategy_name=track_name,
            leg_role=role,
            snapshot_date=snap_date,
            unrealized_pnl=overlay_pnl,
            realized_pnl=Decimal("0"),  # realized only after close — updated by roll
            total_pnl=overlay_pnl,
            ltp=overlay_ltp,
        )
        store.record_leg_snapshot(snap)
        logger.debug("Leg snapshot saved: %s %s %s", track_name, role, snap_date)


# ── Summary table ─────────────────────────────────────────────────────────────


def _print_summary_table(
    results: list[tuple[str, TrackSnapshot]],
    today: date,
) -> None:
    """Print the cross-track comparison table."""
    W = 88
    print(f"\n{'═' * W}")
    print(f"  {'Track':<28} {'Base P&L':>12} {'Overlay':>12} {'Net P&L':>12} {'Ret/NEE':>9}")
    print(f"  {'─' * (W - 4)}")
    for name, snap in results:
        pnl = snap.pnl
        overlay_total = sum(pnl.overlay_pnls.values()) if pnl.overlay_pnls else Decimal("0")
        label = BASE_LABELS.get(name, name)
        print(
            f"  {label:<28} {_fmt(pnl.base_pnl):>12} {_fmt(overlay_total):>12}"
            f" {_fmt(pnl.net_pnl):>12} {float(snap.return_on_nee):>8.2f}%"
        )
    print(f"{'═' * W}")


# ── Main async orchestration ──────────────────────────────────────────────────


async def _run(args: argparse.Namespace) -> None:
    snap_date: date = args.date or date.today()
    save: bool = not args.dry_run

    _TRACK_MAP = {
        "spot": STRATEGY_SPOT,
        "futures": STRATEGY_FUTURES,
        "proxy": STRATEGY_PROXY,
    }
    tracks = [_TRACK_MAP[t] for t in args.tracks] if args.tracks else list(ALL_TRACKS)

    store = PaperStore(args.db_path)

    # Broker — graceful fallback for dry-run without token
    try:
        broker = UpstoxMarketClient()
    except ValueError:
        if args.dry_run:
            logger.warning("UPSTOX_ANALYTICS_TOKEN not set — using mock broker (dry-run mode).")

            class _MockBroker:
                async def get_ltp(self, keys: list[str]) -> dict[str, Decimal]:
                    return {k: Decimal("0.0") for k in keys}

                async def get_option_chain(self, u, e):
                    return []

            broker = _MockBroker()
        else:
            logger.error(
                "UPSTOX_ANALYTICS_TOKEN not set. Use --dry-run for a dry-run without live prices."
            )
            sys.exit(1)

    lookup = InstrumentLookup.from_file(args.bod_path)
    proxy_monitor = ProxyDeltaMonitor(store)

    # Telegram notifier (optional)
    bot_token = settings.telegram_bot_token or ""
    chat_id = settings.telegram_chat_id or ""
    notifier = TelegramNotifier(bot_token, chat_id) if (bot_token and chat_id) else None

    # Fetch Nifty spot — from --spot override if provided, else live LTP fetch.
    if args.spot:
        nifty_spot = Decimal(str(args.spot))
        logger.info("Using supplied spot: %.2f", float(nifty_spot))
    else:
        try:
            ltp_resp = await broker.get_ltp(["NSE_INDEX|Nifty 50"])
            raw = ltp_resp.get("NSE_INDEX|Nifty 50", 0)
            nifty_spot = Decimal(str(raw))
        # Intentional: top-level catch for daily snapshot failure.
        except Exception as exc:
            logger.error("Live spot fetch failed: %s — pass --spot <price> to override.", exc)
            sys.exit(1)
        if nifty_spot <= 0:
            logger.error("Live spot fetch returned 0. Pass --spot <price> to override.")
            sys.exit(1)
        logger.info("Live spot fetched: %.2f", float(nifty_spot))

    nee = compute_nee(nifty_spot, LOT_SIZE)

    W = 88
    mode = "DRY RUN — nothing written to DB" if not save else "SAVING to DB"
    print(f"\n{'═' * W}")
    print(
        f"  3-Track Snapshot  |  {snap_date}  |  Nifty {nifty_spot:,.2f}"
        f"  |  NEE ₹{nee:,.0f}  |  {mode}"
    )
    print(f"{'═' * W}")

    results: list[tuple[str, TrackSnapshot]] = []
    summary_rows = []

    for track_name in tracks:
        monitor = proxy_monitor if track_name == STRATEGY_PROXY else None
        snapshot = await generate_track_snapshot(
            store=store,
            broker=broker,
            lookup=lookup,
            track_namespace=track_name,
            nifty_spot=nifty_spot,
            nee=nee,
            snapshot_date=snap_date,
            proxy_monitor=monitor,
        )
        results.append((track_name, snapshot))

        pnl = snapshot.pnl
        overlay_total = sum(pnl.overlay_pnls.values()) if pnl.overlay_pnls else Decimal("0")
        summary_rows.append(
            {
                "track": BASE_LABELS.get(track_name, track_name),
                "base_pnl": pnl.base_pnl,
                "overlay_pnl": overlay_total,
                "net_pnl": pnl.net_pnl,
                "return_on_nee": snapshot.return_on_nee,
            }
        )

        # Collect LTP map from positions (needed for leg snapshot ltp field)
        trades = store.get_trades(track_name)
        leg_roles = {t.leg_role for t in trades}
        positions = [store.get_position(track_name, r) for r in leg_roles]
        inst_keys = [p.instrument_key for p in positions if p.instrument_key and p.net_qty != 0]
        raw_ltps: dict = {}
        if inst_keys:
            try:
                raw_ltps = await broker.get_ltp(inst_keys)
            # Intentional: catch all snapshot generation errors.
            except Exception as exc:
                logger.warning("LTP fetch for leg snapshots failed: %s", exc)
        ltp_map: dict[str, Decimal] = {k: Decimal(str(v)) for k, v in raw_ltps.items() if v}

        # Telegram critical alert
        if snapshot.proxy_delta_alert and "CRITICAL" in snapshot.proxy_delta_alert:
            msg = (
                f"🚨 *CRITICAL* Proxy Delta alert — {track_name}\n"
                f"Delta: {snapshot.greeks.net_delta:.3f}\n"
                f"Date: {snap_date}"
            )
            if notifier:
                try:
                    await notifier.send(msg)
                # Intentional: catch notification errors to avoid crashing main snapshot.
                except Exception as exc:
                    logger.warning("Telegram alert failed: %s", exc)

        # Persist if not dry-run
        if save:
            _save_nav_snapshot(store, track_name, snapshot, snap_date, nifty_spot)
            _save_leg_snapshots(store, track_name, snapshot, snap_date, ltp_map)

    # ── EOD exit signal evaluation (Tier 1) ──────────────────────────────────
    # Collect open positions across all tracks + CSP strategy, then fetch the
    # nearest monthly option chain and evaluate exit signals for each leg.
    # Skipped in dry-run mode (save=False) — no DB writes or Telegram alerts.
    if save:
        all_positions: list[PaperPosition] = []
        for sname in [*tracks, _CSP_STRATEGY]:
            all_positions.extend(store.get_positions(sname))

        eod_chain: OptionChain | None = None
        try:
            candidates = lookup.get_expiry_candidates(
                "NIFTY", snap_date, preference=["monthly", "quarterly"]
            )
            if candidates:
                _label, expiry_str = candidates[0]
                raw_chain = await broker.get_option_chain("NSE_INDEX|Nifty 50", expiry_str)
                chain_data = raw_chain if isinstance(raw_chain, list) else []
                eod_chain = parse_upstox_option_chain(chain_data)
        # Intentional: chain fetch failure must not crash the snapshot.
        except Exception as exc:
            logger.warning("exit_signals.chain_fetch_failed", error=str(exc))

        if eod_chain is not None:
            await compute_and_record_exit_signals(
                store=store,
                positions=all_positions,
                chain=eod_chain,
                snapshot_id=None,
                engine=ExitSignalEngine,
                today=snap_date,
                notifier=notifier,
                save=save,
            )

        # Check base position expiries (ES11)
        try:
            await _check_base_expiry(
                positions=all_positions,
                instruments=lookup,
                today=snap_date,
                store=store,
                notifier=notifier,
            )
        except Exception as exc:
            logger.warning("base_expiry.check_failed", error=str(exc))

    # Print summary table at the TOP (as requested)
    if summary_rows:
        print(
            "\n"
            + format_track_summary(
                summary_rows, title=f"Comparison Summary — {snap_date}", is_dry_run=args.dry_run
            )
        )

    # Print detailed blocks only if verbose
    if args.verbose:
        for track_name, snapshot in results:
            # Re-calculate leg_deltas for display
            pnl = snapshot.pnl
            leg_deltas = {}
            base_role = _base_leg_role(track_name)
            base_unrealized = pnl.unrealized_pnl - sum(pnl.overlay_pnls.values())
            base_total = base_unrealized + pnl.realized_pnl
            leg_deltas[base_role] = _leg_delta(store, track_name, base_role, base_total, snap_date)
            for role, role_pnl in pnl.overlay_pnls.items():
                leg_deltas[role] = _leg_delta(store, track_name, role, role_pnl, snap_date)

            _print_track_block(track_name, snapshot, leg_deltas, snap_date)

    if save:
        print(f"\n  ✅  All snapshots written to {args.db_path}\n")
    else:
        print("\n  ℹ️   Dry-run: no records written.\n")


def main() -> None:
    """CLI entry point."""
    pass

    parser = argparse.ArgumentParser(
        description=(
            "Canonical daily snapshot for the 3-Track Nifty Long Comparison framework.\n"
            "Writes paper_nav_snapshots + paper_leg_snapshots by default.\n"
            "Use --dry-run for a dry-run inspection (default: on)."
        ),
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
        "--spot",
        type=float,
        default=None,
        metavar="PRICE",
        help="Nifty 50 spot price (default: live fetch via UpstoxMarketClient).",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print report only — do not write to DB (default: on).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed per-leg P&L tables and Greeks.",
    )
    parser.add_argument(
        "--tracks",
        nargs="+",
        choices=["spot", "futures", "proxy"],
        metavar="TRACK",
        help="Restrict to specific tracks (default: all three).",
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
    setup_logging()
    main()
