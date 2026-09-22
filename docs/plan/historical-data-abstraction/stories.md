# Historical Data Abstraction — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## HD-0 — Historical data vendor cost + quality evaluation

> Assigned to: Claude Phase: 0 — Vendor Evaluation (gates all implementation phases) Priority: LOW

---

### Goal

Historical OHLC data is not free. Every API probe call costs either money (paid plans) or quota (rate-limited free tiers). This story runs minimal, cost-bounded probe scripts to measure quality and
price across vendors, then produces a decision matrix that gates which fetcher implementations actually get built in HD-6 through HD-8.

**Cost discipline is mandatory:** every probe uses a 5-trading-day window only. No full-history pulls during evaluation. Dry-run mode must work before any live call.

---

### Vendors to evaluate

| Vendor | What they offer | Cost model | Credentials needed |
|--------|----------------|------------|-------------------|
| **Upstox** (Analytics Token) | Daily + intraday OHLC, India VIX via `NSE_INDEX\|India VIX` key | Included in active trading account | `UPSTOX_ANALYTICS_TOKEN` (already wired) |
| **Dhan** | Historical OHLC via `/v2/charts/historical` | Included in trading account | `DHAN_CLIENT_ID` + `DHAN_ACCESS_TOKEN` (already wired) |
| **Kite/Zerodha** | Historical OHLC via Kite Connect API | ₹2000/month subscription | `KITE_API_KEY` + `KITE_ACCESS_TOKEN` (add to `.env`) |
| **NSE CSV (bhavcopy)** | EOD options OHLCV — already implemented in `bhavcopy_ingest.py` | Free (NSE direct) | None — uses public NSE CDN |
| **Investing.com / Yahoo Finance** | India VIX, Nifty spot — unofficial/scraping | Free but fragile | None |

---

### Dimensions to measure per vendor

For each vendor, answer every question below. Record findings in `hd_analysis.md`.

#### Coverage
- Instruments available: India VIX? Nifty spot? Nifty options chains? Individual equity ETFs?
- Max historical lookback (years)?
- Resolutions available: 1D, 1W, 1min, 5min, 15min, 1H?
- Does India VIX have pre-2020 daily history?

#### Data quality
- Any gaps in the last 252 trading days (IVR window)?
- OHLC values — do they match NSE bhavcopy for the same dates?
- Timestamp: UTC or IST? Is timezone explicit or implicit?
- Are candle values floats or strings? Do they need Decimal conversion?

#### API mechanics
- Authentication method (Bearer token / API key / session)?
- Rate limit: calls/minute? calls/day?
- Batch support: can you fetch multiple instruments in one call?
- Pagination: is there a max rows per response?
- Async support: does the SDK/API support async, or is it sync-only (like current Upstox path)?

#### Cost
- Is historical data included in the base trading account, or is it a paid add-on?
- Price per call / price per month?
- Free tier limits (if any)?
- Estimated cost to bootstrap full 252-day VIX history from zero?

---

### Probe scripts to write

All under `scripts/dev/historical_probe/`. Each accepts `--dry-run` (prints what would be fetched, estimated cost) and `--days N` (default 5, maximum 10 during evaluation).

#### `scripts/dev/historical_probe/probe_vix_history.py`

Fetches daily India VIX candles for the last N trading days from each vendor.

```bash
python -m scripts.dev.historical_probe.probe_vix_history --broker upstox --days 5
python -m scripts.dev.historical_probe.probe_vix_history --broker dhan --days 5
python -m scripts.dev.historical_probe.probe_vix_history --broker kite --days 5 --dry-run
```

Prints per vendor:
- Rows returned and date range
- Close values for each day
- Mismatch vs NSE bhavcopy reference for the same dates (if bhavcopy Parquet exists)
- Fetch latency (ms)
- Rate limit headers (if present)

#### `scripts/dev/historical_probe/probe_ohlc_candles.py`

Fetches daily OHLC for NIFTY spot + one equity ETF (NIFTYBEES) for last N days.

```bash
python -m scripts.dev.historical_probe.probe_ohlc_candles --broker upstox --days 5
python -m scripts.dev.historical_probe.probe_ohlc_candles --broker dhan --days 5
python -m scripts.dev.historical_probe.probe_ohlc_candles --broker kite --days 5 --dry-run
```

Prints:
- OHLC rows, close vs NSE reference
- Whether multiple instruments can be batched in one call
- Max rows returned per call (pagination check)

#### `scripts/dev/historical_probe/probe_intraday_candles.py`

Fetches 5-minute candles for NIFTY for the last 1 trading day only. **Cost warning printed before execution even without `--dry-run`.**

```bash
python -m scripts.dev.historical_probe.probe_intraday_candles --broker upstox
python -m scripts.dev.historical_probe.probe_intraday_candles --broker dhan
python -m scripts.dev.historical_probe.probe_intraday_candles --broker kite --dry-run
```

Prints:
- Bars returned (expect ~75 for a full session at 5-min)
- Any gaps within the session
- Latency

#### `scripts/dev/historical_probe/probe_cost_estimate.py`

Does NOT call any API. Reads probe results from `data/historical_probe/` and prints a cost/quality matrix.

```bash
python -m scripts.dev.historical_probe.probe_cost_estimate
```

Prints the decision matrix table from saved probe results. Designed to be run after the other three probes so findings are summarized in one place.

---

### Output documents (commit after running probes)

#### `docs/plan/historical-data-abstraction/hd_analysis.md`

