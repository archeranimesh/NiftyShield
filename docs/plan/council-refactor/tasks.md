# council-refactor — Task Checklist

> Find the first unchecked item **assigned to you**. That is your only task for this session.
> Each task is tagged `[Claude]` or `[Antigravity]` — only pick up tasks tagged for you.
> If the next unchecked task is tagged for the other agent, stop and hand off.
> After completing: tick the box, append `| SHA: <sha>`, add one line to TODOS.md.
>
> **Story file to load based on task prefix:**
> | Task prefix | Story file |
> |---|---|
> | CR0 | `stories_infra.md` |
> | CR1a, CR1b, CR1c, CR1d | `stories_csp.md` |
> | CC-1, CC-2, CC-3, CC-4, CC-5 | `stories_cc.md` |
> | PP-1, PP-2, PP-3 | `stories_pp.md` |
> | COLLAR-1 | `stories_collar.md` (includes Addition A + B at end of file) |
> | DAEMON-FIX | `stories_daemon.md` |
> | CR2, CR3, NT-1, NT-2 | `stories_overlay.md` |
> | CR4 | `stories_close.md` |
> | AUTO-1 | `stories_auto.md` |
> | BUG-1 … BUG-5 | `stories_bugs_jun09.md` |
> | BUG-6, BUG-7 | `stories_bugs_overlay_state.md` |
| RPT-1, RPT-2, RPT-3 | `stories_track_report.md` |
>
> Also load `README.md` for shared context (signal tables, state machine, dependency order).
> Do NOT load `stories.md` — it is a historical archive.

**Prerequisite gate (run before CR0):**
- [x] `search_graph("ExitSignalEngine")` returns results (ES1 committed)
- [x] `search_graph("StrategyMonitor")` returns results (PB1.2 committed)
- [x] `search_code("send_approval_request")` in `monitor.py` — confirm mismatch

---

## Phase RPT — Track Report Fixes + CLI Redesign

> Story file: `stories_track_report.md`. Fix RPT-1 before RPT-2 (inception mode depends on it).

- [ ] **RPT-1** `[Claude]` — Fix closed overlay legs excluded from summary table: `src/paper/track_snapshot.py`, `generate_track_snapshot`. After the open-positions loop, add a second pass over all overlay roles with `net_qty == 0` and fold their `realized_by_leg` amounts into `overlay_pnls`. No model changes, no new queries — `_compute_realized_pnl_by_leg` already returns closed-leg entries; they were just unused. Tests: expired CC leg included in overlay total; multiple closed cycles summed correctly; all-open behaviour unchanged.

- [ ] **RPT-2** `[Claude]` — CLI redesign + daily P&L mode: `scripts/strategies/three_track/paper_3track_snapshot.py` + `src/paper/formatting.py`. Replace future `--mode` string with `argparse.add_mutually_exclusive_group()`: `--daily`/`-d` (default), `--monthly`/`-m` (guard: exits with error — RPT-3 not built yet), `--inception`/`-i`. Daily mode: both Base and Overlay columns show 1-day delta via `get_prev_leg_snapshot`; computed in `_run` as post-processing, not inside `generate_track_snapshot`. Column headers change per period ("Day Base"/"Day Overlay" for daily, "Base P&L"/"Overlay" for inception). Tests: daily delta with/without prior snapshot; mutual exclusion enforced; `-m` guard exits cleanly; header strings correct per period.

- [ ] **RPT-3** `[Claude]` — Monthly mode implementation (deferred): remove guard from RPT-2, resolve reference date to first NSE trading day of current month via `src/market_calendar/`, fetch nearest prior `paper_leg_snapshots` row, compute delta as in daily mode. Prerequisite: RPT-2 committed + `market_calendar` holiday list confirmed stable.

---

## Phase OPS — Operational Fixes (discovered during manual trading)

