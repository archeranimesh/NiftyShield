# BUG-6 + BUG-7 — Overlay CC State Never Closed + Spurious Jun8 Trade (discovered 2026-06-09)

> Root-cause investigation: querying `paper_trades WHERE leg_role='overlay_cc' AND state='OPEN'`
> returns ALL historical overlay_cc rows including closed cycles.  Two distinct bugs found.
> Fix order: BUG-6 first (enum + store method), BUG-7 second (data cleanup + _close_leg).

---

## Background — What Was Observed

Querying the live DB for open overlay_cc positions returned 8 rows instead of 1:

```
paper_nifty_proxy | overlay_cc | NSE_FO|65900 | 2026-06-09 | SELL | 65  | 543.90 | OPEN
paper_nifty_proxy | overlay_cc | NSE_FO|71474 | 2026-06-08 | SELL | 65  | 12.60  | OPEN  ← spurious
paper_nifty_proxy | overlay_cc | NSE_FO|71474 | 2026-06-08 | BUY  | 130 | 12.60  | OPEN  ← wrong qty
paper_nifty_proxy | overlay_cc | NSE_FO|71474 | 2026-05-11 | SELL | 65  | 221.38 | OPEN  ← closed
paper_nifty_spot  | overlay_cc | NSE_FO|65900 | 2026-06-09 | SELL | 65  | 543.90 | OPEN
paper_nifty_spot  | overlay_cc | NSE_FO|71474 | 2026-06-08 | SELL | 65  | 12.60  | OPEN  ← spurious
paper_nifty_spot  | overlay_cc | NSE_FO|71474 | 2026-06-08 | BUY  | 130 | 12.60  | OPEN  ← wrong qty
paper_nifty_spot  | overlay_cc | NSE_FO|71474 | 2026-05-11 | SELL | 65  | 221.38 | OPEN  ← closed
```

**Actual current position:** only the Jun9 SELL 65 @ 543.90 on instrument 65900 is live.

Net qty cross-check on instrument 71474 (per strategy):
- May11 SELL 65 + Jun8 SELL 65 + Jun8 BUY 130 = net 0  ✓ (closed, by accident — see BUG-7)

Net qty on instrument 65900 = -65  ✓ (live position)

---

## BUG-6 — `TradeState` has no `CLOSED` value; `_close_leg` never transitions state

**Files affected:**
- `src/paper/models.py` — `TradeState` enum
- `src/paper/store.py` — `PaperStore` (new method needed)
- `scripts/strategies/three_track/paper_3track_overlay_roll.py` — `_close_leg`

**Problem:**

`TradeState` only defines `OPEN`, `DEFENDED`, `RE_ENTRY_PENDING`.  There is no `CLOSED`
state.  When `_close_leg` calls `store.record_trade(close_trade)`, it inserts the BUY row
with the default `state=TradeState.OPEN`.  It never calls `update_trade_state` on the
original SELL row.  Result: every row in `paper_trades` keeps `state='OPEN'` forever —
including positions that were rolled months ago.  Any query that filters on
`state = 'OPEN'` returns the full history, not the current position.

Additionally, `paper_trades` schema has a CHECK constraint:

```sql
CHECK(state IN ('OPEN','DEFENDED','RE_ENTRY_PENDING'))
```

This must be extended to allow `'CLOSED'`.  An idempotent migration script is required
(SQLite does not support `ALTER COLUMN` — the column check is part of the CREATE TABLE
statement; migration must recreate the table).

**Root cause:** `TradeState` was designed for CSP lifecycle (OPEN → DEFENDED →
RE_ENTRY_PENDING).  The overlay roll path (`_close_leg` → `record_trade`) was added later
and never wired to the state machine.

**Fix — three parts:**

### Part 1 — `src/paper/models.py`

```python
class TradeState(str, Enum):
    OPEN = "OPEN"
    DEFENDED = "DEFENDED"
    RE_ENTRY_PENDING = "RE_ENTRY_PENDING"
    CLOSED = "CLOSED"          # ← add this
```

### Part 2 — `src/paper/store.py`

Add a new method `mark_trade_closed` that locates the original SELL row by
(strategy_name, leg_role, instrument_key, action=SELL) and flips its state to CLOSED:

