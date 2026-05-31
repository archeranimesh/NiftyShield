# MVP — Story Specs

> One task per session. Find the first unchecked item in `mvp_tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: tick `mvp_tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.

---

## M1.1 — `src/mvp/models.py`: data models + tests

**Files to change:**
- `src/mvp/__init__.py` — new package, single comment line only
- `src/mvp/models.py` — Provider, Category, Pick, MVPSnapshot models
- `tests/unit/mvp/__init__.py` — new test package
- `tests/unit/mvp/test_mvp_models.py` — model tests

**Before any code:**
`search_graph("PaperTrade")` — confirm Pydantic frozen pattern used in this codebase;
`search_graph("PortfolioDelta")` — confirm frozen dataclass pattern;
`search_graph("MVPStore")` — confirm it does NOT yet exist (zero results expected).

**What to implement:**

Four models, all in `src/mvp/models.py`:

```python
class ProviderSource(str, Enum):
    TV = "TV"
    TELEGRAM = "TELEGRAM"
    YOUTUBE = "YOUTUBE"
    OTHER = "OTHER"

class PickStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    TARGET_HIT = "TARGET_HIT"
    SL_HIT = "SL_HIT"
    MANUAL_CLOSE = "MANUAL_CLOSE"

class Provider(frozen Pydantic):
    provider_id: str          # UUID
    slug: str
    display_name: str
    source_type: ProviderSource
    notes: str | None = None
    created_at: str           # ISO datetime UTC

class Category(frozen Pydantic):
    category_id: str          # UUID
    provider_id: str
    slug: str
    display_name: str
    notes: str | None = None
    created_at: str

class Pick(frozen Pydantic):
    pick_id: str              # UUID
    category_id: str | None = None
    symbol: str               # NSE ticker
    instrument_key: str | None = None
    analyst: str | None = None
    entry_price: Decimal | None = None     # None = PENDING
    pick_date: str            # ISO datetime UTC
    target_price: Decimal | None = None
    stop_loss: Decimal | None = None
    notes: str | None = None
    status: PickStatus = PickStatus.PENDING
    closed_at: str | None = None
    close_price: Decimal | None = None
    created_at: str
    updated_at: str

class MVPSnapshot(frozen Pydantic):
    snapshot_id: int | None = None   # autoincrement; None before DB insert
    pick_id: str
    ltp: Decimal
    captured_at: str          # ISO datetime UTC
```

Monetary fields (`entry_price`, `target_price`, `stop_loss`, `ltp`, `close_price`) use
`Decimal`. DB layer (store.py) serialises them as TEXT — models hold `Decimal` objects.

All models `frozen=True`. Google-style docstrings on each class.

**Tests (`tests/unit/mvp/test_mvp_models.py`):**
- `Pick` with all fields populated → `status` is `PickStatus.PENDING` by default.
- `Pick` with `entry_price=None` → `status` defaults to `PENDING` (not OPEN).
- `ProviderSource` enum members match expected string values (`"TV"`, `"TELEGRAM"`, etc.).
- `Pick` with `entry_price=Decimal("1200")` and `target_price=None` → round-trips without error.
- `MVPSnapshot` with `snapshot_id=None` → valid (pre-insert state).

**Commit:** `feat(mvp): add MVP data models — Provider, Category, Pick, MVPSnapshot`

---

## M1.2 — `src/mvp/store.py`: init_db + provider/category methods + tests

**Files to change:**
- `src/mvp/store.py` — MVPStore with init_db, provider/category methods
- `tests/unit/mvp/test_mvp_store.py` — store tests (in-memory SQLite)

**Before any code:**
`get_code_snippet("MVPStore")` — confirm it does NOT yet exist;
`get_code_snippet("db_connection")` — confirm shared SQLite context manager signature
  (`src/db.py`);
`get_code_snippet("Provider")` — get exact field list from M1.1 models;
`get_code_snippet("Category")` — same.

**What to implement:**

`MVPStore.__init__(self, db_path: str)` — stores path only, no connection held open.
Uses `db_connection(db_path)` context manager from `src/db.py` for every operation.

