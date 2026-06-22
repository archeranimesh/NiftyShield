# IC-E3 — Wire IVR into `IronCondorV1.describe_context`

> **Assigned to: Claude** — single-function change; IVR wiring pattern already established in codebase.

**Prerequisite:** IC-E1 committed.

**Files to change:**
- `src/strategy/ic_nifty_v1.py` — replace hardcoded `"IVR: N/A (not yet wired)"` with live IVR computation
- `tests/unit/strategy/test_ic_nifty_v1.py` — add `describe_context` IVR tests

---

## Context

`IronCondorV1.describe_context` currently emits `"IVR: N/A (not yet wired)"`.
When a Telegram approval request fires for a DELTA_STOP or TIME_STOP signal, the operator
sees no IVR information — a key input for deciding whether to close or roll.

The IVR wiring pattern is already established in `paper_cc_entry.py`:
- `load_vix_series(vix_data_dir)` → Parquet series
- `fetch_vix_latest()` → today's VIX float
- `compute_ivr(vix_today, vix_series)` → float | None

`describe_context` is called synchronously inside `StrategyMonitor._dispatch`.
`compute_ivr` is a pure function (no I/O). The I/O — loading the Parquet series — must
be done in `__init__` (lazy-load on first `describe_context` call via `functools.cached_property`
or a `_vix_series` instance attribute loaded at construction time).

**Design choice:** Load VIX series once at construction time into `self._vix_series`.
If the Parquet path does not exist, set `self._vix_series = None` and log a WARNING.
`describe_context` uses the cached series; if `None`, falls back to `"N/A (no VIX data)"`.

This avoids repeated disk reads on every tick and keeps `describe_context` free of I/O.

---

## What to implement

### 1. `IronCondorV1.__init__` — load VIX series

```python
def __init__(
    self,
    broker: BrokerClient,
    store: PaperStore,
    notifier: TelegramGateway,
    vix_data_dir: Path | None = None,
) -> None:
    self._broker = broker
    self._store = store
    self._notifier = notifier
    self._vix_series: pd.Series | None = None

    _vix_dir = vix_data_dir or Path("data/historical/ohlc/india_vix")
    if _vix_dir.exists():
        try:
            self._vix_series = load_vix_series(_vix_dir)
            log.info("ic_nifty_v1.vix_series_loaded", rows=len(self._vix_series))
        except Exception:
            log.warning("ic_nifty_v1.vix_series_load_failed", vix_dir=str(_vix_dir))
    else:
        log.warning("ic_nifty_v1.vix_data_dir_missing", vix_dir=str(_vix_dir))
```

Add the `vix_data_dir` parameter to the constructor. Existing call sites in `monitor_daemon.py`
pass `broker`, `store`, `notifier` — the new parameter is optional with a sensible default,
so no changes to `monitor_daemon.py` are needed.

### 2. `describe_context` — replace the hardcoded IVR line

Replace:
```python
"IVR: N/A (not yet wired)",
```

With:
```python
ivr_str = self._compute_ivr_str()
f"IVR: {ivr_str}",
```

Add private helper:
```python
def _compute_ivr_str(self) -> str:
    """Return a formatted IVR string, or a fallback label when data is unavailable.

    Returns:
        IVR as a percentage string (e.g. "42.0%") or "N/A (no VIX data)".
    """
    if self._vix_series is None:
        return "N/A (no VIX data)"
    try:
        vix_today = fetch_vix_latest()
        ivr = compute_ivr(vix_today, self._vix_series)
        if ivr is None:
            return "N/A (insufficient VIX history)"
        return f"{ivr * 100:.1f}%"
    except Exception:
        log.warning("ic_nifty_v1.ivr_compute_failed")
        return "N/A (compute error)"
```

`fetch_vix_latest()` is a lightweight API call (single data point). It is acceptable in
`describe_context` because that method is only called when an ACTION signal fires — not
on every tick. If the call fails, the fallback label prevents blocking the Telegram message.

### 3. Imports to add

```python
from pathlib import Path

import pandas as pd

from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import fetch_vix_latest, load_vix_series
```

---

## Tests (`tests/unit/strategy/test_ic_nifty_v1.py`)

All tests offline. Patch `fetch_vix_latest` and `load_vix_series`.

**Happy-path tests:**
1. `IronCondorV1` constructed with a mock `vix_data_dir` that exists and `load_vix_series`
   returns a 252-row Series → `describe_context` output contains `"IVR: "` and a percentage.
2. `_compute_ivr_str()` with `_vix_series` populated and `fetch_vix_latest` returning 15.0
   and `compute_ivr` returning 0.42 → returns `"42.0%"`.

**Edge/error tests:**
3. `vix_data_dir` does not exist → `self._vix_series is None` → `describe_context` contains
   `"IVR: N/A (no VIX data)"`.
4. `fetch_vix_latest` raises an exception → `_compute_ivr_str` returns `"N/A (compute error)"`,
   no exception propagates.
5. `compute_ivr` returns `None` (insufficient history) → `"N/A (insufficient VIX history)"`.

---

## Commit

```
feat(strategy): wire IVR into IronCondorV1.describe_context

Why: Telegram approval context showed "N/A (not yet wired)" for IVR — missing
key input for DELTA_STOP and TIME_STOP approval decisions.
What:
- src/strategy/ic_nifty_v1.py: vix_data_dir param in __init__, _compute_ivr_str(),
  describe_context IVR line replaced
- tests/unit/strategy/test_ic_nifty_v1.py: 5 new IVR context tests
Ref: ic-e2e IC-E3
```

---

## Pre-baked Context

**`IronCondorV1.describe_context`** — `src/strategy/ic_nifty_v1.py` lines ~280–340.
Current hardcoded line: `"IVR: N/A (not yet wired)"` (line ~318).

**`compute_ivr`** — `src/backtest/ivr.py`.
Signature: `compute_ivr(vix_today: float, vix_series: pd.Series) -> float | None`.
Returns `None` when series has fewer than 2 data points.

**`load_vix_series`** — `src/backtest/vix_ingest.py`.
Signature: `load_vix_series(data_dir: Path) -> pd.Series`.
Reads Parquet files from `data_dir`; returns a Series indexed by date, values are VIX floats.

**`fetch_vix_latest`** — `src/backtest/vix_ingest.py`.
Signature: `fetch_vix_latest() -> float`.
Makes a single Upstox API call. May raise on network failure.

**`IronCondorV1.__init__`** current signature (from graph):
`__init__(self, broker: BrokerClient, store: PaperStore, notifier: TelegramGateway)`.
Add `vix_data_dir: Path | None = None` as the fourth parameter.

**`monitor_daemon.py`** IC registration block (lines ~256–270):
```python
IronCondorV1(
    broker=broker,
    store=store,
    notifier=gateway,
)
```
No change needed — `vix_data_dir` defaults to `Path("data/historical/ohlc/india_vix")`.
