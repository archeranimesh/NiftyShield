# AUTO-1 — EOD Snapshot Auto-Execution

> **Prerequisite:** CC-4 and PP-2 must be complete (`auto_execute=True` on `CCOverlayV1` and `PPOverlayV1`).
> Load `stories_cc.md` and `stories_overlay.md` for background on `OverlayCloser` and `PaperFillSimulator`.

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
