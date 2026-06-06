#!/usr/bin/env python3
"""Roll expiring Cash-Secured Put (CSP) legs in paper_csp_nifty_v1.

Detects open CSP legs (leg_role="short_put") whose DTE <= 5, fetches the replacement
strike with the same algorithm as the entry script (closest available strike to the
22-delta put), and atomically closes the old leg + opens the new one.

Roll atomicity guarantee:
    - Close trade is written first.
    - If the open write fails for any reason, the close trade is deleted
      via store.delete_trade to restore the pre-roll position.

Usage:
    # Dry-run — show what would roll, write nothing (default):
    python -m scripts.paper_csp_roll --date 2026-05-07

    # Live run:
    python -m scripts.paper_csp_roll --date 2026-05-07 --no-dry-run --yes

    # Force-roll even when DTE > 5:
    python -m scripts.paper_csp_roll --date 2026-05-07 --no-dry-run --yes --force
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import structlog
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.config import settings
from src.utils.logging import setup_logging

load_dotenv()

from src.client.factory import create_client
from src.client.protocol import BrokerClient
from src.instruments.lookup import InstrumentLookup
from src.instruments.strike_selector import filter_strikes_by_delta, rank_strikes
from src.models.portfolio import TradeAction
from src.paper.constants import (
    DEFAULT_BOD_PATH,
    DEFAULT_DB_PATH,
    NIFTY_UNDERLYING,
    STRATEGY_CSP,
)
from src.paper.models import PaperTrade
from src.paper.store import PaperStore

_SCRIPT_NAME = "scripts.strategies.csp.paper_csp_roll"
logger = structlog.get_logger(_SCRIPT_NAME)

# Regex for parsing expiry from Nifty FO instrument keys.
_EXPIRY_RE = re.compile(r"NSE_FO\|NIFTY(\d{2}[A-Z]{3}\d{4})(PE|CE)", re.IGNORECASE)


# ── Result container ──────────────────────────────────────────────────────────


@dataclass
class RollResult:
    """One completed (or dry-run previewed) CSP roll leg."""

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
    """Compute realised P&L for the closing leg of one CSP cycle.

    For SELL-to-open CSP puts, pnl = (open_price - close_price) * quantity.

    Args:
        existing: The trade that opened the position.
        close:    The trade that closes it (opposite action, same qty).

    Returns:
        Realised cycle P&L as Decimal.
    """
    return (existing.price - close.price) * existing.quantity


def _find_expiring_csp(
    trades: list[PaperTrade],
    roll_date: date,
    force: bool = False,
) -> list[PaperTrade]:
    """Return [existing_open_trade] if the CSP is open and qualifies for rolling.

    A position qualifies when:
      - net_qty != 0  (position is open)
      - instrument key parses to a valid expiry
      - DTE <= 5, or force=True

    Args:
        trades:    All trades for the strategy and leg_role.
        roll_date: Date used to compute DTE.
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
        last_trade = t

    if net >= 0 or last_trade is None:
        return []

    expiry = _parse_expiry_from_key(last_trade.instrument_key)
    if expiry is None:
        logger.debug("CSP: equity leg — skipping roll check")
        return []

    dte = (expiry - roll_date).days
    if not force and dte > 5:
        logger.debug("CSP: DTE=%d > 5 — not yet due for roll", dte)
        return []

    logger.info("CSP: DTE=%d <= 5 — eligible for roll", dte)
    return [last_trade]


# ── Closing leg builder ───────────────────────────────────────────────────────


