# MVP Tracker — Corporate-Action (Stock Split) Adjustment

## System Context

`src/mvp/` (MVP — Multi-bagger Value Picks Tracker, shipped, archived
`docs/archive/plan/mvp/`) tracks tipster-provided equity picks through
`Pick` (`src/mvp/models.py:53-108`): absolute `Decimal` price levels
(`entry_price`, `reco_price`, `target_price`, `stop_loss`, `close_price`,
`avg_cost`) plus tranche-fill state (`total_qty`, `deployed_capital`,
`avg_cost`, `idle_cash`) built up as the position scales in over multiple
tranches (`tranche_step_pct`, `max_drawdown_pct`). `tracker.check_prices`
(`src/mvp/tracker.py:22-64`) does a raw numeric comparison of live LTP
against the stored `target_price` / `stop_loss` for every `OPEN` pick, every
hourly tick (`scripts/mvp_watch.py`, live in the crontab), to emit
`TARGET_HIT` / `SL_HIT` events pushed to Telegram.

**Bug (`BUG-054`, `docs/bugs/bugs.md`, filed 2026-09-25, open):** there is no
split/bonus/corporate-action adjustment anywhere in `src/mvp/`. Confirmed by
grep — zero hits across `src/mvp/*.py` and `scripts/mvp*.py` for
split/corporate action/adjust (only an unrelated `re.split()` call). The
`Pick` docstring calls out dividends as explicitly out-of-scope but never
mentions splits — this was never scoped, not deferred by decision.
`docs/archive/plan/mvp/{tasks,stories,schema}.md`, `DECISIONS.md`, and the
bug registry have no prior mention of splits/bonuses for MVP.

**Confirmed today in the live DB** (this session, provider `gtf` /
category `diwali-picks`, all four picks entered 2025-10-21, ~11 months of
live history now backfilled): two of four picks show what looks like
uncorrected post-split pricing —

| Symbol | Avg cost | Current LTP | Naive return% |
|---|---|---|---|
| BAJAJHIND | 22.5763 | 20.78 | -7.96% |
| UCOBANK | 32.8519 | 23.90 | **-27.25%** |
| BANKINDIA | 135.8688 | 137.94 | +1.52% |
| MRPL | 150.0943 | 164.60 | +9.66% |

UCOBANK's -27% in 11 months on a PSU bank pick is the shape of a split, not
organic price action — this is exactly the `BECTORFOOD` `e30d0a11` failure
mode already logged in `BUG-054` (1:5 split, record date 2025-12-12, entry
pre-dated the split), playing out again on a second/third pick independent
of that bug report.

## Mechanics of the failure (from `BUG-054`, re-verified against current
`src/mvp/` source via the graph)

- PENDING→OPEN is not price-driven: `MVPStore.update_pick` flips status to
  `OPEN` only as a side effect of someone setting `entry_price`
  (`scripts/mvp.py update` or the backfill walk in `src/mvp/backfill.py`).
  A `PENDING` pick sitting through a split isn't mechanically broken yet.
- Once `OPEN`, `tracker.check_prices` only evaluates `OPEN` picks
  (`src/mvp/tracker.py:38`) against raw stored levels: `ltp >=
  pick.target_price` → `TARGET_HIT` (line 44); `ltp <= pick.stop_loss` →
  `SL_HIT` (line 54).
- A pre-split `target_price` becomes numerically unreachable post-split
  (never fires); a pre-split `stop_loss` sits *above* the post-split price
  range and fires `SL_HIT` falsely the moment a split happens, closing a
  position that was never actually stopped out.
- Beyond `target_price`/`stop_loss`, the **tranche-fill fields are also
  split-blind**: `total_qty` / `avg_cost` / `deployed_capital` were computed
  at pre-split share counts and prices. A 1:5 split multiplies the "correct"
  post-split share count by 5 and divides the "correct" post-split avg cost
  by 5 — neither is adjusted anywhere, so `P&L = (LTP - avg_cost) *
  total_qty` is wrong in both factors simultaneously, not just off on one
  side. This tranche dimension is not mentioned in `BUG-054`'s original
  write-up and needs to be in scope for the fix design.
- `src/mvp/backfill.py::run_backfill` walks daily closes from
  `data/offline/equity_ohlcv/` (raw NSE bhavcopy, itself **not**
  split-adjusted — bhavcopy reports the actual traded price each day, which
  legitimately gaps down on the split date) to detect `TARGET_HIT`/`SL_HIT`
  day-by-day and to populate `mvp_snapshots`. Any fix must work through this
  historical walk, not just the live hourly tick.

## Relevant existing machinery

- `Pick` (`src/mvp/models.py:53-108`) — `frozen=True` Pydantic model, all
  price/qty fields as above.
- `MVPStore` (`src/mvp/store.py`) — `add_pick`, `update_pick` (tranche
  fill + PENDING→OPEN), `get_pick`, `list_picks`, `backfill_snapshots`,
  `get_category_stats`, `get_category_high_low`. SQLite-backed,
  `mvp_recommendations` / `mvp_snapshots` / `mvp_categories` /
  `mvp_providers` tables (`DB_REGISTRY.md`).
- `tracker.check_prices` / `run_backfill` (`src/mvp/backfill.py:140-232`) —
  the two call sites that compare LTP against stored absolute levels, live
  and historical respectively.
- `scripts/mvp_watch.py` — hourly cron entrypoint calling `check_prices`
  against live LTP.
