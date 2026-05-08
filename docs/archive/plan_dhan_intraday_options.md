# Dhan Intraday Options Tracking

**Status:** NOT STARTED  
**Owner:** Animesh + Cowork  
**Phase:** 0 (live operational — not gated on backtest phases)  
**Blocks:** —  
**Blocked by:** —  
**Estimated effort:** M (2–3 sessions)  

---

## Problem statement

Animesh has started running intraday option trades on Dhan. These trades are
completely invisible to the existing portfolio snapshot system. The 3:45 PM Telegram
summary shows Nuvama options P&L and Dhan delivery holdings, but Dhan intraday
options P&L, position state, and margin utilization are not captured anywhere.

Two gaps:

1. **No intraday tracking.** There is no periodic snapshot of open positions during
   the day — no record of max profit, max drawdown, or how positions evolved.
2. **No EOD capture.** The daily snapshot at 3:45 PM omits the realized P&L from
   Dhan intraday trades entirely, making the combined daily summary incomplete.

The fix is self-contained within `src/dhan/` and `scripts/`. No cross-module changes.

---

## Acceptance criteria

- [ ] A **single cron** `*/15 9-15 * * 1-5` runs `scripts/intraday_tracker.py`, which
  orchestrates both Nuvama and Dhan intraday tracking in sequence. The individual
  `nuvama_intraday_tracker.py` and `dhan_intraday_tracker.py` scripts remain as
  standalone runnable modules but are no longer separate cron entries.
- [ ] `GET /v2/positions` is called every 15 minutes from 9:15 AM to 3:30 PM on trading
  days. Results filtered to `exchangeSegment == "NSE_FNO"` and `productType == "INTRADAY"`.
- [ ] Each periodic fetch records a row in `dhan_options_snapshots` (`is_eod=0`).
- [ ] Fund limit (`GET /v2/fundlimit`) is fetched alongside every position snapshot
  and persisted to `dhan_margin_snapshots`. Not shown in Telegram — stored only.
- [ ] The 3:45 PM `daily_snapshot.py` run fetches positions one final time and records
  an EOD snapshot (`is_eod=1`).
- [ ] The 3:45 Telegram summary includes a new **"Dhan Options (Intraday)"** section
  showing: realized P&L today, calendar-month realized P&L, and position count.
  Unrealized P&L is **omitted** from the summary when zero (expected case for intraday).
  When non-zero, it is shown with a ⚠️ prefix — it signals a position that was not
  squared off before market close.
- [ ] If the Dhan API is unreachable or the token is expired, the Dhan Options section
  shows `[unavailable]` and the rest of the summary is unaffected.
- [ ] Old intraday rows older than 30 days are purged automatically on each tracker run.
- [ ] All offline tests pass. No network calls in tests.

---

## Definition of Done

- [ ] `src/dhan/positions.py` committed with full parser coverage.
- [ ] `src/dhan/store.py` extended — 2 new tables, 5 new methods (including `get_monthly_realized_pnl`).
- [ ] `scripts/dhan_intraday_tracker.py` committed and smoke-tested manually.
- [ ] `scripts/intraday_tracker.py` committed — single combined orchestrator for Nuvama + Dhan.
- [ ] Old Nuvama-only cron entry replaced with single combined cron entry.
- [ ] `scripts/daily_snapshot.py` extended with Dhan Options section.
- [ ] `tests/unit/dhan/test_positions.py` — all tests green.
- [ ] `tests/unit/dhan/test_dhan_store_options.py` — all tests green.
- [ ] `src/dhan/CLAUDE.md` updated with new endpoints and models.
- [ ] `src/nuvama/store.py` extended with `get_monthly_realized_pnl`.
- [ ] `src/nuvama/models.py` — `monthly_realized_pnl` field added to `NuvamaOptionsSummary`.
- [ ] `src/nuvama/options_reader.py` — `build_options_summary` updated.
- [ ] `tests/unit/nuvama/test_nuvama_store_monthly.py` — all tests green.
- [ ] Existing `build_options_summary` call sites updated with new arg.
- [ ] `CONTEXT.md` module tree updated.
- [ ] `TODOS.md` session log entry appended.

---

## Implementation plan

Four phases. Each phase is one commit.

---

### Phase A — Models

**File:** `src/dhan/models.py`

Add three frozen dataclasses. Do not touch existing `DhanHolding` or `DhanPortfolioSummary`.

