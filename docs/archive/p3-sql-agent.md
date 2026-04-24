---
model: claude-sonnet-4-5
description: P3 SQL performance fixes — AR-8 (GROUP BY in get_cumulative_realized_pnl) + AR-10 (N+1 elimination in get_all_positions_for_strategy). Safe to run in parallel with p3-protocol-agent and p3-script-hygiene-agent.
---

You are executing Phase 1, Stream A of the P3 performance sprint for NiftyShield.

## Your Scope (files you may touch)

- `src/nuvama/store.py` — AR-8
- `src/portfolio/store.py` — AR-10
- Test files as needed

**Do NOT touch:** `scripts/`, `src/nuvama/reader.py`, `src/nuvama/protocol.py`, `src/portfolio/tracker.py`.

---

## AR-8: SQL GROUP BY in `get_cumulative_realized_pnl`

**File:** `src/nuvama/store.py` — `NuvamaStore.get_cumulative_realized_pnl`

**Problem:** Fetches every `realized_pnl_today` row with no `GROUP BY` and aggregates by `trade_symbol` in Python. Grows unboundedly — hundreds of rows per 5-minute tick after one year.

**Fix:** Replace the Python loop with a single SQL aggregate:

```python
rows = conn.execute(
    """SELECT trade_symbol, SUM(realized_pnl_today) AS cumulative
       FROM nuvama_options_snapshots
       WHERE snapshot_date < ?
       GROUP BY trade_symbol""",
    (before_date.isoformat(),),
).fetchall()
return {row["trade_symbol"]: Decimal(str(row["cumulative"])) for row in rows}
```

**Decimal invariant:** `realized_pnl_today` is TEXT. `SUM()` on TEXT uses SQLite numeric affinity — result is correct but must be wrapped in `Decimal(str(...))`, not `Decimal(row["cumulative"])` directly.

**Tests:** Existing `test_get_cumulative_realized_pnl_*` tests validate — no test changes needed. Run them first to confirm green baseline, then apply fix, then confirm still green.

---

## AR-10: Eliminate N+1 in `get_all_positions_for_strategy`

**File:** `src/portfolio/store.py` — `PortfolioStore.get_all_positions_for_strategy` (lines 561–593)

**Problem:** Opens 1 connection for DISTINCT, then calls `get_position()` per leg — each opens a new connection and does a full table scan. 8 connections, 7 scans for 7 legs. Called twice per snapshot run.

**Fix:** One `_connect` block, one `SELECT *` across all trades for the strategy, full Python Decimal aggregation — no GROUP BY, no helper calls, no float anywhere in the price path:

```python
def get_all_positions_for_strategy(
    self, strategy_name: str
) -> dict[str, tuple[int, Decimal, str]]:
    """Derive net position for every leg in a single DB round-trip.

    Replaces the previous N+1 pattern (1 DISTINCT query + 1 get_position()
    per leg). One connection, one SELECT, Python Decimal aggregation.
    """
    from collections import defaultdict

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
        price = Decimal(row["price"])  # TEXT → Decimal, no float
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

> [!IMPORTANT]
> One `_connect`, one query — the connection count goes from 8 → 1 for a 7-leg strategy. No `CAST(price AS REAL)` anywhere; all arithmetic stays in Python Decimal.

**Tests:** All existing `test_trade_store.py` tests must stay green. Add one test: `test_get_all_positions_single_connection` — patch `_connect` as a spy, assert it is called exactly **once** for a 7-leg strategy.

---

## Protocol

1. `search_graph` or `get_code_snippet` to confirm current implementation before editing.
2. Run `python -m pytest tests/unit/nuvama/test_store.py tests/unit/portfolio/test_trade_store.py -v` — baseline green.
3. Apply AR-8.
4. Apply AR-10.
5. Run same tests — must stay green.
6. Run `python -m pytest tests/unit/ -v --tb=short` — full suite must stay at 859+ passing.
7. Generate commit messages using `.claude/skills/commit/SKILL.md` format. Two separate commits (one per AR).
