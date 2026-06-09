# AUTO-1 — EOD Snapshot Auto-Execution

> **Prerequisites (updated 2026-06-08):** CC-4, PP-2, COLLAR-1, DAEMON-FIX committed.
> COLLAR-1 must fix `_dispatch_evaluate` (collar put skip + leg role unification) before
> AUTO-1 can handle collar auto-close correctly. See `stories_collar.md` and `stories_daemon.md`.
>
> **Goal:** zero manual intervention for all overlay signals. Every ACTION event in the EOD
> snapshot must auto-execute or fall back gracefully to a Telegram alert.

---

## Execution Model: Daemon-First, EOD Fallback

Two-phase execution — positions exit as soon as the condition is met:

**Phase 1 — Intraday (after DAEMON-FIX):** `StrategyMonitor._route_event` auto-executes
when `strategy.auto_execute=True` and a signal fires during the session (09:15–15:30).
The exit event is written with status `ACTED`.

**Phase 2 — EOD fallback (AUTO-1):** `compute_and_record_exit_signals` runs at 15:35.
For each ACTION event it writes, it checks: if the event is already `ACTED` (caught intraday),
skip. If `OPEN`, execute via `OverlayCloser` and mark `ACTED`.

This means EOD is a safety net, not the primary path. If the daemon catches PROFIT_TARGET at
14:22, the position exits then — not 45 minutes later.

**Key guard in `_auto_close`:** After writing the event, check `event.status != "ACTED"` before
calling `OverlayCloser`. The daemon path and EOD path may never run concurrently (daemon stops
at 15:30, snapshot starts at 15:35), but the guard is cheap insurance against edge cases
(e.g. overlapping run windows in testing).

---

## Signal Disposition Table

| Signal | Role | Auto-execute? | Action |
|---|---|---|---|
| `PROFIT_TARGET` | `overlay_cc` | ✅ Yes | Close CC via `close_single_leg` |
| `TIME_STOP` | `overlay_cc` | ✅ Yes | Close CC via `close_single_leg` |
| `LOSS_STOP` | `overlay_cc` | ✅ Yes | Close CC with 1.5× slippage |
| `DELTA_STOP` | `overlay_cc` | ✅ Yes | Close CC with 1.5× slippage |
| `PROFIT_TARGET` | `overlay_collar_call` | ✅ Yes | Close collar (both legs) via `close_collar_all` |
| `TIME_STOP` | `overlay_collar_call` | ✅ Yes | Close collar (both legs) via `close_collar_all` |
| `LOSS_STOP` | `overlay_collar_call` | ✅ Yes | Close collar with 1.5× slippage |
| `DELTA_STOP` | `overlay_collar_call` | ✅ Yes | Close collar with 1.5× slippage |
| `PROFIT_TARGET` | `overlay_pp` | ✅ Yes | Close PP via `close_single_leg` |
| `CRASH_MONETIZE` | `overlay_pp` | ✅ Yes | Close PP; state → RE_ENTRY_PENDING |
| `ROLL_ELIGIBLE` | `overlay_pp` | ✅ Yes | Close current PP + open new PP on next expiry |
| `PP_REENTRY_ELIGIBLE` | `overlay_pp` (no open trade) | ✅ Yes | Open new PP via `_open_pp_leg` |
| `DELTA_WARN` | any overlay | ❌ No | Suppress — internal signal only, no Telegram |
| `DTE_REVIEW` | any overlay | ❌ No | Suppress — no action needed |
| `BELOW_FLOOR` | any overlay | ❌ No | Suppress |
| `PP_REENTRY_BLOCKED` | `overlay_pp` | ❌ No | Suppress — re-entry gates not met |

**No signal sends a Telegram approval request.** Either auto-close succeeds and sends
a structured notification, or it fails and sends a fallback alert. There is no keyboard.

---

## Important: OverlayCloser Actual API

The story previously referenced `close_cc()`, `close_pp()`, `close_collar()` — those methods
do not exist. The actual `OverlayCloser` API (from `src/strategy/overlay_closer.py`):

