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

Current: Opens 1 connection for `DISTINCT leg_role`, then calls `get_position()` per leg — each opens a new connection and full table scan. For 7 legs: **8 connections, 7 scans per call**. Called twice per snapshot run.

> [!CAUTION]
> Do NOT use a `_get_avg_buy_price()` helper — it would open one connection per leg, recreating the N+1 problem. Do NOT use `CAST(price AS REAL)` anywhere — violates the Decimal invariant.

**Fix:** One `_connect` block, one `SELECT *` for all trades, full Python Decimal aggregation:

```python
from collections import defaultdict

def get_all_positions_for_strategy(
    self, strategy_name: str
) -> dict[str, tuple[int, Decimal, str]]:
    """Single DB round-trip replacing the previous N+1 pattern."""
    with _connect(self.db_path) as conn:
        all_rows = conn.execute(
            """SELECT leg_role, instrument_key, action, quantity, price
               FROM trades
               WHERE strategy_name = ?
               ORDER BY leg_role""",
            (strategy_name,),
        ).fetchall()

    buy_qty: dict[str, int] = defaultdict(int)
    sell_qty: dict[str, int] = defaultdict(int)
    buy_value: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    ikey: dict[str, str] = {}

    for row in all_rows:
        leg = row["leg_role"]
        ikey[leg] = row["instrument_key"]
        qty = row["quantity"]
        price = Decimal(row["price"])   # TEXT → Decimal, no float
        if row["action"] == "BUY":
            buy_qty[leg] += qty
            buy_value[leg] += price * qty
        else:
            sell_qty[leg] += qty

    result: dict[str, tuple[int, Decimal, str]] = {}
    for leg, instrument_key in ikey.items():
        bq = buy_qty[leg]
        net = bq - sell_qty[leg]
        avg = buy_value[leg] / bq if bq > 0 else Decimal("0")
        result[leg] = (net, avg, instrument_key)
    return result
```

Connection count: **8 → 1**. Tests: all existing `test_trade_store.py` tests validate. Add `test_get_all_positions_single_connection` — spy `_connect`, assert called exactly once.

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

`@runtime_checkable` means `isinstance(mock, NuvamaClient)` works at runtime — so the import must be a **normal import, not a `TYPE_CHECKING` guard**:

```python
# Normal import — required because protocol is runtime_checkable
from src.nuvama.protocol import NuvamaClient

def fetch_nuvama_portfolio(api: NuvamaClient, ...) -> NuvamaBondSummary:
    ...
```

Remove `Any` from imports if it's no longer used elsewhere in the file.

#### [MODIFY] `src/nuvama/options_reader.py`
Check if any function takes `api: Any` — if so, apply same `NuvamaClient` annotation.

#### [NEW] `src/nuvama/mock_client.py` *(not in tests/)*

Follows `src/client/mock_client.py` convention — lives in `src/` so scripts and integration tests can import it without coupling to the test tree:

```python
"""MockNuvamaClient — offline substitute for Nuvama APIConnect SDK."""
from __future__ import annotations
import json


class MockNuvamaClient:
    """Satisfies NuvamaClient protocol. See src/client/mock_client.py for the pattern."""

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

Tests: `isinstance(MockNuvamaClient(), NuvamaClient)` must be `True`. Add to `tests/unit/nuvama/test_protocol.py` (new file).

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

### Step B: Eliminate All Extra LTP Fetches (AR-11)

**Depends on:** Step A (daily_snapshot.py must be stable)

**Actual problem — three fetches, not two:**
1. `_async_main` line ~406: `prices = await client.get_ltp(all_keys | {NIFTY_INDEX_KEY})` — master batch
2. Inside `record_all_strategies` → `record_daily_snapshot` → `self.market.get_ltp(instrument_keys)` — per-strategy refetch
3. `compute_pnl(strategy.name)` → `self.market.get_ltp(instrument_keys)` — per-strategy refetch again

The partial fix (returning `StrategyPnL` from `record_all_strategies`) eliminates #3 but leaves #2 — going from 5 total fetches to 3, not 1.

**Correct fix:** Add `prices: dict[str, float] | None = None` to `record_daily_snapshot` and `record_all_strategies`. When provided, skip the internal `get_ltp` call. Compute `StrategyPnL` inline from the passed prices.

#### [MODIFY] `src/portfolio/tracker.py`

```python
def _build_strategy_pnl(
    self, strategy: Strategy, prices: dict[str, float]
) -> StrategyPnL:
    """Compute StrategyPnL from an already-fetched prices dict."""
    leg_pnls = []
    for leg in strategy.legs:
        raw_ltp = prices.get(leg.instrument_key)
        ltp = Decimal(str(raw_ltp)) if raw_ltp is not None else leg.entry_price
        leg_pnls.append(LegPnL(leg=leg, current_price=ltp, pnl=leg.pnl(ltp), pnl_percent=leg.pnl_percent(ltp)))
    return StrategyPnL(strategy_name=strategy.name, legs=leg_pnls)

