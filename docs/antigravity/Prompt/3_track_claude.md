**Context: NiftyShield paper trading system**

NiftyShield is a Python 3.10+ options trading research system built on the Upstox API. The relevant existing infrastructure:

- `src/paper/` — paper trading module. `PaperTrade` (frozen Pydantic model, `paper_` prefix enforced on `strategy_name`), `PaperPosition` + `PaperNavSnapshot` (frozen dataclasses), `PaperStore` (SQLite: `paper_trades` + `paper_nav_snapshots` tables), `PaperTracker` (`compute_pnl`, `record_daily_snapshot`). Module invariants in `src/paper/CLAUDE.md`.
- `src/models/options.py` — `OptionLeg`, `OptionChainStrike`, `OptionChain` (frozen Pydantic). Greeks (delta, theta, vega, gamma) are first-class fields on `OptionChainStrike`.
- `src/client/protocol.py` — `BrokerClient` protocol. All modules depend on this, never on concrete implementations. LTP and option chain fetched via this protocol.
- `src/client/upstox_market.py` — `parse_upstox_option_chain` parses raw Upstox chain response into `OptionChain`.
- `scripts/record_paper_trade.py` — CLI to insert a `PaperTrade` row. Args: `--strategy`, `--leg`, `--key` or (`--underlying`, `--strike`, `--option-type`, `--expiry`), `--action`, `--qty`, `--price`, `--date`, `--notes`.
- `scripts/paper_snapshot.py` — standalone mark-to-market: fetches LTP for all open paper positions, computes unrealized P&L, writes `paper_nav_snapshots`.
- `scripts/find_strike_by_delta.py` — queries live Upstox option chain, filters by delta range, outputs a table and ready-to-paste `record_paper_trade.py` commands.
- `data/portfolio/portfolio.sqlite` — shared SQLite DB. Monetary fields always `Decimal`, stored as TEXT.
- All async I/O via `asyncio` + `aiohttp`. No blocking calls in the hot path. No floats in the money path.

**The new framework to implement**

The strategy spec is at `docs/strategies/nifty_track_comparison_v1.md`. Read it fully before planning. The two research questions it answers:

1. **Base instrument comparison** — given 1 Nifty lot equivalent (NEE = `nifty_spot × 65`), how do these three differ in delta sensitivity (₹ move per 1% Nifty move), broker margin locked, and annualised transaction costs?
   - Track A: `paper_nifty_spot` — long NiftyBees ETF
   - Track B: `paper_nifty_futures` — long Nifty Futures (1 lot)
   - Track C: `paper_nifty_proxy` — long Deep ITM Call (delta ≈ 0.90, monthly expiry)

2. **Protection effectiveness** — for Track A (NiftyBees) as primary, with overlays also recorded on Track B and Track C for DB completeness: how much does each overlay protect on a Nifty down-move, and what is the annualised running cost?
   - Approved overlays: Protective Put (`overlay_pp`), Covered Call (`overlay_cc`), Collar (`overlay_collar_put` + `overlay_collar_call`)
   - CSP is excluded — tracked separately in `paper_csp_nifty_v1`
   - Track B + standalone Covered Call is blocked (hard rule)

**What needs to be built — produce an implementation plan covering:**

**1. Overlay expiry selector**

A utility (callable from scripts and importable as a library function) that, given an underlying, option type, target strike or delta, and the three candidate expiries (next quarterly, next yearly, next monthly), fetches the option chain for each and returns the expiry with the lowest `spread_pct = (ask - bid) / mid × 100`, with a hard gate of `spread_pct ≤ 3%`. Falls back in order: quarterly → yearly → monthly. For collars, applies the gate to `max(put_spread_pct, call_spread_pct)` at each expiry. Returns the chosen expiry, the spread_pct at each expiry considered, and the OI at the target strike — all fields to be logged at entry.

**2. Track snapshot reporter**

A script (and underlying library code) that, given the three `paper_track_*` strategy namespaces, produces the daily structured output defined in the spec's "Daily P&L Report Schema" section:

- Per track: base P&L, per-overlay P&L, net combined P&L (absolute ₹)
- Per track: net Delta, net Theta (₹/day), net Vega (₹ per 1% IV change)
- Per track: cycle max drawdown (peak-to-trough since current entry, as % of NEE)
- Per track: Return on NEE (cumulative since cycle entry)
- Track C specific: delta value with state label — `OK` (≥ 0.65), `WARNING` (< 0.65), `CRITICAL` (< 0.40, showing day N of 3)

Greeks must come from the live Upstox option chain via `BrokerClient`. NiftyBees and Futures base legs carry no theta or vega; assign delta = 1.0 for Futures, delta ≈ 0.92 for NiftyBees (configurable). NEE is computed fresh each day from live Nifty spot.

**3. Track C delta monitor**

Logic (can be embedded in the snapshot reporter) that reads Track C's current delta, maintains a consecutive-days-below-0.40 counter persisted across daily runs (in SQLite or a lightweight state file), and emits a structured alert when the counter reaches 3. The alert text and the counter value must be logged in the daily snapshot output and optionally sent via the existing Telegram notifier (`src/notifications/`).

**4. NEE and cost attribution helpers**

Pure functions (no I/O) for:
- `compute_nee(nifty_spot: Decimal, lot_size: int) → Decimal`
- `compute_return_on_nee(pnl: Decimal, nee: Decimal) → Decimal` (percentage)
- `compute_cycle_max_drawdown(nav_history: list[Decimal]) → tuple[Decimal, Decimal]` (absolute ₹, % of NEE)
- `compute_annualised_overlay_cost(premium_paid: Decimal, dte_at_entry: int) → Decimal` (₹/year, for comparing monthly vs quarterly vs yearly overlays on a common basis)

**Technical constraints**

- All monetary fields `Decimal`, never float
- `BrokerClient` protocol via constructor injection; `MockBrokerClient` in all tests
- No network calls in unit tests
- Every public function: one happy-path test + one error/edge-case test
- Async for all I/O; explicit timeout handling on every coroutine
- Structured JSON logging: timestamp, endpoint, latency_ms per API call
- `dataclasses` or Pydantic for all request/response shapes

**Deliverable**

An implementation plan with: module/file layout, function signatures with type hints, data flow between components, which existing files are touched vs new files created, and test file locations. No code yet — plan only.

