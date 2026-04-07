# NiftyShield Code Review

**Reviewer:** Claude (channelling Guido van Rossum + Linus Torvalds)
**Date:** 2026-04-04
**Scope:** Full codebase — every .py file under src/, scripts/, tests/
**Verdict:** Solid for a 4-day-old project. A few structural issues to fix before the next feature lands.

---

## Executive Summary

The codebase is well-structured, thoroughly tested (168 offline tests), and shows disciplined engineering: immutable Pydantic models, Decimal precision for money, idempotent seeds, injectable dependencies. CONTEXT.md is excellent — treat it as the project's constitution.

There are **3 issues I'd block a PR on**, **7 that should be fixed soon**, and **5 stylistic improvements** that would pay off as the codebase grows.

---

## Blocking Issues

### 1. Python version claim vs reality — `StrEnum` requires 3.11+

`src/portfolio/models.py` line 10:

```python
from enum import StrEnum
```

The project instructions say "Python 3.10+", but `StrEnum` was introduced in 3.11. This isn't academic — running `pytest` on a 3.10 box fails at collection time. Every single test file that transitively imports `portfolio.models` is dead.

**Fix:** Either bump the minimum to 3.11 in `pyproject.toml` and CONTEXT.md, or replace `StrEnum` with `(str, Enum)` which works on 3.10:

```python
class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
```

Note that `src/mf/models.py` already uses `(str, Enum)` for `TransactionType` — so the two modules are inconsistent with each other. Pick one pattern and apply it everywhere.

### 2. `_connect()` is duplicated between `PortfolioStore` and `MFStore`

Both stores have an identical `_connect()` context manager (WAL mode, row_factory, foreign keys, commit/rollback/close). When you fix a bug or change a PRAGMA in one, you have to remember to change the other. You won't.

**Fix:** Extract a shared `_connect()` into a base class or a standalone function in a `src/db.py` module:

```python
# src/db.py
@contextmanager
def connect(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

Both stores import and use it. Same semantics, one source of truth. This also makes it trivial to add connection pooling or retry logic later.

### 3. `portfolio/__init__.py` eagerly imports everything — breaks lazy loading and circular import safety

```python
from src.portfolio.models import (AssetType, DailySnapshot, Direction, Leg, ProductType, Strategy)
from src.portfolio.store import PortfolioStore
```

This means `import src.portfolio` triggers the full chain: models → store → sqlite3. In a project that's growing toward streaming, strategy engine, and risk modules, eager top-level imports in `__init__.py` create circular import hazards and slow startup. The `mf/__init__.py` is empty — correct pattern.

**Fix:** Make `portfolio/__init__.py` empty (or minimal). Let consumers import what they need directly: `from src.portfolio.models import Leg`. This is standard Python packaging practice for projects larger than a single module.

---

## Should-Fix Issues

### 4. `entry_price` and `ltp` stored as `float` in portfolio, but as `Decimal` (via TEXT) in MF

Portfolio's `Leg.entry_price`, `DailySnapshot.ltp`, and all `PortfolioStore` columns use `REAL` (float). MF's `MFTransaction.units`, `MFTransaction.amount`, and all `MFStore` columns use `TEXT` to preserve `Decimal` precision. Then `daily_snapshot.py` line 100 does this to bridge the gap:

```python
Decimal(str(p.total_pnl))
```

This is the kind of code that looks fine until you get a float like `0.1 + 0.2 = 0.30000000000000004` and your combined P&L is off by a paisa. You already solved this correctly in `mf/` — apply the same pattern to `portfolio/`.

**Fix (incremental, not a rewrite):**
- Change `Leg.entry_price` to `Decimal`. Update `DailySnapshot.ltp` and `close` similarly.
- Change `PortfolioStore` columns from `REAL` to `TEXT`, with `str()/Decimal()` round-trip.
- `StrategyPnL.total_pnl` becomes `Decimal` instead of `float`.
- The `Decimal(str(...))` bridging code disappears.

This is a schema migration on a 4-day-old wiped DB — there's no live data to migrate. Do it now before the first real snapshot on Monday.

### 5. ETF leg identification by string prefix is fragile

`daily_snapshot.py` line 58:

```python
if leg.instrument_key.startswith("NSE_EQ|"):
```

The `Leg` model already has `asset_type: AssetType`. Use it:

```python
if leg.asset_type == AssetType.EQUITY:
```

The string prefix check breaks if Upstox ever changes key format, or if you add BSE equity legs. The enum is the canonical source of truth — that's why it exists.

### 6. `daily_snapshot.py` calls `asyncio.run()` twice — creates two event loops

Lines 200-201 and 214:

```python
results = asyncio.run(tracker.record_all_strategies(...))
# ...
pnl = asyncio.run(tracker.compute_pnl(strategy.name))
```

Each `asyncio.run()` creates and destroys an event loop. This works, but it's wasteful and will break if you ever need to share state across async calls (connection pools, rate limiters). The second call is also inside a loop — so you create N event loops for N strategies.

**Fix:** Wrap the entire `main()` body in a single `asyncio.run()` that calls an `async def _async_main()`:

```python
async def _async_main(args) -> int:
    # ... all async work here ...
    results = await tracker.record_all_strategies(...)
    for strategy in strategies:
        pnl = await tracker.compute_pnl(strategy.name)

