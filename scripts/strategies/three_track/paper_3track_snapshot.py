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
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog

from src.client.upstox_market import parse_upstox_option_chain
from src.config import settings
from src.instruments.lookup import InstrumentLookup, parse_expiry
from src.market_calendar.holidays import is_trading_day
from src.models.options import OptionChain
from src.notifications.markdown import escape_markdown
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
from src.paper.constants import (
    DEFAULT_BOD_PATH,
    DEFAULT_DB_PATH,
    LOT_SIZE,
    STRATEGY_FUTURES,
    STRATEGY_OVERLAY,
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
    ProtectionRecoverySnapshot,
    TrackComparisonSnapshot,
    TradeState,
)
from src.paper.proxy_monitor import ProxyDeltaMonitor
from src.paper.store import PaperStore
from src.paper.track_snapshot import TrackSnapshot, generate_track_snapshot
from src.paper.tracker import _compute_leg_unrealized_pnl, _compute_realized_pnl_by_leg
from src.strategy.exit_signals import ExitSignalEngine
from src.utils.logging import bind_trace_id, generate_trace_id, setup_logging

# ── Constants ─────────────────────────────────────────────────────────────────

ALL_TRACKS = [STRATEGY_SPOT, STRATEGY_FUTURES, STRATEGY_PROXY]


_SCRIPT_NAME = "scripts.strategies.three_track.paper_3track_snapshot"
logger = structlog.get_logger(_SCRIPT_NAME)

_CSP_STRATEGY = "paper_csp_nifty_v1"

