# chain-data — Parquet Schema

All chain-data files are Parquet, written via `pyarrow`. No SQLite tables. DuckDB glob-compatible
partition paths — do not change the directory structure without updating `chain_reader.py`.

---

## EOD chain snapshots (task CD1)

**Path:** `data/offline/chain_snapshots/{year}/{month}/upstox_{date}.parquet`

Example: `data/offline/chain_snapshots/2026/05/upstox_2026-05-27.parquet`

One file per trading day. Re-running the cron on the same date **overwrites** the file (idempotent).
Each file contains all strikes for all three tracked expiries captured at a single point-in-time.

```
Column        PyArrow type              Notes
-----------   -----------------------   --------------------------------------------------
snapshot_ts   pa.timestamp('us', tz)    UTC; always 09:30 IST on capture day (standardised)
underlying    pa.string()               'NIFTY_50'
expiry_date   pa.date32()               Contract expiry date
strike        pa.decimal128(18, 6)      Strike price; Dhan keys are "25650.000000" — strip zeros
option_type   pa.string()               'CE' or 'PE'
spot          pa.decimal128(18, 6)      Underlying last price at time of capture
ltp           pa.decimal128(18, 6)      Option last traded price
bid           pa.decimal128(18, 6)      Top-of-book bid
ask           pa.decimal128(18, 6)      Top-of-book ask
oi            pa.int64()                Open interest (contracts)
volume        pa.int64()                Volume (contracts, session)
iv            pa.decimal128(18, 6)      Implied volatility (as reported by Upstox, annualised %)
delta         pa.decimal128(18, 6)      Delta (CE: 0–1, PE: −1–0)
gamma         pa.decimal128(18, 6)      Gamma per point
theta         pa.decimal128(18, 6)      Theta per day (negative for long options)
vega          pa.decimal128(18, 6)      Vega per 1% IV move
```

**Primary key (logical):** `(underlying, expiry_date, strike, option_type, snapshot_ts)` — enforced
by the overwrite-on-same-date strategy; duplicates cannot exist within a single daily file.

**DuckDB scan example:**
```python
import duckdb
df = duckdb.query("""
    SELECT * FROM read_parquet(
        'data/offline/chain_snapshots/2026/*/*.parquet',
        hive_partitioning=false
    )
    WHERE expiry_date = '2026-05-29'
      AND ABS(delta) BETWEEN 0.20 AND 0.30
""").df()
```

---

## Intraday 5-min snapshots (task CD2)

**Path:** `data/offline/chain_snapshots_5min/{year}/{month}/{day}/upstox_{HHMM}.parquet`

Example: `data/offline/chain_snapshots_5min/2026/05/27/upstox_1430.parquet`

One file per 5-minute interval. `HHMM` is IST 24-hour. Re-running within the same 5-min window
overwrites the file. Schema is **identical** to EOD snapshots above — `snapshot_ts` carries
the full intraday UTC timestamp.

**Volume estimate:** ~67 K rows/day (78 intervals × ~3 expiries × ~288 strikes × 2 sides).
~16 M rows/year. Estimated 2–3 GB/year compressed Parquet.

**DuckDB scan example (all intraday snapshots for one day):**
```python
df = duckdb.query("""
    SELECT * FROM read_parquet(
        'data/offline/chain_snapshots_5min/2026/05/27/*.parquet'
    )
    WHERE strike = 24500 AND option_type = 'PE'
    ORDER BY snapshot_ts
""").df()
```

---

## Notes

- `iv` is as-reported by Upstox (their proprietary surface). Not Black-Scholes reconstructed.
  The BS-vs-Upstox drift is what task 1.6a measures — do not "correct" the value here.
- `theta` is per-day (not per-year). Matches Upstox convention. Verify on first capture.
- `bid`/`ask` will be `0.0` outside market hours if Upstox returns zero. Filter `bid > 0`
  in analysis queries.
- `volume` resets to zero at market open. Intraday snapshots show cumulative session volume
  up to the capture time, not volume in the 5-min window. Do not treat as bar volume.
- All `Decimal` fields are written as `pa.decimal128(18, 6)` — 18 total digits, 6 decimal places.
  Read back with `Decimal(str(row.strike))` if converting to Python Decimal for order logic.
