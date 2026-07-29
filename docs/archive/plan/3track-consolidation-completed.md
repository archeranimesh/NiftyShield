# 3-Track Consolidation & Automation — Completed Story Specs (Archive)

> Historical record only. These stories are all shipped and ticked `[x]` in
> `docs/plan/3track-consolidation/tasks.md`. Kept here in full (nothing deleted, only moved)
> because later stories' "Before any code" steps and context sections reference the reasoning
> below — e.g. S3r's design constraints trace directly to the REVISION decision here, and S1r's
> migration script is reused verbatim by future data-migration work if it ever recurs.
> Active/open work lives in `docs/plan/3track-consolidation/stories.md`; the epic-level Decision
> Log and current scope boundary live in `docs/plan/3track-consolidation/prompt.md`.

---

## REVISION (2026-07-29) — Overlay/track independence supersedes S1's spot-only outcome and all of S2

**Operator decision, this session:** overlay must exist in the DB **independent of any track**
— no entry-time block tying it to `paper_nifty_spot`. Comparison (P&L, protection coverage) against
a given track (Spot / Futures / Proxy) is computed **at query time only**, never by writing
duplicate overlay trade rows per track (that was RQ2's mistake — S1 exists to clean up its
consequences, not to reintroduce a narrower version of the same conflation). **No change to
existing qty/lot sizing** — Spot's 5735 ETF units, Futures' 65-qty (1 lot), Proxy's 65-qty (1 lot)
are used as-is; capital parity (~15L margin at entry, confirmed by operator) is what makes the three
tracks P&L-comparable, not exposure parity. Exposure (effective Nifty units) still differs per
track — ETF ≈1x, Futures levered via SPAN margin, DITM call ≈ delta <1x — so overlay *coverage
ratio* per track is a real per-track calculation, not a flat lookup, and does not exist anywhere in
the original S1/S2/S3 design.

**What this supersedes:**
- **S2 is deleted, not implemented.** Its entire purpose (hard-block overlay entry outside
  `paper_nifty_spot`) is the opposite of what's now wanted. The existing narrow
  `_check_futures_cc_block` (`src/strategy/nifty_track_comparison_v1.py:156`) — today's only live
  block, CC+Futures specific — is also in scope for removal under S2r below, since it's the same
  conflation on a smaller scale.
- **S1's outcome changes**, not its cleanup logic. The LTP-fetch/intrinsic-fallback machinery for
  closing the *duplicate* Futures/Proxy overlay rows (three physical copies of the same trade) is
  still correct and still needed — RQ2's bug was writing 3 trade rows for 1 economic position, and
  that's still wrong under the new design. What changes is the destination: instead of closing
  Futures/Proxy copies and leaving the survivor owned by `paper_nifty_spot` (S1's original text),
  the single surviving overlay position is **re-owned** to a new track-independent namespace.
- **S3 is unaffected in its core design** — "overlay never math-linked into the base comparison
  snapshot" already holds under the new model; S3's `pnl_1d_*`/`pnl_inception_*` fields stay
  base-leg-only exactly as specified. Only its terminology needs a pass (S3 currently phrases
  overlay independence as "post-S2"; that pointer now points at S1r/S2r below).

### S1r — Re-home overlay legs to an independent strategy namespace (supersedes S1's destination)

**Status: shipped 2026-07-29 — SHA `8c41cca`.**

**Problem:** `paper_trades.strategy_name` currently conflates two things — *which economic
position* and *which track owns it*. Overlay legs (`overlay_pp`, `overlay_cc`,
`overlay_collar_call`, `overlay_collar_put`) must not be owned by `paper_nifty_spot`,
`paper_nifty_futures`, or `paper_nifty_proxy` at all — they need their own `strategy_name`
(e.g. `paper_nifty_overlay`) so entry, rolls, and exits happen exactly once per real position,
with zero track ownership baked into the row.

**Files changed:**
- `scripts/dev/migrate_3track_close_duplicate_overlays.py` (S1's script, same LTP/intrinsic-fallback
  logic) — retarget: after closing genuine Futures/Proxy duplicates (S1b bug rows included — see
  original S1 table below), **re-write** the surviving overlay rows currently under `paper_nifty_spot`
  with `strategy_name='paper_nifty_overlay'` instead of leaving them under spot. This is a rename
  of ownership, not a new trade — same `trade_date`/`price`/`quantity`, only `strategy_name` changes.
- `src/portfolio/strategies/__init__.py` / `ALL_STRATEGIES`-equivalent registry for 3-track —
  registered `paper_nifty_overlay` as a real (non-track) strategy entry
- `src/db.py` / migration script — `strategies` table row for `paper_nifty_overlay`

**Tests:**
- `test_duplicate_futures_proxy_rows_still_closed` — S1's original behavior, unchanged
- `test_surviving_overlay_rewritten_to_overlay_namespace` — post-migration, `overlay_pp`/
  `overlay_collar_put` rows have `strategy_name='paper_nifty_overlay'`, not `paper_nifty_spot`
- `test_no_new_trade_rows_created_by_rehoming` — row count for the surviving legs is unchanged,
  only `strategy_name` differs (guards against silently duplicating instead of renaming)

**Commit:** `refactor(paper): re-home overlay legs to track-independent strategy_name` — SHA `8c41cca`

### S2r — Remove track-ownership blocks (deletes S2, removes existing `_check_futures_cc_block`)

**Status: shipped 2026-07-29 — SHA `abdb7ef`.**

**Problem:** two blocks currently exist or were planned that tie overlay to a specific track —
today's live `_check_futures_cc_block` (CC+Futures only) and the never-implemented S2 (all overlay
types, Futures+Proxy). Both must go; overlay entry should only ever check the *overlay's own*
namespace/state, never which track is asking.