```python
def mark_trade_closed(
    self,
    strategy_name: str,
    leg_role: str,
    instrument_key: str,
) -> bool:
    """Mark the open SELL trade for this overlay leg as CLOSED.

    Finds the most recent SELL row for (strategy_name, leg_role, instrument_key)
    with state != CLOSED and updates it to CLOSED.

    Args:
        strategy_name:  Strategy owning the trade.
        leg_role:       Overlay leg role (e.g. 'overlay_cc').
        instrument_key: Instrument being closed.

    Returns:
        True if a row was updated; False if no matching open SELL found.
    """
    with _connect(self.db_path) as conn:
        cur = conn.execute(
            """UPDATE paper_trades
               SET state = 'CLOSED'
               WHERE id = (
                   SELECT id FROM paper_trades
                   WHERE strategy_name = ?
                     AND leg_role = ?
                     AND instrument_key = ?
                     AND action = 'SELL'
                     AND state != 'CLOSED'
                   ORDER BY trade_date DESC, id DESC
                   LIMIT 1
               )""",
            (strategy_name, leg_role, instrument_key),
        )
        return cur.rowcount == 1
```

Also update the `paper_trades` CHECK constraint via migration (see Part 4).

### Part 3 — `scripts/strategies/three_track/paper_3track_overlay_roll.py` — `_close_leg`

After `store.record_trade(close_trade)`, call `store.mark_trade_closed`:

```python
if not dry_run:
    store.record_trade(close_trade)
    closed = store.mark_trade_closed(
        existing.strategy_name,
        existing.leg_role,
        existing.instrument_key,
    )
    if not closed:
        logger.warning(
            "close_leg.mark_closed_failed — original SELL not found",
            strategy=existing.strategy_name,
            leg_role=existing.leg_role,
            instrument_key=existing.instrument_key,
        )
```

### Part 4 — Migration script `scripts/dev/migrate_add_closed_state.py`

SQLite does not support ALTER TABLE ... MODIFY COLUMN.  The CHECK constraint is baked
into the CREATE TABLE DDL.  Migration approach: rename old table, recreate with new
CHECK, copy data, drop old.  Must be idempotent (safe to re-run).

```python
MIGRATE_SQL = """
BEGIN;

-- Step 1: rename existing table
ALTER TABLE paper_trades RENAME TO paper_trades_old;

-- Step 2: recreate with CLOSED in CHECK
CREATE TABLE paper_trades (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name  TEXT NOT NULL,
    leg_role       TEXT NOT NULL,
    instrument_key TEXT NOT NULL,
    trade_date     TEXT NOT NULL,
    action         TEXT NOT NULL,
    quantity       INTEGER NOT NULL,
    price          TEXT NOT NULL,
    notes          TEXT NOT NULL DEFAULT '',
    ivr_at_entry   REAL DEFAULT NULL,
    state          TEXT NOT NULL DEFAULT 'OPEN'
                   CHECK(state IN ('OPEN','DEFENDED','RE_ENTRY_PENDING','CLOSED')),
    UNIQUE(strategy_name, leg_role, trade_date, action)
);

-- Step 3: copy data
INSERT INTO paper_trades SELECT * FROM paper_trades_old;

-- Step 4: drop old
DROP TABLE paper_trades_old;

COMMIT;
"""
```

Note: BUG-4 (from `stories_bugs_jun09.md`) requires adding `instrument_key` to the UNIQUE
constraint.  If BUG-4 is fixed in the same migration, combine both changes into one
migration pass to avoid two table recreations.

**Tests to add (`tests/unit/paper/test_store_mark_closed.py`):**
- `mark_trade_closed` on an open SELL → returns True, row has state='CLOSED'
- `mark_trade_closed` on an already-closed row → returns False (no double-flip)
- `mark_trade_closed` with non-existent instrument_key → returns False
- `_close_leg` dry_run=True: `mark_trade_closed` NOT called
- `_close_leg` dry_run=False: `mark_trade_closed` called; original SELL state='CLOSED'

---

## BUG-7 — Jun8 data corruption: wrong BUY qty (130 vs 65) + spurious SELL on expiring instrument

**Files affected:**
- Live DB `data/portfolio/portfolio.sqlite` — data cleanup only (no code change)

**Problem:**

The Jun8 roll on instrument 71474 (NIFTY 25000 CE, expiry 2026-06-30) left two bad rows
per strategy track:

| Date    | Action | Qty | Price | Issue |
|---------|--------|-----|-------|-------|
| Jun8    | SELL   | 65  | 12.6  | Spurious new open on a 22-DTE near-worthless instrument — should not exist |
| Jun8    | BUY    | 130 | 12.6  | Wrong qty — close of the May11 SELL (qty=65) should be BUY 65, not BUY 130 |

