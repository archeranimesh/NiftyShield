# council-refactor — Daemon Overlay Registration Fix

> This story is a prerequisite for `MONITOR_OVERLAYS=1` to be useful.
> Without it, setting `MONITOR_OVERLAYS=1` registers CC, PP, and Collar with
> `store=None`, `notifier=None`, which means auto_execute fires but apply_action
> cannot write to the DB — silently corrupted state.

---

## Background: Two Execution Paths

The system has two signal-detection paths that never share state:

| Path | When | Signal detection | Auto-execute? |
|---|---|---|---|
| `StrategyMonitor` daemon | 09:15–15:30 (live ticks) | `strategy.check_signals()` per tick | Yes — if `auto_execute=True` |
| EOD snapshot cron | 15:35 (after daemon is dead) | `_dispatch_evaluate()` per position | No — writes event + plain Telegram only |

The daemon is stopped at 15:30 (`stop_monitor` cron). The EOD snapshot starts at 15:35.
They never run concurrently. Signals detected at EOD are **never auto-executed today** —
AUTO-1 closes this gap at the snapshot level.

DAEMON-FIX enables overlays in the daemon for intraday auto-execution (a bonus).
AUTO-1 is the primary automation story — it works regardless of MONITOR_OVERLAYS.

---

## DAEMON-FIX `[Claude]` — Fix overlay registration + dependency injection

**Files:**
- `scripts/monitor_daemon.py`
- `.env` (set `MONITOR_OVERLAYS=1`)

**Prerequisite:** CC-4 committed (CCOverlayV1 has `__init__` with store/notifier/vix_data_dir).
PP-2 committed (PPOverlayV1 has `__init__`). COLLAR-1 committed (CollarOverlayV1 has `__init__`).

**Before any code:**
- `get_code_snippet("CCOverlayV1.__init__")` — confirm param names: store, notifier, vix_data_dir
- `get_code_snippet("PPOverlayV1.__init__")` — confirm param names: broker, store, lookup, notifier, vix_data_dir
- `get_code_snippet("CollarOverlayV1.__init__")` — confirm param names post COLLAR-1
- `search_code("MONITOR_OVERLAYS")` in `scripts/monitor_daemon.py` — find the overlay registration block

**The bug:**

Current registration (line ~301 in `monitor_daemon.py`):
```python
for overlay_cls, overlay_name in [
    (CCOverlayV1, "CCOverlayV1"),
    (PPOverlayV1, "PPOverlayV1"),
    (CollarOverlayV1, "CollarOverlayV1"),
]:
    strategies.append(overlay_cls())   # ← zero args; store=None, notifier=None
```

`auto_execute=True` fires in `StrategyMonitor._route_event` → `apply_action` is called →
`self._store.record_trade(...)` raises `AttributeError: 'NoneType' has no attribute 'record_trade'`.
Silently caught by the broad `except Exception` in `_route_event`, logged as error, strategy
continues. Position is never closed.

**Fix:**

```python
if MONITOR_OVERLAYS:
    logger.info("MONITOR_OVERLAYS=1 — registering overlay strategies")
    vix_data_dir = Path(settings.vix_data_dir) if settings.vix_data_dir else None

    overlay_specs: list[tuple[type, str, dict]] = [
        (CCOverlayV1, "CCOverlayV1", {
            "store": store,
            "notifier": gateway,
            "vix_data_dir": vix_data_dir,
        }),
        (PPOverlayV1, "PPOverlayV1", {
            "broker": broker,
            "store": store,
            "lookup": lookup,
            "notifier": gateway,
            "vix_data_dir": vix_data_dir,
        }),
        (CollarOverlayV1, "CollarOverlayV1", {
            "store": store,
            "notifier": gateway,
            "vix_data_dir": vix_data_dir,
        }),
    ]
    for overlay_cls, overlay_name, kwargs in overlay_specs:
        if overlay_cls is not None:
            try:
                strategies.append(overlay_cls(**kwargs))
                logger.info("Registered overlay strategy", name=overlay_name)
            except Exception as e:
                logger.error(
                    "Failed to initialize overlay strategy",
                    name=overlay_name,
                    error=str(e),
                )
        else:
            logger.warning(
                "Overlay module not found; skipping registration",
                name=overlay_name,
            )
```

**`.env` change:**
```
MONITOR_OVERLAYS=1
```

Add comment above:
```
# Set to 1 to enable CC, PP, and Collar overlay strategies in the intraday daemon.
# Requires COLLAR-1 committed (CollarOverlayV1 with full __init__).
# AUTO-1 handles EOD auto-execution independently of this flag.
MONITOR_OVERLAYS=1
```

**Note on `lookup`:** `PPOverlayV1` needs `lookup: InstrumentLookup` for strike selection on
ROLL_PP and OPEN_NEW_PP. Confirm `lookup` is in scope in `monitor_daemon.py`'s `_run` function.
If not, instantiate it: `lookup = InstrumentLookup(settings.instruments_path)`.

**No new tests required** — this is a wiring change; existing strategy tests cover the logic.
Manual verification: after commit, run `python -m scripts.start_monitor --dry-run` and confirm
all three overlay strategies appear in the startup log.

**Commit:** `feat(daemon): fix overlay dependency injection; enable MONITOR_OVERLAYS=1`