- [ ] **OPS-1** `[Claude]` — `paper_3track_overlay_entry.py`: add insert/skip logging. `store.record_trade()` returns `bool` but the entry script silently ignores it. After each call, log `INSERTED` or `SKIPPED (conflict on strategy/leg/date/action)` at INFO level using structlog. Helps diagnose silent no-ops when same-day close + open hit the unique constraint. Tests: mock `record_trade` returning True/False and assert log output.

- [ ] **OPS-2** `[Claude]` — Atomic collar open/close: collar entry and exit must be treated as a paired unit, never as independent legs. Two sub-tasks:
  (a) **Close**: `paper_3track_overlay_entry.py` and `close_*` scripts must validate that closing `overlay_collar_call` also closes `overlay_collar_put` in the same transaction (and vice versa). Block partial-collar close at the script level — raise an error if only one leg is requested.
  (b) **Open**: `paper_3track_overlay_entry.py` must use a single atomic DB transaction for all collar legs (put + call across all tracks). If any leg insert fails or conflicts, roll back all. Currently the put legs can succeed while call legs silently conflict, leaving a half-open collar in the DB. Use `store.record_trades()` (already exists — `records_trades` does atomic multi-insert) instead of calling `store.record_trade()` in a loop.

---

## Phase BUG — Critical Bug Fixes (2026-06-09 signal flood post-mortem)

> All five bugs interact. Fix in order BUG-1 → BUG-2 → BUG-3 → BUG-4 → BUG-5.
> Story file: `stories_bugs_jun09.md`. DB cleanup SQL is in that file.

- [ ] **BUG-1** `[Claude]` — `get_positions` cross-cycle aggregation: `src/paper/store.py`. Reset `avg_sell_price`, `entry_date`, `instrument_key` accumulators when `net_qty` returns to 0 mid-loop so only the current open cycle contributes. Root cause of false TIME_STOP (days_held=28 for a same-day entry) and distorted avg_sell_price (210.51 vs 231.68). Idempotent migration not required (logic fix only). Tests: multi-cycle fixture asserting correct avg_sell_price and entry_date. **Introduced: `69c7a49`**

- [ ] **BUG-2** `[Claude]` — Position-driven chain fetch: the chain expiry must be derived from the open position's instrument, not from a hardcoded `preference=["monthly"]`. Two parts: (a) **Immediate guard** — in `_dispatch_evaluate` (all branches) and `CSPNiftyV1.check_signals`, when `_find_chain_leg` / `_find_put_leg` returns `None`, `return []` / `continue` with WARNING — never default to `ltp=0`. (b) **Structural fix** — EOD snapshot and daemon must resolve each open position's expiry via `InstrumentLookup.get_by_key`, then call `broker.get_option_chain` for THAT expiry. Cache by expiry date if multiple positions share one. `OptionChain.expiry: date` already exists. Root cause: CSP in NIFTY 22500 PE 28 JUL 26 evaluated against June 30 chain → not found → ltp=0 → PROFIT_TARGET always fires. Tests: position in quarterly expiry → chain fetched for that expiry; leg=None → []; two positions in different expiries → two chain fetches. **Introduced: `8fd58d4` + `9191c02`**

- [ ] **BUG-3** `[Claude]` — `_open_new` hardcodes `quantity=1`: `src/strategy/csp_nifty_v1.py` line 414. Change to `quantity=abs(short_put.net_qty)` (pass through from `apply_action`). Opened 1-lot position instead of 65 on 2026-06-09. Tests: CLOSE_AND_ROLL on 65-lot position → new trade qty=65. **Introduced: `e62aee9`**

- [ ] **BUG-4** `[Claude]` — `record_trade` unique key too broad: `src/paper/store.py` schema + `scripts/dev/migrate_paper_trades_unique.py`. Add `instrument_key` to UNIQUE constraint: `(strategy_name, leg_role, instrument_key, trade_date, action)`. Current key allowed second close of same day (different instrument) to silently no-op, causing `_close_leg` to return normally and `_reentry_notification` to fire every 90 s. Tests: same instrument+date+action → no-op; different instrument same date+action → both inserted. **Introduced: `69c7a49`**

