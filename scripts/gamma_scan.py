#!/usr/bin/env python3
"""Near-Expiry Gamma Buy Strategy - Phase B intraday signal scan (GS-5).

Every 5 minutes on DTE 0-1: fetch the chain, evaluate every strike against the
four-layer signal stack, log one ``gamma_signal_log`` row per evaluated strike,
open at most one paper trade per direction, and drive E1/E2/E3 exits.
Paper trades only; this script never places a live order.

All collaborators are injected through ``ScanDeps``; ``main()`` is the only
place that builds real ones (and applies the ``GAMMA_*`` env overrides).
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import os
import sqlite3
import sys
import time as time_mod
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import structlog
from dotenv import load_dotenv

from scripts.pipeline.gamma_daily_watch import resolve_expiries
from src.client.chain_source import ChainSource
from src.client.exceptions import DataFetchError
from src.config import settings
from src.db import connect
from src.gamma.depth import DepthSnapshot, DepthSource, NullDepth
from src.gamma.derive import derive_snapshots
from src.gamma.exits import ExitConfig, ExitPosition, ExitTick, evaluate_exit
from src.gamma.features import PriorScan, ScanFeatures, derive_features
from src.gamma.models import GammaChainSnapshot, GammaSignalLogEntry
from src.gamma.ranking import rank_candidates
from src.gamma.signals import Candidate, SignalConfig, SignalStack, StackResult
from src.gamma.store import GammaStore
from src.instruments.lot_size import DateAwareLotSizeResolver
from src.market_calendar.holidays import is_trading_day
from src.notifications.markdown import escape_markdown
from src.paper.models import PaperTrade
from src.utils.logging import setup_logging

# Cron exports no UPSTOX_ENV, and config treats unset as "test" (ignores .env).
load_dotenv()

_SCRIPT_NAME = "scripts.gamma_scan"
logger = structlog.get_logger(_SCRIPT_NAME)

IST = ZoneInfo("Asia/Kolkata")
STRATEGY = "paper_negamma_v1"
LEG_ROLE = {"CE": "gamma_call", "PE": "gamma_put"}
NIFTY_UNDERLYING = "NSE_INDEX|Nifty 50"
VIX_KEY = "NSE_INDEX|India VIX"
SCAN_START = time(9, 25)
LAST_ENTRY = time(14, 30)
SCAN_END = time(15, 0)
SESSION_CLOSE = time(15, 30)
MIN_LEDGER_PRICE = Decimal("0.05")  # NSE tick; ledger rejects price <= 0 (no-bid exits)
HISTORY_WINDOW = timedelta(minutes=25)
_DEPTH_TIMEOUT_S = 8.0
_NOTIFY_TIMEOUT_S = 15.0
_LOCK_PATH = Path("data/gamma_scan.lock")


# --- Collaborator protocols -----------------------------------------------


class VixSource(Protocol):
    """Live India VIX provider; ``None`` when unavailable."""

    async def india_vix(self) -> Decimal | None: ...


class ContractResolver(Protocol):
    """Maps (expiry, strike, option type) to an Upstox instrument key."""

    def resolve(self, expiry: date, strike: int, option_type: str) -> str | None: ...


class PaperEntryAdapter(Protocol):
    """Paper-ledger writes on the caller's connection (one shared transaction)."""

    def net_qty(self, conn: sqlite3.Connection, leg_role: str) -> int: ...

    def open_long(self, conn: sqlite3.Connection, trade: PaperTrade) -> bool: ...

    def close_long(self, conn: sqlite3.Connection, trade: PaperTrade) -> bool: ...


class Notifier(Protocol):
    async def send(self, text: str) -> Any: ...


@dataclass(frozen=True)
class ScanDeps:
    """Every collaborator of one scan."""

    chain_source: ChainSource
    depth: DepthSource
    store: GammaStore
    stack: SignalStack
    exit_config: ExitConfig
    paper: PaperEntryAdapter
    notifier: Notifier | None
    vix: VixSource
    resolver: ContractResolver
    db_path: Path
    lot_size: int


@dataclass(frozen=True)
class ScanOutcome:
    """What one scan did (for logs and tests)."""

    skipped: str | None = None
    evaluated: int = 0
    triggered: int = 0
    entered: int = 0
    exited: int = 0


