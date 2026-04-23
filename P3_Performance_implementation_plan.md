# P3 — Performance & Structural Correctness

Five action items from the 2026-04-21 architecture review. None produce wrong numbers (those were P0/P1/P2), but they accumulate latency, open N connections per run, and keep the Nuvama SDK un-abstracted — all problems that compound as the position count grows.

---

## Dependency & File-Conflict Map

| AR | Files Touched | Conflicts With |
|---|---|---|
| AR-8 | `src/nuvama/store.py` | None |
| AR-9a (protocol core) | `src/nuvama/protocol.py` (NEW), `src/nuvama/reader.py`, `src/nuvama/options_reader.py`, `tests/` | None |
| AR-9b (wire into scripts) | `scripts/daily_snapshot.py`, `scripts/nuvama_intraday_tracker.py` | AR-11, AR-12 |
| AR-10 | `src/portfolio/store.py` | None |
| AR-11 | `src/portfolio/tracker.py`, `scripts/daily_snapshot.py` | AR-9b |
| AR-12 | `scripts/nuvama_intraday_tracker.py` | AR-9b |

**Conclusion:** AR-8, AR-9a, AR-10, AR-12 have zero file conflicts → run in parallel.  
AR-9b and AR-11 both touch `daily_snapshot.py` → sequential, after Phase 1.

---

## Execution Plan

```
Phase 1 — PARALLEL (3 agents, no conflicts)
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   Agent 1        │ │   Agent 2        │ │   Agent 3        │
│   SQL Perf       │ │   Protocol Core  │ │   Script Hygiene │
│   AR-8 + AR-10   │ │   AR-9a          │ │   AR-12          │
└────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘
         └──────────────┬─────┘──────────────┘
                        ↓
Phase 2 — SEQUENTIAL (one agent integrates all three)
                  AR-9b (wire protocol)
                        ↓
                  AR-11 (eliminate double LTP)
                        ↓
                  Full test suite — all green
```

---

## Phase 1 — Parallel Agent Work

### Agent 1: SQL Performance (`p3-sql-agent`)

**AR-8 — Replace Python aggregation with SQL GROUP BY**  
File: `src/nuvama/store.py:334`

```python
# BEFORE — fetches unbounded rows, aggregates in Python
rows = conn.execute(
    "SELECT trade_symbol, realized_pnl_today FROM nuvama_options_snapshots WHERE snapshot_date < ?",
    (before_date.isoformat(),),
).fetchall()
result: dict[str, Decimal] = {}
for row in rows:
    sym = row["trade_symbol"]
    val = Decimal(row["realized_pnl_today"])
    result[sym] = result.get(sym, Decimal("0")) + val
return result

# AFTER — one aggregate per symbol, O(symbols) not O(trading days × symbols)
rows = conn.execute(
    """SELECT trade_symbol, SUM(realized_pnl_today) AS cumulative
       FROM nuvama_options_snapshots
       WHERE snapshot_date < ?
       GROUP BY trade_symbol""",
    (before_date.isoformat(),),
).fetchall()
return {row["trade_symbol"]: Decimal(str(row["cumulative"])) for row in rows}
```

> [!NOTE]
> `realized_pnl_today` is stored as TEXT (Decimal invariant). `SUM()` on TEXT works in SQLite because TEXT → NUMERIC affinity coercion, but the result must still be wrapped in `Decimal(str(...))` to maintain precision.

Tests: `test_get_cumulative_realized_pnl_default_excludes_today` and `test_get_cumulative_realized_pnl_with_explicit_before_date` validate this with no changes to test code.

---

**AR-10 — Eliminate N+1 DB connections in `get_all_positions_for_strategy`**  
File: `src/portfolio/store.py:561`

Current: Opens 1 connection for `DISTINCT leg_role`, then calls `get_position()` per leg — each `get_position()` opens its own connection and fetches all `trades` rows for that strategy.  
For 7 legs: **8 connections, 7 full table scans per call**. Called twice per snapshot run.

```python
# AFTER — single connection, single aggregate query
def get_all_positions_for_strategy(
    self, strategy_name: str
) -> dict[str, tuple[int, Decimal, str]]:
    """Derive net position for every leg in one SQL aggregate query.
    
    Single connection, single GROUP BY — replaces the previous N+1 pattern
    (one connection for DISTINCT + one get_position() call per leg).
    """
    with _connect(self.db_path) as conn:
        rows = conn.execute(
            """SELECT
                   leg_role,
                   instrument_key,
                   SUM(CASE WHEN action='BUY' THEN quantity ELSE 0 END) AS buy_qty,
                   SUM(CASE WHEN action='SELL' THEN quantity ELSE 0 END) AS sell_qty,
                   SUM(CASE WHEN action='BUY' THEN CAST(price AS REAL) * quantity ELSE 0 END) AS buy_value
               FROM trades
               WHERE strategy_name = ?
               GROUP BY leg_role, instrument_key
               ORDER BY leg_role""",
            (strategy_name,),
        ).fetchall()

    result: dict[str, tuple[int, Decimal, str]] = {}
    for row in rows:
        buy_qty = row["buy_qty"]
        sell_qty = row["sell_qty"]
        net_qty = buy_qty - sell_qty
        # Reconstruct avg_price from raw TEXT price to preserve Decimal invariant
        avg_price: Decimal
        if buy_qty > 0:
            # Re-fetch individual rows for precise Decimal arithmetic
            avg_price = self._get_avg_buy_price(strategy_name, row["leg_role"])
        else:
            avg_price = Decimal("0")
        result[row["leg_role"]] = (net_qty, avg_price, row["instrument_key"])
    return result
```

