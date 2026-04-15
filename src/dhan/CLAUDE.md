# src/dhan/ — Module Context

> Dhan portfolio reader: live holdings, market quote LTP, Equity/Bond classification.

## What This Module Does

Fetches delivery holdings from the Dhan broker API, enriches with prices from
the **Upstox batch LTP call** (not Dhan's paid Data API), classifies each
holding as Equity or Bond, and persists snapshots for day-change delta tracking.

## Key Design Decisions

- **LTP from Upstox, not Dhan** — Dhan's `POST /v2/marketfeed/ltp` requires the
  paid Data API (₹499/month) and returns 401 on free tier. Instead, Upstox keys
  are derived as `NSE_EQ|{ISIN}` via `upstox_keys_for_holdings()` and piggybacked
  onto the existing batch LTP call in `daily_snapshot._async_main`. Use
  `enrich_with_upstox_prices()`. `enrich_with_ltp()` (Dhan API path) exists but
  is not used in production.
- **Two-phase fetch in daily_snapshot** — Holdings are fetched *before* the Upstox
  LTP batch (via `fetch_dhan_holdings()`), keys added to `all_keys`, then enriched
  *after* via `enrich_with_upstox_prices()`. Single batch, zero extra API cost.
- **Classification config** — `_BOND_SYMBOLS` frozenset in `reader.py` maps known
  liquid/bond ETF symbols. Everything else defaults to EQUITY. Add new bond
  instruments here (one line).
- **Double-count prevention** — `build_dhan_holdings()` accepts `exclude_isins`.
  `_async_main` extracts ISINs from `NSE_EQ|{ISIN}` strategy leg keys so
  EBBETF0431 and LIQUIDBEES are never double-counted.
- **Non-fatal in cron** — Dhan block wrapped in try/except. Expired token (24h
  expiry) → `[unavailable]` in Bonds section, rest of summary unaffected.
- **Monetary values as Decimal** — TEXT storage, same as portfolio/ and mf/.

## Data Flow

```
Dhan GET /v2/holdings → raw list
  ↓ build_dhan_holdings(exclude_isins)      — filter + classify
  ↓ upstox_keys_for_holdings()              — derive NSE_EQ|{ISIN} keys
  ↓ [piggybacked onto Upstox batch LTP]
  ↓ enrich_with_upstox_prices(prices)       — prices dict from Upstox
  ↓ build_dhan_summary(prev_holdings)
DhanPortfolioSummary → _build_portfolio_summary → _format_combined_summary
  ↓ DhanStore.record_snapshot()             — for next day's Δday
```

## Files

| File | Role |
|---|---|
| `models.py` | `DhanHolding` + `DhanPortfolioSummary` frozen dataclasses |
| `reader.py` | fetch_dhan_holdings, build_dhan_holdings, enrich_with_upstox_prices, upstox_keys_for_holdings, build_dhan_summary, fetch_dhan_portfolio |
| `store.py` | `DhanStore` — dhan_holdings_snapshots table, upsert, get_prev_snapshot |

## Dhan API Endpoints Used

| Endpoint | Method | Purpose |
|---|---|---|
| `/v2/holdings` | GET | Delivery holdings — qty, avgCostPrice, securityId, isin, exchange |

## Instruments

| Symbol | ISIN | Classification |
|---|---|---|
| NIFTYIETF | INF109K012R6 | EQUITY |
| LIQUIDCASE | INF0R8F01034 | BOND |
