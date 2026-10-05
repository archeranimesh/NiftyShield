"""Scratch-only helper — not for src/ or scripts/dev/ import. Graduate (with tests) before reuse there.

Extracted per SCRATCH.md's convergence rule: the Dhan Data API request plumbing (auth headers, one
paced call with PASS/FAIL result, rolling-option body) is now needed by a third scratch script
(2026-09-22 chain probe, 2026-10-05 api probe, 2026-10-05 ddp3 coverage). The two earlier scripts keep
their own copies; this module is for new scripts only.
"""

from __future__ import annotations

import time
from datetime import date
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
