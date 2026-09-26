"""Diagnostic: fetch live Nifty option chain and validate delta against IC weekly config.

Throwaway script — not part of src/ or scripts/, no tests, no __init__.py needed.
Read-only: fetches chain, prints comparison, writes nothing.

Usage:
    python tmp/check_live_delta.py
"""

# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.client.upstox_market import UpstoxMarketClient

UNDERLYING = "NSE_INDEX|Nifty 50"
EXPIRY = "2026-07-07"

# The four legs from the weekly IC dry-run, with the config's target delta bands.
LEGS = [
    # (strike, option_type, target_min_delta, target_max_delta, role)
    (23500.0, "PE", 0.06, 0.14, "short_put"),
    (23300.0, "PE", None, None, "long_put_hedge"),
    (24750.0, "CE", 0.04, 0.12, "short_call"),
    (24950.0, "CE", None, None, "long_call_hedge"),
]


def extract(entry: dict, option_type: str) -> dict | None:
    raw_key = "call_options" if option_type == "CE" else "put_options"
    opt = entry.get(raw_key) or {}
    greeks = opt.get("option_greeks") or {}
    mktdata = opt.get("market_data") or {}
    if not opt.get("instrument_key"):
        return None
    return {
        "delta": greeks.get("delta"),
        "iv": greeks.get("iv"),
        "ltp": mktdata.get("ltp"),
    }


def main() -> None:
    client = UpstoxMarketClient()
    ltp_map = client.get_ltp_sync([UNDERLYING])
    spot = ltp_map.get(UNDERLYING)
    print(f"Nifty spot: {spot}")

    chain = client.get_option_chain_sync(UNDERLYING, EXPIRY)
    by_strike = {row.get("strike_price"): row for row in chain}

    print(
        f"{'strike':>8} {'type':>4} {'role':>16} {'delta':>8} {'target':>12} {'iv':>6} {'ltp':>8}  status"
    )
    for strike, opt_type, dmin, dmax, role in LEGS:
        entry = by_strike.get(strike)
        if entry is None:
            print(f"{strike:>8} {opt_type:>4} {role:>16}  -- strike not found in live chain --")
            continue
        row = extract(entry, opt_type)
        if row is None or row["delta"] is None:
            print(f"{strike:>8} {opt_type:>4} {role:>16}  -- no greeks/data on this leg --")
            continue
        delta_abs = abs(row["delta"])
        if dmin is not None:
            status = "OK" if dmin <= delta_abs <= dmax else "OUT OF BAND"
            target_str = f"[{dmin},{dmax}]"
        else:
            status = "n/a (hedge leg)"
            target_str = "-"
        print(
            f"{strike:>8} {opt_type:>4} {role:>16} {delta_abs:>8.4f} {target_str:>12} "
            f"{row['iv']:>6} {row['ltp']:>8}  {status}"
        )


if __name__ == "__main__":
    main()