async def _close_csp_leg(
    broker: BrokerClient,
    store: PaperStore,
    existing: PaperTrade,
    roll_date: date,
    dry_run: bool,
) -> PaperTrade:
    """Fetch live LTP for the existing CSP and build/write a close trade.

    Args:
        broker:    BrokerClient protocol implementation.
        store:     PaperStore.
        existing:  The trade being closed.
        roll_date: Date to record the close trade against.
        dry_run:   If True, build the trade but do not write it.

    Returns:
        The close trade (PaperTrade).
    """
    ltp_resp = await broker.get_ltp([existing.instrument_key])
    raw = ltp_resp.get(existing.instrument_key, Decimal("0"))
    close_price = Decimal(str(raw)).quantize(Decimal("0.01"))
    if close_price <= 0:
        logger.warning(
            "LTP fetch returned 0 for %s — using existing open price as close fallback",
            existing.instrument_key,
        )
        close_price = existing.price

    # Close action is the opposite of the opening action (open SELL -> close BUY)
    close_action = TradeAction.BUY if existing.action == TradeAction.SELL else TradeAction.SELL

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


async def _open_new_csp_leg(
    broker: BrokerClient,
    store: PaperStore,
    lookup: InstrumentLookup,
    strategy: str,
    roll_date: date,
    dry_run: bool,
    quantity: int,
    index: int = 0,
) -> PaperTrade:
    """Select and record the replacement CSP leg.

    Args:
        broker:    BrokerClient protocol implementation.
        store:     PaperStore.
        lookup:    Instrument lookup for expiry candidates.
        strategy:  Strategy name for the new trade.
        roll_date: Date to record the new trade.
        dry_run:   If True, build the trade but do not write it.
        index:     0-based rank index for candidate selection.

    Returns:
        The newly built PaperTrade.
    """
    expiries = lookup.get_expiry_candidates(
        underlying="NIFTY", today=roll_date, preference=["monthly"]
    )
    if not expiries:
        expiries = lookup.get_expiry_candidates(underlying="NIFTY", today=roll_date)
    if not expiries:
        raise ValueError("No valid expiry candidates found in BOD instrument list.")

    expiry_label, expiry_str = expiries[0]

    raw_data = await broker.get_option_chain(NIFTY_UNDERLYING, expiry_str)
    if not raw_data:
        raise ValueError(f"No option chain data returned for {expiry_str}")

    # CSP uses Put options (PE), closest to 22-delta. We look between 20-delta and 35-delta.
    rows = filter_strikes_by_delta(
        raw_data,
        option_type="PE",
        delta_min=0.20,
        delta_max=0.35,
    )
    if not rows:
        raise ValueError(f"No PE strikes found in delta range [0.20, 0.35] for expiry {expiry_str}")

    # Annotate rows with expiry
    for r in rows:
        r["expiry"] = expiry_str
        r["expiry_label"] = expiry_label

    ranked = rank_strikes(rows)
    pick_idx = min(index, len(ranked) - 1)
    selected = ranked[pick_idx]

    new_trade = PaperTrade(
        strategy_name=strategy,
        leg_role="short_put",
        instrument_key=selected["instrument_key"],
        trade_date=roll_date,
        action=TradeAction.SELL,
        quantity=quantity,
        price=Decimal(str(selected["mid"])).quantize(Decimal("0.01")),
        notes=f"Roll open: replacement {selected['instrument_key']}",
    )

    if not dry_run:
        store.record_trade(new_trade)

    return new_trade


# ── Atomic roll helper ────────────────────────────────────────────────────────


