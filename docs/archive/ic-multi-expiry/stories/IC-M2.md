# IC-M2 — Parameterise `IronCondorV1` with `ICExpiryConfig`

> **Assigned to: Antigravity** — modifies existing class with full test update; TDD loop.

**Prerequisites (both must be committed before starting):**
- ic-e2e IC-E3 — IVR wiring in `describe_context` (touches same file)
- ic-multi-expiry IC-M1 — `ICExpiryConfig` + `CONFIGS` must exist

**Files to change:**
- `src/strategy/ic_nifty_v1.py` — constructor accepts `ICExpiryConfig`; all threshold refs use config fields; module-level constants removed
- `tests/unit/strategy/test_ic_nifty_v1.py` — all fixture instantiations updated; new per-expiry signal threshold tests added

---

## Context

After IC-M1, `ICExpiryConfig` exists and `CONFIGS` has four presets. This story
wires the config into `IronCondorV1` so that every threshold comparison reads from
`self._config` rather than a module-level constant.

The class interface visible to `StrategyMonitor` does not change — `check_signals`,
`apply_action`, `describe_context`, and `strategy_name` all remain. What changes is
that `strategy_name` is now derived from the injected config rather than being a
hardcoded class attribute, and all `_PROFIT_TARGET_PCT` / `_TIME_STOP_DTE` / etc.
references are replaced with `self._config.*`.

---

## What to implement

### `src/strategy/ic_nifty_v1.py`

**Constructor change:**

```python
def __init__(
    self,
    broker: BrokerClient,
    store: PaperStore,
    notifier: TelegramGateway,
    config: ICExpiryConfig | None = None,
) -> None:
    """Initialise IronCondorV1 for a specific expiry type.

    Args:
        broker: BrokerClient implementation (injected).
        store: PaperStore for position reads/writes.
        notifier: TelegramGateway for signal dispatch.
        config: Per-expiry threshold set. Defaults to CONFIGS["monthly"] when
            None — preserves backward compatibility with existing daemon
            registration that passes no config.
    """
    from src.strategy.ic_expiry_config import CONFIGS
    self._config = config if config is not None else CONFIGS["monthly"]
    self._broker = broker
    self._store = store
    self._notifier = notifier
```

**`strategy_name` property** (replaces class attribute):

```python
@property
def strategy_name(self) -> str:  # type: ignore[override]
    """DB discriminator derived from injected config."""
    return self._config.strategy_name
```

**Module-level constants to remove** (all replaced by `self._config.*`):
- `_PROFIT_TARGET_PCT` → `self._config.profit_target_pct`
- `_LOSS_STOP_PCT` → `self._config.loss_stop_pct`
- `_DELTA_STOP` → `self._config.delta_stop`
- `_DELTA_WARN` → `self._config.delta_warn`
- `_TIME_STOP_DTE` → `self._config.time_stop_dte`
- `_DTE_WARN` → `self._config.dte_warn`
- `_ROLL_WING_DELTA_LO` → `self._config.roll_wing_delta_lo`
- `_ROLL_WING_DELTA_HI` → `self._config.roll_wing_delta_hi`
- `_ROLL_WING_TARGET_DELTA` → `self._config.roll_wing_target_delta`

Keep `_SHORT_ROLES`, `_LONG_ROLES`, `_ALL_ROLES`, `_ALLOWED_ACTIONS` — these are
structural, not threshold values, and do not vary per expiry type.

Keep `auto_execute: bool = False` as a class attribute — it does not vary per expiry.

**`describe_context`** — update the `strategy_name` reference (now a property, not a
class attribute). No other changes to this method.

---

## Tests (`tests/unit/strategy/test_ic_nifty_v1.py`)

**Existing tests:** Every fixture that instantiates `IronCondorV1(broker=..., store=..., notifier=...)`
continues to work because `config=None` defaults to `CONFIGS["monthly"]`. No fixture changes
needed unless a test asserts on `strategy_name` — update those to `"paper_ic_nifty_v1_monthly"`.

**New tests to add:**

1. `test_strategy_name_from_config` — instantiate with each of the four `CONFIGS` presets;
   assert `strategy.strategy_name` matches the preset's `strategy_name`.