Raw findings per vendor per dimension. Template:

```markdown
# Historical Data Vendor Analysis — <date>

## India VIX

### Upstox
- Max lookback: ~5 years (observed)
- Resolutions: 1D, 1W, 1min, 5min, 15min, 30min, 1H
- Pre-2020 data present: Yes / No
- Gaps in last 252 days: None observed / list dates
- Timestamp format: ISO8601 UTC with offset
- Rate limit: not exposed in headers; empirically ~10 req/s
- Authentication: Bearer Analytics Token (separate from trading token)
- Async: No — sync requests only in current impl; aiohttp possible
- Cost: included in trading account
- Notes: ...

### Dhan
...

### Kite
...
```

#### `docs/plan/historical-data-abstraction/hd_decision_matrix.md`

```markdown
# Historical Data — Vendor Decision Matrix

| Data Category | Upstox | Dhan | Kite | NSE CSV | Recommended | Rationale |
|---------------|--------|------|------|---------|-------------|-----------|
| India VIX (daily, 252-day IVR window) | ✓ | ? | ✓ | ✓ (bhavcopy, slow) | Upstox | Already wired; free; fast |
| NIFTY spot daily | ✓ | ✓ | ✓ | ✓ (bhavcopy) | Upstox | Already wired |
| NIFTY 5-min intraday | ✓ | ✓ | ✓ | ✗ | TBD by probe | Measure latency + gaps |
| Options EOD OHLCV | ✗ (paid) | ? | ? | ✓ (bhavcopy) | NSE CSV | Already implemented; free |
| Equity ETF daily | ✓ | ✓ | ✓ | ✗ | TBD by probe | |
```

---

### Gate before closing HD-0

All four conditions must hold before marking HD-0 complete:

1. At least Upstox and Dhan probes ran successfully (Kite optional if credentials unavailable).
2. `hd_analysis.md` committed with raw observations.
3. `hd_decision_matrix.md` committed with recommended vendor per category.
4. `DECISIONS.md` entry added: `Historical data vendor assignments (YYYY-MM-DD, HD-0)`.
5. Tasks HD-6, HD-7 updated in `tasks.md` with "implement" or "skip" based on the matrix.

---

### Files to create

| File | Type |
|------|------|
| `scripts/dev/historical_probe/__init__.py` | Package stub |
| `scripts/dev/historical_probe/probe_vix_history.py` | Cost-bounded probe |
| `scripts/dev/historical_probe/probe_ohlc_candles.py` | Cost-bounded probe |
| `scripts/dev/historical_probe/probe_intraday_candles.py` | Cost-bounded probe (prints cost warning) |
| `scripts/dev/historical_probe/probe_cost_estimate.py` | No-API summary script |
| `data/historical_probe/.gitkeep` | Output directory placeholder |
| `docs/plan/historical-data-abstraction/hd_analysis.md` | Fill after running probes |
| `docs/plan/historical-data-abstraction/hd_decision_matrix.md` | Fill after analysis |

---

### Two-commit strategy

**Commit 1 — probe scripts only:**
```
feat(dev): historical data vendor probe scripts (cost-bounded)

Why: pre-implementation evaluation of Upstox/Dhan/Kite OHLC quality and cost
     before committing to HistoricalCandleFetcher implementations.
What:
- scripts/dev/historical_probe/: 4 probe scripts + package stub
- data/historical_probe/.gitkeep: output directory placeholder
Ref: docs/plan/historical-data-abstraction/stories.md HD-0
```

**Commit 2 — findings + decision matrix (after running probes):**
```
docs(historical-data): vendor analysis findings + decision matrix

Why: HD-0 evaluation gates HD-6/HD-7 implementation decisions.
What:
- docs/plan/historical-data-abstraction/hd_analysis.md: raw probe findings
- docs/plan/historical-data-abstraction/hd_decision_matrix.md: vendor assignments
- DECISIONS.md: historical data vendor assignments entry
Ref: docs/plan/historical-data-abstraction/stories.md HD-0
```

---

### Pre-baked graph context

```
search_graph("ingest_vix_from_api")     # existing Upstox fetch — pattern to replicate per vendor
search_graph("fetch_vix_latest")        # callers — must not break after probe scripts added
search_graph("load_vix_series")         # Parquet loader — reference for comparing probe output
git log --oneline -10 src/backtest/vix_ingest.py
```

Also read `REFERENCES.md` — `NSE_INDEX|India VIX` instrument key and NIFTYBEES key documented there.

---

## HD-1 — `CandleRecord` Pydantic model + `CandleInterval` enum

> Assigned to: Claude Phase: 1 — Canonical Models Blocked by: HD-0 must be complete (decision matrix may influence interval enum members)

---

### Goal

`Candle = dict[str, Any]` in `src/client/protocol.py` is a TODO stub (TD-7). Before writing any fetcher, define the canonical in-memory representation for a single OHLC candle. This model is what
every `HistoricalCandleFetcher` returns — storage writers receive it, Parquet is produced from it, `compute_ivr` receives it as a series.

**Parquet schema is frozen.** `CandleRecord` must map cleanly to the existing Parquet columns `date`, `open`, `high`, `low`, `close` — no schema migration, no column renames.

---

### Files to change

| File | Action |
|------|--------|
| `src/models/candles.py` | New — `CandleInterval` enum + `CandleRecord` frozen Pydantic model |
| `src/client/protocol.py` | Edit — replace `Candle = dict[str, Any]` with `from src.models.candles import CandleRecord as Candle` |
| `tests/unit/models/test_candles.py` | New — model validation tests |

