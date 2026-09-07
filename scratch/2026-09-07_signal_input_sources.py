"""Scratch — S5.2a source-discovery spike: gift_nifty / fii / usd_inr.

PERSISTENT SOURCE-OF-RECORD, not an implementation. Produced 2026-09-07 for
`docs/plan/signals/signals_stories.md` §S5.2a — confirm which broker API serves
each of the three `MarketSnapshot` fields the repo has no fetcher for:
`gift_nifty`, `fii` (FIIData), `usd_inr`.

Animesh's steer: probe the APIs we already authenticate against, one field at a
time, find the best source, then build `src/signals/market_inputs.py` against it.
A field served by nobody → the helper raises `DataFetchError`.

FINDINGS (2026-09-07, debugging one field at a time):

  gift_nifty — Upstox carries it, but NOT in the NSE instrument dump. It is a
               GLOBAL index: separate master at
               https://assets.upstox.com/market-quote/instruments/exchange/global.json.gz
               key form `GLOBAL_INDEX|SGX NIFTY` (per LTP-v3 docs). The batch
               LTP endpoint (`_fetch_ltp_batch`) passes any key straight through
               as the `instrument_key` param — no segment gate — so `get_ltp`
               should serve it. This script resolves the real key from
               global.json.gz and probes it. (Dhan carries GIFT Nifty as index
               id 5024 but its marketfeed/ltp is 401 — paid Data API not on the
               plan. Nuvama has no quote surface. Upstox global is the path.)

  usd_inr    — Upstox `NCD_FO` currency FUTURE. Nearest-expiry USDINR FUT
               resolved from `data/instruments/NSE.json.gz`; `get_ltp` returns
               200. First run gave 0.0 (after hours) — re-confirm in market
               hours. Fetcher: `InstrumentLookup.search("USDINR",
               segment="NCD_FO", instrument_type="FUT")` → nearest expiry.

  fii        — no broker API. Decision 2026-09-07: `fetch_fii_data` downloads
               the NSE FII derivative-statistics CSV each morning (T-1).

Run from repo root, venv active, with `UPSTOX_ANALYTICS_TOKEN` set:

    python scratch/2026-09-07_signal_input_sources.py
    UPSTOX_ENV=sandbox python scratch/2026-09-07_signal_input_sources.py
"""

from __future__ import annotations

import asyncio
import gzip
import io
import json
import os
import sys
import traceback
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # dated filename → no -m

import requests

from src.client.factory import create_client
from src.instruments.lookup import InstrumentLookup, parse_expiry

_BOD_PATH = "data/instruments/NSE.json.gz"
_UPSTOX_GLOBAL = "https://assets.upstox.com/market-quote/instruments/exchange/global.json.gz"


def _nearest_usdinr_future() -> str | None:
    """Resolve the nearest-expiry USDINR FUT instrument_key from the local dump."""
    lookup = InstrumentLookup.from_file(_BOD_PATH)
    futs = lookup.search("USDINR", segment="NCD_FO", instrument_type="FUT", max_results=50)
    today = date.today().isoformat()
    live = sorted(
        ((parse_expiry(f.get("expiry")), f) for f in futs if parse_expiry(f.get("expiry"))),
        key=lambda t: t[0],
    )
    for exp, f in live:
        if exp >= today:
            print(
                f"    nearest USDINR FUT: {f['instrument_key']} ({f['trading_symbol']}, exp {exp})"
            )
            return f["instrument_key"]
    return None


def _global_index_keys() -> list[str]:
    """Download the Upstox global instrument master and return GIFT/SGX index keys."""
    try:
        resp = requests.get(_UPSTOX_GLOBAL, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"    global.json.gz download failed: {type(exc).__name__}: {exc}")
        return []
    with gzip.open(io.BytesIO(resp.content), "rt", encoding="utf-8") as f:
        data = json.load(f)
    print(f"    global.json.gz: {len(data)} instruments")
    hits = [
        d
        for d in data
        if "gift" in str(d.get("name", "")).lower()
        or "sgx" in str(d.get("name", "")).lower()
        or "gift" in str(d.get("trading_symbol", "")).lower()
        or "sgx" in str(d.get("trading_symbol", "")).lower()
    ]
    for d in hits:
        print(
            f"    global row: {json.dumps({k: d.get(k) for k in ('segment', 'name', 'trading_symbol', 'instrument_key')})}"
        )
    return [d["instrument_key"] for d in hits if d.get("instrument_key")]


async def probe_upstox() -> None:
    env = os.environ.get("UPSTOX_ENV", "prod")
    print(f"\n=== Upstox ({env}) — get_ltp ===")
    try:
        client = create_client(env)
    except Exception:  # noqa: BLE001 — spike: show whatever blew up
        print("  create_client failed:")
        traceback.print_exc()
        return

    print("\n  [gift_nifty] — resolving from Upstox global instrument master")
    gift_keys = _global_index_keys() or ["GLOBAL_INDEX|SGX NIFTY"]  # doc fallback

    candidates: dict[str, list[str]] = {
        "gift_nifty": gift_keys,
        "usd_inr": [k for k in (_nearest_usdinr_future(),) if k],
        "india_vix": ["NSE_INDEX|India VIX"],  # control — known good
        "nifty_spot": ["NSE_INDEX|Nifty 50"],  # control — known good
    }
    for field, keys in candidates.items():
        print(f"\n  [{field}]")
        if not keys:
            print("    (no candidate key resolved)")
        for key in keys:
            try:
                resp: dict[str, Any] = await client.get_ltp([key])
                print(f"    {key!r:34} -> {resp}")
            except Exception as exc:  # noqa: BLE001
                print(f"    {key!r:34} -> {type(exc).__name__}: {exc}")


def note_nuvama_and_fii() -> None:
    print("\n=== Nuvama / Dhan (ruled out for gift_nifty) ===")
    print("  Dhan: GIFT Nifty is index id 5024 but marketfeed/ltp → 401 (paid Data API).")
    print("  Nuvama: no arbitrary quote endpoint wired.")

    print("\n=== FII / DII index positioning ===")
    print("  No broker API. Decision 2026-09-07: fetch_fii_data downloads the NSE FII")
    print("  derivative-statistics CSV each morning (T-1). Raises DataFetchError on failure.")


async def main() -> None:
    await probe_upstox()
    note_nuvama_and_fii()
    print("\n--- done. Update signals_stories.md §S5.2a 'Confirmed sources:' with this output ---")


if __name__ == "__main__":
    asyncio.run(main())