2. `test_time_stop_weekly` — build a mock IC position with DTE = 1; use `CONFIGS["weekly"]`
   (time_stop_dte=2); assert TIME_STOP ACTION fires. Same position with `CONFIGS["monthly"]`
   should NOT fire TIME_STOP (DTE=1 < 14 — actually it would fire, use DTE=10 for monthly).
   Clarification: use DTE=3 for weekly (fires), DTE=3 for monthly (does NOT fire, 3 < 14 means
   it DOES fire — pick DTE=15 for monthly non-fire case).

   Simpler: DTE=3, weekly config → TIME_STOP fires. DTE=3, monthly config → TIME_STOP fires too
   (3 < 14). Use DTE=20 as the discriminating case: weekly time_stop=2 → fires; monthly
   time_stop=14 → fires (20 > 14? No, 20 > 14 means DTE=20 > 14 so it does NOT fire for monthly).
   Actually: TIME_STOP fires when `dte <= time_stop_dte`. So DTE=20, monthly (time_stop_dte=14):
   20 > 14 → does not fire. DTE=20, leaps (time_stop_dte=45): 20 <= 45 → fires.
   Use DTE=20 as the discriminating value between monthly and leaps.

3. `test_profit_target_weekly_vs_monthly` — build a combined_mark that is 45% of entry credit.
   Weekly config (profit_target_pct=0.40): 0.45 > 0.40 → does not fire.
   Monthly config (profit_target_pct=0.50): 0.45 <= 0.50 → fires.
   Assert the signal difference.

4. `test_default_config_is_monthly` — instantiate with no config arg; assert
   `strategy.strategy_name == "paper_ic_nifty_v1_monthly"`.

---

## Commit

```
feat(strategy): parameterise IronCondorV1 with ICExpiryConfig

Why: Hardcoded monthly thresholds break weekly/leaps/yearly paper research;
multi-expiry requires per-instance config injection.
What:
- src/strategy/ic_nifty_v1.py: constructor accepts ICExpiryConfig; strategy_name
  becomes property; all threshold module-constants replaced with config fields
- tests/unit/strategy/test_ic_nifty_v1.py: fixtures unchanged (default=monthly);
  4 new per-expiry threshold discrimination tests
Ref: ic-multi-expiry IC-M2
```

---

## Pre-baked Context

**`IronCondorV1.__init__`** current signature (from ic-e2e IC-E3 — must be committed first):
```python
def __init__(self, broker: BrokerClient, store: PaperStore, notifier: TelegramGateway) -> None:
```
After this story: adds `config: ICExpiryConfig | None = None` as a fourth kwarg.

**Module-level constants in `ic_nifty_v1.py`** (lines 54–59, 74–76 — all to be removed):
```python
_PROFIT_TARGET_PCT = Decimal("0.50")
_LOSS_STOP_PCT = Decimal("2.0")
_DELTA_STOP = Decimal("0.35")
_DELTA_WARN = Decimal("0.25")
_TIME_STOP_DTE = 14
_DTE_WARN = 21
_ROLL_WING_DELTA_LO = Decimal("0.10")
_ROLL_WING_DELTA_HI = Decimal("0.20")
_ROLL_WING_TARGET_DELTA = Decimal("0.15")
```

**`ICExpiryConfig`** import path: `from src.strategy.ic_expiry_config import ICExpiryConfig, CONFIGS`

**`strategy_name` as class attribute** (current): `strategy_name: str = "paper_ic_nifty_v1"`.
After IC-M1, the canonical monthly name is `"paper_ic_nifty_v1_monthly"`. The legacy
`STRATEGY_IC = "paper_ic_nifty_v1"` constant in `constants.py` is kept for backward
compatibility but no new code should emit that string from this story onward.

**`StrategyMonitor._dispatch`** reads `strategy_name` via `strategy.strategy_name` (attribute
access). A `@property` satisfies this access pattern without any monitor changes — confirmed
by `grep strategy.strategy_name scripts/monitor_daemon.py` returning no direct attribute
assignments (it's read-only access).
