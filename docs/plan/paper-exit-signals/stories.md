# paper-exit-signals — Story Specs

> One task per session. Find the first unchecked item in `tasks.md` **tagged for you**. That is your only task.
> Implementation rules: `CLAUDE.md` and `REVIEW.md`. After each task: tick `tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.

**Prerequisite check (run before ES0):**
```
search_graph("StrategyMonitor")   # must exist (PB1.2)
search_graph("PaperExecutor")     # must exist (PB1.3)
search_graph("CCOverlayV1")       # must NOT exist yet
```

---

## ES0 `[Antigravity]` — `paper_exit_events` table + PaperStore methods + tests

**Files:** `src/paper/store.py`, `tests/unit/paper/test_paper_store_exit_events.py`

**Before any code:** `get_code_snippet("PaperStore")` — confirm existing table list and `__init__` shape.

DDL and field definitions: `docs/plan/paper-exit-signals/schema.md` (exact DDL).

**Store methods to add:**
- `create_exit_event(strategy_name, leg_name, trade_id, event_time, detected_by, exit_signal, severity, entry_price, *, snapshot_id, ltp, mid, bid, ask, delta, dte, threshold_value, delta_stop_would_fire, premium_stop_would_fire, actual_rule_used, notes) -> int` — INSERT, status=OPEN, returns row id.
- `get_open_exit_events(strategy_name=None) -> list[dict]` — SELECT status=OPEN, optional filter.
- `acknowledge_exit_event(event_id) -> None` — UPDATE status=ACKNOWLEDGED.
- `resolve_exit_event(event_id, status: Literal["ACTED","DISMISSED"], notes=None) -> None` — UPDATE status, append notes.

**Tests (all use `tmp_path` fresh PaperStore):**
- `create_exit_event` → returns int id ≥ 1.
- `get_open_exit_events` → returns row; nullable fields are None.
- Round-trip with all optional fields set → all values preserved.
- `acknowledge_exit_event` → status=ACKNOWLEDGED; row still in `get_open_exit_events`.
- `resolve_exit_event(ACTED)` → row gone from `get_open_exit_events`.
- `resolve_exit_event(DISMISSED)` → row gone.
- Create two; resolve one → exactly one row returned.
- `get_open_exit_events(strategy_name=...)` → filters correctly.
- Migration creates new table; existing `paper_trades` row count unchanged.
- Dual-signal fields: `delta_stop_would_fire=True, premium_stop_would_fire=False` → round-trip returns 1 and 0.

**Commit:** `feat(paper): add paper_exit_events table migration and store methods`

---

## ES1 `[Antigravity]` — `ExitSignalEngine` + tests

**Files:** `src/strategy/exit_signals.py`, `tests/unit/strategy/test_exit_signals.py`

**Before any code:**
- `get_code_snippet("SignalEvent")` — severity literals.
- `get_code_snippet("PaperPosition")` — confirm `entry_price`, `leg_role`, `net_qty`.
- `get_code_snippet("OptionChainStrike")` — confirm delta field name.

**What to implement:** Stateless `ExitSignalEngine` class — no DB, no async. Each `evaluate_*` method returns `list[ExitSignalResult]` ordered ACTION first. Full method signatures, threshold constants, and `ExitSignalResult` dataclass: `docs/plan/paper-exit-signals/prompt.md` §Exit Rules + §Threshold constants.

Key invariant: `delta_stop_would_fire` / `premium_stop_would_fire` are always populated on sell-leg evaluations (None only for PP buy legs); `actual_rule_used` ∈ `{DELTA, PREMIUM, BOTH, NEITHER}`.

**Tests — CSP:**
- mark=49% of entry → `PROFIT_TARGET` ACTION.
- mark=51% → no profit target.
- mark=1.76× → `LOSS_STOP` ACTION; `premium_stop_would_fire=True`.
- mark=1.74× → no loss stop.
- delta=0.46 → `DELTA_STOP` ACTION; `delta_stop_would_fire=True`.
- delta=0.36 → `DELTA_WARN` WARNING.
- days_held=21 → `TIME_STOP` ACTION.
- days_held=20 → no time stop.
- dte=4 → `DTE_REVIEW` INFO.
- Healthy (mark 60%, delta 0.20, days 10) → `[]`.
- delta=0.46, mark=1.76× → both audit flags True.
- delta=None → delta signals absent; premium backstop still fires.

**Tests — CC:**
- entry=₹10 → `BELOW_FLOOR` INFO; `PROFIT_TARGET` does NOT fire even at mark ≤ 50%.
- entry=₹15, mark ≤ 50% → `PROFIT_TARGET` ACTION.
- mark=2.51× → `LOSS_STOP` ACTION.
- delta=0.56 → `DELTA_STOP` ACTION.
- delta=0.46 → `DELTA_WARN` WARNING.
- DTE=4, spot > strike (ITM) → `DTE_FORCED` ACTION.
- DTE=4, spot < strike, delta=0.10, residual ₹3 → no `DTE_FORCED`.

**Tests — PP:**
- delta=−0.81 → `CRASH_MONETIZE` ACTION.
- value=5.01×, spread 8% of mid → `CRASH_MONETIZE` ACTION.
- value=5.01×, spread 12% → no CRASH_MONETIZE (liquidity gate fails).
- dte=4 → `DTE_REVIEW` INFO.
- Healthy (delta −0.15, value 1.5×, dte 20) → `[]`.

**Tests — Collar call:**
- mark ≤ 25% of entry, DTE > 7 → `COLLAR_CALL_DECAY` ACTION.
- residual ≤ ₹3/unit, DTE > 7 → `COLLAR_CALL_DECAY` ACTION.
- delta=0.56 → `COLLAR_CALL_WARN` WARNING (not ACTION).
- DTE=4, call ITM → `DTE_FORCED` ACTION.
- Healthy (mark 40%, delta 0.25, DTE 20) → `[]`.

**Commit:** `feat(strategy): add ExitSignalEngine with CSP, CC, PP, Collar rule sets`

---

## ES2 `[Claude]` — Fix `CSPNiftyV1` thresholds + re-test

**Files:** `src/strategy/csp_nifty_v1.py`, `tests/unit/strategy/test_csp_nifty_v1.py`

**Before any code:**
- `get_code_snippet("CSPNiftyV1")` — confirm PB2.1 inline threshold literals.
- `get_code_snippet("ExitSignalEngine")` — ES1 must be committed first.

**What changes:** Replace inline threshold comparisons in `check_signals()` with calls to `ExitSignalEngine.evaluate_csp()`. Map `ExitSignalResult → SignalEvent`. Thresholds that were wrong in PB2.1:

| Field | PB2.1 (wrong) | Corrected |
|---|---|---|
| `LOSS_STOP` | 2.0× | 1.75× |
| `DELTA_STOP` | 0.35 | 0.45 |
| `DELTA_WARN` | 0.25 | 0.35 |

**TIME_STOP semantic fix (also in this task):** PB2.1 implemented `TIME_STOP` as `DTE ≤ 21` (days to expiry). The correct condition is `days_held ≥ 21` (calendar days elapsed since entry). These are different — a position entered 5 DTE out would never trigger the DTE-based check; the days-held check fires 21 days after entry regardless of expiry distance. `ExitSignalEngine.evaluate_csp(days_held=...)` uses the correct metric. Call it out explicitly in the commit message.

`apply_action()` — CLOSE_FULL only, no change.

**Test updates:**
- delta=0.36 → `DELTA_WARN` WARNING (was wrongly DELTA_STOP in PB2.1).
- delta=0.46 → `DELTA_STOP` ACTION.
- mark=1.76× → `LOSS_STOP` ACTION.
- mark=2.01× → `LOSS_STOP` ACTION (threshold lowered, still fires).
- days_held=21 → `TIME_STOP` ACTION (was `DTE ≤ 21` in PB2.1 — semantic fix).
- days_held=20, DTE=18 → no `TIME_STOP` (confirms days-held metric, not DTE).

**Commit:** `fix(strategy): correct CSPNiftyV1 thresholds and TIME_STOP metric (days_held, not DTE)`

---

## ES3 `[Antigravity]` — `CCOverlayV1` + tests

**Files:** `src/strategy/cc_overlay_v1.py`, `tests/unit/strategy/test_cc_overlay_v1.py`

**Before any code:**
- `get_code_snippet("PaperStrategy")` — exact protocol signature.
- `get_code_snippet("PaperPosition")` — confirm `leg_role`, `entry_price`, `net_qty`.
- `get_code_snippet("ExitSignalEngine")` — `evaluate_cc` signature.
- `get_code_snippet("OptionChainStrike")` — delta and bid/ask field names.

**What to implement:** `CCOverlayV1` implements `PaperStrategy`. Full method signatures: `docs/plan/paper-exit-signals/prompt.md` §ES3.

Key invariants:
- `SHORT_CALL_ROLES = {"short_call", "cc_short_call"}`.
- `check_signals`: if delta unavailable (strike not in chain), use delta=None — premium backstop still evaluated.
- `apply_action`: accepts `CLOSE_CC` only; raises `ValueError` on any other `action_type`.

**Tests (MockBrokerClient + mock OptionChain fixture):**
- No CC positions → `[]`.
- mark ≤ 50%, credit ≥ ₹15 → `PROFIT_TARGET` ACTION.
- entry credit < ₹12 → `BELOW_FLOOR` INFO; no `PROFIT_TARGET`.
- delta ≥ +0.56 → `DELTA_STOP` ACTION.
- mark ≥ 2.5× → `LOSS_STOP` ACTION.
- Strike missing from chain → premium backstop still evaluated.
- `apply_action(CLOSE_CC)` → no error.
- `apply_action(ADJUST)` → raises `ValueError`.
- `describe_context` → non-empty string containing entry credit, current mark, delta, DTE.

**Commit:** `feat(strategy): add CCOverlayV1 with ExitSignalEngine integration`

---

## ES4 `[Antigravity]` — `PPOverlayV1` + tests

**Files:** `src/strategy/pp_overlay_v1.py`, `tests/unit/strategy/test_pp_overlay_v1.py`

**Before any code:**
- `get_code_snippet("PaperStrategy")` — protocol signature.
- `get_code_snippet("ExitSignalEngine")` — `evaluate_pp` signature; note bid/ask required for liquidity gate.

**What to implement:** `PPOverlayV1` implements `PaperStrategy`. Full method signatures: `docs/plan/paper-exit-signals/prompt.md` §ES4.

Key invariants:
- `LONG_PUT_ROLES = {"long_put", "pp_long_put", "protective_put"}`.
- bid/ask: use chain strike values if available; else bid=ask=None (liquidity gate will not fire — conservative).
- `apply_action`: accepts `MONETIZE_PP` only. Does NOT auto-establish replacement protection. Sends WARN Telegram: `"PP closed. Evaluate replacement if DTE ≥ 14."`.

**Tests:**
- No PP positions → `[]`.
- delta ≤ −0.81, spread ≤ 10% → `CRASH_MONETIZE` ACTION.
- delta ≤ −0.81, spread > 10% → no CRASH_MONETIZE.
- value ≥ 5×, spread OK → `CRASH_MONETIZE` ACTION.
- bid/ask unavailable (None) → no CRASH_MONETIZE even if delta breached.
- dte=4 → `DTE_REVIEW` INFO.
- Healthy PP → `[]`.
- `apply_action(MONETIZE_PP)` → no error.
- `apply_action(CLOSE_FULL)` → raises `ValueError`.

**Commit:** `feat(strategy): add PPOverlayV1 with crash-monetise detection`

---

## ES5 `[Antigravity]` — `CollarOverlayV1` + tests

**Files:** `src/strategy/collar_overlay_v1.py`, `tests/unit/strategy/test_collar_overlay_v1.py`

**Before any code:**
- `get_code_snippet("PaperStrategy")` — protocol.
- `get_code_snippet("ExitSignalEngine")` — `evaluate_collar_call` + `evaluate_collar_put`.
- `get_code_snippet("PaperPosition")` — confirm `leg_role` values for collar legs.
- Read `prompt.md` Collar closure sequences — 4 distinct paths.

**What to implement:** `CollarOverlayV1` implements `PaperStrategy`. Full method signatures: `docs/plan/paper-exit-signals/prompt.md` §ES5.

Key invariants:
- `SHORT_CALL_ROLE = "collar_short_call"`, `LONG_PUT_ROLE = "collar_long_put"`.
- Short call: no independent LOSS_STOP — `COLLAR_CALL_WARN` only.
- `apply_action` routes to `OverlayCloser` based on `action_type`: `CLOSE_CALL_ONLY`, `MONETIZE_PUT`, `CLOSE_ALL_OVERLAY`. Any other → `ValueError`.
- payload must include which leg triggered + both leg states.

**Tests:**
- No collar positions → `[]`.
- Short call at 24% of entry, DTE > 7 → `COLLAR_CALL_DECAY` ACTION.
- Short call at 26% → no decay signal.
- Short call residual ≤ ₹3/unit, DTE > 7 → `COLLAR_CALL_DECAY` ACTION.
- Short call delta ≥ +0.56 → `COLLAR_CALL_WARN` WARNING (not ACTION).
- Long put delta ≤ −0.81, spread ≤ 10% → `COLLAR_PUT_CRASH` ACTION.
- DTE=4, short call ITM → `DTE_FORCED` ACTION.
- Healthy collar → `[]`.
- `apply_action(CLOSE_CALL_ONLY / MONETIZE_PUT / CLOSE_ALL_OVERLAY)` → no error.
- `apply_action(ROLL_COLLAR)` → raises `ValueError`.

**Commit:** `feat(strategy): add CollarOverlayV1 with 4-path closure routing`

---

## ES6 `[Antigravity]` — `OverlayCloser` + tests

**Files:** `src/strategy/overlay_closer.py`, `tests/unit/strategy/test_overlay_closer.py`

**Before any code:**
- `get_code_snippet("PaperExecutor")` — `apply()` signature (PB1.3).
- `get_code_snippet("PaperFillSimulator")` — slippage model.
- `get_code_snippet("PaperStore")` — `record_trade` + `create_exit_event` signatures.
- Read `prompt.md` Collar closure sequences — exact rollback steps.

**What to implement:** `OverlayCloser` handles multi-leg close with rollback on failure. Constructor: `(store, simulator, notifier)`. Full method signatures: `docs/plan/paper-exit-signals/prompt.md` §ES6.

Key invariants:
- `close_single_leg(is_loss_stop=True)` → 1.5× slippage multiplier.
- `close_collar_all` Step 2 failure → re-SELL short call to restore Collar, log rollback, alert notifier. Never leave Collar half-closed silently.
- `monetize_collar_put`: close call first if residual < ₹5/unit; close put at mid (not loss-stop slippage).
- `dual_signal_audit` dict persisted to `paper_exit_events`.

**Tests (tmp_path PaperStore, MockBrokerClient, mock TelegramGateway):**
- `close_single_leg` → reverse trade in store; exit event status=ACTED.
- `close_single_leg(is_loss_stop=True)` → slippage 1.5× base (verify via FillResult).
- `close_single_leg` with `dual_signal_audit` → both fields in exit event.
- `close_collar_call_only` → call trade recorded; put position unchanged.
- `close_collar_all` happy path → both trades recorded; both events ACTED.
- `close_collar_all` Step 2 failure (mock raises on second `record_trade`) → rollback trade inserted for call; notifier called; both events remain OPEN.
- `monetize_collar_put` → call closed first if residual < ₹5; put closed at mid.
- `monetize_collar_put` → exit event notes contain "Evaluate replacement".

**Commit:** `feat(strategy): add OverlayCloser with atomic Collar close + rollback`

---

## ES7 `[Claude]` — EOD integration in `paper_3track_snapshot.py` + tests

**Files:** `scripts/paper_3track_snapshot.py`, `tests/unit/scripts/test_paper_3track_snapshot_exit.py`

**Before any code:**
- `get_code_snippet("paper_3track_snapshot")` — confirm where mark fetch and snapshot write happen; this is the insertion point.
- `get_code_snippet("ExitSignalEngine")` — all four `evaluate_*` signatures.
- `get_code_snippet("PaperStore.create_exit_event")` — field list from ES0.

**What to add:** Function `compute_and_record_exit_signals(store, positions, chain, snapshot_id, engine, today)` called after mark-to-market. For each open leg, dispatch to `engine.evaluate_*` by `leg_role`, write ACTION + WARNING results to `paper_exit_events` with `detected_by=EOD`.

Deduplication: `SELECT 1 FROM paper_exit_events WHERE trade_id=? AND exit_signal=? AND date(event_time)=? AND status='OPEN'` — skip insert if exists. INFO signals: engine-internal only, not written to DB.

After signal computation, send Telegram: ACTION → one message per signal; WARNING → batched per strategy; no signals → silence.

**Tests:**
- CSP mark ≤ 50% → `create_exit_event` called with `PROFIT_TARGET`, `detected_by=EOD`.
- CC delta ≥ 0.56 → `DELTA_STOP` event written.
- PP delta ≤ −0.81, spread ≤ 10% → `CRASH_MONETIZE` written.
- Healthy position → `create_exit_event` NOT called.
- Same signal run twice same day → no duplicate (dedup check).
- INFO signals → NOT written to DB.
- Multiple positions, one breaches → only breaching position creates event.
- Notifier called once for ACTIONs; once for batched WARNINGs.
- Notifier raises → event still written to DB (non-fatal).

**Commit:** `feat(scripts): add Tier 1 EOD exit signal detection to paper_3track_snapshot`

---

## ES8 `[Claude]` — Daemon overlay registration + `MONITOR_OVERLAYS` gate

**Files:** `scripts/monitor_daemon.py`, `src/strategy/__init__.py`

**Before any code:**
- `get_code_snippet("monitor_daemon")` — current startup and strategy registration block.
- `search_code("MONITOR_OVERLAYS")` — must return zero results.

**What to add:**

```python
MONITOR_OVERLAYS = os.getenv("MONITOR_OVERLAYS", "0") == "1"

