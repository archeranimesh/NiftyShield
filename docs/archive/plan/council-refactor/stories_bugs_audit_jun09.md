# Full Code Audit — 3-Track Paper Trading System (2026-06-09)

> Conducted by Opus code-reviewer agent against all src/paper/, src/strategy/, and
> scripts/strategies/three_track/ files. Known bugs BUG-1 through BUG-6 are cross-referenced
> but not re-reported. All new findings are independent unless noted.

---

## Four Systemic Root Causes

Before the per-file findings, Opus identified four root causes that explain why bugs keep
appearing:

1. **Write path doesn't honor the ledger** — every overlay `apply_action` (CC, PP, Collar)
   mutates only the in-memory positions list and records no closing trade to the DB. Each tick
   rebuilds the "closed" leg from history and re-fires signals indefinitely.

2. **"Atomic" is a label, not a guarantee** — `overlay_closer.py` and the roll script use
   separate per-leg DB connections and an application-level rollback keyed on 4 fields
   (missing `instrument_key`), which can delete a legitimate row and leave a naked call after
   a partial collar close.

3. **Zero/missing prices propagate everywhere** — `_resolve_mid_price` stubs return
   `Decimal("0")`, `evaluate_pp` fires on `0 >= 0`, and `_find_put_leg` fallbacks silently
   substitute an arbitrary leg instead of skipping with a diagnostic.

4. **Daemon is fragile and audit trail is fictional** — `run()`/`_route_event` have no
   exception guard and call a nonexistent method (`add_pending_approval`), so the first
   manual-approval signal kills the monitor. `_write_audit` inserts wrong columns and swallows
   the `OperationalError`, so no executed action is ever audited.

---

## `src/strategy/monitor.py`

### [CRITICAL] Daemon dies on first manual-approval signal — `add_pending_approval` doesn't exist
- **Line:** ~204
- **Problem:** `self._store.add_pending_approval(strategy.strategy_name, event)` is called
  but `PaperStore` has no such method (only `create_approval`). Masked by `# type: ignore`.
  `_route_event` has no try/except; `run()` has no guard — the exception kills the daemon.
- **Fix:** Implement `add_pending_approval` on `PaperStore`, or call `create_approval` with
  the correct signature. Wrap `_route_event` in try/except so one bad event can't stop the loop.

### [CRITICAL] `run()` loop has no exception guard — any tick error kills the daemon permanently
- **Line:** ~85-89
- **Problem:** `_fetch_chain`, `_write_heartbeat`, and the `_route_event` path are all unguarded
  inside `run()`. Any unhandled exception stops the daemon silently.
- **Fix:** Wrap the `while True` body in try/except that logs and sleeps to the next tick.

### [WARNING] Market-close boundary uses `>` — 15:30 minute included, stale chain can fire signals
- **Line:** ~109
- **Problem:** `hour_min > _MARKET_CLOSE` with `_MARKET_CLOSE = (15, 30)` — the 15:30 window
  still ticks. Chain at close auction is stale/zero, feeds the ltp=0 false-signal path.
- **Fix:** Use `>=` if 15:30 is meant to be closed.
- **Related:** BUG-2

### [WARNING] Hardcoded `"short_put"` default leg role in auto-execute path
- **Line:** ~180
- **Problem:** `legs_to_close=[event.payload.get("leg_role", "short_put")]`. Missing `leg_role`
  in payload defaults to closing the wrong leg for CC/PP/Collar strategies.
- **Fix:** Make `leg_role` mandatory; log-and-skip if absent.

---

## `src/strategy/executor.py`

### [CRITICAL] `_write_audit` always fails silently — no executed action is ever audited
- **Problem:** Inserts into `council_outputs` using wrong columns (`action_type`, `rationale`,
  `council_rank`); the real schema is (`approval_id`, `persona`, `model`, ...). Every insert
  raises `OperationalError` which is swallowed by `except OperationalError: pass`. The audit
  trail for all auto-executed trades is empty.
- **Fix:** Correct the INSERT to match the real schema (or add a dedicated audit table). Remove
  the blanket `pass`.

### [CRITICAL] `_resolve_mid_price` is a stub returning `Decimal("0")` — all simulated fills mispriced
- **Problem:** The method is a TODO stub. Any fill flowing through it records price=0,
  corrupting simulated P&L and feeding ltp=0 signal paths.
- **Fix:** Implement real mid-price resolution from the chain (bid/ask mid, ltp fallback).
  Fail loudly if price cannot be resolved rather than returning 0.
- **Related:** BUG-2

---

## `src/strategy/csp_nifty_v1.py`

