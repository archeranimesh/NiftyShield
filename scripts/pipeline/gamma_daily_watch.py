#!/usr/bin/env python3
"""Near-Expiry Gamma Buy Strategy — Daily Watch Script.

This script runs daily to fetch option chains, compute gamma gearing,
manage the watchlist, calibrate percentiles, and send Telegram updates.
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from bisect import bisect_right
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal

import structlog

from src.client.exceptions import DataFetchError
from src.client.upstox_market import UpstoxMarketClient, parse_upstox_option_chain
from src.config import settings
from src.db import connect
from src.gamma.derive import derive_snapshots
from src.gamma.models import GammaChainSnapshot, GammaWatchlistEntry
from src.gamma.store import GammaStore
from src.gamma.watchlist import GEARING_AVG_DAYS, evaluate_watchlist
from src.market_calendar.holidays import is_trading_day
from src.models.options import OptionChain
from src.notifications.markdown import escape_markdown
from src.notifications.telegram import build_notifier
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.pipeline.gamma_daily_watch"
logger = structlog.get_logger(_SCRIPT_NAME)


def resolve_expiries(today: date) -> tuple[date, date]:
    """Resolve the current-week and next-week expiry dates.

    NSE Nifty weekly options expire on Tuesdays (effective April 2026, SEBI
    circular). Current-week expiry is the Tuesday of the current week (or the
    preceding trading day if Tuesday is a holiday). If today is Tuesday and
    the market is open, today is used. If today is Tuesday but it is a
    holiday, or if today is after Tuesday (Wed–Sun), current-week expiry
    shifts to the next week's Tuesday. Next-week expiry is the Tuesday (or
    preceding trading day) after that.

    Args:
        today: The reference date to resolve expiries for.

    Returns:
        A tuple of (current_week_expiry, next_week_expiry).
    """
    # weekday(): 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
    weekday_diff = 1 - today.weekday()  # days to reach Tuesday (may be negative)
    nominal_tuesday = today + timedelta(days=weekday_diff)

    if today.weekday() == 1 and is_trading_day(today):
        # Today is Tuesday and market is open — use today
        current_week_nominal = today
        next_week_nominal = today + timedelta(weeks=1)
    elif today.weekday() < 1:
        # Monday — this week's Tuesday is still ahead
        current_week_nominal = nominal_tuesday
        next_week_nominal = nominal_tuesday + timedelta(weeks=1)
    else:
        # Tuesday (holiday) or Wed–Sun — use next week's Tuesday
        current_week_nominal = nominal_tuesday + timedelta(weeks=1)
        next_week_nominal = nominal_tuesday + timedelta(weeks=2)

    def _adjust_expiry(nom_tue: date) -> date:
        """Roll back to the nearest preceding trading day if Tuesday is a holiday."""
        curr = nom_tue
        while not is_trading_day(curr):
            curr -= timedelta(days=1)
        return curr

    current_week_expiry = _adjust_expiry(current_week_nominal)
    next_week_expiry = _adjust_expiry(next_week_nominal)

    return current_week_expiry, next_week_expiry


_NIFTY_INSTRUMENT = "NSE_INDEX|Nifty 50"
_HISTORY_DAYS = GEARING_AVG_DAYS
_MIN_HISTORY_DAYS = 20
_GEARING_WINDOW_DAYS = 60
_NOTIFY_TIMEOUT_S = 15.0
_PCTILE_QUANT = Decimal("0.0001")


def _fetch_chain(client: UpstoxMarketClient, expiry_date: date) -> OptionChain | None:
    """Fetch and parse the Nifty option chain for one expiry.

    Args:
        client: Upstox market-data client.
        expiry_date: Expiry to fetch.

    Returns:
        The parsed chain, or None (with a WARNING) when the response is empty,
        e.g. market closed.
    """
    chain = parse_upstox_option_chain(
        client.get_option_chain_sync(_NIFTY_INSTRUMENT, expiry_date.isoformat())
    )
    if not chain.strikes:
        logger.warning("gamma_daily_watch.empty_chain", expiry=str(expiry_date))
        return None
    return chain


def _fetch_and_snapshot(
    client: UpstoxMarketClient,
    expiries: tuple[date, date],
    today: date,
    snapshot_time: str,
    store: GammaStore,
    conn: sqlite3.Connection | None,
    dry_run: bool,
) -> list[GammaChainSnapshot]:
    """Fetch each expiry's chain, derive snapshot rows and persist them.

    Prior-day OI is read once per expiry. A ``DataFetchError`` on one expiry is
    logged and skipped; store errors propagate so ``connect()`` rolls back. With
    ``dry_run`` no store method is called, so ``oi_change_1d`` is None for every
    row and nothing is written.
    """
    snaps: list[GammaChainSnapshot] = []
    for expiry in expiries:
        try:
            chain = _fetch_chain(client, expiry)
        except DataFetchError as exc:
            logger.error("gamma_daily_watch.fetch_failed", expiry=str(expiry), error=str(exc))
            continue
        if chain is None:
            continue
        prior_oi = {} if dry_run or conn is None else store.get_prior_oi(conn, expiry, today)
        rows = derive_snapshots(chain, expiry, today, snapshot_time, prior_oi)
        if dry_run or conn is None:
            logger.info("gamma_daily_watch.dry_run_skip", expiry=str(expiry), rows=len(rows))
        else:
            for snap in rows:
                store.insert_chain_snapshot(conn, snap)
            logger.info("gamma_daily_watch.snapshots_written", expiry=str(expiry), rows=len(rows))
        snaps.extend(rows)
    return snaps


@contextmanager
def _runtime(dry_run: bool) -> Iterator[tuple[UpstoxMarketClient, GammaStore, sqlite3.Connection]]:
    """Yield the client, store and an open connection (tables ensured unless dry-run)."""
    store = GammaStore()
    with connect(settings.db_path) as conn:
        if not dry_run:
            store.create_tables(conn)
        yield UpstoxMarketClient(), store, conn


def _load_watchlist_inputs(
    store: GammaStore, conn: sqlite3.Connection | None, expiry: date, today: date, dry_run: bool
) -> tuple[list[GammaChainSnapshot], list[GammaWatchlistEntry]]:
    """Read prior snapshots and active entries; empty when the tables are absent.

    A dry run never creates tables, so a missing table is treated as empty
    history instead of an error.
    """
    if conn is None:
        return [], []
    try:
        history = store.get_prior_snapshots(conn, expiry, today, _HISTORY_DAYS)
        return history, store.get_all_active_watchlist(conn)
    except sqlite3.OperationalError:
        if not dry_run:
            raise
        logger.warning("gamma_daily_watch.dry_run_no_tables")
        return [], []


def _update_watchlist(
    today_snaps: list[GammaChainSnapshot],
    current_week_expiry: date,
    today: date,
    store: GammaStore,
    conn: sqlite3.Connection | None,
    dry_run: bool,
) -> dict[str, int]:
    """Re-evaluate the watchlist (§5b) and apply the decision through the store.

    Only current-week-expiry snapshots are evaluated (D4); the ``expired`` rule
    still covers every active entry. ``dry_run`` reads but never writes.

    Returns:
        Counts: ``{"added", "retained", "removed", "elevated"}``.
    """
    week_snaps = [s for s in today_snaps if s.expiry_date == current_week_expiry]
    history, active = _load_watchlist_inputs(store, conn, current_week_expiry, today, dry_run)
    decision = evaluate_watchlist(week_snaps, history, active, today)
    stats = {
        "added": len(decision.add),
        "retained": len(decision.retain),
        "removed": len(decision.remove),
        "elevated": len(decision.elevate),
    }
    if dry_run or conn is None:
        logger.info("gamma_daily_watch.watchlist_dry_run", **stats)
        return stats
    for entry in (*decision.add, *decision.retain):
        store.upsert_watchlist(conn, entry)
    for r in decision.remove:
        store.remove_from_watchlist(
            conn, r.expiry_date, r.strike, r.option_type, r.removal_reason, today
        )
    logger.info("gamma_daily_watch.watchlist_updated", **stats)
    return stats


def _percentile(value: Decimal, history: list[Decimal]) -> Decimal:
    """Fraction of ``history`` values that are <= ``value``, to 4 dp (§5c).

    ``history`` must be non-empty and must exclude the value's own day.
    """
    rank = bisect_right(sorted(history), value)
    return (Decimal(rank) / Decimal(len(history))).quantize(_PCTILE_QUANT)


def _calibrate_snap(
    snap: GammaChainSnapshot,
    store: GammaStore,
    conn: sqlite3.Connection,
    today: date,
    iv_cache: dict[tuple[int, str], list[Decimal]],
    gearing_cache: dict[int, list[Decimal] | None],
) -> tuple[Decimal | None, Decimal | None]:
    """Compute (IV percentile, DTE-bucket gearing percentile) for one snapshot.

    Each is None when its prior history is under 20 distinct snapshot days
    (decision D5) or the snapshot's own value is missing.
    """
    iv_pct = None
    if snap.iv_val is not None:
        key = (snap.strike, snap.option_type)
        if key not in iv_cache:
            iv_cache[key] = store.get_iv_history(
                conn, snap.strike, snap.option_type, limit_days=_MIN_HISTORY_DAYS, before=today
            )
        hist = iv_cache[key]
        if len(hist) < _MIN_HISTORY_DAYS:
            logger.warning(
                "gamma_daily_watch.insufficient_iv_history",
                strike=snap.strike,
                opt=snap.option_type,
                days=len(hist),
            )
        else:
            iv_pct = _percentile(snap.iv_val, hist)
    gearing_pct = None
    if snap.gamma_gearing is not None:
        dte = snap.dte_calendar
        if dte not in gearing_cache:
            days = store.count_prior_gearing_days(conn, dte, today)
            if days < _MIN_HISTORY_DAYS:
                logger.warning("gamma_daily_watch.insufficient_gearing_history", dte=dte, days=days)
                gearing_cache[dte] = None
            else:
                gearing_cache[dte] = store.get_gearing_by_dte(
                    conn, dte, limit_days=_GEARING_WINDOW_DAYS, before=today
                )
        bucket = gearing_cache[dte]
        if bucket:
            gearing_pct = _percentile(snap.gamma_gearing, bucket)
    return iv_pct, gearing_pct


def _run_calibration(
    today_snaps: list[GammaChainSnapshot],
    today: date,
    store: GammaStore,
    conn: sqlite3.Connection | None,
    dry_run: bool,
) -> None:
    """Rank today's IV and DTE-bucket gearing against prior days (§5c) and store them.

    Gated on 20 distinct prior snapshot days, never rows (D5); today is never in
    the history it is ranked against. ``dry_run`` reads history but writes
    nothing (D9); a missing table is tolerated in dry-run only.

    Args:
        today_snaps: Snapshot rows captured this run.
        today: Reference date; history is strictly before it.
        store: Gamma store.
        conn: Open connection (None skips calibration).
        dry_run: Compute and log only.
    """
    if conn is None:
        return
    iv_cache: dict[tuple[int, str], list[Decimal]] = {}
    gearing_cache: dict[int, list[Decimal] | None] = {}
    written = 0
    try:
        for snap in today_snaps:
            iv_pct, gearing_pct = _calibrate_snap(snap, store, conn, today, iv_cache, gearing_cache)
            if iv_pct is None and gearing_pct is None:
                continue
            if dry_run:
                written += 1
                continue
            store.update_percentiles(
                conn,
                snapshot_date=snap.snapshot_date,
                snapshot_time=snap.snapshot_time,
                expiry_date=snap.expiry_date,
                strike=snap.strike,
                option_type=snap.option_type,
                iv_pctile=iv_pct,
                gearing_pctile=gearing_pct,
            )
            written += 1
    except sqlite3.OperationalError:
        if not dry_run:
            raise
        logger.warning("gamma_daily_watch.dry_run_no_tables")
        return
    logger.info("gamma_daily_watch.calibrated", rows=written, dry_run=dry_run)


def _send_summary(captured: int, stats: dict[str, int]) -> None:
    """Push the run summary to Telegram; never fatal (D7).

    Skipped silently when no notifier is configured. The send runs under an
    explicit timeout; any failure is logged as a WARNING.
    """
    notifier = build_notifier()
    if notifier is None:
        return
    text = escape_markdown(
        f"Gamma watch: {captured} strikes captured, "
        f"{stats['added'] + stats['retained']} on watchlist, {stats['elevated']} elevated, "
        f"{stats['added']} added, {stats['removed']} removed"
    )
    try:
        asyncio.run(asyncio.wait_for(notifier.send(text), timeout=_NOTIFY_TIMEOUT_S))
    except Exception as exc:  # noqa: BLE001
        logger.warning("gamma_daily_watch.notify_failed", error=str(exc))


def main() -> None:
    """Main execution entry point."""
    pass

    parser = argparse.ArgumentParser(description="Near-Expiry Gamma Buy Strategy Daily Watch")
    parser.add_argument(
        "--morning",
        action="store_true",
        help="Skip watchlist update (morning run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip database updates and notifications",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Override reference date (YYYY-MM-DD)",
    )

    args = parser.parse_args()

    if args.date:
        try:
            today = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            logger.error("Invalid date format: %s. Use YYYY-MM-DD.", args.date)
            sys.exit(1)
    else:
        today = date.today()

    logger.info("Running daily watch for date: %s", today)

    current_week_expiry, next_week_expiry = resolve_expiries(today)
    logger.info("Resolved current-week expiry: %s", current_week_expiry)
    logger.info("Resolved next-week expiry: %s", next_week_expiry)

    snapshot_time = datetime.now().strftime("%H:%M")

    with _runtime(args.dry_run) as (client, store, conn):
        snaps = _fetch_and_snapshot(
            client=client,
            expiries=(current_week_expiry, next_week_expiry),
            today=today,
            snapshot_time=snapshot_time,
            store=store,
            conn=conn,
            dry_run=args.dry_run,
        )

        if not args.morning:
            stats = _update_watchlist(
                today_snaps=snaps,
                current_week_expiry=current_week_expiry,
                today=today,
                store=store,
                conn=conn,
                dry_run=args.dry_run,
            )
            _run_calibration(snaps, today, store, conn, args.dry_run)
            if not args.dry_run:
                _send_summary(len(snaps), stats)


if __name__ == "__main__":
    setup_logging()
    main()
