# 3-Track Consolidation & Automation — Story Specs

> Read `prompt.md` first — it has the Decision Log this whole epic depends on.
> Story order matters: S1 must ship before S3/S4 (dead data would poison the new P&L aggregation).
> S0 (docs) can happen anytime but should land no later than immediately after S4, since stale
> docs actively mislead the next session per CLAUDE.md Rule 0.

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

## S3 — Single-copy P&L aggregation in snapshot + comparison reporting

**Context:** `paper_3track_snapshot.py` currently writes a `paper_leg_snapshots` row per
`(strategy_name, leg_role)` including overlay roles for all three strategies. Post-S1/S2 there's
only ever one live overlay copy (on spot), but the 3-track *comparison* view (whatever currently
renders `docs/viz/3track_comparison.html` / any Telegram EOD report) needs to keep showing
Futures and Proxy as comparably-protected for the comparison to mean anything — otherwise you're
comparing a hedged NiftyBees against two naked directional bets, which isn't the RQ1 question
being asked (RQ1 is base-instrument efficiency, not "which is safest unhedged").

**Decision needed at implementation time (not deferred to operator — this is a reporting-math
call within the confirmed scope, flag if genuinely ambiguous):** for comparison purposes, Futures
and Proxy P&L should be shown two ways — (a) raw/unprotected, and (b) a clearly-labeled
*synthetic* attribution where the NiftyBees overlay's P&L-per-NEE-unit is applied notionally to
Futures/Proxy's NEE-equivalent size, so the operator can eyeball "if this base instrument had
carried the same protection, roughly what would its curve look like" — without creating any new
real DB rows for Futures/Proxy (that would recreate the S1 problem). This synthetic column must
be visually/textually distinguished from real P&L everywhere it appears (report headers, viz
labels) — do not let a synthetic number get mistaken for a tradeable position's actual P&L.

**Files to change:**
- `scripts/strategies/three_track/paper_3track_snapshot.py` — leg aggregation query, synthetic
  overlay-attribution calculation, report formatting
- `scripts/dev/generate_3track_viz.py` — synthetic column in `docs/viz/3track_comparison.html`
- `tests/unit/scripts/test_paper_3track_snapshot_period.py` and siblings

**Before any code:**
```
get_code_snippet("paper_3track_snapshot")     # or trace_path if too large for one snippet
search_code("paper_leg_snapshots")
search_code("underlying_price")               # NEE sizing math already exists somewhere, reuse it
git log --oneline -10 scripts/strategies/three_track/paper_3track_snapshot.py
```

**Tests:**
- `test_niftybees_pnl_includes_overlay_legs` — real P&L, base + overlay
- `test_futures_proxy_pnl_excludes_overlay` — real P&L, base only
- `test_synthetic_attribution_scales_by_nee` — synthetic column math against a known NEE ratio
- `test_synthetic_column_labeled_distinctly` — report/viz output contains an explicit "synthetic"
  / "modeled" marker, not just a bare number indistinguishable from real P&L

**Commit:** `feat(paper): 3-track snapshot uses single NiftyBees overlay copy, synthetic attribution for Futures/Proxy comparison`

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

## S0 — Documentation and decision-log updates

**Context:** `docs/instructions/3track.md` and `docs/strategies/nifty_track_comparison_v1.md`
still describe RQ2 (overlay-per-base comparison) as live research. Once S1–S4 ship, those docs
actively mislead — CLAUDE.md Rule 0 tells every future session to trust `git log` and the graph
over stale docs, but nothing should be relying on that safety net when a one-line doc fix
prevents the confusion entirely.

**Files to change:**
- `docs/instructions/3track.md` — rewrite Overlay Menu table: single column (NiftyBees only),
  remove Futures/Proxy overlay rows, note synthetic-attribution reporting from S3
- `docs/strategies/nifty_track_comparison_v1.md` — retire RQ2 explicitly, don't just delete it
  silently (future readers should know it was tried and retired, not that it was never asked)
- `CONTEXT.md` — update `NiftyTrackComparisonV1` description (`auto_execute=False` → `True`),
  update the module tree entry for any new migration script from S1
- `DECISIONS.md` — two new rows: RQ2 retirement (date, "operator directive, no council run"),
  automation flip (date, "operator directive, council checkpoint explicitly waived by operator")
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
