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
> | DAEMON-S1 | `stories_bugs_audit_jun09.md` |
> | DBI-1 … DBI-3 | `stories_bugs_audit_jun09.md` |
> | SIG-1, SIG-2 | `stories_bugs_audit_jun09.md` |
> | SM-1, SM-2 | `stories_bugs_audit_jun09.md` |
> | LOG-1 | `stories_bugs_audit_jun09.md` |
> | RPT-0, RPT-SNAP | `stories_bugs_audit_jun09.md` |
>
> Also load `README.md` for shared context (signal tables, state machine, dependency order).
> Do NOT load `stories.md` — it is a historical archive.

---

## Phase DAEMON-STABLE — Daemon must not die on a single bad event (P0)

> Fix before re-enabling the daemon. Story file: `stories_bugs_audit_jun09.md`.

- [ ] **DAEMON-S1** `[Claude]` — Two fixes in `scripts/daemon/monitor_daemon.py` and `src/strategy/monitor.py`:
  (a) `add_pending_approval` doesn't exist on `PaperStore` — every manual-approval ACTION event raises `AttributeError` and kills the daemon. Either implement `PaperStore.add_pending_approval(strategy_name, event)` delegating to `create_approval`, or inline the correct `create_approval` call at the call site. Remove the `# type: ignore[attr-defined]` masking it.
  (b) `run()` loop has no exception guard — any unhandled exception in `_fetch_chain`, `_write_heartbeat`, or `_route_event` is terminal. Wrap the `while True` body in `try/except Exception` that logs the error and continues to the next `asyncio.sleep`. A single bad tick must never stop the monitor.
  Tests: mock `create_approval` raising `RuntimeError` → daemon continues; mock nonexistent method → `add_pending_approval` delegates correctly.

---

## Phase DB-INTEGRITY — Every write must be correct and atomic (P1)

> Fix as a unit — all three tasks share the same root cause. Story file: `stories_bugs_audit_jun09.md`.
> Combine DBI-1 migration with BUG-4 migration if BUG-4 is not yet done.

- [ ] **DBI-1** `[Claude]` — Make `overlay_closer.py` and `paper_3track_overlay_roll.py` genuinely atomic, and fix the destructive rollback key:
  (a) `src/paper/overlay_closer.py`: replace per-leg `_connect()` calls with a single shared connection passed to all `record_trade` calls; commit once after all legs succeed; on failure roll back the DB transaction (no application-level delete needed).
  (b) `scripts/strategies/three_track/paper_3track_overlay_roll.py`: same — wrap close+open per roll in a single transaction. `_roll_collar` must commit both legs together or neither.
  (c) `src/paper/store.py` `delete_trade`: add `instrument_key` to the WHERE predicate (same root cause as BUG-4); expose `delete_trade_by_id(trade_id)` as the preferred rollback primitive going forward.
  (d) `overlay_closer.py` `monetize_collar_put`: validate both put and call positions exist before mutating either; abort with an error if the collar structure is incomplete (avoids leaving a naked call).
  Tests: collar close — second leg write raises → first leg rolled back; `delete_trade` with different `instrument_key` same tuple → does not delete wrong row.

- [ ] **DBI-2** `[Claude]` — All three overlay `apply_action` methods record no closing trade to the DB, so positions reappear from the ledger next tick and signals re-fire indefinitely. Fix in `src/strategy/cc_overlay_v1.py`, `src/strategy/pp_overlay_v1.py`, `src/strategy/collar_overlay_v1.py`:
  Each `apply_action` that closes a leg must call `self._store.record_trade(closing_trade)` (BUY for a short leg, SELL for a long leg) at the resolved exit price before returning the filtered positions list. Use `PaperFillSimulator` for the exit price (already available via executor). For collar, record both legs.
  Tests: `apply_action(CLOSE_CC)` → closing BUY trade written to DB; next `get_positions` call returns empty for that leg; idempotent (second call is a no-op via unique key).

- [ ] **DBI-3** `[Claude]` — Two `get_positions` data quality fixes in `src/paper/store.py`:
  (a) `entry_date` is never set for long-first legs (PP, base ETF, deep ITM proxy) — `entry_date` is populated only from the first SELL. Set `entry_date` from the opening trade regardless of action (first row for the leg in the current cycle after last flat point).
  (b) `instrument_key` is taken from the last loop row — on a rolled leg this is the old contract. Take `instrument_key` from the most recent opening trade in the current cycle instead.
  Tests: long-only leg (BUY-opened) → `entry_date` equals BUY trade date; rolled leg → `instrument_key` equals new contract key, not old.

