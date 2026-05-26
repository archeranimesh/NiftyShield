# Story: MVP — Multi-bagger Value Picks Tracker (`src/mvp/`)

> Status: PLANNED — not started  
> Owner: Animesh + Cowork  
> Priority: after Task 3 (June 2026 Finideas roll cycle)

---

## Problem

Stock recommendations arrive throughout the day from multiple providers (TV channels,
Telegram, research houses like DSIJ). There is no structured way to capture them quickly,
fill in details EOD, or measure provider-level hit rates over time.

---

## Name

**MVP** — **M**ulti-bagger, **V**alue, **P**ick  
The three most common recommendation categories in Indian retail research.  
CLI command: `mvp`. Module: `src/mvp/`. Tables: `mvp_providers`, `mvp_categories`, `mvp_recommendations`, `mvp_snapshots`.

---

## Design

### Hierarchy

```
Provider  (DSIJ, prudentequity, CNBC)
  └── Category  (Value Picks, MultiBagger, TAS, general)
        └── Pick  (RELIANCE @ 1200, target 1400, SL 1100)
              └── Snapshot  (hourly LTP during market hours)
```

### Status flow

```
PENDING → OPEN → TARGET_HIT
                → SL_HIT
                → MANUAL_CLOSE
```

- `PENDING`: symbol captured, `entry_price` not yet set. Cron ignores these rows.
- `OPEN`: `entry_price` is set. Cron tracks LTP, checks target/SL breach.
- Terminal states: set by cron (auto-close) or manual `mvp close` command.

### Schema — 4 tables in `portfolio.sqlite`

**`mvp_providers`**
```sql
CREATE TABLE mvp_providers (
    provider_id   TEXT PRIMARY KEY,          -- UUID
    slug          TEXT NOT NULL UNIQUE,      -- e.g. 'dsij', 'prudentequity'
    display_name  TEXT NOT NULL,             -- e.g. 'DSIJ', 'Prudent Equity'
    source_type   TEXT NOT NULL,             -- 'TV' | 'TELEGRAM' | 'YOUTUBE' | 'OTHER'
    notes         TEXT,
    created_at    TEXT NOT NULL              -- ISO datetime UTC
);
```

**`mvp_categories`**
```sql
CREATE TABLE mvp_categories (
    category_id   TEXT PRIMARY KEY,          -- UUID
    provider_id   TEXT NOT NULL REFERENCES mvp_providers(provider_id),
    slug          TEXT NOT NULL,             -- e.g. 'value-picks', 'multibagger'
    display_name  TEXT NOT NULL,             -- e.g. 'Value Picks', 'MultiBagger'
    notes         TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE (provider_id, slug)
);
```

**`mvp_recommendations`**
```sql
CREATE TABLE mvp_recommendations (
    pick_id        TEXT PRIMARY KEY,         -- UUID
    category_id    TEXT REFERENCES mvp_categories(category_id),  -- NULL = unassigned
    symbol         TEXT NOT NULL,            -- NSE ticker e.g. 'RELIANCE'
    instrument_key TEXT,                     -- Upstox key e.g. 'NSE_EQ|INE...' (resolved at update time)
    analyst        TEXT,                     -- individual within provider (optional)
    entry_price    TEXT,                     -- Decimal as TEXT; NULL = PENDING
    pick_date      TEXT NOT NULL,            -- ISO datetime UTC (time of add command)
    target_price   TEXT,                     -- Decimal as TEXT; NULL = no declared target
    stop_loss      TEXT,                     -- Decimal as TEXT; NULL = no declared SL
    notes          TEXT,
    status         TEXT NOT NULL DEFAULT 'PENDING',
    closed_at      TEXT,                     -- ISO datetime UTC
    close_price    TEXT,                     -- Decimal as TEXT
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
```

**`mvp_snapshots`**
```sql
CREATE TABLE mvp_snapshots (
    snapshot_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    pick_id       TEXT NOT NULL REFERENCES mvp_recommendations(pick_id),
    ltp           TEXT NOT NULL,             -- Decimal as TEXT
    captured_at   TEXT NOT NULL             -- ISO datetime UTC
);
CREATE INDEX idx_mvp_snapshots_pick ON mvp_snapshots (pick_id, captured_at);
```

---

## CLI Reference (`scripts/mvp.py`)

### Setup (one-time per provider/category)

```bash
mvp provider add dsij "DSIJ" --source tv
mvp provider add prudentequity "Prudent Equity" --source telegram
mvp provider list

mvp category add dsij value-picks "Value Picks"
mvp category add dsij multibagger "MultiBagger"
mvp category add dsij tas "TAS"
mvp category list dsij
```

### Daily capture (minimum: symbol only)

```bash
mvp add RELIANCE
mvp add RELIANCE -p prudentequity
mvp add RELIANCE -p dsij -c value-picks
```

### EOD fill-in (flips PENDING → OPEN)

```bash
mvp update abc123 --price 1200 --target 1400 --sl 1100
mvp update abc123 -p dsij -c value-picks --price 1200 --target 1400 --sl 1100 --notes "breakout above 200 DMA"
```

All fields except `--price` remain optional — updating just `-p`/`-c` without a price
keeps status as PENDING.

### List / close

