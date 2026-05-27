# backtest-eval-core — Database Schema

Five tables in `data/portfolio/portfolio.sqlite` (shared DB via `src/db.py`).
Analytics module (`src/analytics/`) is pure-function — no DB tables of its own.
All `BacktestStore` tables live in the same SQLite file as the portfolio, isolated by prefix.

---

## BacktestStore tables (task 1.5)

```sql
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id          TEXT PRIMARY KEY,           -- UUID, generated at run start
    strategy_name   TEXT NOT NULL,              -- e.g. 'csp_nifty_v1'
    strategy_version TEXT NOT NULL,             -- semver string e.g. '1.0.0'
    variant         TEXT,                       -- NULL | 'V1' | 'V2' | 'V3' (for CSP re-entry variants)
    start_date      TEXT NOT NULL,              -- ISO date YYYY-MM-DD (backtest window start)
    end_date        TEXT NOT NULL,              -- ISO date YYYY-MM-DD (backtest window end)
    config_json     TEXT NOT NULL,              -- JSON blob of strategy config at run time
    git_sha         TEXT NOT NULL,              -- git SHA of HEAD at run start (reproducibility)
    created_at      TEXT NOT NULL               -- ISO datetime UTC
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy
    ON backtest_runs (strategy_name, strategy_version);

CREATE TABLE IF NOT EXISTS backtest_daily_pnl (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES backtest_runs(run_id),
    date            TEXT NOT NULL,              -- ISO date YYYY-MM-DD
    unrealized_pnl  TEXT NOT NULL,             -- Decimal as TEXT
    realized_pnl    TEXT NOT NULL,             -- Decimal as TEXT
    mark_to_market  TEXT NOT NULL,             -- Decimal as TEXT (portfolio NAV at this date)
    open_positions  INTEGER NOT NULL,           -- count of open legs on this date
    UNIQUE (run_id, date)
);

CREATE INDEX IF NOT EXISTS idx_backtest_daily_pnl_run
    ON backtest_daily_pnl (run_id, date);

CREATE TABLE IF NOT EXISTS backtest_trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES backtest_runs(run_id),
    -- mirrors live `trades` table shape exactly:
    strategy_name   TEXT NOT NULL,
    leg_role        TEXT NOT NULL,
    instrument_key  TEXT NOT NULL,
    trade_date      TEXT NOT NULL,              -- ISO date YYYY-MM-DD
    action          TEXT NOT NULL,              -- 'BUY' | 'SELL'
    quantity        INTEGER NOT NULL,
    price           TEXT NOT NULL,             -- Decimal as TEXT
    notes           TEXT NOT NULL DEFAULT '',
    -- backtest-only additions:
    intended_risk   TEXT,                       -- Decimal as TEXT; NULL if not tracked
    fill_model      TEXT                        -- e.g. 'settle_price' | 'mid' | 'slippage_model_v1'
);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_run
    ON backtest_trades (run_id, strategy_name);

CREATE TABLE IF NOT EXISTS backtest_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES backtest_runs(run_id),
    metric_name     TEXT NOT NULL,              -- e.g. 'sharpe_ratio', 'max_drawdown_pct'
    value           TEXT NOT NULL,             -- Decimal as TEXT (or serialised value for non-Decimal)
    computed_at     TEXT NOT NULL,              -- ISO datetime UTC
    UNIQUE (run_id, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_backtest_metrics_run
    ON backtest_metrics (run_id);
```

---

## Notes

- `backtest_trades.intended_risk` — populated when the strategy config specifies a risk amount per trade. Used by `src/analytics/trade_metrics.py::r_multiple_distribution`. NULL is valid.
- `backtest_trades.fill_model` — records which price model produced the fill (Bhavcopy settle_price, mid, slippage-adjusted). Required for 1.11 bias-adjustment computation.
- `backtest_metrics` stores one row per metric name per run. `value` is always TEXT (Decimal serialisation). Non-numeric values (e.g. a date for `max_drawdown_trough_date`) are stored as ISO strings.
- `backtest_runs.variant` aligns with the three CSP re-entry variants from task 1.7 (`V1`=no reentry, `V2`=IVR-gated, `V3`=always-on). NULL for strategies without variants.
