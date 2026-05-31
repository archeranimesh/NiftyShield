# Scaffolding for src/gamma/ package, models, and GammaStore

This task implements the data access layer and models for the Near-Expiry Gamma Buy strategy. It sets up the package, defines `GammaChainSnapshot` and `GammaWatchlistEntry` dataclasses, and implements `GammaStore` to persist and retrieve these objects from the shared SQLite database.

## User Review Required

> [!IMPORTANT]
> **Decimal Invariant Enforced**: Every numeric/monetary/Greek value in the Python models will be typed as `Decimal` (or `Decimal | None`) and stored as `TEXT` in the SQLite database to preserve precision.
> Specifically, the following fields are affected:
> - **In `GammaChainSnapshot`**: `nifty_spot`, `nifty_futures`, `india_vix`, `delta_val`, `gamma_val`, `vega_val`, `theta_val`, `iv_val`, `gamma_gearing`, `distance_pct`, `best_bid`, `best_ask`, `bid_ask_spread`, `oi_change_1d`, `strike_iv_pctile_20d`, `gamma_gearing_pctile_dte`.
> - **In `GammaWatchlistEntry`**: `distance_pct`, `gamma_gearing`, `oi_change_1d`.
> At load/read time, these fields will be reconstructed using `Decimal(row["col"])` (or `None`).

> [!NOTE]
> All database interactions will use the shared SQLite database (`portfolio.sqlite`) via the connection manager pattern defined in `src/db.py`.
> The schema matches §11 of the Near-Expiry Gamma Buy v1 strategy spec precisely.

## Open Questions

None.

## Proposed Changes

### Gamma Strategy Scaffolding

#### [NEW] [__init__.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/gamma/__init__.py)
Package stub with one comment line.

#### [NEW] [models.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/gamma/models.py)
Define frozen dataclasses `GammaChainSnapshot` and `GammaWatchlistEntry` matching the schema with `Decimal` invariants for all monetary, Greek, and numeric/derived fields.

#### [NEW] [store.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/gamma/store.py)
Define `GammaStore` class with stateless methods:
- `create_tables(conn)`
- `insert_chain_snapshot(conn, snap)`
- `get_chain_snapshots(conn, expiry_date, snapshot_date)`
- `get_yesterday_snapshot(conn, expiry_date, strike, option_type, today)`
  - *Semantics*: Query the most recent snapshot for the specified `(expiry_date, strike, option_type)` where `snapshot_date < today` (ordering by `snapshot_date` DESC, `snapshot_time` DESC, limit 1).
- `upsert_watchlist(conn, entry)`
- `get_active_watchlist(conn, expiry_date)`
- `remove_from_watchlist(conn, expiry_date, strike, option_type, reason, removed_date)`
- **Calibration Support Queries**:
  - `get_iv_history(conn, strike, option_type, limit=20) -> list[Decimal]`
    - *Semantics*: Fetch the trailing `limit` IV values (`iv_val`) for a given strike and option type across all contracts, ordered by `snapshot_date` DESC, then reversed to return chronological order.
  - `get_gearing_by_dte(conn, target_dte, limit_days=60) -> list[Decimal]`
    - *Semantics*: Fetch all `gamma_gearing` values where `dte_calendar = target_dte` over the last `limit_days` distinct snapshot dates, ordered by `snapshot_date` DESC.

#### [NEW] [__init__.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/tests/unit/gamma/__init__.py)
Test package stub.

#### [NEW] [test_gamma_store.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/tests/unit/gamma/test_gamma_store.py)
Unit tests for `GammaStore` using in-memory SQLite database, validating Decimal types on round-trip.

## Verification Plan

### Automated Tests
- Run `python -m pytest tests/unit/gamma/test_gamma_store.py --tb=short` to verify all store operations.
- Run full test suite `python -m pytest tests/unit/ --tb=no -q`.

### Post-Commit Indexing
- Re-index codebase: run `mcp__codebase-memory-mcp__index_repository` with project ID `Users-abhadra-myWork-myCode-python-NiftyShield` to make the new symbols visible in the graph.
