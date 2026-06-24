# IC-F3 — Parameterise `IronCondorV1`; `auto_execute = True`; action priority

> **Assigned to: Antigravity** — modifies existing class + tests; TDD loop.

**Prerequisites (both committed before starting):**
- IC-F1 — IVR wiring in `describe_context`
- IC-F2 — `ICExpiryConfig` + `CONFIGS`

**Files to change:**
- `src/strategy/ic_nifty_v1.py`
- `tests/unit/strategy/test_ic_nifty_v1.py`

---

## What to implement

### Constructor

```python
def __init__(
    self,
    broker: BrokerClient,
    store: PaperStore,
    notifier: TelegramGateway,
    config: ICExpiryConfig | None = None,
) -> None:
    from src.strategy.ic_expiry_config import CONFIGS
    self._config = config if config is not None else CONFIGS["monthly"]
    self._broker = broker
    self._store = store
    self._notifier = notifier
```

`config=None` defaults to monthly — zero breakage to existing daemon registration
that calls `IronCondorV1(broker, store, notifier)` with no config until IC-F5 lands.

### Class-level attribute changes

```python
# Remove:
strategy_name: str = "paper_ic_nifty_v1"
auto_execute: bool = False      # added in IC-E1

# Add:
auto_execute: bool = True       # exits are rule-based; no human approval needed

@property
def strategy_name(self) -> str:
    """DB discriminator derived from injected config."""
    return self._config.strategy_name
```

### Replace all module-level threshold constants with config fields

Remove these nine module-level constants entirely:
```
_PROFIT_TARGET_PCT, _LOSS_STOP_PCT, _DELTA_STOP, _DELTA_WARN,
_TIME_STOP_DTE, _DTE_WARN,
_ROLL_WING_DELTA_LO, _ROLL_WING_DELTA_HI, _ROLL_WING_TARGET_DELTA
```

Replace every reference inside `check_signals` and `_select_wing_roll_target`:
- `_PROFIT_TARGET_PCT` → `self._config.profit_target_pct`
- `_LOSS_STOP_PCT` → `self._config.loss_stop_pct`
- `_DELTA_STOP` → `self._config.delta_stop`
- `_DELTA_WARN` → `self._config.delta_warn`
- `_TIME_STOP_DTE` → `self._config.time_stop_dte`
- `_DTE_WARN` → `self._config.dte_warn`
- `_ROLL_WING_DELTA_LO` → `self._config.roll_wing_delta_lo`
- `_ROLL_WING_DELTA_HI` → `self._config.roll_wing_delta_hi`
- `_ROLL_WING_TARGET_DELTA` → `self._config.roll_wing_target_delta`

Keep structural constants: `_SHORT_ROLES`, `_LONG_ROLES`, `_ALL_ROLES`, `_ALLOWED_ACTIONS`.

### Add `_auto_select_action` private method

```python
def _auto_select_action(self, events: list[SignalEvent]) -> ApprovedAction | None:
    """Select one action from a list of fired signals using priority rules.

    Priority (highest first):
      1. LOSS_STOP   → CLOSE_FULL
      2. TIME_STOP   → CLOSE_FULL
      3. PROFIT_TARGET → CLOSE_FULL
      4. ROLL_WING   → ROLL_WING (use suggested_instrument_key from payload)
      5. DELTA_STOP  → CLOSE_CALL_SPREAD or CLOSE_PUT_SPREAD (from leg_role)

    Returns None when no ACTION-severity events are present.

    Args:
        events: All SignalEvents returned by check_signals for this tick.

    Returns:
        Single ApprovedAction to execute, or None.
    """
    action_events = [e for e in events if e.severity == "ACTION"]
    if not action_events:
        return None

    types = {e.event_type for e in action_events}

    if "LOSS_STOP" in types:
        return ApprovedAction(action_type="CLOSE_FULL", legs_to_close=list(_SHORT_ROLES | _LONG_ROLES), legs_to_open=[])

    if "TIME_STOP" in types:
        return ApprovedAction(action_type="CLOSE_FULL", legs_to_close=list(_SHORT_ROLES | _LONG_ROLES), legs_to_open=[])

    if "PROFIT_TARGET" in types:
        return ApprovedAction(action_type="CLOSE_FULL", legs_to_close=list(_SHORT_ROLES | _LONG_ROLES), legs_to_open=[])

    roll_event = next((e for e in action_events if e.event_type == "ROLL_WING"), None)
    if roll_event is not None:
        new_leg = LegSpec(
            instrument_key=roll_event.payload["suggested_instrument_key"],
            action="SELL",
            quantity=1,
            leg_role=roll_event.payload["leg_role"],
            notes=f"auto_roll delta={roll_event.payload['suggested_delta']}",
        )
        return ApprovedAction(
            action_type="ROLL_WING",
            legs_to_close=[roll_event.payload["leg_role"]],
            legs_to_open=[new_leg],
        )

    delta_event = next((e for e in action_events if e.event_type == "DELTA_STOP"), None)
    if delta_event is not None:
        leg_role = delta_event.payload["leg_role"]
        action_type = "CLOSE_CALL_SPREAD" if leg_role == "short_call" else "CLOSE_PUT_SPREAD"
        spread_roles = (
            {"short_call", "long_call_hedge"} if leg_role == "short_call"
            else {"short_put", "long_put_hedge"}
        )
        return ApprovedAction(action_type=action_type, legs_to_close=list(spread_roles), legs_to_open=[])

    return None
```