---

## Phase SIGNAL-HARDENING — Zero/missing prices must never fire a signal (P2)

> Story file: `stories_bugs_audit_jun09.md`. Fix SIG-1 before SIG-2 (shared price-resolution path).

- [ ] **SIG-1** `[Claude]` — `src/strategy/executor.py` `_resolve_mid_price` is a TODO stub returning `Decimal("0")`. Every fill through it is priced at zero, corrupting P&L and feeding false-signal paths:
  Implement real mid-price resolution: `(bid + ask) / 2` from the chain leg if both are present; fall back to `ltp` if spread is unavailable; raise `ValueError` (do not return 0) if no price can be resolved so the caller can abort rather than record a zero-price fill.
  Also fix `_write_audit` which inserts wrong columns into `council_outputs` under a swallowed `OperationalError` — add a dedicated `paper_action_audit` table with columns `(id, strategy_name, action_type, leg_role, price, qty, rationale, executed_at)` and write there instead.
  Tests: `_resolve_mid_price` with bid+ask → returns mid; ltp-only → returns ltp; no price → raises; `_write_audit` → row in `paper_action_audit`.

- [ ] **SIG-2** `[Claude]` — Two false-signal fixes in `src/strategy/exit_signals.py`:
  (a) `evaluate_pp`: `value_breached = current_mark >= 5.0 * entry_price` fires when `entry_price == 0` (`0 >= 0` → True). Guard: `if entry_price <= 0: return result with no signals` with a WARN logged.
  (b) `evaluate_collar_put`: silently returns no result when `bid` or `ask` is `None` (illiquid strike). Fall back to `ltp` when either is missing; emit an INFO diagnostic when falling back so the operator knows the evaluation used ltp not mid.
  Also convert float monetary comparisons throughout `exit_signals.py` to `Decimal` (REVIEW.md §5).
  Tests: `evaluate_pp` with `entry_price=0` → no signal emitted, WARN logged; `evaluate_collar_put` with missing bid → uses ltp, INFO logged.

---

## Phase STATE-MACHINE — State transitions must actually execute (P3)

> Story file: `stories_bugs_audit_jun09.md`.

- [ ] **SM-1** `[Claude]` — `src/strategy/csp_nifty_v1.py`: `DELTA_BREACH_FINAL` / DEFENDED escalation is dead code. `trade_state = pos.state if hasattr(pos, "state") else TradeState.OPEN` — `pos` is `PaperPosition` which has no `state` field, so `hasattr` is always False and the escalation branch (`OPEN→DEFENDED→DELTA_BREACH_FINAL`) never executes. Fix: read `TradeState` from the trade ledger — call `self._store.get_trade_state(strategy_name, leg_role)` (add this method to `PaperStore` if not present), then use that value instead of `hasattr`. Also fix `_find_put_leg` fallback: when the strike regex fails, skip the position with a WARN rather than returning an arbitrary PE from the chain.
  Tests: position in DEFENDED state → `check_signals` emits `DELTA_BREACH_FINAL`; `_find_put_leg` with no matching strike → returns None, WARN logged.

- [ ] **SM-2** `[Claude]` — `src/strategy/collar_overlay_v1.py` does not inherit `ReEntryMixin` — after a collar leg is closed, re-entry eligibility is never evaluated, breaking the fair-comparison invariant vs CC and PP. Add `ReEntryMixin` to `CollarOverlayV1`, set `reentry_leg_role = "overlay_collar_call"` and `reentry_script_hint`, wire `_check_reentry` into the close path in `apply_action` (same pattern as `CCOverlayV1`). Prerequisite: BUG-5 fixed (dedup), otherwise re-entry notification will flood.
  Tests: `apply_action(CLOSE_COLLAR)` → `_check_reentry` called once; eligibility gated on DTE/IVR/no-open-position.

---

## Phase LOG — Structured logging with correlation ID (P2, can run in parallel with SIGNAL-HARDENING)

> Every execution flow (daemon tick, snapshot run, roll, action dispatch) must be traceable
> end-to-end from a single ID in the log. Story file: `stories_bugs_audit_jun09.md`.

