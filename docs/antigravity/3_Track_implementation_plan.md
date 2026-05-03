# NiftyShield 3-Track Comparison Framework Implementation Plan

This document outlines the implementation plan for the 3-Track Nifty Long Instrument Comparison framework, addressing the requirements for the overlay expiry selector, track snapshot reporter, Track C delta monitor, and NEE/cost attribution helpers.

## User Review Required

- **Proxy State Persistence**: The plan proposes storing the Track C (Proxy) delta monitor state (consecutive days below 0.40) in a lightweight JSON file (`data/portfolio/proxy_state.json`) rather than modifying the core SQLite schema. This keeps the core DB schema clean and avoids migration. Is this acceptable, or would you prefer a new `paper_proxy_state` table in `portfolio.sqlite`?
- **Overlay Target Input**: For the overlay expiry selector, when targeting a delta, the selector will need to fetch the option chain to find the strike closest to the target delta before evaluating spreads. The plan proposes accepting `put_target_strike`, `put_target_delta`, `call_target_strike`, and `call_target_delta`. Please review the signature of `select_overlay_expiry` in `src/paper/overlay_selector.py`.

## Proposed Changes

---

### `src/paper/metrics.py`
[NEW] `metrics.py`(file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/metrics.py)

Pure functions for NEE and cost attribution. No I/O.

- `compute_nee(nifty_spot: Decimal, lot_size: int) -> Decimal`
- `compute_return_on_nee(pnl: Decimal, nee: Decimal) -> Decimal`
- `compute_cycle_max_drawdown(nav_history: list[Decimal]) -> tuple[Decimal, Decimal]`
  *(Returns a tuple of absolute drawdown and % of NEE drawdown)*
- `compute_annualised_overlay_cost(premium_paid: Decimal, dte_at_entry: int) -> Decimal`

---

### `src/paper/overlay_selector.py`
[NEW] `overlay_selector.py`(file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/overlay_selector.py)

Logic to find the most cost-efficient expiry based on bid-ask spreads.

- **Data Models**:
  - `ExpirySpreadProfile`: dataclass capturing `expiry`, `put_spread_pct`, `call_spread_pct`, `put_oi`, `call_oi`.
  - `OverlaySelection`: dataclass returning `chosen_expiry`, `profiles` list, and `fallback_reason`.
- **Function**:
  `async def select_overlay_expiry(broker: BrokerClient, underlying_key: str, candidate_expiries: list[str], option_type: Literal["CE", "PE", "COLLAR"], target_strike: Decimal | None = None, target_delta: Decimal | None = None, timeout_sec: float = 10.0) -> OverlaySelection`
  *(Applies the <= 3% spread gate, checks quarterly -> yearly -> monthly).*

---

### `src/paper/proxy_monitor.py`
[NEW] `proxy_monitor.py`(file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/proxy_monitor.py)

Monitors Track C's delta and tracks consecutive days below 0.40.

- **Data Models**:
  - `ProxyDeltaState`: dataclass with `consecutive_days_below_40` and `last_update_date`.
- **Class**:
  `ProxyDeltaMonitor`
  - `__init__(self, state_file_path: Path)`
  - `def _load_state(self) -> ProxyDeltaState`
  - `def _save_state(self, state: ProxyDeltaState) -> None`
  - `async def update_and_check(self, current_delta: Decimal, current_date: str) -> tuple[str, int]` *(Returns state label 'OK', 'WARNING', 'CRITICAL' and current counter).*

---

### `src/paper/track_snapshot.py`
[NEW] `track_snapshot.py`(file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/track_snapshot.py)

Core logic for producing the daily structured output for the three tracks.

- **Data Models**:
  - `TrackGreeks`: `net_delta`, `net_theta`, `net_vega`
  - `TrackPnL`: `base_pnl`, `overlay_pnl`, `net_pnl`
  - `TrackSnapshot`: comprehensive data for a single track.
- **Function**:
  `async def generate_track_snapshot(store: PaperStore, broker: BrokerClient, track_namespace: str, nifty_spot: Decimal, snapshot_date: date, proxy_monitor: ProxyDeltaMonitor | None = None) -> TrackSnapshot`
  *(Separates base vs overlay P&L by filtering `leg_role` prefixes, fetches live Greeks from Upstox chain, assigns base NiftyBees/Futures deltas, and computes return on NEE and max DD).*

---

### `scripts/paper_track_snapshot.py`
[NEW] `paper_track_snapshot.py`(file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_track_snapshot.py)

CLI script that ties it all together and prints the structured report.

- Parses CLI arguments (`--date`, `--underlying-price`, etc.).
- Initializes `UpstoxMarketClient`, `PaperStore`, and `ProxyDeltaMonitor`.
- Calls `generate_track_snapshot` for all three tracks (`paper_nifty_spot`, `paper_nifty_futures`, `paper_nifty_proxy`).
- Formats and prints the exact console output specified in the requirements schema.
- Uses `src/notifications/` Telegram notifier if the Track C proxy monitor returns a CRITICAL state.

---

### `tests/paper/`
[NEW] test files

- `test_metrics.py`: Happy path and edge case tests for pure math functions.
- `test_overlay_selector.py`: Mock `BrokerClient` tests for spread calculation, fallback logic, and collar MAX threshold logic.
- `test_proxy_monitor.py`: Tests for JSON state loading/saving, and state transitions (e.g. counter resetting when delta > 0.40).
- `test_track_snapshot.py`: Tests for base vs overlay separation, greek aggregation, and correct instantiation of `TrackSnapshot` outputs.

## Verification Plan

### Automated Tests
- Run `pytest tests/paper/test_metrics.py tests/paper/test_overlay_selector.py tests/paper/test_proxy_monitor.py tests/paper/test_track_snapshot.py`
- Verify 100% test coverage for the new files.
- Verify `MockBrokerClient` is strictly used and no network calls are made during tests.

### Manual Verification
- Dry-run the CLI: `python scripts/paper_track_snapshot.py --underlying-price 24000 --dry-run` to verify the output formatting matches the specific schema requested.
- Run the overlay expiry selector manually using a scratch script to hit the live Upstox API and observe real spread values.
