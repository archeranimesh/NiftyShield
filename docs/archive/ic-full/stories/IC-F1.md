# IC-F1 — Wire IVR into `IronCondorV1.describe_context`

> **Assigned to: Claude** — single-method change; no structural impact.

**Prerequisite:** None — first story in the chain.

**Files to change:**
- `src/strategy/ic_nifty_v1.py` — `describe_context`: replace `"IVR: N/A (not yet wired)"` with live VIX-based IVR
- `tests/unit/strategy/test_ic_nifty_v1.py` — 2 new tests

---

## Context

`describe_context` currently emits `"IVR: N/A (not yet wired)"`. This string appears
in every Telegram signal message and in council prompts. Without IVR the context block
is incomplete — the receiving agent cannot assess whether the IC was entered at
favourable volatility or not.

`paper_cc_entry.py` already demonstrates the pattern: load VIX Parquet series via
`load_vix_series()`, fetch today's VIX via `fetch_vix_latest()`, compute
`compute_ivr(vix_today, vix_series)`. The same three calls apply here.

`describe_context` is synchronous in the current protocol. Keep it synchronous — load
VIX data inline. If the Parquet directory does not exist or `compute_ivr` returns
`None`, emit `"IVR: unavailable"` (not an error — data gap is expected in early paper cycles).

---

## What to implement

### `src/strategy/ic_nifty_v1.py` — `describe_context`

Replace:
```python
"IVR: N/A (not yet wired)",
```

With:
```python
from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import fetch_vix_latest, load_vix_series
from pathlib import Path

vix_dir = Path("data/historical/ohlc/india_vix")
ivr_str = "unavailable"
if vix_dir.exists():
    try:
        vix_series = load_vix_series(vix_dir)
        vix_today = fetch_vix_latest(vix_dir)
        if vix_today is not None:
            ivr = compute_ivr(vix_today, vix_series)
            ivr_str = f"{ivr:.2f}" if ivr is not None else "unavailable"
    except Exception:
        pass  # non-fatal: VIX data gap

f"IVR: {ivr_str}",
```

Keep the imports local to the method body — `describe_context` is the only caller;
no module-level import needed.

---

## Tests (`tests/unit/strategy/test_ic_nifty_v1.py`)

**Happy-path test:**
1. `test_describe_context_ivr_present` — mock `load_vix_series`, `fetch_vix_latest`,
   `compute_ivr` to return a known IVR (e.g. `0.42`). Call `describe_context`.
   Assert the returned string contains `"IVR: 0.42"`.

**Edge/error test:**
2. `test_describe_context_ivr_unavailable` — mock VIX directory to not exist (patch
   `Path.exists` to return `False`). Assert returned string contains `"IVR: unavailable"`.
   Assert no exception is raised.

---

## Commit

```
feat(strategy): wire IVR into IronCondorV1.describe_context

Why: Telegram context blocks showed "N/A" for IVR; signal receiver
cannot assess entry volatility quality without it.
What:
- src/strategy/ic_nifty_v1.py: describe_context loads VIX Parquet + computes IVR
- tests/unit/strategy/test_ic_nifty_v1.py: 2 new IVR wiring tests
Ref: ic-full IC-F1
```

---

## Pre-baked Context

**`describe_context` location:** `src/strategy/ic_nifty_v1.py`, line ~291.
Current IVR line: `"IVR: N/A (not yet wired)",` — exact string to replace.

**`compute_ivr`** — `src/backtest/ivr.py`.
Signature: `compute_ivr(vix_today: float, vix_series: pd.Series) -> float | None`.
Returns `None` when series is empty or all-equal.

**`load_vix_series`** — `src/backtest/vix_ingest.py`.
Signature: `load_vix_series(data_dir: Path) -> pd.Series`. Returns indexed float Series.

**`fetch_vix_latest`** — `src/backtest/vix_ingest.py`.
Signature: `fetch_vix_latest(data_dir: Path) -> float | None`. Returns today's VIX close or None.

**VIX data dir:** `Path("data/historical/ohlc/india_vix")` — relative to project root.
Script runs from project root (same as all other scripts), so relative path is correct.
