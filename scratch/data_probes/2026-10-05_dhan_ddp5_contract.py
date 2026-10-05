"""DDP-5: scan stored Upstox intraday chain for Dec 2026 / Jun 2027 delta state. Read-only; writes a per-(file,expiry) summary CSV."""

import glob
import re
import sys

import pandas as pd
import pyarrow.parquet as pq

TARGETS = {"2026-12-29", "2027-06-29"}
rows = []
files = sorted(glob.glob("data/historical/option_chain/intraday/2026/*/*/upstox_*.parquet"))
for f in files:
    m = re.search(r"/2026/(\d\d)/(\d\d)/upstox_(\d{4})(?:_(\w+))?\.parquet", f)
    t = pq.read_table(
        f, columns=["snapshot_ts", "expiry_date", "strike", "option_type", "delta", "ltp"]
    ).to_pandas()
    t = t[t.expiry_date.astype(str).isin(TARGETS)]
    if t.empty:
        continue
    for exp, g in t.groupby(t.expiry_date.astype(str)):
        d = g.delta.astype(float).abs()
        k = g.strike.astype(float)
        rows.append(
            dict(
                date=f"2026-{m[1]}-{m[2]}",
                hhmm=m[3],
                bucket=m[4],
                expiry=exp,
                ts=g.snapshot_ts.iloc[0],
                n=len(g),
                nz=int((d > 0).sum()),
                nz_lt1=int(((d > 0) & (d < 1)).sum()),
                kmin=k.min(),
                kmax=k.max(),
                spot_free=1,
            )
        )
out = pd.DataFrame(rows)
out.to_csv(sys.argv[1], index=False)
print(len(files), "files;", len(out), "rows")