def main() -> int:
    # ... parse args, setup ...
    return asyncio.run(_async_main(args))
```

### 7. `sys.modules` stubbing in tests is a maintenance landmine

`test_daily_snapshot_helpers.py` manipulates `sys.modules` at module level to stub out `dotenv`, `src.client`, and `src.portfolio.tracker` before importing `daily_snapshot`. Then it has to carefully tear down the `src.portfolio.tracker` stub to prevent poisoning other tests.

CONTEXT.md line 168 already documents that this broke once and was fixed. It will break again.

**Fix:** The root cause is that `daily_snapshot.py` performs side effects at import time (`load_dotenv()`, module-level imports of heavy clients). Refactor so the imports happen inside `main()` or behind a guard:

```python
# daily_snapshot.py — move heavy imports inside main()
def main() -> int:
    from dotenv import load_dotenv
    load_dotenv()
    from src.client.upstox_market import UpstoxMarketClient
    # ...
```

Then `_etf_current_value` and `_etf_cost_basis` can be imported without any stubbing — they don't depend on dotenv or the market client at all. Better yet, move them to a `src/portfolio/helpers.py` so they're not trapped inside a script module.

### 8. `UpstoxMarketClient` swallows errors silently

`upstox_market.py` lines 170-173:

```python
except requests.RequestException as e:
    logger.error("LTP fetch failed for batch: %s", e)
    return {}
