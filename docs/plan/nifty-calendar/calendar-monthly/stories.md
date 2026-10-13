
# Calendar Monthly - shared core + monthly variant — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

Spec source: `TradeResearch/findings/14ZZYoV4DBc_combined.md` (part 2 wins on conflict). Terms: **short straddle** = ATM CE+PE sold in the near expiry; **wings** = OTM CE+PE bought in the far expiry;
**structure** = those four legs.

---

## CM-0 — Prior-art audit and live-infra readiness probe

**Files to change / create:**
- `docs/plan/nifty-calendar/calendar-monthly/stories.md` — append a "CM-0 findings" section; amend `prompt.md` Design review if anything below differs.
- A throwaway probe goes in `scratch/` per `SCRATCH.md`; nothing under `src/`.

**Before any code:** `git log --oneline -10` on `src/strategy/` and `src/paper/`; `search_graph` for each shared symbol named below.

**What to answer (each with file and symbol evidence):**

1. Does the mid/spread helper exist outside `ic_nifty_v2.py`? (`_price_utils.resolve_price` is the candidate; IC's `_mid_price` and `_spread_pct` are private IC methods.)
2. **Pre-answered, see findings below.** Remaining for CM-0: call `broker.get_order_margin` with the real four legs (needs a live Upstox token) and record the winged calendar's `final_margin` per lot.
   The video's ₹1.2L/lot is for the classic calendar only.
3. **Pre-answered, see findings below.** Remaining for CM-0: confirm against `DB_REGISTRY.md` that no existing table is a better home, and that `PaperPosition.entry_date` resolves for a four-leg,
   two-expiry position.
4. Probe a live or recorded Upstox chain: for the current monthly pair, do all four legs carry delta, vega, IV, bid and ask? Which strikes (multiples of 100, far month) have a usable bid/ask?
5. `EntryMessage` and `ExitMessage` fit: list every field that assumes one expiry. (`reconstruct_cycles` grouping is pre-answered, see findings below; `EntryMessage` is confirmed to carry a single
   `expiry` / `dte`.)
6. `DefaultPositionAdapter` / `StrikeResolver`: does it raise `InvalidLegsError` on a mixed-expiry position, and what does a correct near-expiry payoff require?
7. How does `StrategyMonitor` register and schedule a strategy (cadence, `due_interval_s`, WARN dedup, auto-execute dispatch)? Name the exact registration lines in `scripts/monitor_daemon.py`.
8. What does IC's entry script do for the duplicate-position guard and Telegram approval, and which parts are reusable without importing IC-specific modules?

9. Reference-trade evidence in `docs/plan/nifty-calendar/reference/README.md`: does `compute_payoff` handle only expiry intrinsic value, and does a calendar's near-expiry curve need a Black-Scholes
   step with an IV input for the far legs? Can our T+0 curve match the reference chart's projected P&L within about ₹900?
10. Same evidence: the reference trade was held at 0.4% from the upper breakeven without adjusting, and margin moved between roughly ₹2.25L and ₹2.57L for 3 lots. Record both as inputs to CM-4 and as
    decisions for Animesh, not as rules.

11. Completed monthly trade in `docs/plan/nifty-calendar/reference/README.md` (strikes 22600 straddle, 22200 PE / 23000 CE wings, exit before the RBI decision at 90% of target): does the selector
    admit 400/400 wings, does the entry-timing phrase match the real entry date, and is an event-calendar exit needed in `ExitDecision`? Record as decisions for Animesh.

**Tests:** none (research task). **Done:** each answer written with evidence; unresolved items listed as explicit decisions for Animesh.

**Commit:** `docs(plan): record nifty-calendar CM-0 audit findings`

### CM-0 findings recorded at planning time (2026-10-12, from reading the IC code)

These were read from the code during epic planning. CM-0 re-verifies them against the code as it stands then, and appends its own live-probe results below this block.

- **Margin (question 2).** IC does not compute margin. `capture_entry_margin` in `scripts/strategies/ic/ic_entry_gates.py` runs once in the entry script, after all legs are persisted. It sends
  `(instrument_key, action, quantity)` tuples to `broker.get_order_margin(...)` (Upstox margin calculator, needs the live token) and stores `required_margin` and `final_margin` through
  `PaperStore.record_margin_snapshot`, upserted on `(strategy_name, entry_date)`. It is non-fatal by design: on any failure it logs `capture_entry_margin.failed` and returns `None`, and the EOD report
  then skips ROI-on-margin for that cycle. Consequences: NC's margin is a broker figure, unknown for the winged structure until CM-0 probes it; and the function sits in a module that imports pandas
  and the backtest IVR code, so NC must not import it from there (extraction task in CM-7).
- **Cycle state (question 3). No table needed, so no `schema.md`.** IC keeps only roll counters and the original credit in memory (`_rolls_executed`, `_original_ic_credit`; lost on restart) and
  rebuilds everything else from `PaperPosition` (`avg_sell_price`, `avg_cost`). NC can do the same: entry date from the position, entry short strike from the instrument key, planned and hard exit
  dates as pure functions of the entry date or near expiry via `CyclePolicy`, target as a config constant. The one in-memory item is the breach-confirmation spot history, which a daemon restart
  resets; that can delay a re-centre by up to the confirmation window, which is the safe direction (see CM-4).
- **Cycle P&L grouping (question 5).** `reconstruct_cycles` cuts a cycle when every seen `leg_role` is at net-zero quantity and is blind to instrument and expiry, so four distinct leg roles across two
  expiries group into one round trip, and a re-centre (close all, then enter) produces two cycles as intended. Caveats: `short_decay_pct` counts short legs only, so the long wings are absent from it
  (the net `decay_pct` and `realized_pnl` include them); `entry_credit_per_unit` assumes uniform lot quantity across legs, true at 1 lot.
- **Ledger uniqueness.** `paper_trades` is `UNIQUE(strategy_name, leg_role, instrument_key, trade_date, action)` with `ON CONFLICT DO NOTHING`. A second trade with the same role, instrument, date and
  action is silently dropped. This matters for any same-day close-and-re-enter on the same strike (see CB-3).

---

## CM-1 — Models and payoff maths (pure)

**Files to change / create:**
- `src/nifty_calendar/__init__.py`, `models.py`, `payoff.py`, `errors.py`
- `tests/unit/nifty_calendar/__init__.py`, `test_models.py`, `test_payoff.py`

**Before any code:** `get_code_snippet("OptionLeg")`, `get_code_snippet("OptionChain")` and `search_graph` on every enum used; reuse the existing Black-Scholes implementation (`greeks-bs-fallback`
story) via `search_graph("black scholes")` — do not write a second one.

**What to implement:**

1. Frozen dataclasses: `CalendarLeg` (instrument key, strike, option type, expiry, side, qty in lots, entry price, delta, vega, iv), `CalendarStructure` (short straddle plus wings, net credit),
   `StructureMetrics` (net delta, net vega, risk-reward, breakeven low and high with % distance from spot, loss at each breakeven, net credit).
2. `payoff_at(structure, spot, as_of, iv_shift)`: value of the structure at `as_of` (default the near expiry). Near legs at intrinsic; far legs repriced with Black-Scholes at remaining time and leg IV
   plus `iv_shift`. All money `Decimal`; float only inside the BS call and converted at the edge.
3. `compute_metrics(structure, spot)`: delta and vega by summing leg Greeks; breakevens found by bracketed search on `payoff_at` over a spot range; risk-reward = max profit / max loss over that range;
   loss at each breakeven per the video's definition (loss at the other breakeven's distance), documented in the docstring.