- [ ] **BUG-5** `[Claude]` — `_check_reentry` dedup: `src/strategy/reentry_mixin.py`. Before writing event + notifying, call `get_open_exit_events` and skip if an R5_REENTRY_BLOCKED/ELIGIBLE event already exists today for same strategy+leg. Produced 13 identical Telegram messages on 2026-06-09. Tests: called twice same day → 1 DB row, 1 Telegram; called on two different days → 2 rows, 2 messages. **Introduced: `c9625e1` / `fb38dde`**

## Phase BUG-OVL — Overlay State Bugs (discovered 2026-06-09 via DB audit)

> Story file: `stories_bugs_overlay_state.md`. Fix BUG-6 before BUG-7.
> BUG-6 migration should be combined with the BUG-4 migration (both touch `paper_trades` schema).

- [ ] **BUG-6** `[Claude]` — `TradeState` missing `CLOSED`; `_close_leg` never transitions state: (a) add `CLOSED = "CLOSED"` to `TradeState` enum in `src/paper/models.py`; (b) add `PaperStore.mark_trade_closed(strategy_name, leg_role, instrument_key)` in `src/paper/store.py`; (c) call it from `_close_leg` in `paper_3track_overlay_roll.py` after `store.record_trade(close_trade)`; (d) write idempotent migration `scripts/dev/migrate_add_closed_state.py` to extend CHECK constraint. Combine with BUG-4 migration if BUG-4 not yet done. Tests: `mark_trade_closed` happy/error paths; `_close_leg` dry_run=False marks original SELL CLOSED. **Discovered: 2026-06-09**

- [ ] **BUG-7** `[Claude]` — Jun8 data corruption on instrument 71474: delete spurious SELL 65 @ 12.6 on Jun8; fix BUY 130 → BUY 65; mark remaining 71474 rows as CLOSED post-BUG-6 migration. Run cleanup SQL from `stories_bugs_overlay_state.md` against live DB. No code change. **Discovered: 2026-06-09**

---

## Phase BF — Bug Fixes

- [x] **CR0** `[Claude]` — Fix `send_approval_request` signature mismatch; remove `CouncilOutput` requirement from daemon approval path | SHA: 4ce6d99
- [x] **BF-1** `[Claude]` — Fix `_find_chain_leg` fallback in `paper_3track_snapshot.py`: numeric BOD keys (`NSE_FO|71474`) could not be parsed by `_parse_strike_from_key`, causing fallback to scan all chain strikes and return the first non-zero LTP leg — always the deepest ITM contract (ltp≈8690, delta≈1.0). Fix: resolve strike via `InstrumentLookup.get_by_key()` when parse fails; remove the scan fallback entirely. Thread `lookup: InstrumentLookup | None` through `_dispatch_evaluate` and `compute_and_record_exit_signals`; `_run` already owns `lookup` and now passes it through. Affected: CC, PP, Collar overlay exit signals and CSP when using numeric BOD keys. | SHA: pending

## Phase AUTO — EOD Snapshot Auto-Execution

- [ ] **AUTO-1** `[Antigravity]` — EOD snapshot auto-close for ALL overlays (CC, PP, Collar): after `compute_and_record_exit_signals` writes an ACTION event, immediately call `OverlayCloser` to paper-execute the close in the same script run. Mark the event `ACTED`. Send structured Telegram notification: leg closed, leg P&L, overlay total P&L. Part 0 prerequisite: add `PaperStore.get_strategy_realized_pnl`. All overlay signals auto-execute — no manual approvals anywhere. Signature change: adds `simulator` and `vix` params. See `stories_auto.md` for full spec. Prerequisites: CC-4 + PP-2 + COLLAR-1 + DAEMON-FIX.

## Phase CR1 — CSP Roll: Extract + Signal + Executor + Automation

