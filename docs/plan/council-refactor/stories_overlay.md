# council-refactor — Overlay Roll Stories

> Shared context and signal tables: `README.md`
> Prerequisite: CR1b committed.

---

## CR2 `[Antigravity]` — `evaluate_roll_overlay()` in `ExitSignalEngine`

**Files:** `src/strategy/exit_signals.py`, `tests/unit/strategy/test_exit_signals.py`

**Prerequisite:** CR1b committed — `ExitSignalResult` field list confirmed.

**Before any code:**
- `get_code_snippet("ExitSignalEngine")` — confirm CR1b signals committed
- `get_code_snippet("ExitSignalResult")` — field list
- `search_code("BASE_ROLL_ROLES")` in `scripts/` — confirm base role names

**What to implement:**

```python
_OVERLAY_SHORT_CALL_ROLES = {"cc_short_call", "collar_short_call"}
_OVERLAY_LONG_PUT_ROLES = {"pp_long_put", "collar_long_put"}
_OVERLAY_STRIKE_OFFSET = 50   # points
_BASE_DTE_GUARD = 10          # if base DTE <= this, block overlay roll

@classmethod
def evaluate_roll_overlay(
    cls,
    *,
    leg_role: str,
    dte: int,
    base_dte: int,
    atm_strike: int,
) -> list[ExitSignalResult]:
    """Evaluate whether an overlay leg is eligible to roll.

    Triggers when dte <= 5.
    If base_dte <= _BASE_DTE_GUARD: returns ROLL_BASE_FIRST WARN.
    Otherwise: returns ROLL_ELIGIBLE ACTION with suggested strike in notes.

    Strike suggestion (advisory — actual selection via strike_selector):
      short call roles: ATM + 50
      long put roles:   ATM - 50

    Raises:
        ValueError: When leg_role is not a known overlay role.
    """
```

If `leg_role` not in `_OVERLAY_SHORT_CALL_ROLES | _OVERLAY_LONG_PUT_ROLES` → raise `ValueError`.

Base-DTE guard result (WARN):
```python
ExitSignalResult(
    exit_signal="ROLL_BASE_FIRST",
    severity="WARN",
    threshold_value=float(_BASE_DTE_GUARD),
    notes=f"Base DTE {base_dte} ≤ {_BASE_DTE_GUARD} — roll base first",
)
```

Roll eligible result (short call):
```python
ExitSignalResult(
    exit_signal="ROLL_ELIGIBLE",
    severity="ACTION",
    threshold_value=5.0,
    notes=f"DTE {dte} ≤ 5 — suggested strike {atm_strike + _OVERLAY_STRIKE_OFFSET}",
)
```

**Tests:**
- CC leg, `dte=4`, `base_dte=25` → `ROLL_ELIGIBLE` ACTION; notes contain `atm_strike + 50`
- PP leg, `dte=4`, `base_dte=25` → `ROLL_ELIGIBLE` ACTION; notes contain `atm_strike - 50`
- `dte=6` → `[]`
- `base_dte=8` → `ROLL_BASE_FIRST` WARN
- `base_dte=11` → `ROLL_ELIGIBLE` (guard does not fire)
- Unknown `leg_role` → `ValueError`
- Collar short call → same result as CC
- Collar long put → same result as PP

**Commit:** `feat(strategy): add evaluate_roll_overlay to ExitSignalEngine with base-DTE guard`

---

## CR3 `[Claude]` — Wire roll signals into overlay strategies

**Files:**
- `src/strategy/nifty_track_comparison_v1.py`
- `tests/unit/strategy/test_nifty_track_comparison_v1.py`

**Prerequisite:** CR2 committed.

**Before any code:**
- `get_code_snippet("NiftyTrackComparisonV1.check_signals")` — current WARN emit logic
- `get_code_snippet("evaluate_roll_overlay")` — CR2 signature

**Changes:**

When DTE ≤ 5, replace `ROLL_DUE_DTE` WARN emission with a call to
`ExitSignalEngine.evaluate_roll_overlay(leg_role, dte, base_dte, atm_strike)`:

- `ROLL_ELIGIBLE` ACTION → emit `SignalEvent(severity="ACTION", payload={..., "action_options": ["RECORD_ROLL"]})`
- `ROLL_BASE_FIRST` WARN → keep as WARN (same as current `ROLL_DUE_DTE`)
- DTE 6–10: keep existing `ROLL_DUE_DTE` WARN unchanged

Note: `NiftyTrackComparisonV1` does NOT set `auto_execute = True` — overlay rolls require
human confirmation. Leg selection order (which overlay to roll first) is not deterministic.

**Tests:**
- Overlay leg `dte=4`, `base_dte=25` → `ROLL_ELIGIBLE` ACTION in signals
- Overlay leg `dte=8` → `ROLL_DUE_DTE` WARN (unchanged)
- `base_dte=8` → `ROLL_BASE_FIRST` WARN; no `ROLL_ELIGIBLE`
- Healthy overlay (`dte=20`) → `[]`

**Commit:** `feat(strategy): wire evaluate_roll_overlay into NiftyTrackComparisonV1`
