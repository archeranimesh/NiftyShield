# MVP — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: tick `tasks.md`, append `| SHA:
> <sha>`, add one line to `TODOS.md`. ⚠️ **Read the "Design decisions" block at the top of `tasks.md` first** — resolved 2026-09-18. Fixed ₹1L notional, 6% tranche ladder, −30% deployed-drawdown hard
> stop. **M-A** (this pass) ships a single lump-sum fill (`qty = capital / price` at recommendation price); **M-B** (later) adds the staggered 4-tranche ladder on top of the same schema.

---

## ⚠️ Canonical worked example — Uniparts (read before M0/M7/M8)

> Fixed acceptance case, agreed 2026-09-23. Do not re-derive this flow — implement M0/M7/M8 against it, then run it end-to-end as the first real exercise of the pipeline before any other stock or
> provider is entered. Only once this passes do we fill in other picks.

**Input data:**
- Provider: `dsij` / "DSIJ", source `other`
- Category: `value_picks` / "Value Picks" (under `dsij`)
- Symbol: `UNIPARTS` (NSE, ISIN `INE244O01017`)
- `reco_date`: 2026-06-11 — DSIJ publishes post-market-hours, so this is a signal date, not an entry date
- `reco_price`: 640.10 (DSIJ's quoted recommendation price)
- `entry_price`: determined by the entry rule below, not assumed equal to `reco_price`
- `target_price`: 828
- `stop_loss`: none given by DSIJ for this pick — `stop_loss=None` is a valid, expected state (not every provider/pick gives one), not a blocker. `check_prices` already handles this (`if
  pick.stop_loss is not None`) — a `None` SL simply means the pick can only exit via `target_price` or the M8/M6 time-stop, never an SL breach. M8 must not invent or require a value.

**Entry rule (resolved 2026-09-23):** because the reco lands post-market, the earliest we could act is the next trading day. Two variants, both needed:
- **Live-forward** (a reco entered in real time, from today onward): poll intraday LTP via `BrokerClient.get_ltp` on the next trading day after the reco (same pattern as `scripts/mvp_watch.py`'s live
  polling) — enter at the first observed price above `reco_price`. If price never goes above `reco_price` that day, do not enter.
- **Backfill** (a reco already in the past, like this Uniparts case): we do not have historical intraday data, and M0's bhavcopy ingest is daily-close only — it cannot answer "first tick above
  640.10." **Fallback for backfill only:** use the next trading day's **close** price. If that close > `reco_price`, enter at that close price on that date. If not, the pick is never entered (no later
  re-check). This is a documented approximation, distinct from the live-forward rule — do not conflate the two in M8's implementation; the backfill path and the live-forward path are separate code
  branches with separate tests.

**End-to-end flow this pick must exercise:**
1. Enter the pick's basic info (provider/category/symbol/reco_price/target/sl/reco_date) — via the M8 backfill entry path, not the "now"-stamping `mvp add`/`update` CLI (`pick_date` must be
   `reco_date`, not today). `entry_price` is NOT supplied up front — M8 determines and fills it per the backfill entry rule above (next trading day's close, if > reco_price).
2. If the next-trading-day close was not above `reco_price`, the pick stays `PENDING`/unentered and the flow stops here — no snapshots, no target/SL tracking. (Not expected for Uniparts given ₹659.70
   was observed on June 12 per the earlier price check, but M8 must implement this branch correctly regardless.)
3. Once entered, run the M8 backfill: walk daily equity closes (from M0's ingested table) from the entry date to today, recording one `MVPSnapshot` per trading day.
4. On the first day a close crosses `target_price` (828) or `stop_loss`, auto-exit the pick that day — `status` flips to `TARGET_HIT`/`SL_HIT`, `close_price` = that day's close, `closed_at` = that
   date. No snapshots recorded past the exit day.
5. If neither breached through today, leave the pick `OPEN`; `scripts/mvp_watch.py`'s live hourly cron takes over from today forward with no extra wiring.
6. Verify via `mvp summary UNIPARTS` (per-pick), `mvp summary -p dsij -c value_picks` (Value Picks rollup), `mvp summary -p dsij` (all DSIJ), and `mvp list --all` (whole-portfolio view) — this
   exercises the individual → category → provider → all-picks rollup the user asked for.

**Sign-off gate:** once M0 + M7 (`reco_price` field) + M8 (backfill) are all implemented and this Uniparts flow runs clean end-to-end with correct data at every level above, tell the user the MVP
pipeline is ready. They will then run Uniparts themselves as the worked example, inspect every data point, and only after they're satisfied will other stocks/providers be entered.

**M0 data-source decision — RESOLVED 2026-09-23: NSE CM bhavcopy.** `scratch/2026-09-23_mvp_m0_data_source_probe.py` compared NSE CM bhavcopy vs. Yahoo Finance chart API for UNIPARTS daily closes, run
twice. NSE CM bhavcopy (`https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip`, UDiFF format, same session/auth pattern already used in
`src/backtest/bhavcopy_ingest.py` for F&O) returned ₹659.70 for 2026-06-12 (matching the figure independently found via web search) and ₹851.70 for 2026-09-22, both dates correct on both runs; `None`
for 2026-07-11 was correctly a non-trading Saturday, not a failure. Yahoo Finance's `query1.finance.yahoo.com` chart endpoint hit a 429 rate limit on both attempts — ruled out as unreliable.
**Confirmed by user 2026-09-23: NSE CM bhavcopy is M0's data source**, mirroring the existing F&O ingest module's structure.

**M0 NIFTY 50 index-level data-source decision — RESOLVED 2026-09-23: NSE index-close bhavcopy.** `scratch/2026-09-23_mvp_m0_nifty_index_probe.py` probed
`https://nsearchives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv` (plain CSV, not zipped, same host/session pattern as the CM equity bhavcopy) for the `Nifty 50` row's `Closing Index
Value`, run twice. Both runs returned identical values: ₹23,622.90 for 2026-06-12 and ₹23,329.00 for 2026-09-22; `None` for 2026-07-11 was correctly a non-trading Saturday, matching the equity probe's
behavior on the same date. Endpoint reachable, response shape stable across runs. **Not independently cross-checked against a second source** (unlike the equity close, which matched an external web
search) — the run-to-run consistency and correct non-trading-day handling are the only verification here; worth a quick sanity check against a known NIFTY close before relying on this for real alpha
numbers. Open point 1 below is fully closed.

---

## Open points — carry to next session (raised 2026-09-23)

Not yet decided; do not silently resolve these — surface and confirm before proceeding.

1. ~~M0 data source~~ — **RESOLVED 2026-09-23: NSE CM bhavcopy (equity) + NSE index-close bhavcopy (NIFTY 50)** (see decisions above). Both legs closed.
2. ~~P&L math (Issue A) is still fully unscoped.~~ — **RESOLVED 2026-09-23: drafted as M9** (`tasks.md`), scoped to the M-A lump-sum fill only — does not depend on M0/M8 landing first, since it's pure
   fill math against `entry_price`/`close_price`, independent of the backfill path.
3. ~~Implementation not yet greenlit.~~ — **RESOLVED 2026-09-23: M8 drafted as a checklist item** (`tasks.md`), blocked on M0. M0 already had a checklist entry (pre-existing, this point's premise was
   stale on that half). No `src/` code written yet for either — this point only gated *drafting*, not *implementing*.
4. **Live-forward branch of the entry rule is unverified against real infra.** The live-forward half of the entry rule (poll `BrokerClient.get_ltp` on the next trading day, enter at first tick above
   `reco_price`) assumes the same live-polling pattern `scripts/mvp_watch.py` already uses will work unchanged for this new use case. Not a known correctness risk, just not yet exercised — worth a
   quick check once M8's live-forward branch is implemented, before relying on it for a real future reco.
5. ~~NIFTY 50 index-level historical source — not probed, and scope depends on a decision not yet made.~~ — **RESOLVED 2026-09-23: day-by-day**, not entry-vs-exit-only. The index-bhavcopy probe this
   point was waiting on is done (point 1 above). Wired into **M8** (`tasks.md`): `MVPSnapshot.benchmark_close`, populated per trading day during the backfill walk from M0's NIFTY 50 table. Live-watch
   snapshots (M4.1, already shipped) stay `NULL` for now — extending day-by-day alpha to live picks is a separate follow-on, not part of M8.

---

## M1.1 — `src/mvp/models.py`: data models + tests

**Files to change:**
- `src/mvp/__init__.py` — new package, single comment line only
- `src/mvp/models.py` — Provider, Category, Pick, MVPTranche, MVPSnapshot models
- `tests/unit/mvp/__init__.py` — new test package
- `tests/unit/mvp/test_mvp_models.py` — model tests

**Before any code:** `search_graph("PaperTrade")` — confirm Pydantic frozen pattern used in this codebase; `search_graph("PortfolioDelta")` — confirm frozen dataclass pattern;
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
    stop_loss: Decimal | None = None       # tipster value, recorded only — not acted on
    notes: str | None = None
    status: PickStatus = PickStatus.PENDING
    closed_at: str | None = None
    close_price: Decimal | None = None
    capital_allotted: Decimal = Decimal("100000")
    tranche_step_pct: Decimal = Decimal("6")
    max_drawdown_pct: Decimal = Decimal("30")   # hard-stop trigger, fully-deployed capital
    deployed_capital: Decimal = Decimal("0")
    total_qty: int = 0
    avg_cost: Decimal | None = None        # blended entry; None pre-fill
    idle_cash: Decimal = Decimal("0")      # floor-rounding residue; not rolled to next tranche
    realized_pnl: Decimal = Decimal("0")   # set on close
    benchmark_entry: Decimal | None = None  # NIFTY 50 level captured live at pick add-time
    created_at: str
    updated_at: str
    # Dividends are out of scope for MVP — not tracked.

class MVPTranche(frozen Pydantic):
    tranche_id: str            # UUID
    pick_id: str
    tranche_index: int         # 0..3; M-A (lump-sum) uses a single index-0 row
    trigger_pct: Decimal       # 0 / -6 / -12 / -18 from pick price
    fill_price: Decimal | None = None      # None until filled
    qty: int | None = None                 # floored share qty; None until filled
    cost_bps: Decimal = Decimal("25")      # round-trip cost knob, applied on this fill
    filled_at: str | None = None           # ISO datetime UTC; None until filled

class MVPSnapshot(frozen Pydantic):
    snapshot_id: int | None = None   # autoincrement; None before DB insert
    pick_id: str
    ltp: Decimal
    captured_at: str          # ISO datetime UTC
```

