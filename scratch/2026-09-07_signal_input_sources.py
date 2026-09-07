"""Scratch — S5.2a source-discovery spike: gift_nifty / fii / usd_inr.

PERSISTENT SOURCE-OF-RECORD, not an implementation. Produced 2026-09-07 for
`docs/plan/signals/signals_stories.md` §S5.2a — confirm which broker API serves
each of the three `MarketSnapshot` fields the repo has no fetcher for:
`gift_nifty`, `fii` (FIIData), `usd_inr`.

Animesh's steer: probe the APIs we already authenticate against, one field at a
time, find the best source, then build `src/signals/market_inputs.py` against it.
A field served by nobody → the helper raises `DataFetchError`.

FINDINGS (2026-09-07, debugging one field at a time):

  gift_nifty — CONFIRMED. Upstox `GLOBAL_INDEX|SGX NIFTY` (from the separate
               global.json.gz master, not NSE.json.gz). `get_ltp` → 23788.5 on
               2026-09-07 21:08 (Nifty spot 23779.15, sane premium). Fetcher is
               a one-line get_ltp on the constant key. (Dhan has it as index id
               5024 but marketfeed/ltp is 401 — paid Data API. Nuvama: no quote
               surface.)

  usd_inr    — OPEN. Upstox `NCD_FO` currency FUTURE returns 0.0 after 17:00
               (NSE currency segment closed). This run also dumps all ~13 global
               instruments in case one is a cleaner USD/INR fx quote, and probes
               both nearest-weekly and nearest-monthly USDINR futures (monthly
               carries the liquidity). RE-RUN DURING MARKET HOURS (09:00-17:00).

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


def _usdinr_futures() -> dict[str, str]:
    """Resolve the nearest-weekly and nearest-monthly USDINR FUT keys from the dump.

    Monthly USDINR futures (last-Tuesday cadence) carry the liquidity; the weekly
    contracts can be thin. Probe both so the real fetcher picks the right one.
    """
    lookup = InstrumentLookup.from_file(_BOD_PATH)
    futs = lookup.search("USDINR", segment="NCD_FO", instrument_type="FUT", max_results=50)
    today = date.today()
    live = sorted(
        (
            (date.fromisoformat(parse_expiry(f["expiry"])), f)
            for f in futs
            if parse_expiry(f.get("expiry"))
            and date.fromisoformat(parse_expiry(f["expiry"])) >= today
        ),
        key=lambda t: t[0],
    )
    out: dict[str, str] = {}
    if live:
        exp, f = live[0]
        print(f"    nearest USDINR FUT (weekly): {f['instrument_key']} ({f['trading_symbol']})")
        out["weekly"] = f["instrument_key"]
    # nearest month-end (last expiry of the earliest calendar month present)
    by_month: dict[tuple[int, int], tuple[date, dict]] = {}
    for exp, f in live:
        key = (exp.year, exp.month)
        if key not in by_month or exp > by_month[key][0]:
            by_month[key] = (exp, f)
    if by_month:
        _, f = by_month[min(by_month)]
        print(f"    nearest USDINR FUT (monthly): {f['instrument_key']} ({f['trading_symbol']})")
        out["monthly"] = f["instrument_key"]
    return out


def _list_global_instruments() -> list[str]:
    """Dump the whole Upstox global master (~13 rows) and return likely usd_inr keys."""
    try:
        resp = requests.get(_UPSTOX_GLOBAL, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"    global.json.gz download failed: {type(exc).__name__}: {exc}")
        return []
    with gzip.open(io.BytesIO(resp.content), "rt", encoding="utf-8") as f:
        data = json.load(f)
    print(f"    global.json.gz: {len(data)} instruments —")
    fx_keys: list[str] = []
    for d in data:
        name = str(d.get("name", ""))
        key = d.get("instrument_key", "")
        print(f"      {key:28} {name}")
        if any(t in name.upper() for t in ("USD", "INR", "DXY", "DOLLAR", "RUPEE")):
            fx_keys.append(key)
    return fx_keys


async def probe_upstox() -> None:
    env = os.environ.get("UPSTOX_ENV", "prod")
    print(f"\n=== Upstox ({env}) — get_ltp ===")
    try:
        client = create_client(env)
    except Exception:  # noqa: BLE001 — spike: show whatever blew up
        print("  create_client failed:")
        traceback.print_exc()
        return

    print("\n  [global master dump — looking for a usd_inr / fx quote]")
    fx_keys = _list_global_instruments()

    print("\n  [usd_inr — NCD_FO currency futures]")
    usdinr = _usdinr_futures()

    candidates: dict[str, list[str]] = {
        "gift_nifty": ["GLOBAL_INDEX|SGX NIFTY"],  # CONFIRMED 2026-09-07
        "usd_inr (global fx?)": fx_keys,
        "usd_inr (NCD_FO fut)": list(usdinr.values()),
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
