#!/usr/bin/env python3
"""Canonical daily snapshot for the 3-Track Nifty Long Comparison framework.

Combines base vs protection P&L, per-leg delta-from-yesterday tracking, and
proxy delta monitoring into a single terminal report. Writes both
``paper_nav_snapshots`` (strategy-level) and ``paper_leg_snapshots`` (per-leg)
by default; use ``--no-save`` for a dry-run inspection.

Replaces ``paper_track_snapshot.py`` as the canonical cron snapshot script.
``paper_track_snapshot.py`` is preserved for backward-compatible operator use.

Usage:
    # Live fetch — save snapshots (default):
    python scripts/paper_3track_snapshot.py --date 2026-05-07

    # Dry-run — print report only, no DB writes:
    python scripts/paper_3track_snapshot.py --date 2026-05-07 --no-save

    # Restrict to specific tracks:
    python scripts/paper_3track_snapshot.py --date 2026-05-07 --tracks spot proxy

Cron example (daily at 15:35 IST):
    35 10 * * 1-5  cd /path/to/NiftyShield && python scripts/paper_3track_snapshot.py

Diagnostics:
    LOG_LEVEL=DEBUG python scripts/paper_3track_snapshot.py --date 2026-05-07
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.client.upstox_market import UpstoxMarketClient
from src.instruments.lookup import InstrumentLookup
from src.models.portfolio import TradeAction
from src.notifications.telegram import TelegramNotifier
from src.paper.metrics import compute_nee
from src.paper.models import PaperLegSnapshot, PaperNavSnapshot
from src.paper.proxy_monitor import ProxyDeltaMonitor
from src.paper.store import PaperStore
from src.paper.track_snapshot import TrackPnL, TrackSnapshot, generate_track_snapshot

# ── Constants ─────────────────────────────────────────────────────────────────

LOT_SIZE = 65           # Nifty 50, effective Jan 2026 — verify before each cycle
DEFAULT_DB  = Path("data/portfolio/portfolio.sqlite")
DEFAULT_BOD = Path("data/instruments/NSE.json.gz")

ALL_TRACKS = ["paper_nifty_spot", "paper_nifty_futures", "paper_nifty_proxy"]

_BASE_LABELS: dict[str, str] = {
    "paper_nifty_spot":    "NiftyBees (Spot)",
    "paper_nifty_futures": "Nifty Futures",
    "paper_nifty_proxy":   "Proxy DITM CE",
}

_OVERLAY_LABELS: dict[str, str] = {
    "overlay_pp":           "PP",
    "overlay_cc":           "CC",
    "overlay_collar_put":   "Collar",
    "overlay_collar_call":  "Collar",
}

logger = logging.getLogger(__name__)


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt(value: Decimal) -> str:
    """Signed, comma-separated integer string: +1,234 or -5,678."""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,.0f}"


def _delta_arrow(delta: Decimal | None) -> str:
    """Return a coloured delta-from-yesterday arrow string."""
    if delta is None:
        return "  (no prior)"
    if delta > 0:
        return f"  Δ {_fmt(delta)} ▲"
    if delta < 0:
        return f"  Δ {_fmt(delta)} ▼"
    return "  Δ ±0"


def _hedge_verdict(base: Decimal, overlay_total: Decimal) -> str:
    if base < 0:
        if overlay_total > 0:
            pct = abs(overlay_total) / abs(base) * 100
            net_after = base + overlay_total
            if abs(net_after) < abs(base):
                return f"✅ Protected ({pct:.0f}% absorbed)"
            return f"⚠️  Partial ({pct:.0f}% absorbed)"
        return "❌ No protection"
    # base >= 0
    if overlay_total < 0:
        return "⚠️  Overlay drag on up-move"
    return "✅ No hedge cost today"


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
    label = _BASE_LABELS.get(track_name, track_name)
    pnl = snapshot.pnl

    # Merge collar legs
    grouped_overlay: dict[str, Decimal] = {}
    for role, amount in pnl.overlay_pnls.items():
        display = _OVERLAY_LABELS.get(role, role)
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
            for role, role_pnl in pnl.overlay_pnls.items():
                if _OVERLAY_LABELS.get(role, role) == display:
                    rd = leg_deltas.get(role)
                    if rd is not None:
                        overlay_delta_sum = (overlay_delta_sum or Decimal("0")) + rd
            print(
                f"  {display:<20} {_fmt(amount):>12}"
                f"{_delta_arrow(overlay_delta_sum)}"
            )
        print(f"  {'─' * 38}")
        verdict = _hedge_verdict(pnl.base_pnl, overlay_total)
        print(f"  {'Net':<20} {_fmt(pnl.net_pnl):>12}   {verdict}")
    else:
        print(f"  {'Net':<20} {_fmt(pnl.net_pnl):>12}   (no overlay)")

    # Greeks + metrics
    g = snapshot.greeks
    print(
        f"  Greeks : Δ={g.net_delta:.3f}  Θ={g.net_theta:.2f}  V={g.net_vega:.2f}"
    )
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
        "paper_nifty_spot":    "base_etf",
        "paper_nifty_futures": "base_futures",
        "paper_nifty_proxy":   "base_ditm_call",
    }.get(track_name, "base_etf")


def _overlay_roles_for_track(
    store: PaperStore, track_name: str, snap_date: date
) -> list[str]:
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
            realized_pnl=Decimal("0"),   # realized only after close — updated by roll
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
        label = _BASE_LABELS.get(name, name)
        print(
            f"  {label:<28} {_fmt(pnl.base_pnl):>12} {_fmt(overlay_total):>12}"
            f" {_fmt(pnl.net_pnl):>12} {float(snap.return_on_nee):>8.2f}%"
        )
    print(f"{'═' * W}")


# ── Main async orchestration ──────────────────────────────────────────────────

async def _run(args: argparse.Namespace) -> None:
    snap_date: date = date.fromisoformat(args.date)
    save: bool = not args.no_save

    _TRACK_MAP = {
        "spot":    "paper_nifty_spot",
        "futures": "paper_nifty_futures",
        "proxy":   "paper_nifty_proxy",
    }
    tracks = [_TRACK_MAP[t] for t in args.tracks] if args.tracks else list(ALL_TRACKS)

    store = PaperStore(args.db_path)

    # Broker — graceful fallback for dry-run without token
    try:
        broker = UpstoxMarketClient()
    except ValueError:
        if args.no_save:
            logger.warning("UPSTOX_ANALYTICS_TOKEN not set — using mock broker (--no-save mode).")

            class _MockBroker:
                async def get_ltp(self, keys):
                    return {k: 0.0 for k in keys}
                async def get_option_chain(self, u, e):
                    return []
            broker = _MockBroker()
        else:
            logger.error(
                "UPSTOX_ANALYTICS_TOKEN not set. "
                "Use --no-save for a dry-run without live prices."
            )
            sys.exit(1)

    lookup = InstrumentLookup.from_file(args.bod_path)
    proxy_monitor = ProxyDeltaMonitor(store)

    # Telegram notifier (optional)
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
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
        except Exception as exc:
            logger.error("Live spot fetch failed: %s — pass --spot <price> to override.", exc)
            sys.exit(1)
        if nifty_spot <= 0:
            logger.error(
                "Live spot fetch returned 0. Pass --spot <price> to override."
            )
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

    for track_name in tracks:
        monitor = proxy_monitor if track_name == "paper_nifty_proxy" else None
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

        # Collect LTP map from positions (needed for leg snapshot ltp field)
        trades = store.get_trades(track_name)
        leg_roles = {t.leg_role for t in trades}
        positions = [store.get_position(track_name, r) for r in leg_roles]
        inst_keys = [p.instrument_key for p in positions if p.instrument_key and p.net_qty != 0]
        raw_ltps: dict = {}
        if inst_keys:
            try:
                raw_ltps = await broker.get_ltp(inst_keys)
            except Exception as exc:
                logger.warning("LTP fetch for leg snapshots failed: %s", exc)
        ltp_map: dict[str, Decimal] = {
            k: Decimal(str(v)) for k, v in raw_ltps.items() if v
        }

        # Compute per-leg deltas-from-yesterday for display
        pnl = snapshot.pnl
        leg_deltas: dict[str, Decimal | None] = {}

        base_role = _base_leg_role(track_name)
        base_unrealized = pnl.unrealized_pnl - sum(pnl.overlay_pnls.values())
        base_total = base_unrealized + pnl.realized_pnl
        leg_deltas[base_role] = _leg_delta(store, track_name, base_role, base_total, snap_date)

        for role, role_pnl in pnl.overlay_pnls.items():
            leg_deltas[role] = _leg_delta(store, track_name, role, role_pnl, snap_date)

        _print_track_block(track_name, snapshot, leg_deltas, snap_date)

        # Telegram critical alert
        if snapshot.proxy_delta_alert and "CRITICAL" in snapshot.proxy_delta_alert:
            msg = (
                f"🚨 *CRITICAL* Proxy Delta alert — {track_name}\n"
                f"Delta: {snapshot.greeks.net_delta:.3f}\n"
                f"Date: {snap_date}"
            )
            if notifier:
                try:
                    await notifier.send_message(msg)
                except Exception as exc:
                    logger.warning("Telegram alert failed: %s", exc)

        # Persist if not dry-run
        if save:
            _save_nav_snapshot(store, track_name, snapshot, snap_date, nifty_spot)
            _save_leg_snapshots(store, track_name, snapshot, snap_date, ltp_map)

    _print_summary_table(results, snap_date)
    if save:
        print(f"  ✅  All snapshots written to {args.db_path}\n")
    else:
        print("  ℹ️   --no-save: no records written.\n")


def main() -> None:
    """CLI entry point."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description=(
            "Canonical daily snapshot for the 3-Track Nifty Long Comparison framework.\n"
            "Writes paper_nav_snapshots + paper_leg_snapshots by default.\n"
            "Use --no-save for a dry-run inspection."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--date", required=True, metavar="YYYY-MM-DD",
        help="Snapshot date.",
    )
    parser.add_argument(
        "--spot", type=float, default=None, metavar="PRICE",
        help="Nifty 50 spot price (default: live fetch via UpstoxMarketClient).",
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="Print report only — do not write to DB.",
    )
    parser.add_argument(
        "--tracks", nargs="+", choices=["spot", "futures", "proxy"],
        metavar="TRACK",
        help="Restrict to specific tracks (default: all three).",
    )
    parser.add_argument(
        "--db-path", type=Path, default=DEFAULT_DB,
        help=f"SQLite DB path (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--bod-path", type=Path, default=DEFAULT_BOD,
        help=f"BOD instruments JSON path (default: {DEFAULT_BOD})",
    )
    args = parser.parse_args()

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