```python
@dataclass(frozen=True)
class DhanOptionPosition:
    """A single intraday Dhan option position (NSE_FNO, INTRADAY product type)."""
    security_id: str
    trading_symbol: str      # e.g. "NIFTY2550523500CE"
    exchange_segment: str    # always "NSE_FNO" after filtering
    product_type: str        # always "INTRADAY" after filtering
    position_type: str       # "LONG" | "SHORT"
    buy_qty: int
    sell_qty: int
    net_qty: int             # 0 = fully closed
    buy_avg: Decimal
    sell_avg: Decimal
    realized_pnl: Decimal    # profit locked in from closed legs today
    unrealized_pnl: Decimal  # ~0 at 3:45 for intraday

@dataclass(frozen=True)
class DhanOptionsSummary:
    """Aggregated view of all intraday option positions at a point in time."""
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal          # realized + unrealized
    position_count: int         # total positions (open + closed today)
    snapshot_ts: datetime       # UTC

@dataclass(frozen=True)
class DhanFundLimit:
    """Margin state from GET /v2/fundlimit. Stored silently — not in Telegram."""
    available_balance: Decimal
    utilized_amount: Decimal
    collateral_amount: Decimal
    withdrawable_balance: Decimal
    snapshot_ts: datetime       # UTC
```

**Tests:** `tests/unit/dhan/test_positions.py` (model construction — field types, Decimal
precision, frozen enforcement). No store or API tests in this phase.

**Commit:** `feat(dhan): add DhanOptionPosition, DhanOptionsSummary, DhanFundLimit models`

---

### Phase B — Positions + fund limit API (`src/dhan/positions.py`)

New file. All parsers are pure functions — no I/O except the two HTTP callers.

```
fetch_positions_raw(client_id, access_token) → list[dict]
    GET /v2/positions
    Raises requests.HTTPError on non-2xx.

parse_option_positions(raw: list[dict]) → list[DhanOptionPosition]
    Maps raw API dicts → DhanOptionPosition.
    Does NOT filter — caller decides what to keep.
    Fields to map:
        securityId       → security_id
        tradingSymbol    → trading_symbol
        exchangeSegment  → exchange_segment
        productType      → product_type
        positionType     → position_type
        buyQty           → buy_qty
        sellQty          → sell_qty
        netQty           → net_qty
        buyAvg           → Decimal(str(v))  ← never float()
        sellAvg          → Decimal(str(v))
        realizedProfit   → Decimal(str(v))
        unrealizedProfit → Decimal(str(v))

filter_intraday_options(positions) → list[DhanOptionPosition]
    Keep only: exchangeSegment == "NSE_FNO" AND productType == "INTRADAY"

build_options_summary(positions, ts) → DhanOptionsSummary
    realized_pnl    = sum(p.realized_pnl for p in positions)
    unrealized_pnl  = sum(p.unrealized_pnl for p in positions)
    total_pnl       = realized_pnl + unrealized_pnl
    position_count  = len(positions)

fetch_fund_limit_raw(client_id, access_token) → dict
    GET /v2/fundlimit
    Raises requests.HTTPError on non-2xx.

parse_fund_limit(raw: dict, ts: datetime) → DhanFundLimit
    Fields to map (Dhan API uses camelCase with a typo — "availabelBalance"):
        availabelBalance     → available_balance   ← sic, Dhan's spelling
        utilizedAmount       → utilized_amount
        collateralAmount     → collateral_amount
        withdrawableBalance  → withdrawable_balance
```

**Tests:** `tests/unit/dhan/test_positions.py`

Fixtures: add `tests/fixtures/responses/dhan_positions.json` and
`tests/fixtures/responses/dhan_fund_limit.json` with realistic sample data.

| Test | Covers |
|---|---|
| `test_parse_option_positions_happy` | 2 positions → correct field mapping, Decimal not float |
| `test_parse_option_positions_empty` | empty list → empty list |
| `test_filter_intraday_options` | mix of NSE_FNO/INTRADAY, NSE_EQ/CNC, NSE_FNO/CNC → only INTRADAY FNO kept |
| `test_build_options_summary_aggregates_correctly` | realized + unrealized math, count |
| `test_build_options_summary_empty` | empty list → all zeros, count=0 |
| `test_parse_fund_limit_happy` | raw dict → DhanFundLimit, Decimal precision |
| `test_parse_fund_limit_typo_field` | confirms `availabelBalance` (typo) is handled |