4. `CalendarError` hierarchy (`InvalidStructureError`, `MissingGreeksError`); a leg without delta, vega or iv raises `MissingGreeksError`.

**Tests (offline):**
- `test_metrics_match_video_sample` — 22,700 short straddle, wings 600 put / 500 call away: delta near 0, breakevens approx 2.5% / 2.4% within a stated tolerance, using a fixture chain built from the
  video's numbers.
- `test_iv_shift_directional` — +3 IV points raises payoff, -3 lowers it (sign check against the video's +4% / -1.5%).
- `test_missing_greeks_raises` — a leg with `None` vega raises `MissingGreeksError`.
- `test_money_is_decimal` — every money field is `Decimal`.

**Commit:** `feat(nifty-calendar): add structure models and payoff maths`

---

## CM-2 — StructureSelector

**Files to change / create:**
- `src/nifty_calendar/selector.py`; `tests/unit/nifty_calendar/test_selector.py`

**Before any code:** `get_code_snippet` on `CalendarStructure`, `StructureMetrics` (from CM-1) and `OptionChain`; read `src/instruments/strike_selector.py` liquidity helpers and reuse where they fit.

**What to implement:**

1. `StructureSelector` as a `Protocol` with `select(chain_near, chain_far, spot, config) -> SelectionResult`. `SelectionResult` is either a structure or a `NoEntry(reason)`. Both are frozen.
2. Default implementation: short straddle at the ATM strike (50 multiples allowed); wing strikes searched in multiples of 100 starting at the config's start points (monthly 600 put / 500 call).
   Hill-climb one 100-point step at a time on either wing until all filters hold or a step budget is exhausted.
3. Filters, all config-driven: |net delta| at most a delta cap; net vega at most the variant cap (monthly 13); risk-reward at least 0.75; breakeven % distances within a symmetry tolerance; loss at
   breakevens within a tolerance; net credit required. Absolute bid/ask spread tolerance per leg (default 2 points) and a "Greeks present on all four legs" check.
4. Return the *reason* for no entry (which filter failed on the best candidate), logged by the caller, so a skipped cycle is explainable.

**Tests:** `test_selects_video_structure` (fixture chain yields wings near 600/500 satisfying all filters) · `test_no_entry_when_vega_cap_unreachable` · `test_wing_strikes_multiples_of_100` ·
`test_wide_spread_leg_rejected` · `test_missing_greeks_is_no_entry_not_exception`.

**Commit:** `feat(nifty-calendar): add wing structure selector`

---

## CM-3 — Variant config, CyclePolicy, CycleCalendar

**Files to change / create:**
- `src/nifty_calendar/config.py`, `cycle.py`; `tests/unit/nifty_calendar/test_config.py`, `test_cycle.py`

**Before any code:** `get_code_snippet("is_trading_day")` and `prev_trading_day`; read `REFERENCES.md` expiry notes (Tuesday since April 2026) and `get_expiry_candidates` in
`src/instruments/lookup.py`.

**What to implement:**

1. `CalendarVariantConfig` (frozen): name, strategy_name, target per lot, planned hold days, hard hold days, exit-by DTE (7), wing start points, vega cap, delta cap, risk-reward floor, symmetry
   tolerances, spread tolerance, breach confirmation minutes (30), breach adjust window days, lots. `MONTHLY` instance here; `BIWEEKLY` is added by `calendar-biweekly`.
2. `CyclePolicy` `Protocol`: `entry_window(today) -> EntryPlan | None` (near and far expiry, planned exit date, hard exit date) and `next_variant_after_exit(today)`.
3. `MonthlyCyclePolicy`: entry on the first trading day on or after the Tuesday following the previous monthly expiry; near = next monthly expiry, far = the month after; planned exit = entry + 7 days
   (trading-day adjusted), hard exit = entry + 10 days; never later than DTE 7 of the near leg.
4. `CycleCalendar`: pure function `active_variant(date, policies) -> variant name | None`, so a handoff between the two strategies is decided in one place and both stay independent. It receives
   policies by injection and holds no variant constants.

**Tests:** `test_entry_day_after_tuesday_expiry` · `test_holiday_pushes_entry_forward` · `test_hard_exit_never_inside_dte_7` · `test_exactly_one_active_variant_per_date` (fixture year, with only
`MONTHLY` registered it returns none outside the monthly window) · `test_config_frozen`.

**Commit:** `feat(nifty-calendar): add variant config and cycle policy`

---

## CM-4 — ExitRule and monthly rule

**Files to change / create:**
- `src/nifty_calendar/exit_rules.py`; `tests/unit/nifty_calendar/test_exit_rules.py`

**Before any code:** `get_code_snippet` on `StructureMetrics`, `EntryPlan` (CM-3); read `src/strategy/signal_exit.py` for the existing pure-evaluator shape and match it.

**What to implement:**

1. `ExitDecision` enum `(str, Enum)`: `HOLD`, `TARGET`, `RECENTRE`, `CLOSE_BREACH_LATE`, `TIME_EXIT`, `DTE_GUARD`. `ExitRule` `Protocol`: `evaluate(state, snapshot, now) -> ExitDecision`.
2. `state`: entry date, entry spot, entry short strike, the plan's dates, the frozen target. `snapshot`: spot, spot closes for the confirmation window, executable structure value (mid net of
   slippage), current breakevens (recomputed live from current IV).
