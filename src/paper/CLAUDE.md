# src/paper — Module Context

> Auto-loaded when working inside `src/paper/`. Read this before touching any file here.

---

## Module Purpose

Records and marks-to-market paper (simulated) trades for strategy validation.
Paper trades live in `portfolio.sqlite` but in **separate tables** (`paper_trades`,
`paper_nav_snapshots`, `paper_leg_snapshots`) — they never touch the live `trades` table.

---

## Invariants

### `paper_` prefix — CRITICAL

Every `strategy_name` stored in `paper_trades` **must start with `paper_`**.
This is enforced at model construction via a Pydantic validator on `PaperTrade`.
The prefix is the sole runtime guard against cross-contamination of live and paper
ledgers in shared SQLite queries.

Valid: `paper_csp_nifty_v1`, `paper_ic_nifty_v1`
Invalid: `csp_nifty_v1`, `finideas_ilts`

### No broker calls

`PaperTracker` consumes the `BrokerClient` protocol (via constructor injection) for
LTP lookups only. It never places orders, modifies positions, or calls any execution
endpoint. Pass `MockBrokerClient` in all tests.

### Decimal invariant

All monetary fields (`price`, `ltp`, `avg_cost`, `realized_pnl`, `unrealized_pnl`)
are `Decimal` in models and stored as **TEXT** in SQLite. Read back with
`Decimal(row["col"])`. No floats in the money path.

### Idempotency

`PaperStore.record_trade` uses `UNIQUE(strategy_name, leg_role, trade_date, action)`
with `ON CONFLICT DO NOTHING` — same as the live `trades` table. Re-running
`record_paper_trade.py` with the same args is always safe.

---

## Table Ownership

| Table                   | Owner         | Notes                                           |
|-------------------------|---------------|-------------------------------------------------|
| `paper_trades`          | `PaperStore`  | Created by `PaperStore.__init__`                |
| `paper_nav_snapshots`   | `PaperStore`  | Daily mark-to-market per strategy               |
| `paper_leg_snapshots`   | `PaperStore`  | Per-leg daily P&L snapshot; PK covers the index |

All tables are in the shared `data/portfolio/portfolio.sqlite` DB.

---

## PaperLegSnapshot

Frozen dataclass added in Phase A. Fields: `strategy_name`, `leg_role`, `snapshot_date`,
`unrealized_pnl`, `realized_pnl`, `total_pnl`, `ltp` (optional).

**`total_pnl` invariant (enforced at write time):** `record_leg_snapshot` asserts
`total_pnl == unrealized_pnl + realized_pnl` and raises `ValueError` on mismatch.
Never construct a `PaperLegSnapshot` with inconsistent components — the store will reject it.

---

## PaperStore API additions (Phase A)

| Method | Signature | Behaviour |
|---|---|---|
| `record_leg_snapshot` | `(snap: PaperLegSnapshot) → None` | Upsert with `ON CONFLICT … DO UPDATE`. Asserts `total_pnl` invariant before writing. |
| `get_leg_snapshot` | `(strategy, leg_role, snap_date) → PaperLegSnapshot \| None` | Exact date lookup. |
| `get_prev_leg_snapshot` | `(strategy, leg_role, before_date) → PaperLegSnapshot \| None` | Latest snapshot strictly before `before_date` (for delta-from-yesterday). |
| `delete_trade` | `(trade: PaperTrade) → None` | Deletes by `(strategy_name, leg_role, trade_date, action)`. No-op if missing. Used for atomic rollback in overlay roll script. |

---

## Key Patterns

- `PaperStore(db_path)` — mirrors `PortfolioStore` constructor; creates tables on first call.
- `PaperTracker(store, market)` — mirrors `PortfolioTracker`; inject `MockBrokerClient` in tests.
- `record_paper_trade.py` — mirrors `record_trade.py`; enforces `paper_` prefix before touching DB.
- `paper_3track_snapshot.py` — canonical EOD cron; writes both `paper_nav_snapshots` and `paper_leg_snapshots`.
- `paper_3track_overlay.py` / `paper_3track_overlay_roll.py` — overlay entry and roll automation; use `delete_trade` for rollback.
