# MVP — Database Schema

> Reflects the capital-deployment framing (2026-09-09 discussion, decisions resolved 2026-09-18) — see `tasks.md` "Design decisions" block. Each pick deploys a fixed ₹1,00,000 notional; **M-A** ships
> a single lump-sum fill first, **M-B** adds the 4-tranche ladder against the `mvp_tranches` table already present here.

Five tables in `data/portfolio/portfolio.sqlite`.

```sql
CREATE TABLE mvp_providers (
    provider_id   TEXT PRIMARY KEY,          -- UUID
    slug          TEXT NOT NULL UNIQUE,      -- e.g. 'dsij', 'prudentequity'
    display_name  TEXT NOT NULL,             -- e.g. 'DSIJ', 'Prudent Equity'
    source_type   TEXT NOT NULL,             -- 'TV' | 'TELEGRAM' | 'YOUTUBE' | 'OTHER'
    notes         TEXT,
    created_at    TEXT NOT NULL              -- ISO datetime UTC
);

CREATE TABLE mvp_categories (
    category_id   TEXT PRIMARY KEY,          -- UUID
    provider_id   TEXT NOT NULL REFERENCES mvp_providers(provider_id),
    slug          TEXT NOT NULL,             -- e.g. 'value-picks', 'multibagger'
    display_name  TEXT NOT NULL,             -- e.g. 'Value Picks', 'MultiBagger'
    notes         TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE (provider_id, slug)
);

CREATE TABLE mvp_recommendations (
    pick_id           TEXT PRIMARY KEY,         -- UUID
    category_id       TEXT REFERENCES mvp_categories(category_id),  -- NULL = unassigned
    symbol            TEXT NOT NULL,            -- NSE ticker e.g. 'RELIANCE'
    instrument_key    TEXT,                     -- Upstox key e.g. 'NSE_EQ|INE...'
    analyst           TEXT,
    entry_price       TEXT,                     -- Decimal as TEXT; NULL = PENDING
    pick_date         TEXT NOT NULL,            -- ISO datetime UTC
    target_price      TEXT,                     -- Decimal as TEXT; NULL = no target
    stop_loss         TEXT,                     -- Decimal as TEXT; tipster value, recorded
                                                 -- only — not acted on (hard stop below)
    notes             TEXT,
    status            TEXT NOT NULL DEFAULT 'PENDING',  -- see PickStatus enum
    closed_at         TEXT,
    close_price       TEXT,                     -- Decimal as TEXT
    capital_allotted  TEXT NOT NULL DEFAULT '100000',  -- Decimal as TEXT; fixed notional
    tranche_step_pct  TEXT NOT NULL DEFAULT '6',        -- Decimal as TEXT
    max_drawdown_pct  TEXT NOT NULL DEFAULT '30',       -- Decimal as TEXT; hard-stop trigger
    deployed_capital  TEXT NOT NULL DEFAULT '0',        -- Decimal as TEXT; sum of tranche fills
    total_qty         INTEGER NOT NULL DEFAULT 0,       -- sum of tranche qty
    avg_cost          TEXT,                     -- Decimal as TEXT; blended entry, NULL pre-fill
    idle_cash         TEXT NOT NULL DEFAULT '0',        -- Decimal as TEXT; floor-rounding residue
    realized_pnl      TEXT NOT NULL DEFAULT '0',        -- Decimal as TEXT; set on close
    benchmark_entry   TEXT,                     -- Decimal as TEXT; NIFTY 50 level at pick_date
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE mvp_tranches (
    tranche_id     TEXT PRIMARY KEY,          -- UUID
    pick_id        TEXT NOT NULL REFERENCES mvp_recommendations(pick_id),
    tranche_index  INTEGER NOT NULL,          -- 0..3; M-A (lump-sum) uses a single 0 row
    trigger_pct    TEXT NOT NULL,             -- Decimal as TEXT; 0/-6/-12/-18 from pick price
    fill_price     TEXT,                      -- Decimal as TEXT; NULL until filled
    qty             INTEGER,                  -- floored share qty; NULL until filled
    cost_bps       TEXT NOT NULL DEFAULT '25', -- Decimal as TEXT; round-trip cost knob
    filled_at      TEXT,                      -- ISO datetime UTC; NULL until filled
    UNIQUE (pick_id, tranche_index)
);

CREATE TABLE mvp_snapshots (
    snapshot_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    pick_id       TEXT NOT NULL REFERENCES mvp_recommendations(pick_id),
    ltp           TEXT NOT NULL,             -- Decimal as TEXT
    captured_at   TEXT NOT NULL             -- ISO datetime UTC
);

CREATE INDEX idx_mvp_snapshots_pick ON mvp_snapshots (pick_id, captured_at);
CREATE INDEX idx_mvp_tranches_pick ON mvp_tranches (pick_id, tranche_index);
```