**Files changed:**
- `src/strategy/nifty_track_comparison_v1.py` — removed `_check_futures_cc_block` (line ~156) and
  its call site (~line 230); no `_check_non_niftybees_overlay_block` sibling implemented
- `tests/unit/strategies/test_nifty_track_comparison_v1.py` — removed the block's tests

**Scope grew during implementation** to also remove a second, undocumented futures+`overlay_cc`
hard-block found inside `_select_overlay_roll_target` (same conflation, confirmed in-scope with
operator before removing).

**Tests:**
- `test_overlay_entry_no_longer_blocked_by_track` — writing an overlay leg regardless of which
  track's context it's entered from succeeds (once re-homed to `paper_nifty_overlay` per S1r,
  "track" stops being a valid input to overlay entry at all — test that the parameter is gone,
  not just unblocked)

**Commit:** `fix(strategy): remove track-based overlay entry blocks, overlay is track-independent` — SHA `abdb7ef`

**Council checkpoint — waived, operator override (2026-07-29):** this revision qualifies under
CLAUDE.md Step 2b, but the operator explicitly declined a council discussion and directed override.
Sign-off recorded in `DECISIONS.md` (round 5 entry) in lieu of a council pass. S1r/S2r/S3r were
cleared to proceed to Step 3 (state plan, get go-ahead) without further gating.

---

## S1 — Retire duplicate overlay legs on Futures and Proxy (data migration, operator go-ahead required)

> **Superseded 2026-07-29 — see REVISION above and S1r.** Original text kept below for the
> LTP-fetch/intrinsic-fallback logic and the S1b bug table, both still correct and reused by S1r.
> S1's original "leave survivor under paper_nifty_spot" outcome was never implemented as such —
> S1r shipped with the re-homed destination instead.

**Context:** `paper_trades` currently carries near-identical overlay legs across all three
strategy namespaces — same instrument_key, same strike, same entry price, entered the same
day — because the original design (RQ2) wanted overlay-per-base comparison. Confirmed live
duplicates as of 2026-07-20:

| leg_role | instrument_key | Spot | Futures | Proxy |
|---|---|---|---|---|
| `overlay_collar_call` | `NSE_FO\|65900` | open | open | open |
| `overlay_collar_put` | `NSE_FO\|65894` | open | open | open |
| `overlay_pp` | `NSE_FO\|58627` | open (never closed — likely expired, booking gap) | open (same gap) | closed (rolled correctly) |
| `overlay_pp` | `NSE_FO\|63848` | open | open | — |
| `overlay_cc` | `NSE_FO\|71474` | state=OPEN but net flat (bought back 06-08) — **separately a data bug, not in scope here, see S1b** | n/a (hard-blocked, never existed for futures) | state=OPEN but net flat |

