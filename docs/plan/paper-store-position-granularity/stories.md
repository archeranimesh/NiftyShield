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

## PG-2 — Audit findings (2026-07-25)

Audit of every `get_positions`/`get_position` call site post-PG-1. Verified clean (no
uniqueness assumption, no change needed): `PaperTracker._get_open_positions`/`compute_pnl`,
`StrategyMonitor._tick`, `IronCondorV1.check_signals`, `ReEntryMixin._check_reentry`,
`ic_entry_gates.check_duplicate`, `auto_close.evaluate_pp_reentry_eod`, `build_stats`/
`build_comparison_report` in `paper_ic_monthly_comparison.py`, `process_variant`/`_run` in
`paper_ic_snapshot.py`.

Real bugs found, split into independent sub-stories below rather than one combined task —
each is independently testable and low-risk to land separately.

---

## PG-2a — `PaperStore.get_position()` ambiguity fix

**Problem:** `get_position(strategy_name, leg_role)` builds
`{p.leg_role: p for p in self.get_positions(strategy_name)}` — a dict comprehension keyed by
`leg_role` only. Post-PG-1, `get_positions()` can return multiple rows sharing a `leg_role`
during a roll overlap (old contract not yet fully closed, new contract already open). The dict
comprehension silently collapses these to whichever row Python's dict construction visits last
— not a meaningful choice, just iteration-order luck.

**Fix:** New signature `get_position(strategy_name, leg_role, instrument_key=None)`.
- If `instrument_key` given: filter `get_positions()` results to that exact
  `(leg_role, instrument_key)` pair; return the flat-position default if no match.
- If `instrument_key` is `None` and exactly one position matches `leg_role`: return it (current
  behavior, unchanged).
- If `instrument_key` is `None` and more than one position matches `leg_role`: pick the one with
  the most recent `entry_date`, and log a WARNING (`paper_store.get_position_ambiguous`) with
  `strategy_name`, `leg_role`, and the count of matches — so a caller relying on the fallback
  path is visible in structured logs rather than silently guessing.

**Why most-recent-`entry_date` and not raise:** `ApprovedAction.legs_to_close` (the primary
caller path, via `PaperExecutor.apply()`) only carries `leg_role` strings today — it cannot
supply `instrument_key`. Raising here would crash `apply()` on every roll-overlap tick with no
way for existing callers to recover. Deferred to **PG-4** (see TODOS.md) — threading
`instrument_key` through `ApprovedAction`/`LegSpec` is the real fix for `apply()`; this task
only removes the *silent* part of the ambiguity for callers not yet updated.

**Tests required (`tests/unit/paper/test_paper_store.py`):**
- No `instrument_key` given, single match → unchanged behavior (existing tests must stay green).
- `instrument_key` given, matches one of two same-leg_role positions → returns that one.
- `instrument_key` given, no match → returns the flat-position default (net_qty=0).
- No `instrument_key`, two same-leg_role positions with different `entry_date` → returns the
  more recent one, and a WARNING is logged (assert via `caplog`/structlog capture).

**Files touched:** `src/paper/store.py`, `tests/unit/paper/test_paper_store.py`.

---

## PG-2b — `paper_3track_snapshot.py` LTP collection fix

**Problem:** `_run()` builds `positions = [store.get_position(track_name, r) for r in leg_roles]`
to collect instrument keys for the leg-snapshot LTP fetch. During a roll overlap this silently
drops the LTP fetch for whichever instrument `get_position()`'s ambiguity resolution didn't pick
— that leg's snapshot row gets no `ltp` even though it's genuinely open.

**Fix:** Replace the per-leg-role loop with a single `store.get_positions(track_name)` call —
no ambiguity possible, every open instrument is included.

**Tests required:** update/add a case in `tests/unit/paper/test_paper_3track_snapshot.py`
covering two open positions sharing a `leg_role` (roll overlap) → both instrument keys appear
in the LTP fetch call.

**Files touched:** `scripts/strategies/three_track/paper_3track_snapshot.py`,
`tests/unit/paper/test_paper_3track_snapshot.py`. Independent of PG-2a.

---

## PG-2c — `paper_snapshot.py` notes dict fix

**Problem:** `most_recent_trade_per_leg = {}` in `_run()` is keyed by `leg_role` only, so when
two instruments share a leg role (roll overlap) only one instrument's note survives into the
printed/telegram notes line.

