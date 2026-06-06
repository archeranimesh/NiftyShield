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
from datetime import date
from decimal import Decimal
from pathlib import Path

import structlog
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.config import settings
from src.utils.logging import setup_logging

load_dotenv()

from src.client.factory import create_client
from src.instruments.lookup import InstrumentLookup
from src.models.portfolio import TradeAction
from src.paper.constants import (
    DEFAULT_BOD_PATH,
    DEFAULT_DB_PATH,
    STRATEGY_CSP,
)
from src.paper.models import PaperTrade
from src.paper.store import PaperStore

_SCRIPT_NAME = "scripts.strategies.csp.paper_csp_roll"
logger = structlog.get_logger(_SCRIPT_NAME)

# Regex for parsing expiry from Nifty FO instrument keys.
_EXPIRY_RE = re.compile(r"NSE_FO\|NIFTY(\d{2}[A-Z]{3}\d{4})(PE|CE)", re.IGNORECASE)


from src.strategy.csp_roll_executor import (
    RollResult,
    _parse_expiry_from_key,
)
from src.strategy.csp_roll_executor import (
    roll_csp as _roll_csp,
)


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