@dataclass
class _Evaluated:
    snap: GammaChainSnapshot
    candidate: Candidate
    result: StackResult
    entry: GammaSignalLogEntry
    instrument_key: str | None


# --- Gates and small helpers ----------------------------------------------


def _dte_trading(today: date, expiry: date) -> int:
    days = (expiry - today).days
    return sum(1 for i in range(1, days + 1) if is_trading_day(today + timedelta(days=i)))


def _gate(now_ist: datetime) -> str | None:
    if not is_trading_day(now_ist.date()):
        return "non_trading_day"
    if not SCAN_START <= now_ist.time() <= SCAN_END:
        return "outside_scan_window"
    return None


def _utc(now: datetime) -> datetime:
    return now.astimezone(timezone.utc).replace(microsecond=0)


def _sec_id(instrument_key: str | None) -> str | None:
    return instrument_key.split("|", 1)[1] if instrument_key and "|" in instrument_key else None


# --- Persistence reads (script-local, read-only) --------------------------


def _load_history(
    conn: sqlite3.Connection, expiry: date, since: datetime
) -> dict[tuple[int, str], list[PriorScan]]:
    rows = conn.execute(
        "SELECT strike, option_type, signal_timestamp, nifty_spot, gamma_val, best_ask,"
        " oi_now, distance_pct FROM gamma_signal_log"
        " WHERE expiry_date = ? AND signal_timestamp >= ? ORDER BY signal_timestamp",
        (expiry.isoformat(), since.isoformat()),
    ).fetchall()
    out: dict[tuple[int, str], list[PriorScan]] = {}
    for r in rows:
        scan = PriorScan(
            at=datetime.fromisoformat(r["signal_timestamp"]),
            nifty_spot=Decimal(r["nifty_spot"]),
            gamma_val=Decimal(r["gamma_val"]),
            best_ask=Decimal(r["best_ask"]),
            oi=r["oi_now"],
            distance_pct=Decimal(r["distance_pct"]),
        )
        out.setdefault((int(r["strike"]), r["option_type"]), []).append(scan)
    return out


def _position_track(
    conn: sqlite3.Connection, pos: GammaSignalLogEntry, before: datetime
) -> list[tuple[Decimal | None, int | None]]:
    """(bid, ask_qty) of earlier scans of a held contract, oldest first."""
    since = pos.fill_timestamp or pos.signal_timestamp
    rows = conn.execute(
        "SELECT best_bid, ask_qty_l1 FROM gamma_signal_log WHERE expiry_date = ? AND strike = ?"
        " AND option_type = ? AND signal_timestamp >= ? AND signal_timestamp < ?"
        " ORDER BY signal_timestamp",
        (
            pos.expiry_date.isoformat(),
            pos.strike,
            pos.option_type,
            _utc(since).isoformat(),
            before.isoformat(),
        ),
    ).fetchall()
    return [
        (Decimal(r["best_bid"]) if r["best_bid"] is not None else None, r["ask_qty_l1"])
        for r in rows
    ]


# A None ask qty (reduced mode / depth failure) deliberately breaks the streak: only a
# confirmed zero counts, so E3 is the backstop when depth is down.
def _zero_ask_streak(track: Sequence[tuple[Decimal | None, int | None]]) -> int:
    streak = 0
    for _, ask_qty in reversed(track):
        if ask_qty != 0:
            break
        streak += 1
    return streak


# --- Row construction -----------------------------------------------------


