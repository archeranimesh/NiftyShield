"""Scratch: compare candidate data sources for M0 (equity daily-close ingest).

Fetches UNIPARTS (NSE) daily closes from the DSIJ reco date (2026-06-11) to
today via two candidates:
  1. Yahoo Finance chart API (UNIPARTS.NS) — single HTTP call, full range.
  2. NSE CM bhavcopy (UDiFF) — one file per trading day, authoritative NSE
     close, same download pattern already used for F&O in
     src/backtest/bhavcopy_ingest.py.

Prints both series side by side for a handful of spot-check dates so we can
decide which source M0 should actually ingest from. Not wired into any
pipeline — throwaway comparison only.

Run: python scratch/2026-09-23_mvp_m0_data_source_probe.py
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timedelta

import requests

SYMBOL_YAHOO = "UNIPARTS.NS"
SYMBOL_NSE = "UNIPARTS"
RECO_DATE = date(2026, 6, 11)
TODAY = date.today()

_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://www.nseindia.com/",
}


def fetch_yahoo_series() -> dict[date, float]:
    """One HTTP call, full date range, no auth needed."""
    period1 = int(datetime(RECO_DATE.year, RECO_DATE.month, RECO_DATE.day).timestamp())
    period2 = int(datetime(TODAY.year, TODAY.month, TODAY.day).timestamp()) + 86400
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL_YAHOO}"
        f"?period1={period1}&period2={period2}&interval=1d"
    )
    resp = requests.get(url, headers={"User-Agent": _NSE_HEADERS["User-Agent"]}, timeout=15)
    resp.raise_for_status()
    payload = resp.json()
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    series: dict[date, float] = {}
    for ts, close in zip(timestamps, closes, strict=True):
        if close is None:
            continue
        d = datetime.utcfromtimestamp(ts).date()
        series[d] = round(close, 2)
    return series


def fetch_nse_cm_bhavcopy_close(trade_date: date) -> float | None:
    """One NSE CM UDiFF bhavcopy zip per day. Authoritative but N calls."""
    session = requests.Session()
    session.headers.update(_NSE_HEADERS)
    session.get("https://www.nseindia.com", timeout=10)  # warm cookies, mirrors F&O ingest

    filename = f"BhavCopy_NSE_CM_0_0_0_{trade_date:%Y%m%d}_F_0000.csv.zip"
    url = f"https://nsearchives.nseindia.com/content/cm/{filename}"
    resp = session.get(url, timeout=15)
    if resp.status_code != 200:
        return None
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            text = io.TextIOWrapper(f, encoding="utf-8")
            header = text.readline().strip().split(",")
            sym_idx = header.index("TckrSymb")
            close_idx = header.index("ClsPric")
            for line in text:
                row = line.strip().split(",")
                if row[sym_idx] == SYMBOL_NSE:
                    return float(row[close_idx])
    return None


def main() -> None:
    print(f"=== Yahoo Finance: {SYMBOL_YAHOO} {RECO_DATE} -> {TODAY} ===")
    try:
        yahoo_series = fetch_yahoo_series()
    except Exception as exc:  # noqa: BLE001 — scratch probe, don't let this block the NSE check
        print(f"  ERROR: {exc}")
        yahoo_series = {}
    else:
        print(f"{len(yahoo_series)} daily closes fetched in 1 call.")
        for d in sorted(yahoo_series)[:3] + sorted(yahoo_series)[-3:]:
            print(f"  {d}  close={yahoo_series[d]}")

    print("\n=== NSE CM bhavcopy spot-check (a few dates) ===")
    spot_check_dates = [
        RECO_DATE + timedelta(days=1),  # next trading day, entry-rule check
        RECO_DATE + timedelta(days=30),
        TODAY - timedelta(days=1),
    ]
    for d in spot_check_dates:
        try:
            nse_close = fetch_nse_cm_bhavcopy_close(d)
        except Exception as exc:  # noqa: BLE001 — scratch probe, just report
            nse_close = f"ERROR: {exc}"
        yahoo_close = yahoo_series.get(d, "no Yahoo row for this date")
        print(f"  {d}  NSE={nse_close}  Yahoo={yahoo_close}")


if __name__ == "__main__":
    main()