Monetary fields (`entry_price`, `target_price`, `stop_loss`, `ltp`, `close_price`, `capital_allotted`, `deployed_capital`, `avg_cost`, `idle_cash`, `realized_pnl`, `benchmark_entry`, `fill_price`) use
`Decimal`. DB layer (store.py) serialises them as TEXT — models hold `Decimal` objects. Percent fields (`tranche_step_pct`, `max_drawdown_pct`, `trigger_pct`, `cost_bps`) are also `Decimal`, same TEXT
convention.

All models `frozen=True`. Google-style docstrings on each class.

**M-A scope note:** this task defines the full `Pick`/`MVPTranche` shape (including the 4-tranche fields) so the schema doesn't need a second migration for M-B, but M-A callers (M2/M3/M4 in this pass)
only ever create a single `MVPTranche(tranche_index=0, trigger_pct=0)` per pick — the ladder logic (indices 1–3, −6/−12/−18% triggers) is M-B's job, appended to `tasks.md` once M-A ships.

**Tests (`tests/unit/mvp/test_mvp_models.py`):**
- `Pick` with all fields populated → `status` is `PickStatus.PENDING` by default.
- `Pick` with `entry_price=None` → `status` defaults to `PENDING` (not OPEN).
- `Pick` defaults: `capital_allotted=Decimal("100000")`, `tranche_step_pct=Decimal("6")`, `max_drawdown_pct=Decimal("30")` when not explicitly set.
- `ProviderSource` enum members match expected string values (`"TV"`, `"TELEGRAM"`, etc.).
- `Pick` with `entry_price=Decimal("1200")` and `target_price=None` → round-trips without error.
- `MVPTranche` with `tranche_index=0`, `fill_price=None`, `qty=None` → valid (pre-fill state).
- `MVPSnapshot` with `snapshot_id=None` → valid (pre-insert state).

