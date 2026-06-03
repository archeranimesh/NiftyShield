# HD-9 — Implement `get_historical_candles` in `UpstoxLiveClient`

> Assigned to: Claude
> Phase: 4 — Wire into `BrokerClient` Protocol
> Blocked by: HD-4 must be merged first (`UpstoxCandleFetcher` must exist)

---

## Goal

`UpstoxLiveClient.get_historical_candles()` currently raises `NotImplementedError`.
Wire it to delegate to `UpstoxCandleFetcher`, closing the gap between the `BrokerClient`
protocol declaration and the actual implementation.

---

## Files to change

| File | Action |
|------|--------|
| `src/client/upstox_live.py` | Edit — implement `get_historical_candles` via `UpstoxCandleFetcher` |
| `tests/unit/client/test_upstox_live.py` | Extend — `get_historical_candles` happy path + error test |

---

## What to implement

### `src/client/upstox_live.py`

```python
async def get_historical_candles(self, params: CandleRequest) -> list[CandleRecord]:
    """Fetch historical OHLC candles via UpstoxCandleFetcher.

    Args:
        params: CandleRequest specifying instrument, interval, and date range.

    Returns:
        List of CandleRecord sorted ascending by date.

    Raises:
        DataFetchError: On API errors.
    """
    fetcher = UpstoxCandleFetcher(token=self._analytics_token)
    return await fetcher.fetch(params)
```

`self._analytics_token` is the Analytics Token already stored on the client for
`get_ltp` and `get_option_chain`. No new constructor params needed.

---

## Tests — extend `tests/unit/client/test_upstox_live.py`

1. **Happy path:** `UpstoxLiveClient.get_historical_candles(request)` with mocked `UpstoxCandleFetcher.fetch` → returns `CandleRecord` list.
2. **DataFetchError propagation:** mocked fetcher raises `DataFetchError` → client propagates it unchanged.
3. **No longer raises NotImplementedError:** calling `get_historical_candles` does not raise `NotImplementedError`.

---

## Commit message

```
feat(client): implement get_historical_candles in UpstoxLiveClient

Why: closes the NotImplementedError gap in BrokerClient protocol implementation;
     delegates to UpstoxCandleFetcher.
What:
- src/client/upstox_live.py: get_historical_candles delegates to UpstoxCandleFetcher
- tests/unit/client/test_upstox_live.py: 3 additional tests
Ref: docs/plan/historical-data-abstraction/stories/HD-9.md
```

---

## Pre-baked graph context

```
search_graph("UpstoxLiveClient")         # constructor fields — find analytics_token attribute name
search_graph("get_historical_candles")   # current NotImplementedError impl
search_graph("UpstoxCandleFetcher")      # confirm HD-4 shipped
search_graph("CandleRequest")            # confirm HD-2 shipped
```