`init_db(self) → None` — creates all four tables if not exists (exact DDL from
`docs/plan/mvp/mvp_schema.md`). Safe to call repeatedly.

`add_provider(self, provider: Provider) → None` — INSERT OR IGNORE on `mvp_providers`.
`get_provider(self, slug: str) → Provider | None` — by slug.
`list_providers(self) → list[Provider]` — all rows, ordered by `display_name`.

`add_category(self, category: Category) → None` — INSERT OR IGNORE on `mvp_categories`.
`get_category(self, provider_id: str, slug: str) → Category | None` — by composite key.
`list_categories(self, provider_id: str) → list[Category]` — for one provider.

Monetary fields: stored as `str(value)` (TEXT in SQLite), read back as
`Decimal(row["col"])`. Never use float.

**Tests (`tests/unit/mvp/test_mvp_store.py`):**
All tests use `tmp_path` fixture with `MVPStore(str(tmp_path / "test.sqlite"))` and
call `init_db()` before any operation.

- `init_db()` called twice → no error (idempotent).
- `add_provider` → `get_provider` round-trip returns identical slug and display_name.
- `get_provider` on missing slug → `None`.
- `add_category` → `get_category` round-trip.
- `add_category` duplicate (same provider_id + slug) → no error (INSERT OR IGNORE).
- `list_categories` returns only categories for requested provider_id.

**Commit:** `feat(mvp): add MVPStore init_db + provider/category persistence`

---

## M1.3 — `src/mvp/store.py`: pick CRUD + snapshot methods + tests

**Files to change:**
- `src/mvp/store.py` — add pick and snapshot methods (extend existing class)
- `tests/unit/mvp/test_mvp_store.py` — extend with pick/snapshot tests

**Before any code:**
`get_code_snippet("MVPStore")` — get current method list (post M1.2);
`get_code_snippet("Pick")` — exact field list;
`get_code_snippet("MVPSnapshot")` — exact field list.

**What to implement (all on `MVPStore`):**

`add_pick(self, pick: Pick) → None` — INSERT into `mvp_recommendations`.
`get_pick(self, pick_id: str) → Pick | None`.
`update_pick(self, pick_id: str, **kwargs) → None` — UPDATE only provided fields +
  always updates `updated_at` to current UTC ISO. Allowed kwargs:
  `category_id`, `symbol`, `instrument_key`, `analyst`, `entry_price`, `target_price`,
  `stop_loss`, `notes`, `status`. If `entry_price` is set and current status is PENDING,
  auto-advance status to OPEN.
`close_pick(self, pick_id: str, close_price: Decimal, status: PickStatus) → None` —
  sets `closed_at`, `close_price`, `status`. `status` must be a terminal value
  (TARGET_HIT / SL_HIT / MANUAL_CLOSE); raises `ValueError` otherwise.
`get_open_picks(self) → list[Pick]` — WHERE status = 'OPEN'.
`list_picks(self, status: PickStatus | None = None, provider_id: str | None = None,
  category_id: str | None = None) → list[Pick]` — filtered list for CLI.

`record_snapshot(self, snapshot: MVPSnapshot) → None` — INSERT into `mvp_snapshots`.
`get_snapshots(self, pick_id: str, limit: int = 10) → list[MVPSnapshot]` — ordered
  by `captured_at DESC`.

**Tests (add to `tests/unit/mvp/test_mvp_store.py`):**
- `add_pick` → `get_pick` round-trip; all Decimal fields survive TEXT serialisation.
- `update_pick` with `entry_price` on a PENDING pick → status auto-advances to OPEN.
- `update_pick` without `entry_price` → status stays PENDING.
- `close_pick` with `MANUAL_CLOSE` → `closed_at` and `close_price` set.
- `close_pick` with `status=OPEN` → raises `ValueError`.
- `get_open_picks` excludes PENDING and terminal rows.
- `record_snapshot` → `get_snapshots` round-trip; `ltp` Decimal survives round-trip.