async def _roll_csp(
    broker: BrokerClient,
    store: PaperStore,
    lookup: InstrumentLookup,
    existing: PaperTrade,
    roll_date: date,
    dry_run: bool,
    index: int = 0,
) -> RollResult:
    """Roll the CSP leg atomically (close + open).

    If the open write fails after the close has been written, the close trade
    is deleted via store.delete_trade to restore the pre-roll position.

    Args:
        broker:    BrokerClient protocol implementation.
        store:     PaperStore.
        lookup:    BOD instrument lookup.
        existing:  The trade being closed/rolled.
        roll_date: Date for the new trades.
        dry_run:   If True, simulate without writing.

    Returns:
        RollResult describing the completed roll.
    """
    close_trade = await _close_csp_leg(broker, store, existing, roll_date, dry_run)
    try:
        open_trade = await _open_new_csp_leg(
            broker,
            store,
            lookup,
            existing.strategy_name,
            roll_date,
            dry_run,
            quantity=existing.quantity,
            index=index,
        )
    except Exception as e:
        if not dry_run:
            try:
                store.delete_trade(close_trade)  # restore pre-roll state
            except Exception as rollback_err:
                logger.error(
                    "CRITICAL: Failed to rollback close trade %s during roll failure: %s",
                    close_trade.instrument_key,
                    rollback_err,
                    exc_info=True,
                )
        raise e

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
    print(f"  CSP Roll | {roll_date} | {mode}")
    print(f"{'═' * 80}")
    if not results:
        print("  No CSP positions eligible for rolling today.")
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
        pnl_str = f"₹{r.cycle_pnl:+,.0f}"
        print(
            f"  {r.strategy:<24} {r.leg_role:<20} {old_short:<28} {new_short:<28} "
            f"{pnl_str:>12} {r.new_dte:>5}"
        )
        total_pnl += r.cycle_pnl

    print(f"  {'─' * 76}")
    total_str = f"₹{total_pnl:+,.0f}"
    print(f"  {'Total cycle P&L':>74} {total_str:>12}")
    print(f"{'═' * 80}")
    if dry_run:
        print("\n  Re-run with --no-dry-run --yes to write to DB.")
    print()


# ── Main orchestration ────────────────────────────────────────────────────────


async def _run(args: argparse.Namespace) -> None:
    """Async entry point — detect and execute CSP rolls."""
    roll_date: date = args.date or date.today()
    dry_run: bool = args.dry_run

    # CLI-3: Guard against hanging on input() in non-TTY environments
    if not dry_run and not args.yes and not sys.stdin.isatty():
        print(
            "ERROR: --no-dry-run requires --yes in non-interactive environments.",
            file=sys.stderr,
        )
        sys.exit(1)

    store = PaperStore(args.db_path)
    lookup = InstrumentLookup(args.bod_path)

    env = settings.upstox_env
    token = ""
    if env in ("prod", "sandbox"):
        token = settings.upstox_analytics_token if env == "prod" else settings.upstox_sandbox_token
        if not token and not dry_run:
            token_env = "UPSTOX_ANALYTICS_TOKEN" if env == "prod" else "UPSTOX_SANDBOX_TOKEN"
            print(f"ERROR: {token_env} not set.", file=sys.stderr)
            sys.exit(1)

    broker = create_client(env, token=token)
    candidate_index = max(0, args.index - 1)

    async def _do_rolls(is_dry: bool) -> list[RollResult]:
        roll_results = []
        trades = store.get_trades(STRATEGY_CSP, "short_put")
        candidates = _find_expiring_csp(trades, roll_date, args.force)
        if candidates:
            res = await _roll_csp(
                broker, store, lookup, candidates[0], roll_date, is_dry, index=candidate_index
            )
            roll_results.append(res)
        return roll_results

    if not args.yes:
        results = await _do_rolls(is_dry=True)
        _print_roll_report(results, roll_date, dry_run=True)

        if not results or dry_run:
            return

        try:
            confirm = input("Confirm CSP roll execution? [y/N]: ").strip().lower()
            if confirm != "y":
                print("Aborted.")
                sys.exit(0)
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)

        results = await _do_rolls(is_dry=False)
        _print_roll_report(results, roll_date, dry_run=False)
    else:
        results = await _do_rolls(is_dry=dry_run)
        _print_roll_report(results, roll_date, dry_run=dry_run)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Roll expiring Nifty CSP short_put position in paper_csp_nifty_v1."
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Roll date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Roll even when DTE > 5.",
    )
    parser.add_argument(
        "--index",
        type=int,
        default=1,
        help="1-based rank of the replacement candidate to select (default: 1).",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print report only — do not write to DB (default: on).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip interactive confirmation and write to DB.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite DB (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD_PATH,
        help=f"Path to BOD instrument JSON (default: {DEFAULT_BOD_PATH})",
    )
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    setup_logging()
    main()
