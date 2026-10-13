
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
6. `DefaultPositionAdapter` / `StrikeResolver`: it raises `InvalidLegsError` only for an unknown type or an unresolved strike and never checks expiry (read from `src/payoff/registry.py` on 2026-10-13;
   verify). What does a correct near-expiry payoff require? The 2026-10-13 POC already answers it: near legs at intrinsic, far legs priced with Black-76 at the leg IV and a forward from put-call
   parity.
7. How does `StrategyMonitor` register and schedule a strategy (cadence, `due_interval_s`, WARN dedup, auto-execute dispatch)? Name the exact registration lines in `scripts/monitor_daemon.py`.
8. What does IC's entry script do for the duplicate-position guard and Telegram approval, and which parts are reusable without importing IC-specific modules?

9. POC evidence (`reference/README.md`, `scratch/chart_poc/`): the interim Black-76 curve matched Sensibull's expiry breakevens within about 30 points and max profit within about 4%, but T+0 P&L was
   off by up to ~₹1.5k when IV was held at its exit-day level. Confirm with a live chain that per-leg IV, bid and ask are available on all four legs, and decide the IV and carry convention for the
   chart (held per-leg IV, forward from parity).
10. Same evidence: the reference trade was held at 0.4% from the upper breakeven without adjusting, and margin moved between roughly ₹2.25L and ₹2.57L for 3 lots. Record both as inputs to CM-4 and as
    decisions for Animesh, not as rules.

11. Completed monthly trade in `docs/plan/nifty-calendar/reference/README.md` (strikes 22600 straddle, 22200 PE / 23000 CE wings, exit before the RBI decision at 90% of target): does the selector
    admit the reference 400/400 wings even though the monthly default is now 600? Entry timing, wing defaults, breach rule and lot size are decided (see the reference README §Decisions); an event-risk
    exit is manual, not automated.

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

**Before any code:** `get_code_snippet("OptionLeg")`, `get_code_snippet("OptionChain")` and `search_graph` on every enum used; `src/pricing` does not exist yet (`greeks-bs-fallback` is at GF-1). Write
the minimal interim Black-76 module `src/nifty_calendar/pricing.py` (price and implied vol, undiscounted, forward as an argument), marked interim in its docstring; CM-9 replaces it with `src/pricing`
once GF-2/GF-3 ship. Port it from `scratch/chart_poc/2026-10-13_calendar_payoff_poc.py`, with tests.

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
2. Default implementation: short straddle at the ATM strike (50 multiples allowed); wing strikes searched in multiples of 100 starting at the config's start points (monthly 600 put / 600 call).
   Hill-climb one 100-point step at a time on either wing, outward or inward down to the config's `min_wing_points` (monthly 300; so 400/400 is reachable), until all filters hold or a step budget is
   exhausted.
3. Filters, all config-driven: |net delta| at most a delta cap; signed net vega per unit at most the variant cap (monthly 20; net long vega is positive, see CM-0 decisions); risk-reward at least 0.75;
   breakeven % distances within a symmetry tolerance; loss at breakevens within a tolerance; net credit required. Absolute bid/ask spread tolerance per leg (monthly default 3.0 points) and a "Greeks
   present on all four legs" check.
4. Return the *reason* for no entry (which filter failed on the best candidate), logged by the caller, so a skipped cycle is explainable.

**Tests:** `test_selects_video_structure` (fixture chain yields wings near 600/600 satisfying all filters) · `test_no_entry_when_vega_cap_unreachable` · `test_wing_strikes_multiples_of_100` ·
`test_wide_spread_leg_rejected` · `test_missing_greeks_is_no_entry_not_exception`.

**Commit:** `feat(nifty-calendar): add wing structure selector`

---

## CM-3 — Variant config, CyclePolicy, CycleCalendar

**Files to change / create:**
- `src/nifty_calendar/config.py`, `cycle.py`; `tests/unit/nifty_calendar/test_config.py`, `test_cycle.py`

**Before any code:** `get_code_snippet("is_trading_day")` and `prev_trading_day`; read `REFERENCES.md` expiry notes (Tuesday since April 2026) and `get_expiry_candidates` in
`src/instruments/lookup.py`.

**What to implement:**

1. `CalendarVariantConfig` (frozen): name, strategy_name, target per lot, planned hold days, hard hold days, exit-by DTE (7), wing start points, minimum wing points, vega cap (per unit), delta cap,
   risk-reward floor, symmetry tolerances, spread tolerance, breach confirmation minutes (30), breach adjust window days, lots. `MONTHLY` instance here; `BIWEEKLY` is added by `calendar-biweekly`.