---

### What to implement

#### `src/models/candles.py`

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

#### `src/client/protocol.py`

Replace the stub:
```python
# Before
Candle = dict[str, Any]  # TODO: TD-7 — replace with Pydantic model from src.models

# After
from src.models.candles import CandleRecord as Candle  # TD-7 resolved
```

Also update `CandleRequest` — leave as `dict[str, Any]` for now (resolved in HD-2).

---

### Tests — `tests/unit/models/test_candles.py`

1. **Happy path:** `CandleRecord(date=date(2026,1,2), open=23000.0, high=23100.0, low=22900.0, close=23050.0)` — validates without error.
2. **High < low:** `high=22000, low=23000` → raises `ValidationError`.
3. **Zero price:** `open=0.0` → raises `ValidationError`.
4. **Negative price:** `close=-1.0` → raises `ValidationError`.
5. **Volume optional:** `CandleRecord(...)` without `volume` → `volume is None`.
6. **Frozen:** attempting `record.close = 1.0` → raises `ValidationError` (frozen model).
7. **Interval default:** no `interval` arg → `interval == CandleInterval.DAY`.
8. **`CandleInterval` str values:** `CandleInterval.DAY == "1d"` (str enum serialises correctly).

---

### Commit message

```
feat(models): CandleRecord + CandleInterval; resolve TD-7 Candle stub

Why: canonical in-memory candle model required before any HistoricalCandleFetcher
     can be typed correctly; replaces untyped dict stub in protocol.py.
What:
- src/models/candles.py: CandleInterval enum + CandleRecord frozen Pydantic model
- src/client/protocol.py: replace Candle = dict[Any] with CandleRecord import (TD-7)
- tests/unit/models/test_candles.py: 8 model validation tests
Ref: docs/plan/historical-data-abstraction/stories.md HD-1
```

---

### Pre-baked graph context

```
search_graph("BhavRecord")          # existing frozen Pydantic model — mirror pattern
search_graph("OptionLeg")           # another frozen model — field_validator pattern
search_graph("Candle")              # confirm it's still dict[str, Any] before starting
git log --oneline -5 src/client/protocol.py
```

---

## HD-2 — `CandleRequest` Pydantic model (resolves TD-7)

> Assigned to: Claude Phase: 1 — Canonical Models Blocked by: HD-1 (needs `CandleInterval` enum)

---

### Goal

`CandleRequest = dict[str, Any]` in `src/client/protocol.py` is the other TD-7 stub. Replace it with a typed Pydantic model so every fetcher and caller has a validated, self-documenting request shape.

---

### Files to change

| File | Action |
|------|--------|
| `src/models/candles.py` | Edit — add `CandleRequest` model |
| `src/client/protocol.py` | Edit — replace `CandleRequest = dict[str, Any]` with import |
| `tests/unit/models/test_candles.py` | Extend — add `CandleRequest` validation tests |

---

### What to implement

#### `src/models/candles.py` — add `CandleRequest`

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

#### `src/client/protocol.py`

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

### Tests — extend `tests/unit/models/test_candles.py`

1. **Happy path:** `CandleRequest(instrument_key="NSE_INDEX|India VIX", interval=CandleInterval.DAY, from_date=date(2026,1,1), to_date=date(2026,1,31))` — validates.
2. **from_date > to_date:** raises `ValidationError`.
3. **from_date == to_date:** valid (single-day fetch).
4. **Frozen:** `req.to_date = date(2026,2,1)` → raises `ValidationError`.

---

### Commit message

```
feat(models): CandleRequest model; resolve TD-7 CandleRequest stub

Why: typed request params for HistoricalCandleFetcher calls; closes TD-7 for Candle + CandleRequest.
What:
- src/models/candles.py: CandleRequest frozen Pydantic model with date-range validator
- src/client/protocol.py: replace CandleRequest = dict[Any] with typed import
- tests/unit/models/test_candles.py: 4 additional CandleRequest tests
Ref: docs/plan/historical-data-abstraction/stories.md HD-2
```

---

### Pre-baked graph context

```
search_graph("CandleRequest")           # confirm it's still dict[str, Any]
search_graph("CandleInterval")          # confirm HD-1 shipped first
search_graph("get_historical_candles")  # all callers — upstox_live raises NotImplementedError
```

---

## HD-3 — `HistoricalCandleFetcher` protocol

> Assigned to: Claude Phase: 2 — Fetcher Protocol + Upstox Implementation Blocked by: HD-1 and HD-2 must be merged first

---

### Goal

Define the `HistoricalCandleFetcher` protocol — the single interface that all vendor implementations (Upstox, Dhan, Kite, NSE CSV) must satisfy. This is the seam that lets `VixIngestPipeline` and
future OHLC consumers switch vendors without changing calling code.

---

### Files to change

| File | Action |
|------|--------|
| `src/backtest/fetchers/__init__.py` | New package stub |
| `src/backtest/fetchers/protocol.py` | New — `HistoricalCandleFetcher` protocol |
| `tests/unit/backtest/test_fetcher_protocol.py` | New — protocol conformance tests |

---

### What to implement

#### `src/backtest/fetchers/protocol.py`

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

### Tests — `tests/unit/backtest/test_fetcher_protocol.py`

