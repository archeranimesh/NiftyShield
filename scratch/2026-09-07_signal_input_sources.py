"""Scratch — S5.2a source-discovery spike: gift_nifty / fii / usd_inr.

PERSISTENT SOURCE-OF-RECORD, not an implementation. Produced 2026-09-07 for
`docs/plan/signals/signals_stories.md` §S5.2a so Animesh can confirm which broker
API (if any) serves each of the three `MarketSnapshot` fields the repo has no
fetcher for: `gift_nifty`, `fii` (FIIData), `usd_inr`.

Animesh's call (2026-09-07): do NOT hard-code neutral defaults, do NOT scrape NSE
HTML — probe the broker APIs we already authenticate against (Upstox, Dhan,
Nuvama), see which serves each field, then build `src/signals/market_inputs.py`
against the confirmed endpoints. A field served by nobody → the helper raises
`DataFetchError` and the caller decides whether to abort the 09:15 run.

What this script does, per field:
  - tries Upstox `get_ltp` against a list of candidate instrument keys;
  - tries Dhan `fetch_ltp_raw` against candidate (exchange, security_id) pairs;
  - notes the Nuvama surface (bond-holdings reader only — no arbitrary quote
    endpoint) and the FII/DII situation (NSE publishes EOD CSV; no broker API);
  - prints, per candidate: the client + endpoint, the raw response shape, and
    the parsed value (or the exception).

Run from repo root, venv active, with live tokens in the environment
(`UPSTOX_ANALYTICS_TOKEN`, `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN`):

    python scratch/2026-09-07_signal_input_sources.py            # prod Upstox token
    UPSTOX_ENV=sandbox python scratch/2026-09-07_signal_input_sources.py

Record the outcome under "Confirmed sources:" in signals_stories.md §S5.2a
before writing the module.
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # dated filename → no -m

from src.client.factory import create_client
from src.config import settings

# ── Candidate instrument keys ────────────────────────────────────────────────
# Upstox V3 LTP batch accepts index, equity and F&O keys in one call
# (REFERENCES.md line 72). GIFT Nifty (NSE IX, ex-SGX Nifty) and USD/INR are the
# unknowns — no key is documented in REFERENCES.md, so these are guesses to be
# confirmed or ruled out by the live run.
UPSTOX_CANDIDATES: dict[str, list[str]] = {
    "gift_nifty": [
        "NSE_INDEX|GIFT Nifty",
        "NSE_INDEX|Gift Nifty 50",
        "NSE_IX|GIFT Nifty",
        "NSE_INDEX|SGX Nifty",
    ],
    "usd_inr": [
        "NSE_INDEX|USD INR",
        "CDS_FO|USDINR",  # current-month USDINR future — needs a real expiry key
        "NSE_CD|USDINR",
        "NCD_FO|USDINR",
    ],
    "india_vix": [  # sanity check — this one we expect to work
        "NSE_INDEX|India VIX",
    ],
    "nifty_spot": [  # control — known-good key from REFERENCES.md
        "NSE_INDEX|Nifty 50",
    ],
}

# Dhan uses numeric security IDs per exchange segment. Without the Dhan
# instrument master loaded here these are placeholders — fill from
# https://images.dhan.co/api-data/api-scrip-master.csv if the Upstox probe fails.
DHAN_CANDIDATES: dict[str, dict[str, list[int]]] = {
    # "usd_inr": {"NSE_CURRENCY": [<security_id>]},
}


async def probe_upstox() -> None:
    env = os.environ.get("UPSTOX_ENV", "prod")
    print(f"\n=== Upstox ({env}) — get_ltp ===")
    try:
        client = create_client(env)
    except Exception:  # noqa: BLE001 — spike: show whatever blew up
        print("  create_client failed:")
        traceback.print_exc()
        return

    for field, keys in UPSTOX_CANDIDATES.items():
        print(f"\n  [{field}]")
        for key in keys:
            try:
                resp: dict[str, Any] = await client.get_ltp([key])
                print(f"    {key!r:34} -> {resp}")
            except Exception as exc:  # noqa: BLE001
                print(f"    {key!r:34} -> {type(exc).__name__}: {exc}")


def probe_dhan() -> None:
    print("\n=== Dhan — fetch_ltp_raw ===")
    cid, tok = settings.dhan_client_id, settings.dhan_access_token
    if not (cid and tok):
        print("  DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN not set — skipped")
        return
    if not DHAN_CANDIDATES:
        print("  no DHAN_CANDIDATES defined — populate from the Dhan scrip master")
        print("  (https://images.dhan.co/api-data/api-scrip-master.csv) if Upstox fails")
        return

    from src.dhan.reader import fetch_ltp_raw

    for field, ids_by_exchange in DHAN_CANDIDATES.items():
        print(f"\n  [{field}]")
        try:
            resp = fetch_ltp_raw(cid, tok, ids_by_exchange)
            print(f"    {ids_by_exchange} -> {resp}")
        except Exception as exc:  # noqa: BLE001
            print(f"    {ids_by_exchange} -> {type(exc).__name__}: {exc}")


def note_nuvama_and_fii() -> None:
    print("\n=== Nuvama ===")
    print("  Surface is a bond-holdings reader (src/nuvama/reader.py) +")
    print("  options-position parser (src/nuvama/options_reader.py). No arbitrary")
    print("  market-quote endpoint is wired. Would need a new APIConnect quote call")
    print("  in src/nuvama/ before it can serve gift_nifty / usd_inr.")

    print("\n=== FII / DII index positioning ===")
    print("  No broker API exposes this. NSE publishes it EOD as")
    print("  'FII derivative statistics' CSV (fii_stats_<DD-Mon-YYYY>.csv) and the")
    print("  participant-wise OI CSV. Options if no broker serves it:")
    print("    (a) fetch_fii_data raises DataFetchError — 09:15 run proceeds without it")
    print("        only if MarketSnapshot.fii is made optional (model change, separate task);")
    print("    (b) a dedicated NSE-CSV fetcher — but that is the scrape path Animesh ruled out;")
    print("    (c) accept T-2 staleness from a manually-refreshed local CSV.")
    print("  DECIDE before implementing fetch_fii_data.")


async def main() -> None:
    await probe_upstox()
    probe_dhan()
    note_nuvama_and_fii()
    print("\n--- done. Paste this output under signals_stories.md §S5.2a 'Confirmed sources:' ---")


if __name__ == "__main__":
    asyncio.run(main())
