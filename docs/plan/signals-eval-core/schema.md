# signals-eval-core — Database Schema

Three tables added to `data/portfolio/portfolio.sqlite`.
All Decimal fields stored as TEXT. All timestamps stored as UTC ISO strings.

---

```sql
-- Daily regime classification for every historical trading day.
-- Populated by src/strategy/regime.py; consumed by all signal generators
-- and the validation pipeline for regime decomposition.
CREATE TABLE IF NOT EXISTS regime_tags (
    tag_date            TEXT PRIMARY KEY,    -- YYYY-MM-DD
    trend_score         REAL NOT NULL,       -- 50D lin-reg slope / 50D ATR (dimensionless)
    trend_label         TEXT NOT NULL,       -- "trending_up" | "range_bound" | "trending_down"
    vix_percentile      REAL NOT NULL,       -- 252D VIX trailing percentile rank (0.0–1.0)
    vol_label           TEXT NOT NULL,       -- "high_vol" | "normal_vol" | "low_vol"
    regime_cell         TEXT NOT NULL,       -- e.g. "trending_up|normal_vol"
    atr_14              REAL NOT NULL,       -- 14-day ATR in Nifty points
    atr_40              REAL NOT NULL,       -- 40-day ATR in Nifty points (spread width input)
    atr_pct_rank_252    REAL,               -- ATR% percentile rank over 252-bar window;
                                             -- NULL when insufficient history (<252 bars)
    created_at          TEXT NOT NULL        -- UTC ISO, when this row was written
);

-- Per-day signal emitted by each swing strategy generator.
-- One row per (signal_date, strategy). FLAT and NO_TRADE rows are recorded
-- so the validation pipeline can compute "days in-market" correctly.
CREATE TABLE IF NOT EXISTS swing_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_date     TEXT NOT NULL,          -- YYYY-MM-DD
    strategy        TEXT NOT NULL,          -- "donchian" | "orb" | "gap_fade"
    direction       TEXT NOT NULL,          -- "LONG" | "SHORT" | "FLAT" | "NO_TRADE"
    trigger_price   TEXT,                   -- Decimal as TEXT; NULL when FLAT / NO_TRADE
    stop_level      TEXT,                   -- Decimal as TEXT; trailing stop for Donchian,
                                             -- session open high/low for ORB/Gap Fade
    target_level    TEXT,                   -- Decimal as TEXT; NULL for Donchian (trailing stop);
                                             -- target price for ORB and Gap Fade
    atr_value       TEXT,                   -- Decimal as TEXT (14D ATR at signal time)
    or_high         TEXT,                   -- Decimal; ORB only — opening range high; NULL otherwise
    or_low          TEXT,                   -- Decimal; ORB only — opening range low; NULL otherwise
    gap_size_pct    TEXT,                   -- Decimal; Gap Fade only — gap as % of prev close; NULL otherwise
    expiry_date     TEXT,                   -- YYYY-MM-DD; ORB + Gap Fade only — selected weekly expiry
    regime_cell     TEXT NOT NULL,          -- regime_tags.regime_cell at signal_date
    excluded_reason TEXT,                   -- e.g. "vix_ivp_above_90th" | "rbi_mpc_day" |
                                             -- "thursday_expiry" | "budget_day" | "fomc_plus1" | NULL
    created_at      TEXT NOT NULL,          -- UTC ISO
    UNIQUE (signal_date, strategy)
);

-- Allocation decisions from each investment strategy signal generator.
-- One row per (decision_date, strategy). Quarterly for PE Band, monthly for SMA/Dual Momentum.
CREATE TABLE IF NOT EXISTS allocation_decisions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_date     TEXT NOT NULL,        -- YYYY-MM-DD (last trading day of check period)
    strategy          TEXT NOT NULL,        -- "sma_v1" | "dual_mom_v1" | "pe_band_v1"
    signal_value      TEXT NOT NULL,        -- Decimal as TEXT
                                             -- SMA: current Nifty monthly close
                                             -- Dual Momentum: trailing return (as fraction, e.g. "0.12")
                                             -- PE Band: trailing PE ratio
    signal_reference  TEXT NOT NULL,        -- Decimal as TEXT — the threshold being compared against
                                             -- SMA: N-month SMA value
                                             -- Dual Momentum: risk-free rate equivalent for same period
                                             -- PE Band: whichever threshold is active (low or high)
    allocation_pct    TEXT NOT NULL,        -- Decimal as TEXT (0.0, 0.30, 0.70, 1.0)
    allocation_reason TEXT NOT NULL,        -- one-line explanation, e.g. "close > 10M SMA → 100%"
    regime_cell       TEXT,                 -- regime_tags.regime_cell at decision_date; NULL if not tagged
    created_at        TEXT NOT NULL,        -- UTC ISO
    UNIQUE (decision_date, strategy)
);
```

---

### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_regime_tags_cell
    ON regime_tags (regime_cell, tag_date);

CREATE INDEX IF NOT EXISTS idx_swing_signals_strategy_date
    ON swing_signals (strategy, signal_date);

CREATE INDEX IF NOT EXISTS idx_allocation_strategy_date
    ON allocation_decisions (strategy, decision_date);
```

---

### Notes on existing tables reused by this module

Backtested trade records (entry/exit prices, P&L, equity curve) are written to the
existing `BacktestStore` tables (`backtest_runs`, `backtest_trades`, `backtest_daily_pnl`,
`backtest_metrics`) from `src/backtest/store.py` (task B1.1/B1.2 in `backtest-eval-core`).
`signals-eval-core` tasks write signal metadata into the three tables above and pass
trade results to `BacktestStore` — no duplicate persistence.

### regime_cell encoding

`regime_cell` is a pipe-delimited string: `"{trend_label}|{vol_label}"`.

| trend_label   | vol_label   | regime_cell                    |
|---------------|-------------|--------------------------------|
| trending_up   | high_vol    | `trending_up\|high_vol`        |
| trending_up   | normal_vol  | `trending_up\|normal_vol`      |
| trending_up   | low_vol     | `trending_up\|low_vol`         |
| range_bound   | high_vol    | `range_bound\|high_vol`        |
| range_bound   | normal_vol  | `range_bound\|normal_vol`      |
| range_bound   | low_vol     | `range_bound\|low_vol`         |
| trending_down | high_vol    | `trending_down\|high_vol`      |
| trending_down | normal_vol  | `trending_down\|normal_vol`    |
| trending_down | low_vol     | `trending_down\|low_vol`       |