**Commit:** `feat(mvp): add MVPStore pick CRUD and snapshot persistence`

---

## M2.1 — `src/mvp/tracker.py`: MVPEvent + check_prices + tests

**Files to change:**
- `src/mvp/tracker.py` — MVPEvent dataclass + check_prices pure function
- `tests/unit/mvp/test_mvp_tracker.py` — new test file

**Before any code:**
`get_code_snippet("Pick")` — exact field list, confirm `target_price`, `stop_loss` types;
`get_code_snippet("PickStatus")` — confirm terminal status names;
`search_graph("check_prices")` — confirm does NOT yet exist.

**What to implement:**

```python
@dataclass(frozen=True)
class MVPEvent:
    pick_id: str
    symbol: str
    event_type: PickStatus          # TARGET_HIT or SL_HIT only
    trigger_price: Decimal          # ltp that caused the breach
    entry_price: Decimal | None

def check_prices(
    picks: list[Pick],
    ltp_map: dict[str, Decimal],    # instrument_key → ltp
) -> list[MVPEvent]:
```

Rules:
- Only processes picks with `status == OPEN` and `instrument_key` in `ltp_map`.
- `ltp >= target_price` → `TARGET_HIT` event (only when `target_price` is not None).
- `ltp <= stop_loss` → `SL_HIT` event (only when `stop_loss` is not None).
- Picks with null `target_price` AND null `stop_loss` → not auto-closed, pass-through.
- Returns list of events; empty if no breaches.
- Pure function: no I/O, no DB, no logging.

**Tests (`tests/unit/mvp/test_mvp_tracker.py`):**
- Target hit: `ltp >= target_price` → one `TARGET_HIT` event returned.
- SL hit: `ltp <= stop_loss` → one `SL_HIT` event.
- Neither: no events.
- Null `target_price` + non-null `stop_loss`: only SL evaluated.
- Null `stop_loss` + non-null `target_price`: only target evaluated.
- Both null: zero events regardless of ltp.
- PENDING pick (not OPEN): excluded even if ltp breaches target.
- `instrument_key` not in `ltp_map`: pick skipped silently.

**Commit:** `feat(mvp): add MVPEvent + check_prices pure logic`

---

## M2.2 — `src/mvp/tracker.py`: format_telegram_summary + tests

**Files to change:**
- `src/mvp/tracker.py` — extend with format_telegram_summary
- `tests/unit/mvp/test_mvp_tracker.py` — extend with summary tests

**Before any code:**
`get_code_snippet("format_telegram_summary")` — confirm not yet implemented;
`search_code("format_telegram")` in `src/notifications/` — check existing Telegram
  formatting patterns in this codebase for HTML parse_mode conventions.

**What to implement:**

```python
def format_telegram_summary(
    picks: list[Pick],
    ltp_map: dict[str, Decimal],        # instrument_key → ltp
    providers: dict[str, str],          # provider_id → display_name
    categories: dict[str, str],         # category_id → display_name
    run_time: str,                       # e.g. "11:00 AM"
) -> str:
```

Output format (HTML for Telegram `parse_mode=HTML`):
```
📊 <b>MVP Watch — 11:00 AM</b>

<b>DSIJ / Value Picks</b>
  RELIANCE  1200→1245  +3.8%  T:1400 (13% away)  SL:1100
  TCS       3400→3350  -1.5%  T:3800 (13% away)  SL:3100

<b>Prudent Equity</b>
  INFY      1500→1530  +2.0%  T:1700 (11% away)  SL:1400

<b>Unassigned (PENDING)</b>
  HDFC, BAJAJ
```

Rules:
- OPEN picks: group by provider → category (unassigned picks under `Unassigned (PENDING)`).
- P&L % = `(ltp - entry_price) / entry_price * 100`; prefix `+` when positive.
- "X% away" for target: `(target_price - ltp) / ltp * 100` (absolute value); omit if no
  target. Same for SL.