> [!IMPORTANT]
> **Decimal invariant on `price`:** `price` is stored as TEXT. `SUM(CAST(price AS REAL) * quantity)` is used only to compute the buy_value for division. For the final `avg_price`, use a helper `_get_avg_buy_price()` that fetches BUY rows as `Decimal(row["price"])` and computes the weighted average in Python — this preserves full Decimal precision.
>
> Alternatively: fetch BUY rows via `WHERE action='BUY' AND strategy_name=? AND leg_role=?` as a sub-query and do Python Decimal arithmetic. The simplest correct approach that avoids any float in the avg_price path.

**Simplest correct approach for avg_price:**
```python
# In the same connection block, or a helper method:
def _get_avg_buy_price(self, strategy_name: str, leg_role: str) -> Decimal:
    with _connect(self.db_path) as conn:
        rows = conn.execute(
            "SELECT quantity, price FROM trades WHERE strategy_name=? AND leg_role=? AND action='BUY'",
            (strategy_name, leg_role),
        ).fetchall()
    total_qty = sum(r["quantity"] for r in rows)
    if total_qty == 0:
        return Decimal("0")
    total_value = sum(Decimal(r["price"]) * r["quantity"] for r in rows)
    return total_value / total_qty
```

Tests: All existing `test_trade_store.py` tests for `get_all_positions_for_strategy` validate this. Add one test asserting a single DB call (mock `_connect`).

---

### Agent 2: Protocol Core (`p3-protocol-agent`)

**AR-9a — Create `NuvamaClient` protocol and `MockNuvamaClient`**

#### [NEW] `src/nuvama/protocol.py`
```python
"""NuvamaClient protocol — abstracts APIConnect SDK behind a 2-method interface."""
from __future__ import annotations
from typing import Protocol, runtime_checkable


@runtime_checkable
class NuvamaClient(Protocol):
    """Minimal protocol over the Nuvama APIConnect SDK.
    
    Only two methods are used in production. All callers accept this protocol
    rather than the concrete APIConnect class, enabling offline testing via
    MockNuvamaClient.
    """

    def Holdings(self) -> str:  # noqa: N802
        """Return raw Holdings() response as JSON string."""
        ...

    def NetPosition(self) -> str:  # noqa: N802
        """Return raw NetPosition() response as JSON string."""
        ...
```

#### [MODIFY] `src/nuvama/reader.py`
Change signature of `fetch_nuvama_portfolio`:
```python
# Before
from typing import Any
def fetch_nuvama_portfolio(api: Any, ...) -> NuvamaBondSummary:

# After
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.nuvama.protocol import NuvamaClient

def fetch_nuvama_portfolio(api: "NuvamaClient", ...) -> NuvamaBondSummary:
```

#### [MODIFY] `src/nuvama/options_reader.py`
Check if it takes an api parameter — if so, apply same typing.

#### [NEW] `tests/unit/nuvama/mock_client.py`
```python
"""MockNuvamaClient for offline testing of Nuvama reader functions."""
from __future__ import annotations

import json


class MockNuvamaClient:
    """Returns fixture JSON strings for Holdings() and NetPosition()."""

    def __init__(
        self,
        holdings_json: str | None = None,
        net_position_json: str | None = None,
    ) -> None:
        self._holdings = holdings_json or json.dumps({})
        self._net_position = net_position_json or json.dumps({})

    def Holdings(self) -> str:  # noqa: N802
        return self._holdings

    def NetPosition(self) -> str:  # noqa: N802
        return self._net_position
```

Tests to add: verify `MockNuvamaClient` satisfies `NuvamaClient` protocol via `isinstance(mock, NuvamaClient)`.

---

### Agent 3: Script Hygiene (`p3-script-hygiene-agent`)

**AR-12 — Defer module-level I/O imports in `nuvama_intraday_tracker.py`**

Current module-level imports to move inside `async def main()`:
- `from src.auth.nuvama_verify import load_api_connect`
- `from src.nuvama.store import NuvamaStore`
- `from src.nuvama.options_reader import parse_options_positions`
- `from src.client.factory import create_client`
- `from src.client.exceptions import LTPFetchError`

Pattern to follow: `daily_snapshot.py` which defers all I/O imports into `_async_main()`.

No new tests required — this is a pure structural refactor with no behavior change. Verify the script still runs:
```bash
UPSTOX_ENV=test python -m scripts.nuvama_intraday_tracker --help
```

---

## Phase 2 — Sequential Integration

### Step A: Wire Protocol into Scripts (AR-9b)