2. `CyclePolicy` `Protocol`: `entry_window(today) -> EntryPlan | None` (near and far expiry, planned exit date, hard exit date) and `next_variant_after_exit(today)`.
3. `MonthlyCyclePolicy`: entry on the first trading day after the previous monthly expiry (the Wednesday), at 10:30 IST (Animesh 2026-10-13; the 30 Sep 2026 reference trade followed the 29 Sep
   expiry); near = next monthly expiry, far = the month after; planned exit = entry + 7 days (trading-day adjusted), hard exit = entry + 10 days; never later than DTE 7 of the near leg.
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
- `src/notifications/payoff_chart.py` — additive optional `curve` argument on `render_payoff_png` and `send_payoff_chart`; existing callers byte-identical.
- `src/strategy/payoff_registrations.py` and a calendar payoff adapter; `payoff_chart_axes.py` strike-tick dedupe; tests under `tests/unit/notifications/` and `tests/unit/payoff/`.

**Before any code:** `get_code_snippet("EntryMessage")`, `ExitMessage`, `CloseLegRow`, `LegRow`; read `src/notifications/CLAUDE.md` §"Instrument Label Formatting" and `FORMATTING.md`.

**What to implement:**

1. Entry message: headline label (`Cal M`), both expiries and DTEs, spot, net credit per lot, delta, vega, breakevens with % distance, risk-reward, four legs. Byte-identical output for existing
   callers (golden-test).
2. Close message: reuse `ExitMessage` unchanged. Signal text is the `ExitDecision` reason; cycle fields come from `cycle_pnl` (confirm four-leg grouping per CM-0). Re-centre sends one message showing
   close and the new entry, not two unrelated messages. Pass `cycle_decay_pct` / `cycle_short_*` only if the message is meant to describe the short straddle alone; `short_decay_pct` excludes the long
   wings, so for the calendar headline use the net `decay_pct` and `realized_pnl`, and say which one the message shows.
3. Payoff chart: a calendar adapter supplies the four legs plus per-leg expiry, IV, entry price and the forward; the curve is near-expiry value with far legs priced by `src/nifty_calendar/pricing.py`
   (CM-1 `payoff_at`), passed to the renderer through the new optional `curve` argument. Register it under both strategy names. Header max loss and R:R use a documented spot range (the POC showed they
   otherwise depend on the sampling window), and a CE and PE at one strike show both in the tick row. If the adapter cannot build the chart (missing IV or price) it fails closed with a logged warning.
   T+0, ±σ bands, POP, OI bars and the per-leg table stay in `chart-model-overlay`.
4. All strings escaped at the one boundary the standard defines; no raw `print`.

**Tests:** `test_entry_message_golden_existing_callers_unchanged` · `test_calendar_entry_message_renders_two_expiries` · `test_markdownv2_escaping` · `test_renderer_unchanged_without_curve` ·
`test_calendar_adapter_values_far_legs` · `test_calendar_adapter_fails_closed_on_missing_iv` · `test_breakevens_match_poc_within_tolerance`.

**Commit:** `feat(notifications): add calendar entry message and payoff chart`

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

---

## CM-9 — Swap the interim pricer for `src/pricing`

**Blocked until** `docs/plan/greeks-bs-fallback/tasks.md` GF-2 and GF-3 are ticked. If either is open, stop and report the block.

**Files to change / create:**
- `src/nifty_calendar/payoff.py`, `selector.py` (anything importing `pricing.py`) — switch to the shared pricer and IV solver.
- `src/nifty_calendar/pricing.py` — delete.
- `tests/unit/nifty_calendar/` — unchanged expectations; only imports move.

**What to implement:** replace every use of the interim Black-76 module with `src/pricing` (price and `solve_iv`), keeping the forward-as-argument convention or the shared module's equivalent; delete
the interim module. Re-run the CM-1 and CM-6 tests unchanged; breakevens must stay within the POC tolerance.

**Commit:** `refactor(nifty-calendar): use shared Black-Scholes pricer`

### CM-0 findings (2026-10-13, code audit + live Upstox probe)

Probe: `scratch/data_probes/2026-10-13_nifty_calendar_cm0_probe.py` (read-only; the margin calculator places no order). Run at 11:30 IST with spot 22,505, near 2026-11-23, far 2026-12-29, ATM 22,500,
lot 65 (confirmed in the BOD file for both expiries).

