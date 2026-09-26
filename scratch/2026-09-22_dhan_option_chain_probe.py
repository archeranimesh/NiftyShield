"""Probe DhanHQ v2 Option Chain API: what strikes/Greeks/fields does it return for NIFTY.

Scratch exploratory script — not wired into src/. Uses existing DHAN_CLIENT_ID /
DHAN_ACCESS_TOKEN from .env via src.auth.dhan_verify.load_dhan_credentials.
"""

from __future__ import annotations

import csv
import io
import json
import time

import requests

from src.auth.dhan_verify import _build_headers, load_dhan_credentials

SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
OPTIONCHAIN_URL = "https://api.dhan.co/v2/optionchain"
EXPIRYLIST_URL = "https://api.dhan.co/v2/optionchain/expirylist"


def find_nifty_index_security_id() -> tuple[int, str]:
    """Look up NIFTY index's security id + segment from Dhan's scrip master CSV."""
    resp = requests.get(SCRIP_MASTER_URL, timeout=30)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    for row in reader:
        symbol = (row.get("SEM_TRADING_SYMBOL") or "").strip()
        instrument = (row.get("SEM_INSTRUMENT_NAME") or "").strip()
        if symbol == "NIFTY" and instrument == "INDEX":
            return int(row["SEM_SMST_SECURITY_ID"]), row.get("SEM_EXM_EXCH_ID", "")
    raise RuntimeError("NIFTY index row not found in scrip master")


def main() -> None:
    client_id, access_token = load_dhan_credentials()
    headers = _build_headers(access_token)
    headers["client-id"] = client_id

    scrip_id, exch = find_nifty_index_security_id()
    print(f"NIFTY index -> UnderlyingScrip={scrip_id}, exch={exch}")

    expiry_resp = requests.post(
        EXPIRYLIST_URL,
        headers=headers,
        json={"UnderlyingScrip": scrip_id, "UnderlyingSeg": "IDX_I"},
        timeout=15,
    )
    print("expirylist status:", expiry_resp.status_code)
    expiry_data = expiry_resp.json()
    print(json.dumps(expiry_data, indent=2)[:1000])

    expiries = expiry_data.get("data", []) if expiry_data.get("status") != "failed" else []
    if not expiries:
        print("No expiries returned, aborting chain fetch.")
        return
    nearest_expiry = expiries[0]

    time.sleep(3)  # Dhan option chain rate limit: 1 request / 3s

    chain_resp = requests.post(
        OPTIONCHAIN_URL,
        headers=headers,
        json={
            "UnderlyingScrip": scrip_id,
            "UnderlyingSeg": "IDX_I",
            "Expiry": nearest_expiry,
        },
        timeout=15,
    )
    print("optionchain status:", chain_resp.status_code)
    chain_data = chain_resp.json()

    oc = chain_data.get("data", {}).get("oc", {})
    print(f"last_price: {chain_data.get('data', {}).get('last_price')}")
    print(f"strikes returned: {len(oc)}")

    if oc:
        sample_strike, sample = next(iter(oc.items()))
        print(f"\nSample strike {sample_strike}:")
        print(json.dumps(sample, indent=2))

        ce_keys = set(sample.get("ce", {}).keys())
        pe_keys = set(sample.get("pe", {}).keys())
        print(f"\nCE fields: {sorted(ce_keys)}")
        print(f"PE fields: {sorted(pe_keys)}")

        greeks = sample.get("ce", {}).get("greeks", {})
        print(f"\nGreeks available: {sorted(greeks.keys()) if greeks else 'none'}")


if __name__ == "__main__":
    main()
