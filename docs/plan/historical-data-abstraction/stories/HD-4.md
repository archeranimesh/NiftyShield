# HD-4 — `UpstoxCandleFetcher` implementation

> Assigned to: Antigravity
> Phase: 2 — Fetcher Protocol + Upstox Implementation
> Blocked by: HD-3 must be merged first

---

## Goal

Wrap the existing `ingest_vix_from_api` and `fetch_vix_latest` logic from
`src/backtest/vix_ingest.py` into a proper `HistoricalCandleFetcher` implementation.
The existing module-level functions are not deleted — they are replaced by a class
that the functions will delegate to in HD-5.

Key problems with the current implementation to fix here:
- Uses synchronous `requests.get` — replace with `aiohttp` (async, consistent with the rest of the codebase)
- `float(candles[0][4])` — raw float from API; keep as float for Parquet compatibility but validate it is finite
- No `supports_interval` logic — hard-codes daily candles; make explicit

---

## Files to change

| File | Action |
|------|--------|
| `src/backtest/fetchers/upstox.py` | New — `UpstoxCandleFetcher` |
| `tests/unit/backtest/test_fetcher_upstox.py` | New — fetcher tests using fixtures |
| `tests/fixtures/responses/upstox_candles_vix.json` | New — minimal candle fixture (5 rows) |

---

## What to implement

### `src/backtest/fetchers/upstox.py`

```python
_HISTORICAL_URL = "https://api.upstox.com/v2/historical-candle/{key}/{interval}/{to_date}"
_INTERVAL_MAP = {
    CandleInterval.DAY: "day",
    CandleInterval.WEEK: "week",
    CandleInterval.MINUTE_1: "1minute",
    CandleInterval.MINUTE_5: "5minute",
    CandleInterval.MINUTE_15: "15minute",
    CandleInterval.MINUTE_30: "30minute",
    CandleInterval.HOUR_1: "60minute",
}
_SUPPORTED = frozenset(_INTERVAL_MAP.keys())

class UpstoxCandleFetcher:
    """HistoricalCandleFetcher for Upstox Analytics Token API.

    Fetches historical OHLC candles using the Upstox v2 historical-candle endpoint.
    Requires UPSTOX_ANALYTICS_TOKEN — not the daily OAuth access token.

    Rate limits: Upstox does not publish rate limits for the analytics endpoint.
    Empirically safe at ~5 requests/second. Add 200ms sleep between paginated calls.
    """

    def __init__(self, token: str | None = None) -> None:
        self._token = token or settings.upstox_analytics_token

    async def fetch(self, request: CandleRequest) -> list[CandleRecord]:
        ...

    def supports_interval(self, interval: CandleInterval) -> bool:
        return interval in _SUPPORTED
```

Parsing rules (from existing `ingest_vix_from_api`):
- Candle array: `[timestamp_str, open, high, low, close, volume, oi]`
- `date` = `pd.to_datetime(c[0]).tz_localize(None).normalize().date()`
- All price fields = `float(c[N])` — keep float (Parquet schema)
- Sort result ascending by date before returning
- Return `[]` (not raise) when API returns `candles: []`
- Raise `DataFetchError` on HTTP errors

Missing token: return `[]` with a structured log warning — do not raise (matches existing `fetch_vix_latest` behaviour).

---

## Fixture — `tests/fixtures/responses/upstox_candles_vix.json`

```json
{
  "status": "success",
  "data": {
    "candles": [
      ["2026-05-26T00:00:00+05:30", 14.23, 15.10, 13.98, 14.87, 0, 0],
      ["2026-05-27T00:00:00+05:30", 14.87, 15.32, 14.50, 15.01, 0, 0],
      ["2026-05-28T00:00:00+05:30", 15.01, 15.45, 14.75, 14.92, 0, 0],
      ["2026-05-29T00:00:00+05:30", 14.92, 15.20, 14.60, 15.15, 0, 0],
      ["2026-05-30T00:00:00+05:30", 15.15, 15.88, 14.90, 15.67, 0, 0]
    ]
  }
}
```

---

## Tests — `tests/unit/backtest/test_fetcher_upstox.py`

Mock `aiohttp.ClientSession` — no network calls.

1. **Happy path:** fixture response → 5 `CandleRecord` rows, sorted ascending, correct `close` values.
2. **Empty candles:** API returns `candles: []` → returns `[]`, no exception.
3. **Missing token:** `UpstoxCandleFetcher(token=None)` with no env var → `fetch()` returns `[]` and logs warning.
4. **HTTP error:** mock returns 500 → raises `DataFetchError`.
5. **`supports_interval`:** `DAY` → `True`; a hypothetical `"tick"` interval → `False`.
6. **Protocol conformance:** `isinstance(UpstoxCandleFetcher(), HistoricalCandleFetcher)` → `True`.
7. **Sort order:** fixture with out-of-order dates → result is ascending by date.

---

## Commit message

```
feat(backtest): UpstoxCandleFetcher — async aiohttp implementation

Why: replaces sync requests.get in vix_ingest with async fetcher conforming
     to HistoricalCandleFetcher protocol.
What:
- src/backtest/fetchers/upstox.py: UpstoxCandleFetcher with aiohttp + CandleRecord output
- tests/unit/backtest/test_fetcher_upstox.py: 7 tests with mocked aiohttp
- tests/fixtures/responses/upstox_candles_vix.json: 5-row candle fixture
Ref: docs/plan/historical-data-abstraction/stories/HD-4.md
```

---

## Pre-baked graph context

```
search_graph("ingest_vix_from_api")      # exact parsing logic to port
search_graph("HistoricalCandleFetcher")  # confirm HD-3 shipped
search_graph("DataFetchError")           # exception class + import path
search_graph("CandleRecord")             # field names + types
git log --oneline -10 src/backtest/vix_ingest.py
```
