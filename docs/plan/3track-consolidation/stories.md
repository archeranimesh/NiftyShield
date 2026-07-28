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

## Open risk not resolved by this epic (log in TODOS.md, don't block on it)

Full automation (S4) combined with a single overlay copy (S1–S3) means a bad overlay-roll
decision now affects the *only* protection NiftyBees has, with no human check before execution.
Previously, even a bad decision was triplicated as "one of three data points" and reviewed
before acting. Recommend the first live cycle after S4 ships gets a manual daily review of
`paper_exit_events` for `paper_nifty_spot` regardless of automation — not as a story requirement,
but flagging it here since nothing in S1–S4 builds in a monitoring backstop for the new risk
concentration.
