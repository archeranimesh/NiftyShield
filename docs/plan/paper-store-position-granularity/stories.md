# PaperStore Position Granularity — Story Specs

---

## PG-1 — Fix `get_positions()` grouping

**Problem:**
`PaperStore.get_positions(strategy_name)` aggregates `net_qty` across all instrument keys for a
given `(strategy_name, leg_role)` pair. During a roll, a SELL on the expiring instrument reduces
the net_qty attributed to the replacement instrument, producing incorrect position state.

Observed failure (2026-06-29): closing `overlay_pp` `NSE_FO|58627` (expired May put, 65 qty)
with a SELL also consumed the 65 qty of `NSE_FO|63848` (live Jun put), zeroing the leg entirely.

**Root cause:**
`get_positions()` groups by `(strategy_name, leg_role)` only. The SQL (or Python aggregation)
sums all BUY quantities and subtracts all SELL quantities across every instrument traded under
that leg role, regardless of which instrument key was bought or sold.

**Fix:**
Group by `(strategy_name, leg_role, instrument_key)`. Return one `PaperPosition` per unique
`(strategy_name, leg_role, instrument_key)` triple. Filter to rows where `net_qty != 0`.

**`PaperPosition` model impact:**
`PaperPosition` already carries `instrument_key` — no field addition needed. Verify the
`avg_cost` and `avg_sell_price` aggregations are also scoped per instrument key (they should
average only the BUY/SELL prices for that specific instrument).

**Consistency note:**
`delete_trade()` already scopes its WHERE to `instrument_key`. `get_positions()` must match
that granularity — they should be consistent about what constitutes "a position."

**Callers (do not fix in PG-1 — defer to PG-2):**
After this change, callers that iterate positions and match by `leg_role` alone will still work
correctly as long as they don't assume there is exactly one position per leg role. Callers that
do assume uniqueness will need updating in PG-2. Do not fix callers in this task.

**Tests required:**
- Happy path: two BUY trades for same leg_role, different instrument_keys → two separate
  `PaperPosition` rows returned.
- Roll scenario: BUY 65 instrument A, SELL 65 instrument A, BUY 65 instrument B →
  instrument A flat (excluded), instrument B open at 65.
- Net-zero exclusion: BUY 65 + SELL 65 same instrument → not returned.
- Existing tests must remain green.

**Files touched:** `src/paper/store.py`, `tests/unit/paper/test_paper_store.py`

---

## PG-2 — Audit and fix callers

**Prerequisite:** PG-1 merged and green.

**What changed:** `get_positions()` now returns potentially multiple positions per leg role.
Any caller assuming `.leg_role` is unique within the result set must be updated.

**Audit targets (search, do not assume):**
```
search_code("get_positions")
```

Known likely callers:
- `src/paper/tracker.py` — `compute_pnl` iterates positions; may build a dict keyed by `leg_role`
- `src/strategy/monitor.py` — tick loop fetches positions per strategy
- `src/strategy/executor.py` — `PaperExecutor` matches actions to positions by `leg_role`
- `scripts/strategies/three_track/paper_3track_snapshot.py` — EOD snapshot display
- `scripts/portfolio/paper_snapshot.py` — portfolio-level snapshot
- `scripts/record/record_paper_trade.py` — delta gate aggregation

**For each caller:**
1. Determine if it assumes one position per leg role.
2. If yes: update to handle multiple positions per leg role (e.g., sum net_qty across instruments
   for display, or match to the open instrument for signal evaluation).
3. Add or update tests to cover the multi-position case.

**Delta tracker special case:**
`PortfolioDeltaTracker.aggregate_delta(positions, ...)` receives the full position list.
If it iterates positions by leg_role uniqueness, fix it to iterate all positions regardless.
Verify the delta sum is still correct when two rows share a leg_role.

**Files touched:** determined by audit — do not pre-list.

---

## PG-3 — Docs close

**No code.** Targeted `Edit` calls only — never `Write` on existing files.

1. `TODOS.md` — mark PG-1, PG-2, PG-3 complete with session log entry.
2. `DECISIONS.md` — add entry: "`get_positions()` groups by `(strategy, leg_role, instrument_key)`;
   one `PaperPosition` per instrument, not per leg role. Rationale: rolls require per-instrument
   accounting; `delete_trade()` already uses this granularity."
3. `CONTEXT.md` — update `PaperStore` description to reflect new grouping behaviour.