- PENDING picks (no `entry_price`): listed by symbol only in the Unassigned block.
- Picks whose `instrument_key` is not in `ltp_map`: show last known price or `—` for ltp.
- Returns empty string if no picks at all.
- Pure function: no I/O.

**Tests (add to `tests/unit/mvp/test_mvp_tracker.py`):**
- Two OPEN picks in same provider/category → both appear in same group block.
- PENDING pick → appears in Unassigned block.
- Positive P&L → `+` prefix present.
- Negative P&L → `-` prefix present.
- Null target_price → "T:" line omitted.
- Empty picks list → empty string returned.

**Commit:** `feat(mvp): add format_telegram_summary for hourly watch output`

---

## M3.1 — `scripts/mvp.py`: provider + category subcommands

**Files to change:**
- `scripts/mvp.py` — new script, provider/category subcommands only

**Before any code:**
`get_code_snippet("MVPStore")` — current public API;
`get_code_snippet("Provider")` — field list;
`get_code_snippet("Category")` — field list;
`search_code("argparse")` in `scripts/record_paper_trade.py` — existing argparse pattern.

**What to implement:**

Entry point: `python -m scripts.mvp <subcommand>`.

Subcommands in this task only — do NOT implement `add`, `update`, `list`, `close`,
`summary` yet:

```
mvp provider add <slug> <display_name> --source <tv|telegram|youtube|other>
mvp provider list

mvp category add <provider_slug> <slug> <display_name>
mvp category list <provider_slug>
```

- `provider add`: creates `Provider`, calls `MVPStore.add_provider`. Prints
  `✓ Provider '<slug>' added.` on success.
- `provider list`: prints table: `SLUG | DISPLAY_NAME | SOURCE`. Empty → `No providers.`
- `category add`: resolves provider by slug via `get_provider`; exits 1 if not found.
  Creates `Category`, calls `add_category`. Prints `✓ Category '<slug>' added.`
- `category list`: resolves provider; prints table: `SLUG | DISPLAY_NAME`. Empty → `No categories.`

DB path: `data/portfolio/portfolio.sqlite` (constant in script). `MVPStore.init_db()`
called at script startup always.

No tests required for CLI scripts (no unit-testable logic beyond what store tests cover).

**Commit:** `feat(scripts): mvp.py provider and category subcommands`

---

## M3.2 — `scripts/mvp.py`: add + update + close subcommands

**Files to change:**
- `scripts/mvp.py` — extend with add/update/close subcommands

**Before any code:**
`get_code_snippet("MVPStore")` — confirm `add_pick`, `update_pick`, `close_pick` APIs;
`get_code_snippet("InstrumentLookup")` — confirm `search_equity` signature and return shape;
`get_code_snippet("Pick")` — exact field list;
`search_code("DEFAULT_BOD_PATH")` in `scripts/instrument_lookup.py` — get the BOD path constant.

**What to implement:**

```
mvp add <SYMBOL> [-p <provider_slug>] [-c <category_slug>] [--defer-key]
mvp update <pick_id> [--price <n>] [--target <n>] [--sl <n>] [-p <slug>] [-c <slug>] [--notes <text>]
mvp close <pick_id> --price <n>
```

**`mvp add` instrument resolution flow:**
1. Load `InstrumentLookup.from_file(DEFAULT_BOD_PATH)` — if file missing, warn and skip
   resolution (`instrument_key = None`).
2. Call `search_equity(symbol)`.
3. Single result with score 1.0 (exact match) → auto-resolve, print
   `  → instrument_key: NSE_EQ|...`.
4. Multiple results or top score < 1.0 → print numbered table
   (`#  SYMBOL  NAME  KEY`) and prompt `Select [1-N / s=skip / q=quit]:`.
   `s` → `instrument_key = None`; `q` → abort without insert.
5. `--defer-key` → skip resolution entirely.

**`mvp add`** creates a `Pick` (UUID for `pick_id`, current UTC for `pick_date` /
`created_at` / `updated_at`) and calls `add_pick`. Resolves `category_id` from provider
slug + category slug if both provided; exits 1 if either not found.
Prints `✓ Pick added: <pick_id[:8]> — SYMBOL (PENDING)`.

