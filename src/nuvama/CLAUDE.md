# src/nuvama/ — Module Context

## Protocol and mock client

`NuvamaClient` protocol lives in `protocol.py`. It abstracts the Nuvama
SDK (`Holdings()`, `NetPosition()`) for testability.

`MockNuvamaClient` lives in `mock_client.py` — **not** `protocol.py`.
It is in `src/nuvama/` (not `tests/`) so scripts and integration tests
can import it without coupling to the test tree. Same convention as
`src/client/mock_client.py`.

## `_EXCLUDE_ISINS` (`reader.py`)

```python
_EXCLUDE_ISINS: frozenset[str] = frozenset(["INF732E01037"])  # LIQUIDBEES
```

LIQUIDBEES is tracked as a strategy leg in `finideas_ilts` (via the Dhan
reader). Including it in Nuvama bond holdings would double-count the
position. Add any future cross-system instruments here with a comment
naming the other system that owns it.

## Atomicity guarantee — `record_all_options_snapshots` (`store.py`)

Uses a single `executemany` inside one transaction (AR-7). All rows for a
snapshot tick commit together or not at all. Do not split this into
per-row inserts.

## `get_cumulative_realized_pnl` (`store.py`)

SQL `GROUP BY` aggregation — `SUM(realized_pnl_today)` across all
historical rows per symbol. Never load rows into Python and sum in-memory;
the table grows unbounded. Returns a `dict[str, Decimal]`.

## `availabelBalance` typo

This typo is in **`src/dhan/positions.py`**, not in this module. Dhan's
`/v2/fundlimit` API response uses `availabelBalance` (missing an `l`).
It is mapped explicitly in `parse_fund_limit()`.

## Decimal invariant

All monetary fields (`avg_price`, `ltp`, `pnl`, etc.) use `Decimal`,
stored as TEXT in SQLite. Read back with `Decimal(row["col"])`.
`InvalidOperation` on malformed rows is caught in `parse_bond_holdings()`
with a WARNING — the snapshot continues without the bad record.
