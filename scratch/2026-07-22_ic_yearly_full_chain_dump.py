"""Diagnostic: dump the FULL NIFTY option chain for a given expiry bucket
(all fields, both sides, every strike) to see which strikes actually have
live market data vs. which are structurally present but empty.

Follow-up to 2026-07-22_ic_yearly_leg_resolution_repro.py, which found that
for the yearly bucket (Dec 2026, DTE 160), option_greeks.delta == 0.0 for
all 20 strikes on both PE and CE -- not missing (None), just zero, despite
every strike having real live ltp/bid/ask/oi/volume (confirmed via this
same script). This script prints every field Upstox returns per strike
(ltp, bid, ask, oi, volume, iv, delta, gamma, theta, vega) so we can check
whether the SAME zero-greeks pattern also holds for other expiry buckets
(e.g. quarterly) -- if quarterly comes back with real non-zero deltas, that
confirms the gap is specific to how far out an expiry is, not a systemic
Upstox outage.

Read-only. Makes one live Upstox API call (get_option_chain_sync).

Run from repo root with the project's normal venv active (defaults to the
yearly bucket; pass a bucket name to check a different one):
    python scratch/2026-07-22_ic_yearly_full_chain_dump.py
    python scratch/2026-07-22_ic_yearly_full_chain_dump.py quarterly
    python scratch/2026-07-22_ic_yearly_full_chain_dump.py monthly
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.client.upstox_market import UpstoxMarketClient  # noqa: E402
from src.config import settings  # noqa: E402
from src.instruments.lookup import InstrumentLookup  # noqa: E402

DEFAULT_BOD_PATH = Path("data/instruments/NSE.json.gz")
DEFAULT_BUCKET = "yearly"


def _row(entry: dict, raw_key: str) -> dict:
    opt = entry.get(raw_key) or {}
    greeks = opt.get("option_greeks") or {}
    mktdata = opt.get("market_data") or {}
    return {
        "instrument_key": opt.get("instrument_key"),
        "ltp": mktdata.get("ltp"),
        "bid": mktdata.get("bid_price"),
        "ask": mktdata.get("ask_price"),
        "oi": mktdata.get("oi"),
        "volume": mktdata.get("volume"),
        "iv": greeks.get("iv"),
        "delta": greeks.get("delta"),
        "gamma": greeks.get("gamma"),
        "theta": greeks.get("theta"),
        "vega": greeks.get("vega"),
    }


def _has_any_market_data(row: dict) -> bool:
    return any(row[k] not in (None, 0, 0.0) for k in ("ltp", "bid", "ask", "oi", "volume"))


def main() -> None:
    bucket = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BUCKET
    print(f"expiry_bucket = {bucket}\n")

    lookup = InstrumentLookup.from_file(DEFAULT_BOD_PATH)
    expiries = lookup.get_expiry_candidates(
        underlying="NIFTY", today=date.today(), preference=[bucket]
    )
    expiry_str = next((e for label, e in expiries if label == bucket), None)
    if expiry_str is None:
        print(f"No '{bucket}' expiry candidate resolved.")
        sys.exit(1)

    dte = (date.fromisoformat(expiry_str) - date.today()).days
    print(f"expiry = {expiry_str}  (DTE {dte})\n")

    client = UpstoxMarketClient(settings.upstox_analytics_token)
    raw_chain = client.get_option_chain_sync("NSE_INDEX|Nifty 50", expiry_str)
    print(f"raw_chain: {len(raw_chain)} strike rows returned\n")

    header = (
        f"{'strike':>9} | {'side':4} | {'ltp':>9} | {'bid':>9} | {'ask':>9} | "
        f"{'oi':>9} | {'vol':>9} | {'iv':>7} | {'delta':>7} | {'gamma':>8} | "
        f"{'theta':>8} | {'vega':>7} | instrument_key"
    )
    print(header)
    print("-" * len(header))

    any_live_row = False
    for entry in sorted(raw_chain, key=lambda e: e.get("strike_price", 0)):
        strike = entry.get("strike_price")
        for side_label, raw_key in (("PE", "put_options"), ("CE", "call_options")):
            row = _row(entry, raw_key)
            live = _has_any_market_data(row)
            any_live_row = any_live_row or live
            marker = "  <-- LIVE" if live else ""
            print(
                f"{strike:>9} | {side_label:4} | {str(row['ltp']):>9} | "
                f"{str(row['bid']):>9} | {str(row['ask']):>9} | {str(row['oi']):>9} | "
                f"{str(row['volume']):>9} | {str(row['iv']):>7} | {str(row['delta']):>7} | "
                f"{str(row['gamma']):>8} | {str(row['theta']):>8} | {str(row['vega']):>7} | "
                f"{row['instrument_key']}{marker}"
            )

    print()
    if any_live_row:
        print("At least one strike has non-zero market data — see LIVE-marked rows above.")
    else:
        print(
            "NO strike on this expiry has any ltp/bid/ask/oi/volume at all — "
            "this contract is entirely unquoted right now, which is why "
            "greeks are all zero (nothing to derive IV/delta from)."
        )


if __name__ == "__main__":
    main()
