#!/usr/bin/env python3
"""Roll expiring overlay legs across all three tracks.

Detects overlay legs whose DTE ≤ OVERLAY_ROLL_DTE, fetches a replacement
strike with the same algorithm as the entry script, and atomically closes
the old leg + opens the new one. Collar rolls close and reopen both legs
atomically (4-trade operation).

Roll atomicity guarantee:
    - Close trade is written first.
    - If the open write fails for any reason, the close trade is deleted
      via store.delete_trade (Phase B lesson: last_trade tracks SELL direction).
    - Collar: all 4 writes succeed or the entire collar position is restored.

Blocked combinations (inherited from entry script):
    paper_nifty_futures + standalone overlay_cc (synthetic short put risk).

Usage:
    # Dry-run — show what would roll, write nothing:
    python -m scripts.paper_3track_overlay_roll --date 2026-05-07 --dry-run

    # Live run:
    python -m scripts.paper_3track_overlay_roll --date 2026-05-07 --yes

    # Force-roll legs whose DTE > OVERLAY_ROLL_DTE (e.g., manual intervention):
    python -m scripts.paper_3track_overlay_roll --date 2026-05-07 --yes --force

    # Restrict to specific tracks:
    python -m scripts.paper_3track_overlay_roll --date 2026-05-07 --yes --tracks spot proxy

Diagnostics:
    LOG_LEVEL=DEBUG python -m scripts.paper_3track_overlay_roll ...
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.client.upstox_market import UpstoxMarketClient
from src.instruments.lookup import InstrumentLookup, parse_expiry as _pe
from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.paper.store import PaperStore

# Re-use constants and pure helpers from the entry script — single source of truth.
from scripts.paper_3track_overlay import (
    ALL_TRACKS,
    CC_OTM_MAX,
    CC_OTM_MIN,
    CC_TARGET_OTM,
    LOT_SIZE,
    NIFTY_UNDERLYING,
    OVERLAY_ROLL_DTE,
    PP_OTM_MAX,
    PP_OTM_MIN,
    PP_TARGET_OTM,
    _ACTION_FOR_ROLE,
    _CC_BLOCKED_TRACKS,
    _OPTION_TYPE_FOR_ROLE,
    _build_trade,
    _collect_expiry_candidates,
    _fetch_candidates_for_expiries,
    _select_best_candidate,
)

DEFAULT_DB  = Path("data/portfolio/portfolio.sqlite")
DEFAULT_BOD = Path("data/instruments/NSE.json.gz")

logger = logging.getLogger(__name__)

# Regex for parsing expiry from Nifty FO instrument keys.
# Matches: NSE_FO|NIFTY29MAY2026PE   or   NSE_FO|NIFTY29MAY2026CE
_EXPIRY_RE = re.compile(r"NSE_FO\|NIFTY(\d{2}[A-Z]{3}\d{4})(PE|CE)", re.IGNORECASE)

# All overlay leg roles the roll script handles.
_OVERLAY_ROLES: list[str] = [
    "overlay_pp",
    "overlay_cc",
    "overlay_collar_put",
    "overlay_collar_call",
]


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class RollResult:
    """One completed (or dry-run previewed) roll leg."""

    strategy: str
    leg_role: str
    old_instrument_key: str
    old_price: Decimal
    close_price: Decimal
    new_instrument_key: str
    new_price: Decimal
    new_expiry: str
    new_dte: int
    cycle_pnl: Decimal


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _parse_expiry_from_key(instrument_key: str) -> date | None:
    """Parse the option expiry date from a Nifty FO instrument key.

    Args:
        instrument_key: e.g. ``"NSE_FO|NIFTY29MAY2026PE"``.

    Returns:
        Parsed expiry date, or ``None`` if the key is not a Nifty FO option.
    """
    m = _EXPIRY_RE.search(instrument_key)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1).upper(), "%d%b%Y").date()
    except ValueError:
        return None


def _cycle_pnl(existing: PaperTrade, close: PaperTrade) -> Decimal:
    """Compute realised P&L for the closing leg of one overlay cycle.

    For BUY-to-open legs (PP, collar put):  pnl = (close_price - open_price) × qty
    For SELL-to-open legs (CC, collar call): pnl = (open_price - close_price) × qty

    Args:
        existing: The trade that opened the position.
        close:    The trade that closes it (opposite action, same qty).

    Returns:
        Realised cycle P&L as Decimal.
    """
    open_action = _ACTION_FOR_ROLE[existing.leg_role]
    if open_action == TradeAction.BUY:
        return (close.price - existing.price) * existing.quantity
    return (existing.price - close.price) * existing.quantity


def _find_expiring_overlay(
    trades: list[PaperTrade],
    roll_date: date,
    leg_role: str,
    force: bool = False,
) -> list[PaperTrade]:
    """Return [existing_open_trade] if the overlay is open and qualifies for rolling.

    A position qualifies when:
      - net_qty != 0  (position is open)
      - instrument key parses to a valid expiry  (equity legs are skipped)
      - DTE ≤ OVERLAY_ROLL_DTE, or force=True

    Uses the Phase B fix: ``last_trade`` is updated on every iteration (not only on BUY)
    so that open SELL positions (CC, collar call) are correctly detected.

    Args:
        trades:    All trades for (strategy, leg_role).
        roll_date: Date used to compute DTE.
        leg_role:  Used only for logging context.
        force:     If True, bypass the DTE threshold check.

    Returns:
        ``[last_open_trade]`` if eligible, ``[]`` otherwise.
    """
    net = 0
    last_trade: PaperTrade | None = None
    for t in trades:
        if t.action == TradeAction.BUY:
            net += t.quantity
        else:
            net -= t.quantity
        last_trade = t  # track regardless of direction (Phase B lesson)

    if net == 0 or last_trade is None:
        return []

    expiry = _parse_expiry_from_key(last_trade.instrument_key)
    if expiry is None:
        logger.debug("%s: equity leg — skipping roll check", leg_role)
        return []

    dte = (expiry - roll_date).days
    if not force and dte > OVERLAY_ROLL_DTE:
        logger.debug("%s: DTE=%d > %d — not yet due for roll", leg_role, dte, OVERLAY_ROLL_DTE)
        return []

    logger.info("%s: DTE=%d ≤ %d — eligible for roll", leg_role, dte, OVERLAY_ROLL_DTE)
    return [last_trade]


# ── OTM band helpers ──────────────────────────────────────────────────────────

def _otm_band(leg_role: str) -> tuple[float, float, float]:
    """Return (otm_min, otm_max, target_otm) for a given leg role.

    Args:
        leg_role: One of the four overlay leg roles.

    Returns:
        Tuple of (min, max, target) OTM fractions.
    """
    option_type = _OPTION_TYPE_FOR_ROLE[leg_role]
    if option_type == "PE":
        return PP_OTM_MIN, PP_OTM_MAX, PP_TARGET_OTM
    return CC_OTM_MIN, CC_OTM_MAX, CC_TARGET_OTM


# ── Closing leg builder ───────────────────────────────────────────────────────

async def _close_leg(
    broker: UpstoxMarketClient,
    store: PaperStore,
    existing: PaperTrade,
    roll_date: date,
    dry_run: bool,
) -> PaperTrade:
    """Fetch live LTP for the existing overlay and build/write a close trade.

    Args:
        broker:    Upstox market client (for live LTP).
        store:     PaperStore (write target).
        existing:  The trade being closed.
        roll_date: Date to record the close trade against.
        dry_run:   If True, build the trade but do not write it.

    Returns:
        The close trade (PaperTrade).
    """
    # Fetch live LTP for the closing price
    ltp_resp = await broker.get_ltp([existing.instrument_key])
    raw = ltp_resp.get(existing.instrument_key, 0)
    close_price = Decimal(str(round(float(raw), 2)))
    if close_price <= 0:
        logger.warning(
            "LTP fetch returned 0 for %s — using existing open price as close fallback",
            existing.instrument_key,
        )
        close_price = existing.price

    # Close action is the opposite of the opening action
    open_action = _ACTION_FOR_ROLE[existing.leg_role]
    close_action = TradeAction.SELL if open_action == TradeAction.BUY else TradeAction.BUY

    close_trade = PaperTrade(
        strategy_name=existing.strategy_name,
        leg_role=existing.leg_role,
        instrument_key=existing.instrument_key,
        trade_date=roll_date,
        action=close_action,
        quantity=existing.quantity,
        price=close_price,
        notes=f"Roll close: expiring {existing.instrument_key}",
    )

    if not dry_run:
        store.record_trade(close_trade)

    return close_trade


# ── New leg builder ───────────────────────────────────────────────────────────

async def _open_new_leg(
    broker: UpstoxMarketClient,
    store: PaperStore,
    lookup: InstrumentLookup,
    leg_role: str,
    strategy: str,
    roll_date: date,
    dry_run: bool,
) -> PaperTrade:
    """Select and record the replacement overlay leg.

    Uses the same expiry-selection and strike-ranking algorithm as the entry script.

    Args:
        broker:    Upstox market client.
        store:     PaperStore (write target).
        lookup:    Instrument lookup for expiry candidates.
        leg_role:  Leg role for the new position.
        strategy:  Strategy name for the new trade.
        roll_date: Date to record the new trade.
        dry_run:   If True, build the trade but do not write it.

    Returns:
        The newly built PaperTrade.
    """
    option_type = _OPTION_TYPE_FOR_ROLE[leg_role]
    otm_min, otm_max, target_otm = _otm_band(leg_role)

    # Fetch spot price
    ltp_resp = await broker.get_ltp([NIFTY_UNDERLYING])
    raw_spot = ltp_resp.get(NIFTY_UNDERLYING, 0)
    spot = float(raw_spot) if raw_spot else 0.0
    if spot <= 0:
        raise ValueError(f"Could not fetch spot price for {NIFTY_UNDERLYING}")

    expiry_candidates = _collect_expiry_candidates(lookup, roll_date)
    if not expiry_candidates:
        raise ValueError("No valid expiry candidates found in BOD instrument list.")

    gate_passers, all_candidates = await _fetch_candidates_for_expiries(
        broker, expiry_candidates, option_type, spot, otm_min, otm_max
    )

    candidates = gate_passers if gate_passers else all_candidates
    best = _select_best_candidate(candidates, target_otm, option_type)
    best["dte"] = (date.fromisoformat(best["expiry"]) - roll_date).days

    new_trade = _build_trade(strategy, leg_role, best, roll_date, LOT_SIZE)

    if not dry_run:
        store.record_trade(new_trade)

    return new_trade


# ── Atomic roll helpers ───────────────────────────────────────────────────────

async def _roll_single(
    broker: UpstoxMarketClient,
    store: PaperStore,
    lookup: InstrumentLookup,
    existing: PaperTrade,
    roll_date: date,
    dry_run: bool,
) -> RollResult:
    """Roll one overlay leg atomically (close + open).

    If the open write fails after the close has been written, the close trade
    is deleted via store.delete_trade to restore the pre-roll position.

    Args:
        broker:    Upstox market client.
        store:     PaperStore.
        lookup:    BOD instrument lookup.
        existing:  The trade being closed/rolled.
        roll_date: Date for the new trades.
        dry_run:   If True, simulate without writing.

    Returns:
        RollResult describing the completed roll.
    """
    close_trade = await _close_leg(broker, store, existing, roll_date, dry_run)
    try:
        open_trade = await _open_new_leg(
            broker, store, lookup, existing.leg_role, existing.strategy_name, roll_date, dry_run
        )
    except Exception:
        if not dry_run:
            store.delete_trade(close_trade)  # restore pre-roll state
        raise

    expiry_from_key = _parse_expiry_from_key(open_trade.instrument_key)
    new_dte = (expiry_from_key - roll_date).days if expiry_from_key else -1

    return RollResult(
        strategy=existing.strategy_name,
        leg_role=existing.leg_role,
        old_instrument_key=existing.instrument_key,
        old_price=existing.price,
        close_price=close_trade.price,
        new_instrument_key=open_trade.instrument_key,
        new_price=open_trade.price,
        new_expiry=str(expiry_from_key or "?"),
        new_dte=new_dte,
        cycle_pnl=_cycle_pnl(existing, close_trade),
    )


async def _roll_collar(
    broker: UpstoxMarketClient,
    store: PaperStore,
    lookup: InstrumentLookup,
    put_leg: PaperTrade,
    call_leg: PaperTrade,
    roll_date: date,
    dry_run: bool,
) -> list[RollResult]:
    """Roll a collar atomically (4-trade: close put, close call, open put, open call).

    Rollback order on failure:
      - If close_call fails:  delete close_put → raise
      - If open_put fails:    delete close_call, delete close_put → raise
      - If open_call fails:   delete open_put, delete close_call, delete close_put → raise

    Args:
        broker:    Upstox market client.
        store:     PaperStore.
        lookup:    BOD instrument lookup.
        put_leg:   Existing collar put trade.
        call_leg:  Existing collar call trade.
        roll_date: Date for the new trades.
        dry_run:   If True, simulate without writing.

    Returns:
        List of two RollResults (put, call).
    """
    close_put = await _close_leg(broker, store, put_leg, roll_date, dry_run)
    try:
        close_call = await _close_leg(broker, store, call_leg, roll_date, dry_run)
    except Exception:
        if not dry_run:
            store.delete_trade(close_put)
        raise

    try:
        open_put = await _open_new_leg(
            broker, store, lookup, "overlay_collar_put", put_leg.strategy_name, roll_date, dry_run
        )
    except Exception:
        if not dry_run:
            store.delete_trade(close_call)
            store.delete_trade(close_put)
        raise

    try:
        open_call = await _open_new_leg(
            broker, store, lookup, "overlay_collar_call", call_leg.strategy_name, roll_date, dry_run
        )
    except Exception:
        if not dry_run:
            store.delete_trade(open_put)
            store.delete_trade(close_call)
            store.delete_trade(close_put)
        raise

    def _result(existing: PaperTrade, close: PaperTrade, opened: PaperTrade) -> RollResult:
        exp = _parse_expiry_from_key(opened.instrument_key)
        return RollResult(
            strategy=existing.strategy_name,
            leg_role=existing.leg_role,
            old_instrument_key=existing.instrument_key,
            old_price=existing.price,
            close_price=close.price,
            new_instrument_key=opened.instrument_key,
            new_price=opened.price,
            new_expiry=str(exp or "?"),
            new_dte=(exp - roll_date).days if exp else -1,
            cycle_pnl=_cycle_pnl(existing, close),
        )

    return [_result(put_leg, close_put, open_put), _result(call_leg, close_call, open_call)]


# ── Report display ────────────────────────────────────────────────────────────

def _print_roll_report(results: list[RollResult], roll_date: date, dry_run: bool) -> None:
    """Print a formatted roll summary to stdout.

    Args:
        results:   All completed roll results.
        roll_date: Date used for the roll.
        dry_run:   If True, label as preview.
    """
    mode = "DRY RUN — nothing written to DB" if dry_run else "RECORDED TO DB"
    print(f"\n{'═' * 80}")
    print(f"  Overlay Roll | {roll_date} | {mode}")
    print(f"{'═' * 80}")
    if not results:
        print("  No overlays eligible for rolling today.")
        print(f"{'═' * 80}\n")
        return

    print(
        f"  {'Strategy':<24} {'Leg':<20} {'Old Key':<28} {'→ New Key':<28} "
        f"{'Cycle P&L':>12} {'DTE':>5}"
    )
    print(f"  {'─' * 76}")

    total_pnl = Decimal("0")
    for r in results:
        old_short = r.old_instrument_key.replace("NSE_FO|NIFTY", "")
        new_short = r.new_instrument_key.replace("NSE_FO|NIFTY", "")
        pnl_str = f"+{r.cycle_pnl:,.0f}" if r.cycle_pnl >= 0 else f"{r.cycle_pnl:,.0f}"
        print(
            f"  {r.strategy:<24} {r.leg_role:<20} {old_short:<28} {new_short:<28} "
            f"{pnl_str:>12} {r.new_dte:>5}"
        )
        total_pnl += r.cycle_pnl

    print(f"  {'─' * 76}")
    total_str = f"+{total_pnl:,.0f}" if total_pnl >= 0 else f"{total_pnl:,.0f}"
    print(f"  {'Total cycle P&L':>74} {total_str:>12}")
    print(f"{'═' * 80}")
    if dry_run:
        print("\n  Re-run without --dry-run (or with --yes) to write to DB.")
    print()


# ── Main orchestration ────────────────────────────────────────────────────────

async def _run(args: argparse.Namespace) -> None:
    """Async entry point — detect and execute overlay rolls.

    Args:
        args: Parsed CLI arguments.
    """
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=log_level, format="%(levelname)s %(name)s %(message)s")

    roll_date: date = args.date or date.today()
    dry_run: bool = not args.yes  # default is dry-run unless --yes is passed

    effective_tracks: list[str] = []
    if args.tracks:
        track_map = {"spot": "paper_nifty_spot", "futures": "paper_nifty_futures", "proxy": "paper_nifty_proxy"}
        effective_tracks = [track_map[t] for t in args.tracks if t in track_map]
    else:
        effective_tracks = list(ALL_TRACKS)

    store = PaperStore(args.db_path)
    lookup = InstrumentLookup(args.bod_path)

    token = os.environ.get("UPSTOX_ANALYTICS_TOKEN", "")
    if not token and not dry_run:
        print("ERROR: UPSTOX_ANALYTICS_TOKEN not set.", file=sys.stderr)
        sys.exit(1)

    broker = UpstoxMarketClient(token)
    results: list[RollResult] = []

    for strategy in effective_tracks:
        trades_by_role: dict[str, list[PaperTrade]] = {}
        for leg_role in _OVERLAY_ROLES:
            trades_by_role[leg_role] = store.get_trades(strategy, leg_role)

        # Detect collar (both collar legs open simultaneously)
        collar_put_candidates  = _find_expiring_overlay(
            trades_by_role["overlay_collar_put"], roll_date, "overlay_collar_put", args.force
        )
        collar_call_candidates = _find_expiring_overlay(
            trades_by_role["overlay_collar_call"], roll_date, "overlay_collar_call", args.force
        )

        if collar_put_candidates and collar_call_candidates:
            logger.info("%s: rolling collar (4-trade atomic)", strategy)
            collar_results = await _roll_collar(
                broker, store, lookup,
                collar_put_candidates[0], collar_call_candidates[0],
                roll_date, dry_run,
            )
            results.extend(collar_results)
            continue  # collar handled — skip individual leg checks for this strategy

        # Roll individual legs (pp, cc — collar legs handled only together above)
        for leg_role in ("overlay_pp", "overlay_cc"):
            # Enforce blocked combo: futures + standalone CC
            if strategy in _CC_BLOCKED_TRACKS and leg_role == "overlay_cc":
                continue

            candidates = _find_expiring_overlay(
                trades_by_role[leg_role], roll_date, leg_role, args.force
            )
            if not candidates:
                continue

            logger.info("%s/%s: rolling single leg", strategy, leg_role)
            result = await _roll_single(broker, store, lookup, candidates[0], roll_date, dry_run)
            results.append(result)

    _print_roll_report(results, roll_date, dry_run)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Roll expiring overlay legs across all three tracks. "
            "Closes legs at DTE ≤ OVERLAY_ROLL_DTE and opens replacement legs "
            "using the same strike-selection algorithm as the entry script."
        )
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Roll date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--tracks",
        nargs="+",
        choices=["spot", "futures", "proxy"],
        default=None,
        help="Restrict to specific tracks. Default: all three.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Roll even when DTE > OVERLAY_ROLL_DTE (manual intervention).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Write to DB. Without this flag the script runs as a dry-run.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB,
        help=f"Path to SQLite DB (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD,
        help=f"Path to BOD instrument JSON (default: {DEFAULT_BOD})",
    )
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