1. **Protocol is runtime-checkable:** create a conforming class without inheriting from the protocol → `isinstance(obj, HistoricalCandleFetcher)` → `True`.
2. **Missing `fetch`:** class with `supports_interval` only → `isinstance` → `False`.
3. **Missing `supports_interval`:** class with `fetch` only → `isinstance` → `False`.
4. **Both methods required:** only a class with both satisfies the protocol.

---

### Commit message

```
feat(backtest): HistoricalCandleFetcher protocol

Why: defines the seam for swappable vendor fetch implementations;
     gates HD-4 through HD-8 implementations.
What:
- src/backtest/fetchers/__init__.py: new package stub
- src/backtest/fetchers/protocol.py: HistoricalCandleFetcher runtime-checkable Protocol
- tests/unit/backtest/test_fetcher_protocol.py: 4 protocol conformance tests
Ref: docs/plan/historical-data-abstraction/stories.md HD-3
```

---

### Pre-baked graph context

```
search_graph("MarketDataParser")         # mirror this protocol pattern exactly
search_graph("CandleRecord")             # confirm HD-1 shipped
search_graph("CandleRequest")            # confirm HD-2 shipped
search_graph("DataFetchError")           # exception to reference in docstring
search_graph("RateLimitError")           # exception to reference in docstring
```

---

## HD-4 — `UpstoxCandleFetcher` implementation

> Assigned to: Antigravity Phase: 2 — Fetcher Protocol + Upstox Implementation Blocked by: HD-3 must be merged first

---

### Goal

Wrap the existing `ingest_vix_from_api` and `fetch_vix_latest` logic from `src/backtest/vix_ingest.py` into a proper `HistoricalCandleFetcher` implementation. The existing module-level functions are
not deleted — they are replaced by a class that the functions will delegate to in HD-5.

Key problems with the current implementation to fix here:
- Uses synchronous `requests.get` — replace with `aiohttp` (async, consistent with the rest of the codebase)
- `float(candles[0][4])` — raw float from API; keep as float for Parquet compatibility but validate it is finite
- No `supports_interval` logic — hard-codes daily candles; make explicit

---

### Files to change

| File | Action |
|------|--------|
| `src/backtest/fetchers/upstox.py` | New — `UpstoxCandleFetcher` |
| `tests/unit/backtest/test_fetcher_upstox.py` | New — fetcher tests using fixtures |
| `tests/fixtures/responses/upstox_candles_vix.json` | New — minimal candle fixture (5 rows) |

---

### What to implement

#### `src/backtest/fetchers/upstox.py`

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

### Fixture — `tests/fixtures/responses/upstox_candles_vix.json`

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

### Tests — `tests/unit/backtest/test_fetcher_upstox.py`

Mock `aiohttp.ClientSession` — no network calls.

1. **Happy path:** fixture response → 5 `CandleRecord` rows, sorted ascending, correct `close` values.
2. **Empty candles:** API returns `candles: []` → returns `[]`, no exception.
3. **Missing token:** `UpstoxCandleFetcher(token=None)` with no env var → `fetch()` returns `[]` and logs warning.
4. **HTTP error:** mock returns 500 → raises `DataFetchError`.
5. **`supports_interval`:** `DAY` → `True`; a hypothetical `"tick"` interval → `False`.
6. **Protocol conformance:** `isinstance(UpstoxCandleFetcher(), HistoricalCandleFetcher)` → `True`.
7. **Sort order:** fixture with out-of-order dates → result is ascending by date.

---

### Commit message

```
feat(backtest): UpstoxCandleFetcher — async aiohttp implementation

Why: replaces sync requests.get in vix_ingest with async fetcher conforming
     to HistoricalCandleFetcher protocol.
What:
- src/backtest/fetchers/upstox.py: UpstoxCandleFetcher with aiohttp + CandleRecord output
- tests/unit/backtest/test_fetcher_upstox.py: 7 tests with mocked aiohttp
- tests/fixtures/responses/upstox_candles_vix.json: 5-row candle fixture
Ref: docs/plan/historical-data-abstraction/stories.md HD-4
```

---

### Pre-baked graph context

```
search_graph("ingest_vix_from_api")      # exact parsing logic to port
search_graph("HistoricalCandleFetcher")  # confirm HD-3 shipped
search_graph("DataFetchError")           # exception class + import path
search_graph("CandleRecord")             # field names + types
git log --oneline -10 src/backtest/vix_ingest.py
```

---

## HD-5 — Wire `UpstoxCandleFetcher` into `VixIngestPipeline`; deprecation shims

> Assigned to: Claude Phase: 2 — Fetcher Protocol + Upstox Implementation Blocked by: HD-4 must be merged first

---

### Goal

Connect the new `UpstoxCandleFetcher` to `VixIngestPipeline` and replace the two module-level functions (`ingest_vix_from_api`, `fetch_vix_latest`) with deprecation shims that delegate to the fetcher.
The 5 script callers of `fetch_vix_latest` and the 1 caller of `ingest_vix_from_api` must not break.

---

### Files to change

| File | Action |
|------|--------|
| `src/backtest/vix_ingest.py` | Edit — inject `HistoricalCandleFetcher`; shim existing functions |
| `tests/unit/backtest/test_vix_ingest.py` | Extend — injection + deprecation warning tests |

---

### What to implement

#### `src/backtest/vix_ingest.py` — `VixIngestPipeline` refactor

The current module has no class — everything is module-level functions. Introduce `VixIngestPipeline` (if it does not already exist) or extend it if it does:

```python
class VixIngestPipeline:
    """Orchestrates VIX candle fetching and Parquet persistence.

    Accepts any HistoricalCandleFetcher — defaults to UpstoxCandleFetcher.
    Storage layer (Parquet) is unchanged.
    """
    def __init__(
        self,
        fetcher: HistoricalCandleFetcher | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self._fetcher = fetcher or UpstoxCandleFetcher()
        self._data_dir = data_dir or settings.vix_data_dir

    async def ingest(self, from_date: date, to_date: date) -> int:
        """Fetch and persist VIX candles. Returns count of new rows written."""
        ...

    async def fetch_latest(self) -> float | None:
        """Return most recent VIX close. Returns None on any failure."""
        ...
```

#### Deprecation shims (module-level, backward-compatible)

```python
def ingest_vix_from_api(
    from_date: date, to_date: date, out_dir: Path, token: str | None = None
) -> int:
    """Deprecated: use VixIngestPipeline.ingest() instead."""
    warnings.warn(
        "ingest_vix_from_api is deprecated; use VixIngestPipeline",
        DeprecationWarning, stacklevel=2,
    )
    pipeline = VixIngestPipeline(
        fetcher=UpstoxCandleFetcher(token=token),
        data_dir=out_dir,
    )
    return asyncio.run(pipeline.ingest(from_date, to_date))


def fetch_vix_latest(token: str | None = None) -> float | None:
    """Deprecated: use VixIngestPipeline.fetch_latest() instead."""
    warnings.warn(
        "fetch_vix_latest is deprecated; use VixIngestPipeline",
        DeprecationWarning, stacklevel=2,
    )
    pipeline = VixIngestPipeline(fetcher=UpstoxCandleFetcher(token=token))
    return asyncio.run(pipeline.fetch_latest())
```

The existing 5 script callers (`record_paper_trade.py`, `paper_cc_entry.py`, `pre_market_brief.py`, `healthcheck.py`) continue to work unchanged. Migration to `VixIngestPipeline` is a separate,
non-urgent cleanup.

---

### Tests — extend `tests/unit/backtest/test_vix_ingest.py`

1. **Injected fetcher used:** `VixIngestPipeline(fetcher=mock_fetcher)` — `ingest()` calls `mock_fetcher.fetch()`.
2. **Default fetcher is Upstox:** `VixIngestPipeline()._fetcher` is `UpstoxCandleFetcher` instance.
3. **`ingest_vix_from_api` shim emits DeprecationWarning.**
4. **`fetch_vix_latest` shim emits DeprecationWarning.**
5. **`fetch_latest` returns None on empty fetcher result:** mock fetcher returns `[]` → `pipeline.fetch_latest()` → `None`.

---

### Commit message

```
feat(backtest): VixIngestPipeline with injected fetcher; deprecation shims

Why: wires UpstoxCandleFetcher into VIX ingest pipeline; shims preserve all 5
     existing script callers without modification.
What:
- src/backtest/vix_ingest.py: VixIngestPipeline class + shims on ingest_vix_from_api
  and fetch_vix_latest
- tests/unit/backtest/test_vix_ingest.py: 5 additional injection + shim tests
Ref: docs/plan/historical-data-abstraction/stories.md HD-5
```

---

### Pre-baked graph context

```
search_graph("VixIngestPipeline")         # may already exist from BA-10 — check before creating
search_graph("fetch_vix_latest")          # all 5 callers — verify none break
search_graph("ingest_vix_from_api")       # 1 caller (bhavcopy_bootstrap? or pipeline script)
search_graph("UpstoxCandleFetcher")       # confirm HD-4 shipped
git log --oneline -10 src/backtest/vix_ingest.py
```

Note: if BA-10 was completed before this story, `VixIngestPipeline` may already exist with a `VixFetcher` protocol. If so, replace `VixFetcher` with `HistoricalCandleFetcher` — do not maintain two
parallel fetcher protocols for the same thing.

---

## HD-6 — `DhanCandleFetcher` implementation

> Assigned to: Antigravity Phase: 3 — Alternative Vendor Implementations Blocked by: HD-3 must be merged first ⚠️ CONDITIONAL: Implement only if HD-0 decision matrix recommends Dhan for OHLC. If HD-0
> marks Dhan as "skip" for historical data, mark this task `[x] skipped — HD-0 decision`.

---

### Goal

Implement `DhanCandleFetcher` using Dhan's `/v2/charts/historical` endpoint. Mirrors `UpstoxCandleFetcher` structure exactly — only URL, auth header, and response parsing differ.

---

### Context: Dhan historical API

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

`securityId` for India VIX on Dhan: confirm from `DhanInstrumentKeyAdapter` (BA-4) or from `REFERENCES.md`. If not documented, add it there.

---

### Files to change

| File | Action |
|------|--------|
| `src/backtest/fetchers/dhan.py` | New — `DhanCandleFetcher` |
| `tests/unit/backtest/test_fetcher_dhan.py` | New — 7 tests with mocked aiohttp |
| `tests/fixtures/responses/dhan_candles_vix.json` | New — 5-row Dhan candle fixture |

---

### What to implement

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

### Tests — `tests/unit/backtest/test_fetcher_dhan.py`

Mirror HD-4 test list exactly (7 tests). Use `tests/fixtures/responses/dhan_candles_vix.json`.