- [ ] **LOG-1** `[Claude]` — Add `trace_id` correlation to all structured log flows across the daemon, snapshot, and roll scripts:
  (a) `src/utils/logging.py`: add `generate_trace_id() -> str` returning an 8-char hex string (`secrets.token_hex(4)`). Add `bind_trace_id(trace_id: str)` that calls `structlog.contextvars.bind_contextvars(trace_id=trace_id)` so the ID appears in every subsequent log call within the same async context or function call stack.
  (b) `src/strategy/monitor.py` `_tick()`: call `bind_trace_id(generate_trace_id())` at the top of each tick. All logs within a tick (chain fetch, signal check, route event, approval write, heartbeat) will carry `trace_id`. Log `tick.start` and `tick.end` with the ID.
  (c) `scripts/strategies/three_track/paper_3track_snapshot.py` `main()`: bind a trace ID at script entry. All leg P&L computations, chain fetches, exit signal evaluations, and DB writes within a single snapshot run share the same ID.
  (d) `scripts/strategies/three_track/paper_3track_overlay_roll.py` `_run()`: same — bind at entry, all roll operations (close, open, DB write) carry the ID.
  (e) `src/strategy/executor.py` `execute_action()`: bind a fresh trace ID per action dispatch, or inherit the calling tick's ID if already bound. Log `action.dispatch`, `action.fill`, `action.complete` with `strategy_name`, `action_type`, `leg_role`, `price`, `qty`.
  This means: if a signal fires and a wrong trade is executed, you can `grep trace_id=abc123ef logs/` and see the full chain: tick start → chain fetch → signal evaluated → action dispatched → fill recorded → DB write.
  Tests: `bind_trace_id` binds to structlog context; log output for a tick includes `trace_id`; two concurrent ticks have different IDs; `generate_trace_id` returns 8-char hex.

---

## Phase RPT-FIX — Reporting correctness (P4)

> Story file: `stories_bugs_audit_jun09.md`. Fix after DB-INTEGRITY (realized P&L attribution depends on correct closing trades).

- [ ] **RPT-0** `[Claude]` — `src/strategy/executor.py` `_write_audit` writes wrong columns and is silently failing for every executed action (no audit trail exists). Part of SIG-1 above — see SIG-1 for the combined fix.

- [ ] **RPT-SNAP** `[Claude]` — `scripts/strategies/three_track/paper_3track_snapshot.py` `_save_leg_snapshots` attributes all strategy-level `realized_pnl` to the base leg and records `realized_pnl=0` for every overlay leg. This is the exact metric the 3-track comparison is measuring. Fix: compute per-`leg_role` realized P&L using FIFO round-trip matching from `paper_trades` (same logic as BUG-6 fix in tracker.py — extract a shared `_compute_realized_pnl_by_leg(trades) -> dict[str, Decimal]` helper and call it from both). The base leg's `realized_pnl` should reflect only the base position's realized amount.
  Prerequisite: DBI-2 committed (closing trades written to DB).
  Tests: closed CC overlay → `paper_leg_snapshots.realized_pnl` for `overlay_cc` equals `(sell − buy) × qty`; base leg realized excludes overlay amounts.

- [ ] **RPT-ROLL** `[Claude]` — `scripts/strategies/three_track/paper_3track_overlay_roll.py` `_find_expiring_overlay` computes net quantity from the full trade history, so a closed-then-reopened leg can net incorrectly and the wrong leg is selected for rolling. Scope the net computation to the current open cycle only (same fix class as BUG-1 / DBI-3).
  Tests: leg with 2 completed cycles + 1 open → net qty reflects only open cycle; all-closed leg → net_qty=0, not selected for roll.

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

> ⚠ AUDIT FINDINGS (2026-06-09) inserted at P0–P4. Daemon must not be re-enabled until
> DAEMON-S1 is done. Existing automation stories (CC-4, PP-2, COLLAR-1, AUTO-1) unblocked
> only after DB-INTEGRITY phase complete.