**Commit:** `feat(dhan): add positions.py — parse_option_positions, build_options_summary, parse_fund_limit`

---

### Phase C — Store (`src/dhan/store.py`)

Extend `DhanStore`. Do not touch the existing `dhan_holdings_snapshots` table or
`record_snapshot` / `get_prev_snapshot` methods.

**Schema additions** (appended to the existing `_SCHEMA` string):

```sql
CREATE TABLE IF NOT EXISTS dhan_options_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc          TEXT NOT NULL,
    trade_date      TEXT NOT NULL,
    realized_pnl    TEXT NOT NULL,
    unrealized_pnl  TEXT NOT NULL,
    total_pnl       TEXT NOT NULL,
    position_count  INTEGER NOT NULL,
    positions_json  TEXT NOT NULL,
    is_eod          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_dhan_opts_date
    ON dhan_options_snapshots(trade_date);

CREATE TABLE IF NOT EXISTS dhan_margin_snapshots (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc               TEXT NOT NULL,
    trade_date           TEXT NOT NULL,
    available_balance    TEXT NOT NULL,
    utilized_amount      TEXT NOT NULL,
    collateral_amount    TEXT NOT NULL,
    withdrawable_balance TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dhan_margin_date
    ON dhan_margin_snapshots(trade_date);
```

**New methods on `DhanStore`:**

```python
def record_options_snapshot(
    self,
    ts: datetime,
    summary: DhanOptionsSummary,
    positions: list[DhanOptionPosition],
    is_eod: bool = False,
) -> None:
    """Persist one options snapshot row. positions serialized to JSON blob."""

def get_intraday_extremes(self, trade_date: date) -> dict:
    """Return max_pnl, min_pnl, eod_pnl for a given trade date.

    Returns dict with keys: max_pnl, min_pnl, eod_pnl (all Decimal | None).
    eod_pnl is from the row where is_eod=1, None if not yet recorded.
    """

def record_margin_snapshot(self, ts: datetime, fund_limit: DhanFundLimit) -> None:
    """Persist one margin snapshot row. No upsert — blind append."""

def purge_old_intraday(self, days: int = 30) -> int:
    """Delete dhan_options_snapshots rows older than `days`. Returns deleted count."""

def get_monthly_realized_pnl(self, year: int, month: int) -> Decimal:
    """Sum realized_pnl from all EOD snapshots (is_eod=1) in the given calendar month.

    Query: SELECT SUM(realized_pnl) FROM dhan_options_snapshots
           WHERE is_eod=1 AND trade_date LIKE 'YYYY-MM-%'
    Returns Decimal("0") if no EOD rows exist for the month.
    """
```

Positions JSON format: `json.dumps([dataclasses.asdict(p) for p in positions], default=str)`
— `default=str` handles Decimal serialization.

**Tests:** `tests/unit/dhan/test_dhan_store_options.py` (in-memory SQLite via `:memory:`)

| Test | Covers |
|---|---|
| `test_record_options_snapshot_happy` | inserts row, reads back, Decimal precision intact |
| `test_record_options_snapshot_is_eod_flag` | `is_eod=True` persists correctly |
| `test_get_intraday_extremes_happy` | 3 intraday rows + 1 EOD → correct max/min/eod |
| `test_get_intraday_extremes_no_eod` | 2 intraday, no EOD row → eod_pnl is None |
| `test_get_intraday_extremes_empty` | no rows for date → all None |
| `test_record_margin_snapshot_happy` | inserts row, Decimal precision intact |
| `test_purge_old_intraday_removes_old` | 2 old rows + 1 recent → only old removed, count=2 |
| `test_purge_old_intraday_empty` | nothing to purge → returns 0 |
| `test_get_monthly_realized_pnl_happy` | 3 EOD rows in month → correct sum |
| `test_get_monthly_realized_pnl_excludes_intraday` | intraday rows (is_eod=0) not counted |
| `test_get_monthly_realized_pnl_empty` | no rows → returns Decimal("0") |

**Commit:** `feat(dhan): extend DhanStore with options_snapshots + margin_snapshots tables`

---

### Phase D — Scripts + cron

#### `scripts/dhan_intraday_tracker.py` (new)