3. `MonthlyExitRule` priority, fixed and documented: `DTE_GUARD` (near leg at or inside exit-by DTE) -> `TIME_EXIT` (past hard exit date) -> `TARGET` (executable P&L at or above target) -> breach:
   confirmed close beyond a breakeven for the config's minutes, then `RECENTRE` if within the first 7 days else `CLOSE_BREACH_LATE` -> `HOLD`.
4. Target is evaluated on executable value only; raw LTP is never an input. A target reached within the first trading day logs a flag (spread-artefact suspicion) but still follows the rule.
5. The breach-confirmation spot history is in-memory in the shell and resets on a daemon restart, delaying a breach decision by up to the confirmation window. Document this in the rule's docstring as
   an accepted, fail-safe-direction limitation; do not persist it unless CM-0 finds a cheap existing store (e.g. `IntradayMarketStore`) that already holds spot ticks.

**Tests:** one per decision plus `test_priority_order` (DTE guard beats target; target beats breach) · `test_breach_requires_full_confirmation_window` · `test_breach_day8_closes_not_recentres` ·
`test_ltp_inflated_value_does_not_trigger_target`.

**Commit:** `feat(nifty-calendar): add exit rule protocol and monthly rule`

---

## CM-5 — NiftyCalendarV1 shell

**Files to change / create:**
- `src/strategy/nifty_calendar_v1.py`; `tests/unit/strategy/test_nifty_calendar_v1.py`

