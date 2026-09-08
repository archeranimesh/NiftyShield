#!/usr/bin/env python3
"""BUG-040 probe — read-only. What OHLC does the signals pipeline actually need,
and where do we get NIFTY's previous-session daily candle from?

`src/signals/snapshot.py::_fetch_prev_ohlc` needs exactly three numbers:
prev-session close, high, low for NSE_INDEX|Nifty 50. It currently calls
`broker.get_ohlc([NIFTY_KEY], "1d")` and reads `["ohlc"]["close"|"high"|"low"]`
— a response shape Upstox v3 does not return.

This script hits every candidate endpoint directly (no src client, no DB, no
writes) and prints what each one gives, so we can pick the fix's data source.

Run:  .venv/bin/python scratch/2026-09-08_signals_ohlc_probe.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from src.config import settings  # noqa: E402

NIFTY_KEY = "NSE_INDEX|Nifty 50"
ENC = quote(NIFTY_KEY, safe="")
TOKEN = settings.upstox_analytics_token or ""
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}


def _get(url: str, params: dict | None = None) -> dict:
    r = requests.get(url, params=params or {}, headers=HEADERS, timeout=10)
    print(f"  GET {r.url}\n  -> {r.status_code}")
    try:
        return r.json()
    except ValueError:
        return {"_raw": r.text[:400]}


def probe_market_quote_ohlc() -> None:
    """v3 /market-quote/ohlc — what the code calls today."""
    for interval in ("1d", "I1"):
        print(f"\n[market-quote/ohlc  interval={interval}]")
        data = _get(
            "https://api.upstox.com/v3/market-quote/ohlc",
            {"instrument_key": NIFTY_KEY, "interval": interval},
        )
        body = data.get("data") or {}
        val = next(iter(body.values()), {}) if body else {}
        print("  keys:", sorted(val.keys()))
        print("  prev_ohlc:", val.get("prev_ohlc"))
        print("  live_ohlc:", val.get("live_ohlc"))


def probe_historical_v3() -> None:
    """v3 /historical-candle/{key}/days/1/{to}/{from} — most-recent daily candles."""
    to_d = date.today()
    from_d = to_d - timedelta(days=10)
    print(f"\n[v3 historical-candle days/1  {from_d} .. {to_d}]")
    data = _get(
        f"https://api.upstox.com/v3/historical-candle/{ENC}/days/1/{to_d.isoformat()}/{from_d.isoformat()}"
    )
    candles = (data.get("data") or {}).get("candles", [])
    for c in candles[:3]:
        print("  ", c)
    _report_prev(candles)


def probe_historical_v2() -> None:
    """v2 /historical-candle/{key}/day/{to}?from_date=  — the pattern src/backtest/vix_ingest.py already uses."""
    to_d = date.today()
    from_d = to_d - timedelta(days=10)
    print(f"\n[v2 historical-candle day  {from_d} .. {to_d}]  (vix_ingest.py's pattern)")
    data = _get(
        f"https://api.upstox.com/v2/historical-candle/{ENC}/day/{to_d.isoformat()}",
        {"from_date": from_d.isoformat()},
    )
    candles = (data.get("data") or {}).get("candles", [])
    for c in candles[:3]:
        print("  ", c)
    _report_prev(candles)


def _report_prev(candles: list) -> None:
    """candles: [[ts, open, high, low, close, volume, oi], ...] most-recent first."""
    if not candles:
        print("  !! no candles")
        return
    ts, _open, high, low, close, *_ = candles[0]
    print(f"  => prev session {ts[:10]}:  close={close}  high={high}  low={low}")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("UPSTOX_ANALYTICS_TOKEN not set")
    print("=" * 70)
    print("BUG-040 OHLC source probe —", date.today().isoformat())
    print("=" * 70)
    probe_market_quote_ohlc()
    probe_historical_v3()
    probe_historical_v2()
    print(
        "\nSurvey — how the repo already sources daily index OHLC:\n"
        "  src/backtest/vix_ingest.py:92,156  -> v2 /historical-candle/{key}/day/{to}?from_date=\n"
        "    parses candles as [ts, o, h, l, c, vol, oi]; used for India VIX daily close.\n"
        "  scripts/dev/verify_analytics.py:239 -> v3 /historical-candle/{key}/days/1/{to}/{from}\n"
        "  No strategy pulls NIFTY prev-day OHLC from /market-quote/ohlc — that endpoint is\n"
        "  LTP/live-candle only. `get_ohlc` in upstox_market.py has exactly one caller:\n"
        "  src/signals/snapshot.py::_fetch_prev_ohlc.\n"
    )