Standalone Dhan-only tracker. Can be run directly (`python -m scripts.dhan_intraday_tracker`)
for manual invocation or debugging. Also importable by the combined orchestrator below.

```
is_trading_day() check → return 1 if holiday (caller decides exit)
before 09:15 → return 0 (Dhan position data unreliable in opening auction)
after 15:30 → return 0 (market closed; 3:45 EOD handled by daily_snapshot.py)

fetch_positions_raw(client_id, access_token)
parse_option_positions(raw)
filter_intraday_options(positions)
build_options_summary(positions, ts=datetime.utcnow())

fetch_fund_limit_raw(client_id, access_token)
parse_fund_limit(raw, ts)

store.record_options_snapshot(ts, summary, positions, is_eod=False)
store.record_margin_snapshot(ts, fund_limit)
store.purge_old_intraday(days=30)

log: "Realized: {:+,.0f} | Unrealized: {:+,.0f} | Positions: {:d}"
```

Auth: `DHAN_CLIENT_ID` + `DHAN_ACCESS_TOKEN` from env (same as `reader.py`).

The `__main__` guard calls `main()` and `sys.exit()` — no `os._exit()` needed here
since there is no Nuvama SDK involved.

#### `scripts/intraday_tracker.py` (new — combined orchestrator, single cron entry)

Runs both Nuvama and Dhan trackers in sequence under one process. `os._exit()` is
called at the very end, which is required to terminate the Nuvama SDK's non-daemon
background thread. Dhan runs first (sync, safe), Nuvama second (async + SDK), then
`os._exit()`.

```python
async def main() -> int:
    from scripts.nuvama_intraday_tracker import main as nuvama_main
    from scripts.dhan_intraday_tracker import main as dhan_main

    # Dhan first — sync, no SDK thread pollution
    dhan_exit = dhan_main()

    # Nuvama second — SDK launches background thread after this returns
    nuvama_exit = await nuvama_main()

    return max(dhan_exit, nuvama_exit)

if __name__ == "__main__":
    code = asyncio.run(main())
    os._exit(code)   # required: kills Nuvama SDK background thread
```

Both individual scripts retain their own `__main__` guards for standalone use.

Cron change — **replace** the existing Nuvama-only `*/5` cron with:
```
*/15 9-15 * * 1-5   cd /path/to/NiftyShield && python -m scripts.intraday_tracker >> logs/intraday.log 2>&1
```

Note: frequency changes from 5-min (Nuvama-only) to 15-min (combined). If Nuvama
needs higher frequency independently in future, split the cron entries back out at
that point.

#### `scripts/daily_snapshot.py` (extend)

After the existing Nuvama + Dhan holdings block, add a Dhan options section.
Wrapped in a standalone try/except — non-fatal.

```python
# --- Dhan Options (Intraday) ---
dhan_options_section = "[unavailable]"
try:
    raw = fetch_positions_raw(dhan_client_id, dhan_access_token)
    positions = filter_intraday_options(parse_option_positions(raw))
    summary = build_options_summary(positions, ts=datetime.utcnow())
    dhan_store.record_options_snapshot(ts, summary, positions, is_eod=True)

    raw_fl = fetch_fund_limit_raw(dhan_client_id, dhan_access_token)
    fund_limit = parse_fund_limit(raw_fl, ts)
    dhan_store.record_margin_snapshot(ts, fund_limit)

    month_pnl = dhan_store.get_monthly_realized_pnl(ts.year, ts.month)
    dhan_options_section = format_options_section(summary, month_pnl)
except Exception:
    logger.exception("Dhan Options fetch failed — continuing without it")
```

Telegram section format (HTML, `parse_mode=HTML`):

```
📊 <b>Dhan Options (Intraday)</b>
Today P&amp;L:   <b>{:+,.0f}</b>
Month P&amp;L:   <b>{:+,.0f}</b>
Positions:   {:d}
⚠️ Unrealized: <b>{:+,.0f}</b>  ← only shown when non-zero
```

The unrealized line is appended only when `summary.unrealized_pnl != Decimal("0")`.
Non-zero unrealized at 3:45 means a position was not squared off — treat as a bug or
auto-square-off scenario, not a normal state.

Pure formatter signature:
```python
def format_options_section(summary: DhanOptionsSummary, month_pnl: Decimal) -> str:
    ...
```

Lives in `src/dhan/positions.py`. Tests:

| Test | Covers |
|---|---|
| `test_format_options_section_zero_unrealized` | unrealized line absent when zero |
| `test_format_options_section_nonzero_unrealized` | ⚠️ line present + correct value |
| `test_format_options_section_month_pnl` | month P&L renders correctly |

**Commit:** `feat(dhan): add dhan_intraday_tracker.py, intraday_tracker.py, daily_snapshot Dhan Options section`

---

---

### Phase E — Nuvama monthly realized P&L

Small targeted addition. Mirrors the Dhan month PnL but works differently under the
hood because Nuvama's daily snapshot splits today's live data (from API) from
historical (from the store), so the monthly total must combine both — same pattern
as `cumulative_realized_pnl` already does.

**Files touched:** `src/nuvama/store.py`, `src/nuvama/models.py`,
`src/nuvama/options_reader.py`, `scripts/daily_snapshot.py`.

#### `src/nuvama/store.py` — new method

```python
def get_monthly_realized_pnl(
    self, year: int, month: int, before_date: date | None = None
) -> Decimal:
    """Sum realized_pnl_today from nuvama_options_snapshots for a calendar month.

    Args:
        year: Calendar year (e.g. 2026).
        month: Calendar month (1–12).
        before_date: Exclude rows on or after this date. Pass snap_date (today)
            to match the same boundary used by get_cumulative_realized_pnl —
            today's realized comes from the live API, not the store.

    Returns:
        Decimal sum. Returns Decimal("0") if no rows match.

    Query:
        SELECT SUM(realized_pnl_today)
        FROM nuvama_options_snapshots
        WHERE snapshot_date LIKE 'YYYY-MM-%'
          AND snapshot_date < before_date   ← only when before_date supplied
    """
```

#### `src/nuvama/models.py` — add field to `NuvamaOptionsSummary`

```python
@dataclass(frozen=True)
class NuvamaOptionsSummary:
    ...
    monthly_realized_pnl: Decimal   # ← new field; calendar-month total
    cumulative_realized_pnl: Decimal  # existing — all-time historical
```

Keep `cumulative_realized_pnl` — it has distinct value for long-term tracking.

#### `src/nuvama/options_reader.py` — thread through `build_options_summary`

```python
def build_options_summary(
    positions: list[NuvamaOptionPosition],
    cumulative_realized_pnl_map: dict[str, Decimal],
    monthly_historical_pnl: Decimal,   # ← new arg; from store.get_monthly_realized_pnl
    ...
) -> NuvamaOptionsSummary:
    ...
    monthly_realized_pnl = monthly_historical_pnl + total_realized_today
    # today's realized (from live API) + stored EOD rows earlier this month
```

#### `scripts/daily_snapshot.py` — one extra store call, one extra field

```python
monthly_hist = nuvama_store.get_monthly_realized_pnl(
    snap_date.year, snap_date.month, before_date=snap_date
)
nuvama_options_summary = build_options_summary(
    pos_list,
    cumulative_map,
    monthly_hist,      # ← new
    ...
)
```

Telegram format addition — insert one line after `Today P&L`:

```
Month P&amp;L:  <b>{:+,.0f}</b>   ← new
```

#### Tests — `tests/unit/nuvama/test_nuvama_store_monthly.py` (new file)

| Test | Covers |
|---|---|
| `test_get_monthly_realized_pnl_happy` | 3 rows same month → correct sum |
| `test_get_monthly_realized_pnl_before_date_excludes_today` | row on `before_date` excluded |
| `test_get_monthly_realized_pnl_excludes_other_months` | prior/next month rows not counted |
| `test_get_monthly_realized_pnl_empty` | no rows → `Decimal("0")` |

`build_options_summary` signature change also needs an update to its existing test
in `tests/unit/nuvama/` — add `monthly_historical_pnl=Decimal("0")` to all existing
call sites.

**Commit:** `feat(nuvama): add monthly_realized_pnl to NuvamaOptionsSummary + store method`

---

## Key design decisions

**Single combined cron (`intraday_tracker.py`) rather than two separate entries:**  
Fewer cron entries means fewer failure surfaces to monitor. The combined orchestrator
runs Dhan first (no SDK side-effects), then Nuvama (SDK launches background thread),
then `os._exit()` kills everything cleanly. The individual scripts remain runnable
standalone for debugging. If the two trackers need different frequencies in future,
split back to two cron lines — this is a one-line change.