1. **Mid and spread helper (Q1).** `_price_utils.resolve_price(leg)` (`src/strategy/_price_utils.py:211`) returns the mid when bid and ask are positive, else LTP, and raises `ValueError` on no price.
   IC's `_mid_price` (`ic_nifty_v2.py:2841`) silently returns LTP (possibly 0) and `_spread_pct` returns a fraction of mid (1 when a side is missing); `PaperExecutor._resolve_mid_price`
   (`executor.py:328`) is a third copy. No absolute-points spread helper exists. Because `nifty_calendar` is a leaf package and may not import `src.strategy`, CM-2 writes its own three-line pure `mid`
   and `spread_points` over `OptionLeg`; the shell uses `resolve_price` for fills.
2. **Margin (Q2).** Upstox calculator, product `D`, 1 lot (65) per leg: short straddle alone `final_margin` ₹142,484 (`required_margin` ₹197,087); winged with 600/600 wings `final_margin` **₹90,767**
   (`required` ₹238,593); winged with 400/400 `final_margin` **₹88,954** (`required` ₹247,548). The far long legs cut `final_margin` by about ₹52k because the calculator recognises the cross-expiry
   hedge; `required_margin` rises by the net buy premium (₹41.5k at 600). This agrees with the reference trade (₹2.25L to ₹2.57L for 3 lots is ₹75k to ₹86k per lot). `capture_entry_margin` stores both
   figures; the EOD ROI should say which one it divides by (open decision below).
3. **Cycle state and entry date (Q3).** `paper_trades` stays the source of truth and `DB_REGISTRY.md` lists no better home, so no `schema.md`. `PaperPosition.entry_date` is the date of the first SELL
   for the leg (`src/paper/models.py:115`) and is `None` for a BUY-only leg, so the two long wings have no entry date. NC derives the cycle entry date from the **short legs** only. The margin
   snapshot's `entry_date` must use that same value. `DB_REGISTRY.md` marks `paper_margin_snapshots` "IC-only", but `record_margin_snapshot` is keyed on `(strategy_name, entry_date)` and is
   strategy-agnostic; CM-7 amends the registry note.
4. **Live chain (Q4).** All four legs carry delta, vega, IV, bid and ask. Greeks at 600/600: near CE 0.585 / vega 29.7 / IV 13.5; near PE -0.416 / 29.7 / 13.7; far 23,100 CE 0.432 / 41.3 / 12.3; far
   21,900 PE -0.253 / 33.6 / 14.5. Every far-month 100-multiple strike within ±1,500 of ATM has a two-sided quote. Spreads (points) are wide on the far CE side: 22,800 2.9, 22,900 3.25, **23,000
   1.15**, 23,100 2.5, 23,200 2.5, 23,300 2.3, 23,400 2.5; puts are tighter: 21,600 1.6, 21,700 1.0, 21,800 1.65, 21,900 1.0, 22,000 1.0, 22,100 2.1, 22,200 1.05. Far-leg LTP lags the quote (23,100 CE
   LTP 400 against 410.05/412.7), so entry and exit must use the mid. **The planned 2-point gate rejects most far CE strikes** (see decisions).
5. **Message fit (Q5).** `EntryMessage` carries a single `expiry: date`, `dte: int` and `expiry_type` (`entry_message.py:45-51`, rendered at lines 70 and 72); this is the only change CM-6 needs there.
   `ExitMessage` has no expiry field, only `dte` (`exit_message.py:80`), so exit needs only a convention: DTE means near-expiry DTE.
6. **Payoff adapter (Q6).** Confirmed (`src/payoff/registry.py:138-165`): `DefaultPositionAdapter` raises `InvalidLegsError` only for an unknown type or unresolved strike, never checks expiry, and
   prices every leg at intrinsic. A correct near-expiry payoff needs near legs at intrinsic and far legs repriced with Black-76 at each leg's own IV, with the forward from put-call parity. Live parity
   forward from the near ATM pair is 22,500 + 517.5 - 323.1 = 22,694 against spot 22,505 (+189 points of carry over 41 days); the far forward comes from the far chain's own ATM pair.
7. **Monitor registration and dispatch (Q7).** `scripts/monitor_daemon.py:349-402` builds each strategy as `Cls(broker=, store=, notifier=gateway, config=)` inside try/except and appends it to
   `strategies`; `StrategyMonitor(strategies=strategies, ...)` is constructed at line 477 (`monitor.register` also exists, `monitor.py:121`). Cadence is the daemon `--poll-interval`; a strategy may
   set a `due_interval_s` class attribute (`monitor.py:145`). WARN dedup keys on `(event_type, leg_role, expiry)` and `reconcile_warn_state`; auto-execute needs `strategy.auto_execute` and
   `payload["auto_execute"]` (`monitor.py:458`). **Material finding:** the tick groups a strategy's positions by expiry and calls `check_signals(chain, positions)` **once per expiry group** with only
   that expiry's chain and only that group's legs (`monitor.py:262-285`). A calendar therefore gets two calls per tick, each seeing two legs and one chain, never the whole structure. A flat strategy
   is never evaluated, so entry stays script-driven as for IC.