**Before any code:** `get_code_snippet("PaperStrategy")`, `LegSpec`, `SignalEvent`, `ApprovedAction`; read `src/strategy/protocol.py`, `reentry_mixin.py` and the CM-0 findings. Use `trace_path` on
`StrategyMonitor` to see which methods it calls. Run `design-principles.md` SOLID triggers; record the outcome in this story's Design review.

**What to implement:**

1. Constructor-injected: broker, `PaperStore`, notifier, `PaperFillSimulator`, `StructureSelector`, `ExitRule`, `CyclePolicy`, `CalendarVariantConfig`. Nothing constructed inside.
2. `check_signals`: if flat and `CyclePolicy.entry_window(today)` is open, fetch both chains, run the selector, fail closed on `NoEntry` (log reason, one WARN per day via the monitor's dedup). If
   open, build the snapshot and call `ExitRule.evaluate`; map `TARGET`, `TIME_EXIT`, `DTE_GUARD` and `CLOSE_BREACH_LATE` to a close action and `RECENTRE` to close plus re-entry through `ReEntryMixin`.
3. `apply_action`: fills via the simulator (mid plus VIX-regime slippage); records four trades with distinct `leg_role`s (`short_call`, `short_put`, `long_call_wing`, `long_put_wing`) via
   `PaperStore.record_trade`; writes exit events. Idempotent under the ledger's `UNIQUE(strategy_name, leg_role, instrument_key, trade_date, action)`, and it must detect a dropped duplicate (record
   returned no new row) and log it, never assume the trade landed. State is rebuilt from `PaperPosition` on every tick; nothing about the cycle lives only in memory except the breach history (CM-4).
   Margin is captured by the entry script (CM-7), not by the shell, as IC does.
4. `describe_context` for the monitor. Strategy name comes from config; the file contains no `if variant` branch. Keep the class under roughly 400 lines; anything bigger belongs in a collaborator.

**Tests (MockBrokerClient, in-memory store):** `test_enters_monthly_cycle_records_four_legs` · `test_no_entry_when_greeks_missing` · `test_target_closes_all_legs` · `test_breach_early_recentres` ·
`test_double_apply_is_idempotent` · `test_no_variant_branch` (the class takes any config and works unchanged with a second fixture config).

**Commit:** `feat(strategy): add NiftyCalendarV1 paper strategy shell`

---

## CM-6 — Telegram messages and payoff chart

**Files to change / create:**
- `src/notifications/entry_message.py` — additive optional `far_expiry` / `far_dte` (or per-leg expiry) on `EntryMessage`; existing callers unchanged.
- `src/notifications/` calendar label and recentre-alert builder, if `alerts.py` is the right home (decide per `src/notifications/CLAUDE.md`).
- `src/strategy/payoff_registrations.py` and a calendar payoff adapter; tests under `tests/unit/notifications/` and `tests/unit/payoff/`.

**Before any code:** `get_code_snippet("EntryMessage")`, `ExitMessage`, `CloseLegRow`, `LegRow`; read `src/notifications/CLAUDE.md` §"Instrument Label Formatting" and `FORMATTING.md`.

**What to implement:**

1. Entry message: headline label (`Cal M`), both expiries and DTEs, spot, net credit per lot, delta, vega, breakevens with % distance, risk-reward, four legs. Byte-identical output for existing
   callers (golden-test).
