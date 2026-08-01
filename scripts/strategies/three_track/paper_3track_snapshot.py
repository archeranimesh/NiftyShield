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
import calendar
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog

from src.client.upstox_market import parse_upstox_option_chain
from src.config import settings
from src.instruments.lookup import InstrumentLookup, parse_expiry
from src.market_calendar.holidays import is_trading_day
from src.models.options import OptionChain
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
from src.paper.models import (
    ExitSignal,
    OverlayPnLSnapshot,
    PaperLegSnapshot,
    PaperNavSnapshot,
    PaperPosition,
    TrackComparisonSnapshot,
    TradeState,
)
from src.paper.proxy_monitor import ProxyDeltaMonitor
from src.paper.store import PaperStore
from src.paper.track_snapshot import TrackSnapshot, generate_track_snapshot
from src.paper.tracker import _compute_realized_pnl_by_leg
from src.strategy.exit_signals import ExitSignalEngine
from src.utils.logging import bind_trace_id, generate_trace_id, setup_logging

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

from src.paper.chain_utils import (
    find_chain_leg as _find_chain_leg,
)
from src.paper.chain_utils import (
    parse_expiry_from_key as _parse_expiry_from_key,
)


def _compute_dte(instrument_key: str, today: date) -> int | None:
    """Return days-to-expiry for the key's embedded expiry, or None."""
    expiry = _parse_expiry_from_key(instrument_key)
    return (expiry - today).days if expiry is not None else None


