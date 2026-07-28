# 3-Track Consolidation & Automation — Story Specs

> Read `prompt.md` first — it has the Decision Log this whole epic depends on.
> Story order (revised 2026-07-28, two rounds): S3 and S5 are independent of S1/S2 — the daily
> comparison snapshot is base-leg-only and never reads overlay rows, so overlay duplication/
> restriction no longer gates it. **S4 (overlay automation) still needs S1 + S2 landed first** —
> automating overlay actions on top of triplicated/unrestricted overlay data would let a bot act
> on the CC state bug or roll an overlay onto a track it's no longer supposed to exist on. **S6
> (bootstrap-entry automation + trade-event Telegram notifications — revised same day, see below)
> needs S2 + S5 landed first** — it automates overlay/base entry and wires notifications into S5's
> roll executor, so it can't ship before those exist. Suggested pick-up order: S3 can start
> immediately, standalone. S5 can start immediately, standalone, but is more useful landed before
> S6. S1 waits on operator go-ahead; S2 can follow S1 or run parallel with S3/S5. S4 after S1+S2.
> S6 last of the functional stories, after S2+S5 (and ideally S4, since S6 is the story that
> removes the last human checkpoint from the whole pipeline — better to land it once overlay
> automation is already proven stable). S0 (docs) trails everything, after S6, since stale docs
> actively mislead the next session per CLAUDE.md Rule 0.
> **Correction (2026-07-28, same day):** S6 originally specified a recurring, fixed-cadence
> re-entry trigger with an unresolved cycle-overlap question. A lifecycle walkthrough with the
> operator surfaced that all three tracks are actually perpetual single-entry positions — nothing
> in this epic ever closes one, "roll" means contract maintenance, not cycle renewal. S6 is revised
> below to a one-time bootstrap entry; the cadence/overlap question is void, not just answered.

---

## S1 — Retire duplicate overlay legs on Futures and Proxy (data migration, operator go-ahead required)

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