# BUG-032 (2026-08-24, council ruling): consecutive days a leg_role stays
# multi-instrument (>1 open position under one role) before the anomaly
# alert escalates from WARNING to ERROR. The council mandated *that* severity
# escalates on a stuck multi-day state but did not pin a specific N; 3 is a
# judgment call made here — long enough that a same-day roll overlap (e.g.
# PP3's intentional two-put window) never escalates, short enough that a
# genuinely stuck state (like the 2026-08-20 BUG-031 incident) escalates
# well before a full trading week passes.
_MULTI_INSTRUMENT_ESCALATION_DAYS = 3

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
        # EC-4: TIME_STOP's dte guard needs a real None on unresolvable expiry,
        # not the 9999 sentinel `dte` carries for evaluate_roll_eligible_csp.
        resolved_dte = None if dte == 9999 else dte
        results += ExitSignalEngine.evaluate_time_stop_csp(days_held=days_held, dte=resolved_dte)
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

    BUG-028 (2026-08-10): base-leg-only — tracks no longer carry overlay P&L,
    so there is nothing to fold in here. The standalone overlay book's own
    1-day P&L is reported separately (``_build_recovery_digest``, and the
    "Overlay (standalone)" summary row via ``_overlay_summary_row``).

    Args:
        results: List of (track_name, TrackSnapshot) pairs from the snapshot loop.
        store: PaperStore for reading prior leg snapshots.
        snap_date: Today's snapshot date.

    Returns:
        List of dicts with keys ``base_pnl``, ``net_pnl`` holding 1-day
        deltas; one dict per result entry (same order).
    """
    rows: list[dict] = []
    for track_name, snapshot in results:
        pnl = snapshot.pnl
        base_role = _base_leg_role(track_name)
        base_total = pnl.unrealized_pnl + pnl.realized_pnl
        base_day = _leg_delta(store, track_name, base_role, base_total, snap_date) or Decimal("0")

        rows.append(
            {
                "base_pnl": base_day,
                "net_pnl": base_day,
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

    BUG-028 (2026-08-10): base-leg-only — see ``_compute_daily_deltas``.

    The MTD reference is the nearest prior leg snapshot on or before the first
    NSE trading day of snap_date's month.  Returns Decimal("0") when no such
    snapshot exists (e.g., first trading day of month with no prior data).

    Args:
        results: List of (track_name, TrackSnapshot) pairs from the snapshot loop.
        store: PaperStore for reading leg snapshots.
        snap_date: Today's snapshot date.

    Returns:
        List of dicts with keys ``base_pnl``, ``net_pnl`` holding MTD deltas;
        one dict per result entry (same order).
    """
    first_td = _first_trading_day_of_month(snap_date)
    # Use first_td + 1 day as exclusive upper bound so the snapshot ON first_td
    # is included (get_prev_leg_snapshot uses strict <).
    ref_date = first_td + timedelta(days=1)

    rows: list[dict] = []
    for track_name, snapshot in results:
        pnl = snapshot.pnl
        base_role = _base_leg_role(track_name)
        base_total = pnl.unrealized_pnl + pnl.realized_pnl

        prev_base = store.get_prev_leg_snapshot(track_name, base_role, before_date=ref_date)
        base_day = (base_total - prev_base.total_pnl) if prev_base is not None else Decimal("0")

        rows.append(
            {
                "base_pnl": base_day,
                "net_pnl": base_day,
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
    """Print the full track block to stdout.

    BUG-028 (2026-08-10): base-leg-only. Overlay P&L (CC/PP/Collar) belongs
    to the independent ``STRATEGY_OVERLAY`` book and is printed separately —
    see the "Overlay (standalone)" block in ``_run`` (verbose mode).
    """
    W = 88
    label = BASE_LABELS.get(track_name, track_name)
    pnl = snapshot.pnl

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
    print(f"  {'Net':<20} {_fmt(pnl.net_pnl):>12}   (overlay reported separately, see below)")

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
    """Persist the base-leg snapshot (paper_leg_snapshots table) for a track.

    BUG-028 (2026-08-10): overlay legs are no longer persisted here — they
    belong to the independent ``STRATEGY_OVERLAY`` strategy and are persisted
    by ``_save_overlay_leg_snapshots`` instead.
    """
    pnl = snapshot.pnl

    all_trades = store.get_trades(track_name)
    realized_by_leg = _compute_realized_pnl_by_leg(all_trades)

    base_role = _base_leg_role(track_name)
    base_unrealized = pnl.unrealized_pnl
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
        net_qty=pos.net_qty if pos else 0,
    )
    store.record_leg_snapshot(leg_snap)


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
# Grouping precedence is owned by _overlay_type_groups (below) now that
# track_snapshot.py's _normalize_overlay_pnls was removed (BUG-028): overlay
# legs no longer flow through a track's snapshot at all, so this file is the
# sole place the collar-merge/CC-dedup convention lives.
# overlay_collar_call takes precedence over overlay_cc (same physical
# contract); collar_call + collar_put merge into one "collar" row; overlay_cc
# + collar_put also merge into "collar" (BUG-030: the entry-side dedup guard
# in paper_3track_overlay_entry.py deliberately tags the call leg overlay_cc
# instead of overlay_collar_call when a CC already covers the same
# instrument key — "the existing CC serves as the collar call" — so this
# combination is economically a collar and must not drop the cc leg's P&L);
# a lone collar_call (no put) or a lone overlay_cc (no put) surfaces as
# "cc"; overlay_pp is independent and always "pp".

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
    elif has_cc and has_put:
        # BUG-030 fix (2026-08-24): the call leg was intentionally tagged
        # overlay_cc rather than overlay_collar_call — see
        # build_overlay_trades()/_record_collar_trades()'s dedup guard in
        # paper_3track_overlay_entry.py, which deliberately skips inserting a
        # second short-call leg when an overlay_cc already covers the same
        # instrument key ("the existing CC serves as the collar call").
        # Economically this is a collar; both legs' P&L must be reported
        # together or the overlay_cc leg silently vanishes from every
        # downstream snapshot/digest (BUG-030).
        groups["collar"] = ["overlay_cc", "overlay_collar_put"]
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
    """Entry cost/credit basis for one leg-role, or None if no open position.

    BUG-032 (2026-08-24, council ruling): resolved via ``get_positions()``
    filtered by ``role``, summed across every open instrument under that
    role — never via ``get_position()``'s single-match API, which silently
    drops all but the most-recent position when a role holds >1 open
    instrument (the exact defect BUG-032 fixes). Hard invariant: sum each
    instrument's own basis, never blend cost bases across instruments first.

    A short leg (e.g. CC's sold call, net_qty < 0) has no BUY trades, so
    ``avg_cost`` is zero — the real basis is the credit received, tracked
    separately as ``avg_sell_price``. A long leg (e.g. PP's bought put,
    net_qty > 0) uses ``avg_cost`` (debit paid) the same way S3's base legs
    do. Picking the wrong field for a short leg would silently zero out its
    denominator and produce a spurious 0% inception return.
    """
    matches = [p for p in store.get_positions(track_name) if p.leg_role == role]
    if not matches:
        return None
    total = Decimal("0")
    for pos in matches:
        per_unit = pos.avg_sell_price if pos.net_qty < 0 else pos.avg_cost
        total += per_unit * abs(pos.net_qty)
    return total if total else None


def _compute_overlay_pnl_snapshots(
    store: PaperStore,
    snap_date: date,
) -> list[OverlayPnLSnapshot]:
    """Compute the per-overlay P&L snapshots for the standalone overlay book.

    BUG-028 fix (2026-08-10): overlay legs (CC/PP/Collar) live under the
    independent ``STRATEGY_OVERLAY`` strategy_name since S2r (2026-07-29),
    not under whichever 3-track strategy they might once have been attached
    to — this queries ``STRATEGY_OVERLAY`` directly instead of inheriting a
    base-track loop's ``strategy_name``, which was the actual root cause of
    the silent-zero bug (the real rows were always filed elsewhere).

    Reads only ``paper_leg_snapshots`` rows already persisted today by
    ``_save_overlay_leg_snapshots`` under ``STRATEGY_OVERLAY`` + the real
    overlay leg_roles — never the collapsed display labels. One row per
    overlay_type present today; no open/closed leg today produces no row.

    Args:
        store: PaperStore instance.
        snap_date: Date of this snapshot.

    Returns:
        List of OverlayPnLSnapshot, one per overlay_type present today, all
        stamped ``strategy_name=STRATEGY_OVERLAY`` (BUG-028's canonical
        attribution — no schema change, same
        ``(strategy_name, overlay_type, snapshot_date)`` primary key).
    """
    today_by_role: dict[str, PaperLegSnapshot] = {}
    for role in _OVERLAY_ROLES:
        leg = store.get_leg_snapshot(STRATEGY_OVERLAY, role, snap_date)
        if leg is not None:
            today_by_role[role] = leg

    groups = _overlay_type_groups(set(today_by_role))
    results: list[OverlayPnLSnapshot] = []

    for overlay_type, roles in groups.items():
        pnl_inception_abs = sum((today_by_role[r].total_pnl for r in roles), Decimal("0"))

        entry_basis = sum(
            (b for r in roles if (b := _leg_entry_basis(store, STRATEGY_OVERLAY, r)) is not None),
            Decimal("0"),
        )
        pnl_inception_pct = _safe_pct(pnl_inception_abs, entry_basis if entry_basis else None)

        prev_by_role: dict[str, PaperLegSnapshot] = {}
        for r in roles:
            prev = store.get_prev_leg_snapshot(STRATEGY_OVERLAY, r, snap_date)
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
            # BUG-036 fix (2026-08-24): use the QUANTITY THAT WAS ACTUALLY
            # OPEN on prev_by_role[r]'s snapshot date (prev_by_role[r].net_qty),
            # not today's live quantity — closes the apples-to-oranges gap
            # where a day-over-day partial close/add blended today's size
            # with yesterday's price. Falls back to today's _position_qty()
            # (the pre-fix behavior) only for legacy rows written before
            # net_qty existed and not yet covered by the backfill script
            # (scripts/dev/backfill_leg_snapshot_net_qty.py) — those still
            # carry the original, documented imprecision until backfilled.
            #
            # REMAINING KNOWN GAP (not fixed here, still BUG-036/symptom 1):
            # when yesterday's snapshot was a multi-instrument aggregate,
            # prev_by_role[r].ltp is NULL by design (a single LTP would
            # misrepresent >1 open instrument) — _mark_value then returns
            # None and that role still contributes 0 to prev_mark_value,
            # understating the pnl_1d_pct denominator for one day. The
            # ideal fix — Σ_i ltp_i × abs(qty_i) from yesterday's
            # per-instrument marks — needs the per-instrument companion
            # table the BUG-032 council ruling explicitly deferred as a
            # separate follow-up story.
            prev_mark_value = sum(
                (
                    _mark_value(
                        prev_by_role[r].ltp,
                        prev_by_role[r].net_qty
                        if prev_by_role[r].net_qty is not None
                        else _position_qty(store, STRATEGY_OVERLAY, r),
                    )
                    or Decimal("0")
                    for r in roles
                    if r in prev_by_role
                ),
                Decimal("0"),
            )
            pnl_1d_pct = _safe_pct(pnl_1d_abs, prev_mark_value if prev_mark_value else None)

        results.append(
            OverlayPnLSnapshot(
                strategy_name=STRATEGY_OVERLAY,
                overlay_type=overlay_type,
                snapshot_date=snap_date,
                pnl_1d_abs=pnl_1d_abs,
                pnl_1d_pct=pnl_1d_pct,
                pnl_inception_abs=pnl_inception_abs,
                pnl_inception_pct=pnl_inception_pct,
            )
        )

    return results


def _overlay_positions_by_role(
    store: PaperStore, strategy_name: str
) -> dict[str, list[PaperPosition]]:
    """Group a strategy's open positions by leg_role.

    BUG-032 (2026-08-24): unlike ``get_position(strategy_name, leg_role)``,
    this never silently drops a position when a role holds >1 open
    instrument — every open ``(leg_role, instrument_key)`` pair from
    ``get_positions()`` (PG-1, flat pairs already excluded) is represented.
    """
    by_role: dict[str, list[PaperPosition]] = defaultdict(list)
    for pos in store.get_positions(strategy_name):
        by_role[pos.leg_role].append(pos)
    return dict(by_role)


def _overlay_multi_instrument_streak_days(
    store: PaperStore, role: str, snap_date: date, max_lookback: int = 30
) -> int:
    """Count consecutive prior days this role's snapshot was multi-instrument.

    A multi-instrument day is marked by ``paper_leg_snapshots.ltp is None``
    (BUG-032's write-time contract: a single LTP for >1 open instrument would
    misrepresent the aggregate, so the field is NULL exactly when a role held
    more than one open position that day). Walks backward through the actual
    snapshot chain (via ``get_prev_leg_snapshot``, so weekends/holidays with
    no snapshot row are skipped correctly) until a single-instrument or
    missing snapshot breaks the streak, or ``max_lookback`` is reached.
    """
    streak = 0
    cursor = snap_date
    for _ in range(max_lookback):
        prev = store.get_prev_leg_snapshot(STRATEGY_OVERLAY, role, cursor)
        if prev is None or prev.ltp is not None:
            break
        streak += 1
        cursor = prev.snapshot_date
    return streak


async def _check_overlay_multi_instrument_alert(
    store: PaperStore,
    role: str,
    snap_date: date,
    n: int,
    notifier: TelegramNotifier | None,
) -> None:
    """Fire/dedup the BUG-032 anomaly alert for a role holding >1 open instrument.

    Council ruling (2026-08-24): alert on the first day a role transitions
    into ``n > 1`` (WARNING) and again when the streak crosses
    ``_MULTI_INSTRUMENT_ESCALATION_DAYS`` (bumped to ERROR) — never re-fire
    Telegram on every subsequent run while the condition persists, though
    every multi-instrument day still gets a structured log line. Logs (and
    Telegrams) a recovery message the first day the role returns to ``n <= 1``
    after a multi-instrument streak.

    Logging always runs regardless of ``notifier`` — only the Telegram send
    is conditional on it. A code-reviewer pass on this fix (2026-08-24) found
    the original version gated the *entire* check (including the structured
    log lines) on ``notifier is not None``, which meant the anomaly went
    completely silent — no log, no alert — whenever Telegram credentials were
    unset in production. That would have reproduced BUG-032's own "silent
    failure" shape one level up, in the fix meant to prevent it.
    """
    prev = store.get_prev_leg_snapshot(STRATEGY_OVERLAY, role, snap_date)
    was_multi = prev is not None and prev.ltp is None

    if n <= 1:
        if was_multi:
            logger.info("overlay_pnl.multi_instrument_role_recovered", leg_role=role)
            if notifier is not None:
                try:
                    await notifier.send(
                        f"✅ overlay {role}: back to a single open instrument — "
                        f"P&L snapshot resumed normal (BUG-032)."
                    )
                # Intentional: notification failure must not crash the snapshot.
                except Exception as exc:
                    logger.warning("overlay_leg_totals.telegram_failed", error=str(exc))
        return

    streak_before = _overlay_multi_instrument_streak_days(store, role, snap_date)
    today_streak = streak_before + 1
    escalated = today_streak >= _MULTI_INSTRUMENT_ESCALATION_DAYS

    logger.warning(
        "overlay_pnl.multi_instrument_role",
        leg_role=role,
        open_instrument_count=n,
        streak_days=today_streak,
        severity="ERROR" if escalated else "WARNING",
    )

    if notifier is not None and (
        streak_before == 0 or today_streak == _MULTI_INSTRUMENT_ESCALATION_DAYS
    ):
        icon = "🚨 *ERROR*" if escalated else "⚠️ *WARNING*"
        try:
            await notifier.send(
                f"{icon} overlay {role}: {n} open instruments under one role for "
                f"{today_streak} day(s) — aggregating P&L across all of them, LTP "
                f"shown as N/A on the snapshot row. See BUG-032."
            )
        # Intentional: notification failure must not crash the snapshot.
        except Exception as exc:
            logger.warning("overlay_leg_totals.telegram_failed", error=str(exc))


async def _compute_overlay_leg_totals(
    store: PaperStore,
    broker: Any,
    snap_date: date,
    notifier: TelegramNotifier | None = None,
) -> dict[str, tuple[Decimal, Decimal, Decimal, Decimal | None, int]]:
    """Compute today's per-leg-role P&L for the standalone overlay book.

    BUG-028 (2026-08-10): the overlay book (``STRATEGY_OVERLAY``) is no
    longer discovered as a side effect of a 3-track base snapshot — it is
    computed directly here, independent of which tracks were selected via
    ``--tracks``. In-memory only (does not read/write ``paper_leg_snapshots``
    itself); used both to persist today's rows (``_save_overlay_leg_snapshots``,
    gated on ``save``) and to populate the dry-run preview summary row
    (``_overlay_summary_row``, always).

    BUG-032 (2026-08-24, council ruling): resolved via ``get_positions()``
    grouped by role rather than ``get_position()``'s single-match API, which
    silently dropped all but the most-recently-opened position when a role
    held >1 open instrument. When a role holds exactly one open instrument,
    behavior is unchanged. When a role holds more than one:

    - Each instrument's unrealized P&L is computed independently against its
      own LTP and then summed — cost bases/LTPs across different strikes or
      expiries are never blended into one average (no tradeable meaning).
    - The snapshot's ``ltp`` field is ``None`` — a single LTP for a
      multi-instrument aggregate would misrepresent the book (the exact
      misrepresentation that hid this bug for 4+ days originally).
    - If any open instrument's LTP is unavailable, that role's snapshot is
      omitted entirely today (fail loud, not a silent partial aggregate) —
      an ERROR log + Telegram alert fires, and unrelated roles still persist.
    - A deduplicated anomaly alert (``_check_overlay_multi_instrument_alert``)
      fires on the transition into/out of the multi-instrument state, not on
      every cron run while it persists.

    Args:
        store: PaperStore instance.
        broker: BrokerClient (or dry-run mock) for the LTP fetch.
        snap_date: Date of this snapshot.
        notifier: Optional TelegramNotifier for the BUG-032 anomaly alert.
            None suppresses the alert (log lines still fire) — used by
            dry-run/preview callers that don't want Telegram side effects.

    Returns:
        Mapping of leg_role -> (unrealized_pnl, realized_pnl, total_pnl, ltp,
        net_qty). ``net_qty`` is summed across every open instrument under
        the role (BUG-036) — same "sum independently, never blend" discipline
        as unrealized_pnl above.
        Empty dict if ``STRATEGY_OVERLAY`` has never had a trade recorded —
        distinguishes "overlay book never entered" from "entered, now flat."
        A role can be absent even when trades exist for it, if it is
        currently multi-instrument with a missing LTP (see above).
    """
    trades = store.get_trades(STRATEGY_OVERLAY)
    if not trades:
        return {}

    leg_roles = sorted({t.leg_role for t in trades})
    realized_by_leg = _compute_realized_pnl_by_leg(trades)
    positions_by_role = _overlay_positions_by_role(store, STRATEGY_OVERLAY)

    open_keys = sorted(
        {
            pos.instrument_key
            for matches in positions_by_role.values()
            for pos in matches
            if pos.instrument_key
        }
    )
    ltp_map: dict[str, Decimal] = {}
    if open_keys:
        try:
            raw = await broker.get_ltp(open_keys)
            ltp_map = {k: Decimal(str(v)) for k, v in raw.items() if v}
        # Intentional: isolate overlay LTP fetch errors from the rest of the run.
        except Exception as exc:
            logger.warning("overlay_leg_totals.ltp_fetch_failed", error=str(exc))

    totals: dict[str, tuple[Decimal, Decimal, Decimal, Decimal | None, int]] = {}
    for role in leg_roles:
        matches = positions_by_role.get(role, [])
        realized = realized_by_leg.get(role, Decimal("0"))
        n = len(matches)

        if n == 0:
            totals[role] = (Decimal("0"), realized, realized, None, 0)
        elif n == 1:
            pos = matches[0]
            overlay_ltp = ltp_map.get(pos.instrument_key) if pos.instrument_key else None
            if overlay_ltp is not None:
                unrealized = _compute_leg_unrealized_pnl(pos, overlay_ltp)
            else:
                logger.warning(
                    "overlay_leg_totals.ltp_unavailable",
                    instrument_key=pos.instrument_key,
                    leg_role=role,
                )
                unrealized = Decimal("0")
            totals[role] = (unrealized, realized, unrealized + realized, overlay_ltp, pos.net_qty)
        else:
            # BUG-032: role holds >1 open instrument. Value each
            # independently and sum — never blend cost bases/LTPs.
            missing_keys = [p.instrument_key for p in matches if p.instrument_key not in ltp_map]
            if missing_keys:
                logger.error(
                    "overlay_leg_totals.multi_instrument_ltp_missing",
                    leg_role=role,
                    missing_instrument_keys=missing_keys,
                )
                if notifier is not None:
                    try:
                        await notifier.send(
                            f"🚨 *ERROR* overlay {role}: {n} open instruments, missing LTP "
                            f"for {missing_keys} — P&L snapshot skipped for this role today "
                            f"(BUG-032, fail-loud, not a partial aggregate)."
                        )
                    # Intentional: notification failure must not crash the snapshot.
                    except Exception as exc:
                        logger.warning("overlay_leg_totals.telegram_failed", error=str(exc))
                # Council ruling: do not write a partial aggregate for a
                # multi-instrument role with an unpriced leg — omit it
                # entirely today rather than reporting an incomplete number.
                continue
            unrealized = sum(
                (_compute_leg_unrealized_pnl(p, ltp_map[p.instrument_key]) for p in matches),
                Decimal("0"),
            )
            net_qty = sum(p.net_qty for p in matches)
            totals[role] = (unrealized, realized, unrealized + realized, None, net_qty)

        # Runs regardless of `notifier` — logging must not go silent just
        # because Telegram credentials were unset (code-review finding,
        # 2026-08-24; see _check_overlay_multi_instrument_alert docstring).
        await _check_overlay_multi_instrument_alert(store, role, snap_date, n, notifier)

    return totals


def _save_overlay_leg_snapshots(
    store: PaperStore,
    totals: dict[str, tuple[Decimal, Decimal, Decimal, Decimal | None, int]],
    snap_date: date,
) -> None:
    """Persist today's standalone overlay leg snapshots (``paper_leg_snapshots``).

    BUG-028 (2026-08-10): overlay legs are their own strategy
    (``STRATEGY_OVERLAY``) now — no longer discovered/persisted as a side
    effect of any 3-track base snapshot (see ``_save_leg_snapshots``, which
    now writes the base leg only).
    """
    for role, (unrealized, realized, total, ltp, net_qty) in totals.items():
        snap = PaperLegSnapshot(
            strategy_name=STRATEGY_OVERLAY,
            leg_role=role,
            snapshot_date=snap_date,
            unrealized_pnl=unrealized,
            realized_pnl=realized,
            total_pnl=total,
            ltp=ltp,
            net_qty=net_qty,
        )
        store.record_leg_snapshot(snap)
        logger.debug("Overlay leg snapshot saved: %s %s", role, snap_date)


def _overlay_summary_row(
    totals: dict[str, tuple[Decimal, Decimal, Decimal, Decimal | None, int]],
) -> dict | None:
    """Build the standalone overlay summary row for the printed comparison table.

    BUG-028 Phase 1 (2026-08-10): overlay P&L is no longer folded into any
    track's row — it gets exactly one row, independent of ``--tracks``
    selection, matching the council-mandated "NiftyBees vs standalone overlay
    book" framing (no "active track" selection).

    Returns:
        None when the overlay book has never been entered (``totals`` empty)
        — the row is omitted rather than shown as a false ``₹0`` (BUG-028
        Phase 2's no-silent-zero mandate applies to the digest; applying the
        same principle here for consistency, even though Phase 2's formal
        WARNING-logging scope is the leg-source layer, not this row).
    """
    if not totals:
        return None

    groups = _overlay_type_groups(set(totals) & set(_OVERLAY_ROLES))
    by_type = {
        overlay_type: sum((totals[r][2] for r in roles if r in totals), Decimal("0"))
        for overlay_type, roles in groups.items()
    }
    overlay_total = sum(by_type.values(), Decimal("0"))
    return {
        "track": "Overlay (standalone)",
        "base_pnl": Decimal("0"),
        "overlay_pnl": overlay_total,
        "cc_pnl": by_type.get("cc", Decimal("0")),
        "collar_pnl": by_type.get("collar", Decimal("0")),
        "pp_pnl": by_type.get("pp", Decimal("0")),
        "net_pnl": overlay_total,
        "return_on_nee": 0.0,
    }


def _position_qty(store: PaperStore, track_name: str, role: str) -> int:
    """Net quantity for a leg-role, summed across every open instrument.

    BUG-032 (2026-08-24, council ruling): sum, not pick-one — resolved via
    ``get_positions()`` filtered by ``role`` rather than ``get_position()``'s
    single-match API, so a role holding >1 open instrument contributes its
    full combined quantity instead of only the most-recently-opened leg's.
    0 if no open position exists.
    """
    return sum(p.net_qty for p in store.get_positions(track_name) if p.leg_role == role)


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


# ── Protection recovery (S9 — NiftyBees vs overlay recovery) ───────────────────


def _best_recovery(
    niftybees_pnl: Decimal,
    overlay_pnls: dict[str, Decimal | None],
) -> tuple[str | None, Decimal | None]:
    """Pick the overlay with the largest recovery share on a red day.

    ``recovery_pct`` is only meaningful when ``niftybees_pnl < 0`` — on a
    flat/green day there is nothing to recover, so both return values are
    ``None`` rather than a misleading zero/negative-anchored figure
    (confirmed with operator, stories.md S9).

    BUG-028 Phase 2: ``overlay_pnls`` values may be ``None`` (source data
    absent for that type/date, see ``_compute_protection_recovery_snapshot``)
    — a missing overlay can never be "best," it's simply excluded from
    consideration, not treated as a recovery of 0.

    Args:
        niftybees_pnl: NiftyBees P&L for the period (1d or inception).
        overlay_pnls: Mapping of overlay_type -> P&L for the same period,
            ``None`` where source data is missing.

    Returns:
        ``(best_overlay, best_recovery_pct)``, both ``None`` together when
        ``niftybees_pnl >= 0`` or when every overlay type is missing data.
    """
    if niftybees_pnl >= 0:
        return None, None
    denom = abs(niftybees_pnl)
    best_type: str | None = None
    best_pct: Decimal | None = None
    for overlay_type, pnl in overlay_pnls.items():
        if pnl is None:
            continue
        pct = pnl / denom
        if best_pct is None or pct > best_pct:
            best_type, best_pct = overlay_type, pct
    return best_type, best_pct


def _compute_protection_recovery_snapshot(
    store: PaperStore,
    snap_date: date,
) -> ProtectionRecoverySnapshot | None:
    """Compute the S9 recovery comparison row for one date.

    Reads S3's ``paper_track_comparison_snapshots`` (NiftyBees row,
    ``strategy_name == STRATEGY_SPOT`` — the base-leg comparison is still
    anchored on the spot track, that half is untouched by BUG-028) and S8's
    ``paper_overlay_pnl_snapshots`` (cc/pp/collar rows, BUG-028 fix: now
    ``strategy_name == STRATEGY_OVERLAY``, the standalone overlay book — was
    incorrectly ``STRATEGY_SPOT`` before this fix, which is why every overlay
    leg opened after S2r (2026-07-29) read back as a silent zero here) for
    the same ``snap_date`` — no independent leg-level computation, per
    stories.md S9. Must be called after
    ``_compute_track_comparison_snapshot``/``_compute_overlay_pnl_snapshots``
    have persisted today's rows.

    Returns:
        None if today's NiftyBees S3 row has not been persisted yet
        (should not happen in the standard ``_run`` flow, guarded
        defensively — mirrors ``_compute_track_comparison_snapshot``'s
        own-day guard).
    """
    niftybees_rows = store.get_track_comparison_snapshots(
        STRATEGY_SPOT, start_date=snap_date, end_date=snap_date
    )
    if not niftybees_rows:
        logger.warning("protection_recovery.no_niftybees_snapshot", date=str(snap_date))
        return None
    niftybees = niftybees_rows[0]

    # BUG-028 Phase 2: default to None ("source data absent"), never
    # Decimal("0") — a missing OverlayPnLSnapshot row must not read back
    # indistinguishably from "overlay observed, computed to no change."
    overlay_1d: dict[str, Decimal | None] = {"cc": None, "pp": None, "collar": None}
    overlay_inception: dict[str, Decimal | None] = dict(overlay_1d)
    for overlay_type in ("cc", "pp", "collar"):
        rows = store.get_overlay_pnl_snapshots(
            STRATEGY_OVERLAY, overlay_type, start_date=snap_date, end_date=snap_date
        )
        if rows:
            overlay_1d[overlay_type] = rows[0].pnl_1d_abs
            overlay_inception[overlay_type] = rows[0].pnl_inception_abs
        else:
            logger.warning(
                "protection_recovery.overlay_source_missing",
                strategy=STRATEGY_OVERLAY,
                overlay_type=overlay_type,
                date=str(snap_date),
            )

    best_overlay, best_recovery_pct = _best_recovery(niftybees.pnl_1d_abs, overlay_1d)
    best_overlay_inception, best_recovery_pct_inception = _best_recovery(
        niftybees.pnl_inception_abs, overlay_inception
    )

    return ProtectionRecoverySnapshot(
        snapshot_date=snap_date,
        niftybees_pnl_1d=niftybees.pnl_1d_abs,
        cc_pnl_1d=overlay_1d["cc"],
        pp_pnl_1d=overlay_1d["pp"],
        collar_pnl_1d=overlay_1d["collar"],
        niftybees_pnl_inception=niftybees.pnl_inception_abs,
        cc_pnl_inception=overlay_inception["cc"],
        pp_pnl_inception=overlay_inception["pp"],
        collar_pnl_inception=overlay_inception["collar"],
        best_overlay=best_overlay,
        best_recovery_pct=best_recovery_pct,
        best_overlay_inception=best_overlay_inception,
        best_recovery_pct_inception=best_recovery_pct_inception,
    )


_RECOVERY_OVERLAY_LABELS = {"cc": "CC", "pp": "PP", "collar": "Collar"}


def _build_recovery_digest(snap: ProtectionRecoverySnapshot) -> str:
    """Build the S9 compact daily Telegram digest text.

    On a red NiftyBees day, overlay lines are sorted by recovery amount
    descending (best first, matching the "Best:" line) and recovery
    percentages/"Best:" are shown. On a flat/green day, recovery framing is
    dropped entirely — lines sorted by raw P&L descending instead, no
    percentages, no "Best:" line (stories.md S9).

    BUG-028 Phase 2: an overlay type with no source data for this date
    (``None``) renders as a "No data" line instead of a false ``+0`` —
    excluded from the amount-based sort (can't be ranked against real
    numbers) and always listed after the real-valued lines.

    Args:
        snap: The computed recovery snapshot for one date.

    Returns:
        Multi-line digest text, ready for ``notifier.send()``.
    """
    overlay_pnls: dict[str, Decimal | None] = {
        "cc": snap.cc_pnl_1d,
        "pp": snap.pp_pnl_1d,
        "collar": snap.collar_pnl_1d,
    }
    known = {k: v for k, v in overlay_pnls.items() if v is not None}
    missing = [k for k, v in overlay_pnls.items() if v is None]

    date_str = snap.snapshot_date.strftime("%d %b")
    lines = [
        escape_markdown(f"📊 NiftyBees vs overlays — {date_str}"),
        escape_markdown(f"NiftyBees: {snap.niftybees_pnl_1d:+.0f}"),
    ]

    is_red = snap.niftybees_pnl_1d < 0
    if is_red:
        ordered = sorted(known.items(), key=lambda kv: kv[1], reverse=True)
        denom = abs(snap.niftybees_pnl_1d)
        for overlay_type, pnl in ordered:
            pct = (pnl / denom) * 100 if denom else Decimal("0")
            label = _RECOVERY_OVERLAY_LABELS[overlay_type]
            lines.append(escape_markdown(f"  {label:<6} {pnl:+.0f} ({pct:.0f}%)"))
        for overlay_type in missing:
            label = _RECOVERY_OVERLAY_LABELS[overlay_type]
            lines.append(escape_markdown(f"  {label:<6} No data"))
        if snap.best_overlay:
            lines.append(
                escape_markdown(
                    f"\nBest: {_RECOVERY_OVERLAY_LABELS[snap.best_overlay]}"
                )
            )
    else:
        ordered = sorted(known.items(), key=lambda kv: kv[1], reverse=True)
        for overlay_type, pnl in ordered:
            label = _RECOVERY_OVERLAY_LABELS[overlay_type]
            lines.append(escape_markdown(f"  {label:<6} {pnl:+.0f}"))
        for overlay_type in missing:
            label = _RECOVERY_OVERLAY_LABELS[overlay_type]
            lines.append(escape_markdown(f"  {label:<6} No data"))

    return "\n".join(lines)


# ── Summary table ─────────────────────────────────────────────────────────────


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
        # BUG-028 (2026-08-10): base-leg-only now — overlay P&L no longer
        # rides along with a track's row. See _overlay_summary_row for the
        # single standalone overlay row appended below, independent of
        # --tracks selection.
        summary_rows.append(
            {
                "track": BASE_LABELS.get(track_name, track_name),
                "base_pnl": pnl.base_pnl,
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

    # BUG-028 (2026-08-10): the overlay book (STRATEGY_OVERLAY) is its own
    # strategy, independent of which tracks were selected via --tracks —
    # always computed once here, not per-track inside the loop above.
    overlay_totals = await _compute_overlay_leg_totals(store, broker, snap_date, notifier)

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

        if overlay_totals:
            _save_overlay_leg_snapshots(store, overlay_totals, snap_date)
            for overlay_snap in _compute_overlay_pnl_snapshots(store, snap_date):
                store.record_overlay_pnl_snapshot(overlay_snap)

        # S9 — NiftyBees vs standalone overlay book recovery comparison +
        # single Telegram digest. Reads S3's STRATEGY_SPOT row (base-leg
        # comparison) and S8's STRATEGY_OVERLAY rows just persisted above
        # (BUG-028 fix — was STRATEGY_SPOT, silently zero for any overlay
        # opened after S2r) — no independent leg-level computation. One
        # notifier.send() call per run, not per overlay.
        recovery_snap = _compute_protection_recovery_snapshot(store, snap_date)
        if recovery_snap is not None:
            store.record_protection_recovery_snapshot(recovery_snap)
            if notifier:
                try:
                    await notifier.send(_build_recovery_digest(recovery_snap))
                # Intentional: notification failure must not crash the snapshot.
                except Exception as exc:
                    logger.warning("protection_recovery.telegram_failed", error=str(exc))

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
        # BUG-028: one standalone overlay row, independent of --tracks
        # selection and of the daily/monthly per-track delta merge above
        # (inception-only for now — 1d/MTD delta parity for this row is not
        # part of Phase 1's correctness fix).
        overlay_row = _overlay_summary_row(overlay_totals)
        if overlay_row is not None:
            display_rows.append(overlay_row)
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
            # Re-calculate leg_deltas for display (base leg only — BUG-028)
            pnl = snapshot.pnl
            leg_deltas = {}
            base_role = _base_leg_role(track_name)
            base_total = pnl.unrealized_pnl + pnl.realized_pnl
            leg_deltas[base_role] = _leg_delta(store, track_name, base_role, base_total, snap_date)

            _print_track_block(track_name, snapshot, leg_deltas, snap_date)

        if overlay_totals:
            W = 88
            print(f"\n  {'─' * (W - 4)}")
            print(f"  {'OVERLAY (STANDALONE)':<40} {STRATEGY_OVERLAY}")
            print(f"  {'─' * (W - 4)}")
            for role, (unrealized, realized, total, _ltp, _net_qty) in sorted(
                overlay_totals.items()
            ):
                label = OVERLAY_LABELS.get(role, role)
                delta = _leg_delta(store, STRATEGY_OVERLAY, role, total, snap_date)
                print(
                    f"  {label:<20} {_fmt(total):>12}"
                    f"   unrealized={_fmt(unrealized)}  realized={_fmt(realized)}"
                    f"{_delta_arrow(delta)}"
                )

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
