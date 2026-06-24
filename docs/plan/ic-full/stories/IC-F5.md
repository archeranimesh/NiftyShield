# IC-F5 — Register four `IronCondorV1` instances in `monitor_daemon.py`

> **Assigned to: Antigravity** — mechanical replacement; TDD.

**Prerequisite:** IC-F3 committed — `IronCondorV1` must accept `ICExpiryConfig`.

**Files to change:**
- `scripts/monitor_daemon.py`
- `tests/unit/test_monitor_daemon.py` (create if absent)

---

## What to implement

### `scripts/monitor_daemon.py`

Replace the single `IronCondorV1` registration block (lines ~256–270) with:

```python
if IronCondorV1 is not None:
    from src.strategy.ic_expiry_config import CONFIGS as IC_CONFIGS
    for expiry_type, ic_config in IC_CONFIGS.items():
        try:
            strategies.append(
                IronCondorV1(broker=broker, store=store, notifier=gateway, config=ic_config)
            )
            logger.info("Registered IronCondorV1", expiry_type=expiry_type,
                        strategy_name=ic_config.strategy_name)
        except Exception as e:
            logger.error("Failed to initialize IronCondorV1",
                         expiry_type=expiry_type, error=str(e))
else:
    logger.warning("IronCondorV1 module not found; skipping IC registration")
```

The `IC_CONFIGS` import is inside the `if IronCondorV1 is not None` block — consistent
with the existing lazy-import pattern for all strategy modules in this file.

---

## Tests

**Check first:** `find tests/ -name "test_monitor_daemon.py"`. Create if absent with a
single `__init__.py` in the test directory as needed.

1. `test_four_ic_strategies_registered` — mock `IronCondorV1`, `CONFIGS` (4 items),
   broker, store, gateway. Assert four `IronCondorV1` instances appended, each with
   a distinct `strategy_name`.

2. `test_one_ic_failure_does_not_block_others` — mock `IronCondorV1.__init__` to raise
   on `expiry_type="weekly"` only. Assert three instances registered; one `logger.error`
   with `expiry_type="weekly"`.

---

## Commit

```
feat(daemon): register all four IronCondorV1 expiry variants

Why: Single registration only covered monthly (default config); all four
IC research variants need simultaneous daemon monitoring.
What:
- scripts/monitor_daemon.py: loop over IC_CONFIGS; per-instance try/except
- tests/unit/test_monitor_daemon.py: 2 registration tests
Ref: ic-full IC-F5
```

---

## Pre-baked Context

**Existing registration block** (`scripts/monitor_daemon.py` lines ~256–270):
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

**Import guard** (lines ~57–60):
```python
try:
    from src.strategy.ic_nifty_v1 import IronCondorV1
except ImportError:
    IronCondorV1 = None
```
Keep this guard unchanged — it already handles missing module gracefully.

**`CONFIGS` insertion order:** `"weekly"`, `"monthly"`, `"leaps"`, `"yearly"`.
Four instances registered in that order. Registration order does not affect correctness —
`StrategyMonitor` evaluates all strategies on every tick.
