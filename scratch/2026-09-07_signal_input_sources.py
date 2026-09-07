"""Scratch — S5.2a source-discovery spike: gift_nifty / fii / usd_inr.

PERSISTENT SOURCE-OF-RECORD, not an implementation. Produced 2026-09-07 for
`docs/plan/signals/signals_stories.md` §S5.2a — confirm which broker API (if any)
serves each of the three `MarketSnapshot` fields the repo has no fetcher for:
`gift_nifty`, `fii` (FIIData), `usd_inr`.

Animesh's call (2026-09-07): do NOT hard-code neutral defaults, do NOT scrape NSE
HTML — probe the broker APIs we already authenticate against (Upstox, Dhan,
Nuvama). A field served by nobody → the helper raises `DataFetchError` and the
caller decides whether to abort the 09:15 run.

FINDINGS AFTER THE FIRST RUN + INSTRUMENT-MASTER DEBUG (2026-09-07):

  usd_inr  — SOLVED via Upstox. USDINR is a currency FUTURE in the `NCD_FO`
             segment of `data/instruments/NSE.json.gz` (23 live contracts). The
             first probe failed only because it passed the bare symbol
             `USDINR`, not the `NCD_FO|<token>` key. This script now resolves
             the nearest-expiry USDINR FUT from the local dump and probes its
             LTP. The real fetcher uses `InstrumentLookup.search("USDINR",
             segment="NCD_FO", instrument_type="FUT")` + nearest expiry.

  gift_nifty — NOT on Upstox. Zero records match "gift" or "sgx" across all
               80,836 NSE instruments (139 NSE_INDEX names, none is GIFT Nifty).
               GIFT Nifty trades on NSE IX (GIFT City) — a separate exchange no
               Indian retail broker market-data feed carries. This script also
               probes the Dhan scrip master to rule Dhan in or out. If Dhan is
               also empty, gift_nifty needs a source DECISION (drop / optional /
               allow a non-broker fetch).

  fii — no broker API (confirmed). Animesh's call: `fetch_fii_data` downloads the
        NSE FII derivative-statistics CSV each morning (T-1 data).

Run from repo root, venv active, with live tokens in the environment
(`UPSTOX_ANALYTICS_TOKEN`, and optionally `DHAN_CLIENT_ID` / `DHAN_ACCESS_TOKEN`):

    python scratch/2026-09-07_signal_input_sources.py
    UPSTOX_ENV=sandbox python scratch/2026-09-07_signal_input_sources.py
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import traceback
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # dated filename → no -m

import requests

from src.client.factory import create_client
from src.config import settings
from src.instruments.lookup import InstrumentLookup, parse_expiry

_BOD_PATH = "data/instruments/NSE.json.gz"
_DHAN_SCRIP_MASTER = "https://images.dhan.co/api-data/api-scrip-master.csv"


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


async def probe_upstox() -> None:
    env = os.environ.get("UPSTOX_ENV", "prod")
    print(f"\n=== Upstox ({env}) — get_ltp ===")
    try:
        client = create_client(env)
    except Exception:  # noqa: BLE001 — spike: show whatever blew up
        print("  create_client failed:")
        traceback.print_exc()
        return

    candidates: dict[str, list[str]] = {
        "usd_inr": [k for k in (_nearest_usdinr_future(),) if k],
        "gift_nifty": [
            "NSE_INDEX|GIFT Nifty",
            "NSE_INDEX|Gift Nifty 50",
            "NSE_INDEX|SGX Nifty",
        ],
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


def _gift_nifty_dhan_security_id() -> int | None:
    """Find the GIFT Nifty INDEX security id in the Dhan scrip master.

    Confirmed row (2026-09-07): NSE,I,5024,INDEX,0,GIFTNIFTY,...,Gift Nifty
    """
    try:
        resp = requests.get(_DHAN_SCRIP_MASTER, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"  scrip-master download failed: {type(exc).__name__}: {exc}")
        return None
    body = resp.content
    if body[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            body = zf.read(zf.namelist()[0])
    for ln in body.decode("utf-8", errors="replace").splitlines():
        cols = ln.split(",")
        # SEM_EXM_EXCH_ID, SEM_SEGMENT, SEM_SMST_SECURITY_ID, SEM_INSTRUMENT_NAME, ...
        if len(cols) > 5 and cols[0] == "NSE" and cols[3] == "INDEX" and "GIFT" in cols[5].upper():
            print(f"  scrip-master row: {ln[:120]}")
            return int(cols[2])
    return None


def probe_dhan_gift_nifty() -> None:
    """gift_nifty is not on Upstox. Dhan carries it as an index — probe its LTP.

    Dhan marketfeed/ltp segment for an index is `IDX_I`. NOTE (src/dhan/reader.py
    line ~230): that endpoint needs the paid Dhan Data API — a 401/403 here means
    the plan doesn't include it, not that the instrument is missing.
    """
    print("\n=== Dhan — gift_nifty via marketfeed/ltp (IDX_I) ===")
    cid, tok = settings.dhan_client_id, settings.dhan_access_token
    if not (cid and tok):
        print("  DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN not set — skipped")
        return
    sec_id = _gift_nifty_dhan_security_id()
    if sec_id is None:
        print("  GIFT Nifty not found in scrip master")
        return
    print(f"  GIFT Nifty Dhan security id: {sec_id}")

    from src.dhan.reader import fetch_ltp_raw

    for segment in ("IDX_I", "NSE_I", "NSE_EQ"):
        try:
            out = fetch_ltp_raw(cid, tok, {segment: [sec_id]})
            print(f"    {segment:8} -> {out}")
        except Exception as exc:  # noqa: BLE001
            print(f"    {segment:8} -> {type(exc).__name__}: {exc}")


def note_nuvama_and_fii() -> None:
    print("\n=== Nuvama ===")
    print("  Bond-holdings reader + options-position parser only. No arbitrary quote")
    print("  endpoint wired — would need a new APIConnect call in src/nuvama/. Not")
    print("  pursued: Upstox already serves usd_inr and the index controls.")

    print("\n=== FII / DII index positioning ===")
    print("  No broker API. Decision taken 2026-09-07: fetch_fii_data downloads the")
    print("  NSE FII derivative-statistics CSV each morning (T-1). Raises DataFetchError")
    print("  on download/parse failure — caller decides whether to abort the 09:15 run.")


async def main() -> None:
    await probe_upstox()
    probe_dhan_gift_nifty()
    note_nuvama_and_fii()
    print("\n--- done. Update signals_stories.md §S5.2a 'Confirmed sources:' with this output ---")


if __name__ == "__main__":
    asyncio.run(main())