**Commit:** `feat(mvp): add MVP data models — Provider, Category, Pick, MVPTranche, MVPSnapshot`

---

## M1.2 — `src/mvp/store.py`: init_db + provider/category methods + tests

**Files to change:**
- `src/mvp/store.py` — MVPStore with init_db, provider/category methods
- `tests/unit/mvp/test_mvp_store.py` — store tests (in-memory SQLite)

**Before any code:** `get_code_snippet("MVPStore")` — confirm it does NOT yet exist; `get_code_snippet("db_connection")` — confirm shared SQLite context manager signature (`src/db.py`);
`get_code_snippet("Provider")` — get exact field list from M1.1 models; `get_code_snippet("Category")` — same.

**What to implement:**

`MVPStore.__init__(self, db_path: str)` — stores path only, no connection held open. Uses `db_connection(db_path)` context manager from `src/db.py` for every operation.

`init_db(self) → None` — creates all four tables if not exists (exact DDL from `docs/plan/mvp/schema.md`). Safe to call repeatedly.

`add_provider(self, provider: Provider) → None` — INSERT OR IGNORE on `mvp_providers`. `get_provider(self, slug: str) → Provider | None` — by slug. `list_providers(self) → list[Provider]` — all rows,
ordered by `display_name`.

`add_category(self, category: Category) → None` — INSERT OR IGNORE on `mvp_categories`. `get_category(self, provider_id: str, slug: str) → Category | None` — by composite key. `list_categories(self,
provider_id: str) → list[Category]` — for one provider.

