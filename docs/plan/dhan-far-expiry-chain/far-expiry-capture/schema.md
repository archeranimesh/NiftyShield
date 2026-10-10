# Far-Expiry Capture — schema

Decided in FC-1 (`DECISIONS.md`, "Far-expiry chain capture storage: SQLite, not `ChainWriter` Parquet, 2026-10-10"). The table is created in FC-2; add its `DB_REGISTRY.md` row in that commit. Use the
`src/db.py` context manager and the additive-migration pattern the other stores use; do not invent a new one.

## `far_expiry_chain_snapshots`

| Column | Type | Notes |
|---|---|---|
| `snapshot_date` | `TEXT NOT NULL` | IST trading date, `YYYY-MM-DD` |
| `captured_at` | `TEXT NOT NULL` | UTC ISO timestamp of the fetch; this is the `delta_asof` source for the last-known-delta policy |
| `underlying` | `TEXT NOT NULL` | e.g. `NIFTY_50` |
| `expiry` | `TEXT NOT NULL` | `YYYY-MM-DD` |
| `strike` | `TEXT NOT NULL` | `Decimal` |
| `option_type` | `TEXT NOT NULL` | `CE` or `PE` |
| `source` | `TEXT NOT NULL` | `dhan` or `upstox` |
| `underlying_spot` | `TEXT NULL` | `Decimal` |
| `ltp`, `bid`, `ask` | `TEXT NOT NULL` | `Decimal`; a missing price is `0` (matches `OptionLeg`) |
| `oi`, `volume` | `INTEGER NOT NULL` | |
| `iv`, `delta`, `gamma`, `theta`, `vega` | `TEXT NULL` | `Decimal`; **`NULL` means the broker supplied no value**, never coerced to `0` |

Primary key: `(snapshot_date, expiry, strike, option_type, source)`. Write with `INSERT OR REPLACE` so a same-day rerun overwrites. Index `(expiry, option_type, strike, snapshot_date)` for the
last-known-delta point lookup.

## Rules

- `NULL` Greek versus `0`: the parser already normalises Dhan's zero-Greek encoding to `None`; the store must round-trip `None` as SQL `NULL`. `test_zero_delta_rows_flagged` covers this.
- `chain_to_liquidity_rows` is pure and derives quote status, spread % of mid, OI and delta presence from stored or live values; those derived values are not persisted.
- No bid/ask size columns: `OptionLeg` does not carry them (see the `DECISIONS.md` known gap).
- Retention: none. The table is the evidence base for FG-1 and FG-3; roughly 300 rows per expiry per day.
