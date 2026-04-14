# src/dhan/ — Module Context

> Dhan portfolio reader: live holdings, market quote LTP, Equity/Bond classification.

## What This Module Does

Fetches delivery holdings from the Dhan broker API, retrieves current prices
via Dhan's own market quote endpoint, classifies each holding as Equity or
Bond, and persists snapshots for day-change delta tracking.

## Key Design Decisions

- **LTP from Dhan** — Uses `POST /v2/marketfeed/ltp` with `securityId` (from holdings
  response). No dependency on Upstox for Dhan holdings.
- **Classification config** — `_BOND_SYMBOLS` frozenset in `reader.py` maps known
  liquid/bond ETF symbols. Everything else defaults to EQUITY. Update this set
  when adding a new bond instrument.
- **Double-count prevention** — `build_dhan_holdings()` accepts `exclude_isins` set.
  The caller (daily_snapshot.py) passes ISINs extracted from existing strategy legs
  so instruments like EBBETF0431 and LIQUIDBEES aren't counted twice.
- **Non-fatal in cron** — The entire Dhan block in daily_snapshot.py is wrapped in
  try/except. Expired token → Dhan section shows [unavailable], rest of summary works.
- **Monetary values as Decimal** — Same TEXT storage convention as portfolio/ and mf/.

## Data Flow

```
Dhan GET /v2/holdings → raw holdings list
  ↓ build_dhan_holdings(exclude_isins)
  ↓ classify each as EQUITY or BOND
  ↓ build_security_id_map()
Dhan POST /v2/marketfeed/ltp → {exchange: {security_id: {last_price}}}
  ↓ enrich_with_ltp()
  ↓ build_dhan_summary(prev_holdings)
DhanPortfolioSummary → daily_snapshot formatter
```

## Files

| File | Role |
|---|---|
| `models.py` | `DhanHolding` + `DhanPortfolioSummary` frozen dataclasses |
| `reader.py` | Fetch, classify, enrich, summarise. Pure functions + 2 HTTP callers |
| `store.py` | `DhanStore` — SQLite persistence, day-change lookups |

## Dhan API Endpoints Used

| Endpoint | Method | Purpose |
|---|---|---|
| `/v2/holdings` | GET | Delivery holdings (qty, avgCostPrice, securityId, isin) |
| `/v2/marketfeed/ltp` | POST | LTP by securityId. Body: `{"NSE_EQ": [id1, id2]}` |

## Instruments

| Symbol | ISIN | Security ID | Classification |
|---|---|---|---|
| NIFTYIETF | INF109K012R6 | (lookup from API) | EQUITY |
| LIQUIDCASE | INF0R8F01034 | (lookup from API) | BOND |
