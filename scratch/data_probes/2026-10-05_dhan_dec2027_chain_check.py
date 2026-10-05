"""DDP-6 follow-up: Dhan live chain for 2027-12-28, CE strikes above spot. Read-only; raw JSON to argv[1] dir."""

import json
import sys

from scratch._lib.dhan_data_api import auth_headers, call

h = auth_headers()
data, err = call(
    "POST",
    "/optionchain",
    h,
    {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I", "Expiry": "2027-12-28"},
    6.0,
)
if err:
    sys.exit(err)
json.dump(data, open(f"{sys.argv[1]}/dhan_chain_2027-12-28.json", "w"))
d = data["data"]
oc, spot = d["oc"], d.get("last_price")
print("strikes", len(oc), "spot", spot)
print("CE above spot (strike, ltp, bid, ask, oi, delta):")
for k in sorted(oc, key=float):
    ce = oc[k].get("ce") or {}
    if float(k) > (spot or 0):
        print(
            int(float(k)),
            ce.get("last_price"),
            ce.get("top_bid_price"),
            ce.get("top_ask_price"),
            ce.get("oi"),
            (ce.get("greeks") or {}).get("delta"),
        )