Monetary fields: stored as `str(value)` (TEXT in SQLite), read back as `Decimal(row["col"])`. Never use float.

**Tests (`tests/unit/mvp/test_mvp_store.py`):** All tests use `tmp_path` fixture with `MVPStore(str(tmp_path / "test.sqlite"))` and call `init_db()` before any operation.

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

**Before any code:** `get_code_snippet("MVPStore")` — get current method list (post M1.2); `get_code_snippet("Pick")` — exact field list; `get_code_snippet("MVPSnapshot")` — exact field list.

**What to implement (all on `MVPStore`):**

`add_pick(self, pick: Pick) → None` — INSERT into `mvp_recommendations`. `get_pick(self, pick_id: str) → Pick | None`. `update_pick(self, pick_id: str, **kwargs) → None` — UPDATE only provided
fields + always updates `updated_at` to current UTC ISO. Allowed kwargs: `category_id`, `symbol`, `instrument_key`, `analyst`, `entry_price`, `target_price`, `stop_loss`, `notes`, `status`. If
`entry_price` is set and current status is PENDING, auto-advance status to OPEN. `close_pick(self, pick_id: str, close_price: Decimal, status: PickStatus) → None` — sets `closed_at`, `close_price`,
`status`. `status` must be a terminal value (TARGET_HIT / SL_HIT / MANUAL_CLOSE); raises `ValueError` otherwise. `get_open_picks(self) → list[Pick]` — WHERE status = 'OPEN'. `list_picks(self, status:
PickStatus | None = None, provider_id: str | None = None, category_id: str | None = None) → list[Pick]` — filtered list for CLI.

`record_snapshot(self, snapshot: MVPSnapshot) → None` — INSERT into `mvp_snapshots`. `get_snapshots(self, pick_id: str, limit: int = 10) → list[MVPSnapshot]` — ordered by `captured_at DESC`.

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

**Before any code:** `get_code_snippet("Pick")` — exact field list, confirm `target_price`, `stop_loss` types; `get_code_snippet("PickStatus")` — confirm terminal status names;
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

**Before any code:** `get_code_snippet("format_telegram_summary")` — confirm not yet implemented; `search_code("format_telegram")` in `src/notifications/` — check existing Telegram formatting patterns
in this codebase for HTML parse_mode conventions.

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
- "X% away" for target: `(target_price - ltp) / ltp * 100` (absolute value); omit if no target. Same for SL.
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

**Before any code:** `get_code_snippet("MVPStore")` — current public API; `get_code_snippet("Provider")` — field list; `get_code_snippet("Category")` — field list; `search_code("argparse")` in
`scripts/record_paper_trade.py` — existing argparse pattern.

**What to implement:**

Entry point: `python -m scripts.mvp <subcommand>`.

Subcommands in this task only — do NOT implement `add`, `update`, `list`, `close`, `summary` yet:

```
mvp provider add <slug> <display_name> --source <tv|telegram|youtube|other>
mvp provider list

mvp category add <provider_slug> <slug> <display_name>
mvp category list <provider_slug>
```

- `provider add`: creates `Provider`, calls `MVPStore.add_provider`. Prints `✓ Provider '<slug>' added.` on success.
- `provider list`: prints table: `SLUG | DISPLAY_NAME | SOURCE`. Empty → `No providers.`
- `category add`: resolves provider by slug via `get_provider`; exits 1 if not found. Creates `Category`, calls `add_category`. Prints `✓ Category '<slug>' added.`
- `category list`: resolves provider; prints table: `SLUG | DISPLAY_NAME`. Empty → `No categories.`