**Decision (prompt.md #2 recommendation — confirm with operator before executing this story,
even though the rest of the epic doesn't need sign-off):** write explicit closing trades for
the Futures and Proxy copies of `overlay_collar_call`, `overlay_collar_put`, and `overlay_pp`,
priced at the LTP available at story-execution time (same pattern as `close_ic_legs()` in
`src/strategy/ic_close_executor.py` — batch LTP fetch, intrinsic-value fallback if expired).
Do not hard-delete rows. NiftyBees (`paper_nifty_spot`) copies are untouched by this story —
they become the sole surviving live overlay after S3 ships.

**S1b (bundle into this story, same root cause class):** the `overlay_cc` leg for spot has a
closing BUY (`NSE_FO|71474`, 06-08, price 12.60) tagged `state='OPEN'` when the near-identical
`overlay_collar_call` closing BUY at the same price/date is correctly `CLOSED`. Fix the state
on that row too — this is the reason CC currently shows as absent from `paper_leg_snapshots`
via omission rather than an explicit closed state, which will confuse the new single-copy
aggregation in S3 if left as-is.

**Files to change:**
- New one-off script: `scripts/dev/migrate_3track_close_duplicate_overlays.py` (follow
  `scripts/dev/migrate_add_closed_state.py` pattern referenced in TODOS.md BUG-7 — `--dry-run`
  default, explicit `--apply` flag, structured log line per row closed)
- `tests/unit/scripts/test_migrate_3track_close_duplicate_overlays.py`

**Before any code:**
```
git log --oneline -10 scripts/dev/migrate_add_closed_state.py   # prior art for this exact pattern
search_graph("close_ic_legs")                                    # reuse LTP-fetch/fallback logic
search_code("state='OPEN'")                                      # confirm no other consumers assume these rows stay open
```

**Tests:**
- `test_dry_run_reports_rows_without_writing` — dry-run mode touches zero rows
- `test_apply_closes_futures_and_proxy_overlay_legs` — after `--apply`, all Futures/Proxy overlay
  rows for collar_call/collar_put/pp are `state='CLOSED'`; Spot rows untouched
- `test_cc_state_bug_fixed` — `overlay_cc` 71474 BUY row for spot/proxy now `CLOSED`
- `test_expired_leg_uses_intrinsic_fallback` — 58627 (past expiry) prices via intrinsic value, not live LTP

**Commit:** `fix(paper): close duplicate Futures/Proxy overlay legs, retire RQ2 overlay data`

---

## S2 — Restrict overlay entry to NiftyBees only

**Context:** `paper_3track_overlay.py` / `paper_3track_overlay_entry.py` / `find_overlay_strikes.py`
currently write overlay legs for all three strategy namespaces in one pass. Post-S1, only
`paper_nifty_spot` should ever receive a new overlay leg. Futures already has a standalone-CC
hard block (`_check_futures_cc_block`) — this story generalizes that pattern to a full
non-NiftyBees overlay block, all overlay types, both Futures and Proxy.

**Files to change:**
- `scripts/strategies/three_track/paper_3track_overlay.py`
- `scripts/strategies/three_track/paper_3track_overlay_entry.py`
- `scripts/lookup/find_overlay_strikes.py`
- `src/strategy/nifty_track_comparison_v1.py` — `_check_futures_cc_block` → generalize or add
  a sibling `_check_non_niftybees_overlay_block` (ERROR severity, matches existing pattern)
- `tests/unit/scripts/`, `tests/unit/strategies/test_nifty_track_comparison_v1.py`

**Before any code:**
```
get_code_snippet("NiftyTrackComparisonV1._check_futures_cc_block")
search_code("overlay_collar")
search_code("overlay_pp")
search_code("overlay_cc")
git log --oneline -10 src/strategy/nifty_track_comparison_v1.py
```

**Required behavior:**
- Any script that would write an `overlay_*` leg_role trade for `paper_nifty_futures` or
  `paper_nifty_proxy` must hard-fail (not silently skip) with a clear error naming the
  blocked strategy_name, matching the existing futures-CC error message style.
- `paper_3track_overlay.py` / `_entry.py` drop the `--tracks` fan-out for overlay writes
  entirely — overlay commands no longer accept `futures`/`proxy` as valid `--track` values.
  Base-leg entry (`paper_3track_entry.py`) is untouched — all three tracks still get a base
  position, this story only touches overlays.

**Tests:**
- `test_overlay_entry_blocks_futures` / `test_overlay_entry_blocks_proxy` — attempted overlay
  write for either namespace raises/hard-exits with the expected error
- `test_overlay_entry_allows_niftybees` — happy path unchanged for spot
- `test_track_flag_rejects_non_niftybees_for_overlay_commands`

**Commit:** `feat(strategy): restrict all overlay entry to paper_nifty_spot only`

---

## S3 — Independent daily base-leg comparison snapshot (overlay fully excluded)

**Context (revised 2026-07-28 — supersedes the original synthetic-attribution design below the
operator explicitly rejected):** RQ1 is "which base instrument tracks Nifty best" — NiftyBees,
Futures, or the DITM synthetic long. The operator wants this answered as a clean, apples-to-apples
comparison across all three tracks, with **zero overlay involvement, for any track, including
NiftyBees.** Overlay P&L is real and useful, but it answers a different question (protection
cost/benefit) and must never blend into or be inferred from the base-instrument comparison.
Concretely: no synthetic attribution, no overlay-adjusted NiftyBees figure in this comparison —
overlay is display/analysis only, never trade-linked to Futures/Proxy (already true post-S2) and
now also never *math*-linked to the comparison numbers for any of the three tracks.

**Two independent, non-overlapping outputs from this story:**

1. **Daily base-only comparison snapshot** — new persisted table (e.g. `paper_track_comparison_snapshots`),
   one row per `(snapshot_date, strategy_name)` for all three 3-track strategies, computed strictly
   from `base_etf` / `base_futures` / `base_ditm_call` leg mark price (never touching overlay
   rows). **Level-1 fields, confirmed 2026-07-28 (operator):**
   - `pnl_1d_abs` — today's base-leg mark minus yesterday's base-leg mark (absolute ₹)
   - `pnl_1d_pct` — `pnl_1d_abs / yesterday's_mark` (denominator is yesterday's closing mark, the
     standard daily-return definition — NOT entry cost basis, NOT NEE/spot notional)
   - `pnl_inception_abs` — today's base-leg mark minus entry price (absolute ₹, cumulative since
     the track's original entry date)
   - `pnl_inception_pct` — `pnl_inception_abs / entry_cost_basis` (denominator is the original
     entry price/cost — deliberately a *different* denominator than the 1-day figure; do not reuse
     yesterday's mark here, and do not conflate the two %s as directly subtractable/addable)
   - Tracking-error figure (base track cumulative return % vs. Nifty spot cumulative return % over
     the same window) — this is a secondary/bonus field answering RQ1's actual tracking-quality
     question; the four `pnl_*` fields above are the operator's explicit level-1 ask and take
     priority if there's ever a conflict in implementation ordering.

   **Nifty spot as a 4th series (confirmed 2026-07-28, operator):** Nifty spot gets the identical
   four `pnl_1d_abs`/`pnl_1d_pct`/`pnl_inception_abs`/`pnl_inception_pct` fields, computed the
   exact same way as the three tracks — 1-day % against yesterday's spot close, inception % against
   spot's price on the relevant track's entry date. Persist it as its own row in the same table
   using a synthetic `strategy_name` value (e.g. `"nifty_index"`) rather than a separate schema or
   a bolt-on column set — keeps `get_track_comparison_snapshots()` and every downstream query
   uniform across all four series (three tracks + spot), no special-casing required. Since the
   three tracks may have different entry dates in principle (even though today's live data has
   them entered the same day), spot's `pnl_inception_*` should be computed once per *comparison
   context* against whichever track's entry date is relevant to that comparison — flag this as an
   implementation-time detail to resolve if entry dates ever diverge across tracks; not expected to
   matter for the current live data (see S1 context table — all three entered same day).

   Written by a daily cron (extend `paper_3track_snapshot.py` or a new sibling script — decide at
   implementation time based on how entangled the existing snapshot function already is). Must be
   queryable independently, e.g.
   `SELECT * FROM paper_track_comparison_snapshots WHERE strategy_name = ? ORDER BY snapshot_date` —
   this is the whole point: performance-over-time query support, not just an EOD print.
2. **Overlay P&L** — stays exactly where it already lives (existing `paper_leg_snapshots` /
   `get_strategy_realized_pnl` machinery for `paper_nifty_spot`'s overlay legs). No new table. The
   comparison query in (1) must never join or filter on overlay `leg_role`s — enforce this with an
   explicit `leg_role IN ('base_etf','base_futures','base_ditm_call')` filter, not an implicit
   exclusion, so a future contributor can't accidentally reintroduce overlay rows by widening a
   query.

**Files to change:**
- `scripts/strategies/three_track/paper_3track_snapshot.py` — new base-only comparison
  aggregation + daily persistence call; leave existing overlay P&L reporting untouched
- `src/paper/store.py` / `src/paper/models.py` — new `TrackComparisonSnapshot` model +
  `record_track_comparison_snapshot()` / `get_track_comparison_snapshots()` store methods
- `scripts/dev/generate_3track_viz.py` — comparison viz reads from the new table, overlay stays a
  visually separate section, never merged into the same series/column
- `tests/unit/scripts/test_paper_3track_snapshot_period.py` and siblings
- `tests/unit/paper/test_store.py` (or sibling) for the new snapshot table

**Before any code:**
```
get_code_snippet("paper_3track_snapshot")     # or trace_path if too large for one snippet
search_code("paper_leg_snapshots")
search_code("underlying_price")               # NEE/tracking-error math already exists somewhere, reuse it
git log --oneline -10 scripts/strategies/three_track/paper_3track_snapshot.py
```

**Tests:**
- `test_comparison_snapshot_excludes_overlay_legs` — base-only P&L, verified against a fixture
  with overlay rows present, asserting they never enter the aggregation
- `test_comparison_snapshot_persists_all_three_tracks_daily` — one row per strategy per day
- `test_comparison_snapshot_queryable_by_date_range` — `get_track_comparison_snapshots()` returns
  ordered history for a given strategy
- `test_pnl_1d_uses_yesterday_mark_denominator` — `pnl_1d_pct` computed against yesterday's
  closing mark, not entry cost or NEE
- `test_pnl_inception_uses_entry_cost_denominator` — `pnl_inception_pct` computed against original
  entry price/cost basis, not yesterday's mark
- `test_pnl_1d_and_inception_use_different_denominators` — explicit regression guard that the two
  percentage fields are never computed off the same base, given they look similar but aren't
- `test_tracking_error_computed_against_spot` — base track return vs. Nifty spot return since entry
- `test_spot_persisted_as_fourth_series` — Nifty spot row present with the same 4 `pnl_*` fields,
  same denominators as the 3 tracks, queryable via the same `strategy_name`-keyed method
- `test_overlay_pnl_untouched_by_comparison_change` — existing overlay P&L reporting path produces
  identical output before/after this story (regression guard against accidental coupling)

**Commit:** `feat(paper): independent daily base-leg comparison snapshot, overlay fully decoupled`

---

## S4 — Full automation of NiftyTrackComparisonV1

**Context:** `NiftyTrackComparisonV1.auto_execute` is currently `False` by explicit prior design
(CONTEXT.md: "all overlay and Proxy actions require human confirmation") — every other overlay
strategy in the codebase (`CCOverlayV1`, `PPOverlayV1`, `CollarOverlayV1`) already runs
`auto_execute=True`. Operator has confirmed (prompt.md Decision Log #3) they want this flipped,
council-checkpoint explicitly skipped at their instruction.

**This story ships last**, after S1–S3, so automated actions are operating against the
already-cleaned single-copy overlay data — flipping automation on top of the current
triplicated/buggy state would let a bot act on the CC state bug (S1b) or the PP booking gap
before those are fixed.

**Files to change:**
- `src/strategy/nifty_track_comparison_v1.py` — `auto_execute` property/flag
- `src/notifications/telegram_gateway.py` — likely no change (approval path just won't be
  invoked for this strategy anymore), but confirm no dead-code assumption elsewhere depends on
  this strategy always routing through Telegram approval
- `tests/unit/strategies/test_nifty_track_comparison_v1.py`

**Before any code:**
```
get_code_snippet("NiftyTrackComparisonV1")
search_code("auto_execute")                     # compare pattern against CCOverlayV1/PPOverlayV1/CollarOverlayV1
trace_path("StrategyMonitor._handle_event")      # confirm auto-execute dispatch path handles this strategy's action set already
git log --oneline -10 src/strategy/nifty_track_comparison_v1.py
```

**Required behavior:**
- `auto_execute=True`, dispatched through `PaperExecutor` like the other three overlay strategies.
- All existing hard blocks (`_check_futures_cc_block` / S2's generalized non-NiftyBees overlay
  block, proxy delta signals, roll-base-first guard) remain enforced — automation removes the
  human approval step, not the safety gates. This is the single most important invariant of this
  story: automating the wrong action faster is strictly worse than the current manual-approval
  state, not neutral.
- Confirm `close_ic_legs()`-style persistence discipline applies here too — TODOS.md already
  documents a real incident (2026-07-15) where auto-execute actions were computed but never
  written to `paper_trades` for IC strategies. Explicitly test that every auto-executed action
  in this strategy actually persists.

**Tests:**
- `test_auto_execute_flag_is_true`
- `test_roll_eligible_action_dispatches_without_approval`
- `test_blocked_combination_still_enforced_under_automation` — confirms S2's guard fires even
  with `auto_execute=True`
- `test_auto_executed_action_persists_to_paper_trades` — regression test for the exact class of
  bug fixed 2026-07-15 in the IC strategies

**Commit:** `feat(strategy): NiftyTrackComparisonV1 fully automated, auto_execute=True`

---

## S5 — Automated base-leg rolling for Futures and DITM tracks (2026-07-28)

**Context:** Base-leg rolling for `base_futures` and `base_ditm_call` has no automated script
today — `paper_3track_entry.py` is initial entry only (manual, `--confirm`), and
`_check_base_expiry()` (`paper_3track_snapshot.py`) only *alerts* on an expiring base leg via
`InstrumentLookup.get_next_contract_in_band()` (fixed 2026-07-20 to respect the monthly/
quarterly/yearly band, see DECISIONS.md), it doesn't execute the roll. `NiftyTrackComparisonV1`
explicitly does not evaluate base legs (`base_etf`/`base_futures`/`base_ditm_call` excluded from
its check_signals loop) — this story's automation is independent of S4's `auto_execute` flip and
does not depend on it.

**Confirmed decisions (2026-07-28, operator):**
- **Band preference stays `["monthly", "quarterly", "yearly"]`** — the codebase default in
  `get_expiry_candidates()`/`get_next_contract_in_band()` is unchanged; do not flip to
  quarterly-first. (Considered and rejected: NSE index F&O only lists 3 monthly serials — near/
  next/far — so a fixed quarterly-first preference would deliberately pick the least liquid of
  the available serials every roll.)
- **Roll trigger is per-leg, confirmed 2026-07-28 after a lifecycle walkthrough (not a single
  shared DTE threshold — corrects the original single-trigger design below):**
  - **`base_futures`: DTE ≤ 1** — roll on expiry day itself or the day before. Operator's explicit
    preference, prioritizing capital efficiency (stay in the current contract as long as possible)
    over the liquidity-crunch concern raised earlier. **Flagged, not blocking:** this deliberately
    rolls into the window where near-month OI is thinnest — if paper P&L ever looks materially
    better on this leg than a live desk would realize, this trigger choice is the first place to
    check before trusting the number.
  - **`base_ditm_call`: DTE < 20** (band_min + 5 buffer) — roll about a week ahead of expiry.
    Operator's stated reasoning was rising margin near expiry; the more material driver is this
    leg's much thinner options liquidity far from front-month (see Decision Log #6/#8 in
    `prompt.md`) — same conclusion, keep the early trigger regardless of which reason weighs more.
  - Checked daily off the existing snapshot/monitor cron for both legs.
- **Liquidity gate: warn-only, always roll** — matches `paper_3track_entry.py`'s existing
  `PROXY_OI_MIN`/`PROXY_SPREAD_MAX` pattern (log a WARNING, execute anyway). Operator explicitly
  chose not to hard-block on thin liquidity for this story.
- **Futures liquidity check: relative OI threshold** — target (next-band) contract's OI must be
  ≥ 10% of the current near-month contract's OI, checked at roll time. Chosen over an absolute
  OI floor because futures OI operates on a different scale than option OI and an absolute number
  would need periodic re-tuning as market-wide volume drifts; a relative threshold self-normalizes.
  DITM leg reuses the existing `PROXY_OI_MIN`/`PROXY_SPREAD_MAX` constants (already option-scale).

**Required behavior:**
- New daily check (extend the existing snapshot cron or add a sibling script — decide at
  implementation time): for each of `base_futures`/`base_ditm_call`, if held contract DTE < 20,
  resolve the next-band contract via `get_next_contract_in_band()`, compute the liquidity gate
  (relative-OI for futures, existing OI/spread constants for DITM), log WARN if it fails but roll
  regardless, execute the roll (close current leg, open next-band leg), and persist both trades
  atomically (same discipline as `close_ic_legs()` — this is a paper-trading system with a real
  prior incident, 2026-07-15, of auto-computed actions never reaching `paper_trades`).
- This story does **not** touch `NiftyTrackComparisonV1` or its `auto_execute` flag — base-leg
  rolling is a separate execution path from overlay strategy evaluation.

**Files to change:**
- New script or extension: `scripts/strategies/three_track/paper_3track_roll.py` (or extend
  `paper_3track_snapshot.py`'s `_check_base_expiry` from alert-only to alert+execute — decide
  based on how the existing function is structured)
- `tests/unit/scripts/test_paper_3track_roll.py` (or sibling matching final file location)

**Before any code:**
```
get_code_snippet("_check_base_expiry")
get_code_snippet("get_next_contract_in_band")
search_code("PROXY_OI_MIN")
search_code("PROXY_SPREAD_MAX")
git log --oneline -10 scripts/strategies/three_track/paper_3track_snapshot.py
```

**Tests:**
- `test_futures_roll_triggers_at_dte_1` / `test_futures_roll_does_not_trigger_above_dte_1`
- `test_ditm_roll_triggers_at_dte_20` / `test_ditm_roll_does_not_trigger_above_dte_20`
- `test_futures_and_ditm_use_independent_trigger_thresholds` — regression guard that the two legs'
  DTE thresholds are never accidentally unified into one shared constant
- `test_futures_relative_oi_gate_warns_not_blocks` — OI < 10% of near-month still rolls, logs WARN
- `test_ditm_liquidity_gate_reuses_existing_constants`
- `test_roll_persists_both_close_and_open_atomically` — regression guard for the 2026-07-15 class
  of bug (auto-computed action never reaching `paper_trades`)
- `test_niftytrackcomparisonv1_untouched` — confirms this story makes no change to overlay
  automation/evaluation

**Commit:** `feat(paper): automate base-leg rolling for Futures/DITM 3-track legs`

---

## S6 — Full unattended automation: cycle entry trigger + trade-event Telegram notifications (2026-07-28)

**Context:** Base-leg entry (`paper_3track_entry.py`) and overlay entry (`paper_3track_overlay_entry.py`)
are both manual today — run by hand with `--confirm`, no automatic trigger, no Telegram
notification on success. Overlay *close* already notifies (`cc_overlay_v1.py`/`pp_overlay_v1.py`/
`collar_overlay_v1.py` — `<b>CC: CLOSE</b>` style messages via `TelegramNotifier`). Base-leg roll
(S5) doesn't exist yet and needs a notification wired in from the start. Operator has now decided
(2026-07-28) that the entire pipeline should run unattended end to end — entry, roll, and overlay
actions all execute automatically, with Telegram as the sole visibility mechanism (no approval
gate anywhere in the flow after this story ships).

**Confirmed decisions (2026-07-28, revised same day after a lifecycle walkthrough surfaced a
contradiction — see below):**
- **All three tracks are perpetual, single-entry positions — there is no "cycle" that ever closes
  and no recurring re-entry.** NiftyBees is never closed. Futures and DITM "roll" means exactly
  "close current-month/current-band contract, open next-month/next-band contract" (S5) — it is
  contract maintenance on one continuous position, not a new cycle. This directly struck the
  original version of this story's "fixed cadence, independent of position state" entry-trigger
  decision, which only made sense under a "periodic new cycles" model that turned out not to be
  the operator's intent — flagged and corrected in the same session rather than left inconsistent
  across docs (see DECISIONS.md "round 3" entry).
- **Entry automation is a one-time bootstrap, not a recurring trigger.** If a track has no open
  base-leg position (i.e., it has never been entered, or — purely hypothetically, since nothing in
  this epic ever closes one — somehow became flat), automate that single entry. There is no
  cadence, no overlap handling to design, because there is no second cycle to overlap with.
- **Telegram notification required on:** base-leg roll (S5, new — must be built alongside S5, not
  bolted on after), overlay entry/open (new — currently silent), base-leg initial entry (new —
  currently silent, one-time). Overlay close is already implemented and unchanged by this story.

**Required behavior:**
- Reuse the existing `TelegramNotifier`/`build_notifier()` non-fatal contract
  (`src/notifications/CLAUDE.md`) — notification failure must never block or roll back a trade
  that already executed; log WARNING and continue, matching every other strategy's pattern.
- Message format matches the codebase's existing convention: plain text, `<b>`/`<code>` HTML tags
  (rendered inert inside Telegram's `<pre>` wrapper per `dhan/positions.py`'s documented behavior,
  but kept for consistency with strategies that send outside a `<pre>` wrapper — confirm which
  path `TelegramNotifier.send()` actually uses for these new call sites before assuming), emoji
  prefix per event type (suggest: 🔄 for roll, 🟢 for new entry, matching ✅/⚠️ used elsewhere).
- Each new call site (entry script, overlay entry script, S5's roll executor) gets its own
  non-fatal try/except around the notify call, mirroring `csp_nifty_v1.py`'s pattern — a
  notification failure is cosmetic, not a trade failure.

**Files to change:**
- `scripts/strategies/three_track/paper_3track_entry.py` — cadence-trigger logic (cron-invoked,
  not manual `--confirm` only), Telegram notify on successful entry
- `scripts/strategies/three_track/paper_3track_overlay_entry.py` — same trigger/notify treatment
- S5's roll script/function — Telegram notify on successful roll (build this in alongside S5,
  not as a follow-up)
- `tests/unit/scripts/` — per file above

**Before any code:**
```
get_code_snippet("TelegramNotifier.send")
search_code("build_notifier")
git log --oneline -10 src/strategy/cc_overlay_v1.py   # existing close-notification pattern to mirror
```

**Tests:**
- `test_entry_trigger_fires_when_no_open_position` — bootstrap-only, no cadence/schedule involved
- `test_entry_trigger_does_not_refire_once_position_open` — regression guard against accidentally
  reintroducing a recurring re-entry
- `test_entry_notifies_telegram_on_success`
- `test_overlay_entry_notifies_telegram_on_success`
- `test_roll_notifies_telegram_on_success` (mirrors S5's own roll tests — may be the same test file)
- `test_notification_failure_does_not_block_trade` — non-fatal contract regression guard, for
  every new call site added by this story

**Commit:** `feat(paper): automate 3-track cycle entry + Telegram notifications on every trade event`

**Flagged risk (log in TODOS.md's existing "Open risk not resolved by this epic" section, don't
block on it):** this story removes the last human checkpoint in the entire 3-track pipeline —
entry timing, strike selection, and every roll/overlay action now execute with no approval step,
Telegram becoming the only observability layer. Combined with S4's overlay automation and S5's
warn-only (non-blocking) liquidity gate, a bad automated decision anywhere in this chain now
executes for real (in paper terms) before any human sees it. Recommend the first live cycle after
S6 ships gets a manual daily review regardless of automation, same recommendation already logged
for S4.

---

## S0 — Documentation and decision-log updates

**Context:** `docs/instructions/3track.md` and `docs/strategies/nifty_track_comparison_v1.md`
still describe RQ2 (overlay-per-base comparison) as live research. Once S1–S6 ship, those docs
actively mislead — CLAUDE.md Rule 0 tells every future session to trust `git log` and the graph
over stale docs, but nothing should be relying on that safety net when a one-line doc fix
prevents the confusion entirely.

**Files to change:**
- `docs/instructions/3track.md` — rewrite Overlay Menu table: single column (NiftyBees only),
  remove Futures/Proxy overlay rows; note the daily base-only comparison snapshot (S3) is
  computed strictly from base legs, overlay P&L is a fully separate, non-blended report; note S5's
  automated base-leg roll cadence (DTE<20 trigger, band preference, liquidity gate behavior); note
  S6's cycle-entry cadence and full unattended pipeline, with Telegram as the sole visibility layer
- `docs/strategies/nifty_track_comparison_v1.md` — retire RQ2 explicitly, don't just delete it
  silently (future readers should know it was tried and retired, not that it was never asked)
- `CONTEXT.md` — update `NiftyTrackComparisonV1` description (`auto_execute=False` → `True`),
  add module tree entries for S1's migration script, S3's `TrackComparisonSnapshot`
  model/table + query methods, S5's roll script, and S6's entry-trigger + notification wiring
- `DECISIONS.md` — rows for: RQ2 retirement, automation flip, base-only comparison snapshot
  (overlay fully decoupled from RQ1 comparison), S5's roll trigger/liquidity-gate design, and S6's
  full-automation + notification-on-every-trade decision
- `TODOS.md` — close out the pre-existing PP booking-gap and CC state-bug items this epic
  subsumes (search for the 2026-07-20 session log entries this conversation would produce)

**No code-reviewer gate** — docs-only, per CLAUDE.md Step 5c.

**Commit:** `docs(3track): retire RQ2, document single-copy overlay + full automation`

---

## CC1 — Per-strategy delta candidate ladder, CC gets its own

> Context: `scripts/lookup/find_strike_by_delta.py` already does everything needed for a
> delta-targeted, multi-expiry (monthly/quarterly/yearly), liquidity-gated strike search —
> but it is CSP-only under the hood. Confirmed via live run (2026-07-28, `--option-type CE
> --delta-min 0.20 --delta-max 0.35 --strategy paper_covered_call_v1`): the printed
> comparison table honors the user's `--delta-min`/`--delta-max` flags, but the actual
> auto-selected strike (the one that generates the `record_paper_trade` command) does not —
> it re-filters against a hardcoded module-level `DELTA_CANDIDATES = [0.22, 0.25, 0.20]`,
> which is CSP's short-put target ladder, regardless of what the caller asked for. For CC
> this is silently wrong: the CLI accepted CE + a CC-appropriate delta range and then handed
> back a strike chosen against CSP's target deltas anyway.

**Problem:** `DELTA_CANDIDATES` (module-level constant in `find_strike_by_delta.py`) is used
unconditionally in `main()`'s auto-select loop, regardless of `--strategy`/`--option-type`.
There is no `CC_DELTA_CANDIDATES` — CC either silently inherits CSP's ladder (current, wrong
behavior) or has to bypass auto-select entirely and read the printed table by hand (current
workaround).

**Files to change:**
- `scripts/lookup/find_strike_by_delta.py` — add `CC_DELTA_CANDIDATES`, select the ladder
  based on `--option-type` (CE → CC ladder, PE → existing CSP ladder) or an explicit
  `--overlay-type cc` flag if that reads more clearly than inferring from side
- `src/instruments/strike_selector.py` — `rank_strikes()`'s docstring says "CSP entry
  preference" but the ranking tuple itself (round-strike preference, spread bucket, OI,
  exact spread) isn't actually CSP-specific — confirm this before assuming it needs to
  change; likely just a docstring fix, not a logic change
- `tests/unit/test_find_strike_by_delta.py` — new tests for CC ladder selection
- `src/strategy/cc_overlay_v1.py` — `reentry_script_hint` currently points to
  `find_overlay_strikes.py --overlay-type cc` (the %OTM tool); decide whether this story's
  output should update that hint to the delta-based tool instead (see CC2 below — this
  can't be decided independently of CC2)

**Before any code:**
```
get_code_snippet("find_strike_by_delta.main")           # confirm auto-select loop location
get_code_snippet("DELTA_CANDIDATES")                      # confirm current CSP values
search_code("DEFAULT_STRATEGY")                           # confirm all CSP-specific defaults that need a CC sibling
git log --oneline -10 scripts/lookup/find_strike_by_delta.py
```

**Tests:**
- `test_cc_ladder_used_for_ce_option_type` — `--option-type CE` selects from
  `CC_DELTA_CANDIDATES`, not `DELTA_CANDIDATES`
- `test_csp_ladder_unchanged_for_pe_option_type` — regression guard, PE path untouched
- `test_selected_strike_respects_requested_delta_range` — the auto-selected row's delta
  actually falls near the CC ladder, not CSP's, when `--option-type CE`

**Commit:** `feat(instruments): CC-specific delta candidate ladder, decouple from CSP's`

---

## CC2 — Open decision (needs operator input before CC1 can pick real numbers)

**What `CC_DELTA_CANDIDATES` should actually contain is not a mechanical choice — it's a
live strategy-parameter decision, and there's a real tension to resolve first:**

The CC overlay's current *production* entry path (`find_overlay_strikes.py
--overlay-type cc`) targets a fixed 4% OTM strike — confirmed 2026-07-28 experiment: for
monthly (2026-08-25), 4% OTM lands near strike 24950 (delta ≈0.135, quite far OTM / low
delta). A delta-targeted search at 0.20–0.24 (this session's test run) instead picked strike
24700 (≈2.4% OTM, delta 0.2191) — a **closer, higher-delta, higher-premium, higher-assignment-
risk strike than the current live default.** These are not the same strike and not a rounding
difference — they represent two different entry philosophies (fixed %OTM vs. fixed-delta),
and CC's existing exit rules (`DELTA_STOP` 0.55, `DELTA_WARN` 0.45) were presumably calibrated
against whatever entry delta the %OTM approach has historically produced, not against a
0.20–0.24 entry target.

**Cross-reference (2026-07-28, found while fixing this folder's structure):**
`docs/plan/paper-exit-codification/stories.md` **EC-4** already owns the TIME_STOP
redesign — replacing `days_held >= 21` with a per-strategy/per-expiry-type DTE-remaining
floor in `evaluate_cc`/`evaluate_time_stop_csp`, spawned from a real production bug
(TODOS.md event 68, 2026-06-30: TIME_STOP fired on a 91-DTE-remaining collar call).
**CC2 does not own the TIME_STOP mechanism question — EC-4 does.** CC2 is narrowed to
just the delta-band decision. Two things this cross-reference surfaces that neither
story currently resolves on its own:
- EC-4's example floors are themselves marked "e.g." (≤7 weekly, ≤14 monthly, ≤21
  quarterly) — provisional, not decided, same open-parameter problem CC2 has for delta.
  Two epics independently carrying the same kind of unresolved number.
- EC-4's example monthly floor (14 DTE) sits above CC's existing `DTE_REVIEW` WARN
  threshold (5 DTE) — if EC-4 lands with that example value, `DTE_REVIEW` becomes dead
  code for CC monthly, since TIME_STOP would always fire first. EC-4's spec doesn't
  address this interaction; flag it there before EC-4 ships, not just here.

**Revised recommendation:** CC1/CC3 should depend on **EC-4 having landed**, not just on
CC2 — entering CC closer to the money (a delta-targeted strike) only makes sense once the
exit rule meant to protect that position is measuring DTE-remaining correctly, not
days-held. Calibrating CC1's ladder against the current (wrong) TIME_STOP risks doing the
delta-band tuning twice: once now, again after EC-4 changes what actually triggers the
exit.

**CC2, narrowed — council checkpoint still applies** (load-bearing: changes what strike
real paper trades get entered at; two materially different approaches with different
P&L/assignment-risk profiles; spans strategy design + NSE microstructure). Recommend
template `strategy_parameters`, draft question:

> "CCOverlayV1's current production entry uses a fixed 4% OTM strike via
> find_overlay_strikes.py. A delta-targeted alternative (using the existing
> find_strike_by_delta.py engine, generalized for CC) would instead target a fixed delta
> band (e.g. 0.20–0.30). These produce materially different strikes — 4% OTM is
> ~0.135 delta on the current monthly chain, versus 0.20–0.24 landing 1.6 percentage
> points closer to the money. Should CC entry move to a delta-targeted approach, and if so
> what delta band, given DELTA_STOP fires at 0.55 and DELTA_WARN at 0.45 — is there a
> preferred cushion between entry delta and the stop? (Note: TIME_STOP/DTE_REVIEW
> calibration is EC-4's scope, not this question's — assume EC-4 has landed with
> whatever DTE-remaining floor it settles on before answering.)"

**Until this is answered, CC1 can ship as an experimentation/comparison tool only** (parallel
to `find_overlay_strikes.py`, not replacing it) — `CC_DELTA_CANDIDATES` gets a reasonable
placeholder (e.g. matching the 0.20–0.24 band already validated in this session's test run)
with an explicit code comment that the values are provisional pending this decision, and
`cc_overlay_v1.py`'s `reentry_script_hint` stays pointed at the %OTM tool until the operator
decides otherwise.

**Commit:** none — this is a decision-gate note, not an implementation story. Resolve via
council or direct operator decision, then update `DECISIONS.md` and CC1's ladder values.

---

## CC3 — Automated CC entry script + cron wiring

**Context (2026-07-28, operator directive):** CC entry today is entirely manual — run
`find_overlay_strikes.py --overlay-type cc` (or, once CC1 lands, the delta-targeted
`find_strike_by_delta.py --option-type CE`), eyeball the table, hand-paste the
`record_paper_trade` command. Operator wants this scheduled: entry checked every
Wednesday, gated so it only actually acts the one week that matters (the Wednesday
immediately after the monthly Tuesday expiry — always a Wednesday, not necessarily the
calendar's *last* Wednesday of the month; confirmed with operator this distinction
matters and "day after expiry" is the intended target, not "last calendar Wednesday").

**Model directly on `paper_ic_entry.py`'s existing, working production pattern** — do not
invent a new scheduling mechanism. Confirmed live in today's crontab:
```
30 10 * * 3 ... paper_ic_entry.py --expiry-type monthly --no-dry-run >> logs/ic_monthly.log 2>&1
```
This fires **every Wednesday**, not just the monthly-expiry Wednesday — precision comes
from the script's own idempotency guard (`tests/unit/strategies/ic/test_paper_ic_entry.py
::test_open_position_prevention`: checks `store.get_positions()` for an existing open leg
of the relevant `leg_role`/`strategy_name` first; if found, `sys.exit(1)` before any
subprocess/entry logic runs — confirmed via `mock_subprocess.call_count == 0` in that
test). Three weeks out of four this is a silent no-op; the fourth week it's the real
entry. This sidesteps needing to compute "is today actually the Wednesday after expiry"
in cron syntax at all (cron cannot express that natively) — the guard makes the schedule
correct by omission rather than by precise date math.

**Correction (2026-07-28, same session):** `paper_3track_overlay_entry.py` already reads
`cfg.overlay_type` (`'pp'`/`'cc'`/`'collar'`) from `overlay_entry.yaml` — CC is already a
supported value, not a new argument to add. **Extend this existing script, do not create
a new one.** However, its only existing safety check (`_query_open_call_roles`) is
narrower than it looks: it prevents writing `overlay_cc` and `overlay_collar_call` on the
*same instrument*, not "does an `overlay_cc` position already exist at all for
`paper_nifty_spot`." Unlike `paper_ic_entry.py`, there is **no bootstrap-if-flat
idempotency guard today** — run as-is against a freshly-generated YAML, it will record a
second `overlay_cc` entry even if one is already open. This must be added before weekly
cron is safe; without it, a Wednesday cron would double up positions three weeks out of
four instead of safely no-op'ing the way IC's does.

Full automation also needs a second piece IC's single-script model doesn't require for
CC: today, generating `overlay_entry.yaml` (via `find_overlay_strikes.py`, or CC1's
`find_strike_by_delta.py` once it ships) and recording it (via
`paper_3track_overlay_entry.py`) are two separate manual steps a human chains by hand.
Unattended cron needs something invoking both in sequence — either a thin wrapper script,
or folding YAML generation directly into `paper_3track_overlay_entry.py` so it calls the
selector itself rather than reading a pre-written file.

**Scope extension (2026-07-28, operator directive — "I do not want anything manually,
please make sure the exit happens, I only get notified"):** verified exit itself is
already fully hands-off — `StrategyMonitor._route_event()` dispatches ACTION events
straight to `apply_action()` with no approval step whenever `strategy.auto_execute` and
the event's `auto_execute` payload are both `True` (true for all four of CC's ACTION
signals), so nothing needed there. But re-entry has a silent gap that contradicts
"I only get notified": `CCOverlayV1.apply_action()` only calls `ReEntryMixin._check_reentry()`
when `triggering_signal in ("PROFIT_TARGET", "TIME_STOP")` — a `LOSS_STOP` or `DELTA_STOP`
close gets **no** re-entry eligibility check and **no** notification at all today. This
story must extend that guard to cover all four signals, not just add the cron. The
`ReEntryMixin` gates themselves (DTE ≥14, IVR ≥0.25, no open position) stay as-is and
still apply regardless of *why* the leg closed — a LOSS_STOP close after a sharp rally
should still be allowed to block re-entry if IVR is unfavorable, that gate logic doesn't
need to change, only the trigger condition that decides whether to run the check at all.

**Files to change:**
- `scripts/strategies/three_track/paper_3track_overlay_entry.py` — add the missing
  open-position idempotency guard (mirroring `paper_ic_entry.py`'s pattern: check
  `store.get_positions()` for an existing open `overlay_cc` leg on `paper_nifty_spot`
  before recording; exit without writing if found), and either accept CC1's selector
  output directly or add a wrapper step that calls it before `load_overlay_config()`
- `src/strategy/cc_overlay_v1.py` — `apply_action()`'s re-entry trigger guard currently
  reads `if triggering_signal in ("PROFIT_TARGET", "TIME_STOP")`; widen to all four ACTION
  signals (`PROFIT_TARGET`, `LOSS_STOP`, `DELTA_STOP`, `TIME_STOP`) so every close runs
  the eligibility check and sends a notification — closes the silent gap where
  `LOSS_STOP`/`DELTA_STOP` closes currently produce no re-entry signal at all
- Reuses CC1's `find_strike_by_delta.py --option-type CE` (once CC1 ships) for strike
  selection — **do not** wire this to `find_overlay_strikes.py`'s %OTM path; that stays
  the fallback/manual tool until CC2 resolves which approach is the real production entry
  method
- `tests/unit/paper/test_overlay_entry.py` (existing test file for this script) — add
  idempotency-guard tests alongside the existing `_query_open_call_roles`/collar-pair
  tests
- `tests/unit/strategy/test_cc_overlay_v1.py` — extend `apply_action` tests for the
  widened re-entry trigger guard (see Tests below)
- New cron line (added to crontab directly, not a repo file — confirm with operator
  whether this project keeps a tracked crontab reference file anywhere, e.g.
  `docs/ops/crontab.md`, and update it if so)

**Before any code:**
```
get_code_snippet("paper_3track_overlay_entry.main")       # exact current guard/flow
get_code_snippet("_query_open_call_roles")                # confirm exact scope of the existing (narrower) guard
get_code_snippet("paper_ic_entry.run")                     # exact idempotency-guard structure to mirror
get_code_snippet("test_open_position_prevention")          # exact assertions to replicate for CC
git log --oneline -10 scripts/strategies/three_track/paper_3track_overlay_entry.py
```

**Required behavior:**
- Cron: `* * * 3` (every Wednesday), matching IC's pattern exactly — no attempt at
  "compute the actual post-expiry Wednesday" scheduling logic
- Script checks for an existing open `overlay_cc` position for `paper_nifty_spot` first
  (new guard, mirroring `paper_ic_entry.py`'s pattern — distinct from the existing
  `_query_open_call_roles` same-instrument check, which stays as-is) — if found, exit
  without acting, log at INFO (not WARNING/ERROR — a no-op week is expected behavior, not
  a fault)
- If no open position: run CC1's delta-targeted strike search, apply the same re-entry
  gates `ReEntryMixin` already defines (DTE ≥14, IVR ≥0.25) even though this is a fresh
  bootstrap entry rather than a post-close re-entry — the gates exist to avoid entering
  into a bad IV/DTE environment regardless of *why* the leg is currently flat
- Telegram notification on successful entry (non-fatal, matches `build_notifier()`
  contract) — this is the same notification gap S6 already identifies for base-leg entry;
  CC's version of it can ship independently of S6 rather than waiting for it
- **Hard dependency: this story cannot go live with `--no-dry-run` (or unattended cron)
  until CC1 (ladder) and CC2 (delta-band decision) are both resolved** — until then, ship
  this story with `--dry-run` only, same posture as `find_overlay_strikes.py`/
  `find_strike_by_delta.py` today

**Tests:**
- `test_entry_skipped_when_open_overlay_cc_position_exists` — new idempotency guard,
  mirrors `test_open_position_prevention`; asserts no trade recorded
- `test_entry_proceeds_when_no_open_position`
- `test_existing_query_open_call_roles_guard_unchanged` — regression guard, the
  same-instrument cross-type check still works exactly as today
- `test_reentry_gates_applied_to_bootstrap_entry` — DTE/IVR gates block entry even when
  there's no prior close event to trigger them (bootstrap case, not just post-close)
- `test_dry_run_default_until_cc1_cc2_resolved` — regression guard against accidentally
  shipping `--no-dry-run` as a default before the ladder/band decision lands
- `test_notification_failure_does_not_block_entry` — non-fatal Telegram contract
- `test_reentry_check_called_for_loss_stop` — new: `_check_reentry` now called when
  `triggering_signal == "LOSS_STOP"` (regression test for the gap this story closes)
- `test_reentry_check_called_for_delta_stop` — same for `DELTA_STOP`
- `test_reentry_gates_unchanged_regardless_of_triggering_signal` — DTE/IVR/open-position
  gate logic itself doesn't change, only which signals invoke it — a LOSS_STOP close with
  unfavorable IVR still correctly blocks re-entry, same as a PROFIT_TARGET close would

**Commit:** `feat(strategy): automated CC entry script, Wednesday cron, guarded by open-position check; re-entry check on all four exit signals`

---

## Open risk not resolved by this epic (log in TODOS.md, don't block on it)

Full automation (S4) combined with a single overlay copy (S1–S3) means a bad overlay-roll
decision now affects the *only* protection NiftyBees has, with no human check before execution.
Previously, even a bad decision was triplicated as "one of three data points" and reviewed
before acting. Recommend the first live cycle after S4 ships gets a manual daily review of
`paper_exit_events` for `paper_nifty_spot` regardless of automation — not as a story requirement,
but flagging it here since nothing in S1–S4 builds in a monitoring backstop for the new risk
concentration.
