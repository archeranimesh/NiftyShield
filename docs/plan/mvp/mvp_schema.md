# MVP — Database Schema

Four tables in `data/portfolio/portfolio.sqlite`.

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
    pick_id        TEXT PRIMARY KEY,         -- UUID
    category_id    TEXT REFERENCES mvp_categories(category_id),  -- NULL = unassigned
    symbol         TEXT NOT NULL,            -- NSE ticker e.g. 'RELIANCE'
    instrument_key TEXT,                     -- Upstox key e.g. 'NSE_EQ|INE...'
    analyst        TEXT,
    entry_price    TEXT,                     -- Decimal as TEXT; NULL = PENDING
    pick_date      TEXT NOT NULL,            -- ISO datetime UTC
    target_price   TEXT,                     -- Decimal as TEXT; NULL = no target
    stop_loss      TEXT,                     -- Decimal as TEXT; NULL = no SL
    notes          TEXT,
    status         TEXT NOT NULL DEFAULT 'PENDING',  -- see PickStatus enum
    closed_at      TEXT,
    close_price    TEXT,                     -- Decimal as TEXT
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE mvp_snapshots (
    snapshot_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    pick_id       TEXT NOT NULL REFERENCES mvp_recommendations(pick_id),
    ltp           TEXT NOT NULL,             -- Decimal as TEXT
    captured_at   TEXT NOT NULL             -- ISO datetime UTC
);

CREATE INDEX idx_mvp_snapshots_pick ON mvp_snapshots (pick_id, captured_at);
```