DB path: `data/portfolio/portfolio.sqlite` (constant in script). `MVPStore.init_db()` called at script startup always.

No tests required for CLI scripts (no unit-testable logic beyond what store tests cover).

**Commit:** `feat(scripts): mvp.py provider and category subcommands`

---

## M3.2 — `scripts/mvp.py`: add + update + close subcommands

**Files to change:**
- `scripts/mvp.py` — extend with add/update/close subcommands

**Before any code:** `get_code_snippet("MVPStore")` — confirm `add_pick`, `update_pick`, `close_pick` APIs; `get_code_snippet("InstrumentLookup")` — confirm `search_equity` signature and return shape;
`get_code_snippet("Pick")` — exact field list; `search_code("DEFAULT_BOD_PATH")` in `scripts/instrument_lookup.py` — get the BOD path constant.

**What to implement:**

```
mvp add <SYMBOL> [-p <provider_slug>] [-c <category_slug>] [--defer-key]
mvp update <pick_id> [--price <n>] [--target <n>] [--sl <n>] [-p <slug>] [-c <slug>] [--notes <text>]
mvp close <pick_id> --price <n>
```

**`mvp add` instrument resolution flow:**
1. Load `InstrumentLookup.from_file(DEFAULT_BOD_PATH)` — if file missing, warn and skip resolution (`instrument_key = None`).
2. Call `search_equity(symbol)`.
3. Single result with score 1.0 (exact match) → auto-resolve, print ` → instrument_key: NSE_EQ|...`.
4. Multiple results or top score < 1.0 → print numbered table (`# SYMBOL NAME KEY`) and prompt `Select [1-N / s=skip / q=quit]:`. `s` → `instrument_key = None`; `q` → abort without insert.
5. `--defer-key` → skip resolution entirely.

**`mvp add`** creates a `Pick` (UUID for `pick_id`, current UTC for `pick_date` / `created_at` / `updated_at`) and calls `add_pick`. Resolves `category_id` from provider slug + category slug if both
provided; exits 1 if either not found. Prints `✓ Pick added: <pick_id[:8]> — SYMBOL (PENDING)`.

**`mvp update`** calls `update_pick` with only provided kwargs. Prints `✓ Updated.` Flipping PENDING → OPEN (by setting `--price`) is handled inside `update_pick` already.

**`mvp close`** calls `close_pick(pick_id, close_price, PickStatus.MANUAL_CLOSE)`. Prints `✓ Closed at <price>.`

No tests required for CLI scripts.

**Commit:** `feat(scripts): mvp.py add, update, close subcommands with instrument resolution`

---

## M3.3 — `scripts/mvp.py`: list + summary subcommands

**Files to change:**
- `scripts/mvp.py` — extend with list/summary subcommands

**Before any code:** `get_code_snippet("MVPStore.list_picks")` — confirm signature and filter params; `get_code_snippet("Pick")` — field list for display columns.

**What to implement:**

```
mvp list [--open] [--all] [-p <provider_slug>] [-c <category_slug>]
mvp summary [-p <provider_slug>] [-c <category_slug>]
mvp summary <SYMBOL>
```

**`mvp list`** defaults to `--status PENDING`. `--open` → status=OPEN. `--all` → no status filter. Output columns: `ID[:8] | SYMBOL | STATUS | ENTRY | TARGET | SL | PROVIDER/CATEGORY | DATE`. Empty →
`No picks.`

**`mvp summary`** with no SYMBOL: groups picks by provider → category. Per group prints: count OPEN, count TARGET_HIT, count SL_HIT, win rate (TARGET_HIT / (TARGET_HIT + SL_HIT)), total closed picks.
No live LTP fetch — summary is DB-only.

**`mvp summary <SYMBOL>`**: cross-provider view. Lists every pick for that symbol across all providers/categories, one row per pick: `PROVIDER | CATEGORY | ENTRY | STATUS | CLOSE_PRICE | DATE`.

No tests required for CLI scripts.

**Commit:** `feat(scripts): mvp.py list and summary subcommands`

---

## M4.1 — `scripts/mvp_watch.py`: LTP fetch + snapshot + auto-close

**Files to change:**
- `scripts/mvp_watch.py` — new hourly cron script

