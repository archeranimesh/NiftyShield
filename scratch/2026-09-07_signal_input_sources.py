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
               global.json.gz master). `get_ltp` → 23791.0 (Nifty spot 23779.15).
               Fetcher: one get_ltp on the constant key.

  usd_inr    — comparing two Upstox sources (value ~94.5 confirmed against the
               live app: USDINR FUT NCD 28SEP26 = 94.5675):
                 A. `GLOBAL_INDICATOR|USDINR` — only the historical-candle v3
                    endpoint accepts it (LTP / full-quote / ohlc all 400
                    "Invalid Instrument key"). T-1 daily close, no intraday.
                 B. `NCD_FO` USDINR monthly future — `get_ltp` works, live
                    09:00–17:00 (so live at the 09:15 cron); needs nearest
                    month-end expiry resolution. This run also pulls its T-1
                    hist-candle close for an after-hours comparison with A.

  fii        — no broker API, and the F&O positioning CSV (participant-wise OI)
               404s for every date. Only the CASH-market `fiidiiTradeReact` JSON
               serves data: FII/FPI + DII buy/sell/net ₹ cr, previous session.
               → `FIIData` must be redefined to cash net flows (see story §S5.2a).

Run from repo root, venv active, with `UPSTOX_ANALYTICS_TOKEN` set. For B's live
LTP, run during currency-market hours (09:00–17:00 IST):

    python scratch/2026-09-07_signal_input_sources.py
    UPSTOX_ENV=sandbox python scratch/2026-09-07_signal_input_sources.py
