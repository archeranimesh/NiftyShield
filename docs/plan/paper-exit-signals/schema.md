# paper-exit-signals — Database Schema

One new table added to `data/portfolio/portfolio.sqlite`.
Migration lives in `PaperStore.__init__` alongside the paper-backbone tables —
idempotent `CREATE TABLE IF NOT EXISTS`.

---

## `paper_exit_events`

```sql
CREATE TABLE IF NOT EXISTS paper_exit_events (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name           TEXT    NOT NULL,   -- e.g. "paper_nifty_spot"
    leg_name                TEXT    NOT NULL,   -- leg_role value from paper_trades
    trade_id                TEXT    NOT NULL,   -- paper_trade_id FK (no FK constraint — soft ref)
    snapshot_id             INTEGER,            -- FK to paper_leg_snapshots.id (nullable)
    event_time              TEXT    NOT NULL,   -- ISO 8601 UTC
    detected_by             TEXT    NOT NULL,   -- EOD | INTRADAY | MANUAL
    exit_signal             TEXT    NOT NULL,   -- enum (see below)
    severity                TEXT    NOT NULL,   -- INFO | WARNING | ACTION
    ltp                     REAL,               -- option LTP at detection time
    mid                     REAL,               -- (bid + ask) / 2 if available
    bid                     REAL,
    ask                     REAL,
    delta                   REAL,               -- option delta at detection time (NULL if unavailable)
    dte                     INTEGER,            -- calendar days to expiry
    entry_price             REAL    NOT NULL,   -- original entry credit/debit (Decimal stored as TEXT → cast at read)
    threshold_value         REAL,               -- the threshold that triggered (e.g. 0.55 for DELTA_STOP)
    -- Q2 dual-signal audit (council mandate — sell legs only)
    delta_stop_would_fire   INTEGER,            -- 1 if delta threshold breached, 0 if not, NULL for non-sell legs
    premium_stop_would_fire INTEGER,            -- 1 if premium multiple breached, 0 if not, NULL for non-sell legs
    actual_rule_used        TEXT,               -- which rule fired: DELTA | PREMIUM | BOTH | NEITHER
    -- Workflow
    status                  TEXT    NOT NULL DEFAULT 'OPEN',
                                                -- OPEN | ACKNOWLEDGED | ACTED | DISMISSED
    notes                   TEXT,
    created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);
```

### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_exit_events_strategy_leg
    ON paper_exit_events (strategy_name, leg_name, status);

CREATE INDEX IF NOT EXISTS idx_exit_events_trade
    ON paper_exit_events (trade_id, exit_signal);

CREATE INDEX IF NOT EXISTS idx_exit_events_open
    ON paper_exit_events (status, event_time)
    WHERE status = 'OPEN';
```

---

## `exit_signal` Enum Values

```
-- Profit / time exits (sell legs)
PROFIT_TARGET       -- mark ≤ 50% of entry credit (CC, CSP)
TIME_STOP           -- 21 calendar days elapsed (CSP only)
DTE_FORCED          -- DTE ≤ 5 with ITM/delta/residual condition (CC, Collar short call)
DTE_REVIEW          -- DTE ≤ 5 informational (PP, CSP)

-- Loss exits (sell legs)
LOSS_STOP           -- mark ≥ Nx entry credit (CSP 1.75×, CC 2.5×)
DELTA_STOP          -- delta breach (CSP ≥ 0.45, CC ≥ 0.55)
DELTA_WARN          -- delta approaching threshold (WARN only, no close)

-- Below-floor notice (CC only)
BELOW_FLOOR         -- entry credit < ₹12/unit; percentage exits suspended

-- Protection leg exits (PP, Collar put)
CRASH_MONETIZE      -- deep ITM + liquidity gate met (PP, Collar long put)

-- Collar-specific
COLLAR_CALL_DECAY   -- short call at 75% decay; close call only, keep put
COLLAR_CALL_WARN    -- short call delta ≥ +0.55 (informational, no close)
COLLAR_PUT_CRASH    -- Collar long put crash monetisation
COLLAR_CLOSE_ALL    -- full overlay exit (MANUAL_OVERRIDE)
COLLAR_REBALANCE    -- future: mid-cycle rebalance (reserved, not Phase 0)

-- Manual / system
MANUAL              -- user-initiated close not matching any rule
MANUAL_OVERRIDE     -- overrides the no-independent-stop rule for Collar
NONE                -- no signal (default / cleared state)
```

---

## `status` Lifecycle

```
OPEN         → signal detected, not yet acted on
ACKNOWLEDGED → user saw the Telegram alert (button pressed but "later" selected)
ACTED        → closure executed successfully
DISMISSED    → user explicitly dismissed (rejected the action)
```

---

## Monetary Fields Note

`entry_price`, `ltp`, `mid`, `bid`, `ask`, `threshold_value` are stored as `REAL`
in this table (not TEXT as in `paper_trades`) because:
- These are snapshots for audit, not ledger values
- Decimal precision at the cent level is sufficient for signal detection
- Read back with `Decimal(str(row["entry_price"]))` in any path that feeds into P&L

---

## Relationship to paper-backbone Tables

| Table | Role |
|---|---|
| `pending_approvals` | One row per ACTION signal pending user decision |
| `paper_exit_events` | Full event history regardless of status; never mutated after ACTED |
| `council_outputs` | Per-persona rapid council responses for ACTION signals |

An ACTION signal creates both a `paper_exit_events` row (this table) and a
`pending_approvals` row (backbone). The `pending_approvals.id` is stored in
`paper_exit_events.notes` as `approval_id=<n>` for cross-reference.
No hard FK — avoids migration order dependency.