| Method | What it closes |
|---|---|
| `close_single_leg(strategy_name, leg_role, market, event_id, vix, is_loss_stop)` | Any single leg by role |
| `close_collar_call_only(strategy_name, market, event_id, vix)` | Collar short call only (uses `collar_short_call` role) |
| `close_collar_all(strategy_name, market, event_id, vix)` | Both collar legs atomically, with rollback |
| `route(strategy_name, action, market, event_id, vix)` | Routes by `ApprovedAction.action_type` |

`close_single_leg` takes `leg_role` — must match the role string in the DB exactly.
After COLLAR-1, collar roles are `overlay_collar_call` / `overlay_collar_put`.
`close_collar_all` internally uses `SHORT_CALL_ROLE` / `LONG_PUT_ROLE` constants —
these must be updated in COLLAR-1 to match the canonical role strings.

---

## Part 0 — `PaperStore.get_strategy_realized_pnl` (prerequisite sub-task, ~15 lines)

**Files:** `src/paper/store.py`, `tests/unit/paper/test_paper_store.py`

Add:
```python
def get_strategy_realized_pnl(self, strategy_name: str) -> Decimal:
    """Sum of realized P&L across all closed legs for this strategy.

    Queries paper_leg_snapshots for the latest snapshot per (strategy_name, leg_role)
    where the position is effectively closed, and sums realized_pnl.
    Returns Decimal("0") if no data.

    Args:
        strategy_name: e.g. 'paper_covered_call_v1'

    Returns:
        Total realized Decimal, always >= 0 for profitable strategies.
    """
```

SQL:
```sql
SELECT COALESCE(SUM(s.realized_pnl), 0)
FROM paper_leg_snapshots s
INNER JOIN (
    SELECT strategy_name, leg_role, MAX(snapshot_date) AS max_date
    FROM paper_leg_snapshots
    WHERE strategy_name = ?
    GROUP BY strategy_name, leg_role
) latest ON s.strategy_name = latest.strategy_name
         AND s.leg_role = latest.leg_role
         AND s.snapshot_date = latest.max_date
```

Tests: sum of closed legs, empty strategy → 0, no snapshots → 0.

Also confirm `PaperStore.get_exit_event(event_id: int) -> dict | None` exists.
If not, add it:
```python
def get_exit_event(self, event_id: int) -> dict | None:
    """Fetch a single exit event row by ID."""
```

---

## Part 1 — `src/strategy/auto_close_registry.py` (new, ~25 lines)

```python
"""Registry of (leg_role, exit_signal) pairs that auto-close in the EOD snapshot."""
from __future__ import annotations

AUTO_CLOSE_SIGNALS: frozenset[tuple[str, str]] = frozenset({
    # CC — all ACTION signals close the short call leg
    ("overlay_cc", "PROFIT_TARGET"),
    ("overlay_cc", "TIME_STOP"),
    ("overlay_cc", "LOSS_STOP"),
    ("overlay_cc", "DELTA_STOP"),
    # Collar — all ACTION signals on call leg trigger atomic close of both legs
    ("overlay_collar_call", "PROFIT_TARGET"),
    ("overlay_collar_call", "TIME_STOP"),
    ("overlay_collar_call", "LOSS_STOP"),
    ("overlay_collar_call", "DELTA_STOP"),
    # PP
    ("overlay_pp", "PROFIT_TARGET"),
    ("overlay_pp", "CRASH_MONETIZE"),
    ("overlay_pp", "ROLL_ELIGIBLE"),
})

# Overlay roles that suppress generic Telegram WARN/INFO messages.
# These roles send structured close notifications only — no raw signal text.
OVERLAY_ROLES: frozenset[str] = frozenset({
    "overlay_cc",
    "overlay_collar_call",
    "overlay_collar_put",   # put has no independent exit — never appears in AUTO_CLOSE_SIGNALS
    "overlay_pp",
})
```

---

## Part 2 — `_is_loss_stop_signal` helper (~10 lines)