**Fix:** Key by `(leg_role, instrument_key)` instead, iterating `open_legs` as a set of
`(leg_role, instrument_key)` pairs derived from `positions` rather than just `leg_role`.

**Tests required:** add a case in the relevant `paper_snapshot` test file covering two open
positions sharing a `leg_role` with distinct notes → both notes appear in output.

**Files touched:** `scripts/portfolio/paper_snapshot.py` + its test file. Independent of PG-2a.

---

## PG-2d — `record_paper_trade.py` explicit instrument_key

**Problem:** The final position-summary print calls
`store.get_position(trade.strategy_name, trade.leg_role)` without passing the `instrument_key`
it already has in hand (`instrument_key` is resolved earlier in `main()`), so it's exposed to
the same ambiguity PG-2a fixes rather than sidestepping it entirely.

**Fix:** Pass `instrument_key=instrument_key` explicitly.

**Tests required:** update the existing `main()` CLI test(s) to assert `get_position` is called
with the instrument_key kwarg (mock/spy assertion).

**Files touched:** `scripts/record/record_paper_trade.py` + its test file. **Depends on PG-2a**
landing first (needs the new parameter to exist).

---

## PG-2e — `paper_ic_entry.py` explicit instrument_key

**Problem:** The post-entry verification loop calls `store.get_position(config.strategy_name, role)`
without the `key` variable already available from the `legs` tuples built earlier in `run()`.
Currently documented as safe because these are fresh legs with no prior fills, but passing the
instrument_key removes reliance on that assumption entirely.

**Fix:** Pass `instrument_key=key` explicitly in the verification loop.

**Tests required:** update the existing entry-workflow test(s) to assert the instrument_key
kwarg is passed.

**Files touched:** `scripts/strategies/ic/paper_ic_entry.py` + its test file. **Depends on
PG-2a** landing first.

---

## PG-3 — Docs close

**No code.** Targeted `Edit` calls only — never `Write` on existing files.

1. `TODOS.md` — mark PG-1, PG-2 (+2a-2e), PG-3 complete with session log entry.
2. `DECISIONS.md` — add entry: "`get_positions()` groups by `(strategy, leg_role, instrument_key)`;
   one `PaperPosition` per instrument, not per leg role. Rationale: rolls require per-instrument
   accounting; `delete_trade()` already uses this granularity."
3. `CONTEXT.md` — update `PaperStore` description to reflect new grouping behaviour.

Note: PG-3 should run only after PG-2a through PG-2e (or whichever subset the team decides to
land) are complete — its docs-close pass summarizes the whole PG-2 split, not just PG-2a.

---

## PG-4 — (deferred) Thread instrument_key through ApprovedAction for PaperExecutor.apply()

**Problem:** `PaperExecutor.apply()` closes a leg via
`self._store.get_position(strategy_name, leg_role)` — it has no way to specify which instrument
to close when a roll overlap leaves two positions sharing a `leg_role`, because
`ApprovedAction.legs_to_close` (`src/strategy/protocol.py`) is just `list[str]` of leg roles.
PG-2a's WARNING-logged most-recent-`entry_date` fallback reduces this from a silent wrong-leg
risk to a *logged* wrong-leg risk, but does not eliminate it.

**Fix (not yet scoped in detail):** Change `legs_to_close` to carry `(leg_role, instrument_key)`
pairs (or a small dataclass), update every strategy that constructs `ApprovedAction`
(`CSPNiftyV1`, `CCOverlayV1`, `PPOverlayV1`, `CollarOverlayV1`, `IronCondorV1`, `IronCondorV2`,
`NiftyTrackComparisonV1` — see `src/strategy/*.py`) to populate it, and update
`PaperExecutor.apply()` to pass `instrument_key` through to `get_position()`.

**Why deferred:** Touches the shared `PaperStrategy`/`ApprovedAction` protocol plus every
concrete strategy — a materially larger, independent change than PG-2's per-caller audit fixes.
Needs its own scoping session before implementation.

**Files likely touched:** `src/strategy/protocol.py`, `src/strategy/executor.py`, all
`src/strategy/*_v1.py` + `ic_nifty_v1.py`/`ic_nifty_v2.py`, their tests.
