# 3-Track Consolidation & Automation — Story Specs

> Read `prompt.md` first — it has the epic's Decision Log. Find your task ID in
> `docs/plan/3track-consolidation/tasks.md`'s checklist, then jump straight to that heading
> below (`##`/`###` headings match task IDs exactly, e.g. `## S5`, `### S3r`). Only open/pending
> stories live in this file — completed ones (S1r, S2r, S3, plus the original superseded S1/S2)
> are archived in full at `docs/archive/plan/3track-consolidation-completed.md`, referenced from
> S3r's recap below where their reasoning is still load-bearing.

> **Story order:** S3r, S5, S7 are independent — any can start immediately. **S4** (overlay
> automation) needs S1r+S2r landed first (done) plus S3r ideally in place so automation isn't
> flying blind on coverage. **S6** needs S2r+S5 landed (S2r done; S5 pending) and is best
> sequenced after S4. **S0** (docs) trails everything. **S8** needs **S7** landed first (reads
> S7's leg-role fix). **S9** needs **S3 and S8** landed first (reads their output tables only).
> CC1/PP1/Collar1 (delta ladders) → CC2/PP2/Collar2 (decision gates) → CC3/PP3/Collar3
> (automated entry) is a strict per-thread chain; PP1a and the re-entry-gap halves of
> CC3/PP3/Collar3 can each ship independently/first. See each story's own "Depends on" line for
> specifics — do not infer ordering by story number alone.

---

## S3r — Per-track coverage/P&L comparison, computed at query time

**Context recap (full decision history archived in
`docs/archive/plan/3track-consolidation-completed.md`'s REVISION section — S1r/S2r, both
shipped 2026-07-29):** overlay legs now live in a track-independent `paper_nifty_overlay`
strategy_name (S1r) with no track-ownership entry blocks (S2r). Per-track overlay coverage/P&L
must be computed **at query time only**, never via duplicate trade rows per track (that was
RQ2's mistake). Qty/lot values are **not** normalized or resized — Spot's 5735 ETF units,
Futures' 65-qty (1 lot), Proxy's 65-qty (1 lot) are used as-is; capital parity (~15L margin at
entry, confirmed by operator) is what makes the three tracks P&L-comparable, not exposure
parity. Exposure (effective Nifty units) still differs per track — ETF ≈1x, Futures levered via
SPAN margin, DITM call ≈ delta <1x — so overlay *coverage ratio* per track is a real per-track
calculation, not a flat lookup.

**Problem:** with overlay re-homed to its own namespace (S1r), there is no existing code path that
answers "how much protection does this overlay give Spot / Futures / Proxy right now" — that
comparison was never built under the RQ2 design (which faked it by physical duplication) and isn't
built under S3's base-only snapshot either (S3 deliberately excludes overlay). This story is the
actual query-time join the operator is asking for.

**Design constraint (confirmed 2026-07-29):** coverage is computed as **effective Nifty-point
exposure**, not raw qty, because the three tracks are capital-equivalent (~15L margin) but not
exposure-equivalent:
- Spot: `qty * 1.0` (ETF tracks Nifty ≈1:1)
- Futures: `qty * lot_multiplier * 1.0` delta, but levered relative to margin — flag notional via
  `paper_margin_snapshots` rather than assuming a fixed 15L, since SPAN margin drifts intraday/day-to-day
- Proxy (DITM call): `qty * current_delta` — delta must be pulled live (Greeks snapshot), not
  assumed ≈1, since "DITM" drifts toward ATM as spot moves and delta is time-varying

Overlay coverage % for a given track = `overlay_position_delta_equivalent / track_effective_nifty_units`.

**Files to change:**
- New query function, likely `src/portfolio/overlay_coverage.py` or a method on the existing
  tracker — confirm placement via graph, do not assume a new file is needed if
  `PortfolioTracker`/`summary.py` already has an analogous per-strategy join pattern
- Reuses `paper_margin_snapshots` (existing table, confirmed present) for Futures notional/margin,
  and whatever Greeks-snapshot source CC1/PP1/Collar1 already read delta from (confirm — do not
  duplicate a second delta-fetch path)
- `tests/unit/` — coverage-ratio tests per track type, including a delta-drift case for Proxy
  (DITM call delta moving from ~0.95 toward ~0.7 as spot falls, confirming coverage % recalculates
  rather than using entry-time delta)

**Before any code:**
```
get_code_snippet("PortfolioTracker")            # confirm existing per-strategy join pattern
search_code("paper_margin_snapshots")           # confirm schema/columns for futures notional
search_graph("delta")                            # confirm which Greeks source is canonical (avoid a second path)
```

**Commit:** `feat(portfolio): query-time overlay coverage ratio per track, no duplicate rows`

**Note:** CC1/PP1/Collar1 (delta-targeted strike selection stories, below) are unaffected by this
revision — they govern *which strike* an overlay leg enters at, orthogonal to *which track owns
the leg* (now: none, per S1r). No changes needed to those stories.

**Council checkpoint — waived, operator override (2026-07-29):** this revision qualifies under
CLAUDE.md Step 2b, but the operator explicitly declined a council discussion and directed override.
Sign-off recorded in `DECISIONS.md` (round 5 entry) in lieu of a council pass. S3r is cleared to
proceed to Step 3 (state plan, get go-ahead) without further gating.

---

## S4 — Full automation of NiftyTrackComparisonV1

**Context:** `NiftyTrackComparisonV1.auto_execute` is currently `False` by explicit prior design
(CONTEXT.md: "all overlay and Proxy actions require human confirmation") — every other overlay
strategy in the codebase (`CCOverlayV1`, `PPOverlayV1`, `CollarOverlayV1`) already runs
`auto_execute=True`. Operator has confirmed (prompt.md Decision Log #3) they want this flipped,
council-checkpoint explicitly skipped at their instruction.

**This story ships after S1r/S2r (done) and against the already-cleaned single-copy overlay
data** — flipping automation on top of the prior triplicated/buggy state would let a bot act on
the CC state bug (S1b) or the PP booking gap before those were fixed.

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
- All existing hard blocks (proxy delta signals, roll-base-first guard) remain enforced —
  automation removes the human approval step, not the safety gates. This is the single most
  important invariant of this story: automating the wrong action faster is strictly worse than
  the current manual-approval state, not neutral.
- Confirm `close_ic_legs()`-style persistence discipline applies here too — TODOS.md already
  documents a real incident (2026-07-15) where auto-execute actions were computed but never
  written to `paper_trades` for IC strategies. Explicitly test that every auto-executed action
  in this strategy actually persists.

**Tests:**
- `test_auto_execute_flag_is_true`
- `test_roll_eligible_action_dispatches_without_approval`
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
contradiction — see DECISIONS.md "round 3" entry):**
- **All three tracks are perpetual, single-entry positions — there is no "cycle" that ever closes
  and no recurring re-entry.** NiftyBees is never closed. Futures and DITM "roll" means exactly
  "close current-month/current-band contract, open next-month/next-band contract" (S5) — it is
  contract maintenance on one continuous position, not a new cycle.
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
- Message format matches the codebase's existing convention: plain text, `<b>`/`<code>` HTML tags,
  emoji prefix per event type (suggest: 🔄 for roll, 🟢 for new entry, matching ✅/⚠️ used elsewhere).
  Confirm which rendering path `TelegramNotifier.send()` actually uses for these new call sites
  before assuming.
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
still describe RQ2 (overlay-per-base comparison) as live research. Once S3r–S6 ship, those docs
actively mislead — CLAUDE.md Rule 0 tells every future session to trust `git log` and the graph
over stale docs, but nothing should be relying on that safety net when a one-line doc fix
prevents the confusion entirely.

**Files to change:**
- `docs/instructions/3track.md` — rewrite Overlay Menu table: single column (NiftyBees only),
  remove Futures/Proxy overlay rows; note the daily base-only comparison snapshot (S3, shipped) is
  computed strictly from base legs, overlay P&L is a fully separate, non-blended report; note S5's
  automated base-leg roll cadence (DTE<20 trigger, band preference, liquidity gate behavior); note
  S6's cycle-entry cadence and full unattended pipeline, with Telegram as the sole visibility layer
- `docs/strategies/nifty_track_comparison_v1.md` — retire RQ2 explicitly, don't just delete it
  silently (future readers should know it was tried and retired, not that it was never asked)
- `CONTEXT.md` — update `NiftyTrackComparisonV1` description (`auto_execute=False` → `True`),
  add module tree entries for S5's roll script and S6's entry-trigger + notification wiring
- `DECISIONS.md` — rows for: RQ2 retirement, automation flip, S5's roll trigger/liquidity-gate
  design, and S6's full-automation + notification-on-every-trade decision
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

**Resolved (2026-08-01, direct operator decision, no council pass):** delta band **0.18–0.20**,
matching CC1's existing `CC_DELTA_CANDIDATES` values as-is — no new number needed calibration.
OI is the liquidity gate (already what `rank_strikes()`/`_apply_liquidity_gate` enforce); no
separate round-strike rule at this decision's level — round-500 preference is CC4's scope, a
refinement *within* whatever strike this band selects, not part of CC2's own resolution. Path
to this answer: operator initially wanted more analysis (BS-calibrated delta estimate, then
confirmed against the live chain — 1% OTM ≈0.39 delta, judged too little DELTA_WARN/STOP
cushion), then converged on 0.20 delta with a preference for round strikes; the round-strike
half of that was split out into CC4 rather than folded into CC2's band decision. Note this band
converges with today's live 4% OTM default on the chain checked this session (both landed on
strike 25000) — so this resolution is better read as "confirm and make delta-native what's
already the production default," not a behavior change in itself. `CC_DELTA_CANDIDATES`'s code
comment (`scripts/lookup/find_strike_by_delta.py`) updated provisional → confirmed accordingly.
**Still blocked on EC-5** (`docs/plan/paper-exit-codification`, CC's TIME_STOP/DTE_REVIEW
collapse) landing before CC3 can go `--no-dry-run` — this resolution does not itself clear that
dependency.

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

## CC4 — Round-500 strike preference for CC ranking, with liquidity-aware fallback to round-100

**Context (2026-08-01, operator directive, arising from CC2 analysis session):** while stress-
testing CC2's delta-band question, operator noted that round-₹500 strikes (24500, 25000, 25500…)
carry materially deeper OI than neighboring round-100 strikes on the live chain checked this
session (strike 25000: 5.4M OI vs. strike 24800's 2.2M — 2.5x, both "round-100" under
`rank_strikes()`'s current tier-1 test, but only 25000 is round-500). `rank_strikes()`
(`src/instruments/strike_selector.py:180-206`) already has a round-100 preference baked into its
ranking tuple (`is_non_round = strike % 100 != 0`, tier 1 of 4), but it's **shared and
side-agnostic** — 12 inbound callers per the graph (`paper_ic_entry_v2`, `csp_roll_executor`,
`record_paper_trade`, `paper_3track_snapshot`, plus CC1/CC3's use via `find_strike_by_delta.py`).
Changing its default tier would silently change CSP/IC/PP strike selection too — out of scope
here, this story is CC-only.

**Design, corrected mid-discussion from an initial hard-filter proposal:** not a hard filter
(exclude non-round-500 strikes entirely) — operator wants round-500 preferred in ranking, with
an explicit, liquidity-aware fallback: if the round-500 candidate(s) inside the active delta
window (CC1's ±0.02 band around the current ladder rung, e.g. 0.18–0.22 for a 0.20 target) don't
clear a "sufficient cushion" bar on liquidity/OI (or any other parameter — spread, delta
proximity — worth checking), fall back to the best round-100 strike in-window instead, chosen by
the existing spread/OI ranking. **Whenever the fallback path is taken, log a line explaining
why** — which parameter(s) failed to clear cushion on the round-500 candidate(s) — so a human
reviewing `logs/cc_option.log` (or wherever this script logs) can see when and why round-500 was
skipped, not just which strike got picked.

**Open design questions to resolve before implementation (do not guess — confirm with operator
or via `get_code_snippet`/chain inspection at implementation time):**
- What exactly defines "sufficient cushion" on liquidity/OI for a round-500 candidate to be
  accepted over falling back to round-100? A hard OI floor? A relative-to-round-100-candidate
  ratio (e.g., round-500 OI must be ≥ some fraction of the best round-100 OI in-window)? The
  session that spawned this story didn't pin a number — needs a decision, possibly its own
  mini-decision-gate rather than a number picked from first principles.
- "any other parameter" (operator's phrasing) is open — spread width and delta-proximity-to-
  target are candidates worth checking in addition to OI before deciding round-500 is unsuitable.
- **Ranking within the round-500 tier itself (2026-08-01, operator example):** when multiple
  round-500 candidates exist, delta-proximity-to-target wins over raw OI — operator's worked
  example: choosing between strike 25500 (delta 0.1902, close to the 0.20 rung) and strike 25000
  (delta 0.3489, far from any CC1 ladder target) prefers 25500 despite both being round-500,
  because 0.3489 isn't a real fit for the ladder regardless of round-strike status. In practice
  this mostly falls out of the existing ±0.02 delta-window filter already applied before ranking
  (a 0.3489-delta strike wouldn't survive that filter to begin with) — but confirm the round-500
  tier's internal ordering is delta-proximity-first, OI/spread as tiebreaker, not OI-first.
- **Cross-expiry scope (2026-08-01, flagged from the same example — operator's example strike was
  on the quarterly expiry, not monthly):** does the round-500 fallback search only within the
  currently-targeted expiry (monthly, per CC1/CC3's cadence), or is reaching to quarterly/yearly
  for a round-500 fit intentional? Reaching cross-expiry sidesteps CC3's Wednesday-post-monthly-
  expiry cron assumption and changes DTE/theta/roll economics materially — **not yet confirmed
  with operator, do not assume cross-expiry search is in scope.** Default assumption until
  answered: round-500 preference applies within the targeted expiry only; if no round-500 strike
  clears cushion on that expiry, fall back to round-100 on the *same* expiry, not to another
  expiry's round-500 strike.
  **Re-entry-guard concern resolved (2026-08-01):** operator confirmed CC3's idempotency guard is
  presence-based (checks for any open `overlay_cc` leg on `paper_nifty_spot`, not expiry-scoped)
  — same pattern as IC's `test_open_position_prevention` — so cross-expiry entry would not cause
  double-entry on later Wednesdays regardless of which expiry got picked. **Still open:** the
  economics concern — a quarterly-dated CC leg has materially different DTE/theta/roll behavior
  than CC1's exit thresholds (`DELTA_STOP`/`DELTA_WARN`, TIME_STOP pending EC-4) were reasoned
  about assuming. Entry-guard mechanics are no longer a blocker to answering the cross-expiry
  question; the economics question is.
- Does this belong in `rank_strikes()` as an optional `round_to`/preference parameter (keeps the
  ranking logic centralized, but touches a 12-caller shared function's signature), or as a
  CC-local wrapper in `find_strike_by_delta.py` that doesn't touch the shared function at all
  (smaller blast radius, some duplication of ranking logic)? Lean toward the CC-local wrapper
  given the shared function's caller count, but confirm at implementation time rather than
  assuming.

**Related (2026-08-01):** while stress-testing CC's exit thresholds against these same round-500
candidates, operator found `days_held >= 21` TIME_STOP would misfire on a quarterly-dated CC
(force-close at 38 DTE remaining) — spawned a cross-epic decision, EC-5 in
`docs/plan/paper-exit-codification`, collapsing CC's TIME_STOP/DTE_REVIEW into one DTE<=5
auto-close. See this folder's `tasks.md` CC5 entry (pointer only, implementation lives in
`paper-exit-codification`). Relevant to CC4 because it directly informs the still-open
cross-expiry economics question above: a DTE-based close is safe regardless of which expiry
CC4's round-500 fallback lands on, which removes one (but not all — delta-risk-over-time is
still open) of the concerns about letting CC4 reach into quarterly/yearly expiries.

**Depends on:** CC1 (ladder must exist first — this story refines *which* strike CC1's ladder
picks, doesn't change the ladder itself); narrows the same delta window CC1 already searches.
Like CC1, results here stay provisional until CC2 resolves — this story doesn't change the
CC2 dependency, it only affects strike selection *within* whatever delta band CC2 eventually
confirms.

**Files to change (tentative, confirm at implementation time per open question above):**
- `scripts/lookup/find_strike_by_delta.py` — CC branch of the candidate-selection loop
- Possibly `src/instruments/strike_selector.py` if the round-500 preference is added as a
  `rank_strikes()` parameter rather than a script-local wrapper
- Log line for the fallback-reason case (confirm target log file/logger per `LOGGING.md`
  standard — this project's canonical logging doc, mandatory reading before adding any
  `logger.*()` call)

**Tests (mandatory, no network):**
- Round-500 candidate present with sufficient cushion → selected over round-100 alternatives
  in the same delta window
- Round-500 candidate present but fails the cushion bar (whatever it's defined as) → falls back
  to best round-100 strike, and a log line is emitted explaining which parameter failed
- No round-500 candidate at all in-window → falls back cleanly, same logging behavior
- Regression: CSP/IC/PP paths through `rank_strikes()` unaffected (if implemented as a shared
  parameter, confirm default preserves today's round-100-only behavior for all non-CC callers)

**Resolved + implemented (2026-08-01, direct operator decision, no council pass):** cushion bar
is the existing `_apply_liquidity_gate()` — no separate OI/spread comparison ratio between
round-500 and round-100 tiers. No additional spread/delta-proximity gate beyond what already
runs upstream (spread via the liquidity gate, delta-proximity via the existing ±0.02 candidate
window). Cross-expiry reach is allowed — a round-500 strike on quarterly/yearly can win over a
round-100 strike on the nearer expiry; confirmed this was already inherent in `main()`'s
candidate loop (pools all resolved expiries before ranking/gating), not new behavior introduced
by this story. Placement: CC-local `_reorder_cc_round500_first()` in
`scripts/lookup/find_strike_by_delta.py`, not a `rank_strikes()` parameter — keeps the 12-caller
shared function untouched. **Known accepted risk, unresolved by this story:** cross-expiry reach
can select a leg whose DTE/theta/roll economics diverge from what CC's exit thresholds assume;
`TIME_STOP` is still `days_held >= 21` until EC-5 lands. See DECISIONS.md 2026-08-01 CC4 entry
for full implementation detail.

**Commit:** `feat(lookup): CC round-500 strike preference with liquidity-gated round-100 fallback`

---

## PP1 — Per-strategy delta candidate ladder for PP, extend `find_strike_by_delta.py`

**Context (added 2026-07-28, mirrors CC1):** `PPOverlayV1.reentry_script_hint` points at
`find_overlay_strikes.py --overlay-type pp` (fixed %OTM selection), same tool CC used before
CC1. `find_strike_by_delta.py`'s auto-select loop is CSP-only (`DELTA_CANDIDATES`); CC1 adds a
CE-side ladder. This story adds the PE-long-protection ladder so PP gets the same
delta-targeted option CC does, without disturbing the CSP short-put path.

**Confirmed via code read (2026-07-28), not memory — corrects a stale CONTEXT.md claim:**
`PPOverlayV1` already inherits `ReEntryMixin` (`class PPOverlayV1(ReEntryMixin)`,
`src/strategy/pp_overlay_v1.py:58`) and calls `self._check_reentry(...)` from `apply_action`.
It overrides `_ivr_passes()` for its inverted gate (`reentry_ivr_threshold=0.60`, blocks when
IVR is *above* threshold — the opposite of CSP/CC's "don't sell premium when IV is cheap"
logic, here it's "don't buy protection right after a vol spike"). It does **not** need a custom
`_evaluate_pp_reentry` method — that CONTEXT.md description is out of date and should be
corrected as part of this story's S0-equivalent doc pass, not carried forward.

**Problem:** PP is long options (buying a put for protection), not short — its delta ladder
target is conceptually different from both CSP's short-put ladder and CC1's CE ladder: PP wants
a strike deep enough OTM to be cheap, but close enough to the money that it actually pays out in
a crash. `find_strike_by_delta.py` has no PE-long-protection candidate set today; the CSP
ladder assumes short-premium selection criteria (round-strike preference, spread/OI ranking
tuned for entry-credit optimization) that don't obviously transfer to a long-debit purchase.

**Scope note (2026-07-28, operator directive):** the original PP1 draft also raised a
PE-ambiguity/ladder-collision concern (bare `--option-type PE` can't distinguish CSP from PP,
both fall through to `DELTA_CANDIDATES` today). Operator has scoped that out for now — PP is
being evaluated independently of CSP, not run live alongside it against the same instrument, so
the collision risk doesn't apply yet. That concern is **not deleted, just deferred** — re-open it
before PP and CSP are ever both automated/live simultaneously (see S4/CC3/PP3's "full automation"
direction, where this could resurface). The action-direction bug found via live-testing this
session (see **PP1a**, split out separately) is unrelated to this deferral and stays in scope.

**Files to change:**
- `scripts/lookup/find_strike_by_delta.py` — add `PP_DELTA_CANDIDATES`; ladder selection keyed
  off `--option-type PE` + an explicit `--overlay-type pp` flag (PE is ambiguous on its own —
  CSP is also PE-side; do not infer PP vs. CSP from option-type alone, require the explicit flag)
- `src/instruments/strike_selector.py` — confirm (don't assume) whether `rank_strikes()`'s
  spread/OI ranking is appropriate unchanged for a long-debit purchase, or whether PP needs its
  own ranking tuple (e.g., liquidity may matter more than spread tightness for an infrequently-
  touched protective leg) — this is a real open question, not a mechanical copy from CC1
- `tests/unit/test_find_strike_by_delta.py` — PP ladder selection tests
- `src/strategy/pp_overlay_v1.py` — `reentry_script_hint` update decision deferred to PP2
  (same dependency shape as CC1/CC2/`cc_overlay_v1.py`'s hint)

**Before any code:**
```
get_code_snippet("PPOverlayV1")                          # already read this session — inherits ReEntryMixin, confirmed
get_code_snippet("find_strike_by_delta.main")
get_code_snippet("DELTA_CANDIDATES")
get_code_snippet("CC_DELTA_CANDIDATES")                   # once CC1 lands — mirror its flag/selection pattern, don't diverge stylistically
search_code("rank_strikes")
git log --oneline -10 scripts/lookup/find_strike_by_delta.py
```

**Tests:**
- `test_pp_ladder_used_for_pe_option_type_with_overlay_flag` — `--option-type PE --overlay-type pp`
  selects from `PP_DELTA_CANDIDATES`, not `DELTA_CANDIDATES`
- `test_csp_ladder_unchanged_for_pe_without_overlay_flag` — regression guard, bare `--option-type PE`
  (CSP's existing invocation shape) is untouched
- `test_pe_without_overlay_flag_does_not_silently_pick_pp_ladder` — explicit guard against the
  ambiguity this story exists to resolve (PE alone must never imply PP)

**Commit:** `feat(instruments): PP-specific delta candidate ladder, decouple PE-long from CSP's PE-short`

---

## PP1a — Fix `--action` defaulting to SELL for `paper_protective_put_v1` (confirmed live bug, 2026-07-28)

**Confirmed via live run this session** — `python -m scripts.lookup.find_strike_by_delta
--option-type PE --delta-min 0.20 --delta-max 0.35 --strategy paper_protective_put_v1`
generated `record_paper_trade --strategy paper_protective_put_v1 --key "NSE_FO|61500" --price
110.85 --no-dry-run` with **no `--action` in the printed command**, because the script's
default `--action` is `SELL` (`scripts/lookup/find_strike_by_delta.py`, `_parse_args`,
`default="SELL"`). Protective put is a long-put (protection-buying) strategy — a `SELL PE`
recorded under `paper_protective_put_v1` is not a delta mismatch, it's the wrong trade
direction entirely: a naked short put booked under a strategy name that implies protection.

**Scope explicitly narrowed (2026-07-28, operator directive):** evaluate PP independently of
CSP for now — ignore the PE-ambiguity/ladder-collision concern PP1 originally raised (CSP vs.
PP both resolving through the same `DELTA_CANDIDATES` fallback because `--option-type PE`
alone doesn't distinguish them). That concern only matters if both strategies are live
simultaneously against the same instrument; not the case today. **This story is action-direction
only, decoupled from PP1's ladder-selection scope.**

**Required behavior:**
- When `--strategy` resolves to `STRATEGY_PP_OVERLAY` (`"paper_protective_put_v1"`), `--action`
  must resolve to `BUY` automatically — no manual `--action BUY` flag should be required to get
  the correct trade direction, since this script's whole purpose (per S6/CC3/PP3) is eventually
  feeding an automated entry path with no human eyeballing the printed command first.
  Concretely: a caller must not be able to record a `SELL` under this strategy at all, whether
  by omission (currently the actual bug) or by explicit override (`--action SELL` passed by
  mistake) — treat "explicit SELL for PP" as a hard error, not just "let the default handle it,"
  since a human/script that explicitly gets this wrong is exactly the failure mode a delta ladder
  fix doesn't protect against.
- Introduce a small pure, importable, unit-testable resolver (e.g. `_resolve_action(strategy,
  action) -> str`) rather than inlining the branch into `main()` — matches this file's existing
  pattern of keeping `main()` thin and pushing logic into testable helpers (`_infer_leg`,
  `filter_strikes_by_delta`, `rank_strikes` are all already factored this way).
- `--action`'s argparse default likely needs to move from a static `"SELL"` to `None`, with the
  strategy-aware resolution happening after `--track`'s `--strategy` shortcut is applied (so
  `--track spot --strategy paper_protective_put_v1`-style overrides are still caught).

**Files to change:**
- `scripts/lookup/find_strike_by_delta.py` — new `_resolve_action()` helper, `--action` default
  change, wire into `main()` before `build_record_command()` is called
- `tests/unit/test_find_strike_by_delta.py` — new tests, following this file's existing
  docstring-table convention (see the numbered test list at the top of the file)

**Before any code:**
```
get_code_snippet("_infer_leg")            # existing pattern for a small pure helper this mirrors
get_code_snippet("build_record_command")  # confirm where --action currently flows into the printed command
search_code("STRATEGY_PP_OVERLAY")        # confirm the exact constant/import path (src/paper/constants.py)
git log --oneline -10 scripts/lookup/find_strike_by_delta.py
```

**Tests:**
- `test_resolve_action_defaults_buy_for_pp_strategy` — `_resolve_action("paper_protective_put_v1", None)` → `"BUY"`
- `test_resolve_action_rejects_explicit_sell_for_pp_strategy` — `_resolve_action("paper_protective_put_v1", "SELL")` raises
- `test_resolve_action_unchanged_for_non_pp_strategies` — regression guard, CSP/CC/other strategies keep the existing `SELL` default when `action=None`, and still accept an explicit `BUY`/`SELL` override
- `test_resolve_action_explicit_buy_for_pp_is_a_noop` — passing `--action BUY` explicitly for PP still resolves to `BUY` (not an error, just redundant)

**Commit:** `fix(lookup): find_strike_by_delta.py defaults/enforces BUY for paper_protective_put_v1`

---

## PP2 — Open decision: does PP move off fixed %OTM to delta-targeted entry?

**Mirrors CC2's shape, narrower stakes.** Unlike CC (where %OTM vs. delta-targeted changes
assignment risk and premium collected), PP is a debit purchase — the tradeoff is protection
cost vs. protection responsiveness (a closer-to-the-money put costs more but pays out earlier
in a drawdown; a further OTM put is cheap tail insurance that may not trigger until a severe
move). This is a real strategy-parameter decision, not a mechanical follow-on from PP1.

**Council checkpoint applies** (load-bearing — changes the cost/response profile of the only
downside protection in the pipeline post-S1r/S2r; two defensible approaches; spans strategy
design + NSE options microstructure). Recommend template `strategy_parameters`, draft question:

> "PPOverlayV1's current production entry uses `find_overlay_strikes.py --overlay-type pp`
> (fixed %OTM). A delta-targeted alternative (PP1's `PP_DELTA_CANDIDATES` via
> `find_strike_by_delta.py`) would target a fixed delta band instead. Given PP's exit rules
> (`CRASH_MONETIZE` at delta ≤ -0.80 or 5× debit, `ROLL_ELIGIBLE` at low DTE) were calibrated
> against whatever entry delta the %OTM approach has historically produced, and given PP's
> re-entry IVR gate is inverted (blocks re-entry when IVR is high, unlike CSP/CC) — should PP
> also move to delta-targeted entry, and if so what band? Note PP is long options: the tradeoff
> is protection cost (cheaper, further OTM) vs. protection responsiveness (pricier, closer to
> the money, pays out sooner in a drawdown) — this is a different axis than CC's
> premium-vs-assignment-risk tradeoff, don't reuse CC2's answer by analogy."

**Until answered:** PP1 ships as an experimentation/comparison tool only, `PP_DELTA_CANDIDATES`
provisional, `reentry_script_hint` stays pointed at the %OTM tool.

**Commit:** none — decision-gate note. Resolve via council or operator, then update
`DECISIONS.md` and PP1's ladder values.

---

**RESOLVED (2026-08-03, direct operator decision, no council pass despite the council-checkpoint
recommendation above):** 0.15 delta, monthly cadence. Operator reviewed a live chain pull
(`logs/pp_option.log`, spot ₹24,562.10) cross-referencing PP1's whole ladder (0.15/0.20/0.25 →
strikes 23,800/24,100/24,200, premiums ₹49.35/87.05/105.85). 0.20-0.25 rejected as pricing PP
closer to a recurring-strangle cost than insurance (7-10x the current ~9%-OTM premium annually);
current 9% OTM rejected as functionally decorative for this book (≈0.03 delta, priced to almost
never pay — fine for pure black-swan cover, not fit for purpose when PP's actual job is protecting
a pledged-collateral margin cushion that gets stressed well before crash-level moves).

**Quarterly cadence explicitly rejected, not just deprioritized** — evaluated head-to-head against
a quarterly-equivalent candidate (23,300 strike, 5.1% OTM, ₹71.25, `NSE_FO|73924`, delta -0.1135).
A 5%-in-one-quarter move lands spot at 23,334 — *above* the 23,300 strike — so the quarterly put
would expire worthless while the monthly 23,800-strike put nets ≈₹27k/lot on the identical 5% move
inside a single month. Quarterly cadence structurally under-protects against a real but partial
intra-period drawdown that recovers before the (infrequent) roll date; monthly re-pricing doesn't
have that blind spot. Annual cost comparison (₹38,493 monthly-12x vs. ₹18,525 quarterly-4x) was
explicitly not the deciding factor — the quarterly plan's cheapness reflects doing the job less
often, not doing it more efficiently.

**Empirical grounding (operator-supplied data, not requested by Claude but decisive in framing the
cost):** 26 years of Nifty monthly returns (2000–2026 YTD, 307 months) show single-month declines
≥5% occurred 36 times (~11.7%, ~1.4×/year), ≥10% ten times (~once/2.6yr), ≥15% six times
(~once/4.3yr), ≥20% twice (2008, 2020 — ~once/13yr). This confirms a 3.1%-OTM monthly put sits
below a recurring, not rare, event threshold — the ≈₹38,493/year premium is better understood as
budgeted annual insurance against an expected event, not tail-cover premium that's "supposed to"
mostly expire worthless.

**Companion items surfaced, not resolved here:**
1. `CRASH_MONETIZE`'s delta ≤ -0.80 threshold was calibrated against whatever entry delta the old
   ~9%-OTM (≈0.03 delta) approach produced; a 0.15-delta entry reaches -0.80 on a materially
   smaller move. Whether/how to recalibrate is folded into **PP4** below, not decided here.
2. PP3's cadence question (was open, "confirm with operator") is now resolved as part of this
   discussion, not deferred to PP3's own session — see PP3's updated spec below and its
   `tasks.md` entry: daily check, same-day roll re-entry, unconditional IVR-gate bypass for the
   routine `ROLL_PP` path specifically (does not extend to `MONETIZE_PP`-triggered re-entry, see
   PP4).

**Action:** `PP_DELTA_CANDIDATES`'s inline comment: provisional → confirmed (0.15). No code
change beyond the comment — PP1 already shipped the ladder values as-is.

**Full analysis trail:** conversation-derived, not a separate doc — key numbers reproduced above
so this resolution is self-contained without needing to replay the session.

---

## PP3 — Fix silent re-entry gap on ROLL_PP + automated PP entry script + cron

**Context (2026-07-28, same "I only get notified" directive that drove CC3):** Two independent
gaps, bundled here because both are re-entry/automation completeness gaps on the same strategy.

**Gap 1 — confirmed via code read, `src/strategy/pp_overlay_v1.py` `apply_action()`:**
```python
if action.action_type == "MONETIZE_PP" and closed_pos is not None:
    await self._check_reentry(...)
```
`ROLL_PP` closes never call `_check_reentry` — a rolled-away protective put produces **no**
re-entry eligibility check and **no** notification, mirroring exactly the class of gap CC3 fixes
for `LOSS_STOP`/`DELTA_STOP`. Unlike CC (four ACTION signals, all should trigger), PP has two
action types and the question of whether `ROLL_PP` *should* trigger `_check_reentry` needs a
moment's thought: a ROLL_PP is (per naming) a continuation of protection into a new contract,
not a full exit to flat — so this may be intentionally different from CC's case, not simply an
oversight to copy the same fix onto. **Resolve this distinction before writing the test**, not
after — confirm via `git log --oneline -10 src/strategy/pp_overlay_v1.py` and
`get_code_snippet("evaluate_pp")` whether `ROLL_PP` leaves the position open (in which case no
re-entry check is correct behavior — there's nothing to re-enter, the leg just changed
contracts) or closes it to flat pending a fresh entry (in which case this is the same bug class
as CC's and needs the same fix). Do not assume the answer mirrors CC without checking.

**Gap 2 — automated entry.** `paper_3track_overlay_entry.py` already reads `overlay_type='pp'`
from YAML (same as CC). Needs the same missing pieces CC3 identifies: an idempotency guard
(check for an existing open `protective_put`/`LONG_PUT_ROLES` position on `paper_nifty_spot`
before recording — today's only related check, `_query_open_call_roles`, doesn't cover this),
and a wrapper/fold-in step invoking strike selection (PP1's tool, or the existing %OTM tool
pending PP2) before recording, matching CC3's two-step-to-one-step consolidation.

**Cron cadence — RESOLVED 2026-08-03, folded in from the PP2 decision session, not deferred to
this story's own start:** daily check (not CC3's weekly Wednesday cron), off the existing snapshot
cron, against two conditions — no open `protective_put`/`LONG_PUT_ROLES` position at all
(bootstrap/gap-fill case), or an existing position with DTE ≤ 5 (routine roll trigger, matches
`evaluate_pp`'s existing `ROLL_ELIGIBLE` threshold so the entry script's own idempotency check
and the exit-signal engine's roll trigger stay in lockstep).

**No-gap requirement — RESOLVED same session, this is now a hard design constraint, not an
open question:** the replacement put must be bought the **same day** the DTE≤5 signal fires, not
after the outgoing put expires — this means briefly holding two puts (outgoing, ≤5 DTE remaining,
and the fresh one) rather than a window with zero protection. Operator was explicit: "i do not
want unprotected day." **The routine `ROLL_PP` re-entry must bypass PP's IVR gate unconditionally**
— a roll is coverage continuity the operator already committed to, not a new discretionary
purchase, and blocking renewal on elevated IVR would refuse protection exactly when volatility
(and plausibly the need for protection) is highest. This bypass is scoped **only** to the
`ROLL_PP`/routine-roll path — `MONETIZE_PP`-triggered re-entry (crash cash-out) keeps the existing
IVR gate as-is; whether *that* gate should also be relaxed is a materially different, higher-stakes
question spun into its own story, **PP4** (council checkpoint applies there, not here — this
routine-roll fix was judged simple enough for direct resolution, same tier as PP2/CC2/CC4).

**Files to change:**
- `src/strategy/pp_overlay_v1.py` — resolve and fix Gap 1 per the investigation above
- `scripts/strategies/three_track/paper_3track_overlay_entry.py` — idempotency guard for PP,
  extending whatever guard CC3 adds (likely the same function, parameterized by overlay type,
  rather than a second copy-pasted guard)
- `tests/unit/strategy/test_pp_overlay_v1.py` — reentry-trigger tests for whichever fix Gap 1
  resolves to
- `tests/unit/paper/test_overlay_entry.py` — PP idempotency-guard tests
- Cron config / `docs/ops/crontab.md` if it exists (see CC3 — same open question about whether
  this project tracks a crontab reference file)

**Before any code:**
```
get_code_snippet("PPOverlayV1.apply_action")              # already read this session — re-confirm before writing code
get_code_snippet("evaluate_pp")                            # does ROLL_PP semantically leave a position open?
git log --oneline -10 src/strategy/pp_overlay_v1.py
get_code_snippet("_query_open_call_roles")                 # confirm scope, same as CC3
```

**Depends on:** PP1 + PP2 for the entry-selection method (mirrors CC3's dependency on CC1/CC2);
Gap 1's fix does not depend on PP1/PP2 and can ship independently/first.

**Tests:**
- `test_roll_pp_reentry_check_behavior` — named generically pending the Gap 1 investigation;
  either `test_roll_pp_triggers_reentry_check` (if fix needed) or
  `test_roll_pp_correctly_skips_reentry_check_position_stays_open` (if current behavior is
  correct) — do not write this test until the investigation step above is done
- `test_entry_skipped_when_open_pp_position_exists`
- `test_entry_proceeds_when_no_open_pp_position`
- `test_notification_failure_does_not_block_pp_entry`
- `test_dry_run_default_until_pp1_pp2_resolved`

**Commit:** `fix(strategy): resolve PP re-entry gap + automated PP entry, guarded by open-position check`

---

## PP4 — Open decision: CRASH_MONETIZE re-entry continuity gap under PP's inverted IVR gate

**Context (surfaced 2026-08-03, during the PP2/PP3 decision session, not a pre-planned story):**
Confirmed via code read (`src/strategy/pp_overlay_v1.py::apply_action`, `exit_signals.py::evaluate_pp`):
`CRASH_MONETIZE` (delta ≤ -0.80 OR value ≥ 5× entry debit) is an ACTION-severity signal that
auto-closes the position and immediately calls `_check_reentry`. `_check_reentry` runs
`_ivr_passes`, and PP overrides this to be **inverted** relative to CSP/CC — it blocks re-entry
when IVR is *elevated* (`reentry_ivr_threshold = 0.60`), on the reasoning that you shouldn't
overpay for protection when volatility is already rich.

That reasoning is sound for an isolated vol spike, but breaks down across an **extended** decline.
IV is typically elevated precisely because the crash that just triggered `CRASH_MONETIZE` is still
in progress — so the gate is most likely to block re-entry at the exact moment the book has just
been left unprotected by design. Reference case: 2008 had six separate single-month declines ≥5%
across ten months (Jan −16.31%, Mar −9.36%, May −5.73%, Jun −17.03%, Sep −10.06%, Oct −26.41% —
see PP2's empirical table). A `CRASH_MONETIZE` triggered early in a decline of that shape, followed
by an IVR-blocked re-entry, could leave the book naked through several subsequent down-months.

**Distinct from PP3's routine-roll fix, which is already settled and unconditional:** PP3's IVR
bypass applies only to `ROLL_PP` (maintenance of a position already committed to, no discretion
involved). PP4 is about `MONETIZE_PP`-triggered re-entry specifically — a case where the operator
already realized a gain and is making a fresh, discretionary decision to re-arm. Overriding the
gate here trades away its original purpose (don't buy protection when vol is priced rich) against
coverage-continuity risk. That tradeoff is real in both directions and is exactly why this is a
council-checkpoint item, unlike PP3's roll fix.

**Also folds in, rather than spinning out separately:** whether `CRASH_MONETIZE`'s
delta ≤ -0.80 threshold itself needs recalibration now that PP2 moved entry to 0.15 delta. The
threshold was never explicitly calibrated against any specific entry delta, but a put entered
closer to the money reaches -0.80 on a smaller underlying move than one entered far OTM — worth
resolving in the same pass since both bear on "how does PP behave once a crash is already
underway."

**Council checkpoint applies** — clears all three of CLAUDE.md Step 2b's conditions: (1)
load-bearing, costly to reverse — this is the only downside protection in the pipeline and the
failure mode is "unprotected mid-crash," not a cosmetic issue; (2) genuinely multiple defensible
approaches — full IVR-gate bypass post-`CRASH_MONETIZE` (mirrors PP3's roll fix), a time-boxed
override (bypass only for N days post-crash-close, then gate resumes), a separate elevated-
tolerance re-entry threshold specific to this path (e.g. IVR ≤ 0.80 instead of 0.60 for
post-monetize re-entry only), or recalibrating `CRASH_MONETIZE`'s delta threshold instead of or
alongside a gate change; (3) spans strategy design, NSE crash-microstructure (deep-ITM put
liquidity/spread behavior during a crash — relevant to whether re-entry can even fill cleanly),
and risk/capital management simultaneously. Recommend template `strategy_parameters`. Draft
question:

> "PPOverlayV1's `CRASH_MONETIZE` signal (delta ≤ -0.80 or value ≥ 5× entry debit) auto-closes and
> immediately attempts re-entry, gated by an inverted IVR check that blocks re-entry when IVR is
> elevated. Because crashes elevate IV, this gate is most likely to block re-entry exactly when the
> book has just been left without protection, risking extended unprotected exposure across a
> multi-month decline (2008-style). Should this re-entry path bypass the IVR gate (fully, or with
> a time-boxed/threshold-relaxed variant), and separately, should `CRASH_MONETIZE`'s delta ≤ -0.80
> threshold be recalibrated given PP2 moved entry to 0.15 delta (closer to the money than the
> ~0.03-delta entry the threshold was implicitly tuned against)? Note this is a narrower, path-
> specific question than PP3's roll-cadence fix (already resolved, unconditional bypass) — don't
> reuse that answer by analogy, the discretionary-vs-maintenance distinction is the crux here."

**Until answered:** `CRASH_MONETIZE` ships unchanged — immediate full close, existing IVR-gated
re-entry attempt. The gap is documented (this story, plus the `tasks.md` PP4 entry), not fixed.

**Depends on:** none structurally to start the council process, but reasons about both PP2
(entry delta, resolved) and PP3 (routine-roll re-entry design, resolved) — sequence after both.

**Commit:** none — decision-gate note, same as PP2. Resolve via council, then update
`DECISIONS.md`, `evaluate_pp`'s threshold (if recalibrated), and `PPOverlayV1._ivr_passes`
call-site behavior for the `MONETIZE_PP` path (if bypass/relaxation chosen).

---

## Collar1 — Two-leg strike selection for Collar, coordinating CC1's CE ladder and PP1's PE ladder

**Context (added 2026-07-28, mirrors CC1/PP1 but not a mechanical copy):** `CollarOverlayV1`
(`src/strategy/collar_overlay_v1.py:57-499`) holds two simultaneous legs — a short call
(`overlay_collar_call`, `SHORT_CALL_ROLE`) and a long put (`overlay_collar_put`, `LONG_PUT_ROLE`).
Its production entry path today is `find_overlay_strikes.py --overlay-type collar` (fixed %OTM
for both legs — confirmed via `reentry_script_hint = "run find_overlay_strikes.py --overlay-type
collar"`, `collar_overlay_v1.py:63`). `find_strike_by_delta.py` has **zero references to collar
today** (confirmed via `search_code("collar", path_filter="scripts/lookup/find_strike_by_delta.py")`
— no matches) — unlike CSP/CC/PP, there is no delta-based candidate ladder for either collar leg
yet, and no coordination logic between the two legs at all.

**Problem, not a single-leg problem:** a collar isn't "CC1's ladder plus PP1's ladder run
independently" — the two legs interact financially. Selling the call funds buying the put (in
whole or in part); the OTM distance chosen for each leg jointly determines whether the combo is
net credit, net debit, or zero-cost, and how much upside is capped versus how much downside is
covered. Running CC1's CE search and PP1's PE search as two unrelated calls would pick each leg's
"best" delta in isolation and could easily produce a combo that's expensive (both legs picked for
liquidity/spread quality with no netting constraint) or lopsided (deep downside protection funded
by giving up almost no upside, or vice versa) without that being a deliberate choice.

**Scope, once CC1 and PP1 have landed (hard dependency — see below):** extend
`find_strike_by_delta.py` (or a thin wrapper over it) with an `--overlay-type collar` mode that:
1. Runs the CE-side search using `CC_DELTA_CANDIDATES` (CC1) for the short call leg.
2. Runs the PE-side search using `PP_DELTA_CANDIDATES` (PP1) for the long put leg.
3. Reports the **net premium** of the combo (call credit − put debit) alongside each leg's
   individual delta/strike/liquidity figures — this net figure is the one piece of coordination
   logic this story must add; it does not exist for either CC1 or PP1 individually because
   neither is a two-leg combo.
4. Does **not** attempt to auto-select "the" combo the way CC1/PP1 auto-select a single strike —
   print the cross-product of viable call/put candidates (small: each ladder is 2-4 candidates)
   with net premium for each pairing, and leave the actual pick to CC2/PP2-style operator judgment
   (folded into Collar2 below) rather than inventing a third auto-select heuristic no one has
   asked for.

**Hard dependency — this story cannot start until CC1 and PP1 both ship** (unlike CC1/PP1
themselves, which only depend on each other loosely): there is no independent "Collar ladder" to
invent from scratch — this story's entire job is coordinating the two ladders CC1/PP1 already
define. Building a third, Collar-specific ladder in parallel would duplicate CC1/PP1's delta-band
work and risk drifting out of sync with whatever CC2/PP2 later decide.

**Files to change:**
- `scripts/lookup/find_strike_by_delta.py` — `--overlay-type collar` mode; reuses
  `CC_DELTA_CANDIDATES` (CC1) and `PP_DELTA_CANDIDATES` (PP1) directly, does not define new
  constants; new `_net_collar_premium(call_price, put_price) -> Decimal` pure helper
- `src/instruments/strike_selector.py` — confirm (don't assume) whether the existing
  `rank_strikes()` tuple needs a collar-aware variant, or whether CC1's/PP1's per-leg ranking
  already suffices once each leg's candidate is picked independently and only the net-premium
  report is new
- `tests/unit/test_find_strike_by_delta.py` — collar mode tests
- `src/strategy/collar_overlay_v1.py` — `reentry_script_hint` update decision deferred to
  Collar2 (same dependency shape as CC1→CC2, PP1→PP2)

**Before any code:**
```
get_code_snippet("CollarOverlayV1")                       # already read this session — confirmed
                                                            # two-leg roles, ReEntryMixin inheritance
get_code_snippet("CC_DELTA_CANDIDATES")                    # once CC1 lands
get_code_snippet("PP_DELTA_CANDIDATES")                    # once PP1 lands
search_code("overlay-type collar")                         # confirm find_overlay_strikes.py's
                                                            # existing %OTM collar mode as reference
git log --oneline -10 scripts/lookup/find_strike_by_delta.py
```

**Tests:**
- `test_collar_mode_runs_both_ce_and_pe_searches` — `--overlay-type collar` invokes both ladders,
  not just one
- `test_net_collar_premium_computed_correctly` — call credit minus put debit, sign correct for
  net-credit and net-debit cases
- `test_collar_mode_does_not_auto_select_a_single_combo` — regression guard against inventing an
  unrequested third auto-select heuristic; output is the candidate cross-product, not one pick
- `test_collar_mode_requires_cc1_pp1_ladders_present` — collar mode raises a clear error if
  `CC_DELTA_CANDIDATES`/`PP_DELTA_CANDIDATES` aren't importable (guards the hard dependency)

**Commit:** `feat(instruments): two-leg delta-targeted strike search for Collar, coordinating CC1/PP1 ladders`

---

## Collar2 — Open decision: does Collar move off fixed %OTM to coordinated delta-targeted entry?

**Mirrors CC2/PP2's shape, different tradeoff axis again — do not answer by analogy to either.**
CC2's axis is premium collected vs. assignment risk (single short leg). PP2's axis is protection
cost vs. protection responsiveness (single long leg). Collar's axis is **net cost/credit of the
combo vs. how much upside is capped and how much downside is covered** — a genuinely two-
dimensional tradeoff neither single-leg story faces, because moving either leg's strike changes
both the combo's net cost *and* its cap/floor simultaneously.

**Council checkpoint applies** (load-bearing — changes the net cost basis and payoff shape of the
one overlay that already covers both call and put; two defensible approaches; spans strategy
design + NSE options microstructure + capital-efficiency tradeoffs distinct from CC2/PP2).
Recommend template `strategy_parameters`, draft question:

> "CollarOverlayV1's current production entry uses `find_overlay_strikes.py --overlay-type
> collar` (fixed %OTM for both legs). A delta-targeted alternative (Collar1's coordinated
> CC_DELTA_CANDIDATES/PP_DELTA_CANDIDATES search) would instead target a fixed delta band per
> leg and report net combo premium. Given the call leg's exit rules (`DELTA_STOP` 0.55,
> `DELTA_WARN` 0.45, shared with CC via `evaluate_cc`) and the put leg's protective role, should
> Collar move to delta-targeted entry for both legs, and if so what per-leg bands — and should the
> combo be constrained toward net-zero-cost, or is a net-debit/net-credit skew acceptable if it
> produces a better cap/floor shape? This is a two-dimensional tradeoff (net cost *and* payoff
> shape move together) — don't reuse CC2's or PP2's single-axis answer by analogy."

**Until answered:** Collar1 ships as an experimentation/comparison tool only (candidate
cross-product, no auto-select), `reentry_script_hint` stays pointed at the %OTM tool.

**Commit:** none — decision-gate note. Resolve via council or operator, then update
`DECISIONS.md` and Collar1's ladder/net-premium presentation.

---

## Collar3 — Automated Collar entry script + idempotency guard + cron + re-entry gap audit

**Context (2026-07-28, same "I only get notified" directive that drove CC3/PP3):** Collar entry
today is entirely manual — run `find_overlay_strikes.py --overlay-type collar`, eyeball both
legs, hand-paste two `record_paper_trade` commands (or the YAML → `paper_3track_overlay_entry.py`
path for the two-track write). This story automates entry the same way CC3/PP3 do, but the
two-leg nature changes both the idempotency guard and the re-entry audit shape.

**Idempotency guard gap — confirmed via code read, `paper_3track_overlay_entry.py`:** the only
existing safety check for collar is `_query_open_call_roles()`
(`paper_3track_overlay_entry.py:231-273`) plus `_validate_collar_pairs()` (`:63-102`). Both are
narrower than "does an open Collar position already exist":
- `_query_open_call_roles()` answers "does *any* strategy already have an open short call
  (`overlay_cc` or `overlay_collar_call`) on *this specific instrument key*" — a same-instrument
  cross-type dedup check (prevents double-counting one physical short call under two leg_roles),
  not a "Collar already open, don't re-enter" bootstrap guard.
- `_validate_collar_pairs()` only checks that a collar submission includes both legs (or is
  exempted because an existing `overlay_cc` covers the call side) — it validates the *shape* of
  a submission already in flight, it doesn't check whether a collar is already open before that
  submission is built.
- Confirmed by reading `main()` (`:494-569`): there is no call anywhere in the entry flow that
  asks "does `paper_nifty_spot` already hold an open `overlay_collar_call` + `overlay_collar_put`
  pair" before proceeding to `build_overlay_trades()`. Same class of gap CC3/PP3 found and fixed
  for their single-leg cases — run as-is against a freshly-generated collar YAML, a Wednesday (or
  whatever cadence) cron would record a second collar pair even if one is already open, same
  three-weeks-out-of-four double-up risk CC3 flags.

**Re-entry gap — confirmed via code read, `CollarOverlayV1.apply_action`
(`src/strategy/collar_overlay_v1.py`):**
```python
triggering_signal = action.metadata.get("triggering_signal") if action.metadata else None
if triggering_signal in ("PROFIT_TARGET", "TIME_STOP") and short_call_pos is not None:
    ...
    await self._check_reentry(...)
```
This is the exact same gap class CC3 fixes — `evaluate_cc()` (which drives Collar's short-call
signal evaluation, confirmed via `check_signals`'s `ExitSignalEngine.evaluate_cc(...)` call) can
also emit `LOSS_STOP`, `DELTA_STOP`, `DELTA_WARN`, and `BELOW_FLOOR` (`src/strategy/exit_signals.py:284-338`)
— only `PROFIT_TARGET` and `TIME_STOP` currently trigger `_check_reentry`. A `LOSS_STOP` or
`DELTA_STOP` close on the short call (both `ACTION` severity, both route through `CLOSE_COLLAR`
same as a `PROFIT_TARGET` close) produces **no** re-entry eligibility check and **no** re-entry
notification today — identical bug shape to the one CC3 closes for `CCOverlayV1`, confirmed
independently here rather than assumed by analogy (per this task's own instruction not to assume
Collar mirrors CC without checking).

**What is correctly two-leg-aware already (don't re-fix):** `apply_action`'s close logic and
`OverlayCloser.close_collar_all`/`monetize_collar_put` (`src/strategy/overlay_closer.py`) already
handle the two-leg atomicity concern — `apply_action` builds close trades for whichever of
`short_call_pos`/`long_put_pos` are present and writes them via a single `store.record_trades([...])`
call (not two separate `record_trade()` calls), and logs a warning if the put leg is missing
(`collar_overlay_v1.apply_action.missing_put_leg`). This story's job is the *entry-side*
idempotency guard and the *re-entry-trigger* widening — not re-doing the close-side atomicity,
which is already correct.

**Files to change:**
- `scripts/strategies/three_track/paper_3track_overlay_entry.py` — new idempotency guard (e.g.
  `_query_open_collar_pair(db_path) -> bool`, parameterized alongside whatever CC3/PP3 land for
  their own overlay types, per tasks.md's note that CC3/PP3's guards are likely one shared
  parameterized function rather than three separate copies) — checks for an existing open
  `overlay_collar_call` **and** `overlay_collar_put` pair for `paper_nifty_spot` before recording;
  if found, exit without acting, log at INFO (expected no-op, matching CC3's INFO-not-WARNING
  convention for a no-op week)
- `src/strategy/collar_overlay_v1.py` — widen `apply_action`'s re-entry trigger guard from
  `triggering_signal in ("PROFIT_TARGET", "TIME_STOP")` to include `LOSS_STOP`, `DELTA_STOP`, and
  `BELOW_FLOOR` (mirror CC3's exact reasoning: the `ReEntryMixin` gates themselves — DTE ≥14, IVR
  ≥0.25, no open position — don't need to change, only which signals invoke `_check_reentry`).
  Confirm whether `DELTA_WARN` (a `WARN`, not `ACTION`, severity) should also trigger — likely not,
  since `WARN` signals don't close the position (no `CLOSE_COLLAR` dispatched), so there's nothing
  to re-enter after; verify this against `check_signals`'s severity-based dispatch before assuming
- Reuses Collar1's two-leg delta-targeted search (once Collar1 ships) for strike selection —
  same **hard dependency** shape as CC3 on CC1/CC2 and PP3 on PP1/PP2: this story cannot go live
  with `--no-dry-run`/unattended cron until Collar1 and Collar2 are both resolved
- `tests/unit/paper/test_overlay_entry.py` — idempotency-guard tests for the collar pair
- `tests/unit/strategy/test_collar_overlay_v1.py` — extend `apply_action` tests for the widened
  re-entry trigger guard

**Before any code:**
```
get_code_snippet("paper_3track_overlay_entry.main")        # confirm exact current guard/flow —
                                                             # already read this session, re-confirm
get_code_snippet("_query_open_call_roles")                  # confirm exact (narrower) scope — already
                                                             # read this session, confirmed same-instrument
                                                             # cross-type dedup, not bootstrap idempotency
get_code_snippet("_validate_collar_pairs")                  # confirm exact (narrower) scope — same read
get_code_snippet("CollarOverlayV1.apply_action")             # already read this session — confirmed
                                                             # PROFIT_TARGET/TIME_STOP-only gap
get_code_snippet("ExitSignalEngine.evaluate_cc")             # confirm full signal set driving Collar's
                                                             # short-call evaluation — already read
                                                             # this session, confirmed BELOW_FLOOR/
                                                             # PROFIT_TARGET/LOSS_STOP/DELTA_STOP/DELTA_WARN
git log --oneline -10 src/strategy/collar_overlay_v1.py
```

**Cron cadence:** not decided here — flag as open, same as PP3 (do not assume CC3's Wednesday
cadence transfers; Collar's short-call side is expiry-cycle premium collection like CC, but its
put side is drawdown protection like PP — a single shared cadence for both legs' re-entry isn't
obviously right and needs the same operator confirmation PP3 defers).

**Depends on:** Collar1 + Collar2 for the entry-selection method (mirrors CC3→CC1/CC2,
PP3→PP1/PP2). The re-entry-trigger-widening fix does not depend on Collar1/Collar2 and can ship
independently/first, same as PP3's Gap-1/Gap-2 split.

**Tests:**
- `test_entry_skipped_when_open_collar_pair_exists` — new idempotency guard, mirrors CC3/PP3's
  pattern; asserts no trade recorded for either leg
- `test_entry_proceeds_when_no_open_collar_position`
- `test_existing_query_open_call_roles_guard_unchanged` — regression guard, the same-instrument
  cross-type check still works exactly as today
- `test_existing_validate_collar_pairs_guard_unchanged` — regression guard, partial-collar
  submission validation still fires exactly as today
- `test_dry_run_default_until_collar1_collar2_resolved` — regression guard against accidentally
  shipping `--no-dry-run` before the ladder/band decision lands
- `test_reentry_check_called_for_loss_stop` — new: `_check_reentry` now called when
  `triggering_signal == "LOSS_STOP"`
- `test_reentry_check_called_for_delta_stop` — same for `DELTA_STOP`
- `test_reentry_check_called_for_below_floor` — same for `BELOW_FLOOR`
- `test_reentry_check_not_called_for_delta_warn` — regression guard: WARN-severity signals never
  close the position, so no re-entry check should fire for them (confirm this assumption in code
  before writing the test, per this story's own "don't assume" instruction)
- `test_reentry_gates_unchanged_regardless_of_triggering_signal` — DTE/IVR/open-position gate
  logic itself doesn't change, only which signals invoke it
- `test_close_collar_all_atomicity_unchanged` — regression guard that this story doesn't disturb
  the already-correct two-leg atomic close/missing-put-leg-warning behavior

**Commit:** `feat(strategy): automated Collar entry script, idempotency-guarded, re-entry check widened to all applicable exit signals`

---

## S7 — Fix overlay leg-role mismatch breaking daily CC/PP/Collar snapshot persistence (confirmed bug, 2026-07-28)

**Context:** User-reported observation ("there is no snapshot for collar, CC and PP, we should be
able to track these overlay's daily pnl") led to a code read that found a real, confirmed bug —
not a missing feature. `_save_leg_snapshots()` (`scripts/strategies/three_track/paper_3track_snapshot.py:964-1014`)
does loop `snapshot.pnl.overlay_pnls.items()` and calls `store.record_leg_snapshot()` for each
role — on the surface this looks like it already persists a daily row per overlay leg. The bug is
in what `role` actually is by the time it gets there.

`generate_track_snapshot()` (`src/paper/track_snapshot.py:130-304`) computes `overlay_pnls` keyed
by the *real* leg_role (`overlay_cc`, `overlay_pp`, `overlay_collar_call`, `overlay_collar_put`)
during its main loop, but immediately before returning, calls:
```python
overlay_pnls = _normalize_overlay_pnls(overlay_pnls)
```
`_normalize_overlay_pnls()` (`src/paper/track_snapshot.py:57-98`) collapses those real leg_roles
into three **display labels** — `"cc"`, `"collar"`, `"pp"` — merging collar's call+put into one
unit and deduplicating `overlay_cc` vs `overlay_collar_call` (same physical contract recorded
under two roles). This collapsing is correct and necessary for the printed comparison table and
for `net_pnl` (prevents double-counting the short call) — **but the `TrackSnapshot` returned by
`generate_track_snapshot()` carries only the collapsed labels forward**, and `_save_leg_snapshots()`
persists directly from that already-normalized `pnl.overlay_pnls` dict with no re-expansion step.

**Concrete consequences, confirmed by reading both functions:**
1. `_save_leg_snapshots()` calls `store.get_position(track_name, role)` where `role` is `"cc"`,
   `"collar"`, or `"pp"` — none of these are real `leg_role` values in `paper_trades`, so this
   lookup never matches, and `overlay_ltp` is silently `None` for every CC/PP/Collar snapshot row,
   every day (not an occasional gap — this is the row's *only* possible outcome given the key
   mismatch).
2. The `PaperLegSnapshot` row gets written with `leg_role="cc"` / `"collar"` / `"pp"` — disconnected
   from the real `overlay_cc`/`overlay_pp`/`overlay_collar_call`/`overlay_collar_put` leg_roles
   every other consumer in the codebase uses (e.g. `store.get_prev_leg_snapshot(track_name, role,
   ...)` calls elsewhere in this same file for MTD/daily-delta calculations pass through the same
   collapsed labels, so those *do* work internally today — but nothing outside this file's own
   round-trip can query CC/PP/Collar's daily P&L history by its real leg_role, and S3's
   `paper_track_comparison_snapshots` table explicitly filters to base-only legs, so it can't be
   used as a substitute path either).
3. **Not caught by the existing test suite:** `test_save_leg_snapshots_with_overlay`
   (`tests/unit/paper/test_paper_3track_snapshot.py:276+`) constructs its `TrackSnapshot` fixture
   directly with the real leg_role key (`overlay_pnls={"overlay_pp": Decimal("-200")}`), bypassing
   `generate_track_snapshot()`'s normalization step entirely. The test has been green throughout
   because it never exercises the actual runtime data flow (`_run()` always calls
   `generate_track_snapshot()` first, then feeds its already-normalized output into
   `_save_leg_snapshots()`) — a real gap between unit-test assumptions and the production call
   path, not a flaky or skipped test.

**Fix options (pick one, don't mix — decide at implementation time based on which is less
invasive):**
- **(a) Persist before normalization.** Have `_run()` also capture the raw (pre-normalize)
  overlay_pnls dict from `generate_track_snapshot()` (would require that function to return both,
  or a second lighter-weight call) and pass the raw dict to `_save_leg_snapshots()` for
  persistence, while the display/summary path keeps using the normalized dict as today. Keeps
  the two concerns (display grouping vs. persistence granularity) cleanly separated.
- **(b) Re-expand at persistence time.** Give `_save_leg_snapshots()` (or a helper it calls) the
  original per-leg-role realized/unrealized breakdown — it already computes `realized_by_leg` from
  `store.get_trades(track_name)` using real leg_roles, so the raw per-role unrealized figures could
  be recomputed or threaded through separately from the normalized `pnl.overlay_pnls` used for
  `overlay_ltp`/display.
- Whichever is chosen, `store.get_position(track_name, role)` inside `_save_leg_snapshots` must
  end up called with a real leg_role (`overlay_cc`/`overlay_pp`/`overlay_collar_call`/
  `overlay_collar_put`), never the collapsed display label.

**Files to change:**
- `src/paper/track_snapshot.py` — `generate_track_snapshot()` (expose raw overlay_pnls
  alongside normalized, per whichever fix option is chosen)
- `scripts/strategies/three_track/paper_3track_snapshot.py` — `_save_leg_snapshots()` (persist
  against real leg_role, not the collapsed display label)
- `tests/unit/paper/test_paper_3track_snapshot.py` — new integration-shaped test that goes
  through `generate_track_snapshot()` → `_save_leg_snapshots()` end to end (the existing unit test
  stays as a regression guard for `_save_leg_snapshots()` in isolation, but this story needs the
  gap between the two functions covered, which nothing today exercises)
- `tests/unit/paper/test_track_snapshot.py` (or sibling) — coverage for whatever new raw-dict
  exposure `generate_track_snapshot()` gains

**Before any code:**
```
get_code_snippet("generate_track_snapshot")          # already read this session — confirmed
                                                       # normalization happens before return
get_code_snippet("_normalize_overlay_pnls")           # already read this session — confirmed
                                                       # collapses overlay_cc/pp/collar_call/put
                                                       # to "cc"/"collar"/"pp"
get_code_snippet("_save_leg_snapshots")               # already read this session — confirmed
                                                       # persists against the collapsed labels
get_code_snippet("test_save_leg_snapshots_with_overlay")  # confirmed this test bypasses the
                                                       # normalization step, doesn't catch the bug
git log --oneline -10 src/paper/track_snapshot.py
git log --oneline -10 scripts/strategies/three_track/paper_3track_snapshot.py
```

**Tests:**
- `test_generate_track_snapshot_exposes_raw_overlay_leg_roles` — whichever fix option is chosen,
  the real leg_role keys (`overlay_cc`, `overlay_pp`, `overlay_collar_call`, `overlay_collar_put`)
  must be recoverable somewhere in the return value, not just the collapsed `"cc"/"collar"/"pp"`
- `test_save_leg_snapshots_end_to_end_uses_real_leg_role` — full `generate_track_snapshot()` →
  `_save_leg_snapshots()` path; asserts `store.get_leg_snapshot(track, "overlay_cc", date)` (etc.)
  returns a row, not `store.get_leg_snapshot(track, "cc", date)`
- `test_save_leg_snapshots_end_to_end_ltp_populated` — regression guard for consequence #1: the
  persisted overlay row's `ltp` field is non-None when the instrument has a live price, proving
  `get_position()` was called with a real leg_role
- `test_save_leg_snapshots_collar_persists_both_legs_separately` — Collar's call and put legs
  each get their own `paper_leg_snapshots` row (real leg_role each), even though they're displayed
  as one merged `"collar"` figure in the summary table — persistence granularity and display
  granularity are allowed to differ, this test guards that they do differ correctly rather than
  collapsing at both layers
- `test_existing_display_normalization_unchanged` — regression guard: the printed comparison
  table / `_normalize_overlay_pnls`'s collar-merge and CC/collar_call dedup logic is untouched by
  this fix; only the *persistence* path changes

**Commit:** `fix(paper): persist daily CC/PP/Collar leg snapshots under real leg_role, not display label`

---

## S8 — Overlay P&L comparison table (CC/PP/Collar), mirroring S3's design for the base tracks

**Context:** S3 (shipped) gave the three base tracks a dedicated, queryable daily comparison table
(`paper_track_comparison_snapshots`) with `pnl_1d_abs/pct` and `pnl_inception_abs/pct` per track.
Overlays have no equivalent — S7 fixes `paper_leg_snapshots` to persist under the correct real
leg_role, but that table's schema/query shape was designed for arbitrary per-leg audit rows, not
for a clean "show me CC's daily and cumulative P&L over time" query the way S3's table serves that
exact purpose for base legs. **Hard dependency: S7 must land first** — building this on top of
the collapsed-label bug would inherit the same `None`-ltp and wrong-key problems.

**Required behavior (mirrors S3's Level-1 fields exactly, applied per overlay instead of per
base track):**
- New table, e.g. `paper_overlay_pnl_snapshots`, one row per `(snapshot_date, strategy_name,
  overlay_type)` where `overlay_type ∈ {"cc", "pp", "collar"}` — Collar's call+put stays merged
  as one unit here too (matching S3's per-track granularity, not S7's per-real-leg-role
  persistence granularity; S7 fixes the underlying leg data, this table is a display/analysis
  aggregation on top, same relationship `paper_leg_snapshots` already has to the printed summary)
- Same four fields as S3: `pnl_1d_abs`, `pnl_1d_pct` (denominator = yesterday's overlay mark),
  `pnl_inception_abs`, `pnl_inception_pct` (denominator = entry cost/credit basis) — confirm
  with the operator whether CC's credit-received basis and PP's debit-paid basis need different
  sign conventions before assuming they're symmetric with S3's long-only base-leg math
- Written by the same daily cron as S3/S7 (`paper_3track_snapshot.py`), computed from the
  now-correctly-keyed `paper_leg_snapshots` rows S7 produces
- Queryable independently: `get_overlay_pnl_snapshots(strategy_name, overlay_type) →
  list[OverlayPnLSnapshot]`, same pattern as S3's `get_track_comparison_snapshots()`

**Files to change:**
- `src/paper/store.py` / `src/paper/models.py` — new `OverlayPnLSnapshot` model + store methods
- `scripts/strategies/three_track/paper_3track_snapshot.py` — new aggregation step, reads S7's
  corrected `paper_leg_snapshots` rows
- `tests/unit/paper/test_store.py` (or sibling), `tests/unit/scripts/`

**Before any code:**
```
get_code_snippet("TrackComparisonSnapshot")      # S3's model — mirror its shape, don't diverge
get_code_snippet("record_track_comparison_snapshot")
get_code_snippet("get_track_comparison_snapshots")
```
Confirm S7 has landed (check `git log --oneline -5 src/paper/track_snapshot.py` for S7's commit)
before starting — this story's entire input depends on S7's leg_role fix being live.

**Tests:**
- `test_overlay_pnl_snapshot_persists_all_three_types_daily`
- `test_overlay_pnl_1d_uses_yesterday_mark_denominator` / `..._inception_uses_entry_basis`
- `test_collar_call_and_put_merged_as_one_row` — Collar's two legs produce one comparison row,
  not two, matching the display convention S3/S7 already established
- `test_queryable_by_strategy_and_overlay_type`

**Commit:** `feat(paper): daily P&L comparison table for CC/PP/Collar overlays, mirrors S3's base-track design`

---

## S9 — NiftyBees protection-recovery comparison table + Telegram digest

**Context:** S3 (shipped) gives per-track base P&L, S8 gives per-overlay P&L. Neither answers the
operator's actual question: on a day NiftyBees is down, how much of that loss did each overlay
recover? Confirmed with operator (2026-07-28) via sample-table iteration — final approved shape is
one row per day, NiftyBees 1D P&L next to CC/PP/Collar 1D P&L side by side, plus a single "best
recovery" figure, not three separate per-overlay recovery percentages. **Hard dependency: S3 and
S8 must both land first** — this table reads their output, it computes nothing from raw legs itself.

**Required behavior:**
- New table `paper_protection_recovery_snapshots`, one row per `snapshot_date`, columns:
  `niftybees_pnl_1d`, `cc_pnl_1d`, `pp_pnl_1d`, `collar_pnl_1d`, `niftybees_pnl_inception`,
  `cc_pnl_inception`, `pp_pnl_inception`, `collar_pnl_inception`, `best_overlay` (nullable —
  which of cc/pp/collar recovered the largest share), `best_recovery_pct` (nullable).
- `recovery_pct` (per overlay, used to pick `best_overlay`) is defined **only** when
  `niftybees_pnl_1d < 0`: `overlay_pnl_1d / abs(niftybees_pnl_1d)`. On a day NiftyBees is flat or
  positive, `best_overlay`/`best_recovery_pct` are `NULL`, not a negative or zero-anchored number —
  confirmed with operator this avoids a misleading "-36% recovery" reading on green days when
  nothing needed recovering.
- Same rule applies at inception granularity using `niftybees_pnl_inception` / overlay
  `pnl_inception` — a separate `best_overlay_inception` / `best_recovery_pct_inception` pair, not
  a running sum of the daily figures (inception basis is entry cost/credit, per S3/S8, so it will
  legitimately drift from a naive cumulative sum of the daily column — that's expected, not a bug
  to reconcile away).
- **Open design question to resolve before implementation, not deferred silently:** does NiftyBees
  carry all three overlays live simultaneously, or is this an analysis/backtest view comparing
  three hypothetical scenarios against the one live overlay actually attached? The "single overlay
  copy" risk noted at the end of this epic implies the latter — confirm with operator before
  writing the aggregation query, since it changes whether `cc_pnl_1d`/`pp_pnl_1d`/`collar_pnl_1d`
  are three live parallel series or three what-if reconstructions.
- Written by the same daily cron as S3/S7/S8 (`paper_3track_snapshot.py`), reading S3's
  `paper_track_comparison_snapshots` (niftybees row) and S8's `paper_overlay_pnl_snapshots`
  (cc/pp/collar rows) for the same `snapshot_date` — no independent leg-level computation.
- Queryable: `get_protection_recovery_snapshots(strategy_name, start_date=None, end_date=None) →
  list[ProtectionRecoverySnapshot]`.

**Telegram digest (new — optimized format, replaces console-only reporting):**
Today this data only prints to console (`summary_rows` in `paper_3track_snapshot.py`'s `main()`)
— no Telegram message exists for the cross-track/overlay comparison at all, only a critical proxy-
delta alert. S9 adds one compact daily Telegram message, sent once per cron run (not per-track,
not per-overlay — a single digest), format:

```
📊 NiftyBees vs overlays — 28 Jul
NiftyBees: -700
  CC   +300 (43%)
  PP   +180 (26%)
  Collar +240 (34%)
Best: CC
```

On a flat/green NiftyBees day, drop the recovery percentages and the "Best" line entirely rather
than printing misleading numbers:

```
📊 NiftyBees vs overlays — 27 Jul
NiftyBees: +250
  CC   -90
  PP   -45
  Collar -60
```

Rules for the message builder (`_build_recovery_digest()`, new function):
- One `notifier.send()` call per cron run for this digest, not one per overlay — avoid the
  per-signal Telegram spam pattern the exit-signal path already has to batch around (see
  `compute_and_record_exit_signals`'s WARN-batching comment, same file, ~line 525).
- Overlay lines sorted by recovery amount descending on a red NiftyBees day (best first, matching
  the "Best:" line), sorted by raw P&L descending on a green day (no recovery framing to sort by).
- Reuse `notifier.send()` (`TelegramNotifier`, already imported in this file) — no new gateway.
- Suppressed (like the rest of this script's Telegram calls) in dry-run mode (`save=False`).

**Files to change:**
- `src/paper/store.py` / `src/paper/models.py` — new `ProtectionRecoverySnapshot` model +
  `record_protection_recovery_snapshot()` / `get_protection_recovery_snapshots()` store methods
- `scripts/strategies/three_track/paper_3track_snapshot.py` — new aggregation step (reads S3+S8
  output for the same `snap_date`) + `_build_recovery_digest()` + one `notifier.send()` call in
  `main()`
- `tests/unit/paper/test_store.py` (or sibling), `tests/unit/scripts/`

**Before any code:**
```
get_code_snippet("TrackComparisonSnapshot")       # S3's model
get_code_snippet("OverlayPnLSnapshot")            # S8's model
search_code("_normalize_overlay_pnls")            # existing collar-merge/dedup convention to match
git log --oneline -5 src/paper/store.py           # confirm S3+S8 have landed
```
Confirm both S3 and S8 have landed (models + store methods present) before starting — this
story's entire input is their output tables, computed from nothing else.

**Tests:**
- `test_recovery_pct_null_on_green_niftybees_day` — `niftybees_pnl_1d >= 0` → `best_overlay`
  and `best_recovery_pct` are `None`, not a negative/zero number
- `test_recovery_pct_computed_correctly_on_red_day` — fixture matching the -700/+300/+180/+240
  sample above asserts `best_overlay == "cc"`, `best_recovery_pct == pytest.approx(0.4286)`
- `test_inception_recovery_independent_of_daily` — inception fields don't derive from summing
  daily rows
- `test_digest_omits_recovery_lines_on_green_day` — message builder output has no "Best:" line
  and no percentages when NiftyBees 1D P&L is non-negative
- `test_digest_single_telegram_call_per_run` — `notifier.send()` called exactly once for the
  recovery digest, not once per overlay

**Commit:** `feat(paper): NiftyBees protection-recovery comparison + Telegram digest`

---

## Open risk not resolved by this epic (log in TODOS.md, don't block on it)

Full automation (S4) combined with a single overlay copy (S1r/S2r) means a bad overlay-roll
decision now affects the *only* protection NiftyBees has, with no human check before execution.
Previously, even a bad decision was triplicated as "one of three data points" and reviewed
before acting. Recommend the first live cycle after S4 ships gets a manual daily review of
`paper_exit_events` for `paper_nifty_spot` regardless of automation — not as a story requirement,
but flagging it here since nothing in S3r/S4 builds in a monitoring backstop for the new risk
concentration.