def _dispatch_evaluate(
    pos: PaperPosition,
    chains: dict[date, OptionChain],
    underlying_price: float,
    today: date,
    lookup: InstrumentLookup | None = None,
) -> list:
    """Dispatch a position to the correct ExitSignalEngine.evaluate_* method.

    Returns [] for positions that are not signal-eligible (base legs, closed,
    or unrecognised strategy/role combinations).

    Args:
        pos: Open paper position.
        chains: Map of expiry date → parsed OptionChain.  The correct chain
            is selected per position by resolving the position's expiry.
        underlying_price: Nifty spot price as float.
        today: Evaluation date (for DTE and days_held calculations).
        lookup: Optional BOD instrument lookup for resolving numeric keys.

    Returns:
        List of ExitSignalResult objects (may be empty).
    """
    role = pos.leg_role
    dte = _compute_dte(pos.instrument_key, today) or 9999

    # Resolve the chain that covers this position's expiry.
    pos_expiry = (
        _get_expiry_date(pos.instrument_key, lookup)
        if lookup is not None
        else _parse_expiry_from_key(pos.instrument_key)
    )
    chain = chains.get(pos_expiry) if pos_expiry is not None else None
    if chain is None:
        # Fall back to any chain when expiry is unresolvable (e.g. non-option legs).
        chain = next(iter(chains.values()), None) if chains else None
    if chain is None:
        logger.warning(
            "dispatch_evaluate.no_chain_available",
            instrument_key=pos.instrument_key,
            expiry=str(pos_expiry),
        )
        return []

    if pos.strategy_name == _CSP_STRATEGY and pos.net_qty < 0:
        # Short put — CSP: five independent evaluators (CR1b)
        leg = _find_chain_leg(chain, pos.instrument_key, "PE", lookup)
        if leg is None:
            logger.warning(
                "dispatch_evaluate.csp_leg_not_found",
                instrument_key=pos.instrument_key,
                reason="chain_expiry_mismatch_or_unresolved_strike",
            )
            return []
        entry_credit = Decimal(str(pos.avg_sell_price))
        days_held = (today - pos.entry_date).days if pos.entry_date else 0
        results: list = []
        results += ExitSignalEngine.evaluate_profit_target_csp(
            ltp=Decimal(str(leg.ltp)), entry_credit=entry_credit
        )
        results += ExitSignalEngine.evaluate_hard_stop_csp(
            ltp=Decimal(str(leg.ltp)), entry_credit=entry_credit
        )
        results += ExitSignalEngine.evaluate_delta_breach_csp(
            delta=float(leg.delta) if leg.delta is not None else None, state=TradeState.OPEN
        )
        results += ExitSignalEngine.evaluate_time_stop_csp(days_held=days_held)
        results += ExitSignalEngine.evaluate_roll_eligible_csp(dte=dte)
        return ExitSignalEngine._sort_results(results)

    if role == "overlay_cc" and pos.net_qty < 0:
        leg = _find_chain_leg(chain, pos.instrument_key, "CE", lookup)
        if leg is None:
            logger.warning(
                "dispatch_evaluate.cc_leg_not_found",
                instrument_key=pos.instrument_key,
                reason="chain_expiry_mismatch_or_unresolved_strike",
            )
            return []
        if pos.entry_date:
            days_held = (today - pos.entry_date).days
        else:
            logger.warning(
                "dispatch_evaluate.entry_date_missing",
                leg_role=pos.leg_role,
                instrument_key=pos.instrument_key,
                reason="CC position entry_date is None, TIME_STOP will not fire",
            )
            days_held = 0
        return ExitSignalEngine.evaluate_cc(
            entry_price=float(pos.avg_sell_price),
            current_mark=float(leg.ltp),
            delta=float(leg.delta) if leg.delta is not None else None,
            dte=dte,
            days_held=days_held,
        )

    if role == "overlay_pp" and pos.net_qty > 0:
        leg = _find_chain_leg(chain, pos.instrument_key, "PE", lookup)
        if leg is None:
            logger.warning(
                "dispatch_evaluate.pp_leg_not_found",
                instrument_key=pos.instrument_key,
                reason="chain_expiry_mismatch_or_unresolved_strike",
            )
            return []
        return ExitSignalEngine.evaluate_pp(
            entry_price=float(pos.avg_cost),
            current_mark=float(leg.ltp),
            delta=float(leg.delta) if leg.delta is not None else None,
            dte=dte,
        )

    if role == "overlay_collar_call" and pos.net_qty < 0:
        leg = _find_chain_leg(chain, pos.instrument_key, "CE", lookup)
        if leg is None:
            logger.warning(
                "dispatch_evaluate.collar_call_leg_not_found",
                instrument_key=pos.instrument_key,
                reason="chain_expiry_mismatch_or_unresolved_strike",
            )
            return []
        if pos.entry_date:
            days_held = (today - pos.entry_date).days
        else:
            logger.warning(
                "dispatch_evaluate.entry_date_missing",
                leg_role=pos.leg_role,
                instrument_key=pos.instrument_key,
                reason="Collar position entry_date is None, TIME_STOP will not fire",
            )
            days_held = 0
        return ExitSignalEngine.evaluate_cc(
            entry_price=float(pos.avg_sell_price),
            current_mark=float(leg.ltp),
            delta=float(leg.delta) if leg.delta is not None else None,
            dte=dte,
            days_held=days_held,
        )

    if role == "overlay_collar_put":
        if pos.net_qty <= 0:
            logger.warning(
                "dispatch_evaluate.collar_put_invalid_qty",
                leg_role=pos.leg_role,
                instrument_key=pos.instrument_key,
                net_qty=pos.net_qty,
                reason="Collar put leg must have net_qty > 0 (long); short put will not be evaluated",
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
                last_day = calendar.monthrange(2000 + yy, month)[1]
                d = date(2000 + yy, month, last_day)
                while (
                    d.weekday() != 1
                ):  # Tuesday (SEBI change: NIFTY monthly expiry moved from Thu→Tue, Apr 2026)
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
                last_day = calendar.monthrange(year, month)[1]
                d = date(year, month, last_day)
                while (
                    d.weekday() != 1
                ):  # Tuesday (SEBI change: NIFTY monthly expiry moved from Thu→Tue, Apr 2026)
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
        # base_ditm_call must roll within the monthly/quarterly/yearly cadence, never
        # into a weekly contract — NIFTY options list a weekly expiry at every strike,
        # so a plain "next chronological expiry" walk lands on next week's contract.
        # base_futures has no weekly contract to begin with (NSE lists NIFTY futures
        # monthly-only), so the plain next-expiry walk is safe there.
        if pos.leg_role == "base_ditm_call":
            next_inst = instruments.get_next_contract_in_band(pos.instrument_key, today)
        else:
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
                threshold_value=Decimal("5"),
                notes=f"Next contract: {next_symbol} ({next_key})",
            )
        except Exception as exc:
            logger.warning("base_expiry.db_write_failed", error=str(exc))

        # Calculate next trading day
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
    chains: dict[date, OptionChain],
    snapshot_id: int | None,
    engine: type[ExitSignalEngine],
    today: date,
    notifier: TelegramNotifier | None = None,
    *,
    save: bool = True,
    lookup: InstrumentLookup | None = None,
    broker: Any | None = None,
    simulator: Any | None = None,
    vix: float | None = None,
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
        chains: Map of expiry date → parsed OptionChain.  Each position is
            evaluated against the chain matching its own expiry, preventing
            cross-expiry false signals (e.g. July CSP vs June chain → ltp=0).
        snapshot_id: Optional NAV snapshot row id to link events.
        engine: ExitSignalEngine class (all methods are classmethods).
        today: Evaluation date.
        notifier: Optional TelegramNotifier; None suppresses Telegram alerts.
        save: When False (dry-run), skip DB writes and Telegram entirely.
        lookup: BOD instrument lookup for resolving numeric keys to strikes.
        broker: Optional BrokerClient.
        simulator: Optional PaperFillSimulator for auto-close fills.
        vix: Optional VIX LTP value.
    """
    if not save:
        return

    if not chains:
        logger.warning("compute_and_record_exit_signals.no_chains_available")
        return

    # Build dedup set from already-open events dated today
    today_iso = today.isoformat()
    existing: set[tuple[str, str]] = {
        (ev["trade_id"], ev["exit_signal"])
        for ev in store.get_open_exit_events()
        if ev["event_time"][:10] == today_iso
    }

    first_chain = next(iter(chains.values()))
    underlying_price = float(first_chain.underlying_spot)
    event_time = datetime.combine(today, datetime.min.time())

    action_messages: list[str] = []
    warn_by_strategy: dict[str, list[str]] = {}

    for pos in positions:
        if pos.net_qty == 0:
            continue

        results = _dispatch_evaluate(pos, chains, underlying_price, today, lookup)

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
            # Use the position's expiry-specific chain for the opt_leg lookup.
            pos_expiry = (
                _get_expiry_date(pos.instrument_key, lookup)
                if lookup is not None
                else _parse_expiry_from_key(pos.instrument_key)
            )
            pos_chain = chains.get(pos_expiry) if pos_expiry is not None else first_chain
            opt_leg = _find_chain_leg(
                pos_chain or first_chain, pos.instrument_key, opt_type, lookup
            )

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
                    ltp=opt_leg.ltp if opt_leg is not None else None,
                    bid=opt_leg.bid if opt_leg is not None else None,
                    ask=opt_leg.ask if opt_leg is not None else None,
                    delta=float(opt_leg.delta)
                    if (opt_leg is not None and opt_leg.delta is not None)
                    else None,
                    dte=_compute_dte(pos.instrument_key, today),
                    threshold_value=(
                        Decimal(str(result.threshold_value))
                        if result.threshold_value is not None
                        else None
                    ),
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

            # Auto-close path for overlay ACTION signals (AUTO-1)
            event_row = store.get_exit_event(event_id)
            already_acted = event_row and event_row.get("status") == "ACTED"

            from src.strategy.auto_close import (
                AUTO_CLOSE_SIGNALS,
                OVERLAY_ROLES,
                auto_close_overlay,
            )

            if (
                (pos.leg_role, result.exit_signal) in AUTO_CLOSE_SIGNALS
                and simulator is not None
                and not already_acted
            ):
                # Find position's correct chain
                act_chain = pos_chain if pos_chain is not None else first_chain
                await auto_close_overlay(
                    store=store,
                    simulator=simulator,
                    pos=pos,
                    event_id=event_id,
                    chain=act_chain,
                    notifier=notifier,
                    lookup=lookup,
                    vix=vix,
                    exit_signal=result.exit_signal,
                )
                continue
            elif already_acted:
                continue

            # Suppress WARN for overlay roles — no noise for overlay monitoring signals
            if pos.leg_role in OVERLAY_ROLES:
                continue

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


def _compute_daily_deltas(
    results: list[tuple[str, TrackSnapshot]],
    store: PaperStore,
    snap_date: date,
) -> list[dict]:
    """Compute 1-day P&L delta fields for each track in the summary table.

    For each track: reads the prior leg snapshot for base and each overlay leg,
    computes today − prior.  Returns Decimal("0") when no prior snapshot exists.

    Args:
        results: List of (track_name, TrackSnapshot) pairs from the snapshot loop.
        store: PaperStore for reading prior leg snapshots.
        snap_date: Today's snapshot date.

    Returns:
        List of dicts with keys ``base_pnl``, ``overlay_pnl``, ``net_pnl``
        holding 1-day deltas; one dict per result entry (same order).
    """
    rows: list[dict] = []
    for track_name, snapshot in results:
        pnl = snapshot.pnl
        base_role = _base_leg_role(track_name)
        base_unrealized = pnl.unrealized_pnl - sum(pnl.overlay_pnls.values())
        base_total = base_unrealized + pnl.realized_pnl
        base_day = _leg_delta(store, track_name, base_role, base_total, snap_date) or Decimal("0")

        overlay_day = Decimal("0")
        for role, role_pnl in pnl.overlay_pnls.items():
            d = _leg_delta(store, track_name, role, role_pnl, snap_date)
            if d is not None:
                overlay_day += d

        rows.append(
            {
                "base_pnl": base_day,
                "overlay_pnl": overlay_day,
                "net_pnl": base_day + overlay_day,
            }
        )
    return rows


def _first_trading_day_of_month(ref_date: date) -> date:
    """Return the first NSE trading day of ref_date's month.

    Walks forward from the 1st until a trading day is found.

    Args:
        ref_date: Any date within the target month.

    Returns:
        The first NSE trading day of that calendar month.
    """
    candidate = date(ref_date.year, ref_date.month, 1)
    while not is_trading_day(candidate):
        candidate += timedelta(days=1)
    return candidate


def _compute_monthly_deltas(
    results: list[tuple[str, TrackSnapshot]],
    store: PaperStore,
    snap_date: date,
) -> list[dict]:
    """Compute month-to-date P&L delta fields for each track in the summary table.

    The MTD reference is the nearest prior leg snapshot on or before the first
    NSE trading day of snap_date's month.  Returns Decimal("0") when no such
    snapshot exists (e.g., first trading day of month with no prior data).

    Args:
        results: List of (track_name, TrackSnapshot) pairs from the snapshot loop.
        store: PaperStore for reading leg snapshots.
        snap_date: Today's snapshot date.

    Returns:
        List of dicts with keys ``base_pnl``, ``overlay_pnl``, ``net_pnl``
        holding MTD deltas; one dict per result entry (same order).
    """
    first_td = _first_trading_day_of_month(snap_date)
    # Use first_td + 1 day as exclusive upper bound so the snapshot ON first_td
    # is included (get_prev_leg_snapshot uses strict <).
    ref_date = first_td + timedelta(days=1)

    rows: list[dict] = []
    for track_name, snapshot in results:
        pnl = snapshot.pnl
        base_role = _base_leg_role(track_name)
        base_unrealized = pnl.unrealized_pnl - sum(pnl.overlay_pnls.values())
        base_total = base_unrealized + pnl.realized_pnl

        prev_base = store.get_prev_leg_snapshot(track_name, base_role, before_date=ref_date)
        base_day = (base_total - prev_base.total_pnl) if prev_base is not None else Decimal("0")

        overlay_day = Decimal("0")
        for role, role_pnl in pnl.overlay_pnls.items():
            prev = store.get_prev_leg_snapshot(track_name, role, before_date=ref_date)
            if prev is not None:
                overlay_day += role_pnl - prev.total_pnl

        rows.append(
            {
                "base_pnl": base_day,
                "overlay_pnl": overlay_day,
                "net_pnl": base_day + overlay_day,
            }
        )
    return rows


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

    # Compute per-leg realized P&L from the full trade ledger so that closed
    # overlay legs carry their actual realized amount rather than Decimal("0").
    all_trades = store.get_trades(track_name)
    realized_by_leg = _compute_realized_pnl_by_leg(all_trades)

    # Base leg
    base_role = _base_leg_role(track_name)
    base_unrealized = pnl.unrealized_pnl - sum(pnl.overlay_pnls.values())
    base_realized = realized_by_leg.get(base_role, Decimal("0"))
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

    # Overlay legs (one snapshot per real leg_role — never the collapsed
    # display label in pnl.overlay_pnls, e.g. "cc"/"collar"/"pp". Using the
    # display label here silently orphaned get_position() lookups and left
    # overlay_ltp always None (S7, 2026-07-28).
    for role, overlay_pnl in pnl.raw_overlay_pnls.items():
        overlay_pos = store.get_position(track_name, role)
        overlay_ltp = ltp_map.get(overlay_pos.instrument_key) if overlay_pos else None
        overlay_realized = realized_by_leg.get(role, Decimal("0"))
        snap = PaperLegSnapshot(
            strategy_name=track_name,
            leg_role=role,
            snapshot_date=snap_date,
            unrealized_pnl=overlay_pnl,
            realized_pnl=overlay_realized,
            total_pnl=overlay_pnl + overlay_realized,
            ltp=overlay_ltp,
        )
        store.record_leg_snapshot(snap)
        logger.debug("Leg snapshot saved: %s %s %s", track_name, role, snap_date)


# ── Track comparison snapshots (S3 — base-leg only, overlay excluded) ──────────
#
# RQ1 ("which base instrument tracks Nifty best") is answered here strictly
# from base-leg mark price. Overlay P&L (CC/PP/Collar) is real and reported
# elsewhere (paper_leg_snapshots / get_strategy_realized_pnl) but must never
# blend into or be inferred from these numbers, for any track — including
# NiftyBees. See docs/plan/3track-consolidation/stories.md S3.

_SPOT_SERIES_NAME = "nifty_index"


def _mark_value(ltp: Decimal | None, net_qty: int) -> Decimal | None:
    """Position mark value (LTP * absolute quantity), or None if LTP unknown."""
    if ltp is None:
        return None
    return ltp * abs(net_qty)


def _safe_pct(numerator: Decimal, denominator: Decimal | None) -> Decimal:
    """Percentage return, or 0 if the denominator is missing/zero."""
    if not denominator:
        return Decimal("0")
    return numerator / denominator


def _spot_price_on(store: PaperStore, track_name: str, on_date: date) -> Decimal | None:
    """Best-effort Nifty spot lookup for a date, reusing nav-snapshot history.

    ``paper_nav_snapshots.underlying_price`` already carries the Nifty spot
    fetched once per snapshot run — reused here instead of a second spot
    price history table.
    """
    for snap in store.get_nav_snapshots(track_name):
        if snap.snapshot_date == on_date:
            return snap.underlying_price
    return None


def _compute_track_comparison_snapshot(
    store: PaperStore,
    track_name: str,
    snap_date: date,
    nifty_spot: Decimal,
) -> TrackComparisonSnapshot | None:
    """Compute the S3 base-leg-only comparison snapshot for one 3-track strategy.

    Reads only the base leg (``_base_leg_role(track_name)``) — overlay legs
    never enter this calculation or its denominators. Must be called after
    ``_save_leg_snapshots`` has persisted today's base-leg row for this track.

    Returns:
        None if today's base-leg snapshot has not been persisted yet (should
        not happen in the standard ``_run`` flow, guarded defensively).
    """
    base_role = _base_leg_role(track_name)
    today_leg = store.get_leg_snapshot(track_name, base_role, snap_date)
    if today_leg is None:
        logger.warning(
            "track_comparison.no_base_leg_snapshot", track=track_name, date=str(snap_date)
        )
        return None

    pos = store.get_position(track_name, base_role)
    net_qty = pos.net_qty if pos else 0
    avg_cost = pos.avg_cost if pos else Decimal("0")
    entry_cost_basis = avg_cost * abs(net_qty) if net_qty else None

    pnl_inception_abs = today_leg.total_pnl
    pnl_inception_pct = _safe_pct(pnl_inception_abs, entry_cost_basis)

    prev = store.get_prev_leg_snapshot(track_name, base_role, snap_date)
    if prev is None:
        # First-ever snapshot for this leg: no prior mark to diff against —
        # today's cumulative move IS the 1-day move.
        pnl_1d_abs = pnl_inception_abs
        pnl_1d_pct = Decimal("0")
    else:
        pnl_1d_abs = today_leg.total_pnl - prev.total_pnl
        prev_mark_value = _mark_value(prev.ltp, net_qty)
        pnl_1d_pct = _safe_pct(pnl_1d_abs, prev_mark_value)

    tracking_error_pct: Decimal | None = None
    if pos is not None and pos.entry_date is not None:
        spot_entry = _spot_price_on(store, track_name, pos.entry_date)
        if spot_entry:
            spot_return_pct = (nifty_spot - spot_entry) / spot_entry
            tracking_error_pct = pnl_inception_pct - spot_return_pct

    return TrackComparisonSnapshot(
        strategy_name=track_name,
        snapshot_date=snap_date,
        pnl_1d_abs=pnl_1d_abs,
        pnl_1d_pct=pnl_1d_pct,
        pnl_inception_abs=pnl_inception_abs,
        pnl_inception_pct=pnl_inception_pct,
        tracking_error_pct=tracking_error_pct,
    )


# ── Overlay P&L snapshots (S8 — per-overlay, mirrors S3's shape) ───────────────
#
# Grouping mirrors _normalize_overlay_pnls' precedence exactly, so this table
# never diverges from the printed summary's collar-merge/CC-dedup convention:
# overlay_collar_call takes precedence over overlay_cc (same physical
# contract); collar_call + collar_put merge into one "collar" row; a lone
# collar_call (no put) or a lone overlay_cc surfaces as "cc"; overlay_pp is
# independent and always "pp".

_OVERLAY_ROLES = ("overlay_cc", "overlay_pp", "overlay_collar_call", "overlay_collar_put")


def _overlay_type_groups(present_roles: set[str]) -> dict[str, list[str]]:
    """Map real leg_roles present today to their overlay_type group.

    Args:
        present_roles: Real leg_role keys with a today's leg snapshot.

    Returns:
        Dict of overlay_type -> list of real leg_roles composing it.
    """
    groups: dict[str, list[str]] = {}
    has_call = "overlay_collar_call" in present_roles
    has_put = "overlay_collar_put" in present_roles
    has_cc = "overlay_cc" in present_roles
    has_pp = "overlay_pp" in present_roles

    if has_call and has_put:
        groups["collar"] = ["overlay_collar_call", "overlay_collar_put"]
    elif has_call:
        groups["cc"] = ["overlay_collar_call"]
    elif has_put:
        # Call leg closed/rolled off, put leg still open — still a "collar"
        # position (the protective put), not a dropped/orphaned leg. Logged
        # so a real lifecycle transition (not a bug) is visible in the cron
        # output, same spirit as _compute_track_comparison_snapshot's
        # no-base-leg-snapshot WARNING.
        logger.warning(
            "overlay_pnl.collar_put_without_call",
            detail="Collar call leg absent today, put leg still open — reporting as collar-put-only",
        )
        groups["collar"] = ["overlay_collar_put"]
    elif has_cc:
        groups["cc"] = ["overlay_cc"]

    if has_pp:
        groups["pp"] = ["overlay_pp"]

    return groups


def _leg_entry_basis(store: PaperStore, track_name: str, role: str) -> Decimal | None:
    """Entry cost/credit basis for one leg, or None if no open position.

    A short leg (e.g. CC's sold call, net_qty < 0) has no BUY trades, so
    ``avg_cost`` is zero — the real basis is the credit received, tracked
    separately as ``avg_sell_price``. A long leg (e.g. PP's bought put,
    net_qty > 0) uses ``avg_cost`` (debit paid) the same way S3's base legs
    do. Picking the wrong field for a short leg would silently zero out its
    denominator and produce a spurious 0% inception return.
    """
    pos = store.get_position(track_name, role)
    if pos is None or pos.net_qty == 0:
        return None
    per_unit = pos.avg_sell_price if pos.net_qty < 0 else pos.avg_cost
    return per_unit * abs(pos.net_qty)


def _compute_overlay_pnl_snapshots(
    store: PaperStore,
    track_name: str,
    snap_date: date,
) -> list[OverlayPnLSnapshot]:
    """Compute the S8 per-overlay comparison snapshots for one 3-track strategy.

    Reads only ``paper_leg_snapshots`` rows already persisted today by
    ``_save_leg_snapshots`` under the real overlay leg_roles (S7's fix) —
    never the collapsed display labels. One row per overlay_type present
    today; an overlay with no open/closed leg today produces no row (unlike
    S3's base-leg guard, there is no "should always exist" invariant here —
    a track may simply carry no overlay).

    Args:
        store: PaperStore instance.
        track_name: 3-track strategy the overlay is attached to.
        snap_date: Date of this snapshot.

    Returns:
        List of OverlayPnLSnapshot, one per overlay_type present today.
    """
    today_by_role: dict[str, PaperLegSnapshot] = {}
    for role in _OVERLAY_ROLES:
        leg = store.get_leg_snapshot(track_name, role, snap_date)
        if leg is not None:
            today_by_role[role] = leg

    groups = _overlay_type_groups(set(today_by_role))
    results: list[OverlayPnLSnapshot] = []

    for overlay_type, roles in groups.items():
        pnl_inception_abs = sum((today_by_role[r].total_pnl for r in roles), Decimal("0"))

        entry_basis = sum(
            (b for r in roles if (b := _leg_entry_basis(store, track_name, r)) is not None),
            Decimal("0"),
        )
        pnl_inception_pct = _safe_pct(pnl_inception_abs, entry_basis if entry_basis else None)

        prev_by_role: dict[str, PaperLegSnapshot] = {}
        for r in roles:
            prev = store.get_prev_leg_snapshot(track_name, r, snap_date)
            if prev is not None:
                prev_by_role[r] = prev

        if not prev_by_role:
            # First-ever snapshot for every role in this group: no prior mark
            # to diff against — today's cumulative move IS the 1-day move.
            pnl_1d_abs = pnl_inception_abs
            pnl_1d_pct = Decimal("0")
        else:
            pnl_1d_abs = pnl_inception_abs - sum(
                (prev_by_role[r].total_pnl for r in roles if r in prev_by_role), Decimal("0")
            )
            prev_mark_value = sum(
                (
                    _mark_value(prev_by_role[r].ltp, _position_qty(store, track_name, r))
                    or Decimal("0")
                    for r in roles
                    if r in prev_by_role
                ),
                Decimal("0"),
            )
            pnl_1d_pct = _safe_pct(pnl_1d_abs, prev_mark_value if prev_mark_value else None)

        results.append(
            OverlayPnLSnapshot(
                strategy_name=track_name,
                overlay_type=overlay_type,
                snapshot_date=snap_date,
                pnl_1d_abs=pnl_1d_abs,
                pnl_1d_pct=pnl_1d_pct,
                pnl_inception_abs=pnl_inception_abs,
                pnl_inception_pct=pnl_inception_pct,
            )
        )

    return results


def _position_qty(store: PaperStore, track_name: str, role: str) -> int:
    """Net quantity for a leg, or 0 if no position exists."""
    pos = store.get_position(track_name, role)
    return pos.net_qty if pos is not None else 0


def _compute_spot_comparison_snapshot(
    store: PaperStore,
    snap_date: date,
    nifty_spot: Decimal,
    entry_date: date | None,
) -> TrackComparisonSnapshot:
    """Compute the 4th synthetic ``"nifty_index"`` comparison series.

    Same pnl_1d/pnl_inception definitions as the three base tracks, with the
    spot price itself standing in for both mark and unit notional.
    ``entry_date`` anchors the inception denominator — callers pass the
    relevant track's base-leg entry_date. Today's live data has all three
    tracks entered the same day, so this is a single unambiguous value for
    now; if entry dates ever diverge across tracks, which one to anchor
    spot's inception% against becomes a real design question, flagged as an
    implementation-time detail in docs/plan/3track-consolidation/stories.md S3
    and not resolved here.
    """
    spot_entry = _spot_price_on(store, STRATEGY_SPOT, entry_date) if entry_date else None
    if spot_entry is None:
        # Bootstrap: no historical spot recorded yet for the entry date
        # (e.g. first-ever run) — use today's spot as a same-day proxy,
        # yielding a 0% inception return until real history accumulates.
        spot_entry = nifty_spot

    pnl_inception_abs = nifty_spot - spot_entry
    pnl_inception_pct = _safe_pct(pnl_inception_abs, spot_entry)

    prev_rows = store.get_track_comparison_snapshots(
        _SPOT_SERIES_NAME, end_date=snap_date - timedelta(days=1)
    )
    prev = prev_rows[-1] if prev_rows else None
    if prev is None:
        pnl_1d_abs = pnl_inception_abs
        pnl_1d_pct = Decimal("0")
    else:
        prev_spot = _spot_price_on(store, STRATEGY_SPOT, prev.snapshot_date)
        if prev_spot:
            pnl_1d_abs = nifty_spot - prev_spot
            pnl_1d_pct = _safe_pct(pnl_1d_abs, prev_spot)
        else:
            pnl_1d_abs = pnl_inception_abs - prev.pnl_inception_abs
            pnl_1d_pct = Decimal("0")

    return TrackComparisonSnapshot(
        strategy_name=_SPOT_SERIES_NAME,
        snapshot_date=snap_date,
        pnl_1d_abs=pnl_1d_abs,
        pnl_1d_pct=pnl_1d_pct,
        pnl_inception_abs=pnl_inception_abs,
        pnl_inception_pct=pnl_inception_pct,
        tracking_error_pct=None,
    )


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
    period: str = args.period

    _TRACK_MAP = {
        "spot": STRATEGY_SPOT,
        "futures": STRATEGY_FUTURES,
        "proxy": STRATEGY_PROXY,
    }
    tracks = [_TRACK_MAP[t] for t in args.tracks] if args.tracks else list(ALL_TRACKS)

    store = PaperStore(args.db_path)

    from src.client.factory import create_client

    # Broker — resolved via standard factory composition root (AUTO-1)
    try:
        broker = create_client(settings.upstox_env)
    except ValueError:
        if args.dry_run:
            logger.warning("Upstox client initialization failed — using mock broker (dry-run).")

            class _MockBroker:
                async def get_ltp(self, keys: list[str]) -> dict[str, Decimal]:
                    return {k: Decimal("0.0") for k in keys}

                async def get_option_chain(self, u, e):
                    return []

            broker = _MockBroker()
        else:
            logger.error(
                "Upstox client initialization failed. Use --dry-run for a dry-run without live prices."
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
        # overlay_pnls is normalized by generate_track_snapshot: keys are
        # "cc", "collar", "pp" — collar = call+put as one unit, no double-count.
        overlay_total = sum(pnl.overlay_pnls.values()) if pnl.overlay_pnls else Decimal("0")
        summary_rows.append(
            {
                "track": BASE_LABELS.get(track_name, track_name),
                "base_pnl": pnl.base_pnl,
                "overlay_pnl": overlay_total,
                # Per-overlay breakdown (collar = call+put as 1 unit)
                "cc_pnl": pnl.overlay_pnls.get("cc", Decimal("0")),
                "collar_pnl": pnl.overlay_pnls.get("collar", Decimal("0")),
                "pp_pnl": pnl.overlay_pnls.get("pp", Decimal("0")),
                "net_pnl": pnl.net_pnl,
                "return_on_nee": snapshot.return_on_nee,
            }
        )

        # Collect LTP map from positions (needed for leg snapshot ltp field).
        # PG-2b: get_positions() returns one row per (leg_role, instrument_key),
        # so a roll overlap (old + new instrument sharing a leg_role) is never
        # silently dropped the way per-leg_role get_position() calls could.
        positions = store.get_positions(track_name)
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
            cmp_snap = _compute_track_comparison_snapshot(store, track_name, snap_date, nifty_spot)
            if cmp_snap is not None:
                store.record_track_comparison_snapshot(cmp_snap)

            for overlay_snap in _compute_overlay_pnl_snapshots(store, track_name, snap_date):
                store.record_overlay_pnl_snapshot(overlay_snap)

    if save:
        # 4th synthetic series: Nifty spot, same fields/denominators as the
        # three tracks above. Anchored on STRATEGY_SPOT's base-leg entry_date
        # (see _compute_spot_comparison_snapshot docstring for the caveat if
        # tracks ever have divergent entry dates).
        spot_pos = store.get_position(STRATEGY_SPOT, _base_leg_role(STRATEGY_SPOT))
        spot_entry_date = spot_pos.entry_date if spot_pos else None
        spot_cmp_snap = _compute_spot_comparison_snapshot(
            store, snap_date, nifty_spot, spot_entry_date
        )
        store.record_track_comparison_snapshot(spot_cmp_snap)

    # ── EOD exit signal evaluation (Tier 1) ──────────────────────────────────
    # Collect open positions across all tracks + CSP strategy, derive unique
    # expiry dates, fetch one chain per expiry, and evaluate each position
    # against the chain that matches its own expiry.  This prevents cross-
    # expiry false signals (e.g. a Jul CSP evaluated against the Jun chain
    # returning ltp=0 and triggering a false PROFIT_TARGET).
    # Skipped in dry-run mode (save=False) — no DB writes or Telegram alerts.
    if save:
        all_positions: list[PaperPosition] = []
        for sname in [*tracks, _CSP_STRATEGY]:
            all_positions.extend(store.get_positions(sname))

        # Collect unique expiry dates from open option positions.
        unique_expiries: set[date] = set()
        for pos in all_positions:
            if pos.net_qty == 0:
                continue
            exp = _get_expiry_date(pos.instrument_key, lookup)
            if exp is not None:
                unique_expiries.add(exp)

        # Fallback: if no positions carry a parseable expiry, use nearest monthly.
        if not unique_expiries:
            try:
                candidates = lookup.get_expiry_candidates(
                    "NIFTY", snap_date, preference=["monthly", "quarterly"]
                )
                if candidates:
                    _label, expiry_str = candidates[0]
                    unique_expiries.add(date.fromisoformat(expiry_str))
            except Exception as exc:
                logger.warning("exit_signals.fallback_expiry_failed", error=str(exc))

        eod_chains: dict[date, OptionChain] = {}
        for expiry_date in unique_expiries:
            expiry_str = expiry_date.isoformat()
            try:
                raw_chain = await broker.get_option_chain("NSE_INDEX|Nifty 50", expiry_str)
                chain_data = raw_chain if isinstance(raw_chain, list) else []
                eod_chains[expiry_date] = parse_upstox_option_chain(chain_data)
                logger.info(
                    "exit_signals.chain_fetched",
                    expiry=expiry_str,
                    strikes=len(eod_chains[expiry_date].strikes),
                )
            # Intentional: per-expiry chain fetch failure must not crash the snapshot.
            except Exception as exc:
                logger.warning("exit_signals.chain_fetch_failed", expiry=expiry_str, error=str(exc))

        vix: float | None = None
        try:
            vix_resp = await broker.get_ltp(["NSE_INDEX|India VIX"])
            vix = float(vix_resp.get("NSE_INDEX|India VIX", 0.0))
        except Exception as exc:
            logger.warning("exit_signals.vix_fetch_failed", error=str(exc))

        from src.strategy.executor import PaperFillSimulator

        simulator = PaperFillSimulator()

        if eod_chains:
            await compute_and_record_exit_signals(
                store=store,
                positions=all_positions,
                chains=eod_chains,
                snapshot_id=None,
                engine=ExitSignalEngine,
                today=snap_date,
                notifier=notifier,
                save=save,
                lookup=lookup,
                broker=broker,
                simulator=simulator,
                vix=vix,
            )

            from src.strategy.auto_close import evaluate_pp_reentry_eod

            try:
                first_expiry_chain = next(iter(eod_chains.values()))
                await evaluate_pp_reentry_eod(
                    store=store,
                    simulator=simulator,
                    chain=first_expiry_chain,
                    lookup=lookup,
                    notifier=notifier,
                    vix_data_dir=Path(settings.vix_data_dir) if settings.vix_data_dir else None,
                    today=snap_date,
                )
            except Exception as exc:
                logger.warning("exit_signals.pp_reentry_failed", error=str(exc))

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
        display_rows = list(summary_rows)
        if period == "daily":
            daily_deltas = _compute_daily_deltas(results, store, snap_date)
            for i, delta_row in enumerate(daily_deltas):
                display_rows[i] = {**display_rows[i], **delta_row}
        elif period == "monthly":
            monthly_deltas = _compute_monthly_deltas(results, store, snap_date)
            for i, delta_row in enumerate(monthly_deltas):
                display_rows[i] = {**display_rows[i], **delta_row}
        print(
            "\n"
            + format_track_summary(
                display_rows,
                title=f"Comparison Summary — {snap_date}",
                is_dry_run=args.dry_run,
                period=period,
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

    # Mutually exclusive period flags (default: daily)
    period_group = parser.add_mutually_exclusive_group()
    period_group.add_argument(
        "--daily",
        "-d",
        dest="period",
        action="store_const",
        const="daily",
        help="Show 1-day P&L delta in the summary table (default).",
    )
    period_group.add_argument(
        "--monthly",
        "-m",
        dest="period",
        action="store_const",
        const="monthly",
        help="Show month-to-date P&L delta (not yet implemented — RPT-3).",
    )
    period_group.add_argument(
        "--inception",
        "-i",
        dest="period",
        action="store_const",
        const="inception",
        help="Show since-inception cumulative P&L in the summary table.",
    )
    parser.set_defaults(period="daily")

    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    setup_logging()
    bind_trace_id(generate_trace_id())
    main()