**`mvp update`** calls `update_pick` with only provided kwargs. Prints `✓ Updated.`
Flipping PENDING → OPEN (by setting `--price`) is handled inside `update_pick` already.

**`mvp close`** calls `close_pick(pick_id, close_price, PickStatus.MANUAL_CLOSE)`.
Prints `✓ Closed at <price>.`

No tests required for CLI scripts.

**Commit:** `feat(scripts): mvp.py add, update, close subcommands with instrument resolution`

---

## M3.3 — `scripts/mvp.py`: list + summary subcommands

**Files to change:**
- `scripts/mvp.py` — extend with list/summary subcommands

**Before any code:**
`get_code_snippet("MVPStore.list_picks")` — confirm signature and filter params;
`get_code_snippet("Pick")` — field list for display columns.

**What to implement:**

```
mvp list [--open] [--all] [-p <provider_slug>] [-c <category_slug>]
mvp summary [-p <provider_slug>] [-c <category_slug>]
mvp summary <SYMBOL>
```

**`mvp list`** defaults to `--status PENDING`.
`--open` → status=OPEN. `--all` → no status filter.
Output columns: `ID[:8] | SYMBOL | STATUS | ENTRY | TARGET | SL | PROVIDER/CATEGORY | DATE`.
Empty → `No picks.`

**`mvp summary`** with no SYMBOL: groups picks by provider → category.
Per group prints: count OPEN, count TARGET_HIT, count SL_HIT, win rate (TARGET_HIT /
(TARGET_HIT + SL_HIT)), total closed picks. No live LTP fetch — summary is DB-only.

**`mvp summary <SYMBOL>`**: cross-provider view. Lists every pick for that symbol across
all providers/categories, one row per pick: `PROVIDER | CATEGORY | ENTRY | STATUS | CLOSE_PRICE | DATE`.

No tests required for CLI scripts.

**Commit:** `feat(scripts): mvp.py list and summary subcommands`

---

## M4.1 — `scripts/mvp_watch.py`: LTP fetch + snapshot + auto-close

**Files to change:**
- `scripts/mvp_watch.py` — new hourly cron script

**Before any code:**
`get_code_snippet("MVPStore.get_open_picks")` — confirm return type;
`get_code_snippet("MVPStore.record_snapshot")` — confirm signature;
`get_code_snippet("MVPStore.close_pick")` — confirm signature;
`search_code("UPSTOX_ANALYTICS_TOKEN")` in `src/dhan/ltp_fetcher.py` or similar — find
  the existing V3 batch LTP fetch pattern (same endpoint used by `src/dhan/`);
`search_code("batch_ltp")` — find the helper if it exists.

**What to implement:**

Cron schedule comment: `# 0 9-15 * * 1-5`

```python
async def run() -> None:
    picks = store.get_open_picks()
    if not picks:
        return
    # batch-fetch LTP for all instrument_keys (skip picks with None key)
    ltp_map = await fetch_ltp_batch(instrument_keys, token)
    for pick in picks:
        ltp = ltp_map.get(pick.instrument_key)
        if ltp is None:
            continue
        store.record_snapshot(MVPSnapshot(pick_id=..., ltp=ltp, captured_at=utc_now()))
    events = check_prices(picks, ltp_map)
    for event in events:
        store.close_pick(event.pick_id, event.trigger_price, event.event_type)
        # per-alert Telegram message (M4.2)
```

LTP fetch: use the same `UPSTOX_ANALYTICS_TOKEN` batch endpoint already used by
`src/dhan/ltp_fetcher.py`. Reuse that function directly — do not reimplement.

Graceful: any Telegram failure (M4.2 not yet wired) logs warning, does not abort.
Writes structured log to `logs/mvp_watch.log` via Python `logging` (JSON format, same
as other cron scripts).

No unit tests for this script — integration-only.

**Commit:** `feat(scripts): mvp_watch.py LTP fetch, snapshot recording, auto-close`

---

## M4.2 — `scripts/mvp_watch.py`: Telegram alerts + consolidated summary