**Why net qty is accidentally correct:**

Per-track net on instrument 71474:
`-65 (May11 SELL) + (-65 Jun8 SELL) + 130 (Jun8 BUY) = 0`

This accidentally nets to zero — so `_find_expiring_overlay` correctly sees net=0 and
skips 71474 for future rolls.  No position is double-counted.  But the rows are noise and
will mislead any future audit, P&L reporting, or state query.

**Root cause (likely sequence on Jun8):**

1. Roll script ran in dry-run: showed BUY 65 close + new SELL on a fresh quarterly
2. User instead ran `record_paper_trade.py` manually with `--qty 130` (intending to cover
   both tracks' 65 lots in a single command — incorrect; each strategy_name needs its own
   record).  This wrote BUY 130 on 71474 for each track.
3. `_open_new_leg` (or a separate manual entry) then opened SELL 65 @ 12.6 on the same
   expiring instrument 71474 rather than the new Sep29 quarterly.
4. Next day (Jun9), the actual quarterly CC was opened manually:
   SELL 65 @ 543.90 on instrument 65900 (strike=24000, expiry=2026-09-29).

**Data cleanup:** see "DB Cleanup Required" section below.

---

## DB Cleanup Required (run before deploying BUG-6 fix)

**For both `paper_nifty_proxy` and `paper_nifty_spot`:**

```sql
-- Step 1: verify current state before touching anything
SELECT id, strategy_name, leg_role, instrument_key, trade_date, action, quantity, price, state
FROM paper_trades
WHERE leg_role = 'overlay_cc'
ORDER BY strategy_name, trade_date, id;

-- Step 2: delete the spurious Jun8 SELL 65 @ 12.6 on instrument 71474
-- (new open on an already-rolling position — should not exist)
DELETE FROM paper_trades
WHERE leg_role = 'overlay_cc'
  AND instrument_key LIKE '%71474%'
  AND trade_date = '2026-06-08'
  AND action = 'SELL'
  AND CAST(price AS REAL) = 12.6;

-- Step 3: fix BUY 130 → BUY 65 on instrument 71474 (close qty must match open qty)
UPDATE paper_trades
SET quantity = 65
WHERE leg_role = 'overlay_cc'
  AND instrument_key LIKE '%71474%'
  AND trade_date = '2026-06-08'
  AND action = 'BUY'
  AND quantity = 130;

-- Step 4: verify net qty on 71474 is now 0 (closed)
SELECT
    strategy_name,
    SUM(CASE WHEN action='SELL' THEN -quantity ELSE quantity END) AS net_qty
FROM paper_trades
WHERE leg_role = 'overlay_cc'
  AND instrument_key LIKE '%71474%'
GROUP BY strategy_name;
-- Expected: net_qty = 0 for both paper_nifty_proxy and paper_nifty_spot

-- Step 5: verify Jun9 SELL on 65900 is the only remaining open position
SELECT strategy_name, instrument_key, trade_date, action, quantity, price, state
FROM paper_trades
WHERE leg_role = 'overlay_cc'
ORDER BY strategy_name, trade_date;
```

**After BUG-6 migration is deployed**, additionally run:

```sql
-- Mark May11 SELL and Jun8 BUY (the legitimate close) as CLOSED
UPDATE paper_trades
SET state = 'CLOSED'
WHERE leg_role = 'overlay_cc'
  AND instrument_key LIKE '%71474%';
-- Both the May11 SELL and the Jun8 BUY should be CLOSED; Jun9 SELL stays OPEN.
```

---

## Fix Dependency Order

```
BUG-6 Part 1+2+3 (TradeState.CLOSED + mark_trade_closed + _close_leg)
  ↓
Migration script (combine with BUG-4 migration if not yet done)
  ↓
BUG-7 Data cleanup (run cleanup SQL against live DB)
  ↓
Manually flip May11+Jun8 rows on 71474 to CLOSED (post-migration SQL above)
```

Note: BUG-4 from `stories_bugs_jun09.md` (add `instrument_key` to UNIQUE constraint) and
this BUG-6 migration both require a table recreation.  Combine into one migration pass:

```sql
UNIQUE(strategy_name, leg_role, instrument_key, trade_date, action)  -- BUG-4
CHECK(state IN ('OPEN','DEFENDED','RE_ENTRY_PENDING','CLOSED'))       -- BUG-6
```