```python
def _is_loss_stop_signal(store: PaperStore, event_id: int) -> bool:
    """Return True when the event exit_signal is LOSS_STOP or DELTA_STOP.
    Used to apply 1.5× slippage multiplier in OverlayCloser.close_single_leg.
    """
    try:
        event = store.get_exit_event(event_id)
        return event["exit_signal"] in ("LOSS_STOP", "DELTA_STOP") if event else False
    except Exception:
        return False
```

---

## Part 3 — `_auto_close` helper (~90 lines)

```python
async def _auto_close(
    store: PaperStore,
    simulator: PaperFillSimulator,
    pos: PaperPosition,
    event_id: int,
    chain: OptionChain,
    notifier: TelegramNotifier | None,
    lookup: InstrumentLookup | None,
    vix: float | None,
    exit_signal: str,
) -> bool:
    """Auto-close an overlay position after an ACTION signal.

    Returns True if close succeeded, False if it failed (fallback Telegram sent).
    """
    closer = OverlayCloser(store=store, simulator=simulator, notifier=None)
    strategy_name = pos.strategy_name
    leg_role = pos.leg_role
    is_short = pos.net_qty < 0
    entry_price = pos.avg_sell_price if is_short else pos.avg_cost

    opt_type = _OVERLAY_OPTION_TYPE.get(leg_role, "CE" if is_short else "PE")
    opt_leg = _find_chain_leg(chain, pos.instrument_key, opt_type, lookup)
    exit_ltp = opt_leg.ltp if opt_leg is not None else Decimal("0")
    exit_delta = float(opt_leg.delta) if opt_leg is not None else None

    try:
        is_loss = _is_loss_stop_signal(store, event_id)

        if leg_role == "overlay_cc":
            closer.close_single_leg(
                strategy_name=strategy_name,
                leg_role=leg_role,
                market=chain,
                event_id=event_id,
                vix=vix,
                is_loss_stop=is_loss,
            )
            leg_pnl = (entry_price - exit_ltp) * abs(pos.net_qty)
            _send_close_notification(
                notifier, strategy_name, leg_role, pos.instrument_key,
                entry_price, exit_ltp, exit_delta, leg_pnl, exit_signal,
                store=store, chain=chain, lookup=lookup,
            )

        elif leg_role == "overlay_collar_call":
            closer.close_collar_all(
                strategy_name=strategy_name,
                market=chain,
                event_id=event_id,
                vix=vix,
            )
            call_pnl = (entry_price - exit_ltp) * abs(pos.net_qty)
            _send_collar_close_notification(
                notifier, strategy_name, pos, entry_price, exit_ltp,
                call_pnl, exit_signal, store=store, chain=chain, lookup=lookup,
            )

        elif leg_role == "overlay_pp":
            closer.close_single_leg(
                strategy_name=strategy_name,
                leg_role=leg_role,
                market=chain,
                event_id=event_id,
                vix=vix,
                is_loss_stop=False,
            )
            leg_pnl = (exit_ltp - entry_price) * abs(pos.net_qty)
            _send_close_notification(
                notifier, strategy_name, leg_role, pos.instrument_key,
                entry_price, exit_ltp, exit_delta, leg_pnl, exit_signal,
                store=store, chain=chain, lookup=lookup,
            )

        else:
            logger.error("auto_close.unknown_role", leg_role=leg_role)
            return False

    except Exception as exc:
        logger.error(
            "auto_close.failed",
            strategy=strategy_name, leg=leg_role,
            event_id=event_id, error=str(exc),
        )
        if notifier:
            try:
                await notifier.send(
                    f"⚠️ AUTO-CLOSE FAILED — {strategy_name} / {leg_role}\n"
                    f"Signal: {exit_signal}  Event: {event_id}\n"
                    f"Error: {exc}\n"
                    f"Close manually via paper_cc_roll.py or record_paper_trade.py"
                )
            except Exception:
                pass
        return False

    logger.info(
        "auto_close.executed",
        strategy=strategy_name, leg=leg_role,
        exit_signal=exit_signal, event_id=event_id,
    )
    return True
```

---

