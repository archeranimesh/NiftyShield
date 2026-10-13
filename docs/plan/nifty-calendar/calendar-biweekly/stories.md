
# Calendar Bi-weekly variant — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

Spec source: `TradeResearch/findings/14ZZYoV4DBc_combined.md`. Reuses everything from `calendar-monthly/`; these tasks add implementers and registry entries only.

---

## CB-1 — BIWEEKLY config and BiweeklyCyclePolicy

**Files to change / create:**
- `src/nifty_calendar/config.py` — add the `BIWEEKLY` instance (additive).
- `src/nifty_calendar/cycle.py` — add `BiweeklyCyclePolicy` and register it (additive).
- `tests/unit/nifty_calendar/test_cycle_biweekly.py`

**Before any code:** `get_code_snippet("CalendarVariantConfig")`, `CyclePolicy`, `EntryPlan`, `CycleCalendar` (CM-3); `get_expiry_candidates` for the weekly expiry list.

**What to implement:**

1. `BIWEEKLY` config: target ₹1,600 per lot, hard hold 7 days, exit-by DTE 7, wing start 400 put / 400 call, vega cap about 5, breach adjust window 3-4 days, lots 1, strategy_name
   `paper_nifty_calendar_biweekly`.
2. `BiweeklyCyclePolicy.entry_window`: on the monthly exit day (or the previous bi-weekly's exit day) near = the weekly expiry after next (about 14 DTE), far = one week beyond it. Skip the current
   weekly. A same-pair redeploy plan (CB-2 asks for it) reuses the original pair and the original hard exit date.
3. Chain end: no bi-weekly entry whose hard exit date would run past the start of the next monthly entry window; `CycleCalendar.active_variant` then returns `monthly` from that date.
4. Holiday handling through `src/market_calendar`; an expiry moved by a holiday is taken from the instrument lookup, not computed.

**Tests:** `test_pair_skips_current_weekly` · `test_far_is_one_week_beyond_near` · `test_chain_stops_before_monthly_window` · `test_redeploy_keeps_original_hard_exit` ·
`test_holiday_shifted_expiry_used` · `test_calendar_returns_one_variant_per_date_with_both_registered`.

**Commit:** `feat(nifty-calendar): add bi-weekly config and cycle policy`

---

## CB-2 — BiweeklyExitRule

**Files to change / create:**
- `src/nifty_calendar/exit_rules.py` — add `BiweeklyExitRule` and register it (additive); `ExitDecision` gains `REDEPLOY_SAME_PAIR` and `RECENTRE_OFF_CENTRE` members.
- `tests/unit/nifty_calendar/test_exit_rules_biweekly.py`

**Before any code:** `get_code_snippet("MonthlyExitRule")`, `ExitDecision`, `ExitRule`; `search_graph("ExitDecision")` for every consumer so new members do not break an exhaustive match.

**What to implement:** priority order, fixed and documented:

1. `DTE_GUARD` -> `TIME_EXIT` (past the 7-day hard exit).
2. `TARGET` (executable P&L at or above ₹1,600 per lot): if a same-pair redeploy is still allowed (near DTE above the exit-by threshold) return `REDEPLOY_SAME_PAIR`, else `TIME_EXIT`-style close.
3. Breach (confirmed close beyond a breakeven): within day 3-4 return `RECENTRE`, afterwards `CLOSE_BREACH_LATE`.
4. Day 4-5 with no target and no breach: spot 200 or more points from the entry short strike returns `RECENTRE_OFF_CENTRE`; otherwise `HOLD` (carry to the planned exit).
5. `HOLD`.

The 200-point threshold and the day windows are config fields (defaults from the video), not literals. Inputs come from rebuilt `PaperPosition` state, not memory, except the breach-confirmation spot
history (resets on a daemon restart; accepted limitation documented in CM-4). Redeploy decisions only return `REDEPLOY_SAME_PAIR`; the same-day ledger collision is handled by the caller in CB-3.

**Tests:** one per decision · `test_200_point_boundary_199_holds_200_recentres` · `test_target_with_room_redeploys_same_pair` · `test_target_late_closes_without_redeploy` ·
`test_priority_dte_guard_beats_target` · `test_early_target_flagged_spread_artifact`.

**Commit:** `feat(nifty-calendar): add bi-weekly exit rule`

---

## CB-3 — Register the second variant

**Files to change / create:**
- `scripts/monitor_daemon.py` — register `paper_nifty_calendar_biweekly` beside the monthly one (additive).
- `scripts/strategies/nifty_calendar/paper_calendar_entry.py`, `paper_calendar_snapshot.py` — a `--variant monthly|biweekly` flag selecting a registry entry (extend CM-7 scripts; no fork).
- `src/notifications/` label `Cal BW`; tests. No payoff registration (deferred to chart-model-overlay).

**Before any code:** read the CM-7 scripts as shipped, `get_code_snippet` on the variant registry from CM-3, and `FORMATTING.md` for the label. The shell must need **no** change; if it does, stop
(scope guard).

**What to implement:**

1. Variant lookup by a `dict` registry (config, policy, rule) as defined in CM-3; the scripts do `REGISTRY[args.variant]`, no `if`/`elif` chain.
2. Handoff: the entry script asks `CycleCalendar.active_variant(today)` and exits quietly (logged) if its own variant is not the active one, so cron can run both unconditionally.
3. Re-centre and same-pair redeploy send one combined Telegram message, as the monthly re-centre does.
4. Registration in the daemon and the EOD summaries; confirm both strategies show in open positions and strategy P&L.
5. Same-day redeploy guard. `paper_trades` is `UNIQUE(strategy_name, leg_role, instrument_key, trade_date, action)` with `ON CONFLICT DO NOTHING`, so a same-pair redeploy (or re-centre) that lands on
   the entry date of the cycle it replaces, at the same ATM strike, would have its second SELL silently dropped and the ledger would be wrong. The redeploy path must detect a dropped insert (no new
   row returned), log it and not proceed as if the leg was opened. Decide with Animesh whether to defer the redeploy to the next day in that case or to pick the adjacent strike; default is defer,
   logged, with a Telegram WARN. Unlikely but cheap to test, and a silent drop here would corrupt cycle P&L.

**Tests:** `test_registry_lookup_both_variants` · `test_entry_script_noops_when_other_variant_active` · `test_biweekly_label_renders` · `test_unknown_variant_rejected` ·
`test_same_day_same_strike_redeploy_is_detected_not_dropped_silently`.

**Commit:** `feat(scripts): wire bi-weekly nifty calendar variant`

---

## CB-4 — Full-month integration test and close-out

**Files to change / create:** `tests/unit/nifty_calendar/test_full_cycle.py` (offline, fixtures only); docs per CLAUDE.md Step 5a; epic `README.md` status; `src/nifty_calendar/CLAUDE.md`; cutover
note.

**What to implement:**

1. Fixture-driven walk across a month starting the first session after a monthly expiry (the Wednesday, 10:30 IST): monthly entry, monthly exit (target or day 7-10), bi-weekly entry, successive
   bi-weeklies, last bi-weekly exit before the next monthly window, monthly entry again. Uses `MockBrokerClient`, an in-memory `PaperStore`, no network.
2. Asserts per date: exactly one variant active, no overlapping open positions across the two strategy names, no entry on a holiday, every close has a recorded exit event, cycle P&L groups four legs
   into one round trip per strategy.
3. Update the cutover note: both cron entries, the order they run in, how to confirm the handoff in the first live paper week.
4. `python -m scripts.dev.reflow_md` on new `.md` files; `python -m pytest tests/unit/ --tb=no -q` green; Step 5d close-out.

**Tests:** `test_full_month_two_variants` · `test_no_overlap_between_variants` · `test_each_close_has_exit_event` · `test_holiday_month_variant`.

**Commit:** `docs(plan): close nifty-calendar bi-weekly story`