def _build_entry(
    *,
    snap: GammaChainSnapshot,
    cand: Candidate,
    result: StackResult,
    feats: ScanFeatures,
    depth: DepthSnapshot | None,
    now: datetime,
    cfg: SignalConfig,
    elevated: bool,
    dte_trading: int,
) -> GammaSignalLogEntry:
    assert snap.best_ask is not None and snap.gamma_val is not None  # noqa: S101 - filtered upstream
    assert snap.gamma_gearing is not None  # noqa: S101
    now_utc = _utc(now)
    mid = (snap.best_bid + snap.best_ask) / 2 if snap.best_bid is not None else None
    spread_pct = snap.bid_ask_spread / mid if snap.bid_ask_spread is not None and mid else None
    ok = result.passed
    return GammaSignalLogEntry(
        signal_id=str(uuid.uuid4()),
        signal_timestamp=now_utc,
        expiry_date=snap.expiry_date,
        strike=snap.strike,
        option_type=snap.option_type,
        dte_calendar=snap.dte_calendar,
        dte_trading=dte_trading,
        watchlist_hit=cand.watchlist_hit,
        watchlist_elevated=elevated,
        nifty_spot=snap.nifty_spot,
        nifty_futures_price=None,
        futures_basis=None,
        underlying_return_1m=None,
        underlying_return_5m=None,
        underlying_return_15m=feats.underlying_return_15m,
        underlying_rvol_15m=feats.underlying_rvol_15m,
        distance_pct=snap.distance_pct if snap.distance_pct is not None else Decimal(0),
        distance_sigma=feats.distance_sigma,
        best_bid=snap.best_bid,
        best_ask=snap.best_ask,
        bid_ask_spread=snap.bid_ask_spread,
        spread_pct_of_mid=spread_pct,
        bid_qty_l1=None if depth is None else depth.bid_qty_l1,
        ask_qty_l1=None if depth is None else depth.ask_qty_l1,
        total_bid_qty=None if depth is None else depth.total_bid_qty,
        total_ask_qty=None if depth is None else depth.total_ask_qty,
        delta_val=snap.delta_val,
        gamma_val=snap.gamma_val,
        vega_val=snap.vega_val,
        theta_val=snap.theta_val,
        iv_val=snap.iv_val,
        gamma_gearing=snap.gamma_gearing,
        speed_5m=feats.speed_5m,
        speed_5m_unavailable=feats.speed_5m is None,
        theoretical_price=cand.theoretical_price,
        model_edge=None,
        strike_iv_pctile_20d=snap.strike_iv_pctile_20d,
        gearing_threshold_used=cfg.gearing_threshold,
        volume_5m=None,
        volume_zscore_5m=cand.volume_zscore_5m,
        oi_now=snap.oi,
        oi_velocity_15m=feats.oi_velocity_15m,
        option_price_rising=feats.option_price_rising,
        india_vix=cand.india_vix,
        india_vix_pctile_252d=None,
        event_flag=False,
        event_type=None,
        f0_hard_pass=result.f0,
        f0_fail_reason=result.reason.value if result.failed_layer == 0 and result.reason else None,
        f1_directional_pass=result.f1,
        f2_convexity_pass=result.f2,
        f3_quality_pass=result.f3,
        f3_quality_method=result.quality_method if result.f3 is not None else None,
        f4_flow_pass=result.f4,
        signal_triggered=ok,
        paper_trade_attempted=False,
        paper_trade_filled=False,
        entry_fill_price=None,
        fill_timestamp=None,
        unfilled_reason=None if ok else (result.reason.value if result.reason else None),
        exit_price=None,
        exit_timestamp=None,
        exit_reason=None,
        mfe=None,
        mae=None,
        realised_r_multiple=None,
        created_at=datetime.now(timezone.utc),
    )


# --- Evaluation -----------------------------------------------------------


