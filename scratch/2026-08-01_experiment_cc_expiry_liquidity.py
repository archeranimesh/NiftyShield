#!/usr/bin/env python3
"""Throwaway experiment: compare CC (covered call) liquidity across monthly/quarterly/yearly.

Not a tracked deliverable — run once, read the table, decide the CC entry-expiry
preference order, then this file can be deleted or left as a reference script.

Pulls the live Nifty option chain for each of the three expiry bands
(InstrumentLookup.get_expiry_candidates resolves the actual dates offline from the
BOD instrument file), finds the ~4% OTM call in each (matches
DEFAULT_CALL_OTM_PCT in scripts/lookup/find_overlay_strikes.py), and prints OI,
bid/ask spread, delta, and DTE side by side.

Usage:
    python -m scripts.dev.experiment_cc_expiry_liquidity --nifty-spot 24000
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.lookup.find_overlay_strikes import compute_target_strike, find_chain_entry
from src.client.upstox_market import UpstoxMarketClient
from src.config import settings
from src.instruments.lookup import InstrumentLookup

DEFAULT_CALL_OTM_PCT = 4.0
UNDERLYING_INDEX = "NSE_INDEX|Nifty 50"
UNDERLYING_SYMBOL = "NIFTY"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--nifty-spot", type=float, required=True)
    p.add_argument("--call-otm-pct", type=float, default=DEFAULT_CALL_OTM_PCT)
    args = p.parse_args()

    today = date.today()
    lookup = InstrumentLookup.from_file(Path(settings.bod_instruments_path))
    candidates = lookup.get_expiry_candidates(
        UNDERLYING_SYMBOL, today, preference=["monthly", "quarterly", "yearly"]
    )
    if not candidates:
        print("ERROR: no expiry candidates resolved from BOD instrument file.", file=sys.stderr)
        sys.exit(1)

    target_call = compute_target_strike(args.nifty_spot, args.call_otm_pct, "CE")
    print(
        f"Nifty spot: {args.nifty_spot} | target call strike: ~{target_call:.0f} "
        f"({args.call_otm_pct}% OTM)\n"
    )

    client = UpstoxMarketClient()

    header = f"{'LABEL':<10} {'EXPIRY':<12} {'DTE':>4} {'STRIKE':>8} {'DELTA':>7} {'SPREAD%':>8} {'OI':>10} {'LTP':>8}"
    print(header)
    print("-" * len(header))

    for label, expiry in candidates:
        dte = (date.fromisoformat(expiry) - today).days
        try:
            chain_data = client.get_option_chain_sync(UNDERLYING_INDEX, expiry)
        except Exception as exc:
            print(f"{label:<10} {expiry:<12} {dte:>4}  FETCH FAILED: {exc}")
            continue

        call_entry = find_chain_entry(chain_data, "CE", target_call)
        if call_entry is None:
            print(f"{label:<10} {expiry:<12} {dte:>4}  NO MATCHING STRIKE FOUND")
            continue

        spread = (
            f"{call_entry['spread_pct']:.2f}" if call_entry["spread_pct"] is not None else "N/A"
        )
        print(
            f"{label:<10} {expiry:<12} {dte:>4} "
            f"{call_entry['strike']:>8.0f} {call_entry['delta']:>7.3f} "
            f"{spread:>8} {call_entry['oi']:>10,} {call_entry['ltp']:>8.2f}"
        )

    print(
        "\nRead: lower spread% + higher OI = more liquid. Compare against the CC exit "
        "thresholds (DELTA_STOP 0.55, PROFIT_TARGET at 30% of entry credit, TIME_STOP 21 "
        "days) to judge whether a further-dated (quarterly/yearly) contract's slower decay "
        "is worth its wider spread and thinner OI relative to monthly."
    )


if __name__ == "__main__":
    main()