async def record_daily_snapshot(
    self,
    strategy_name: str,
    snapshot_date: date | None = None,
    underlying_price: float | None = None,
    prices: dict[str, float] | None = None,  # NEW — skip internal get_ltp if provided
) -> tuple[int, StrategyPnL | None]:  # was: int
    ...
    if prices is None:
        prices = await self.market.get_ltp(instrument_keys)
    # record snapshots using prices (unchanged logic)
    ...
    pnl = self._build_strategy_pnl(strategy, prices)
    return count, pnl

async def record_all_strategies(
    self,
    snapshot_date: date | None = None,
    underlying_price: float | None = None,
    prices: dict[str, float] | None = None,  # NEW — passed through
) -> tuple[dict[str, int], dict[str, StrategyPnL | None]]:
    ...
    count, pnl = await self.record_daily_snapshot(
        strategy.name, snapshot_date, underlying_price, prices=prices
    )
```

#### [MODIFY] `scripts/daily_snapshot.py` (lines 424–443)

```python
# AFTER — pass master prices, drop all compute_pnl calls
results, strategy_pnls = await tracker.record_all_strategies(
    snapshot_date=snap_date,
    underlying_price=underlying_price,
    prices=prices,  # master prices already fetched at line ~406
)
for strategy in strategies:
    count = results.get(strategy.name, 0)
    pnl = strategy_pnls.get(strategy.name)
    # print block unchanged
```

LTP fetches: **5 → 1** (master batch only). `compute_pnl` is no longer called in `_async_main`.

Tests:
- Update `test_record_all_strategies` for new `(counts, pnls)` return type
- Update `test_record_daily_snapshot` for new `(count, pnl)` return type  
- Add `test_record_daily_snapshot_uses_provided_prices` — assert `market.get_ltp` NOT called when `prices` kwarg is provided
- Add `test_record_all_strategies_single_ltp_call` — mock tracker, assert single `get_ltp` call for 2-strategy portfolio

---

## Verification Plan

### After Phase 1 (each agent independently)
```bash
python -m pytest tests/unit/ -v --tb=short
# Expected: 859+ passing, same pre-existing failures
```

### After Phase 2
```bash
python -m pytest tests/unit/ -v --tb=short
# Expected: 859+ passing
UPSTOX_ENV=test python -m scripts.daily_snapshot  # smoke test — single LTP batch fetch
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
| `refactor(nuvama): introduce NuvamaClient protocol and MockNuvamaClient` | AR-9a | `src/nuvama/protocol.py`, `src/nuvama/mock_client.py`, `reader.py`, `options_reader.py` |
| `refactor(scripts): defer I/O imports in nuvama_intraday_tracker` | AR-12 | `scripts/nuvama_intraday_tracker.py` |
| `refactor(nuvama): wire NuvamaClient type into scripts` | AR-9b | `scripts/daily_snapshot.py`, `scripts/nuvama_intraday_tracker.py` |
| `perf(tracker): eliminate all extra LTP fetches via prices pass-through` | AR-11 | `src/portfolio/tracker.py`, `scripts/daily_snapshot.py` |

Each commit: run `python -m pytest tests/unit/` → all green before tagging.
