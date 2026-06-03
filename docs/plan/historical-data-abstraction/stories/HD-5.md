# HD-5 — Wire `UpstoxCandleFetcher` into `VixIngestPipeline`; deprecation shims

> Assigned to: Claude
> Phase: 2 — Fetcher Protocol + Upstox Implementation
> Blocked by: HD-4 must be merged first

---

## Goal

Connect the new `UpstoxCandleFetcher` to `VixIngestPipeline` and replace the two
module-level functions (`ingest_vix_from_api`, `fetch_vix_latest`) with deprecation shims
that delegate to the fetcher. The 5 script callers of `fetch_vix_latest` and the 1 caller
of `ingest_vix_from_api` must not break.

---

## Files to change

| File | Action |
|------|--------|
| `src/backtest/vix_ingest.py` | Edit — inject `HistoricalCandleFetcher`; shim existing functions |
| `tests/unit/backtest/test_vix_ingest.py` | Extend — injection + deprecation warning tests |

---

## What to implement

### `src/backtest/vix_ingest.py` — `VixIngestPipeline` refactor

The current module has no class — everything is module-level functions. Introduce
`VixIngestPipeline` (if it does not already exist) or extend it if it does:

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

### Deprecation shims (module-level, backward-compatible)

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

The existing 5 script callers (`record_paper_trade.py`, `paper_cc_entry.py`,
`pre_market_brief.py`, `healthcheck.py`) continue to work unchanged. Migration to
`VixIngestPipeline` is a separate, non-urgent cleanup.

---

## Tests — extend `tests/unit/backtest/test_vix_ingest.py`

1. **Injected fetcher used:** `VixIngestPipeline(fetcher=mock_fetcher)` — `ingest()` calls `mock_fetcher.fetch()`.
2. **Default fetcher is Upstox:** `VixIngestPipeline()._fetcher` is `UpstoxCandleFetcher` instance.
3. **`ingest_vix_from_api` shim emits DeprecationWarning.**
4. **`fetch_vix_latest` shim emits DeprecationWarning.**
5. **`fetch_latest` returns None on empty fetcher result:** mock fetcher returns `[]` → `pipeline.fetch_latest()` → `None`.

---

## Commit message

```
feat(backtest): VixIngestPipeline with injected fetcher; deprecation shims

Why: wires UpstoxCandleFetcher into VIX ingest pipeline; shims preserve all 5
     existing script callers without modification.
What:
- src/backtest/vix_ingest.py: VixIngestPipeline class + shims on ingest_vix_from_api
  and fetch_vix_latest
- tests/unit/backtest/test_vix_ingest.py: 5 additional injection + shim tests
Ref: docs/plan/historical-data-abstraction/stories/HD-5.md
```

---

## Pre-baked graph context

```
search_graph("VixIngestPipeline")         # may already exist from BA-10 — check before creating
search_graph("fetch_vix_latest")          # all 5 callers — verify none break
search_graph("ingest_vix_from_api")       # 1 caller (bhavcopy_bootstrap? or pipeline script)
search_graph("UpstoxCandleFetcher")       # confirm HD-4 shipped
git log --oneline -10 src/backtest/vix_ingest.py
```

Note: if BA-10 was completed before this story, `VixIngestPipeline` may already exist with
a `VixFetcher` protocol. If so, replace `VixFetcher` with `HistoricalCandleFetcher` —
do not maintain two parallel fetcher protocols for the same thing.
