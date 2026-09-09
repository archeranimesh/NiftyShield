# Signals — Database Schema

Four tables added to `data/portfolio/portfolio.sqlite`.

```sql
CREATE TABLE IF NOT EXISTS signal_inputs (
    trade_date    TEXT PRIMARY KEY,    -- YYYY-MM-DD
    snapshot_json TEXT NOT NULL        -- full MarketSnapshot serialised as JSON
);

CREATE TABLE IF NOT EXISTS signal_responses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date   TEXT    NOT NULL,
    provider     TEXT    NOT NULL,     -- "grok" | "gpt4o" | "gemini"
    direction    TEXT    NOT NULL,     -- "BULLISH" | "BEARISH" | "NEUTRAL"
    confidence   INTEGER NOT NULL,     -- 1–5
    strike       INTEGER NOT NULL,
    premium_low  TEXT    NOT NULL,     -- Decimal as TEXT
    premium_high TEXT    NOT NULL,     -- Decimal as TEXT
    key_reason   TEXT    NOT NULL,
    key_risk     TEXT    NOT NULL,
    raw_response TEXT    NOT NULL,     -- full JSON string from model
    created_at   TEXT    NOT NULL,     -- UTC ISO
    UNIQUE (trade_date, provider)
);

CREATE TABLE IF NOT EXISTS daily_signals (
    trade_date           TEXT PRIMARY KEY,
    consensus_direction  TEXT NOT NULL,
    consensus_confidence TEXT NOT NULL,  -- Decimal as TEXT
    trade_action         TEXT NOT NULL,  -- "BUY_CALL" | "BUY_PUT" | "NO_TRADE"
    recommended_strike   INTEGER,        -- NULL when NO_TRADE
    agreeing_models      TEXT NOT NULL,  -- JSON array e.g. '["grok","gemini"]'
    dissenting_models    TEXT NOT NULL,  -- JSON array
    created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_outcomes (
    trade_date         TEXT PRIMARY KEY,
    trade_action       TEXT NOT NULL,
    recommended_strike INTEGER,
    entry_premium      TEXT,            -- Decimal as TEXT; NULL if not executed
    exit_premium       TEXT,            -- Decimal as TEXT
    pnl_per_lot        TEXT,            -- Decimal as TEXT
    nifty_close        TEXT NOT NULL,   -- Decimal as TEXT
    executed           INTEGER NOT NULL DEFAULT 0,  -- boolean (0/1)
    phase              TEXT NOT NULL DEFAULT 'openrouter_only',
                                        -- 'openrouter_only' | 'search_enabled'
    notes              TEXT,
    recorded_at        TEXT NOT NULL    -- UTC ISO
);
```

### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_signal_responses_date
    ON signal_responses (trade_date);

CREATE INDEX IF NOT EXISTS idx_signal_outcomes_phase
    ON signal_outcomes (phase, trade_date);
```

### Phase column values

| Value | When |
|---|---|
| `openrouter_only` | Phase 1 — all providers via OpenRouter, no search capability |
| `search_enabled` | Phase 2 — Grok via xAI (search=True), Gemini via Google AI SDK (grounding) |

This column lets `signal_report.py` split performance between the two phases and measure
how much search capability contributes to edge.
