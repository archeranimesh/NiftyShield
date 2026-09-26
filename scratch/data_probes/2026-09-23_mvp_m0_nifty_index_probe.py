"""Scratch: probe NSE index-close bhavcopy for NIFTY 50 (M0 open point 1).

Candidate: NSE's daily "indices close" archive file, one CSV per trading
day (not zipped, unlike the CM/F&O bhavcopy), same nsearchives.nseindia.com
host and session/cookie pattern already used for CM equity bhavcopy in
scratch/2026-09-23_mvp_m0_data_source_probe.py and F&O ingest in
src/backtest/bhavcopy_ingest.py.

Fetches NIFTY 50 close for a few spot-check dates and prints them for
manual cross-check against an independently known value before trusting
this as M0's index data source.

Run: python scratch/2026-09-23_mvp_m0_nifty_index_probe.py
"""

from __future__ import annotations

import io
from datetime import date, timedelta

import requests

INDEX_NAME_NSE = "Nifty 50"

_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://www.nseindia.com/",
}


def fetch_nse_index_close(session: requests.Session, trade_date: date) -> float | None:
    """One NSE 'indices close' CSV per day — plain CSV, not zipped."""
    filename = f"ind_close_all_{trade_date:%d%m%Y}.csv"
    url = f"https://nsearchives.nseindia.com/content/indices/{filename}"
    resp = session.get(url, timeout=15)
    if resp.status_code != 200:
        return None
    text = io.StringIO(resp.text)
    header = text.readline().strip().split(",")
    name_idx = header.index("Index Name")
    close_idx = header.index("Closing Index Value")
    for line in text:
        row = line.strip().split(",")
        if row[name_idx].strip().strip('"') == INDEX_NAME_NSE:
            return float(row[close_idx])
    return None


def main() -> None:
    session = requests.Session()
    session.headers.update(_NSE_HEADERS)
    session.get("https://www.nseindia.com", timeout=10)  # warm cookies

    reco_date = date(2026, 6, 11)
    today = date.today()
    spot_check_dates = [
        reco_date + timedelta(days=1),
        reco_date + timedelta(days=30),
        today - timedelta(days=1),
    ]

    print("=== NSE index-close bhavcopy spot-check: NIFTY 50 ===")
    for d in spot_check_dates:
        try:
            close = fetch_nse_index_close(session, d)
        except Exception as exc:  # noqa: BLE001 — scratch probe, just report
            close = f"ERROR: {exc}"
        print(f"  {d}  NIFTY 50 close={close}")


if __name__ == "__main__":
    main()
