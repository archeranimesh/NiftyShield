# src/portfolio — Module Context

> Auto-loaded when working inside `src/portfolio/`. Read this before touching any file here. Invariants and caller contracts only — wiring lists, model/registry enumerations, and rationale live in
> **`NOTES.md`** (same directory, not auto-loaded).

---

## Note: `overlay_coverage.py` is a different domain than the rest of this directory

Everything else below (`Leg`/`Trade`/`Strategy`, `PortfolioTracker`, `apply_trade_positions()`) belongs to the **live** finideas/finrakshak portfolio system. `overlay_coverage.py` is **paper-trading**
code. Do not assume the Decimal/Leg/Trade conventions below apply to it — see `src/paper/CLAUDE.md` instead, and `NOTES.md` for why it sits in this directory.

---

## Core Distinctions

### Leg vs Trade
- **`Leg`** (in `strategies/finideas/ilts.py`, `finrakshak.py`) — conceptual strategy role. Defines instrument key, direction, entry price, and quantity as a *definition*. Never mutated at runtime.
- **`Trade`** (in `trades` table via `store.py`) — physical execution record. What actually transacted, when, at what price. Drives cost-basis and qty used in P&L.
- They coexist permanently: `Leg` defines shape; `Trade` drives numbers. Both are required.

### Decimal Invariant
All monetary fields (`entry_price`, `ltp`, `close`, `underlying_price`, `price`) are **`Decimal`** in Pydantic models and stored as **TEXT** in SQLite. Never store as float. Read back with
`Decimal(row["col"])`. Float LTPs from the Upstox API are converted at the boundary via `Decimal(str(float_val))`.

---

## Key Patterns

### `apply_trade_positions()` — the overlay function
Module-level pure function in `tracker.py`. Call signature:
```python
apply_trade_positions(strategy: Strategy, positions: dict[str, tuple[int, Decimal]]) -> Strategy
```
- Patches `Leg.qty` and `Leg.entry_price` from weighted average trade data
- Appends trade-only legs (e.g. LIQUIDBEES) as `EQUITY/CNC` — these have no definition in `ilts.py`
- Drops legs whose net qty is zero (closed positions)
- Returns a new `Strategy` — never mutates the original

Callers do **not** need to apply it manually for tracker paths — the overlay is internalized. Full call-site list: `NOTES.md`.

### Trade-only legs and `ensure_leg()`
When `record_daily_snapshot` encounters a leg with `id is None` (e.g. LIQUIDBEES appended by overlay), it calls `store.ensure_leg(strategy_name, leg)` to upsert and obtain a DB id. Idempotent — safe
to call multiple times.

---

## `trades.strategy_name` Constraint — CRITICAL

Must exactly match the `strategies.name` column. Canonical values:
- `finideas_ilts`
- `finrakshak`

Any other value silently disables the overlay — `get_all_positions_for_strategy()` returns empty, no error raised. This is the most common silent failure mode.

When calling `record_trade.py`:
```bash
python -m scripts.record_trade --strategy finideas_ilts ...
# NOT --strategy ILTS or --strategy "Finideas ILTS"
```

---

## `store.py` Key Behaviours
- `record_trade` — idempotent via `UNIQUE(strategy_name, leg_role, trade_date, action)`
- `get_position(strategy_name, leg_role)` — returns `(net_qty, avg_buy_price)`. SELL prices excluded from average — only BUY prices matter for cost basis.
- `get_all_positions_for_strategy(strategy_name)` — returns `dict[leg_role, (net_qty, avg_price, instrument_key)]`

## Models and Strategy Registry

`models.py` holds `Leg`, `Strategy`, `DailySnapshot`, `Trade`, `TradeAction`, `PortfolioSummary`; `Trade` is `frozen=True` with `qty > 0` / `price > 0` validators, and P&L methods accept `float |
Decimal` but always return `Decimal`. Registry (`strategies/`) and the per-model field lists: `NOTES.md`.