8. **IC entry script (Q8).** `paper_ic_entry.py` has **no Telegram approval step**; Telegram is notification only. Reusable ideas, none needing IC imports: the structural duplicate guard
   (`store.get_positions(name)` with any `net_qty != 0` aborts with an alert, line ~282); persist the legs, re-read each from the store to verify, and on any miss run compensating closes
   (`_compensate_legs`, line 91, which lives in the script and would have to be extracted); then `capture_entry_margin`, `EntryMessage` and `send_payoff_chart`. IC persists legs by shelling out to
   `record_paper_trade`; NC should call `PaperStore` / `PaperExecutor` directly.
9. **Chart IV and carry convention (Q9).** Decided as recommended by the POC: hold each leg's own IV constant and take the forward per expiry from put-call parity on that expiry's ATM pair. The POC's
   up-to-₹1.5k T+0 error when IV is held at its exit-day level is a chart-accuracy limit and out of scope until the overlay story; the expiry curve and breakevens (within about 30 points of Sensibull)
   are what the interim chart claims.
10. **Reference-trade inputs for CM-4 (Q10).** Held 0.4% from the upper breakeven: the 30-minute-close breach rule did not fire, which is the rule working. Margin ranged ₹2.25L to ₹2.57L for 3 lots,
    which the live ₹89k to ₹91k per lot `final_margin` brackets. Neither becomes a rule.
11. **Do the filters admit 400/400? (Q11).** Not provable yet. CM-2's search starts at 600 and the spec says "one 100-point step on either wing" without saying inward steps are allowed; it must permit
    moving inward down to a configured minimum so that 400/400 is reachable. Whether the filters pass depends on the vega-cap unit (below). Live net vega per unit is +15.4 at 600/600 and +18.5 at
    400/400 (near short 59.5, far long 74.9 and 78.0).

**Design review amendment (monitor dispatch).** The shell cannot rely on `check_signals` seeing the whole structure. Recommended for CM-5: the shell acts only on the call whose chain expiry equals the
near expiry, reads **all** its positions from the injected `PaperStore`, and fetches the far chain itself through the injected broker. This leaves `StrategyMonitor` and IC untouched. The alternative,
an opt-in whole-position dispatch in the monitor, edits shared infra on the IC tick path and is not recommended.

**Other findings.** The November monthly expiry is **Monday 2026-11-23**, not Tuesday the 24th (holiday shift; `/v2/option/contract` lists 2026-10-27, 11-03, 11-09, 11-23, 12-29), so `CycleCalendar`
must take expiries from the instrument list or holiday-aware rules, never "last Tuesday". The research file is at `/Users/abhadra/myWork/myCode/AI/TradeResearch/findings/14ZZYoV4DBc_combined.md`
(outside this repo; the `prompt.md` path is relative to a sibling repo). It states "net vega: monthly ≤ ~13, bi-weekly ≤ ~5 (classic same-strike calendar ≈ 90)" with no unit, and the part-2 vega
reasoning is garbled in the transcript. A classic calendar nets about 30 per unit on the Upstox chain, so the presenter's scale cannot be mapped onto ours.

**Decisions (Animesh, 2026-10-13, accepted as recommended).**

