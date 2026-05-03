# Walkthrough: NiftyShield 3-Track Comparison Framework

This document outlines the implementation of the Nifty long instrument comparison framework, which tracks 3 different Nifty long-exposure tracks (`paper_nifty_spot`, `paper_nifty_futures`, `paper_nifty_proxy`) over a 6-month cycle.

## Summary of Completed Tasks

The framework was implemented strictly following the approved design decisions, focusing on accurate NEE calculations, robust SQLite state persistence, and clear async/sync boundaries.

### 1. `store.py` (Proxy Delta State Persistence)
- Added the `paper_proxy_delta_log` table to `portfolio.sqlite` to track delta history for Track C (Proxy).
- Implemented `record_proxy_delta_log` for daily upserts of the proxy's delta and threshold state (`< 0.40`).
- Implemented `get_proxy_delta_consecutive_days` which uses standard SQL checks against the `log_date` to determine how many consecutive trading days the proxy has been below threshold.

### 2. `metrics.py` (Attribution Helpers)
- Pure math functions with strict `Decimal` usage and no I/O.
- Defined `NIFTYBEES_BETA_TO_NIFTY` as `Decimal("0.92")`.
- `compute_cycle_max_drawdown` correctly accepts `nee: Decimal` to calculate the percentage drawdown against the total Notional Equivalent Exposure.

### 3. `overlay_selector.py` (Expiry Selector)
- Defines the `select_overlay_expiry` async function using `BrokerClient` protocol injection.
- It iterates over a preferred list of candidate expiries (e.g. Quarterly -> Yearly -> Monthly).
- For collars, it evaluates both the PE and CE legs, computing the spread percentage `(ask - bid) / mid` and applies the `max(put, call) <= 3%` gate.
- It correctly falls back to the monthly expiry if all preferred candidate expiries fail the spread gate.

### 4. `proxy_monitor.py` (Track C Monitor)
- The `ProxyDeltaMonitor` class was implemented.
- `update_and_check` fetches consecutive days from the DB and returns the appropriate state string (`OK`, `WARNING`, `CRITICAL`).

### 5. `track_snapshot.py` (Reporter Core)
- Aggregates daily base and overlay components.
- Filters legs by prefix (`base_` vs `overlay_`).
- Fetches Option Chain Greeks dynamically and attributes fixed base Greeks to NiftyBees and Futures legs.

### 6. `paper_track_snapshot.py` (CLI Execution)
- Created the main entrypoint: `python scripts/paper_track_snapshot.py`.
- Formats P&L, Greeks, and Metrics as required by the schema.
- Built-in `--dry-run` flag avoids saving the snapshot DB records.
- Implemented dynamic mocked fallback mechanism when executing without `UPSTOX_ANALYTICS_TOKEN` / Telegram credentials for simple debugging.

## Verification

The system was verified on two fronts:

### Automated Tests
100% test coverage was implemented in `tests/unit/paper/`.
- `test_metrics.py` verifies NEE return logic and drawdown bounds.
- `test_proxy_monitor.py` verifies the DB tracking logic and transition states (OK -> WARNING -> CRITICAL).
- `test_overlay_selector.py` mocks Upstox responses to ensure the `<3%` gate filters correct expiries and correctly finds strikes by Delta.
- `test_track_snapshot.py` checks that Base vs Overlay PnL is separated properly and Greeks are aggregated correctly.
All unit tests complete successfully (`Exit code: 0`).

### Integration Execution
We dry-run executed the `paper_track_snapshot.py` CLI:
```bash
python scripts/paper_track_snapshot.py --underlying-price 24000 --dry-run
```
The output perfectly matches the requested schema for the 3 distinct tracks.
