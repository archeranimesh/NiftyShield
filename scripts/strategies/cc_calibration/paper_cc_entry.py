# scripts/paper_cc_entry.py
"""CLI for Covered Call Overlay entry.

Gates on IVR, computes max lots, selects closest to 15Δ monthly CE from the live
Upstox option chain, and prints/executes the record_paper_trade command.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import fetch_vix_latest, load_vix_series
from src.client.upstox_market import UpstoxMarketClient
from src.instruments.lookup import InstrumentLookup
from src.instruments.strike_selector import filter_strikes_by_delta
from src.intraday.market_store import IntradayMarketStore
from src.paper.constants import (
    DEFAULT_BOD_PATH,
    DEFAULT_DB_PATH,
    LOT_SIZE,
    NIFTYBEES_KEY,
    STRATEGY_CC_OVERLAY,
    compute_max_lots,
)

load_dotenv()


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(description="Covered Call Overlay entry helper.")
    parser.add_argument(
        "--niftybees-units",
        type=int,
        default=5725,
        help="NiftyBees units pledged (default: 5725).",
    )
    parser.add_argument(
        "--niftybees-ltp",
        type=float,
        default=None,
        help="NiftyBees LTP in ₹ (fetched live if omitted).",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print record_paper_trade command only; do not execute (default: on).",
    )
    parser.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD_PATH,
        help=f"Path to BOD instruments JSON file (default: {DEFAULT_BOD_PATH}).",
    )
    return parser.parse_args()


async def run() -> None:
    """Run the Covered Call entry workflow."""
    args = parse_args()

    # 1. IVR Gate Check
    vix_data_dir = Path("data/historical/ohlc/india_vix")
    ivr = None
    if vix_data_dir.exists():
        try:
            series = load_vix_series(vix_data_dir)
            # Fetch latest VIX (intraday DB or live API fallback)
            vix_today = IntradayMarketStore(DEFAULT_DB_PATH).get_latest_vix_today()
            if vix_today is None:
                vix_today = fetch_vix_latest()

            if vix_today is not None:
                ivr = compute_ivr(vix_today, series)
        except Exception as exc:
            print(f"WARNING: failed to load VIX or compute IVR: {exc}", file=sys.stderr)
    else:
        print(
            f"WARNING: VIX data directory not found at {vix_data_dir}. IVR skipped.",
            file=sys.stderr,
        )

    if ivr is not None:
        if ivr < 0.25:
            print(
                f"⚠️  IVR {ivr:.2f} — below entry threshold (0.25). Skip this cycle or override manually.",
                file=sys.stderr,
            )
            sys.exit(0)
        else:
            print(f"INFO: India VIX IVR = {ivr:.2f}")
    else:
        print("WARNING: India VIX IVR is None (insufficient data). Continuing.", file=sys.stderr)

    # 2. Get live prices & compute max lots
    try:
        client = UpstoxMarketClient()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # Resolve spot and niftybees ltp
    instruments = ["NSE_INDEX|Nifty 50"]
    if args.niftybees_ltp is None:
        instruments.append(NIFTYBEES_KEY)

    try:
        ltp_map = client.get_ltp_sync(instruments)
    except Exception as exc:
        print(f"ERROR: failed to fetch live LTP: {exc}", file=sys.stderr)
        sys.exit(1)

    nifty_spot = ltp_map.get("NSE_INDEX|Nifty 50")
    if nifty_spot is None:
        print("ERROR: failed to fetch live Nifty 50 spot price.", file=sys.stderr)
        sys.exit(1)

    niftybees_ltp: Decimal
    if args.niftybees_ltp is not None:
        niftybees_ltp = Decimal(str(args.niftybees_ltp))
    else:
        val = ltp_map.get(NIFTYBEES_KEY)
        if val is None:
            print("ERROR: failed to fetch live NiftyBees LTP.", file=sys.stderr)
            sys.exit(1)
        niftybees_ltp = val

    # compute max lots
    max_lots = compute_max_lots(
        niftybees_units=args.niftybees_units,
        nifty_spot=nifty_spot,
        niftybees_ltp=niftybees_ltp,
        lot_size=LOT_SIZE,
    )

    if max_lots <= 0:
        print(
            "ERROR: NiftyBees holding insufficient to cover even 1 lot at current Nifty/NiftyBees ratio.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Max lots: {max_lots} (covering {args.niftybees_units} NiftyBees units)")

    # 3. Strike Selection
    if not args.bod_path.exists():
        print(f"ERROR: BOD file not found at {args.bod_path}", file=sys.stderr)
        sys.exit(1)

    try:
        lookup = InstrumentLookup.from_file(args.bod_path)
        expiries = lookup.get_expiry_candidates(underlying="NIFTY", today=date.today())
    except Exception as exc:
        print(f"ERROR: failed to load BOD or resolve expiries: {exc}", file=sys.stderr)
        sys.exit(1)

    monthly_expiry = None
    for label, exp_str in expiries:
        if label == "monthly":
            monthly_expiry = exp_str
            break

    if monthly_expiry is None:
        print("ERROR: no monthly expiry candidate found (DTE 15–45). Stop.", file=sys.stderr)
        sys.exit(1)

    print(f"Using monthly expiry: {monthly_expiry}")

    try:
        raw_chain = client.get_option_chain_sync("NSE_INDEX|Nifty 50", monthly_expiry)
    except Exception as exc:
        print(f"ERROR: failed to fetch option chain for {monthly_expiry}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not raw_chain:
        print(f"ERROR: option chain empty for {monthly_expiry}", file=sys.stderr)
        sys.exit(1)

    candidates = filter_strikes_by_delta(
        raw_chain, option_type="CE", delta_min=0.12, delta_max=0.18
    )
    if not candidates:
        print(
            "ERROR: No CE strikes found in 12–18 delta range. Market may be closed or IVR/chain data stale.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Rank by proximity to target 0.15 delta
    candidates.sort(key=lambda r: abs(abs(r["delta"]) - 0.15))

    print(f"\nTop {min(3, len(candidates))} candidates (closest to 15Δ CE):")
    print(f"{'Strike':<10} {'Delta':<8} {'IV':<8} {'LTP':<8} {'Key'}")
    print(f"{'-' * 6:<10} {'-' * 5:<8} {'-' * 2:<8} {'-' * 3:<8} {'-' * 3}")
    for c in candidates[:3]:
        print(
            f"{int(c['strike']):<10d} {c['delta']:<8.3f} {c['iv']:>5.1f}%  {c['ltp']:<8.2f} {c['instrument_key']}"
        )

    selected = candidates[0]
    print(f"\nAuto-selected: {int(selected['strike'])} CE (delta={selected['delta']:.3f})")

    # 4. Print command
    ivr_str = f"{ivr:.2f}" if ivr is not None else "None"
    notes = (
        f"15d CC entry; IVR={ivr_str}; delta={selected['delta']:.3f}; NiftyBees={niftybees_ltp:.2f}"
    )

    cmd_parts = [
        "python -m scripts.record.record_paper_trade",
        f"  --strategy {STRATEGY_CC_OVERLAY}",
        "  --leg-role covered_call",
        '  --underlying "NSE_INDEX|Nifty 50"',
        "  --option-type CE",
        f"  --strike {int(selected['strike'])}",
        f"  --expiry {monthly_expiry}",
        "  --action SELL",
        f"  --qty {LOT_SIZE}",
        f'  --notes "{notes}"',
    ]
    print("\nCommand to execute:")
    print(" \\\n".join(cmd_parts))

    if args.dry_run:
        print("\nDry-run mode: execution skipped.")
        return

    ans = input("\nExecute? [y/N]: ").strip().lower()
    if ans == "y":
        import subprocess

        exec_cmd = [
            sys.executable,
            "-m",
            "scripts.record.record_paper_trade",
            "--strategy",
            STRATEGY_CC_OVERLAY,
            "--leg-role",
            "covered_call",
            "--underlying",
            "NSE_INDEX|Nifty 50",
            "--option-type",
            "CE",
            "--strike",
            str(int(selected["strike"])),
            "--expiry",
            monthly_expiry,
            "--action",
            "SELL",
            "--qty",
            str(LOT_SIZE),
            "--notes",
            notes,
            "--no-dry-run",
        ]
        print(f"Executing: {' '.join(exec_cmd)}")
        subprocess.run(exec_cmd, check=True)
    else:
        print("Execution cancelled.")


def main() -> None:
    """CLI entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