strategies = [CSPNiftyV1(...), IronCondorV1(...), NiftyTrackComparisonV1(...)]
if MONITOR_OVERLAYS:
    strategies.extend([CCOverlayV1(...), PPOverlayV1(...), CollarOverlayV1(...)])
```

Wire `OverlayCloser` into the `on_approved` callback. Route `action_type` ∈ `{CLOSE_CALL_ONLY, MONETIZE_PUT, CLOSE_ALL_OVERLAY}` → `overlay_closer.route(...)`, else → `executor.apply(...)`.

No new test file required. Add one integration smoke test: daemon registers overlays when `MONITOR_OVERLAYS=1`.

**Commit:** `feat(scripts): register overlay strategies in daemon with MONITOR_OVERLAYS gate`

---

## ES10 `[Claude]` — CSP R5 re-entry eligibility check + tests

**Files:** `src/strategy/csp_nifty_v1.py`, `tests/unit/strategy/test_csp_nifty_v1.py`

**Before any code:**
- `get_code_snippet("CSPNiftyV1")` — confirm ES2 committed; `apply_action` signature.
- `get_code_snippet("compute_ivr")` and `get_code_snippet("load_vix_series")` — IVR computation path.
- `get_code_snippet("PaperStore.get_open_positions")` — confirm method exists.

**What to add:** After `apply_action(PROFIT_TARGET)` closes the short put, call `_check_r5_reentry(store, notifier, expiry, today, vix_data_dir)`.

Three gates (all must pass):
1. `(expiry - today).days ≥ 14`
2. `compute_ivr(vix_today, load_vix_series(vix_data_dir)) ≥ 0.25`; None → blocked (conservative)
3. No open `short_put` in `paper_trades` for `paper_csp_nifty_v1`

Eligible → `paper_exit_events` row `exit_signal=R5_REENTRY_ELIGIBLE`, severity=INFO + Telegram. Blocked → `R5_REENTRY_BLOCKED` row + Telegram with reason. Notifier failure → event still written, exception not propagated.

**Tests (tmp_path PaperStore, mock notifier, mock VIX series):**
- DTE=15, IVR=0.30, no open pos → `R5_REENTRY_ELIGIBLE`; notifier called.
- DTE=13 → `R5_REENTRY_BLOCKED`; reason contains "DTE".
- IVR=0.22 → `R5_REENTRY_BLOCKED`; reason contains "IVR".
- IVR=None (empty history) → `R5_REENTRY_BLOCKED`; reason contains "IVR history".
- Open `short_put` exists → `R5_REENTRY_BLOCKED`; reason contains "open position".
- `apply_action(PROFIT_TARGET)` integration → close recorded then `_check_r5_reentry` called.
- Notifier raises → event still written.

**Commit:** `feat(strategy): add R5 re-entry eligibility check to CSPNiftyV1 post-profit-target close`

---

## ES11 `[Antigravity]` — Base expiry detection + roll alert + tests

**Files:** `scripts/paper_3track_snapshot.py`, `src/instruments/lookup.py`, `tests/unit/paper/test_base_expiry_detection.py`

**Before any code:**
- `get_code_snippet("paper_3track_snapshot")` — insertion point after MTM fetch.
- `get_code_snippet("InstrumentLookup")` — existing BOD methods and `from_file` path.
- `get_code_snippet("PaperStore")` — how open positions are fetched.

**What to add:**

`get_next_contract(instrument_key, instruments)` in `InstrumentLookup`: find current contract in BOD, return the entry with the same `underlying_symbol` + `instrument_type` and the smallest `expiry` greater than current. Returns `None` if not found (log WARNING).

`_check_base_expiry(positions, instruments, today, store, notifier)` in snapshot: for any open `base_futures` or `base_ditm_call` leg with DTE ≤ 5, write `BASE_EXPIRY_ALERT` to `paper_exit_events` and send Telegram with pre-computed settlement-close and roll-open commands (see `prompt.md` §ES11 for exact format). ETF (`base_etf`) excluded. Idempotent: skip if OPEN `BASE_EXPIRY_ALERT` already exists for this trade today.

`BASE_ROLL_ROLES = {"base_futures", "base_ditm_call"}`

**Tests:**
- `base_futures` DTE=4 → alert written; notifier called with both commands.
- `base_futures` DTE=6 → no event.
- `base_ditm_call` DTE=4 → alert written.
- `base_etf` DTE=4 → no alert.
- `get_next_contract` → correct next-expiry key from BOD fixture.
- `get_next_contract` no next expiry → returns None; alert includes "WARNING: next contract not found in BOD".
- Idempotency: second run same day → no duplicate `BASE_EXPIRY_ALERT`.
- Notifier raises → event still written.

**Commit:** `feat(scripts): add base position expiry detection and Telegram roll alert to paper_3track_snapshot`

---

## ES12 `[Antigravity]` — Liquidity gate enforcement + R3 hard block + tests

**Files:** `scripts/find_strike_by_delta.py`, `scripts/record_paper_trade.py`, `tests/unit/scripts/test_find_strike_liquidity_gate.py`, `tests/unit/scripts/test_record_paper_trade_r3.py`

**Before any code:**
- `get_code_snippet("filter_strikes_by_delta")` — confirm `spread_pct` field already computed.
- `get_code_snippet("_get_ivr_and_warn")` in `record_paper_trade.py` — current IVR path (to rename).
- Read `prompt.md` §ES12 — exact `LIQUIDITY_GATE_PCT`, fallback-delta logic, `--force-entry` spec.

**Liquidity gate (`find_strike_by_delta.py`):**

`LIQUIDITY_GATE_PCT = Decimal("0.05")`. Add `_apply_liquidity_gate(ranked, gate_pct) -> list[dict]`. After `rank_strikes()`: filter → if empty, try next delta candidate → if all exhausted: print GATE FAIL message, `sys.exit(1)`. If fallback used: print WARNING with selected vs. requested delta.

**R3 hard block (`record_paper_trade.py`):**

Rename `_get_ivr_and_warn` → `_get_ivr_and_enforce`. On SELL with IVR < 0.25 and no `--force-entry`: print error, `sys.exit(1)`. On SELL with `--force-entry` + IVR < 0.25: print WARNING, write `MANUAL_OVERRIDE` event to `paper_exit_events`. Add `--force-entry` to argparse.

**Tests — liquidity gate:**
- Primary delta spread ≤ 5% → selected normally.
- Primary spread > 5%, fallback ≤ 5% → fallback selected; WARNING printed.
- All candidates > 5% → `sys.exit(1)`.
- `_apply_liquidity_gate([])` → returns `[]`.

**Tests — R3 block:**
- IVR=0.30, SELL → no block.
- IVR=0.22, SELL → `sys.exit(1)`; message contains "R3 blocked".
- IVR=0.22, SELL, `--force-entry` → trade recorded; override event written.
- IVR=None, SELL → no block (warning only — cannot enforce without data).
- IVR=0.10, BUY → no block (gate SELL-only).

**Commit:** `feat(scripts): enforce liquidity gate in find_strike_by_delta and R3 hard block in record_paper_trade`

---

## ES9 `[Claude]` — Docs close + archive (MUST BE LAST)

**Files:** `DECISIONS.md`, `CONTEXT.md`, `TODOS.md`, `docs/plan/paper-exit-signals/tasks.md`

**Git archive moves:**
```bash
git mv docs/council/2026-05-28_paper-trade-exit-philosophy.md docs/council/archive/strategy/
git mv docs/strategies/csp_nifty_v1.md docs/strategies/archive/csp_nifty_v1.md
```

Prepend deprecation notice to archived `csp_nifty_v1.md`:
```markdown
> **ARCHIVED 2026-05-28** — Exit rules codified in `src/strategy/csp_nifty_v1.py`
> (ExitSignalEngine constants) and `docs/plan/paper-exit-signals/`.
> This file is retained for historical reference only. Do not update.
```

**DECISIONS.md — add 10 rows from council Summary Table + dissenting note:**

| Date | Decision | Source |
|---|---|---|
| 2026-05-28 | CC profit target: 50% decay, ₹15/unit floor, ₹12 hard minimum | council exit-philosophy |
| 2026-05-28 | CC loss stop: delta ≥ +0.55 primary, 2.5× premium backstop | council exit-philosophy |
| 2026-05-28 | PP exit: hold to expiry; CRASH_MONETIZE at delta ≤ −0.80 + spread ≤ 10% | council exit-philosophy |
| 2026-05-28 | Collar short call profit: 75% decay rule (25% remaining), close call only | council exit-philosophy |
| 2026-05-28 | Collar short call loss: no independent stop; WARN only; full exit = MANUAL_OVERRIDE | council exit-philosophy |
| 2026-05-28 | Collar put profit: no early exit; CRASH_MONETIZE same as PP | council exit-philosophy |
| 2026-05-28 | Static exits for Phase 0; regime conditioning deferred to ≥24 cycles | council exit-philosophy |
| 2026-05-28 | Automation: Tier 1 EOD mandatory; Tier 2 intraday behind MONITOR_OVERLAYS=1 | council exit-philosophy |
| 2026-05-28 | Storage: `paper_exit_events` table; dual-signal audit mandatory on sell legs | council exit-philosophy |
| 2026-05-28 | CSP thresholds corrected: DELTA_STOP=0.45, LOSS_STOP=1.75× (PB2.1 had 0.35, 2.0×) | council exit-philosophy |

Dissenting note: **Noted, deferred (Q2 minority):** Premium-multiple-only stop for Phase 0. Validate via `delta_stop_would_fire` vs `premium_stop_would_fire` in `paper_exit_events` after 6–12 overlay cycles.

**No code changes in ES9.**

**Commit:** `docs(strategy): add paper-exit-signals decisions, archive council + csp_nifty_v1 spec`
