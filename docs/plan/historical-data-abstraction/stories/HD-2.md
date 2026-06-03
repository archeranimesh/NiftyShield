# HD-2 — `CandleRequest` Pydantic model (resolves TD-7)

> Assigned to: Claude
> Phase: 1 — Canonical Models
> Blocked by: HD-1 (needs `CandleInterval` enum)

---

## Goal

`CandleRequest = dict[str, Any]` in `src/client/protocol.py` is the other TD-7 stub.
Replace it with a typed Pydantic model so every fetcher and caller has a validated,
self-documenting request shape.

---

## Files to change

| File | Action |
|------|--------|
| `src/models/candles.py` | Edit — add `CandleRequest` model |
| `src/client/protocol.py` | Edit — replace `CandleRequest = dict[str, Any]` with import |
| `tests/unit/models/test_candles.py` | Extend — add `CandleRequest` validation tests |

---

## What to implement

### `src/models/candles.py` — add `CandleRequest`

```python
class CandleRequest(BaseModel, frozen=True):
    """Broker-agnostic request parameters for historical OHLC candles.

    Fetcher implementations translate these fields into their broker-native
    request format. No broker-specific fields here.
    """
    instrument_key: str          # canonical "EXCHANGE_SEGMENT|TOKEN" or index key
    interval: CandleInterval
    from_date: date
    to_date: date

    @model_validator(mode="after")
    def date_range_valid(self) -> "CandleRequest":
        if self.from_date > self.to_date:
            raise ValueError(
                f"from_date ({self.from_date}) must be <= to_date ({self.to_date})"
            )
        return self
```

### `src/client/protocol.py`

```python
# Before
CandleRequest = dict[str, Any]  # TODO: TD-7 — replace with Pydantic model from src.models

# After
from src.models.candles import CandleRequest  # TD-7 resolved
```

Update `BrokerClient.get_historical_candles` signature accordingly:
```python
async def get_historical_candles(self, params: CandleRequest) -> list[CandleRecord]: ...
```

---

## Tests — extend `tests/unit/models/test_candles.py`

1. **Happy path:** `CandleRequest(instrument_key="NSE_INDEX|India VIX", interval=CandleInterval.DAY, from_date=date(2026,1,1), to_date=date(2026,1,31))` — validates.
2. **from_date > to_date:** raises `ValidationError`.
3. **from_date == to_date:** valid (single-day fetch).
4. **Frozen:** `req.to_date = date(2026,2,1)` → raises `ValidationError`.

---

## Commit message

```
feat(models): CandleRequest model; resolve TD-7 CandleRequest stub

Why: typed request params for HistoricalCandleFetcher calls; closes TD-7 for Candle + CandleRequest.
What:
- src/models/candles.py: CandleRequest frozen Pydantic model with date-range validator
- src/client/protocol.py: replace CandleRequest = dict[Any] with typed import
- tests/unit/models/test_candles.py: 4 additional CandleRequest tests
Ref: docs/plan/historical-data-abstraction/stories/HD-2.md
```

---

## Pre-baked graph context

```
search_graph("CandleRequest")           # confirm it's still dict[str, Any]
search_graph("CandleInterval")          # confirm HD-1 shipped first
search_graph("get_historical_candles")  # all callers — upstox_live raises NotImplementedError
```