```bash
mvp list                           # pending (default)
mvp list --open
mvp list -p dsij -c value-picks

mvp close abc123 --price 1380
```

### Summary

```bash
mvp summary                        # all providers, all categories
mvp summary -p dsij                # all DSIJ categories side-by-side
mvp summary -p dsij -c value-picks
mvp summary RELIANCE               # cross-provider view of one stock
```

---

## Cron (`scripts/mvp_watch.py`)

Schedule: `0 9-15 * * 1-5` — top of each hour, 9 AM to 3 PM IST, weekdays only.

**Logic per run:**
1. Fetch all `OPEN` picks from store.
2. Batch-fetch LTP via Upstox Analytics token (V3 Market Quote, same pattern as `src/dhan/`).
3. Record an `mvp_snapshot` row per pick.
4. Detect target/SL breach:
   - `ltp >= target_price` → close as `TARGET_HIT`, fire Telegram alert.
   - `ltp <= stop_loss` → close as `SL_HIT`, fire Telegram alert.
5. Send consolidated hourly summary to Telegram (grouped by provider → category).
6. Write to `logs/mvp_watch.log`.

**Telegram summary format (per run):**
```
📊 MVP Watch — 11:00 AM

DSIJ / Value Picks
  RELIANCE  1200→1245  +3.8%  T:1400 (13% away)  SL:1100
  TCS       3400→3350  -1.5%  T:3800 (13% away)  SL:3100

Prudent Equity
  INFY      1500→1530  +2.0%  T:1700 (11% away)  SL:1400

Unassigned (PENDING)
  HDFC, BAJAJ                  ← price not yet set
```

---

## Module Structure

```
src/mvp/
├── __init__.py
├── models.py       # Provider, Category, Pick, MVPSnapshot (Pydantic/dataclass)
├── store.py        # MVPStore — all SQLite reads/writes
└── tracker.py      # check_prices(), format_telegram_summary() — pure logic, no I/O

scripts/
├── mvp.py          # CLI (provider/category setup, add, update, list, close, summary)
└── mvp_watch.py    # hourly cron

tests/unit/mvp/
├── __init__.py
├── test_mvp_models.py
├── test_mvp_store.py
└── test_mvp_tracker.py
```

---

## Implementation Phases

| Phase | Files | Description |
|---|---|---|
| M1 | `src/mvp/models.py`, `src/mvp/store.py` | Data models + SQLite store + tests |
| M2 | `src/mvp/tracker.py` | Price check logic + Telegram formatter + tests |
| M3 | `scripts/mvp.py` | Full CLI (provider, category, add, update, list, close, summary) |
| M4 | `scripts/mvp_watch.py` | Hourly cron — LTP fetch, snapshot, auto-close, Telegram push |
| M5 | Docs close | CONTEXT.md tree, DECISIONS.md, TODOS.md session log, cron entry |

Each phase = one commit. M1 must land before M2; M2 before M4. M3 can run parallel to M2.

### Phase M1 DoD
- All four tables created via `MVPStore.init_db()`
- `add_provider`, `get_provider`, `add_category`, `get_category` working
- `add_pick` (symbol only, all else null), `update_pick`, `close_pick`
- `record_snapshot`, `get_open_picks`
- Tests: happy path + edge case for every public method
- No network calls in tests

### Phase M2 DoD
- `check_prices(picks, ltp_map) → list[MVPEvent]` — pure fn, no I/O
- `format_telegram_summary(...)` — grouped by provider → category
- `MVPEvent` covers: TARGET_HIT, SL_HIT (price + pick_id payload)
- Rows with null `target_price` or `stop_loss` are not auto-closed (pass-through)
- Tests cover: target hit, SL hit, neither, null target/SL, unassigned category

### Phase M3 DoD
- All subcommands wired: `provider add/list`, `category add/list`, `add`, `update`, `list`, `close`, `summary`
- `mvp add RELIANCE` resolves instrument_key via `InstrumentLookup.search_equity(symbol)`
- `mvp summary RELIANCE` cross-provider query works
- `mvp list` defaults to `--status pending`

### Phase M4 DoD
- Cron fetches LTP via `UPSTOX_ANALYTICS_TOKEN` (same V3 batch endpoint as `src/dhan/`)
- Records snapshots, fires close + per-alert Telegram message on breach
- Sends consolidated hourly summary
- Writes structured log to `logs/mvp_watch.log`
- Graceful: Telegram failure logs warning, does not abort run

---

## Key Design Decisions

- Named **MVP** (Multi-bagger, Value, Pick) — maps to the three dominant recommendation
  categories in Indian retail research.
- `provider` as the top-level entity — covers orgs (DSIJ, CNBC) and individuals uniformly.
- `category_id` nullable at insert time — quick capture doesn't force provider assignment.
- Cron skips `PENDING` rows (null `entry_price`) — no spurious snapshots.
- `instrument_key` resolved at `update` time (when symbol is confirmed), not at `add` time.
- Monetary fields (`entry_price`, `target_price`, `stop_loss`, `ltp`) stored as `TEXT`
  (Decimal invariant, same as rest of codebase).
- Auto-close only when both price AND the relevant threshold (target/SL) are non-null.
- No auto-created `general` category — `category_id` stays NULL until assigned.