**Decision (prompt.md #2 recommendation):** write explicit closing trades for
the Futures and Proxy copies of `overlay_collar_call`, `overlay_collar_put`, and `overlay_pp`,
priced at the LTP available at story-execution time (same pattern as `close_ic_legs()` in
`src/strategy/ic_close_executor.py` — batch LTP fetch, intrinsic-value fallback if expired).
Do not hard-delete rows. NiftyBees (`paper_nifty_spot`) copies are untouched by this story —
they become the sole surviving live overlay after S3 ships.

**S1b (bundled into this story, same root cause class):** the `overlay_cc` leg for spot has a
closing BUY (`NSE_FO|71474`, 06-08, price 12.60) tagged `state='OPEN'` when the near-identical
`overlay_collar_call` closing BUY at the same price/date is correctly `CLOSED`. Fixed the state
on that row too — this was the reason CC showed as absent from `paper_leg_snapshots` via omission
rather than an explicit closed state, which would have confused the single-copy aggregation in S3.

**Files changed:**
- New one-off script: `scripts/dev/migrate_3track_close_duplicate_overlays.py` (`--dry-run`
  default, explicit `--apply` flag, structured log line per row closed)
- `tests/unit/scripts/test_migrate_3track_close_duplicate_overlays.py`

**Tests:**
- `test_dry_run_reports_rows_without_writing` — dry-run mode touches zero rows
- `test_apply_closes_futures_and_proxy_overlay_legs` — after `--apply`, all Futures/Proxy overlay
  rows for collar_call/collar_put/pp are `state='CLOSED'`; Spot rows untouched
- `test_cc_state_bug_fixed` — `overlay_cc` 71474 BUY row for spot/proxy now `CLOSED`
- `test_expired_leg_uses_intrinsic_fallback` — 58627 (past expiry) prices via intrinsic value, not live LTP

**Commit:** `fix(paper): close duplicate Futures/Proxy overlay legs, retire RQ2 overlay data`

---

## S2 — Restrict overlay entry to NiftyBees only

> **Deleted 2026-07-29 — see REVISION above and S2r. Never implemented.** Overlay entry
> is track-independent by operator decision; this story's entire premise (block non-spot overlay
> entry) was superseded before implementation.

**Context:** `paper_3track_overlay.py` / `paper_3track_overlay_entry.py` / `find_overlay_strikes.py`
currently write overlay legs for all three strategy namespaces in one pass. Post-S1, only
`paper_nifty_spot` should ever receive a new overlay leg. Futures already has a standalone-CC
hard block (`_check_futures_cc_block`) — this story generalizes that pattern to a full
non-NiftyBees overlay block, all overlay types, both Futures and Proxy.

**Files that would have changed (never implemented):**
- `scripts/strategies/three_track/paper_3track_overlay.py`
- `scripts/strategies/three_track/paper_3track_overlay_entry.py`
- `scripts/lookup/find_overlay_strikes.py`
- `src/strategy/nifty_track_comparison_v1.py` — `_check_futures_cc_block` → generalize or add
  a sibling `_check_non_niftybees_overlay_block` (ERROR severity, matches existing pattern)
- `tests/unit/scripts/`, `tests/unit/strategies/test_nifty_track_comparison_v1.py`

**Required behavior (as originally specified):**
- Any script that would write an `overlay_*` leg_role trade for `paper_nifty_futures` or
  `paper_nifty_proxy` must hard-fail (not silently skip) with a clear error naming the
  blocked strategy_name, matching the existing futures-CC error message style.
- `paper_3track_overlay.py` / `_entry.py` drop the `--tracks` fan-out for overlay writes
  entirely — overlay commands no longer accept `futures`/`proxy` as valid `--track` values.
  Base-leg entry (`paper_3track_entry.py`) is untouched — all three tracks still get a base
  position, this story only touches overlays.

**Commit:** none — deleted before implementation.

---

## S3 — Independent daily base-leg comparison snapshot (overlay fully excluded)

**Status: shipped 2026-07-29 — SHA `07570d3`.**

**Context (revised 2026-07-28 — supersedes the original synthetic-attribution design below the
operator explicitly rejected):** RQ1 is "which base instrument tracks Nifty best" — NiftyBees,
Futures, or the DITM synthetic long. The operator wants this answered as a clean, apples-to-apples
comparison across all three tracks, with **zero overlay involvement, for any track, including
NiftyBees.** Overlay P&L is real and useful, but it answers a different question (protection
cost/benefit) and must never blend into or be inferred from the base-instrument comparison.
Concretely: no synthetic attribution, no overlay-adjusted NiftyBees figure in this comparison —
overlay is display/analysis only, never trade-linked to Futures/Proxy (already true post-S2r) and
never *math*-linked to the comparison numbers for any of the three tracks.