**Before any code:** `get_code_snippet("MVPStore.get_open_picks")` — confirm return type; `get_code_snippet("MVPStore.record_snapshot")` — confirm signature; `get_code_snippet("MVPStore.close_pick")`
— confirm signature; `search_code("UPSTOX_ANALYTICS_TOKEN")` in `src/dhan/ltp_fetcher.py` or similar — find the existing V3 batch LTP fetch pattern (same endpoint used by `src/dhan/`);
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

LTP fetch: use the same `UPSTOX_ANALYTICS_TOKEN` batch endpoint already used by `src/dhan/ltp_fetcher.py`. Reuse that function directly — do not reimplement.

Graceful: any Telegram failure (M4.2 not yet wired) logs warning, does not abort. Writes structured log to `logs/mvp_watch.log` via Python `logging` (JSON format, same as other cron scripts).

No unit tests for this script — integration-only.

**Commit:** `feat(scripts): mvp_watch.py LTP fetch, snapshot recording, auto-close`

---

## M4.2 — `scripts/mvp_watch.py`: Telegram alerts + consolidated summary

**Files to change:**
- `scripts/mvp_watch.py` — extend with Telegram notifications

**Before any code:** `get_code_snippet("TelegramNotifier")` — confirm `send_message` signature and HTML parse_mode; `get_code_snippet("build_notifier")` — confirm factory function signature;
`get_code_snippet("format_telegram_summary")` — confirm signature from M2.2; `search_code("build_notifier")` in an existing cron script — see usage pattern.

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

2. After per-alert messages: build and send consolidated hourly summary via `format_telegram_summary(...)`. Requires loading providers and categories from store to pass the lookup dicts.

3. `build_notifier()` returns `None` when env vars missing — check for `None` before any `send_message` call.

No unit tests for this script.

**Commit:** `feat(scripts): mvp_watch Telegram per-alert + consolidated hourly summary`

---

## M6 — Historical backfill + retrospective SL/target detection (Good-to-Have)

> **Not part of core story. Implement only after M5 is complete.** Useful when adding picks that were issued in the past (e.g. a tip from 1 Jan 2026 recorded today). Without this, `mvp_snapshots` will
> only have data from the day of recording forward.

**What it adds:**

1. **`MVPStore.backfill_snapshots(pick_id, daily_closes: list[tuple[date, Decimal]]) → None`** — bulk-inserts historical daily close prices into `mvp_snapshots` for dates between `pick_date` and
   today. Skips dates already present (INSERT OR IGNORE keyed on `pick_id + captured_at date`). Monetary values follow TEXT/Decimal invariant.

2. **`src/mvp/backfill.py` — `fetch_historical_closes(symbol, from_date, to_date) → list[tuple[date, Decimal]]`** — fetches daily EOD close prices from NSE Bhavcopy Parquet (already ingested at
   `data/historical/bhavcopy/`). Falls back to a warning + empty list if data not available. No live API calls — Bhavcopy only.

3. **`scripts/mvp.py backfill <pick_id>`** subcommand:
   - Loads pick; derives `from_date = pick_date.date()`, `to_date = date.today()`.
   - Calls `fetch_historical_closes` → `backfill_snapshots`.
   - Then calls `check_prices` over the historical series in chronological order; stops at the **first breach** (SL or target) and calls `close_pick` at that date/price.
   - Prints: `Backfilled N days. SL hit on 2026-02-14 at ₹1,050.` or `Backfilled N days. No SL/target breach detected.`

**Tests (`tests/unit/mvp/test_mvp_backfill.py`):**
- `backfill_snapshots` with 5 dates → 5 rows in `mvp_snapshots`.
- Duplicate call → no duplicate rows (INSERT OR IGNORE).
- Historical series with SL breach on day 3 → `close_pick` called at day 3 price.
- Historical series with no breach → pick stays OPEN.

**Commit:** `feat(mvp): historical backfill + retrospective SL/target detection`

---

## M5 — Docs close

**Files to change:**
- `CONTEXT.md` — add `src/mvp/` to module tree; add `scripts/mvp.py` and `scripts/mvp_watch.py` to scripts list
- `DECISIONS.md` — one entry: "MVP module added; instrument_key resolved at add-time via InstrumentLookup; monetary fields TEXT/Decimal invariant maintained"
- `TODOS.md` — session log entry

No code changes. No tests. Targeted `Edit` calls only — never `Write` on these files.

**Commit:** `docs(mvp): update CONTEXT.md, DECISIONS.md, TODOS.md for MVP module`
