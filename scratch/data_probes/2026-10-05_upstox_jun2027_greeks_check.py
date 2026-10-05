"""DDP-5 follow-up: one live Upstox chain call per expiry to see whether Jun 2027 Greeks are still zero. Read-only; raw JSON to argv[1] dir."""

import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()
H = {
    "Accept": "application/json",
    "Authorization": f"Bearer {os.environ['UPSTOX_ANALYTICS_TOKEN']}",
}
for exp in ["2027-06-29", "2026-12-29"]:
    r = requests.get(
        "https://api.upstox.com/v2/option/chain",
        headers=H,
        params={"instrument_key": "NSE_INDEX|Nifty 50", "expiry_date": exp},
        timeout=30,
    )
    if r.status_code != 200:
        print(exp, "HTTP", r.status_code, r.text[:200])
        continue
    rows = r.json()["data"]
    json.dump(rows, open(f"{sys.argv[1]}/upstox_chain_{exp}.json", "w"))
    n = nz = two = 0
    ks = []
    for s in rows:
        for side in ("call_options", "put_options"):
            o = s.get(side) or {}
            g = o.get("option_greeks") or {}
            m = o.get("market_data") or {}
            n += 1
            d = abs(g.get("delta") or 0)
            if 0 < d < 1:
                nz += 1
                ks.append(s["strike_price"])
            if (m.get("bid_price") or 0) > 0 and (m.get("ask_price") or 0) > 0:
                two += 1
    print(
        exp,
        "strikes",
        len(rows),
        "rows",
        n,
        "0<|delta|<1",
        nz,
        "two-sided",
        two,
        "spot",
        rows[0].get("underlying_spot_price"),
        "nz strike range",
        (min(ks), max(ks)) if ks else None,
    )
    time.sleep(4)