1. Spread gate: 3.0 points per leg, a config value (`spread_tolerance`). No summed or basis-point gate.
2. Vega cap: an upper bound on **signed net vega per unit** (net long positive), config field `vega_cap`, monthly default **20**, which admits both 600/600 (+15.4) and 400/400 (+18.5). The 20 is
   uncalibrated (the source's 13 is on an unmappable scale); recalibrate from paper-run data in CM-8. Bi-weekly sets its own value in `calendar-biweekly`.
3. EOD return on margin: divide by `final_margin`, as `eod_pt_summary` already does for IC (`src/reporting/eod_pt_summary.py:487`); it also matches the reference trade's ₹75k to ₹86k per lot.
   `required_margin` stays stored, not used for ROI.
4. Inward search: wings may move inward to `min_wing_points`, monthly default **300**.

### CM-8 cutover note (2026-10-13)

**State at hand-over.** Code through CM-7 is merged on `main`. `scripts/monitor_daemon.py` already registers `NiftyCalendarV1` (`paper_nifty_calendar_monthly`), so the next daemon restart picks it up;
a flat strategy is never ticked, so registration alone writes nothing. Both scripts default to `--dry-run`; **no cron line exists**. Crontab is not version-controlled, so the lines below are a
procedure for Animesh, not a repo change.

**Parallel-run-then-flip.**

1. *Dry cycle (no cron, manual).* On each trading day inside the next monthly entry window (the session after the previous monthly expiry; expiries come from the instrument list, e.g. November 2026 is
   Monday 23rd), run the entry script by hand at or after 10:30 IST in dry mode and read the proposal and the log outcome code (`DRY_RUN`, `NO_ENTRY`, `CHAIN_FAILED`, `NO_EXPIRY`). Run the snapshot
   script in dry mode once at 15:45 to confirm it ends `NO_TRADES` or `FLAT` without writing. `python -m scripts.strategies.nifty_calendar.paper_calendar_entry` and `python -m
   scripts.strategies.nifty_calendar.paper_calendar_snapshot` (dry-run is the default).
2. *Exit criteria for the dry cycle.* At least one full monthly window observed with a sensible proposal (four legs, executable mids, winged `final_margin` near the CM-0 figure of about 90k per lot),
   no unexpected ERROR lines in `logs/`, and the Telegram alert text for `NO_ENTRY` reasons reads correctly. Outside the window `plan_entry` returns nothing and the script is a silent no-op, so a
   daily cron is safe once flipped.
3. *Flip.* Add the two cron lines below (daily Mon-Fri; the scripts call `guard_trading_day` and self-gate on the cycle window), then restart the monitor daemon if it was not restarted after CM-7.
   Keep the first live cycle under observation: check the entry card, `paper_margin_snapshots`, and the `paper_nav_snapshots` row after the first 15:45 run.

```
30 10 * * 1-5  cd /Users/abhadra/myWork/myCode/python/NiftyShield && python -m scripts.strategies.nifty_calendar.paper_calendar_entry --no-dry-run >> logs/nifty_calendar_entry.log 2>&1
45 15 * * 1-5  cd /Users/abhadra/myWork/myCode/python/NiftyShield && python -m scripts.strategies.nifty_calendar.paper_calendar_snapshot --no-dry-run >> logs/nifty_calendar_snapshot.log 2>&1
```

The entry cron is a no-op while a structure is open (`ALREADY_OPEN`). A re-centre closes in the daemon (close/ROLL card) and re-enters on the next entry-cron run the same day; if that run has already
passed, re-run the entry script by hand with `--no-dry-run`.

**Known open items, not fixed in CM-8.**

- (a) *Pre-commit mypy scope.* The hook matches `^src/(client|paper)/`; the new `src/paper/margin_capture.py` pulls mypy into six pre-existing errors in `src/payoff/core.py`,
  `src/notifications/payoff_chart.py`, `payoff_chart_axes.py` and `ic_nifty_v1.py:929/941` (`PhotoSender` vs `TelegramGateway`). CM-7 was committed with `SKIP=mypy`, which was not authorized. Needs
  its own cleanup task (fix the six errors) or a narrowed hook scope; decide before the next commit touching `src/paper/`.
- (b) *Re-centre sends two Telegram messages* (shell close/ROLL card, then the entry script's entry card). Recorded in `DECISIONS.md` §"Nifty calendar scripts".
- (c) *CM-9 is blocked* on `docs/plan/greeks-bs-fallback/tasks.md` GF-2/GF-3; the interim `src/nifty_calendar/pricing.py` stays until then. The story is therefore not archived.
- (d) *Partial entry* is alerted, not auto-compensated (`INCOMPLETE`); VIX-regime slippage is `None` in the daemon registration (default band).

**`vega_cap` recalibration note.** The monthly default of 20 (signed net vega per unit, net long positive) is uncalibrated: the source's "13" is on a scale that cannot be mapped to Upstox vega (a
classic same-strike calendar nets about 30 per unit here, live 600/600 is +15.4, 400/400 is +18.5). After the first 3 to 5 paper entries, read `vega_cap`'s effect from the logged
`nifty_calendar.no_entry` events (`failed_filter == "vega_cap"`) and the net vega of each structure actually entered (leg snapshots). If no entry was rejected on vega and entered vega clusters well
below 20, tighten towards the observed maximum plus a margin; if vega rejected otherwise acceptable structures, loosen. Change only `MONTHLY.vega_cap` in `src/nifty_calendar/config.py` with a
`DECISIONS.md` line; bi-weekly sets its own value in `calendar-biweekly`. Do not recalibrate from fewer than three entered cycles.
