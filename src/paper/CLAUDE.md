# src/paper — Module Context

> Auto-loaded when working inside `src/paper/`. Read this before touching any file here.

---

## Module Purpose

Records and marks-to-market paper (simulated) trades for strategy validation.
Paper trades live in `portfolio.sqlite` but in **separate tables** (`paper_trades`,
`paper_nav_snapshots`) — they never touch the live `trades` table.

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

| Table                  | Owner         | Notes                          |
|------------------------|---------------|--------------------------------|
| `paper_trades`         | `PaperStore`  | Created by `PaperStore.__init__` |
| `paper_nav_snapshots`  | `PaperStore`  | Daily mark-to-market per strategy |

Both tables are in the shared `data/portfolio/portfolio.sqlite` DB.

---

## Key Patterns

- `PaperStore(db_path)` — mirrors `PortfolioStore` constructor; creates tables on first call.
- `PaperTracker(store, market)` — mirrors `PortfolioTracker`; inject `MockBrokerClient` in tests.
- `record_paper_trade.py` — mirrors `record_trade.py`; enforces `paper_` prefix before touching DB.