### Wire `_auto_select_action` into `check_signals`

`check_signals` already returns the list of events. `StrategyMonitor._dispatch` handles
`auto_execute=True` by calling `apply_action` directly. The monitor does not call
`_auto_select_action` — that is the strategy's own logic, invoked inside `apply_action`
when needed, OR exposed as a helper for the monitor.

Check `StrategyMonitor._dispatch` source to confirm the exact call pattern before
deciding where to wire `_auto_select_action`. Do not guess — use `get_code_snippet`
or `sed` to read lines ~190–260 of `src/strategy/monitor.py`.

If the monitor calls `apply_action(positions, action)` where `action` comes from the
Telegram payload (for non-auto strategies) or from the signal payload (for auto-execute),
then `_auto_select_action` should be called by the monitor before `apply_action`. In
that case, expose it as a public method `auto_select_action` and wire it in the monitor.

If the monitor dispatches differently for auto-execute strategies, follow that pattern.
**Read the monitor code before deciding — this is the one ambiguity in this story.**

---

## Tests

**Existing tests:** All fixtures call `IronCondorV1(broker, store, notifier)` — no config
arg, defaults to monthly. Assertions on `strategy_name` must be updated to
`"paper_ic_nifty_v1_monthly"`.

**New tests to add:**

1. `test_strategy_name_from_config` — four presets → four distinct strategy_name values.
2. `test_auto_execute_is_true` — `assert IronCondorV1(...).auto_execute is True`.
3. `test_auto_select_loss_stop_wins` — LOSS_STOP + PROFIT_TARGET both in events → CLOSE_FULL from LOSS_STOP priority.
4. `test_auto_select_roll_over_delta_stop` — ROLL_WING + DELTA_STOP both in events → ROLL_WING action returned.
5. `test_auto_select_delta_stop_call_spread` — DELTA_STOP on `short_call` only → `CLOSE_CALL_SPREAD`.
6. `test_auto_select_none_when_no_action` — only WARN/INFO events → returns `None`.

---

## Commit

```
feat(strategy): parameterise IronCondorV1; auto_execute=True; action priority

Why: Human Telegram approval loop unnecessary for rule-based exits; multi-expiry
research requires per-config threshold isolation.
What:
- src/strategy/ic_nifty_v1.py: config injection; strategy_name property;
  auto_execute=True; hardcoded constants → config fields; _auto_select_action()
- tests/unit/strategy/test_ic_nifty_v1.py: strategy_name assertions updated;
  6 new auto-execute + priority tests
Ref: ic-full IC-F3
```

---

## Pre-baked Context

**Module-level constants in `ic_nifty_v1.py`** (lines 54–76, all to remove):
```python
_PROFIT_TARGET_PCT = Decimal("0.50")
_LOSS_STOP_PCT     = Decimal("2.0")
_DELTA_STOP        = Decimal("0.35")
_DELTA_WARN        = Decimal("0.25")
_TIME_STOP_DTE     = 14
_DTE_WARN          = 21
_ROLL_WING_DELTA_LO    = Decimal("0.10")
_ROLL_WING_DELTA_HI    = Decimal("0.20")
_ROLL_WING_TARGET_DELTA = Decimal("0.15")
```

**`ApprovedAction`** — `src/strategy/protocol.py`.
Fields: `action_type: str`, `legs_to_close: list[str]`, `legs_to_open: list[LegSpec]`.

**`LegSpec`** — `src/strategy/protocol.py`.
Fields: `instrument_key: str`, `action: str`, `quantity: int`, `leg_role: str`, `notes: str`.

**`StrategyMonitor._dispatch`** — lines ~190–260 of `src/strategy/monitor.py`.
Read before deciding where to wire `auto_select_action`. The monitor is the caller —
understand its contract before modifying either side.

**`auto_execute` class attribute** (from IC-E1, SHA: 17a9744):
Currently `auto_execute: bool = False`. Change value to `True`. Keep as class attribute
(not per-instance) since all instances of a given expiry type have the same auto-execute policy.