- [x] **CR1a** `[Antigravity]` — Extract `filter_strikes_by_delta`, `_apply_liquidity_gate`, `rank_strikes` from `find_strike_by_delta.py` → `src/instruments/strike_selector.py`; update imports in `find_strike_by_delta.py` and `paper_csp_roll.py`; tests in `test_strike_selector.py` | SHA: 0a6b3bd
- [x] **CR1b** `[Claude]` — `TradeState` enum + `state` field on `PaperTrade`; `PaperStore.update_trade_state`; remove `evaluate_csp`, add 5 independent CSP classmethods (`evaluate_profit_target_csp`, `evaluate_hard_stop_csp`, `evaluate_delta_breach_csp`, `evaluate_time_stop_csp`, `evaluate_roll_eligible_csp`); `_PROFIT_TARGET_RETENTION` constant; migrate `CSPNiftyV1.check_signals` + `paper_3track_snapshot.py`; idempotent migration script; 20+ tests | SHA: 8fd58d4
- [x] **CR1c** `[Antigravity]` — Refactor `paper_csp_roll.py` to thin CLI wrapper around `csp_roll_executor.py`; existing tests must stay green | SHA: 154a64c

## Phase CC — CC Signal Alignment + Automation

- [x] **CC-1** `[Antigravity]` — Align `evaluate_cc()` to CSP structure: add `days_held` param, `TIME_STOP` signal, replace `DTE_FORCED` with `DTE_REVIEW` WARN, use `_PROFIT_TARGET_RETENTION` constant, add `_CC_MIN_ENTRY_CREDIT`; update `CCOverlayV1` caller; tests | SHA: 5314ec0
- [x] **CC-2** `[Antigravity]` — `ReEntryMixin` in `src/strategy/reentry_mixin.py`: three-gate check (DTE ≥ 14, IVR ≥ 0.25, no open position); `reentry_leg_role` + `reentry_script_hint` class attrs; writes paper_exit_events; Telegram notification | SHA: fb38dde
- [x] **CC-3** `[Claude]` — Migrate `CSPNiftyV1` to `ReEntryMixin`: inherit mixin, add class attrs, remove `_check_r5_reentry`, call `_check_reentry` on PROFIT_TARGET **and** TIME_STOP in `apply_action` (TIME_STOP was missing — regression fix) | SHA: 269c08e
- [x] **CR1d** `[Claude]` — `CSPNiftyV1` full automation: `auto_execute=True`, `_SIGNAL_ACTION_MAP`, priority first-match ACTION signals, refactor `apply_action` to handle CLOSE_AND_ROLL / ROLL_DOWN_AND_OUT / CLOSE_AND_WAIT / OPEN_NEW / CLOSE_FULL; `PaperStrategy` protocol gets `auto_execute: bool`; `StrategyMonitor._route_event` auto-execute dispatch path; `send_notification` already present in `TelegramGateway`; 8 new tests | SHA: pending
- [x] **CC-4** `[Antigravity]` — `CCOverlayV1` full automation: `auto_execute=True`, inherit `ReEntryMixin`, add `__init__` with store/notifier/vix_data_dir, handle `CLOSE_CC` in `apply_action`, `_send_close_notification` via `send_notification`; re-entry check on PROFIT_TARGET + TIME_STOP only | SHA: 3058108, 4320e22
- [x] **CC-5** `[Antigravity]` — `scripts/paper_cc_roll.py`: manual override exit handler with four triggers (loss_stop 2.5×, delta_stop 0.55, profit_target 30%, time_stop 21d) matching `evaluate_cc()` thresholds; dry-run mode; tests in `tests/unit/paper/test_cc_roll.py` | SHA: afd8a9a

## Phase PP — PP Automation

- [x] **PP-1** `[Antigravity]` — Update `evaluate_pp()`: remove bid/ask spread guard from CRASH_MONETIZE; promote DTE_REVIEW INFO → ROLL_ELIGIBLE ACTION; remove bid/ask params from signature; update PPOverlayV1 caller; tests | SHA: 8fd7f68
- [x] **PP-2** `[Antigravity]` — `PPOverlayV1` full automation: `auto_execute=True`, inject store/broker/lookup/notifier, implicit position-based state machine (presence of active position is OPEN; absence is RE_ENTRY_PENDING), three action types (MONETIZE_PP / ROLL_PP / OPEN_NEW_PP), IVR ≤ 0.60 re-entry gate, Telegram notifications; tests | SHA: bcde997, 794b9cb