"""

from __future__ import annotations

import asyncio
import datetime as dt
import gzip
import io
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # dated filename → no -m

import requests

from src.client.factory import create_client
from src.instruments.lookup import InstrumentLookup, parse_expiry

_BOD_PATH = "data/instruments/NSE.json.gz"
_UPSTOX_GLOBAL = "https://assets.upstox.com/market-quote/instruments/exchange/global.json.gz"

GIFT_NIFTY_KEY = "GLOBAL_INDEX|SGX NIFTY"
USD_INR_GLOBAL_KEY = "GLOBAL_INDICATOR|USDINR"


def _dump_global_master() -> None:
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


def _nearest_monthly_usdinr_future() -> dict | None:
    """Nearest month-end USDINR FUT from the local Upstox dump (the liquid contract)."""
    lookup = InstrumentLookup.from_file(_BOD_PATH)
    futs = lookup.search("USDINR", segment="NCD_FO", instrument_type="FUT", max_results=50)
    today = dt.date.today()
    live: list[tuple[dt.date, dict]] = []
    for f in futs:
        exp_s = parse_expiry(f.get("expiry"))
        if exp_s:
            exp = dt.date.fromisoformat(exp_s)
            if exp >= today:
                live.append((exp, f))
    by_month: dict[tuple[int, int], tuple[dt.date, dict]] = {}
    for exp, f in live:
        k = (exp.year, exp.month)
        if k not in by_month or exp > by_month[k][0]:
            by_month[k] = (exp, f)
    if not by_month:
        return None
    _, f = by_month[min(by_month)]
    return f


def _hist_candle_latest_close(session: requests.Session, key: str) -> Any:
    """Latest daily close for `key` via historical-candle v3 (the only endpoint that
    accepts GLOBAL_INDICATOR). Returns the (date, close) of the newest candle."""
    today = dt.date.today()
    to_d = today.isoformat()
    from_d = (today - dt.timedelta(days=10)).isoformat()
    url = (
        f"https://api.upstox.com/v3/historical-candle/{quote(key, safe='')}/days/1/{to_d}/{from_d}"
    )
    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200:
            return f"[{r.status_code}] {r.text[:160]}"
        candles = r.json().get("data", {}).get("candles", [])
        if not candles:
            return "no candles"
        c = candles[0]  # newest first
        return f"{c[0][:10]} close={c[4]}"
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"


async def probe_upstox() -> None:
    env = os.environ.get("UPSTOX_ENV", "prod")
    print(f"\n=== Upstox ({env}) ===")
    try:
        client = create_client(env)
    except Exception:  # noqa: BLE001
        print("  create_client failed:")
        traceback.print_exc()
        return

    print("\n  [global instrument master]")
    _dump_global_master()

    for field, key in (
        ("gift_nifty", GIFT_NIFTY_KEY),
        ("india_vix (control)", "NSE_INDEX|India VIX"),
        ("nifty_spot (control)", "NSE_INDEX|Nifty 50"),
    ):
        print(f"\n  [{field}] get_ltp")
        try:
            print(f"    {key!r:26} -> {await client.get_ltp([key])}")
        except Exception as exc:  # noqa: BLE001
            print(f"    {key!r:26} -> {type(exc).__name__}: {exc}")

    # ── usd_inr: compare source A (GLOBAL_INDICATOR hist-candle) vs B (NCD_FO fut) ──
    print("\n  [usd_inr — SOURCE COMPARISON]")
    session = client._market._session  # noqa: SLF001 — spike

    print("  A. GLOBAL_INDICATOR|USDINR")
    print("     get_ltp        -> ", end="")
    try:
        print(await client.get_ltp([USD_INR_GLOBAL_KEY]))
    except Exception as exc:  # noqa: BLE001
        print(f"{type(exc).__name__}: {exc}")
    print(f"     hist-candle    -> {_hist_candle_latest_close(session, USD_INR_GLOBAL_KEY)}")

    print("  B. NCD_FO USDINR monthly future")
    fut = _nearest_monthly_usdinr_future()
    if not fut:
        print("     (no live NCD_FO USDINR FUT found in the dump)")
    else:
        fkey = fut["instrument_key"]
        print(f"     contract       -> {fkey} ({fut.get('trading_symbol')})")
        try:
            print(f"     get_ltp        -> {await client.get_ltp([fkey])}")
        except Exception as exc:  # noqa: BLE001
            print(f"     get_ltp        -> {type(exc).__name__}: {exc}")
        print(f"     hist-candle    -> {_hist_candle_latest_close(session, fkey)}")


_NSE_FII_DII = "https://www.nseindia.com/api/fiidiiTradeReact"
_NSE_FAO_PART_OI = "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{d}.csv"


def probe_fii() -> None:
    """FII/DII data probe.

    Only the cash-market fiidiiTradeReact JSON serves data in this environment.
    The F&O participant-wise OI CSV (index-futures / index-options net position)
    404s for every recent date — that source is not available.
    """
    print("\n=== FII / DII ===")
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

    print("  A. cash-market net (fiidiiTradeReact):")
    try:
        r = s.get(_NSE_FII_DII, timeout=15)
        print(f"     [{r.status_code}] {r.text[:400]}")
    except Exception as exc:  # noqa: BLE001
        print(f"     {type(exc).__name__}: {exc}")

    print("  B. F&O participant-wise OI CSV (index fut/opt positioning):")
    for ds in ("05-Sep-2026", "04-Sep-2026", "03-Sep-2026"):
        try:
            r = s.get(_NSE_FAO_PART_OI.format(d=ds), timeout=15)
            print(f"     {ds}: [{r.status_code}] len={len(r.text)}")
        except Exception as exc:  # noqa: BLE001
            print(f"     {ds}: {type(exc).__name__}: {exc}")


def note_ruled_out() -> None:
    print("\n=== Ruled out / decided ===")
    print("  Dhan: GIFT Nifty is index id 5024 but marketfeed/ltp → 401 (paid Data API).")
    print("  Nuvama: no arbitrary quote endpoint wired.")


async def main() -> None:
    await probe_upstox()
    probe_fii()
    note_ruled_out()
    print("\n--- done. Update signals_stories.md §S5.2a 'Confirmed sources:' with this output ---")


if __name__ == "__main__":
    asyncio.run(main())
