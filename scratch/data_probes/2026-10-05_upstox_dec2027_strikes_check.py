"""DDP-6 follow-up: which Dec 2027 strikes does Upstox list, and are CE strikes at 0.15-0.25 delta present? Read-only; raw JSON to argv[1] dir."""

import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()
H = {
    "Accept": "application/json",
    "Authorization": f"Bearer {os.environ['UPSTOX_ANALYTICS_TOKEN']}",
}
EXP = "2027-12-28"
r = requests.get(
    "https://api.upstox.com/v2/option/chain",
    headers=H,
    params={"instrument_key": "NSE_INDEX|Nifty 50", "expiry_date": EXP},
    timeout=30,
)
if r.status_code != 200:
    sys.exit(f"HTTP {r.status_code} {r.text[:200]}")
rows = r.json()["data"]
json.dump(rows, open(f"{sys.argv[1]}/upstox_chain_{EXP}.json", "w"))
spot = rows[0].get("underlying_spot_price") if rows else None
print("expiry", EXP, "strikes", len(rows), "spot", spot)
for side in ("call_options", "put_options"):
    ks, nz, two = [], 0, 0
    for s in rows:
        o = s.get(side) or {}
        d = abs((o.get("option_greeks") or {}).get("delta") or 0)
        m = o.get("market_data") or {}
        nz += 0 < d < 1
        two += (m.get("bid_price") or 0) > 0 and (m.get("ask_price") or 0) > 0
        ks.append(s["strike_price"])
    print(side, "nonzero-delta", nz, "two-sided", two)
print("strike list", sorted(ks))
print("CE strikes above spot (strike, ltp, bid, ask, oi, delta):")
for s in sorted(rows, key=lambda x: x["strike_price"]):
    if spot and s["strike_price"] > spot:
        o = s.get("call_options") or {}
        m, g = o.get("market_data") or {}, o.get("option_greeks") or {}
        print(
            s["strike_price"],
            m.get("ltp"),
            m.get("bid_price"),
            m.get("ask_price"),
            m.get("oi"),
            g.get("delta"),
        )
