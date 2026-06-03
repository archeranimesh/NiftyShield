# HD-1 — `CandleRecord` Pydantic model + `CandleInterval` enum

> Assigned to: Claude
> Phase: 1 — Canonical Models
> Blocked by: HD-0 must be complete (decision matrix may influence interval enum members)

---

## Goal

`Candle = dict[str, Any]` in `src/client/protocol.py` is a TODO stub (TD-7). Before writing
any fetcher, define the canonical in-memory representation for a single OHLC candle.
This model is what every `HistoricalCandleFetcher` returns — storage writers receive it,
Parquet is produced from it, `compute_ivr` receives it as a series.

**Parquet schema is frozen.** `CandleRecord` must map cleanly to the existing Parquet columns
`date`, `open`, `high`, `low`, `close` — no schema migration, no column renames.

---

## Files to change

| File | Action |
|------|--------|
| `src/models/candles.py` | New — `CandleInterval` enum + `CandleRecord` frozen Pydantic model |
| `src/client/protocol.py` | Edit — replace `Candle = dict[str, Any]` with `from src.models.candles import CandleRecord as Candle` |
| `tests/unit/models/test_candles.py` | New — model validation tests |

---

## What to implement

### `src/models/candles.py`

```python
class CandleInterval(str, Enum):
    """Supported OHLC candle resolutions.

    Members reflect the union of resolutions available across Upstox, Dhan,
    and Kite (confirmed in HD-0 decision matrix). Add members only when a
    fetcher implementation actually uses them — do not pre-declare.
    """
    DAY = "1d"
    WEEK = "1w"
    MINUTE_1 = "1min"
    MINUTE_5 = "5min"
    MINUTE_15 = "15min"
    MINUTE_30 = "30min"
    HOUR_1 = "1h"


class CandleRecord(BaseModel, frozen=True):
    """Canonical in-memory OHLC candle record.

    Broker parsers must produce CandleRecord; Parquet writers consume it.
    The Parquet schema (date/open/high/low/close float64) is frozen — this
    model's field names and types must remain stable.

    Price fields are float (not Decimal) to match the existing Parquet schema.
    Decimal conversion is not applied here — it is applied at the SQLite layer
    only if candles are ever stored there (they currently are not).
    """
    date: date               # trading date (IST calendar date, not UTC datetime)
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None    # absent in some vendor responses
    oi: int | None = None        # open interest — options only
    interval: CandleInterval = CandleInterval.DAY
    instrument_key: str | None = None   # canonical key; None for index instruments (VIX)

    @field_validator("high")
    @classmethod
    def high_gte_low(cls, v: float, info: FieldValidationInfo) -> float:
        if "low" in info.data and v < info.data["low"]:
            raise ValueError(f"high ({v}) must be >= low ({info.data['low']})")
        return v

    @field_validator("open", "high", "low", "close")
    @classmethod
    def price_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"price must be positive, got {v}")
        return v
```

### `src/client/protocol.py`

Replace the stub:
```python
# Before
Candle = dict[str, Any]  # TODO: TD-7 — replace with Pydantic model from src.models

# After
from src.models.candles import CandleRecord as Candle  # TD-7 resolved
```

Also update `CandleRequest` — leave as `dict[str, Any]` for now (resolved in HD-2).

---

## Tests — `tests/unit/models/test_candles.py`

1. **Happy path:** `CandleRecord(date=date(2026,1,2), open=23000.0, high=23100.0, low=22900.0, close=23050.0)` — validates without error.
2. **High < low:** `high=22000, low=23000` → raises `ValidationError`.
3. **Zero price:** `open=0.0` → raises `ValidationError`.
4. **Negative price:** `close=-1.0` → raises `ValidationError`.
5. **Volume optional:** `CandleRecord(...)` without `volume` → `volume is None`.
6. **Frozen:** attempting `record.close = 1.0` → raises `ValidationError` (frozen model).
7. **Interval default:** no `interval` arg → `interval == CandleInterval.DAY`.
8. **`CandleInterval` str values:** `CandleInterval.DAY == "1d"` (str enum serialises correctly).

---

## Commit message

```
feat(models): CandleRecord + CandleInterval; resolve TD-7 Candle stub

Why: canonical in-memory candle model required before any HistoricalCandleFetcher
     can be typed correctly; replaces untyped dict stub in protocol.py.
What:
- src/models/candles.py: CandleInterval enum + CandleRecord frozen Pydantic model
- src/client/protocol.py: replace Candle = dict[Any] with CandleRecord import (TD-7)
- tests/unit/models/test_candles.py: 8 model validation tests
Ref: docs/plan/historical-data-abstraction/stories/HD-1.md
```

---

## Pre-baked graph context

```
search_graph("BhavRecord")          # existing frozen Pydantic model — mirror pattern
search_graph("OptionLeg")           # another frozen model — field_validator pattern
search_graph("Candle")              # confirm it's still dict[str, Any] before starting
git log --oneline -5 src/client/protocol.py
```