- No corporate-actions data source is currently wired into the project
  anywhere (`src/instruments/`, `src/dhan/`, `src/nuvama/` were grepped via
  the graph — none carry split/bonus event data today).

**Already decided / out of scope for the council:**

| Parameter | Decision |
|---|---|
| Dividends | Explicitly out of scope for `Pick` (existing docstring, `src/mvp/models.py:57`) — not reopened here. |
| Existing `PENDING`→`OPEN` transition mechanics | Not being redesigned; only how it interacts with a split event mid-`PENDING` is in scope. |

## The decision to resolve

### Option A — Manual ratio-adjustment command, rebase stored levels in place

When a split is noticed (manually, no automated feed), an operator runs a
new `scripts/mvp.py adjust-split <pick_id> --ratio 1:5` (or similar) that
divides `entry_price` / `reco_price` / `target_price` / `stop_loss` /
`avg_cost` by the ratio and multiplies `total_qty` by the ratio, in place,
for that one pick — a point-in-time correction. `Pick` stays a flat
absolute-`Decimal` model, no schema change. Historical `mvp_snapshots` rows
before the split date are left as originally recorded (pre-split absolute
prices, now inconsistent with the post-split `avg_cost`/`target_price` they
sit next to) unless also rewritten by the same command.

### Option B — Corporate-actions table, adjust at read time

Add `mvp_corporate_actions` (symbol, ex-date, ratio, action_type) populated
either manually or from an ingested feed (NSE corporate-action bhavcopy/
announcement data — availability unconfirmed, would need its own research).
`tracker.check_prices` and `run_backfill` join against it and adjust the
live LTP (or the comparison levels) at evaluation time; stored `Pick` levels
remain exactly as recorded at entry, untouched. Tranche `avg_cost`/
`total_qty` would need either a similar read-time adjustment or a
materialized rebase triggered off the same table when the ex-date passes.

## Q1 — Which approach, and why, given the tranche-fill dimension?

Given the split affects not just `target_price`/`stop_loss` but
`total_qty`/`avg_cost`/`deployed_capital` (tranche-fill state, not just
entry/target levels), is Option A (manual, in-place rebase covering *all*
affected fields including tranches) or Option B (corporate-actions table,
read-time adjustment) the right shape? Does the tranche dimension change the
calculus versus `BUG-054`'s original entry/target/SL-only framing?

## Q2 — If B, what's the realistic data source for the corporate-actions table?

Is there a reliable, low-effort way to source split/bonus events for NSE
equities (a feed, a scrape, a manual weekly check) that would make B
practical rather than "a table nobody populates"? If no good automated
source exists, does that tip the answer toward A regardless of A's
correctness tradeoffs?

## Q3 — Historical data integrity: rewrite `mvp_snapshots`, or interpret at read time?

For a pick like UCOBANK that already has ~11 months of `mvp_snapshots`
straddling an undetected split, should the fix (A or B) rewrite the
pre-split snapshot rows to a post-split-equivalent basis, leave them as
recorded and adjust only the comparison logic going forward, or flag the
pick for manual review rather than auto-correcting history? What is the
risk of silently rewriting snapshot history versus leaving a known-dirty
series in place with a documented caveat?

## Q4 — Detection: manual-only, or a cheap automated flag?

Given no corporate-actions feed currently exists in the project, is a
purely manual "operator notices, runs the adjustment command" detection
model (as `BUG-054`'s workaround already assumes) acceptable long-term, or
is there a cheap heuristic worth adding now — e.g. flag any `OPEN` pick
whose day-over-day LTP move exceeds some threshold (10%? 20%?) for manual
review, without claiming to auto-detect the ratio? Where should that check
live — `scripts/mvp_watch.py`'s hourly tick, or a separate daily job?

## Q5 — Retrofit scope: which existing picks need correction now?

Beyond UCOBANK (strong signal) and the already-known `BECTORFOOD`
`e30d0a11`, is a one-time audit pass across all `OPEN`/`PENDING` picks
(comparing entry-to-now price ratio against a sanity threshold) the right
immediate action to surface other undetected splits, before or independent
of shipping the general fix?

---

## Required Council Output Format

```
## Summary Table

| Decision | Recommendation |
|----------|---------------|
| A (manual rebase) vs B (corporate-actions table, read-time adjust) | |
| Tranche fields (total_qty/avg_cost/deployed_capital) in scope for the same fix | |
| Corporate-actions data source (if B) | |
| Historical mvp_snapshots — rewrite, leave + adjust logic, or flag for review | |
| Detection model — manual-only vs cheap automated flag, and where it runs | |
| Immediate retrofit — one-time audit pass now? | |

## Design Rationale
[Why the recommended option is correct given the tranche-fill dimension,
the absence of a corporate-actions feed today, and BUG-054's existing
BECTORFOOD precedent.]

## Data Model / Schema Detail
[If B: exact `mvp_corporate_actions` schema. If A: exact command shape and
every field it must touch, including tranches. Either way: how
`tracker.check_prices` and `run_backfill` change.]

## Historical Data Handling
[Concrete recommendation for existing dirty snapshot history — rewrite
strategy or documented-caveat strategy — and for the UCOBANK/BECTORFOOD
retrofit specifically.]

## Dissenting Notes
[Panel disagreements, particularly on A vs B and on whether to auto-flag
suspicious moves.]
```