1. Happy path — 5 rows, correct close values
2. Empty response — returns `[]`
3. Missing credentials — returns `[]`, logs warning
4. HTTP error — raises `DataFetchError`
5. `supports_interval` — `DAY` True, unsupported False
6. Protocol conformance — `isinstance(DhanCandleFetcher(...), HistoricalCandleFetcher)` True
7. Sort order — ascending by date

---

### Commit message

```
feat(backtest): DhanCandleFetcher for /v2/charts/historical endpoint

Why: provides Dhan as an alternative historical OHLC source per HD-0 decision matrix.
What:
- src/backtest/fetchers/dhan.py: DhanCandleFetcher conforming to HistoricalCandleFetcher
- tests/unit/backtest/test_fetcher_dhan.py: 7 tests with mocked aiohttp
- tests/fixtures/responses/dhan_candles_vix.json: 5-row Dhan candle fixture
Ref: docs/plan/historical-data-abstraction/stories.md HD-6
```

---

### Pre-baked graph context

```
search_graph("HistoricalCandleFetcher")  # protocol — confirm HD-3 shipped
search_graph("UpstoxCandleFetcher")      # reference implementation to mirror
search_graph("DhanInstrumentKeyAdapter") # confirm BA-4 shipped; needed for key translation
search_graph("dhan_client_id")           # settings field name
```

---

## HD-7 — `KiteCandleFetcher` implementation

> Assigned to: Antigravity Phase: 3 — Alternative Vendor Implementations Blocked by: HD-3 must be merged first ⚠️ CONDITIONAL: Implement only if HD-0 decision matrix recommends Kite for OHLC. If HD-0
> marks Kite as "skip", mark this task `[x] skipped — HD-0 decision`. ⚠️ Kite Connect API costs ₹2000/month. Confirm subscription active before starting.

---

### Goal

Implement `KiteCandleFetcher` using the Kite Connect historical data API. Kite has the widest lookback (3Y+ observed in HD-0 probes) but costs ₹2000/month. Only build this if HD-0 confirms Kite is
meaningfully better than Upstox for a specific use case (e.g. longer pre-2020 VIX history, lower gap rate).

---

### Context: Kite Connect historical API

Endpoint: `GET https://api.kite.trade/instruments/historical/{instrument_token}/{interval}`

Query params: `from=YYYY-MM-DD+HH:MM:SS`, `to=YYYY-MM-DD+HH:MM:SS`, `continuous=0`, `oi=1`

Interval strings: `minute`, `3minute`, `5minute`, `10minute`, `15minute`, `30minute`, `60minute`, `day`, `week`, `month`.

`instrument_token` is Kite's numeric integer ID (from the instruments CSV). Use `KiteInstrumentKeyAdapter` (BA-7) to translate canonical key → Kite token.

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

Column order: `[datetime_str, open, high, low, close, volume, oi]` Datetime strings are IST. Parse with `datetime.strptime(s, "%Y-%m-%d %H:%M:%S").date()` for daily candles.

---

### Files to change

| File | Action |
|------|--------|
| `src/backtest/fetchers/kite.py` | New — `KiteCandleFetcher` |
| `tests/unit/backtest/test_fetcher_kite.py` | New — 7 tests with mocked aiohttp |
| `tests/fixtures/responses/kite_candles_vix.json` | New — 5-row Kite candle fixture |

---

### What to implement

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

### Tests — `tests/unit/backtest/test_fetcher_kite.py`

Mirror HD-4 test list exactly (7 tests).

---

### Commit message

```
feat(backtest): KiteCandleFetcher for Kite Connect historical API

Why: provides Kite as an alternative historical OHLC source per HD-0 decision matrix
     (widest lookback; requires ₹2000/month subscription).
What:
- src/backtest/fetchers/kite.py: KiteCandleFetcher conforming to HistoricalCandleFetcher
- tests/unit/backtest/test_fetcher_kite.py: 7 tests with mocked aiohttp
- tests/fixtures/responses/kite_candles_vix.json: 5-row Kite candle fixture
Ref: docs/plan/historical-data-abstraction/stories.md HD-7
```

---

### Pre-baked graph context

```
search_graph("HistoricalCandleFetcher")  # protocol
search_graph("UpstoxCandleFetcher")      # reference implementation
search_graph("KiteInstrumentKeyAdapter") # confirm BA-7 shipped
search_graph("kite_api_key")             # settings field name
```

---

## HD-8 — `NseCsvCandleFetcher` (broker-agnostic VIX via NSE CSV)

> Assigned to: Antigravity Phase: 3 — Alternative Vendor Implementations Blocked by: HD-3 must be merged first. Can run in parallel with HD-6 / HD-7. Note: This fetcher covers VIX only. General OHLC
> is not available from NSE CSV.

---

### Goal

`src/backtest/vix_ingest.py` already has `ingest_vix_from_csv()` — a function that reads a locally downloaded NSE VIX CSV file and writes it to Parquet. This story wraps it as a proper
`HistoricalCandleFetcher` so it can be used as a zero-cost fallback when no broker credentials are available (CI, offline backtesting, air-gapped environments).

This fetcher is **read-from-file only** — it does not download the CSV. The operator downloads the NSE VIX history CSV from
`https://www.nseindia.com/products/content/equities/indices/historical_index_data.htm` and places it at a known path. The fetcher reads it.

---

### Files to change

| File | Action |
|------|--------|
| `src/backtest/fetchers/nse_csv.py` | New — `NseCsvVixFetcher` |
| `tests/unit/backtest/test_fetcher_nse_csv.py` | New — 6 tests using a fixture CSV |
| `tests/fixtures/historical/nse_vix_sample.csv` | New — 10-row NSE VIX CSV fixture |