async def _fetch_depth(depth: DepthSource, instrument_key: str | None) -> DepthSnapshot | None:
    sec_id = _sec_id(instrument_key)
    if sec_id is None:
        return None
    try:
        return await asyncio.wait_for(depth.fetch(sec_id), timeout=_DEPTH_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - depth failure degrades to reduced mode
        logger.warning("gamma_scan.depth_failed", security_id=sec_id, error=str(exc))
        return None


def _needs_depth(snap: GammaChainSnapshot, cfg: SignalConfig, held: bool) -> bool:
    """Depth only matters past the premium gate (which precedes ask-qty) or if held."""
    in_band = snap.best_ask is not None and cfg.min_premium <= snap.best_ask <= cfg.max_premium
    return held or in_band


async def _evaluate_all(
    deps: ScanDeps,
    conn: sqlite3.Connection,
    snaps: list[GammaChainSnapshot],
    *,
    now: datetime,
    vix: Decimal | None,
    fetched_mono: float,
    held: set[tuple[int, str]],
) -> list[_Evaluated]:
    cfg = deps.stack.config
    expiry = snaps[0].expiry_date
    history = _load_history(conn, expiry, _utc(now) - HISTORY_WINDOW)
    watch = {(w.strike, w.option_type): w for w in deps.store.get_active_watchlist(conn, expiry)}
    close_at = datetime.combine(now.date(), SESSION_CLOSE, tzinfo=IST)
    dte_trading = _dte_trading(now.date(), expiry)
    out: list[_Evaluated] = []
    skipped = 0
    for snap in snaps:
        if snap.gamma_val is None or snap.gamma_gearing is None or not snap.best_ask:
            skipped += 1
            continue
        key = (snap.strike, snap.option_type)
        key_str = deps.resolver.resolve(snap.expiry_date, snap.strike, snap.option_type)
        depth = (
            await _fetch_depth(deps.depth, key_str)
            if _needs_depth(snap, cfg, key in held)
            else None
        )
        feats = derive_features(
            now=_utc(now),
            option_type=snap.option_type,
            spot=snap.nifty_spot,
            gamma=snap.gamma_val,
            ask=snap.best_ask,
            oi=snap.oi,
            distance_pct=snap.distance_pct or Decimal(0),
            history=history.get(key, []),
            close_at=close_at,
        )
        cand = Candidate(
            option_type=snap.option_type,
            dte=snap.dte_calendar,
            ask=snap.best_ask,
            bid=snap.best_bid,
            spread=snap.bid_ask_spread,
            ask_qty_l1=None if depth is None else depth.ask_qty_l1,
            india_vix=vix,
            # Upstox chain/LTP carry no per-contract trade time here: age is time since fetch.
            quote_age_seconds=int(time_mod.monotonic() - fetched_mono),
            oi=snap.oi,
            underlying_return_15m=feats.underlying_return_15m,
            distance_pct=snap.distance_pct or Decimal(0),
            distance_pct_15m_ago=feats.distance_pct_15m_ago,
            distance_sigma=feats.distance_sigma,
            gamma_gearing=snap.gamma_gearing,
            speed_5m=feats.speed_5m,
            theoretical_price=None,  # no Black '76 module in the codebase; Layer 3 uses B
            strike_iv_pctile_20d=snap.strike_iv_pctile_20d,
            volume_zscore_5m=None,  # day volume is not persisted per scan; Layer 4 fails closed
            oi_velocity_15m=feats.oi_velocity_15m,
            option_price_rising=feats.option_price_rising,
            watchlist_hit=key in watch,
        )
        result = deps.stack.evaluate(cand)
        w = watch.get(key)
        entry = _build_entry(
            snap=snap,
            cand=cand,
            result=result,
            feats=feats,
            depth=depth,
            now=now,
            cfg=cfg,
            elevated=bool(w and w.elevated),
            dte_trading=dte_trading,
        )
        out.append(_Evaluated(snap, cand, result, entry, key_str))
    if skipped:
        logger.warning("gamma_scan.strikes_skipped_no_gearing", count=skipped)
    return out


# --- Entry ----------------------------------------------------------------


def _select_entries(evals: list[_Evaluated]) -> dict[str, _Evaluated]:
    """Top-ranked passing candidate per direction (stable input order)."""
    passed = sorted(
        (e for e in evals if e.result.passed), key=lambda e: (e.snap.option_type, e.snap.strike)
    )
    by_id = {id(e.candidate): e for e in passed}
    chosen: dict[str, _Evaluated] = {}
    for c in rank_candidates([e.candidate for e in passed]):
        chosen.setdefault(c.option_type, by_id[id(c)])
    return chosen


def _atomic_entry(deps: ScanDeps, conn: sqlite3.Connection, ev: _Evaluated, now: datetime) -> bool:
    """Check no open position and record the entry in ONE write transaction.

    ``BEGIN IMMEDIATE`` takes the DB write lock before the check, so a second
    process cannot pass the check until this one commits. Returns True if filled.
    """
    entry = ev.entry
    leg = LEG_ROLE[entry.option_type]
    conn.commit()  # no transaction may be open before BEGIN IMMEDIATE
    conn.execute("BEGIN IMMEDIATE")
    try:
        if deps.store.get_open_signal_positions(conn, entry.option_type) or deps.paper.net_qty(
            conn, leg
        ):
            final = replace(entry, unfilled_reason="open_position_same_direction")
            filled = False
        else:
            trade = PaperTrade(
                strategy_name=STRATEGY,
                leg_role=leg,
                instrument_key=ev.instrument_key or "",
                trade_date=now.date(),
                action="BUY",  # type: ignore[arg-type]  # pydantic coerces the enum value
                quantity=deps.lot_size,
                price=entry.best_ask,
                notes=f"gamma_scan signal {entry.signal_id}",
            )
            filled = deps.paper.open_long(conn, trade)
            final = replace(
                entry,
                paper_trade_attempted=True,
                paper_trade_filled=filled,
                entry_fill_price=entry.best_ask if filled else None,
                fill_timestamp=_utc(now) if filled else None,
                unfilled_reason=None if filled else "duplicate_trade",
            )
        deps.store.insert_signal_log(conn, final)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return filled


def _record_rows(
    deps: ScanDeps, conn: sqlite3.Connection, evals: list[_Evaluated], skip_ids: set[str]
) -> None:
    for ev in evals:
        if ev.entry.signal_id not in skip_ids:
            deps.store.insert_signal_log(conn, ev.entry)
    conn.commit()


def _log_entry_error(deps: ScanDeps, conn: sqlite3.Connection, ev: _Evaluated) -> None:
    """Best-effort audit row for a failed entry; a second failure is only logged."""
    try:
        failed = replace(ev.entry, paper_trade_attempted=True, unfilled_reason="entry_error")
        deps.store.insert_signal_log(conn, failed)
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - audit row is best-effort
        conn.rollback()
        logger.error("gamma_scan.entry_error_row_failed", error=str(exc))


async def _run_entries(
    deps: ScanDeps,
    conn: sqlite3.Connection,
    evals: list[_Evaluated],
    now: datetime,
    dry_run: bool,
    messages: list[str],
) -> int:
    chosen = _select_entries(evals)
    chosen_ids = {e.entry.signal_id for e in chosen.values()}
    for ev in evals:
        if ev.entry.signal_triggered and ev.entry.signal_id not in chosen_ids:
            ev.entry = replace(ev.entry, unfilled_reason="not_top_ranked")
    if dry_run or now.time() > LAST_ENTRY:
        why = "dry_run" if dry_run else "entry_window_closed"
        for ev in chosen.values():
            ev.entry = replace(ev.entry, unfilled_reason=why)
            logger.info("gamma_scan.signal_not_entered", reason=why, strike=ev.snap.strike)
        _record_rows(deps, conn, evals, set())
        return 0
    _record_rows(deps, conn, evals, chosen_ids)
    entered = 0
    for ev in chosen.values():
        try:
            filled = _atomic_entry(deps, conn, ev, now)
        except Exception as exc:  # noqa: BLE001 - isolate one entry failure from the scan
            logger.error("gamma_scan.entry_failed", strike=ev.snap.strike, error=str(exc))
            _log_entry_error(deps, conn, ev)
            continue
        if filled:
            entered += 1
            messages.append(
                f"Gamma paper trade opened: {ev.snap.option_type} {ev.snap.strike} "
                f"@ {ev.entry.best_ask}"
            )
    return entered


# --- Exits ----------------------------------------------------------------


def _excursions(
    entry_ask: Decimal, bids: Sequence[Decimal]
) -> tuple[Decimal | None, Decimal | None]:
    if not bids:
        return None, None
    return max(bids) - entry_ask, entry_ask - min(bids)


def _atomic_exit(
    deps: ScanDeps,
    conn: sqlite3.Connection,
    pos: GammaSignalLogEntry,
    instrument_key: str,
    decision_price: Decimal | None,
    reason: str,
    realised_r: Decimal | None,
    excursions: tuple[Decimal | None, Decimal | None],
    now: datetime,
) -> bool:
    """Ledger SELL + signal-log exit update in one transaction."""
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        trade = PaperTrade(
            strategy_name=STRATEGY,
            leg_role=LEG_ROLE[pos.option_type],
            instrument_key=instrument_key,
            trade_date=now.date(),
            action="SELL",  # type: ignore[arg-type]  # pydantic coerces the enum value
            quantity=deps.lot_size,
            price=decision_price if decision_price and decision_price > 0 else MIN_LEDGER_PRICE,
            notes=f"gamma_scan exit {reason} signal {pos.signal_id}",
        )
        deps.paper.close_long(conn, trade)
        done = deps.store.update_signal_exit(
            conn,
            pos.signal_id,
            exit_price=decision_price,
            exit_timestamp=_utc(now),
            exit_reason=reason,
            mfe=excursions[0],
            mae=excursions[1],
            realised_r_multiple=realised_r,
        )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return done


async def _run_exits(
    deps: ScanDeps,
    conn: sqlite3.Connection,
    positions: list[GammaSignalLogEntry],
    evals: list[_Evaluated],
    now: datetime,
    dry_run: bool,
    messages: list[str],
) -> int:
    by_key = {(e.snap.expiry_date, e.snap.strike, e.snap.option_type): e for e in evals}
    now_utc = _utc(now)
    exited = 0
    for pos in positions:
        ev = by_key.get((pos.expiry_date, pos.strike, pos.option_type))
        if ev is None:
            logger.warning("gamma_scan.open_position_unmarked", signal_id=pos.signal_id)
            continue
        track = _position_track(conn, pos, now_utc)
        entry_ask = pos.entry_fill_price or pos.best_ask
        bid = ev.snap.best_bid if ev.snap.best_bid and ev.snap.best_bid > 0 else None
        tick = ExitTick(
            at=now.time(), dte=ev.snap.dte_calendar, bid=bid, ask_qty=ev.entry.ask_qty_l1
        )
        held = ExitPosition(entry_ask=entry_ask, prior_zero_ask_scans=_zero_ask_streak(track))
        decision = evaluate_exit(held, tick, deps.exit_config)
        if decision is None:
            continue
        logger.info("gamma_scan.exit_fired", reason=decision.reason.value, signal_id=pos.signal_id)
        if ev.instrument_key is None and not dry_run:
            logger.warning("gamma_scan.exit_unresolved_key", signal_id=pos.signal_id)
        if dry_run or ev.instrument_key is None:
            continue
        bids = [b for b, _ in track if b is not None and b > 0] + ([bid] if bid else [])
        try:
            _atomic_exit(
                deps,
                conn,
                pos,
                ev.instrument_key,
                decision.exit_price,
                decision.reason.value,
                decision.realised_r,
                _excursions(entry_ask, bids),
                now,
            )
        except Exception as exc:  # noqa: BLE001 - one failed exit must not hide the others
            logger.error("gamma_scan.exit_failed", signal_id=pos.signal_id, error=str(exc))
            continue
        exited += 1
        messages.append(
            f"Gamma exit {decision.reason.value}: {pos.option_type} {pos.strike} @ {decision.exit_price}"
        )
    return exited


# --- Notification ---------------------------------------------------------


async def _notify(notifier: Notifier | None, messages: list[str]) -> None:
    """Send each message; never fatal."""
    if notifier is None:
        return
    for text in messages:
        try:
            await asyncio.wait_for(notifier.send(escape_markdown(text)), timeout=_NOTIFY_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 - Telegram is non-fatal
            logger.warning("gamma_scan.notify_failed", error=str(exc))


# --- Scan -----------------------------------------------------------------


async def run_scan(deps: ScanDeps, now: datetime, dry_run: bool = False) -> ScanOutcome:
    """Run one 5-minute scan.

    Args:
        deps: Injected collaborators.
        now: Scan time, timezone-aware (converted to IST for the gates).
        dry_run: Evaluate and log rows, but never trade, exit or notify.

    Returns:
        What the scan did.
    """
    now = now.astimezone(IST)
    skip = _gate(now)
    if skip:
        logger.info("gamma_scan.skip", reason=skip)
        return ScanOutcome(skipped=skip)
    expiry = resolve_expiries(now.date())[0]
    if (expiry - now.date()).days > 1:
        logger.info("gamma_scan.skip", reason="dte_out_of_range", expiry=str(expiry))
        return ScanOutcome(skipped="dte_out_of_range")
    try:
        chain = await deps.chain_source.get_chain(NIFTY_UNDERLYING, expiry.isoformat())
    except DataFetchError as exc:
        logger.error("gamma_scan.chain_fetch_failed", error=str(exc))
        return ScanOutcome(skipped="chain_fetch_failed")
    fetched_mono = time_mod.monotonic()
    if not chain.strikes:
        logger.warning("gamma_scan.empty_chain", expiry=str(expiry))
        return ScanOutcome(skipped="empty_chain")
    vix = await _live_vix(deps.vix)
    messages: list[str] = []
    with connect(deps.db_path) as conn:
        deps.store.create_tables(conn)
        prior_oi = deps.store.get_prior_oi(conn, expiry, now.date())
        snaps = derive_snapshots(chain, expiry, now.date(), now.strftime("%H:%M"), prior_oi)
        if not snaps:
            return ScanOutcome(skipped="no_snapshots")
        positions = deps.store.get_open_signal_positions(conn)
        held: set[tuple[int, str]] = {
            (p.strike, p.option_type) for p in positions if p.expiry_date == expiry
        }
        evals = await _evaluate_all(
            deps, conn, snaps, now=now, vix=vix, fetched_mono=fetched_mono, held=held
        )
        entered = await _run_entries(deps, conn, evals, now, dry_run, messages)
        exited = await _run_exits(deps, conn, positions, evals, now, dry_run, messages)
    triggered = sum(1 for e in evals if e.result.passed)
    if triggered and not dry_run:
        messages.insert(0, f"Gamma signal fired: {triggered} qualifying strike(s)")
    if not dry_run:
        await _notify(deps.notifier, messages)
    logger.info(
        "gamma_scan.done",
        evaluated=len(evals),
        triggered=triggered,
        entered=entered,
        exited=exited,
        dry_run=dry_run,
    )
    return ScanOutcome(None, len(evals), triggered, entered, exited)


async def _live_vix(source: VixSource) -> Decimal | None:
    try:
        vix = await asyncio.wait_for(source.india_vix(), timeout=_DEPTH_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - missing VIX fails Layer 0 closed
        logger.warning("gamma_scan.vix_unavailable", error=str(exc))
        return None
    return vix if vix is not None and vix > 0 else None


# --- Process lock ---------------------------------------------------------


@contextmanager
def process_lock(path: Path) -> Iterator[bool]:
    """Hold a non-blocking exclusive file lock; yield False if already held."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


# --- Real collaborators ---------------------------------------------------


class UpstoxVixSource:
    """India VIX via the Upstox LTP endpoint (same key as the signals pipeline)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def india_vix(self) -> Decimal | None:
        quotes = await self._client.get_ltp([VIX_KEY])
        return quotes.get(VIX_KEY)


class BodContractResolver:
    """Instrument keys from the offline BOD file, cached per expiry."""

    def __init__(self, lookup: Any) -> None:
        self._lookup = lookup
        self._cache: dict[date, dict[tuple[int, str], str]] = {}

    def resolve(self, expiry: date, strike: int, option_type: str) -> str | None:
        if expiry not in self._cache:
            found = self._lookup.search_options("NIFTY", expiry=expiry, max_results=5000)
            self._cache[expiry] = {
                (int(i["strike_price"]), i["instrument_type"]): i["instrument_key"] for i in found
            }
        return self._cache[expiry].get((strike, option_type))


_INSERT_TRADE = (
    "INSERT INTO paper_trades (strategy_name, leg_role, instrument_key, trade_date, action,"
    " quantity, price, notes, ivr_at_entry, state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    " ON CONFLICT(strategy_name, leg_role, instrument_key, trade_date, action) DO NOTHING"
)


class PaperLedgerAdapter:
    """Writes ``paper_trades`` on the caller's connection.

    ``PaperStore.record_trade`` opens its own connection, which would deadlock
    against the scan's ``BEGIN IMMEDIATE`` transaction, so the identical INSERT
    runs on the shared connection. ``PaperTrade`` still validates every row and
    ``PaperStore(db_path)`` still owns schema creation.
    """

    def __init__(self, db_path: Path) -> None:
        from src.paper.store import PaperStore

        PaperStore(db_path)  # creates the paper tables if missing

    def net_qty(self, conn: sqlite3.Connection, leg_role: str) -> int:
        row = conn.execute(
            "SELECT COALESCE(SUM(CASE action WHEN 'BUY' THEN quantity ELSE -quantity END), 0)"
            " AS net FROM paper_trades WHERE strategy_name = ? AND leg_role = ?",
            (STRATEGY, leg_role),
        ).fetchone()
        return int(row["net"])

    def _insert(self, conn: sqlite3.Connection, t: PaperTrade) -> bool:
        cur = conn.execute(
            _INSERT_TRADE,
            (
                t.strategy_name,
                t.leg_role,
                t.instrument_key,
                t.trade_date.isoformat(),
                t.action.value,
                t.quantity,
                str(t.price),
                t.notes,
                t.ivr_at_entry,
                t.state.value,
            ),
        )
        return cur.rowcount == 1

    def open_long(self, conn: sqlite3.Connection, trade: PaperTrade) -> bool:
        return self._insert(conn, trade)

    def close_long(self, conn: sqlite3.Connection, trade: PaperTrade) -> bool:
        inserted = self._insert(conn, trade)
        if self.net_qty(conn, trade.leg_role) == 0:
            conn.execute(
                "UPDATE paper_trades SET state = 'CLOSED' WHERE strategy_name = ? AND leg_role = ?"
                " AND instrument_key = ? AND state IN ('OPEN', 'DEFENDED')",
                (trade.strategy_name, trade.leg_role, trade.instrument_key),
            )
        return inserted


class _RealClock:
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def time(self) -> float:
        return asyncio.get_running_loop().time()


def build_signal_config(
    lot_size: int, env: dict[str, str] | os._Environ[str] = os.environ
) -> SignalConfig:
    """Build the stack config, applying the GAMMA_* env overrides once (section 12)."""
    overrides = {
        "GAMMA_MIN_GEARING": "gearing_threshold",
        "GAMMA_MIN_PREMIUM": "min_premium",
        "GAMMA_MAX_PREMIUM": "max_premium",
    }
    kw = {field: Decimal(env[var]) for var, field in overrides.items() if env.get(var)}
    return SignalConfig(min_ask_qty=lot_size, **kw)  # type: ignore[arg-type]


async def _main(dry_run: bool) -> int:
    import aiohttp

    from src.client.chain_source import UpstoxChainSource
    from src.client.dhan_depth import DhanDepthAdapter
    from src.client.dhan_market import SpacingRateLimiter
    from src.client.upstox_market import UpstoxMarketClient
    from src.instruments.lookup import InstrumentLookup
    from src.notifications.telegram import build_notifier

    now = datetime.now(IST)
    lot_size = DateAwareLotSizeResolver.resolve("NIFTY", now.date())
    db_path = Path(settings.db_path)
    client = UpstoxMarketClient()
    key = os.environ.get("DHAN_DATA_API_KEY")
    async with aiohttp.ClientSession() as session:
        depth: DepthSource = NullDepth()
        if key and settings.dhan_client_id:
            clock = _RealClock()
            depth = DhanDepthAdapter(
                session,
                SpacingRateLimiter(spacing=1.0, clock=clock),
                clock,
                key,
                settings.dhan_client_id,
            )
        else:
            logger.info("gamma_scan.reduced_mode", reason="DHAN_DATA_API_KEY or client id unset")
        deps = ScanDeps(
            chain_source=UpstoxChainSource(client),
            depth=depth,
            store=GammaStore(),
            stack=SignalStack(build_signal_config(lot_size)),
            exit_config=ExitConfig(),
            paper=PaperLedgerAdapter(db_path),
            notifier=build_notifier(),
            vix=UpstoxVixSource(client),
            resolver=BodContractResolver(
                InstrumentLookup.from_file(Path(settings.bod_instruments_path))
            ),
            db_path=db_path,
            lot_size=lot_size,
        )
        await run_scan(deps, now, dry_run)
    return 0


def main(argv: Sequence[str] | None = None, lock_path: Path = _LOCK_PATH) -> int:
    """CLI entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(description="Near-Expiry Gamma Buy intraday scan (Phase B)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate and log signal rows; never record a paper trade or send Telegram",
    )
    args = parser.parse_args(argv)
    with process_lock(lock_path) as acquired:
        if not acquired:
            logger.info("gamma_scan.lock_held")
            return 0
        return asyncio.run(_main(args.dry_run))


if __name__ == "__main__":
    setup_logging()
    sys.exit(main())
