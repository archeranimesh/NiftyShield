# Backtest Methodology Domain

You are advising on the backtest engine for a Nifty 50 monthly options selling strategy
(NiftyShield). Your recommendation must work within these hard constraints.

## Stack

- Python 3.10+, pandas / numpy / scipy, pyarrow / Parquet
- SQLite (WAL mode) for relational data; Parquet under data/offline/ for time-series OHLCV
- No DuckDB yet (planned for Phase 2+ only if EOD volumes justify it)
- No TimescaleDB (deferred indefinitely — EOD Bhavcopy ~4M rows fits Parquet + SQLite)

## Data Available

- NSE F&O Bhavcopy: free, EOD, 2016–present. Fields: symbol, expiry, strike, option_type,
  open, high, low, close, volume, OI, settle_price. No historical bid/ask. No historical Greeks.
- Nifty Futures settle_price: in the same daily Bhavcopy CSV (FUTIDX rows).
- Nifty 50 spot OHLC: Upstox historical candles (free, Analytics Token).
- India VIX daily OHLC: Upstox historical candles (free).
- All paid data sources evaluated and rejected: TrueData (shallow history), DhanHQ (5-day
  intraday depth only, not 5 years as documented).

## Settled Decisions — Do Not Re-Litigate

These have already been decided by a prior council or architectural review:

| Decision | Outcome | Date |
|---|---|---|
| Pricing model for IV reconstruction | Black '76 with Nifty Futures as forward (not BS with spot) | 2026-04-30 |
| Risk-free rate | Stepped RBI Repo Rate table (~20 entries 2016–present) | 2026-04-30 |
| Delta computation | Quadratic smile fit in log-moneyness, then delta from smoothed IV | 2026-04-30 |
| Option price field | Blend: close if liquid+sane, settle_price as fallback | 2026-04-30 |
| IV percentile series | 30-DTE constant-maturity ATM IV, variance-space interpolation | 2026-04-30 |
| Slippage model | Absolute INR, VIX-regime-aware, OI liquidity multiplier | 2026-04-30 |
| Slippage bias | Err modestly conservative (60th–70th percentile of spreads) | 2026-04-30 |
| Data source | NSE F&O Bhavcopy (free, exchange-authoritative, 2016–present) | 2026-04-27 |
| Storage | Parquet + SQLite (not TimescaleDB, not DuckDB yet) | 2026-04-27 |

## Primary Strategy

Monthly Cash Secured Put (CSP) on Nifty 50 index options:
- Entry: 25-delta short put, 30–45 DTE, monthly expiry (last Thursday)
- Exit: 50% profit target / 21 DTE time stop / 2× credit loss stop / −0.45 delta stop
- 1 lot = 50 units. No intra-trade adjustments in v1 spec.
- NiftyBees ETF collateral leg must be included in P&L alongside the short put.
