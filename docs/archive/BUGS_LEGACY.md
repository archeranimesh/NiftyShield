# NiftyShield — Known Bugs (legacy, archived)

> **Relocated from repo root to `docs/archive/` on 2026-08-27 (RDO-4).** This is the
> original flat bug registry. The canonical home for defect tracking is
> [`docs/bugs/`](../bugs/). Only `BUG-001` (below) is still open; this file is deleted
> once it lands. A 3-line stub remains at the repo root pointing here.

> Defects that are understood but not yet fixed. Each entry has enough context to
> implement a fix without re-investigation. Reference the entry in commit messages
> when the fix lands, then delete the entry here.
>
> **New bugs go to [docs/bugs/](../bugs/) instead of here** (added 2026-07-02) — that
> folder follows `docs/plan/` story conventions (`prompt.md`/`bugs.md`/`task.md`) with
> severity, root-cause, and fix-checklist structure this flat file doesn't have. ID
> numbering is a single shared sequence across both files — `docs/bugs/` continues from
> `BUG-002`. This file stays until `BUG-001` is fixed and deleted per the rule above.

---

## BUG-001 — No backfill path in `daily_snapshot.py`

**Status:** Open  
**Severity:** Low (data gap; does not break forward operation)  
**Affected script:** `scripts/daily_snapshot.py`

### What happened

On 2026-05-25 the EOD cron crashed with a `ValidationError` on `Leg id=3`
(NIFTY JUN 23000 CE, expiry `2026-06-30`) because the Pydantic validator
rejected the Tuesday expiry date. The crash was in `store.get_all_strategies()`
before any snapshot data was written, so the entire run produced no DB rows.

The validator bug was fixed in commit `4f882c1` (2026-05-27):
`fix(portfolio): skip Thursday-expiry check for NSE Tuesday-expiry contracts (Apr 2026+)`

However, `daily_snapshot.py` has no backfill mode. Historical mode (`--date`)
only reads rows that were already written — it cannot reconstruct a missing day.
As a result, **2026-05-26 (Monday) has no snapshot row** in `daily_snapshots`,
`mf_nav_snapshots`, or any of the Dhan/Nuvama sub-stores.

### Root cause

`_async_main` (live mode) writes snapshot data using real-time LTP from the
Upstox API. `_historical_main` (historical mode) reads what `_async_main`
already wrote. There is no third mode that fetches historical candle data and
inserts it for a past date.

### What a fix looks like

Add a `--backfill YYYY-MM-DD` flag (or repurpose `--date` with a `--force`
flag) that:

1. Accepts a past date and fetches EOD closing prices from the Upstox
   historical candles API (`get_historical_candles`, already wired in
   `src/client/`) for each instrument key present in `legs` on that date.
2. Fetches AMFI NAV for the same date from the flat-file URL
   (`src/mf/nav_fetcher.py` already has the fetch logic).
3. Writes `daily_snapshots`, `mf_nav_snapshots`, and any Dhan/Nuvama rows
   using the same upsert helpers used by `_async_main` — wrapped in a
   transaction so a partial run leaves no partial rows.
4. Prints a `[BACKFILL]` prefix on every line so the output is clearly
   distinguishable from a live run.

The natural entry point is a new `_backfill_main(snap_date, db_path)` coroutine
that mirrors `_async_main` but substitutes historical candle closes for live LTP.
`main()` routes to it when `--backfill` is supplied.

### Workaround

Accept the gap. Queries that look for "previous snapshot" fall back to the last
available row (2026-05-25) naturally. The missing day has no material impact on
forward P&L continuity.

---