**Depends on:** Agent 2 (protocol exists) + Agent 3 (deferred imports in place)

Files: `scripts/daily_snapshot.py`, `scripts/nuvama_intraday_tracker.py`

In `_async_main()` of `daily_snapshot.py`, add type annotation for `nuvama_api_instance`:
```python
from src.nuvama.protocol import NuvamaClient
# ...
nuvama_api_instance: NuvamaClient = load_api_connect()
```

In `nuvama_intraday_tracker.py` (already deferred by AR-12), same annotation on the `api` local variable.

No behavior change — purely type-level improvement.

---

### Step B: Eliminate Double LTP Fetch (AR-11)

**Depends on:** Step A (daily_snapshot.py must be stable before further edits)

**Problem:** In `_async_main` (lines 424–443):
1. `await tracker.record_all_strategies(...)` — fetches LTPs internally per strategy
2. `await tracker.compute_pnl(strategy.name)` per strategy — fetches LTPs again

**Fix:** Change `record_all_strategies` return type to `dict[str, StrategyPnL | None]`, built from prices already fetched in `record_daily_snapshot`.

#### [MODIFY] `src/portfolio/tracker.py`

```python
# record_daily_snapshot: add StrategyPnL to return value
async def record_daily_snapshot(
    self, strategy_name: str, snapshot_date: date | None = None,
    underlying_price: float | None = None,
) -> tuple[int, StrategyPnL | None]:  # was: int
    ...
    # At the point where LTPs are already fetched (prices dict exists):
    strategy_pnl = self._compute_pnl_from_prices(strategy, prices)
    return count, strategy_pnl

# record_all_strategies: collect and return StrategyPnL per strategy
async def record_all_strategies(
    self, snapshot_date: date | None = None,
    underlying_price: float | None = None,
) -> tuple[dict[str, int], dict[str, StrategyPnL | None]]:  # was: dict[str, int]
    strategies = self._get_all_overlaid_strategies()
    counts: dict[str, int] = {}
    pnls: dict[str, StrategyPnL | None] = {}
    for strategy in strategies:
        count, pnl = await self.record_daily_snapshot(strategy.name, snapshot_date, underlying_price)
        counts[strategy.name] = count
        pnls[strategy.name] = pnl
    return counts, pnls
```

#### [MODIFY] `scripts/daily_snapshot.py` (lines 424–443)

```python
# BEFORE
results = await tracker.record_all_strategies(...)
strategy_pnls: dict[str, object] = {}
for strategy in strategies:
    count = results.get(strategy.name, 0)
    pnl = await tracker.compute_pnl(strategy.name)  # ← 2nd LTP fetch
    strategy_pnls[strategy.name] = pnl

# AFTER
results, strategy_pnls = await tracker.record_all_strategies(...)
for strategy in strategies:
    count = results.get(strategy.name, 0)
    pnl = strategy_pnls.get(strategy.name)
    # print block unchanged
```

Tests: Update `test_record_all_strategies` for new return type. Add a test asserting `market.get_ltp` is called exactly once per strategy after the fix.

---

## Verification Plan

### After Phase 1 (each agent independently)
```bash
python -m pytest tests/unit/ -v --tb=short
# Expected: 846+ passing, same pre-existing failures
```

### After Phase 2
```bash
python -m pytest tests/unit/ -v --tb=short
# Expected: 846+ passing
UPSTOX_ENV=test python -m scripts.daily_snapshot  # smoke test — no double fetch warning
```

### Per-AR smoke commands
```bash
# AR-8: no observable change — validate via test
python -m pytest tests/unit/nuvama/test_store.py -v -k "cumulative"

# AR-10: no observable change — validate via test  
python -m pytest tests/unit/portfolio/test_trade_store.py -v -k "positions"

# AR-12: import safety check
python -c "import scripts.nuvama_intraday_tracker"  # must not fail without .env
```

---

## Commit Plan

| Commit | Items | Files |
|---|---|---|
| `perf(nuvama): replace Python aggregation with SQL GROUP BY in get_cumulative_realized_pnl` | AR-8 | `src/nuvama/store.py` |
| `perf(portfolio): eliminate N+1 DB connections in get_all_positions_for_strategy` | AR-10 | `src/portfolio/store.py` |
| `refactor(nuvama): introduce NuvamaClient protocol and MockNuvamaClient` | AR-9a | `src/nuvama/protocol.py`, `reader.py`, `options_reader.py`, `tests/` |
| `refactor(scripts): defer I/O imports in nuvama_intraday_tracker` | AR-12 | `scripts/nuvama_intraday_tracker.py` |
| `refactor(nuvama): wire NuvamaClient type into daily_snapshot + intraday_tracker` | AR-9b | `scripts/daily_snapshot.py`, `scripts/nuvama_intraday_tracker.py` |
| `perf(tracker): eliminate double LTP fetch in record_all_strategies` | AR-11 | `src/portfolio/tracker.py`, `scripts/daily_snapshot.py` |

Each commit: run `python -m pytest tests/unit/` → all green before tagging.
