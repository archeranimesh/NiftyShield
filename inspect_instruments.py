"""Scratch: inspect NSE.json.gz for NIFTY option instrument fields,
looking for any weekly/monthly/quarterly identifier instead of DTE-band guessing."""

import gzip
import json
from collections import defaultdict

path = "data/instruments/NSE.json.gz"
with gzip.open(path, "rt") as f:
    data = json.load(f)

print(f"total instruments: {len(data)}")
print("sample keys of first record:", list(data[0].keys()))

# Filter NIFTY index options
nifty_opts = [
    d
    for d in data
    if d.get("segment") == "NSE_FO"
    and d.get("instrument_type") in ("CE", "PE")
    and d.get("underlying_symbol", "").upper() == "NIFTY"
]
print(f"\nNIFTY NSE_FO CE/PE instruments: {len(nifty_opts)}")

# Print all unique keys across nifty option records
all_keys = set()
for d in nifty_opts:
    all_keys.update(d.keys())
print("\nall unique keys across NIFTY option records:", sorted(all_keys))

# Group distinct expiries and dump one full record per expiry to see if any
# field hints at weekly/monthly/quarterly/yearly cadence.
by_expiry = defaultdict(list)
for d in nifty_opts:
    by_expiry[d.get("expiry")].append(d)

expiries = sorted(by_expiry.keys())
print(f"\ndistinct expiries: {len(expiries)}")
print("last 10 expiries (likely include yearly/quarterly far-dated ones):")
for e in expiries[-10:]:
    sample = by_expiry[e][0]
    print(f"  expiry={e} sample_record={json.dumps(sample, indent=None)}")

# Also print the very first few expiries (weeklies) for comparison
print("\nfirst 5 expiries:")
for e in expiries[:5]:
    sample = by_expiry[e][0]
    print(f"  expiry={e} sample_record={json.dumps(sample, indent=None)}")

# Look for any field name containing weekly/monthly/quarter/year/freq/cadence
suspect_fields = [
    k
    for k in all_keys
    if any(
        t in k.lower()
        for t in ["week", "month", "quarter", "year", "freq", "cadence", "series", "contract"]
    )
]
print("\nfields with suspicious naming:", suspect_fields)
for f in suspect_fields:
    vals = set(str(d.get(f)) for d in nifty_opts[:2000])
    print(f"  {f}: sample distinct values -> {list(vals)[:10]}")