```

When the API returns a 500 or times out, you get an empty dict back, and the snapshot proceeds with `ltp = 0.0` for every leg. The caller has no way to distinguish "API is down" from "all instruments have been delisted." For a trading system, a silent degradation to zero prices is dangerous — it distorts P&L and could trigger false signals.

**Fix:** Let the exception propagate (or wrap it in a custom `DataFetchError`). The caller (`daily_snapshot.py`) already checks `if not prices: return 1` — let it handle the failure explicitly rather than receiving a partial result that looks successful.

At minimum, raise on total failure (empty response or HTTP error) and return partial results only when some instruments succeed and others don't.

### 9. No `__all__` in `src/client/__init__.py` or `src/instruments/__init__.py`

Both are empty `__init__.py` files. That's fine for now, but add them before these modules grow — it prevents `from src.client import *` from pulling in internals.

### 10. `insert_transaction` opens and closes a connection per row

`MFStore.insert_transaction()` opens a connection, inserts one row, commits, closes. When called in a loop (which the bulk method avoids), this is N connections for N transactions. The `seed_holdings()` function correctly uses `insert_transactions_bulk()`, but future SIP scripts might use the single-row method in a loop by mistake.

**Fix:** Document the single-row method as "use for individual SIP events only." Or better — accept a `conn` parameter optionally for callers that want to batch within an existing transaction.

---

## Style and Maintainability

### 11. Type annotation: `list` vs `list[...]` for untyped strategy lists

`daily_snapshot.py` lines 42 and 64:

```python
def _etf_current_value(strategies: list, prices: dict[str, float]) -> Decimal:
def _etf_cost_basis(strategies: list) -> Decimal:
```

Bare `list` loses all type information. The tests use fake `_Strategy` dataclasses because the type is unspecified. Use `list[Strategy]` — this is a typed codebase, and these functions only work with `Strategy` objects.

### 12. Inconsistent `Enum` base class

`portfolio/models.py` uses `StrEnum` (3.11+). `mf/models.py` uses `(str, Enum)` (3.10+). Pick one.

### 13. `_HOLDINGS` tuple structure is implicit

`seed_mf_holdings.py` line 36:

```python
_HOLDINGS: list[tuple[str, str, str, str]] = [
    ("104481", "DSP Midcap Fund - Regular Plan - Growth", "4020.602", "439978.00"),
```

Four strings with no names. You have to count positions to know which is code, name, units, amount. A `NamedTuple` or `TypedDict` would make this self-documenting:

```python
class HoldingEntry(NamedTuple):
    amfi_code: str
    scheme_name: str
    units: str
    amount: str
```

### 14. `_print_combined_summary` mixes computation and presentation

`daily_snapshot.py` line 81 computes `total_value`, `total_invested`, `total_pnl`, `total_pnl_pct` and immediately prints them. When you add P&L visualization or a React dashboard, you'll need these values as data, not as print statements.

Extract a `PortfolioSummary` frozen dataclass (CONTEXT.md line 77 already calls this out) and separate the computation from the display. The compute function returns the dataclass; the print function formats it.

### 15. Logging config is absent

No `logging.basicConfig()` or `logging.config` setup anywhere. The `logger = logging.getLogger(__name__)` calls throughout the codebase are correct, but without a root logger configuration, all those `logger.warning()` calls in `nav_fetcher.py`, `tracker.py`, etc. go to `/dev/null` unless the caller happens to set up logging.

**Fix:** Add a `src/utils/logging_setup.py` (or configure in `daily_snapshot.py` at minimum):

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
```

---

## What's Done Well

These aren't filler compliments — they're patterns I'd want preserved as the codebase grows:

**Decimal discipline in MF module.** `TEXT` columns, `Decimal` everywhere, quantization only at display boundaries. This is how you handle money. Apply it to portfolio/ too.

**Injectable `nav_fetcher` as `Callable[[set[str]], dict[str, Decimal]]`.** Clean dependency injection without a framework. Tests pass a lambda. Production gets the real AMFI fetcher. No interface class needed.

**Idempotent seeds with `ON CONFLICT DO NOTHING`.** Re-runnable without fear. Combined with the `build_transactions()` / `seed_holdings()` split, the seed logic is independently testable.

**CONTEXT.md as single source of truth.** Every decision is documented with rationale. The session log tracks what was built when. This is better than most production codebases I've reviewed.

**`MarketDataProvider` protocol with `@runtime_checkable`.** Correct use of structural subtyping. The tracker doesn't know or care whether it's talking to Upstox or a mock.

**Frozen dataclasses for computed P&L types.** `SchemePnL`, `PortfolioPnL`, `LegPnL`, `StrategyPnL` — all immutable. Prevents accidental mutation in the display layer.

---

## Priority Order for Fixes

| # | Issue | Effort | Impact | When |
|---|-------|--------|--------|------|
| 1 | StrEnum → (str, Enum) or bump to 3.11 | 10 min | Tests run on 3.10 | Now |
| 2 | Extract shared `_connect()` to `src/db.py` | 30 min | DRY, single bug-fix point | Now |
| 3 | Empty `portfolio/__init__.py` | 5 min | Prevents circular imports | Now |
| 4 | Portfolio float → Decimal | 2 hrs | Precision parity with MF | Before Monday snapshot |
| 5 | `AssetType.EQUITY` instead of string prefix | 5 min | Correctness | Before Monday snapshot |
| 6 | Single `asyncio.run()` in daily_snapshot | 20 min | Clean event loop | Before Monday snapshot |
| 7 | Refactor daily_snapshot imports for testability | 1 hr | Kill sys.modules stubs | Next commit |
| 8 | UpstoxMarketClient error propagation | 30 min | Safety | Next commit |

---

## Summary

The architecture is sound. The test coverage for a 4-day project is impressive. CONTEXT.md is a model for how to document a growing codebase. The main risks are the float/Decimal inconsistency between the two store modules (fix before real data starts accumulating) and the module-level import side effects in daily_snapshot.py (fix before the test suite becomes unmaintainable).

Fix the blocking issues, tackle the should-fixes before Monday's first snapshot, and this codebase is in good shape for the BrokerClient protocol layer and trade history model that come next.