## Part 4 — Notification helpers

### `_send_close_notification` (CC / PP)

```python
def _send_close_notification(
    notifier, strategy_name, leg_role, instrument_key,
    entry_price, exit_ltp, exit_delta, leg_pnl, exit_signal,
    *, store, chain, lookup,
) -> None:
```

Non-fatal. Wraps in `try/except`, never raises.

**CC format:**
```
✅ CC CLOSED — {strategy_name}
📤 {instrument_key} @ ₹{exit_ltp:.2f}  (entry ₹{entry_price:.2f})
Signal : {exit_signal}
Leg P&L: ₹{leg_pnl:+,.0f}
Overlay P&L (total realized): ₹{overlay_pnl:+,.0f}
```

**PP CRASH_MONETIZE format:**
```
💰 PP CRASH MONETIZED — {strategy_name}
📤 {instrument_key} @ ₹{exit_ltp:.2f}  (entry ₹{entry_price:.2f})
Signal : CRASH_MONETIZE  (delta {exit_delta:.3f})
Leg P&L: ₹{leg_pnl:+,.0f}
State  : → RE_ENTRY_PENDING (monitoring IVR ≤ 0.60, DTE ≥ 14)
Overlay P&L (total realized): ₹{overlay_pnl:+,.0f}
```

**PP PROFIT_TARGET / ROLL_ELIGIBLE format:**
```
✅ PP CLOSED — {strategy_name}
📤 {instrument_key} @ ₹{exit_ltp:.2f}  (entry ₹{entry_price:.2f})
Signal : {exit_signal}
Leg P&L: ₹{leg_pnl:+,.0f}
Overlay P&L (total realized): ₹{overlay_pnl:+,.0f}
```

`overlay_pnl = store.get_strategy_realized_pnl(strategy_name)` — called once per notification.

### `_send_collar_close_notification` (Collar — both legs)

After `close_collar_all`, fetch put position from `store.get_position(strategy_name, "overlay_collar_put")`.
If put was already closed (net_qty=0), use last known entry from position history.

```
✅ COLLAR CLOSED — {strategy_name}
📤 Short Call: {call_key} @ ₹{call_exit:.2f}  (entry ₹{call_entry:.2f})  → ₹{call_pnl:+,.0f}
📥 Long Put:   {put_key}  @ ₹{put_exit:.2f}   (entry ₹{put_entry:.2f})   → ₹{put_pnl:+,.0f}
Signal    : {exit_signal}
Net P&L   : ₹{net_pnl:+,.0f}  (call + put combined)
Overlay P&L (total realized): ₹{overlay_pnl:+,.0f}
```

### PP Roll notification (ROLL_ELIGIBLE)

After closing old PP and opening new one:
```
🔄 PP ROLLED — {strategy_name}
📤 Closed: {old_key} @ ₹{exit_ltp:.2f}  →  Leg P&L: ₹{leg_pnl:+,.0f}
📥 Opened: {new_key} @ ₹{new_price:.2f}  delta {new_delta:.3f}  DTE {new_dte}
Overlay P&L (total realized): ₹{overlay_pnl:+,.0f}
```

### PP re-entry open notification

```
🟢 PP RE-ENTRY OPENED — {strategy_name}
📥 {new_key} @ ₹{new_price:.2f}  delta {new_delta:.3f}  DTE {new_dte}  IVR {ivr:.2f}
State  : RE_ENTRY_PENDING → OPEN
Overlay P&L (total realized): ₹{overlay_pnl:+,.0f}
```

---

## Part 5 — PP Re-entry Loop

After main signal loop in `compute_and_record_exit_signals`:

```python
async def _evaluate_pp_reentry_eod(
    store: PaperStore,
    simulator: PaperFillSimulator,
    chain: OptionChain,
    lookup: InstrumentLookup,
    notifier: TelegramNotifier | None,
    vix_data_dir: Path | None,
    today: date,
) -> None:
    """For each PP strategy with no open trade, evaluate re-entry eligibility.

    PP strategy names come from src/paper/constants.py (e.g. STRATEGY_PP_OVERLAY per track).
    For each: if no open overlay_pp position exists → check IVR ≤ 0.60 and DTE ≥ 14 on
    next weekly contract. If eligible → open new PP leg, send notification.
    If blocked → suppress (no Telegram for re-entry blocked).
    """
```