---

### What to implement

```python
class NseCsvVixFetcher:
    """HistoricalCandleFetcher that reads a locally downloaded NSE VIX CSV.

    Covers India VIX daily data only — other instruments are not supported.
    Use as a zero-cost fallback when broker credentials are unavailable.

    NSE VIX CSV format (downloaded from nseindia.com):
        Date,Open,High,Low,Close
        01-Jan-2020,14.23,15.10,13.98,14.87
        ...
    Dates are in DD-Mon-YYYY format (Indian locale). No volume or OI.
    """

    _SUPPORTED_KEY = "NSE_INDEX|India VIX"
    _SUPPORTED_INTERVAL = CandleInterval.DAY

    def __init__(self, csv_path: Path) -> None:
        self._path = csv_path

    async def fetch(self, request: CandleRequest) -> list[CandleRecord]:
        if request.instrument_key != self._SUPPORTED_KEY:
            raise ValueError(
                f"NseCsvVixFetcher only supports '{self._SUPPORTED_KEY}', "
                f"got '{request.instrument_key}'"
            )
        if request.interval != self._SUPPORTED_INTERVAL:
            raise ValueError(
                f"NseCsvVixFetcher only supports DAY interval, got {request.interval}"
            )
        # read CSV, filter by date range, return CandleRecord list
        ...

    def supports_interval(self, interval: CandleInterval) -> bool:
        return interval == self._SUPPORTED_INTERVAL
```

CSV parsing rules:
- Parse `Date` column: `datetime.strptime(row["Date"], "%d-%b-%Y").date()`
- Filter rows where `from_date <= row_date <= to_date`
- Raise `FileNotFoundError` if CSV does not exist
- Return `[]` if date range yields no rows (not an error)
- Sort ascending by date

---

### Fixture — `tests/fixtures/historical/nse_vix_sample.csv`

```csv
Date,Open,High,Low,Close
26-May-2026,14.23,15.10,13.98,14.87
27-May-2026,14.87,15.32,14.50,15.01
28-May-2026,15.01,15.45,14.75,14.92
29-May-2026,14.92,15.20,14.60,15.15
30-May-2026,15.15,15.88,14.90,15.67
02-Jun-2026,15.67,16.10,15.40,15.89
03-Jun-2026,15.89,16.25,15.60,16.01
04-Jun-2026,16.01,16.45,15.80,16.20
05-Jun-2026,16.20,16.60,15.95,16.35
06-Jun-2026,16.35,16.80,16.10,16.55
```

---

### Tests — `tests/unit/backtest/test_fetcher_nse_csv.py`

1. **Happy path:** request covering 5 rows → 5 `CandleRecord` rows, correct dates and closes.
2. **Date filter:** request covering only 3 of 10 rows → returns exactly 3.
3. **Out-of-range request:** date range beyond CSV coverage → returns `[]`.
4. **Wrong instrument:** `instrument_key != "NSE_INDEX|India VIX"` → raises `ValueError`.
5. **Missing CSV file:** `NseCsvVixFetcher(Path("/nonexistent.csv"))` → `fetch()` raises `FileNotFoundError`.
6. **Protocol conformance:** `isinstance(NseCsvVixFetcher(path), HistoricalCandleFetcher)` → `True`.

---

### Commit message

```
feat(backtest): NseCsvVixFetcher — zero-cost offline VIX fallback

Why: broker-agnostic VIX fetcher for CI, offline backtesting, and credential-free
     environments; reads locally downloaded NSE VIX CSV.
What:
- src/backtest/fetchers/nse_csv.py: NseCsvVixFetcher conforming to HistoricalCandleFetcher
- tests/unit/backtest/test_fetcher_nse_csv.py: 6 tests
- tests/fixtures/historical/nse_vix_sample.csv: 10-row fixture
Ref: docs/plan/historical-data-abstraction/stories.md HD-8
```

---

### Pre-baked graph context

```
search_graph("ingest_vix_from_csv")      # existing CSV parsing logic to port
search_graph("HistoricalCandleFetcher")  # confirm HD-3 shipped
search_graph("NseCsvVixFetcher")         # must be zero results — confirm not already created
```

---

## HD-9 — Implement `get_historical_candles` in `UpstoxLiveClient`

> Assigned to: Claude Phase: 4 — Wire into `BrokerClient` Protocol Blocked by: HD-4 must be merged first (`UpstoxCandleFetcher` must exist)

---

### Goal

`UpstoxLiveClient.get_historical_candles()` currently raises `NotImplementedError`. Wire it to delegate to `UpstoxCandleFetcher`, closing the gap between the `BrokerClient` protocol declaration and
the actual implementation.

---

### Files to change

| File | Action |
|------|--------|
| `src/client/upstox_live.py` | Edit — implement `get_historical_candles` via `UpstoxCandleFetcher` |
| `tests/unit/client/test_upstox_live.py` | Extend — `get_historical_candles` happy path + error test |

---

### What to implement

#### `src/client/upstox_live.py`

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

`self._analytics_token` is the Analytics Token already stored on the client for `get_ltp` and `get_option_chain`. No new constructor params needed.

---

### Tests — extend `tests/unit/client/test_upstox_live.py`