### [CRITICAL] `DELTA_BREACH_FINAL` / DEFENDED escalation is dead code — `hasattr(pos, "state")` always False
- **Problem:** `trade_state = pos.state if hasattr(pos, "state") else TradeState.OPEN`.
  `pos` is `PaperPosition` which has no `state` field. `hasattr` is permanently False →
  `trade_state` is always `OPEN` → the defend→escalate state machine never executes.
- **Fix:** Read `TradeState` from the trade ledger (latest `PaperTrade.state` for the leg),
  not from `PaperPosition`.

### [ERROR] `_find_put_leg` fallback returns first non-zero-LTP PE — wrong leg in multi-strike chains
- **Problem:** When the strike regex fails, the fallback returns an arbitrary PE from the chain.
  Signals evaluated against the wrong option's delta/mark.
- **Fix:** Skip the position with WARN if the specific strike can't be resolved. No arbitrary fallbacks.

### [WARNING] `InstrumentLookup.from_file("data/instruments/NSE.json.gz")` loaded per-call with relative path
- **Problem:** Relative path is fragile under cron/daemon CWD. File re-parsed on every call.
- **Fix:** Resolve path from settings (absolute) and cache the lookup at construction.

---

## `src/strategy/exit_signals.py`

### [CRITICAL] `evaluate_pp` value-breach fires when `entry_price == 0` (`0 >= 0` → True)
- **Problem:** `value_breached = current_mark >= 5.0 * entry_price`. When `entry_price=0` and
  `current_mark=0`, this is `True` → false CRASH_MONETIZE fires.
- **Fix:** Guard `entry_price > 0` before evaluating the multiplier breach.
- **Related:** BUG-2

### [ERROR] `evaluate_collar_put` silently never fires when bid or ask is missing
- **Problem:** Evaluation is gated on both bid and ask. If either is missing (illiquid strike),
  the function returns no result with no diagnostic.
- **Fix:** Fall back to ltp/mid when bid or ask missing; emit WARN when evaluation is skipped.

### [WARNING] CC `BELOW_FLOOR` and `PROFIT_TARGET` are mutually exclusive via `elif` — only first reported
- **Problem:** If both conditions are true simultaneously, only the first is emitted. Undocumented precedence.
- **Fix:** Either document the intended precedence explicitly or emit both signals.

### [WARNING] Float arithmetic on monetary values throughout
- **Problem:** `entry_price`, `current_mark`, multipliers are `float`. REVIEW.md §5 violation.
- **Fix:** Move monetary comparisons to `Decimal`.

---

## `src/strategy/pp_overlay_v1.py`

### [ERROR] `apply_action` records no closing trade — position reappears next tick from ledger
- **Problem:** `apply_action` filters the in-memory positions list but never calls
  `store.record_trade(...)`. The DB still shows the leg open; `get_positions` rebuilds it
  next tick and signals re-fire indefinitely.
- **Fix:** Record an explicit closing trade (opposite action, resolved exit price) before
  returning the filtered list.
- **Related:** BUG-1/BUG-6

### [ERROR] `_find_put_leg` fallback returns first non-zero-LTP PE — same wrong-leg risk as CSP
- **Fix:** Skip with WARN when specific strike can't be resolved.

### [WARNING] `float(pos.avg_cost)` and `float(put_leg.ltp)` convert Decimal money to float
- **Fix:** Keep `Decimal` through the evaluation path. REVIEW.md §5.

### [INFO] `current_mark = float(put_leg.ltp) if put_leg is not None else entry_price` masks lookup failure
- **Problem:** When put leg not found, `current_mark` silently becomes `entry_price` so the
  value-breach test is always False. No diagnostic emitted.
- **Fix:** Emit WARN on `put_leg is None`; don't substitute entry price.
- **Related:** BUG-2

---

## `src/strategy/cc_overlay_v1.py`

### [ERROR] `apply_action` records no closing trade (same persistence gap as PP)
- **Problem:** Identical to PP — call is closed only in memory. Next tick rebuilds it.
- **Fix:** Record explicit closing trade before returning.
- **Related:** BUG-1/BUG-6

### [INFO] `current_mark = float(call_leg.ltp) if call_leg else entry_price` masks lookup failure
- **Fix:** WARN on `call_leg is None`; do not substitute.
- **Related:** BUG-2

---

## `src/strategy/collar_overlay_v1.py`

### [ERROR] Collar does not inherit `ReEntryMixin` — re-entry silently unavailable for collars
- **Problem:** `CollarOverlayV1` doesn't inherit `ReEntryMixin`. After a collar leg is closed,
  no `_check_reentry` runs. The collar track is missing a capability the other two have —
  breaking the fair-comparison invariant.
- **Fix:** Inherit `ReEntryMixin` or explicitly document why collars are exempt.

