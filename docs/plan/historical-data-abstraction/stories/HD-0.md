# HD-0 — Historical data vendor cost + quality evaluation

> Assigned to: Claude
> Phase: 0 — Vendor Evaluation (gates all implementation phases)
> Priority: LOW

---

## Goal

Historical OHLC data is not free. Every API probe call costs either money (paid plans) or
quota (rate-limited free tiers). This story runs minimal, cost-bounded probe scripts to
measure quality and price across vendors, then produces a decision matrix that gates which
fetcher implementations actually get built in HD-6 through HD-8.

**Cost discipline is mandatory:** every probe uses a 5-trading-day window only.
No full-history pulls during evaluation. Dry-run mode must work before any live call.

---

## Vendors to evaluate

| Vendor | What they offer | Cost model | Credentials needed |
|--------|----------------|------------|-------------------|
| **Upstox** (Analytics Token) | Daily + intraday OHLC, India VIX via `NSE_INDEX\|India VIX` key | Included in active trading account | `UPSTOX_ANALYTICS_TOKEN` (already wired) |
| **Dhan** | Historical OHLC via `/v2/charts/historical` | Included in trading account | `DHAN_CLIENT_ID` + `DHAN_ACCESS_TOKEN` (already wired) |
| **Kite/Zerodha** | Historical OHLC via Kite Connect API | ₹2000/month subscription | `KITE_API_KEY` + `KITE_ACCESS_TOKEN` (add to `.env`) |
| **NSE CSV (bhavcopy)** | EOD options OHLCV — already implemented in `bhavcopy_ingest.py` | Free (NSE direct) | None — uses public NSE CDN |
| **Investing.com / Yahoo Finance** | India VIX, Nifty spot — unofficial/scraping | Free but fragile | None |

---

## Dimensions to measure per vendor

For each vendor, answer every question below. Record findings in `hd_analysis.md`.

### Coverage
- Instruments available: India VIX? Nifty spot? Nifty options chains? Individual equity ETFs?
- Max historical lookback (years)?
- Resolutions available: 1D, 1W, 1min, 5min, 15min, 1H?
- Does India VIX have pre-2020 daily history?

### Data quality
- Any gaps in the last 252 trading days (IVR window)?
- OHLC values — do they match NSE bhavcopy for the same dates?
- Timestamp: UTC or IST? Is timezone explicit or implicit?
- Are candle values floats or strings? Do they need Decimal conversion?

### API mechanics
- Authentication method (Bearer token / API key / session)?
- Rate limit: calls/minute? calls/day?
- Batch support: can you fetch multiple instruments in one call?
- Pagination: is there a max rows per response?
- Async support: does the SDK/API support async, or is it sync-only (like current Upstox path)?

### Cost
- Is historical data included in the base trading account, or is it a paid add-on?
- Price per call / price per month?
- Free tier limits (if any)?
- Estimated cost to bootstrap full 252-day VIX history from zero?

---

## Probe scripts to write

All under `scripts/dev/historical_probe/`. Each accepts `--dry-run` (prints what would be
fetched, estimated cost) and `--days N` (default 5, maximum 10 during evaluation).

### `scripts/dev/historical_probe/probe_vix_history.py`

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

### `scripts/dev/historical_probe/probe_ohlc_candles.py`

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

### `scripts/dev/historical_probe/probe_intraday_candles.py`

Fetches 5-minute candles for NIFTY for the last 1 trading day only.
**Cost warning printed before execution even without `--dry-run`.**

```bash
python -m scripts.dev.historical_probe.probe_intraday_candles --broker upstox
python -m scripts.dev.historical_probe.probe_intraday_candles --broker dhan
python -m scripts.dev.historical_probe.probe_intraday_candles --broker kite --dry-run
```

Prints:
- Bars returned (expect ~75 for a full session at 5-min)
- Any gaps within the session
- Latency

### `scripts/dev/historical_probe/probe_cost_estimate.py`

Does NOT call any API. Reads probe results from `data/historical_probe/` and prints a
cost/quality matrix.

```bash
python -m scripts.dev.historical_probe.probe_cost_estimate
```

Prints the decision matrix table from saved probe results. Designed to be run after the
other three probes so findings are summarized in one place.

---

## Output documents (commit after running probes)

### `docs/plan/historical-data-abstraction/hd_analysis.md`

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

### `docs/plan/historical-data-abstraction/hd_decision_matrix.md`

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

## Gate before closing HD-0

All four conditions must hold before marking HD-0 complete:

1. At least Upstox and Dhan probes ran successfully (Kite optional if credentials unavailable).
2. `hd_analysis.md` committed with raw observations.
3. `hd_decision_matrix.md` committed with recommended vendor per category.
4. `DECISIONS.md` entry added: `Historical data vendor assignments (YYYY-MM-DD, HD-0)`.
5. Tasks HD-6, HD-7 updated in `tasks.md` with "implement" or "skip" based on the matrix.

---

## Files to create

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

## Two-commit strategy

**Commit 1 — probe scripts only:**
```
feat(dev): historical data vendor probe scripts (cost-bounded)

Why: pre-implementation evaluation of Upstox/Dhan/Kite OHLC quality and cost
     before committing to HistoricalCandleFetcher implementations.
What:
- scripts/dev/historical_probe/: 4 probe scripts + package stub
- data/historical_probe/.gitkeep: output directory placeholder
Ref: docs/plan/historical-data-abstraction/stories/HD-0.md
```

**Commit 2 — findings + decision matrix (after running probes):**
```
docs(historical-data): vendor analysis findings + decision matrix

Why: HD-0 evaluation gates HD-6/HD-7 implementation decisions.
What:
- docs/plan/historical-data-abstraction/hd_analysis.md: raw probe findings
- docs/plan/historical-data-abstraction/hd_decision_matrix.md: vendor assignments
- DECISIONS.md: historical data vendor assignments entry
Ref: docs/plan/historical-data-abstraction/stories/HD-0.md
```

---

## Pre-baked graph context

```
search_graph("ingest_vix_from_api")     # existing Upstox fetch — pattern to replicate per vendor
search_graph("fetch_vix_latest")        # callers — must not break after probe scripts added
search_graph("load_vix_series")         # Parquet loader — reference for comparing probe output
git log --oneline -10 src/backtest/vix_ingest.py
```

Also read `REFERENCES.md` — `NSE_INDEX|India VIX` instrument key and NIFTYBEES key documented there.