1. **Happy path:** `UpstoxLiveClient.get_historical_candles(request)` with mocked `UpstoxCandleFetcher.fetch` → returns `CandleRecord` list.
2. **DataFetchError propagation:** mocked fetcher raises `DataFetchError` → client propagates it unchanged.
3. **No longer raises NotImplementedError:** calling `get_historical_candles` does not raise `NotImplementedError`.

---

### Commit message

```
feat(client): implement get_historical_candles in UpstoxLiveClient

Why: closes the NotImplementedError gap in BrokerClient protocol implementation;
     delegates to UpstoxCandleFetcher.
What:
- src/client/upstox_live.py: get_historical_candles delegates to UpstoxCandleFetcher
- tests/unit/client/test_upstox_live.py: 3 additional tests
Ref: docs/plan/historical-data-abstraction/stories.md HD-9
```

---

### Pre-baked graph context

```
search_graph("UpstoxLiveClient")         # constructor fields — find analytics_token attribute name
search_graph("get_historical_candles")   # current NotImplementedError impl
search_graph("UpstoxCandleFetcher")      # confirm HD-4 shipped
search_graph("CandleRequest")            # confirm HD-2 shipped
```

---

## HD-10 — `build_historical_fetcher()` factory function

> Assigned to: Claude Phase: 4 — Wire into `BrokerClient` Protocol Blocked by: HD-5 must be merged. HD-6 / HD-7 must be complete or marked skipped per HD-0.

---

### Goal

Add `build_historical_fetcher()` to `src/client/factory.py` — the sole composition root. This mirrors `build_market_data_parser()` (BA-5): selects the correct `HistoricalCandleFetcher` based on
`settings.upstox_env` and the HD-0 decision matrix.

---

### Files to change

| File | Action |
|------|--------|
| `src/client/factory.py` | Add `build_historical_fetcher()` |
| `tests/unit/client/test_factory_historical.py` | New — factory selection + smoke tests |

---

### What to implement

```python
def build_historical_fetcher(
    settings: Settings | None = None,
    fetcher: HistoricalCandleFetcher | None = None,
) -> HistoricalCandleFetcher:
    """Return the HistoricalCandleFetcher for the active broker environment.

    Selection follows the HD-0 decision matrix. Update this function when the
    matrix changes — do not scatter broker-selection logic elsewhere.

    Args:
        settings: Settings singleton override (primarily for testing).
        fetcher: Explicit fetcher override (testing / dependency injection).

    Returns:
        HistoricalCandleFetcher conforming to the protocol.

    Raises:
        ValueError: If upstox_env maps to an unsupported fetcher configuration.
    """
    if fetcher is not None:
        return fetcher

    cfg = settings or _settings
    env = cfg.upstox_env

    if env in ("prod", "sandbox", "test"):
        return UpstoxCandleFetcher(token=cfg.upstox_analytics_token)
    if env == "dhan":
        # Only if HD-6 was implemented; otherwise raise with instructions
        return DhanCandleFetcher(...)
    if env == "kite":
        # Only if HD-7 was implemented; otherwise raise with instructions
        return KiteCandleFetcher(...)

    raise ValueError(f"No HistoricalCandleFetcher configured for env '{env}'")
```

If HD-6 or HD-7 were skipped (per HD-0 decision), raise a descriptive `ValueError` for those env values rather than importing a non-existent class.

Also register `NseCsvVixFetcher` as an explicit override option (not env-based):

```python
def build_vix_fallback_fetcher(csv_path: Path) -> HistoricalCandleFetcher:
    """Return NseCsvVixFetcher for offline/CI use."""
    return NseCsvVixFetcher(csv_path)
```

---

### Tests — `tests/unit/client/test_factory_historical.py`

1. **Upstox default:** `upstox_env="prod"` → returns `UpstoxCandleFetcher`.
2. **Test env:** `upstox_env="test"` → also returns `UpstoxCandleFetcher`.
3. **Dhan (if HD-6 shipped):** `upstox_env="dhan"` → returns `DhanCandleFetcher`.
4. **Kite (if HD-7 shipped):** `upstox_env="kite"` → returns `KiteCandleFetcher`.
5. **Unknown env:** `upstox_env="unknown"` → raises `ValueError`.
6. **Injected override:** `build_historical_fetcher(fetcher=mock)` → returns mock unchanged.
7. **Fallback builder:** `build_vix_fallback_fetcher(fixture_csv)` → returns `NseCsvVixFetcher`.
8. **Protocol conformance:** all returned fetchers satisfy `isinstance(..., HistoricalCandleFetcher)`.

---

### Commit message

```
feat(client): build_historical_fetcher() factory + vix fallback builder

Why: makes factory.py the sole composition root for historical fetcher selection,
consistent with build_market_data_parser() pattern.
What:
- src/client/factory.py: build_historical_fetcher() + build_vix_fallback_fetcher()
- tests/unit/client/test_factory_historical.py: 8 factory tests
Ref: docs/plan/historical-data-abstraction/stories.md HD-10
```

---

### Pre-baked graph context

```
search_graph("build_market_data_parser")    # pattern to mirror exactly
search_graph("HistoricalCandleFetcher")     # confirm HD-3 shipped
search_graph("UpstoxCandleFetcher")         # confirm HD-4/5 shipped
search_graph("DhanCandleFetcher")           # check if HD-6 shipped or was skipped
search_graph("KiteCandleFetcher")           # check if HD-7 shipped or was skipped
search_graph("NseCsvVixFetcher")            # confirm HD-8 shipped
```
</content>
