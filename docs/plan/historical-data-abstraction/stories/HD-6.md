# HD-6 — `DhanCandleFetcher` implementation

> Assigned to: Antigravity
> Phase: 3 — Alternative Vendor Implementations
> Blocked by: HD-3 must be merged first
> ⚠️  CONDITIONAL: Implement only if HD-0 decision matrix recommends Dhan for OHLC.
>    If HD-0 marks Dhan as "skip" for historical data, mark this task `[x] skipped — HD-0 decision`.

---

## Goal

Implement `DhanCandleFetcher` using Dhan's `/v2/charts/historical` endpoint.
Mirrors `UpstoxCandleFetcher` structure exactly — only URL, auth header, and response
parsing differ.

---

## Context: Dhan historical API

Endpoint: `POST https://api.dhan.co/v2/charts/historical`

Request body (JSON):
```json
{
  "securityId": "13",
  "exchangeSegment": "IDX_I",
  "instrument": "INDEX",
  "interval": "D",
  "fromDate": "2026-01-01",
  "toDate": "2026-01-31"
}
```

Interval codes: `"1"` (1-min), `"5"` (5-min), `"15"`, `"25"`, `"60"` (1-hour), `"D"` (daily), `"W"` (weekly).

Response shape:
```json
{
  "open": [23000.0, ...],
  "high": [23100.0, ...],
  "low": [22900.0, ...],
  "close": [23050.0, ...],
  "volume": [12345, ...],
  "timestamp": [1234567890, ...]
}
```

Timestamps are Unix epoch seconds (IST). Convert via `datetime.fromtimestamp(ts, tz=IST).date()`.

`securityId` for India VIX on Dhan: confirm from `DhanInstrumentKeyAdapter` (BA-4)
or from `REFERENCES.md`. If not documented, add it there.

---

## Files to change

| File | Action |
|------|--------|
| `src/backtest/fetchers/dhan.py` | New — `DhanCandleFetcher` |
| `tests/unit/backtest/test_fetcher_dhan.py` | New — 7 tests with mocked aiohttp |
| `tests/fixtures/responses/dhan_candles_vix.json` | New — 5-row Dhan candle fixture |

---

## What to implement

```python
_INTERVAL_MAP = {
    CandleInterval.DAY: "D",
    CandleInterval.WEEK: "W",
    CandleInterval.MINUTE_1: "1",
    CandleInterval.MINUTE_5: "5",
    CandleInterval.MINUTE_15: "15",
    CandleInterval.HOUR_1: "60",
}
_SUPPORTED = frozenset(_INTERVAL_MAP.keys())

class DhanCandleFetcher:
    """HistoricalCandleFetcher for Dhan /v2/charts/historical endpoint."""

    def __init__(
        self,
        adapter: InstrumentKeyAdapter | None = None,
        client_id: str | None = None,
        access_token: str | None = None,
    ) -> None:
        self._adapter = adapter or DhanInstrumentKeyAdapter(...)
        self._client_id = client_id or settings.dhan_client_id
        self._token = access_token or settings.dhan_access_token

    async def fetch(self, request: CandleRequest) -> list[CandleRecord]:
        # translate canonical key → Dhan securityId via adapter
        # POST to /v2/charts/historical
        # parse columnar response → list[CandleRecord]
        ...

    def supports_interval(self, interval: CandleInterval) -> bool:
        return interval in _SUPPORTED
```

Parsing rules:
- Response is columnar (parallel arrays) — zip `timestamp`, `open`, `high`, `low`, `close`, `volume`
- Convert Unix timestamp to IST date
- Sort ascending by date
- Return `[]` on empty arrays
- Raise `DataFetchError` on HTTP error

---

## Tests — `tests/unit/backtest/test_fetcher_dhan.py`

Mirror HD-4 test list exactly (7 tests). Use `tests/fixtures/responses/dhan_candles_vix.json`.

1. Happy path — 5 rows, correct close values
2. Empty response — returns `[]`
3. Missing credentials — returns `[]`, logs warning
4. HTTP error — raises `DataFetchError`
5. `supports_interval` — `DAY` True, unsupported False
6. Protocol conformance — `isinstance(DhanCandleFetcher(...), HistoricalCandleFetcher)` True
7. Sort order — ascending by date

---

## Commit message

```
feat(backtest): DhanCandleFetcher for /v2/charts/historical endpoint

Why: provides Dhan as an alternative historical OHLC source per HD-0 decision matrix.
What:
- src/backtest/fetchers/dhan.py: DhanCandleFetcher conforming to HistoricalCandleFetcher
- tests/unit/backtest/test_fetcher_dhan.py: 7 tests with mocked aiohttp
- tests/fixtures/responses/dhan_candles_vix.json: 5-row Dhan candle fixture
Ref: docs/plan/historical-data-abstraction/stories/HD-6.md
```

---

## Pre-baked graph context

```
search_graph("HistoricalCandleFetcher")  # protocol — confirm HD-3 shipped
search_graph("UpstoxCandleFetcher")      # reference implementation to mirror
search_graph("DhanInstrumentKeyAdapter") # confirm BA-4 shipped; needed for key translation
search_graph("dhan_client_id")           # settings field name
```