**Frequency drop from 5-min to 15-min:**  
The existing Nuvama cron is 5-min. Dhan options positions change in discrete trade
events, not tick-by-tick. 15-min is adequate granularity for the intraday P&L curve.
The frequency can be tightened by changing one cron parameter — no code changes needed.

**Unrealized PnL omitted from summary when zero:**  
For strictly intraday trading, unrealized PnL at 3:45 PM is always expected to be zero
(all positions closed). Printing zero is noise. When it is non-zero, it is a signal —
either auto-square-off fired, or a position slipped past close. The ⚠️ prefix makes
this unambiguous in the Telegram summary without requiring the reader to remember the
convention.

**Month PnL via `get_monthly_realized_pnl` querying only `is_eod=1` rows:**  
Intraday rows accumulate realized P&L throughout the day as positions close, but each
15-min snapshot reflects cumulative-to-that-point, not incremental. Summing intraday
rows would double-count. Only the EOD snapshot (`is_eod=1`) holds the final settled
realized P&L for the day. Summing those across the calendar month gives the correct
total without double-counting.

**Why `is_eod` flag instead of a separate table?**  
Keeps all options snapshots queryable in one place. `get_intraday_extremes` can return
EOD P&L in the same query. A separate table would require a JOIN for any trend analysis.

**Why `positions_json` blob instead of normalized rows?**  
Leg-level detail is needed for ad-hoc debugging but not for any aggregation query. A blob
avoids schema churn as Dhan adds/changes position fields. The summary columns (realized,
unrealized, count) are first-class for query efficiency.

**Why Nuvama monthly PnL needs `before_date` but Dhan's doesn't:**  
Dhan's `get_monthly_realized_pnl` queries only `is_eod=1` rows. Today's EOD row is
written *during* the 3:45 run before the query fires, so today is always included
cleanly. Nuvama is different — `nuvama_options_snapshots` stores yesterday's EOD data,
and today's realized PnL comes from the live API (`realized_pnl_today` in `pos_list`),
not the store. Using `before_date=snap_date` keeps the boundary consistent with
`get_cumulative_realized_pnl` and avoids double-counting today. The two are then
summed in `build_options_summary` to produce the correct calendar-month total.

**Why not replace `cumulative_realized_pnl` with `monthly_realized_pnl`?**  
They answer different questions. Monthly is operational — "how is this month going?"
Cumulative is the ledger — useful for tax, strategy review, and multi-month comparisons.
Keep both.

**Why not share models with Nuvama?**  
Nuvama and Dhan have fundamentally different auth paths, position schemas, and SDK
dependencies. Sharing models couples two independently-failable systems. Keep them
parallel — `src/nuvama/` and `src/dhan/` are siblings, not hierarchical.

**Decimal from Dhan API floats:**  
Dhan returns floats in JSON (`realizedProfit: 1250.5`). Always convert via
`Decimal(str(v))` — never `Decimal(v)` directly from a float, which introduces
binary floating-point error.

**`availabelBalance` typo:**  
Dhan's `/v2/fundlimit` response uses `availabelBalance` (missing an 'l'). Known Dhan
API bug. The parser maps it explicitly and the test confirms the exact spelling.

---

## Dhan API reference

| Endpoint | Method | Auth headers |
|---|---|---|
| `/v2/positions` | GET | `access-token`, `client-id` |
| `/v2/fundlimit` | GET | `access-token`, `client-id` |

Base URL: `https://api.dhan.co/v2` (same as existing `reader.py`)

Env vars: `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN` (24h expiry — same as current holdings fetch)

Relevant response fields for `/v2/positions`:

| API field | Type | Maps to |
|---|---|---|
| `securityId` | str | `security_id` |
| `tradingSymbol` | str | `trading_symbol` |
| `exchangeSegment` | str | `exchange_segment` |
| `productType` | str | `product_type` |
| `positionType` | str | `position_type` |
| `buyQty` | int | `buy_qty` |
| `sellQty` | int | `sell_qty` |
| `netQty` | int | `net_qty` |
| `buyAvg` | float | `buy_avg` via `Decimal(str(...))` |
| `sellAvg` | float | `sell_avg` via `Decimal(str(...))` |
| `realizedProfit` | float | `realized_pnl` via `Decimal(str(...))` |
| `unrealizedProfit` | float | `unrealized_pnl` via `Decimal(str(...))` |
