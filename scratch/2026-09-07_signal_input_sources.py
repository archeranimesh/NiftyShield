"""Scratch — S5.2a source-discovery spike: gift_nifty / fii / usd_inr.

PERSISTENT SOURCE-OF-RECORD, not an implementation. Produced 2026-09-07 for
`docs/plan/signals/signals_stories.md` §S5.2a — confirm which broker API serves
each of the three `MarketSnapshot` fields the repo has no fetcher for:
`gift_nifty`, `fii` (FIIData), `usd_inr`.

Animesh's steer: probe the APIs we already authenticate against, one field at a
time, find the best source, then build `src/signals/market_inputs.py` against it.
A field served by nobody → the helper raises `DataFetchError`.

FINDINGS (2026-09-07):

  gift_nifty — CONFIRMED. Upstox `GLOBAL_INDEX|SGX NIFTY` (from the separate
               global.json.gz master, not NSE.json.gz). `get_ltp` → 23788.5 on
               2026-09-07 21:08 (Nifty spot 23779.15 — sane premium). 120s
               latency, trades 06:30 Mon–02:45 Sat. Fetcher: one get_ltp on the
               constant key.

  usd_inr    — CONFIRMED (source). Upstox `GLOBAL_INDICATOR|USDINR` ("USD INR"),
               same global master. Spot fx quote — 20s latency, trades ~24/7
               (02:30 Sun–01:30 Sat). Cleaner than the NCD_FO currency futures
               (which read 0.0 outside 09:00–17:00). Fetcher: one get_ltp on the
               constant key. This run confirms the live LTP.

  fii        — no broker API. Decision 2026-09-07: `fetch_fii_data` downloads
               the NSE FII derivative-statistics CSV each morning (T-1).

The full Upstox global master (13 instruments, 2026-09-07):
  GLOBAL_INDEX|SGX NIFTY (GIFT NIFTY) | GLOBAL_INDICATOR|USDINR (USD INR)
  GLOBAL_INDICATOR|BZUSD (Brent) | GLOBAL_INDICATOR|CLUSD (WTI)
  GLOBAL_INDEX|^DJI ^GSPC IXIX (US Tech 100) DOW FUTURES (US 30)
  GLOBAL_INDEX|^HSI ^FTSE ^GDAXI ^FCHI ^N225

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
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # dated filename → no -m

import requests

from src.client.factory import create_client

_UPSTOX_GLOBAL = "https://assets.upstox.com/market-quote/instruments/exchange/global.json.gz"

# Confirmed constant keys from the Upstox global instrument master.
GIFT_NIFTY_KEY = "GLOBAL_INDEX|SGX NIFTY"
USD_INR_KEY = "GLOBAL_INDICATOR|USDINR"


def _dump_global_master() -> None:
    """Print the whole Upstox global master for the record."""
    try:
        resp = requests.get(_UPSTOX_GLOBAL, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"    global.json.gz download failed: {type(exc).__name__}: {exc}")
        return
    with gzip.open(io.BytesIO(resp.content), "rt", encoding="utf-8") as f:
        data = json.load(f)
    print(f"    global.json.gz: {len(data)} instruments —")
    for d in data:
        print(
            f"      {d.get('instrument_key', '?'):30} {d.get('name', ''):14} "
            f"lat={d.get('latency', '')} hrs={d.get('start_time', '')}-{d.get('end_time', '')}"
        )


async def probe_upstox() -> None:
    env = os.environ.get("UPSTOX_ENV", "prod")
    print(f"\n=== Upstox ({env}) — get_ltp ===")
    try:
        client = create_client(env)
    except Exception:  # noqa: BLE001 — spike: show whatever blew up
        print("  create_client failed:")
        traceback.print_exc()
        return

    print("\n  [global instrument master]")
    _dump_global_master()

    candidates: dict[str, list[str]] = {
        "gift_nifty": [GIFT_NIFTY_KEY],  # CONFIRMED 2026-09-07 → 23788.5
        "usd_inr": [USD_INR_KEY],  # confirming live LTP this run
        "india_vix": ["NSE_INDEX|India VIX"],  # control — known good
        "nifty_spot": ["NSE_INDEX|Nifty 50"],  # control — known good
    }
    for field, keys in candidates.items():
        print(f"\n  [{field}]")
        for key in keys:
            try:
                resp: dict[str, Any] = await client.get_ltp([key])
                print(f"    {key!r:28} -> {resp}")
            except Exception as exc:  # noqa: BLE001
                print(f"    {key!r:28} -> {type(exc).__name__}: {exc}")


def note_ruled_out() -> None:
    print("\n=== Ruled out ===")
    print("  Dhan: GIFT Nifty is index id 5024 but marketfeed/ltp → 401 (paid Data API).")
    print("  Dhan/Upstox NCD_FO USDINR futures: read 0.0 outside 09:00–17:00; the")
    print("    GLOBAL_INDICATOR|USDINR spot quote supersedes them.")
    print("  Nuvama: no arbitrary quote endpoint wired.")

    print("\n=== FII / DII index positioning ===")
    print("  No broker API. Decision 2026-09-07: fetch_fii_data downloads the NSE FII")
    print("  derivative-statistics CSV each morning (T-1). Raises DataFetchError on failure.")


async def main() -> None:
    await probe_upstox()
    note_ruled_out()
    print("\n--- done. Update signals_stories.md §S5.2a 'Confirmed sources:' with this output ---")


if __name__ == "__main__":
    asyncio.run(main())
