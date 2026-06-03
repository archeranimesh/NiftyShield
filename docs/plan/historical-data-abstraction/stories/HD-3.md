# HD-3 — `HistoricalCandleFetcher` protocol

> Assigned to: Claude
> Phase: 2 — Fetcher Protocol + Upstox Implementation
> Blocked by: HD-1 and HD-2 must be merged first

---

## Goal

Define the `HistoricalCandleFetcher` protocol — the single interface that all vendor
implementations (Upstox, Dhan, Kite, NSE CSV) must satisfy. This is the seam that lets
`VixIngestPipeline` and future OHLC consumers switch vendors without changing calling code.

---

## Files to change

| File | Action |
|------|--------|
| `src/backtest/fetchers/__init__.py` | New package stub |
| `src/backtest/fetchers/protocol.py` | New — `HistoricalCandleFetcher` protocol |
| `tests/unit/backtest/test_fetcher_protocol.py` | New — protocol conformance tests |

---

## What to implement

### `src/backtest/fetchers/protocol.py`

```python
from typing import Protocol, runtime_checkable
from src.models.candles import CandleRecord, CandleRequest

@runtime_checkable
class HistoricalCandleFetcher(Protocol):
    """Fetches historical OHLC candle data for a given instrument and date range.

    All implementations must:
    - Return CandleRecord list sorted ascending by date
    - Return an empty list (not raise) when no data exists for the range
    - Never return duplicate dates for the same instrument + interval
    - Translate broker-native prices to float (Parquet schema is float64)
    - Honour the CandleRequest date range exactly — do not silently truncate

    Implementations are responsible for their own rate-limit handling and retries.
    They must not cache results internally — caching belongs in the pipeline layer.
    """

    async def fetch(self, request: CandleRequest) -> list[CandleRecord]:
        """Fetch candles for the given request.

        Args:
            request: Validated CandleRequest specifying instrument, interval,
                     and date range.

        Returns:
            List of CandleRecord sorted by date ascending. Empty list if no
            data is available for the requested range.

        Raises:
            DataFetchError: On unrecoverable network or API errors.
            RateLimitError: If rate limit is hit and retries are exhausted.
        """
        ...

    def supports_interval(self, interval: CandleInterval) -> bool:
        """Return True if this fetcher supports the given interval.

        Used by factory / pipeline to select the correct fetcher when multiple
        are registered. A fetcher that does not support an interval must return
        False here rather than raising at fetch time.
        """
        ...
```

`@runtime_checkable` is required for `isinstance` guards in `build_historical_fetcher()`.

---

## Tests — `tests/unit/backtest/test_fetcher_protocol.py`

1. **Protocol is runtime-checkable:** create a conforming class without inheriting from the protocol → `isinstance(obj, HistoricalCandleFetcher)` → `True`.
2. **Missing `fetch`:** class with `supports_interval` only → `isinstance` → `False`.
3. **Missing `supports_interval`:** class with `fetch` only → `isinstance` → `False`.
4. **Both methods required:** only a class with both satisfies the protocol.

---

## Commit message

```
feat(backtest): HistoricalCandleFetcher protocol

Why: defines the seam for swappable vendor fetch implementations;
     gates HD-4 through HD-8 implementations.
What:
- src/backtest/fetchers/__init__.py: new package stub
- src/backtest/fetchers/protocol.py: HistoricalCandleFetcher runtime-checkable Protocol
- tests/unit/backtest/test_fetcher_protocol.py: 4 protocol conformance tests
Ref: docs/plan/historical-data-abstraction/stories/HD-3.md
```

---

## Pre-baked graph context

```
search_graph("MarketDataParser")         # mirror this protocol pattern exactly
search_graph("CandleRecord")             # confirm HD-1 shipped
search_graph("CandleRequest")            # confirm HD-2 shipped
search_graph("DataFetchError")           # exception to reference in docstring
search_graph("RateLimitError")           # exception to reference in docstring
```
