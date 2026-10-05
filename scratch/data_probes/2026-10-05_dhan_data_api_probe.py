"""Probe the paid Dhan Data API: is the subscription live, and which feature families respond.

Scratch exploratory script (story: docs/plan/dhan-data-poc, DDP-1/DDP-3 groundwork). Read-only,
no orders. Credentials come from .env via src.auth.dhan_verify; the token is never printed.

Usage:
    PYTHONPATH=. python scratch/data_probes/2026-10-05_dhan_data_api_probe.py [--skip depth,chain]

Probes (each prints status + response shape, then a PASS/FAIL table at the end):
    profile      GET  /profile                  -> dataPlan / dataValidity (subscription flag)
    ltp/ohlc/quote  POST /marketfeed/*          -> live snapshot for NIFTY index + one equity
    daily        POST /charts/historical        -> daily candles
    intraday     POST /charts/intraday          -> minute candles, last few days
    expirylist/chain  POST /optionchain[/expirylist] -> live chain with Greeks
    rolling      POST /charts/rollingoption     -> expired options by ATM offset (the POC dataset)
    depth        POST /charts/rollingoption     -> how far back does expired-option history go
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from typing import Any

import requests

from src.auth.dhan_verify import DHAN_API_BASE, _build_headers, load_dhan_credentials

NIFTY_ID = 13  # NIFTY 50 index security id, segment IDX_I (confirmed by 2026-09-22 probe)
TCS_ID = 11536  # NSE_EQ sample equity
REQUEST_GAP_S = 1.0  # Data API allows ~5 req/s; option chain alone is 1 req / 3 s
CHAIN_GAP_S = 3.2

RESULTS: list[tuple[str, str, str]] = []  # (probe, PASS/FAIL, note)


def call(
    name: str,
    method: str,
    path: str,
    headers: dict[str, str],
    body: dict[str, Any] | None = None,
    gap: float = REQUEST_GAP_S,
) -> Any | None:
    """Fire one request, print status + truncated body, record PASS/FAIL, return parsed JSON."""
    time.sleep(gap)
    url = f"{DHAN_API_BASE}{path}"
    print(f"\n=== {name}: {method} {path}")
    try:
        resp = requests.request(method, url, headers=headers, json=body, timeout=30)
    except requests.RequestException as exc:
        print(f"  network error: {exc}")
        RESULTS.append((name, "FAIL", f"network: {type(exc).__name__}"))
        return None
    try:
        data = resp.json()
    except ValueError:
        data = None
    ok = resp.status_code == 200 and not _is_error_body(data)
    print(f"  HTTP {resp.status_code}  ->  {'PASS' if ok else 'FAIL'}")
    if not ok:
        note = _error_note(resp.status_code, data, resp.text)
        print(f"  {note}")
        RESULTS.append((name, "FAIL", note))
        return None
    RESULTS.append((name, "PASS", ""))
    return data


def _is_error_body(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    return data.get("status") == "failed" or "errorCode" in data


def _error_note(status: int, data: Any, text: str) -> str:
    if isinstance(data, dict):
        code = data.get("errorCode") or data.get("data", {}) or ""
        msg = data.get("errorMessage") or data.get("remarks") or ""
        return f"errorCode={code} message={msg}"[:300]
    return f"HTTP {status}: {text[:200]}"


def show(label: str, obj: Any, limit: int = 600) -> None:
    print(f"  {label}: {json.dumps(obj, default=str)[:limit]}")


def series_summary(data: dict[str, Any]) -> None:
    """Summarise a columnar candle response ({open:[...], timestamp:[...], ...})."""
    cols = {k: v for k, v in data.items() if isinstance(v, list)}
    print(f"  columns: {sorted(cols)}")
    if not cols:
        show("raw", data)
        return
    n = max(len(v) for v in cols.values())
    print(f"  rows: {n}")
    ts = cols.get("timestamp") or cols.get("start_Time") or []
    if ts:
        print(f"  first/last timestamp (epoch): {ts[0]} .. {ts[-1]}")
    for k, v in cols.items():
        if k != "timestamp" and v:
            print(f"  {k}: first={v[0]} last={v[-1]} nulls={sum(1 for x in v if x is None)}")


def probe_profile(h: dict[str, str]) -> None:
    data = call("profile", "GET", "/profile", h)
    if not data:
        return
    # Print everything except identifiers/tokens; dataPlan + dataValidity are the point.
    safe = {k: v for k, v in data.items() if k.lower() not in {"dhanclientid", "tokenvalidity"}}
    show("profile (ids stripped)", safe)
    plan = str(data.get("dataPlan", "")).lower()
    RESULTS[-1] = (
        "profile",
        "PASS",
        f"dataPlan={data.get('dataPlan')} validity={data.get('dataValidity')}",
    )
    if plan and plan != "active":
        print("  WARNING: dataPlan is not Active; paid endpoints will likely 401/DH-902.")


def probe_marketfeed(h: dict[str, str]) -> None:
    body = {"IDX_I": [NIFTY_ID], "NSE_EQ": [TCS_ID]}
    for kind in ("ltp", "ohlc", "quote"):
        data = call(kind, "POST", f"/marketfeed/{kind}", h, body)
        if data:
            show("NIFTY idx", data.get("data", {}).get("IDX_I", {}).get(str(NIFTY_ID)))
            show("TCS", data.get("data", {}).get("NSE_EQ", {}).get(str(TCS_ID)))


def probe_historical(h: dict[str, str]) -> None:
    today = date.today()
    daily = {
        "securityId": str(NIFTY_ID),
        "exchangeSegment": "IDX_I",
        "instrument": "INDEX",
        "expiryCode": 0,
        "fromDate": (today - timedelta(days=30)).isoformat(),
        "toDate": today.isoformat(),
    }
    data = call("daily", "POST", "/charts/historical", h, daily)
    if data:
        series_summary(data)
    intraday = {
        "securityId": str(NIFTY_ID),
        "exchangeSegment": "IDX_I",
        "instrument": "INDEX",
        "interval": "5",
        "fromDate": f"{(today - timedelta(days=4)).isoformat()} 09:15:00",
        "toDate": f"{today.isoformat()} 15:30:00",
    }
    data = call("intraday", "POST", "/charts/intraday", h, intraday)
    if data:
        series_summary(data)


def probe_chain(h: dict[str, str]) -> None:
    base = {"UnderlyingScrip": NIFTY_ID, "UnderlyingSeg": "IDX_I"}
    data = call("expirylist", "POST", "/optionchain/expirylist", h, base, gap=CHAIN_GAP_S)
    expiries = (data or {}).get("data") or []
    if not expiries:
        return
    print(f"  expiries ({len(expiries)}): {expiries[:6]} ... {expiries[-3:]}")
    far = expiries[-1]  # farthest listed expiry: check whether Greeks are populated there too
    for label, expiry in (("chain-near", expiries[0]), ("chain-far", far)):
        chain = call(label, "POST", "/optionchain", h, {**base, "Expiry": expiry}, gap=CHAIN_GAP_S)
        oc = ((chain or {}).get("data") or {}).get("oc") or {}
        if not oc:
            continue
        nonzero = sum(
            1 for r in oc.values() if (r.get("ce", {}).get("greeks", {}).get("delta") or 0)
        )
        print(f"  {expiry}: strikes={len(oc)} strikes_with_nonzero_CE_delta={nonzero}")
        k, row = next(iter(oc.items()))
        show(f"sample strike {k} CE fields", sorted(row.get("ce", {})))
        show("CE greeks fields", sorted(row.get("ce", {}).get("greeks", {})))


def rolling_body(strike: str, opt: str, flag: str, start: date, end: date) -> dict[str, Any]:
    return {
        "exchangeSegment": "NSE_FNO",
        "interval": "60",
        "securityId": NIFTY_ID,
        "instrument": "OPTIDX",
        "expiryFlag": flag,
        "expiryCode": 1,
        "strike": strike,
        "drvOptionType": opt,
        "requiredData": ["open", "high", "low", "close", "iv", "volume", "strike", "oi", "spot"],
        "fromDate": start.isoformat(),
        "toDate": end.isoformat(),
    }


def probe_rolling(h: dict[str, str]) -> None:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=4)
    cases = [
        ("ATM", "CALL", "WEEK"),
        ("ATM", "PUT", "MONTH"),
        ("ATM+10", "CALL", "MONTH"),
        ("ATM-10", "PUT", "MONTH"),
    ]
    for strike, opt, flag in cases:
        name = f"rolling {strike} {opt} {flag}"
        data = call(
            name, "POST", "/charts/rollingoption", h, rolling_body(strike, opt, flag, start, end)
        )
        side = "ce" if opt == "CALL" else "pe"
        block = ((data or {}).get("data") or {}).get(side)
        if block:
            series_summary(block)


def probe_depth(h: dict[str, str]) -> None:
    """Find the earliest date with expired-option rows: 5-day windows at increasing age."""
    today = date.today()
    for days_back in (60, 180, 365, 730, 1095, 1825):
        end = today - timedelta(days=days_back)
        start = end - timedelta(days=4)
        name = f"depth -{days_back}d"
        data = call(
            name,
            "POST",
            "/charts/rollingoption",
            h,
            rolling_body("ATM", "CALL", "MONTH", start, end),
        )
        block = ((data or {}).get("data") or {}).get("ce") or {}
        rows = max((len(v) for v in block.values() if isinstance(v, list)), default=0)
        print(f"  window {start}..{end}: rows={rows}")
        if data and not rows:
            RESULTS[-1] = (name, "FAIL", "200 OK but empty (no history this far back?)")


PROBES = {
    "profile": probe_profile,
    "marketfeed": probe_marketfeed,
    "historical": probe_historical,
    "chain": probe_chain,
    "rolling": probe_rolling,
    "depth": probe_depth,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip", default="", help=f"comma list from: {','.join(PROBES)}")
    skip = {s.strip() for s in parser.parse_args().skip.split(",") if s.strip()}

    client_id, token = load_dhan_credentials()
    headers = {**_build_headers(token), "client-id": client_id, "Accept": "application/json"}

    for name, fn in PROBES.items():
        if name not in skip:
            fn(headers)

    print("\n" + "=" * 60 + "\nSUMMARY")
    for probe, status, note in RESULTS:
        print(f"  {status:4}  {probe:28} {note}")
    return 0 if all(s == "PASS" for _, s, _ in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