| Priority | Task | Owner | Rationale |
|---|---|---|---|
| P0 | CR0 | Claude | ✅ Done — fixes live runtime TypeError |
| P0 | DAEMON-S1 | Claude | `add_pending_approval` missing + `run()` no guard — daemon kills itself on first approval signal |
| P1 | LOG-1 | Claude | Correlation ID — add first so all subsequent fixes emit traceable logs |
| P1 | DBI-1 | Claude | Atomic overlay close/roll + destructive rollback key fix — root cause of data corruption |
| P1 | DBI-2 | Claude | `apply_action` must write closing trades — positions reappear every tick without this |
| P1 | DBI-3 | Claude | `get_positions` entry_date + instrument_key — downstream DTE/age logic is broken without this |
| P2 | BUG-1 | Claude | `get_positions` cross-cycle aggregation — needs DBI-3 in same file, do together |
| P2 | BUG-4 | Claude | Unique key missing `instrument_key` — combine migration with DBI-1 |
| P2 | SIG-1 | Claude | `_resolve_mid_price` stub + `_write_audit` wrong columns |
| P2 | SIG-2 | Claude | `evaluate_pp` zero-entry false signal + `evaluate_collar_put` silent skip |
| P2 | BUG-2 | Claude | Position-driven chain fetch — blocks all correct signal evaluation |
| P2 | BUG-6 | Claude | `_compute_realized_pnl` cross-cycle inflation — combine with BUG-1 fix in tracker.py |
| P3 | BUG-3 | Claude | `_open_new` qty=1 hardcoded |
| P3 | BUG-5 | Claude | `_check_reentry` dedup |
| P3 | SM-1 | Claude | `DELTA_BREACH_FINAL` dead code + `_find_put_leg` arbitrary fallback |
| P3 | SM-2 | Claude | `CollarOverlayV1` missing `ReEntryMixin` — needs BUG-5 first |
| P4 | RPT-SNAP | Claude | Per-leg realized P&L attribution — needs DBI-2 (closing trades must exist) |
| P4 | RPT-ROLL | Claude | `_find_expiring_overlay` scoped to current cycle — needs BUG-1 fix |
| P4 | BUG-7 | Claude | DB cleanup for Jun8 data corruption |
| P4 | RPT-1 | Claude | Closed overlay legs excluded from summary table |
| P4 | RPT-2 | Claude | CLI redesign + daily P&L mode |
| P5 | CR1a | Antigravity | `strike_selector.py` — unblocks CR1b and PP-2 |
| P5 | CC-2 | Antigravity | `ReEntryMixin` — independent, run in parallel with CR1a |
| P6 | CR1b | Claude | DB migration + CSP signals |
| P7 | CC-1 | Antigravity | Align `evaluate_cc()` — needs CR1b |
| P7 | PP-1 | Antigravity | Update `evaluate_pp()` — needs CR1b; parallel with CC-1 |
| P7 | CC-3 | Claude | Migrate CSPNiftyV1 to mixin — needs CC-2; parallel with CC-1, PP-1 |
| P8 | CR1c | Antigravity | CSPRollExecutor — needs CR1b |
| P9 | CR1d | Claude | CSPNiftyV1 full automation — needs CR1c + CC-3 |
| P10 | CC-4 | Antigravity | CCOverlayV1 automation — needs CC-1 + CC-2 + CR1d + DBI-2 |
| P10 | PP-2 | Antigravity | PPOverlayV1 automation — needs CR1a + CR1b + PP-1 + DBI-2; parallel with CC-4 |
| P10 | COLLAR-1 | Antigravity | CollarOverlayV1 automation — needs CC-1 + CC-2 + CR1d + SM-2 + DBI-2; parallel with CC-4 |
| P10 | CC-5 | Antigravity | paper_cc_roll.py — needs CC-1; parallel with CC-4 |
| P11 | DAEMON-FIX | Claude | Overlay DI in daemon — needs CC-4 + PP-2 + COLLAR-1 + DAEMON-S1 |
| P11 | CR2 | Antigravity | evaluate_roll_overlay — needs CR1b |
| P12 | CR3 | Claude | Wire overlay roll — needs CR2 |
| P12 | NT-1 | Antigravity | Proxy delta signals — needs CR3; parallel with NT-2 |
| P12 | NT-2 | Claude | Futures+CC block guard — needs CR3; parallel with NT-1 |
| P13 | AUTO-1 | Antigravity | EOD snapshot auto-close — needs CC-4 + PP-2 + COLLAR-1 + DAEMON-FIX |
| P13 | OPS-1 | Claude | insert/skip logging in overlay entry |
| P13 | OPS-2 | Claude | Atomic collar open/close in entry script |
| P13 | RPT-3 | Claude | Monthly mode — needs RPT-2 + market_calendar |
| P14 | CR4 + PP-3 | Claude | Always last — docs close |

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