**Two independent, non-overlapping outputs from this story:**

1. **Daily base-only comparison snapshot** — persisted table `paper_track_comparison_snapshots`,
   one row per `(snapshot_date, strategy_name)` for all three 3-track strategies, computed strictly
   from `base_etf` / `base_futures` / `base_ditm_call` leg mark price (never touching overlay
   rows). **Level-1 fields, confirmed 2026-07-28 (operator):**
   - `pnl_1d_abs` — today's base-leg mark minus yesterday's base-leg mark (absolute ₹)
   - `pnl_1d_pct` — `pnl_1d_abs / yesterday's_mark` (denominator is yesterday's closing mark, the
     standard daily-return definition — NOT entry cost basis, NOT NEE/spot notional)
   - `pnl_inception_abs` — today's base-leg mark minus entry price (absolute ₹, cumulative since
     the track's original entry date)
   - `pnl_inception_pct` — `pnl_inception_abs / entry_cost_basis` (denominator is the original
     entry price/cost — deliberately a *different* denominator than the 1-day figure)
   - Tracking-error figure (base track cumulative return % vs. Nifty spot cumulative return % over
     the same window) — secondary/bonus field.

   **Nifty spot as a 4th series (confirmed 2026-07-28, operator):** Nifty spot gets the identical
   four `pnl_1d_abs`/`pnl_1d_pct`/`pnl_inception_abs`/`pnl_inception_pct` fields, computed the
   exact same way as the three tracks. Persisted as its own row in the same table using synthetic
   `strategy_name="nifty_index"` rather than a separate schema.

   Written by the daily cron (`paper_3track_snapshot.py`). Queryable independently via
   `get_track_comparison_snapshots(strategy_name, start_date=None, end_date=None)`.
2. **Overlay P&L** — stays exactly where it already lives (`paper_leg_snapshots` /
   `get_strategy_realized_pnl`). No new table. The comparison query in (1) never joins or filters
   on overlay `leg_role`s — enforced with an explicit `leg_role IN ('base_etf','base_futures',
   'base_ditm_call')` filter.

**Files changed:**
- `src/paper/models.py` — `TrackComparisonSnapshot` dataclass
- `src/paper/store.py` — `paper_track_comparison_snapshots` table, `record_track_comparison_snapshot()`
  / `get_track_comparison_snapshots()`
- `scripts/strategies/three_track/paper_3track_snapshot.py` — `_compute_track_comparison_snapshot()`
  / `_compute_spot_comparison_snapshot()`, wired into `_run()`
- `scripts/dev/generate_3track_viz.py` — separate RQ1 comparison table, never merged with the
  overlay-inclusive base/cc/pp/collar series
- `tests/unit/paper/test_store.py`, `tests/unit/scripts/test_paper_3track_comparison.py`

**Tests:**
- `test_comparison_snapshot_excludes_overlay_legs` — base-only P&L, verified against a fixture
  with overlay rows present, asserting they never enter the aggregation
- `test_pnl_1d_uses_yesterday_mark_denominator` — `pnl_1d_pct` computed against yesterday's
  closing mark, not entry cost or NEE
- `test_pnl_inception_uses_entry_cost_denominator` — `pnl_inception_pct` computed against original
  entry price/cost basis, not yesterday's mark
- `test_pnl_1d_and_inception_use_different_denominators` — explicit regression guard that the two
  percentage fields are never computed off the same base
- `test_tracking_error_computed_against_spot` — base track return vs. Nifty spot return since entry
- `test_spot_persisted_as_fourth_series` — Nifty spot row present with the same 4 `pnl_*` fields
- Full list: `tests/unit/scripts/test_paper_3track_comparison.py`, `tests/unit/paper/test_store.py`

**Commit:** `feat(paper): independent daily base-leg comparison snapshot, overlay fully decoupled` — SHA `07570d3`

**Deferred (2 WARNINGs, real `@code-reviewer` pass, 0 CRITICAL/ERROR):** both
`_compute_track_comparison_snapshot`'s no-prior-snapshot bootstrap branch and
`_compute_spot_comparison_snapshot`'s prev-spot-lookup-gap fallback force `pnl_1d_pct =
Decimal("0")` even when `pnl_1d_abs` is non-zero. Low mission impact (paper-trading, cosmetic
edge case). See `DECISIONS.md` 2026-07-29 S3 entry.
