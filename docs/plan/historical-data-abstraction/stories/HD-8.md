# HD-8 — `NseCsvCandleFetcher` (broker-agnostic VIX via NSE CSV)

> Assigned to: Antigravity
> Phase: 3 — Alternative Vendor Implementations
> Blocked by: HD-3 must be merged first. Can run in parallel with HD-6 / HD-7.
> Note: This fetcher covers VIX only. General OHLC is not available from NSE CSV.

---

## Goal

`src/backtest/vix_ingest.py` already has `ingest_vix_from_csv()` — a function that reads
a locally downloaded NSE VIX CSV file and writes it to Parquet. This story wraps it as a
proper `HistoricalCandleFetcher` so it can be used as a zero-cost fallback when no broker
credentials are available (CI, offline backtesting, air-gapped environments).

This fetcher is **read-from-file only** — it does not download the CSV. The operator
downloads the NSE VIX history CSV from `https://www.nseindia.com/products/content/equities/indices/historical_index_data.htm`
and places it at a known path. The fetcher reads it.

---

## Files to change

| File | Action |
|------|--------|
| `src/backtest/fetchers/nse_csv.py` | New — `NseCsvVixFetcher` |
| `tests/unit/backtest/test_fetcher_nse_csv.py` | New — 6 tests using a fixture CSV |
| `tests/fixtures/historical/nse_vix_sample.csv` | New — 10-row NSE VIX CSV fixture |

---

## What to implement

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

## Fixture — `tests/fixtures/historical/nse_vix_sample.csv`

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

## Tests — `tests/unit/backtest/test_fetcher_nse_csv.py`

1. **Happy path:** request covering 5 rows → 5 `CandleRecord` rows, correct dates and closes.
2. **Date filter:** request covering only 3 of 10 rows → returns exactly 3.
3. **Out-of-range request:** date range beyond CSV coverage → returns `[]`.
4. **Wrong instrument:** `instrument_key != "NSE_INDEX|India VIX"` → raises `ValueError`.
5. **Missing CSV file:** `NseCsvVixFetcher(Path("/nonexistent.csv"))` → `fetch()` raises `FileNotFoundError`.
6. **Protocol conformance:** `isinstance(NseCsvVixFetcher(path), HistoricalCandleFetcher)` → `True`.

---

## Commit message

```
feat(backtest): NseCsvVixFetcher — zero-cost offline VIX fallback

Why: broker-agnostic VIX fetcher for CI, offline backtesting, and credential-free
     environments; reads locally downloaded NSE VIX CSV.
What:
- src/backtest/fetchers/nse_csv.py: NseCsvVixFetcher conforming to HistoricalCandleFetcher
- tests/unit/backtest/test_fetcher_nse_csv.py: 6 tests
- tests/fixtures/historical/nse_vix_sample.csv: 10-row fixture
Ref: docs/plan/historical-data-abstraction/stories/HD-8.md
```

---

## Pre-baked graph context

```
search_graph("ingest_vix_from_csv")      # existing CSV parsing logic to port
search_graph("HistoricalCandleFetcher")  # confirm HD-3 shipped
search_graph("NseCsvVixFetcher")         # must be zero results — confirm not already created
```