## Phase COLLAR — Collar Automation

- [ ] **COLLAR-1** `[Antigravity]` — `CollarOverlayV1` full automation: `auto_execute=True`, inherit `ReEntryMixin`, add `__init__` with store/notifier/vix_data_dir, remove `evaluate_collar_call`/`evaluate_collar_put` from `exit_signals.py` (call `evaluate_cc` directly), handle `CLOSE_COLLAR` in `apply_action` (both legs via `OverlayCloser.close_collar_all`), `_send_close_notification` showing call + put; re-entry check on PROFIT_TARGET + TIME_STOP only. Also includes Addition A (unify `collar_short_call`/`collar_long_put` → `overlay_collar_call`/`overlay_collar_put` in `OverlayCloser` + DB migration if needed) and Addition B (`_dispatch_evaluate` fix: use `evaluate_cc` for call, skip put leg entirely). See `stories_collar.md` "COLLAR-1 Additions" section.

## Phase DAEMON — Overlay Registration Fix

- [ ] **DAEMON-FIX** `[Claude]` — Fix overlay dependency injection in `scripts/monitor_daemon.py`: replace `overlay_cls()` zero-arg instantiation with `overlay_cls(**kwargs)` passing broker/store/gateway/vix_data_dir; set `MONITOR_OVERLAYS=1` in `.env`. Prerequisite: CC-4 + PP-2 + COLLAR-1 all committed. See `stories_daemon.md`.

## Phase CR2 — Overlay Roll Signal

- [ ] **CR2** `[Antigravity]` — Add `evaluate_roll_overlay(leg_role, dte, base_dte, atm_strike)` to `ExitSignalEngine` returning `list[ExitSignalResult]`; no `RollSignalResult`; base-DTE guard → `ROLL_BASE_FIRST` WARN; tests extend `test_exit_signals.py`

## Phase CR3 — Wire Overlay Roll Into 3-Track Strategy

- [ ] **CR3** `[Claude]` — Wire `evaluate_roll_overlay` into `NiftyTrackComparisonV1.check_signals`; promote DTE ≤ 5 WARN to ACTION for `ROLL_ELIGIBLE`; keep `ROLL_BASE_FIRST` as WARN; tests

## Phase NT — NiftyTrack Proxy + Safety Signals

- [ ] **NT-1** `[Antigravity]` — `evaluate_proxy_delta()` in `ExitSignalEngine`: three signals (PROXY_DELTA_CRITICAL ACTION at δ<0.40 for 3 consecutive days, PROXY_PREMIUM_DECAY ACTION at mark<₹0.50 with DTE≥5, PROXY_DELTA_WARN WARN at δ<0.65); consecutive-day counter via `PaperStore.get/set_proxy_delta_breach_count`; wire into `NiftyTrackComparisonV1.check_signals` for `base_ditm_call` legs; tests
- [ ] **NT-2** `[Claude]` — `NiftyTrackComparisonV1._check_futures_cc_block()`: emit `BLOCKED_COMBINATION` ERROR when Futures namespace has standalone short call with no paired long put; collar (short call + long put together) explicitly exempted; called at top of `check_signals`; tests

## Phase CR4 — Docs Close (MUST BE LAST)

- [ ] **CR4** `[Claude]` — `DECISIONS.md`, `CONTEXT.md`, `TODOS.md`; update `ExitSignalEngine` description; update `CSPNiftyV1`, `CCOverlayV1`, `PPOverlayV1`, and `NiftyTrackComparisonV1` descriptions
- [ ] **PP-3** `[Claude]` — `DECISIONS.md`, `CONTEXT.md`, `README.md`, `tasks.md`; document PP always-reprotect design, IVR re-entry gate, spread guard removal