**Files to change:**
- `scripts/mvp_watch.py` — extend with Telegram notifications

**Before any code:**
`get_code_snippet("TelegramNotifier")` — confirm `send_message` signature and HTML parse_mode;
`get_code_snippet("build_notifier")` — confirm factory function signature;
`get_code_snippet("format_telegram_summary")` — confirm signature from M2.2;
`search_code("build_notifier")` in an existing cron script — see usage pattern.

**What to implement:**

Extend `run()` in `mvp_watch.py`:

1. After auto-close loop: for each `MVPEvent`, send a per-alert Telegram message:
   ```
   🎯 TARGET HIT — RELIANCE
   Entry: 1200 | Exit: 1401 | +16.75%
   DSIJ / Value Picks
   ```
   or:
   ```
   🛑 SL HIT — TCS
   Entry: 3400 | Exit: 3098 | -8.88%
   DSIJ / Value Picks
   ```

2. After per-alert messages: build and send consolidated hourly summary via
   `format_telegram_summary(...)`. Requires loading providers and categories from store
   to pass the lookup dicts.

3. `build_notifier()` returns `None` when env vars missing — check for `None` before
   any `send_message` call.

No unit tests for this script.

**Commit:** `feat(scripts): mvp_watch Telegram per-alert + consolidated hourly summary`

---

## M6 — Historical backfill + retrospective SL/target detection (Good-to-Have)

> **Not part of core story. Implement only after M5 is complete.**
> Useful when adding picks that were issued in the past (e.g. a tip from 1 Jan 2026
> recorded today). Without this, `mvp_snapshots` will only have data from the day of
> recording forward.

**What it adds:**

1. **`MVPStore.backfill_snapshots(pick_id, daily_closes: list[tuple[date, Decimal]]) → None`**
   — bulk-inserts historical daily close prices into `mvp_snapshots` for dates between
   `pick_date` and today. Skips dates already present (INSERT OR IGNORE keyed on
   `pick_id + captured_at date`). Monetary values follow TEXT/Decimal invariant.

2. **`src/mvp/backfill.py` — `fetch_historical_closes(symbol, from_date, to_date) → list[tuple[date, Decimal]]`**
   — fetches daily EOD close prices from NSE Bhavcopy Parquet (already ingested at
   `data/historical/bhavcopy/`). Falls back to a warning + empty list if data not available.
   No live API calls — Bhavcopy only.

3. **`scripts/mvp.py backfill <pick_id>`** subcommand:
   - Loads pick; derives `from_date = pick_date.date()`, `to_date = date.today()`.
   - Calls `fetch_historical_closes` → `backfill_snapshots`.
   - Then calls `check_prices` over the historical series in chronological order; stops at
     the **first breach** (SL or target) and calls `close_pick` at that date/price.
   - Prints: `Backfilled N days. SL hit on 2026-02-14 at ₹1,050.` or
     `Backfilled N days. No SL/target breach detected.`

**Tests (`tests/unit/mvp/test_mvp_backfill.py`):**
- `backfill_snapshots` with 5 dates → 5 rows in `mvp_snapshots`.
- Duplicate call → no duplicate rows (INSERT OR IGNORE).
- Historical series with SL breach on day 3 → `close_pick` called at day 3 price.
- Historical series with no breach → pick stays OPEN.

**Commit:** `feat(mvp): historical backfill + retrospective SL/target detection`

---

## M5 — Docs close

**Files to change:**
- `CONTEXT.md` — add `src/mvp/` to module tree; add `scripts/mvp.py` and
  `scripts/mvp_watch.py` to scripts list
- `DECISIONS.md` — one entry: "MVP module added; instrument_key resolved at add-time
  via InstrumentLookup; monetary fields TEXT/Decimal invariant maintained"
- `TODOS.md` — session log entry

No code changes. No tests. Targeted `Edit` calls only — never `Write` on these files.

**Commit:** `docs(mvp): update CONTEXT.md, DECISIONS.md, TODOS.md for MVP module`
