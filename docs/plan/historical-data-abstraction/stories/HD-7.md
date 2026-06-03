# HD-7 — `KiteCandleFetcher` implementation

> Assigned to: Antigravity
> Phase: 3 — Alternative Vendor Implementations
> Blocked by: HD-3 must be merged first
> ⚠️  CONDITIONAL: Implement only if HD-0 decision matrix recommends Kite for OHLC.
>    If HD-0 marks Kite as "skip", mark this task `[x] skipped — HD-0 decision`.
> ⚠️  Kite Connect API costs ₹2000/month. Confirm subscription active before starting.

---

## Goal

Implement `KiteCandleFetcher` using the Kite Connect historical data API.
Kite has the widest lookback (3Y+ observed in HD-0 probes) but costs ₹2000/month.
Only build this if HD-0 confirms Kite is meaningfully better than Upstox for a specific
use case (e.g. longer pre-2020 VIX history, lower gap rate).

---

## Context: Kite Connect historical API

Endpoint: `GET https://api.kite.trade/instruments/historical/{instrument_token}/{interval}`

Query params: `from=YYYY-MM-DD+HH:MM:SS`, `to=YYYY-MM-DD+HH:MM:SS`, `continuous=0`, `oi=1`

Interval strings: `minute`, `3minute`, `5minute`, `10minute`, `15minute`, `30minute`,
`60minute`, `day`, `week`, `month`.

`instrument_token` is Kite's numeric integer ID (from the instruments CSV).
Use `KiteInstrumentKeyAdapter` (BA-7) to translate canonical key → Kite token.

Response shape:
```json
{
  "status": "success",
  "data": {
    "candles": [
      ["2026-01-02 00:00:00", 23000.0, 23100.0, 22900.0, 23050.0, 12345, 0],
      ...
    ]
  }
}
```

Column order: `[datetime_str, open, high, low, close, volume, oi]`
Datetime strings are IST. Parse with `datetime.strptime(s, "%Y-%m-%d %H:%M:%S").date()`
for daily candles.

---

## Files to change

| File | Action |
|------|--------|
| `src/backtest/fetchers/kite.py` | New — `KiteCandleFetcher` |
| `tests/unit/backtest/test_fetcher_kite.py` | New — 7 tests with mocked aiohttp |
| `tests/fixtures/responses/kite_candles_vix.json` | New — 5-row Kite candle fixture |

---

## What to implement

```python
_INTERVAL_MAP = {
    CandleInterval.DAY: "day",
    CandleInterval.WEEK: "week",
    CandleInterval.MINUTE_1: "minute",
    CandleInterval.MINUTE_5: "5minute",
    CandleInterval.MINUTE_15: "15minute",
    CandleInterval.MINUTE_30: "30minute",
    CandleInterval.HOUR_1: "60minute",
}
_BASE_URL = "https://api.kite.trade/instruments/historical"
_SUPPORTED = frozenset(_INTERVAL_MAP.keys())

class KiteCandleFetcher:
    """HistoricalCandleFetcher for Kite Connect historical data API.

    Requires an active Kite Connect subscription (₹2000/month).
    Use KiteInstrumentKeyAdapter to resolve canonical keys to Kite instrument tokens.
    """

    def __init__(
        self,
        adapter: InstrumentKeyAdapter | None = None,
        api_key: str | None = None,
        access_token: str | None = None,
    ) -> None:
        ...

    async def fetch(self, request: CandleRequest) -> list[CandleRecord]: ...
    def supports_interval(self, interval: CandleInterval) -> bool: ...
```

Auth header: `Authorization: token {api_key}:{access_token}`

---

## Tests — `tests/unit/backtest/test_fetcher_kite.py`

Mirror HD-4 test list exactly (7 tests).

---

## Commit message

```
feat(backtest): KiteCandleFetcher for Kite Connect historical API

Why: provides Kite as an alternative historical OHLC source per HD-0 decision matrix
     (widest lookback; requires ₹2000/month subscription).
What:
- src/backtest/fetchers/kite.py: KiteCandleFetcher conforming to HistoricalCandleFetcher
- tests/unit/backtest/test_fetcher_kite.py: 7 tests with mocked aiohttp
- tests/fixtures/responses/kite_candles_vix.json: 5-row Kite candle fixture
Ref: docs/plan/historical-data-abstraction/stories/HD-7.md
```

---

## Pre-baked graph context

```
search_graph("HistoricalCandleFetcher")  # protocol
search_graph("UpstoxCandleFetcher")      # reference implementation
search_graph("KiteInstrumentKeyAdapter") # confirm BA-7 shipped
search_graph("kite_api_key")             # settings field name
```