Use `PPOverlayV1._open_pp_leg` logic. Either:
- Extract `_open_pp_leg` to a module-level function in `pp_overlay_v1.py` (preferred)
- Or inline the strike-selection logic in the re-entry helper (avoid duplication)

`vix_data_dir` from `settings.vix_data_dir`. IVR computed via `compute_ivr(vix_today, vix_series)`.

---

## Part 6 — `compute_and_record_exit_signals` changes

**Signature (add two optional params):**
```python
async def compute_and_record_exit_signals(
    ...
    simulator: PaperFillSimulator | None = None,   # NEW
    vix: float | None = None,                       # NEW
) -> None:
```

**After writing each exit event to DB, replace existing Telegram block with:**
```python
if result.severity == "INFO":
    continue  # INFO never written to DB and never sent

# Auto-close path for overlay ACTION signals
# Check ACTED guard: daemon may have already executed this intraday
event_row = store.get_exit_event(event_id)
already_acted = event_row and event_row.get("status") == "ACTED"
if (pos.leg_role, result.exit_signal) in AUTO_CLOSE_SIGNALS and simulator is not None and not already_acted:
    await _auto_close(
        store=store, simulator=simulator, pos=pos,
        event_id=event_id, chain=chain, notifier=notifier,
        lookup=lookup, vix=vix, exit_signal=result.exit_signal,
    )
    continue  # skip generic Telegram path
elif already_acted:
    continue  # daemon handled it intraday — no Telegram noise at EOD

# Suppress WARN for overlay roles — no noise for overlay monitoring signals
if pos.leg_role in OVERLAY_ROLES:
    continue

# Existing generic alert for non-overlay strategies (CSP, NiftyTrack)
msg = (
    f"🚨 EXIT SIGNAL [{result.severity}] — {pos.strategy_name} / {pos.leg_role}\n"
    f"Signal: {result.exit_signal}\n"
    f"{result.notes or ''}"
)
if result.severity == "ACTION":
    action_messages.append(msg)
else:
    warn_by_strategy.setdefault(pos.strategy_name, []).append(...)
```

**After main loop, before returning:**
```python
if simulator is not None and save:
    await _evaluate_pp_reentry_eod(
        store=store, simulator=simulator, chain=chain,
        lookup=lookup, notifier=notifier,
        vix_data_dir=Path(settings.vix_data_dir) if settings.vix_data_dir else None,
        today=today,
    )
```

---

## Part 7 — `_run` wiring

```python
simulator = PaperFillSimulator()
# Attempt VIX fetch from broker; fall back to None (OverlayCloser handles None gracefully)
try:
    vix_resp = await broker.get_ltp(["NSE_INDEX|India VIX"])
    vix = float(next(iter(vix_resp.values()))) if vix_resp else None
except Exception:
    vix = None

await compute_and_record_exit_signals(
    ...
    simulator=simulator,
    vix=vix,
)
```

---

## Files Changed

| File | Change |
|---|---|
| `src/strategy/auto_close_registry.py` | New — `AUTO_CLOSE_SIGNALS`, `OVERLAY_ROLES` |
| `src/paper/store.py` | Add `get_strategy_realized_pnl`, confirm `get_exit_event` |
| `scripts/strategies/three_track/paper_3track_snapshot.py` | `_auto_close`, `_send_close_notification`, `_send_collar_close_notification`, `_is_loss_stop_signal`, `_evaluate_pp_reentry_eod`; updated `compute_and_record_exit_signals` |
| `tests/unit/scripts/test_paper_3track_snapshot_exit.py` | See tests below |
| `tests/unit/paper/test_paper_store.py` | `get_strategy_realized_pnl` tests |

---

## Tests (`test_paper_3track_snapshot_exit.py`)