### [ERROR] `apply_action` records no closing trade (same persistence gap)
- **Problem:** For a partial close (e.g. monetize put only), the put close is invisible to
  the ledger next tick while the call remains open — the structure becomes silently wrong.
- **Fix:** Record closing trades for each leg actually closed.
- **Related:** BUG-1/BUG-6

---

## `src/strategy/overlay_closer.py`

### [CRITICAL] "Atomic" multi-leg close is not transactional — separate connections per leg
- **Problem:** Each `record_trade` call opens its own connection/commit. A failure on leg 2
  leaves leg 1 committed but not leg 2 — a half-closed collar (e.g. put closed, call open =
  naked call). The "rollback" is application-level only.
- **Fix:** Single DB transaction wrapping all leg writes; commit once; let the DB roll back on failure.
- **Related:** BUG-4

### [CRITICAL] Rollback via `delete_trade` (4-field key) can destroy a legitimate row
- **Problem:** `delete_trade` keys on `(strategy, leg_role, trade_date, action)` without
  `instrument_key`. If a legitimate trade exists with the same tuple, rollback deletes it.
  Data corruption masquerading as cleanup.
- **Fix:** Add `instrument_key` to the delete key. Better: use real DB transaction instead of
  application-level rollback.
- **Related:** BUG-4