---

## Implementation Order

| Priority | Task | Owner | Rationale |
|---|---|---|---|
| P0 | CR0 | Claude | ✅ Done — fixes live runtime TypeError |
| P1 | CR1a | Antigravity | `strike_selector.py` unblocks CR1b and PP-2 |
| P1 | CC-2 | Antigravity | `ReEntryMixin` — independent, run in parallel with CR1a |
| P2 | CR1b | Claude | DB migration + CSP signals; introduces `_PROFIT_TARGET_RETENTION` + `TradeState` |
| P3 | CC-1 | Antigravity | Align `evaluate_cc()` — needs `_PROFIT_TARGET_RETENTION` from CR1b |
| P3 | PP-1 | Antigravity | Update `evaluate_pp()` — needs CR1b for ExitSignalResult; run parallel with CC-1 |
| P3 | CC-3 | Claude | Migrate CSPNiftyV1 to mixin — needs CC-2; run parallel with CC-1, PP-1 |
| P4 | CR1c | Antigravity | CSPRollExecutor — needs CR1b; run parallel with CC-1, CC-3, PP-1 |
| P5 | CR1d | Claude | CSPNiftyV1 full automation — needs CR1c + CC-3 |
| P6 | CC-4 | Antigravity | CCOverlayV1 automation — needs CC-1 + CC-2 + CR1d |
| P6 | PP-2 | Antigravity | PPOverlayV1 automation — needs CR1a + CR1b + PP-1; parallel with CC-4 |
| P6 | COLLAR-1 | Antigravity | CollarOverlayV1 automation + leg role unification + dispatch fix — needs CC-1 + CC-2 + CR1d; parallel with CC-4 and PP-2 |
| P6 | CC-5 | Antigravity | paper_cc_roll.py — needs CC-1 (aligned thresholds); parallel with CC-4 |
| P7 | DAEMON-FIX | Claude | Fix overlay DI in daemon — needs CC-4 + PP-2 + COLLAR-1 all done |
| P7 | CR2 | Antigravity | evaluate_roll_overlay — needs CR1b; can run after P4 |
| P8 | CR3 | Claude | Wire overlay roll — needs CR2 |
| P8 | NT-1 | Antigravity | Proxy delta signals + breach counter — needs CR3; parallel with NT-2 |
| P8 | NT-2 | Claude | Futures+CC block guard — needs CR3; parallel with NT-1 |
| P9 | AUTO-1 | Antigravity | EOD snapshot auto-close (all overlays) — needs CC-4 + PP-2 + COLLAR-1 + DAEMON-FIX |
| P10 | CR4 + PP-3 | Claude | Always last — docs close for all automation stories |

---

## Definition of Done

All tasks above checked. Then verify:

```bash
python -m pytest tests/unit/ --tb=no -q          # all green
search_code("RapidCouncil")                       # zero results in monitor_daemon.py
search_graph("evaluate_profit_target_csp")        # exists in ExitSignalEngine
search_graph("evaluate_roll_overlay")             # exists in ExitSignalEngine
search_graph("close_csp_leg")                     # exists in csp_roll_executor
search_graph("filter_strikes_by_delta")           # exists in strike_selector
search_graph("ReEntryMixin")                      # exists in reentry_mixin
search_graph("CCOverlayV1.auto_execute")          # True
search_graph("PPOverlayV1.auto_execute")          # True
search_graph("_PROFIT_TARGET_RETENTION")          # single constant, used by CSP + CC
search_graph("_evaluate_pp_reentry")             # exists in PPOverlayV1
```

## Regression Gate

Must remain green after each commit:

```bash
python -m pytest tests/unit/strategy/ --tb=short -q
python -m pytest tests/unit/paper/ --tb=short -q
```

## Environment Variables

`MONITOR_OVERLAYS=1` set by DAEMON-FIX. `AUTO-1` works regardless (EOD path is independent).
New in AUTO-1: no new env vars — `simulator` and `vix` are injected at call site.