- CC `PROFIT_TARGET` → `close_single_leg` called with `is_loss_stop=False`; event `ACTED`; notifier called with "CC CLOSED" and positive leg P&L
- CC `LOSS_STOP` → `close_single_leg` called with `is_loss_stop=True`; event `ACTED`
- CC `DELTA_WARN` (WARN severity) → no close; no Telegram; event written to DB
- Collar `PROFIT_TARGET` → `close_collar_all` called; notifier called with both legs in message and net P&L
- PP `CRASH_MONETIZE` → `close_single_leg` called; notifier contains "RE_ENTRY_PENDING"
- PP `ROLL_ELIGIBLE` → close + open called; notifier contains "ROLLED" and new key
- PP re-entry loop → no open PP + IVR ≤ 0.60 → `_open_pp_leg` called; notifier "RE-ENTRY OPENED"
- Auto-close failure → event stays OPEN; fallback Telegram "AUTO-CLOSE FAILED" sent
- `simulator=None` (dry-run) → event written; no close; generic text sent

---

## Definition of Done

```bash
grep "CC CLOSED\|COLLAR CLOSED\|PP CRASH MONETIZED\|PP CLOSED\|PP ROLLED\|RE-ENTRY OPENED" \
    logs/paper_snapshot.log
# → structured close notifications present

sqlite3 data/portfolio/portfolio.sqlite \
    "SELECT status, exit_signal FROM paper_exit_events ORDER BY id DESC LIMIT 5;"
# → ACTED for auto-closed signals; OPEN only for events where auto-close failed

grep "AUTO-CLOSE FAILED" logs/paper_snapshot.log  # ideally empty
grep "🚨 EXIT SIGNAL.*overlay" logs/paper_snapshot.log  # empty — overlays suppressed
```

---

---

## ⚠️ Archived — original spec below (superseded by Parts 0-7 above)

> Everything from this line down is the original AUTO-1 spec. It references stale API methods
> (`close_cc()`, `close_pp()`, `close_collar_call()` — none exist in `OverlayCloser`) and
> still lists LOSS_STOP/CRASH_MONETIZE as manual approval. The active spec is Parts 0-7 above.
> Keeping for reference only. Do NOT implement from this section.

---

## Problem Statement

`compute_and_record_exit_signals` (in `paper_3track_snapshot.py`) writes ACTION events to `paper_exit_events`
and fires a Telegram approval request. The user must manually tap "Close" on the keyboard. This is fine for
loss-stop and delta-breach events (where human judgment adds value), but for clean decay events
(70–94% premium captured, DTE ≤ 2) the close is mechanical and the approval step only adds friction
and risk — if the user misses the notification, a nearly-worthless short survives into final-day gamma territory.

The real-time daemon path (`StrategyMonitor._route_event`) already auto-executes when `auto_execute=True`,
but the daemon requires a live WebSocket tick stream. The EOD snapshot is a cron with no such stream.
These two execution paths never converge on the same positions.

---

## Scope

Extend `compute_and_record_exit_signals` to auto-execute closes for strategies with `auto_execute=True`
**in the EOD snapshot context**, using `OverlayCloser` (which delegates to `PaperFillSimulator`).

### Signals that auto-close (no human approval needed)

| Signal | Role | Rationale |
|---|---|---|
| `PROFIT_TARGET` | `overlay_cc`, `overlay_pp` | Mechanical decay — no judgment needed |
| `TIME_STOP` | `overlay_cc` | DTE ≥ 21 held; position should close regardless |
| `COLLAR_DECAY` | `overlay_collar_call` | 75% captured; collar short call is mechanical |

### Signals that still send Telegram approval request (human-in-the-loop)

| Signal | Role | Rationale |
|---|---|---|
| `LOSS_STOP` | any | Adverse move — human should confirm before closing |
| `DELTA_STOP` | any | Directional breach — may warrant adjustment, not just close |
| `CRASH_MONETIZE` | `overlay_pp` | Large move event — human should decide timing |
| `ROLL_ELIGIBLE` | any | Roll requires strike selection — needs human or separate roll script |