### [ERROR] `_resolve_mid_price` returns `Decimal("0")` on parse failure — bad fills
- **Problem:** Unparseable instrument key → zero price → close recorded at ₹0, corrupting realized P&L.
- **Fix:** Fail the close (don't record) when price cannot be resolved.
- **Related:** BUG-2/BUG-6

### [ERROR] `monetize_collar_put` can leave a naked call when `put_pos` is missing
- **Problem:** If the put position lookup returns None but the call side proceeds, the protective
  put is gone while the short call remains — naked-call exposure hidden by the "collar" label.
- **Fix:** Validate both legs exist before mutating either; abort if structure is incomplete.

---

## `src/strategy/reentry_mixin.py`

### [ERROR] `datetime.utcnow()` is deprecated and naive — event timestamps wrong vs IST
- **Problem:** Writes naive UTC to `paper_exit_events`. Rest of system reasons in IST.
  Off-by-5:30h timestamps; `utcnow()` deprecated in Python 3.12+.
- **Fix:** Use `datetime.now(tz=timezone.utc)` consistently.

### [WARNING] `vix_series.iloc[-1]` assumed to be today's VIX — stale VIX silently used
- **Problem:** On a stale VIX file (ingestion lagging a day), IVR gate uses old vol with no
  freshness check.
- **Fix:** Assert last index date == today before using; block with reason if stale.

---

## `scripts/strategies/three_track/paper_3track_entry.py`

### [WARNING] Stray `pass` in `main()`
- Editing artifact. Remove.

### [WARNING] Float math in `compute_proxy_entry_price` / qty sizing on monetary values
- **Problem:** Slippage/mid in float, then `str(round(...))` to Decimal. NiftyBees qty uses
  `float(nifty_spot)`. Can shift recorded entry price by a paisa at boundaries. REVIEW.md §5.
- **Fix:** Keep prices in Decimal end-to-end.

### [INFO] `record_trade` loop has no per-trade error handling — partial 3-leg entry on mid-loop failure
- **Problem:** If futures `record_trade` raises after spot committed, entry is left with 1-of-3
  base legs open and no rollback. Breaks the 3-track comparison invariant.
- **Fix:** Record all three within one transaction; check/clean up on partial failure.
- **Related:** BUG-4

---

## `scripts/strategies/three_track/paper_3track_snapshot.py`

### [CRITICAL] `_save_leg_snapshots` assigns all realized P&L to the base leg — overlay P&L always zero
- **Problem:** Realized P&L from `_compute_realized_pnl` (strategy-level total) is attributed
  entirely to the base leg. Overlay legs (`overlay_cc`, `overlay_pp`, etc.) are recorded with
  `realized_pnl=0`. This is the exact metric the experiment is measuring — the comparison
  numbers are wrong.
- **Fix:** Compute and persist realized P&L per leg_role from that leg's own closing trades.
- **Related:** BUG-6

### [WARNING] Stray `pass` in `main()`
- Remove.

---

## `scripts/strategies/three_track/paper_3track_overlay_roll.py`

### [CRITICAL] Roll is not transactional — partial roll leaves inconsistent state
- **Problem:** Same root cause as `overlay_closer.py`. Each leg (close old + open new, ×2 for
  collar) is its own connection/commit. Mid-roll failure leaves a leg closed but not reopened.
- **Fix:** Single transaction wrapping all close+open writes per roll.
- **Related:** BUG-4

### [CRITICAL] Rollback via `delete_trade` (4-field key) — same destructive-key risk
- **Fix:** Full-identity key including `instrument_key`, or real transaction rollback.
- **Related:** BUG-4

### [ERROR] `_find_expiring_overlay` recomputes net from full ledger history — wrong leg selected
- **Problem:** Net quantity rebuilt from entire trade history, not just the current open cycle.
  Closed-then-reopened legs can net incorrectly and the wrong leg is rolled.
- **Fix:** Scope net computation to current open cycle (same fix class as BUG-1).
- **Related:** BUG-1

### [WARNING] Stray `pass` in `_run()`
- Remove.

---

## `src/paper/store.py`

### [ERROR] `delete_trade` keys on 4 fields — enables rollback corruption in all callers
- **Problem:** `delete_trade` deletes by `(strategy_name, leg_role, trade_date, action)`,
  omitting `instrument_key`. This is the store-level enabler of the two rollback-corruption
  CRITICALs above.
- **Fix:** Add `instrument_key` (and a surrogate `id`) to the delete predicate; expose
  delete-by-id as the primary rollback primitive.
- **Related:** BUG-4

### [ERROR] `get_positions` never sets `entry_date` for long-first legs (PP, proxy, ETF)
- **Problem:** `entry_date` is populated only when a SELL row is encountered first. Long-only
  legs (BUY-opened) always get `entry_date=None`. Downstream DTE/age logic silently degrades.
- **Fix:** Set `entry_date` from the opening trade regardless of action.
- **Related:** BUG-1

### [WARNING] `instrument_key` taken from the last loop row — may be a rolled/old contract
- **Problem:** A leg traded across multiple instrument keys (a roll) reports the last key seen,
  which may not be the currently-open contract.
- **Fix:** Take `instrument_key` from the latest open trade in the current cycle.
- **Related:** BUG-1

---

## `src/paper/models.py`

Clean. One structural note: `PaperPosition` lacks a `state` field while `csp_nifty_v1.py`
does `hasattr(pos, "state")` — the model is correct; the consumer is wrong (reported under
CSP CRITICAL above).

---

## `src/paper/tracker.py`

`_compute_realized_pnl` (BUG-6) and `compute_pnl` ltp=0 fallback (BUG-2) are known bugs.
Multiple downstream callers also assume non-zero prices — fixing tracker alone is insufficient;
the zero-price guard must be applied at `exit_signals.py` and all `apply_action` paths too.

---

## Priority Fix Order

```
P0 — Daemon stability (daemon is currently unsafe to run):
  CRIT: monitor.py — add_pending_approval doesn't exist
  CRIT: monitor.py — run() loop has no exception guard

P1 — DB integrity (every close/roll is currently non-atomic and rollback is destructive):
  CRIT: overlay_closer.py — not transactional; rollback deletes wrong rows
  CRIT: paper_3track_overlay_roll.py — same
  ERROR: store.py — delete_trade 4-field key (root cause of above two)
  ERROR: store.py — entry_date never set for long-first legs
  ERROR: pp/cc/collar apply_action — no closing trade recorded (positions reappear)
  ERROR: overlay_closer.py — monetize_collar_put can leave naked call

P2 — Zero-price / false-signal paths:
  CRIT: executor.py — _resolve_mid_price stub returns 0
  CRIT: exit_signals.py — evaluate_pp fires on entry_price=0
  ERROR: exit_signals.py — evaluate_collar_put silently never fires on missing bid/ask
  INFO: pp/cc apply_action — entry_price substitution masks lookup failure

P3 — State machine correctness:
  CRIT: csp_nifty_v1.py — DELTA_BREACH_FINAL dead code (hasattr always False)
  ERROR: collar_overlay_v1.py — no ReEntryMixin
  ERROR: _find_put_leg fallbacks in csp + pp

P4 — Audit / reporting:
  CRIT: executor.py — _write_audit wrong columns, swallowed error
  CRIT: paper_3track_snapshot.py — all realized P&L attributed to base leg
  ERROR: paper_3track_overlay_roll.py — _find_expiring_overlay reads full history

P5 — Minor / defensive:
  ERROR: reentry_mixin.py — datetime.utcnow() deprecated/naive
  WARNING: market-close boundary off by one minute
  WARNING: stray pass in 3 scripts
  WARNING: float math on monetary values in entry script + exit_signals
```

---

## Summary

17 new issues found (4 CRITICAL, 8 ERROR, 4 WARNING, 1 INFO), in addition to BUG-1 through
BUG-6. The two most urgent: the daemon kills itself on the first manual-approval signal
(P0), and every overlay close/roll is non-atomic with a rollback that can corrupt legitimate
rows (P1). The comparison numbers the 3-track experiment produces are also wrong at two
levels: realized P&L is fully misattributed to the base leg in snapshots, and the ltp=0
false-signal paths have been distorting exit decisions throughout.