2. Close message: reuse `ExitMessage` unchanged. Signal text is the `ExitDecision` reason; cycle fields come from `cycle_pnl` (confirm four-leg grouping per CM-0). Re-centre sends one message showing
   close and the new entry, not two unrelated messages. Pass `cycle_decay_pct` / `cycle_short_*` only if the message is meant to describe the short straddle alone; `short_decay_pct` excludes the long
   wings, so for the calendar headline use the net `decay_pct` and `realized_pnl`, and say which one the message shows.
3. Payoff chart: a calendar adapter that values far legs at the near expiry with BS (reusing CM-1 `payoff_at`), registered under both strategy names. If it cannot build the chart it fails closed
   (logged warning, no partial payoff), matching `InvalidLegsError` semantics.
4. All strings escaped at the one boundary the standard defines; no raw `print`.

**Tests:** `test_entry_message_golden_existing_callers_unchanged` · `test_calendar_entry_message_renders_two_expiries` · `test_markdownv2_escaping` · `test_payoff_adapter_values_far_legs` ·
`test_payoff_adapter_fails_closed_on_partial_position`.

**Commit:** `feat(notifications): add calendar entry message and payoff`

---

## CM-7 — Scripts, daemon and EOD wiring

**Files to change / create:**
- `scripts/strategies/nifty_calendar/__init__.py`, `paper_calendar_entry.py`, `paper_calendar_snapshot.py`
- `scripts/monitor_daemon.py` — register the strategy; `scripts/eod_summary.py` / `src/reporting/eod_pt_summary.py` — pick-up if not automatic.
- `tests/unit/scripts/` for pure helpers.

**Before any code:** read `LOGGING.md` fully; read `scripts/strategies/ic/paper_ic_entry_v2.py` and `paper_ic_snapshot.py` as patterns only. Note `process_variant` in the IC snapshot script is coupled
to IC classes — do not extend it.

**What to implement:**

1. Entry script: duplicate-position guard, `guard_trading_day`, chain fetch, shell `check_signals`, Telegram entry message, payoff chart send. `_SCRIPT_NAME =
   "scripts.strategies.nifty_calendar.paper_calendar_entry"`.
2. Snapshot script: writes `paper_nav_snapshots` and `paper_leg_snapshots` for the strategy, builds the EOD report with `build_leg_table` (legs, LTP, P&L, net delta and vega, days held, next exit
   date), sends it and the payoff chart. Own script, same shared renderers.
3. Register `paper_nifty_calendar_monthly` in `monitor_daemon.py` with the same pattern IC uses; confirm the EOD summaries list it in open positions and strategy P&L.
4. Cron lines go in the CM-8 cutover note, not in the repo crontab.
5. Margin: move `capture_entry_margin` out of `scripts/strategies/ic/ic_entry_gates.py` into a shared module (e.g. `scripts/strategies/_margin.py` or `src/paper/`, decided against the dedup doc's
   module-map test), keep an import shim or update the IC callers so IC behaviour is unchanged, and have the NC entry script call it after the four legs are persisted. It stays non-fatal. The IC
   change is mechanical and gets a golden test (same calls, same snapshot). If this is judged too invasive for this story, the fallback is a copy-free thin wrapper in the NC script that calls the same
   broker method, recorded as a deferred-dedup item in `DECISIONS.md`.

**Tests:** pure-helper tests only (leg-table rows, header builder); a dry-run mode against `MockBrokerClient` for both scripts, no network.

**Commit:** `feat(scripts): wire nifty calendar entry and snapshot`

---

## CM-8 — Close-out docs and cutover note

**Files to change / create:** `CONTEXT.md` (What Exists), `CONTEXT_TREE.md`, `DECISIONS.md`, `DB_REGISTRY.md` (only if CM-0 required a table), `REFERENCES.md` (strategy table), `TODOS.md`,
`docs/plan/README.md`, `src/nifty_calendar/CLAUDE.md` (new), `src/strategy/CLAUDE.md`, epic `README.md` status row.

**What to do:**

1. Per CLAUDE.md Step 5a: targeted `Edit` calls only. New module `CLAUDE.md` records the invariants: pure core, no I/O, one-way dependencies, executable-price valuation, no `if variant`.
2. Re-index the graph (`index_repository`) after confirming every new package has `__init__.py`.
3. Write the parallel-run-then-flip cutover: run the entry and snapshot scripts in dry mode for at least one full cycle alongside nothing live; only then add cron entries. List the exact cron lines.
4. Run `python -m scripts.dev.reflow_md` on every new `.md` in this epic.
5. `python -m pytest tests/unit/ --tb=no -q` green; then Step 5d session close-out.

**Commit:** `docs(plan): close nifty-calendar monthly story`
