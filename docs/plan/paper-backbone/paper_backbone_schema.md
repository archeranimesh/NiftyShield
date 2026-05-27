# paper-backbone — Database Schema

Three new tables added to `data/portfolio/portfolio.sqlite`.
All migrations live in `PaperStore.__init__` — idempotent `CREATE TABLE IF NOT EXISTS`.

```sql
CREATE TABLE IF NOT EXISTS pending_approvals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name   TEXT    NOT NULL,
    event_type      TEXT    NOT NULL,
    council_output  TEXT    NOT NULL,   -- JSON blob (CouncilOutput serialised)
    status          TEXT    NOT NULL,   -- PENDING | APPROVED | REJECTED | EXPIRED
    approved_rank   INTEGER,            -- rank of the action the user approved (NULL until resolved)
    expires_at      TEXT    NOT NULL,   -- ISO UTC; set to +30 min at creation
    telegram_msg_id INTEGER,            -- message_id returned by Telegram API
    created_at      TEXT    NOT NULL,   -- ISO UTC
    resolved_at     TEXT                -- ISO UTC; NULL until APPROVED/REJECTED/EXPIRED
);

CREATE TABLE IF NOT EXISTS council_outputs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    approval_id     INTEGER NOT NULL REFERENCES pending_approvals(id),
    persona         TEXT    NOT NULL,   -- "QuantAnalyst" | "SpecGuardian" | "RiskManager" | "OptionsStrategist" | "Chairman"
    model           TEXT    NOT NULL,   -- e.g. "deepseek/deepseek-r1-0528"
    prompt_tokens   INTEGER,
    output_tokens   INTEGER,
    latency_ms      INTEGER,
    response        TEXT    NOT NULL,   -- raw model response text
    created_at      TEXT    NOT NULL    -- ISO UTC
);

CREATE TABLE IF NOT EXISTS daemon_heartbeat (
    id          INTEGER PRIMARY KEY CHECK (id = 1),   -- single-row table
    pid         INTEGER NOT NULL,
    last_beat   TEXT    NOT NULL,   -- ISO UTC; updated every monitor tick
    strategies  TEXT    NOT NULL,   -- JSON array of registered strategy_name strings
    last_event  TEXT                -- last SignalEvent.event_type seen; NULL if none yet
);
```

### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_pending_approvals_status
    ON pending_approvals (status, strategy_name);

CREATE INDEX IF NOT EXISTS idx_council_outputs_approval
    ON council_outputs (approval_id);
```

### Status lifecycle for `pending_approvals`

| Status | Set by |
|---|---|
| `PENDING` | `PaperStore.create_approval()` at creation |
| `APPROVED` | `TelegramGateway` callback handler on button press |
| `REJECTED` | `TelegramGateway` callback handler on reject button |
| `EXPIRED` | Background timeout scanner when `expires_at < now` |
