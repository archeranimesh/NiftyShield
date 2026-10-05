"""Scratch-only helper — not for src/ or scripts/dev/ import. Graduate (with tests) before reuse there.

Extracted per SCRATCH.md's convergence rule: the Dhan Data API request plumbing (auth headers, one
paced call with PASS/FAIL result, rolling-option body) is now needed by a third scratch script
(2026-09-22 chain probe, 2026-10-05 api probe, 2026-10-05 ddp3 coverage). The two earlier scripts keep
their own copies; this module is for new scripts only. Also holds the inferred-expiry and delta helpers
shared by the ddp4 validation script.
"""

from __future__ import annotations

import math
import time
from datetime import date, timedelta
from typing import Any

import requests

from src.auth.dhan_verify import DHAN_API_BASE, _build_headers, load_dhan_credentials

NIFTY_ID = 13  # NIFTY 50 index security id, segment IDX_I


def auth_headers() -> dict[str, str]:
    """Return request headers from .env credentials; the token is never printed."""
    client_id, token = load_dhan_credentials()
    return {**_build_headers(token), "client-id": client_id, "Accept": "application/json"}


def call(
    method: str, path: str, headers: dict[str, str], body: dict[str, Any] | None, gap: float
) -> tuple[Any | None, str]:
    """Fire one paced request. Returns (parsed JSON or None, short error note or '')."""
    time.sleep(gap)
    try:
        resp = requests.request(
            method, f"{DHAN_API_BASE}{path}", headers=headers, json=body, timeout=30
        )
    except requests.RequestException as exc:
        return None, f"network:{type(exc).__name__}"
    try:
        data = resp.json()
    except ValueError:
        data = None
    failed = isinstance(data, dict) and (data.get("status") == "failed" or "errorCode" in data)
    if resp.status_code != 200 or failed:
        code = data.get("errorCode") if isinstance(data, dict) else ""
        msg = (data.get("errorMessage") if isinstance(data, dict) else resp.text[:120]) or ""
        return None, f"HTTP{resp.status_code} {code} {str(msg)[:100]}"
    return data, ""


def rolling_body(
    strike: str, opt: str, flag: str, code: int, interval: str, start: date, end: date
) -> dict[str, Any]:
    """Body for POST /charts/rollingoption on NIFTY. strike like 'ATM', 'ATM+10'; opt CALL|PUT."""
    return {
        "exchangeSegment": "NSE_FNO",
        "interval": interval,
        "securityId": NIFTY_ID,
        "instrument": "OPTIDX",
        "expiryFlag": flag,
        "expiryCode": code,
        "strike": strike,
        "drvOptionType": opt,
        "requiredData": ["open", "high", "low", "close", "iv", "volume", "strike", "oi", "spot"],
        "fromDate": start.isoformat(),
        "toDate": end.isoformat(),
    }


# --- expiry and delta helpers (inference: Tuesday expiries per REFERENCES.md, r = 6.5%) ---
RATE = 0.065


def last_tuesday(year: int, month: int) -> date:
    """Last Tuesday of the month (NIFTY monthly expiry since April 2026)."""
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - 1) % 7)


def expiry_for(d: date, flag: str, code: int) -> date:
    """Expiry that rolling expiryCode 1/2/3 (near/next/far, inferred) points at on date d."""
    if flag == "WEEK":
        first = d + timedelta(days=(1 - d.weekday()) % 7)
        return first + timedelta(weeks=code - 1)
    y, m = d.year, d.month
    if last_tuesday(y, m) < d:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    for _ in range(code - 1):
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return last_tuesday(y, m)


def bs_delta(
    spot: float, strike: float, t_years: float, iv_pct: float, is_call: bool
) -> float | None:
    """Black-Scholes delta from a stored IV in percent; None when inputs are unusable."""
    if t_years <= 0 or iv_pct <= 0 or spot <= 0:
        return None
    s = iv_pct / 100.0
    d1 = (math.log(spot / strike) + (RATE + s * s / 2) * t_years) / (s * math.sqrt(t_years))
    nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    return nd1 if is_call else nd1 - 1
