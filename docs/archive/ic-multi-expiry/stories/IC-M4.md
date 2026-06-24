# IC-M4 — Register four `IronCondorV1` instances in `monitor_daemon.py`

> **Assigned to: Antigravity** — mechanical replacement of one registration block with four.

**Prerequisites (both must be committed before starting):**
- ic-multi-expiry IC-M2 — `IronCondorV1` must accept `ICExpiryConfig`

**Files to change:**
- `scripts/monitor_daemon.py` — replace the single `IronCondorV1` registration with a loop over all four `CONFIGS` presets
- `tests/unit/test_monitor_daemon.py` — update/add tests for four-instance registration (if this test file exists; check first)

---

## Context

`monitor_daemon.py` currently registers one `IronCondorV1`:

```python
if IronCondorV1 is not None:
    try:
        strategies.append(
            IronCondorV1(broker=broker, store=store, notifier=gateway)
        )
        logger.info("Registered IronCondorV1 strategy")
    except Exception as e:
        logger.error("Failed to initialize IronCondorV1", error=str(e))
else:
    logger.warning("IronCondorV1 module not found; skipping registration")
```

After IC-M2, `IronCondorV1(broker, store, notifier)` with no config defaults to monthly.
This story replaces that single registration with a loop over all four presets, so all
four IC variants are monitored simultaneously.

---

## What to implement

### `scripts/monitor_daemon.py`

Replace the existing `IronCondorV1` registration block with:

```python
if IronCondorV1 is not None:
    from src.strategy.ic_expiry_config import CONFIGS as IC_CONFIGS
    for expiry_type, ic_config in IC_CONFIGS.items():
        try:
            strategies.append(
                IronCondorV1(broker=broker, store=store, notifier=gateway, config=ic_config)
            )
            logger.info("Registered IronCondorV1 strategy", expiry_type=expiry_type)
        except Exception as e:
            logger.error(
                "Failed to initialize IronCondorV1",
                expiry_type=expiry_type,
                error=str(e),
            )
else:
    logger.warning("IronCondorV1 module not found; skipping registration")
```

No other changes to `monitor_daemon.py`. The guard pattern (`if IronCondorV1 is not None`)
and the try/except per-registration are preserved — a failure on one expiry type does not
prevent the others from registering.

---

## Tests

**Check first:** run `find tests/ -name "test_monitor_daemon.py"` — if the file does not
exist, create it. If it exists, add tests there.

**New tests to add:**

1. `test_four_ic_strategies_registered` — mock `IronCondorV1` import, `CONFIGS`, broker,
   store, gateway. Call the daemon's strategy-building function (or mock the registration
   block). Assert that four `IronCondorV1` instances were appended to `strategies`, each
   with a distinct `strategy_name`.

2. `test_one_ic_failure_does_not_block_others` — mock `IronCondorV1.__init__` to raise
   on the `"weekly"` config only. Assert three instances still register successfully and
   one `logger.error` was called with `expiry_type="weekly"`.

---

## Commit

```
feat(daemon): register all four IronCondorV1 expiry variants in monitor_daemon

Why: Multi-expiry IC paper research requires simultaneous monitoring of
weekly/monthly/leaps/yearly positions; single registration only covered monthly.
What:
- scripts/monitor_daemon.py: loop over IC_CONFIGS presets; per-instance try/except
- tests/unit/test_monitor_daemon.py: 2 new multi-instance registration tests
Ref: ic-multi-expiry IC-M4
```

---

## Pre-baked Context

**Existing IronCondorV1 registration block** in `scripts/monitor_daemon.py` (lines ~256–270):
```python
if IronCondorV1 is not None:
    try:
        strategies.append(
            IronCondorV1(broker=broker, store=store, notifier=gateway)
        )
        logger.info("Registered IronCondorV1 strategy")
    except Exception as e:
        logger.error("Failed to initialize IronCondorV1", error=str(e))
else:
    logger.warning("IronCondorV1 module not found; skipping registration")
```

**Import guard pattern** — `IronCondorV1` is imported inside a try/except at module level
(lines ~57–60):
```python
try:
    from src.strategy.ic_nifty_v1 import IronCondorV1
except ImportError:
    IronCondorV1 = None
```
The `IC_CONFIGS` import must be inside the `if IronCondorV1 is not None:` block to avoid
a bare import at module level (consistent with the existing pattern).

**`CONFIGS` dict key order:** `"weekly"`, `"monthly"`, `"leaps"`, `"yearly"` (insertion order,
Python 3.7+ dict). The loop will register in that order. `StrategyMonitor.register()` appends
to a list — order affects tick evaluation order, which is fine (all four run on every tick).