---

## Implementation Plan

### 1. `src/strategy/auto_close_registry.py` (new, ~30 lines)

```python
# Maps (leg_role, exit_signal) → bool indicating auto-close eligibility.
# Only signals listed here are auto-closed; all others fall through to Telegram approval.
AUTO_CLOSE_SIGNALS: frozenset[tuple[str, str]] = frozenset({
    ("overlay_cc", "PROFIT_TARGET"),
    ("overlay_cc", "TIME_STOP"),
    ("overlay_pp", "PROFIT_TARGET"),
    ("overlay_collar_call", "COLLAR_DECAY"),
})
```

### 2. `compute_and_record_exit_signals` changes

After writing the exit event to DB, check:
```python
if (pos.leg_role, result.exit_signal) in AUTO_CLOSE_SIGNALS:
    await _auto_close(store, broker, pos, event_id, notifier)
else:
    # existing Telegram approval request path
    ...
```

### 3. `_auto_close(store, broker, pos, event_id, notifier)` (new helper, ~40 lines)

```python
async def _auto_close(
    store: PaperStore,
    broker: BrokerClient,
    pos: PaperPosition,
    event_id: int,
    notifier: TelegramNotifier | None,
    lookup: InstrumentLookup | None,
) -> None:
    closer = OverlayCloser(store=store, broker=broker, lookup=lookup)
    try:
        if pos.leg_role == "overlay_cc":
            await closer.close_cc(strategy_name=pos.strategy_name)
        elif pos.leg_role == "overlay_pp":
            await closer.close_pp(strategy_name=pos.strategy_name)
        elif pos.leg_role == "overlay_collar_call":
            await closer.close_collar_call(strategy_name=pos.strategy_name)
    except Exception as exc:
        logger.error("auto_close.failed", leg=pos.leg_role, error=str(exc))
        # Fall through: mark event OPEN (not ACTED) so Telegram approval still fires
        return

    store.update_exit_event_status(event_id, "ACTED")
    if notifier:
        msg = (
            f"✅ AUTO-CLOSE EXECUTED — {pos.strategy_name} / {pos.leg_role}\n"
            f"Signal: ...\nFill: ..."
        )
        await notifier.send(msg)
```

### 4. `compute_and_record_exit_signals` signature change

Add `broker: BrokerClient` parameter (already available in `_run` as `broker`). Pass it through.

### 5. `_run` wiring

`broker` is already in scope. Pass it to `compute_and_record_exit_signals`.

---

## Files Changed

| File | Change |
|---|---|
| `src/strategy/auto_close_registry.py` | New — `AUTO_CLOSE_SIGNALS` set |
| `scripts/strategies/three_track/paper_3track_snapshot.py` | Add `broker` param to `compute_and_record_exit_signals`; call `_auto_close` for eligible signals; pass `broker` from `_run` |
| `tests/unit/scripts/test_paper_3track_snapshot_exit.py` | Add tests: `test_cc_profit_target_auto_closed`, `test_cc_loss_stop_sends_approval_not_auto_close`, `test_auto_close_failure_leaves_event_open` |

---

## Definition of Done

- `PROFIT_TARGET` ACTION on CC leg → `paper_exit_events.status == ACTED`, no Telegram approval keyboard sent
- `LOSS_STOP` ACTION on CC leg → `paper_exit_events.status == OPEN`, Telegram approval keyboard sent as before
- Auto-close failure (OverlayCloser raises) → event stays `OPEN`, Telegram approval fires as fallback
- All existing `test_paper_3track_snapshot_exit.py` tests pass
- 3 new tests covering the above cases

---

## Council Trigger Check

This task does NOT require council. The decision is unambiguous:

- Decay-based closes (70%+ captured, DTE ≤ 2) are mechanical — no judgment adds value
- Loss/delta/crash signals preserve human approval because position sizing and adjustment options vary
- `OverlayCloser` already handles all needed close operations (CC single-leg, PP single-leg, Collar call)
- No new data model changes; no new infrastructure; no new async patterns
