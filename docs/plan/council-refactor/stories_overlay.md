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

---

## NT-1 `[Antigravity]` — Proxy delta signals + consecutive-day state tracking

> **Source:** `docs/strategies/nifty_track_comparison_v1.md` — Proxy Early Exit Trigger,
> Proxy Delta Monitoring, Kill Criteria (premium decay).

**Files:**
- `src/strategy/exit_signals.py`
- `src/strategy/nifty_track_comparison_v1.py`
- `src/paper/store.py` (add `get_proxy_delta_breach_count` + `set_proxy_delta_breach_count`)
- `tests/unit/strategy/test_exit_signals.py`
- `tests/unit/strategy/test_nifty_track_comparison_v1.py`

**Prerequisite:** CR3 committed — `NiftyTrackComparisonV1.check_signals` wired with overlay roll signals.

**Before any code:**
- `get_code_snippet("ExitSignalEngine")` — confirm evaluate_roll_overlay committed (CR2 gate)
- `get_code_snippet("NiftyTrackComparisonV1.check_signals")` — current signal emit structure post-CR3
- `get_code_snippet("PaperStore")` — get public API for state storage; confirm no existing delta breach counter
- `search_graph("proxy_delta_breach_count")` — confirm does NOT yet exist

**What to add to `exit_signals.py`:**

Module-level constants:
```python
_PROXY_DELTA_WARN = 0.65        # warning threshold — emit WARN, do not close
_PROXY_DELTA_CRITICAL = 0.40    # critical threshold — close after 3 consecutive days
_PROXY_DELTA_CONSECUTIVE = 3    # consecutive days below critical before ACTION fires
_PROXY_PREMIUM_FLOOR = Decimal("0.50")   # premium decay kill — close if mark < this with DTE >= 5
```

New classmethod:
```python
@classmethod
def evaluate_proxy_delta(
    cls,
    *,
    current_delta: float,
    current_mark: Decimal,
    dte: int,
    days_below_critical: int = 0,
) -> list[ExitSignalResult]:
    """Evaluate exit signals for the Proxy deep ITM call leg.

    Three independent signals in priority order:

    1. PROXY_DELTA_CRITICAL (ACTION): delta < 0.40 AND days_below_critical >= 3.
       Close immediately and re-enter at delta ≈ 0.90.
    2. PROXY_PREMIUM_DECAY (ACTION): current_mark < 0.50 AND dte >= 5.
       Deep ITM call has lost virtually all optionality — carry risk is too high.
    3. PROXY_DELTA_WARN (WARN): delta < 0.65. Flag for monitoring; no close.

    PROXY_DELTA_CRITICAL and PROXY_PREMIUM_DECAY are independent — both can fire
    simultaneously. PROXY_DELTA_WARN is suppressed if PROXY_DELTA_CRITICAL fires
    (CRITICAL subsumes WARN).

    Args:
        current_delta: Current delta of the deep ITM call (positive float, 0–1).
        current_mark: Current mark-to-market price of the call (positive Decimal).
        dte: Calendar days to expiry.
        days_below_critical: Consecutive trading days delta has been < 0.40.
            Caller is responsible for maintaining this count across sessions.

    Returns:
        List of ExitSignalResult ordered ACTION before WARN.
    """
```

Signal results:

```python
# PROXY_DELTA_CRITICAL
ExitSignalResult(
    exit_signal="PROXY_DELTA_CRITICAL",
    severity="ACTION",
    threshold_value=_PROXY_DELTA_CRITICAL,
    notes=f"delta {current_delta:.3f} < {_PROXY_DELTA_CRITICAL} for {days_below_critical} consecutive days — close and re-enter at δ≈0.90",
)

# PROXY_PREMIUM_DECAY
ExitSignalResult(
    exit_signal="PROXY_PREMIUM_DECAY",
    severity="ACTION",
    threshold_value=float(_PROXY_PREMIUM_FLOOR),
    notes=f"mark ₹{current_mark} < ₹{_PROXY_PREMIUM_FLOOR} with DTE {dte} — optionality exhausted",
)

# PROXY_DELTA_WARN
ExitSignalResult(
    exit_signal="PROXY_DELTA_WARN",
    severity="WARN",
    threshold_value=_PROXY_DELTA_WARN,
    notes=f"delta {current_delta:.3f} < {_PROXY_DELTA_WARN} — monitor; {_PROXY_DELTA_CONSECUTIVE - days_below_critical} more days below {_PROXY_DELTA_CRITICAL} triggers close",
)
```

**Consecutive-day state in `PaperStore`:**

Add two methods to `src/paper/store.py`:

```python
def get_proxy_delta_breach_count(self, strategy_name: str) -> int:
    """Return the number of consecutive trading days the Proxy delta has been below
    _PROXY_DELTA_CRITICAL (0.40). Returns 0 if no record exists.

    Args:
        strategy_name: Strategy namespace (e.g. 'paper_nifty_proxy').

    Returns:
        Non-negative integer.
    """

def set_proxy_delta_breach_count(self, strategy_name: str, count: int) -> None:
    """Persist the consecutive Proxy delta breach count.
    Resets to 0 when delta recovers above _PROXY_DELTA_CRITICAL.

    Args:
        strategy_name: Strategy namespace.
        count: New breach count (0 to reset, N to increment).
    """
```

Storage: add a `proxy_delta_breach_count INTEGER DEFAULT 0` column to the
`paper_strategies` table (or create the table if it does not exist). Use `INSERT OR REPLACE`.

**Wiring into `NiftyTrackComparisonV1.check_signals()`:**

For any position with `leg_role == "base_ditm_call"`:
1. Fetch `days_below_critical = store.get_proxy_delta_breach_count(strategy_name)`.
2. Call `ExitSignalEngine.evaluate_proxy_delta(current_delta, current_mark, dte, days_below_critical)`.
3. If delta < `_PROXY_DELTA_CRITICAL`: call `store.set_proxy_delta_breach_count(strategy_name, days_below_critical + 1)`.
4. Else: call `store.set_proxy_delta_breach_count(strategy_name, 0)` (reset on recovery).
5. Emit all returned signals as `SignalEvent` entries (ACTION payloads include `"valid_actions": ["RECORD_REENTRY"]`).

`NiftyTrackComparisonV1` does NOT set `auto_execute = True` — Proxy re-entry requires
human confirmation (strike selection via `find_strike_by_delta.py`).

**Tests (`tests/unit/strategy/test_exit_signals.py`) — `evaluate_proxy_delta`:**

- `delta=0.88, mark=Decimal("120"), dte=20, days_below_critical=0` → `[]` (healthy)
- `delta=0.62, mark=Decimal("80"), dte=20` → `[PROXY_DELTA_WARN]` (below 0.65, above 0.40)
- `delta=0.38, mark=Decimal("80"), dte=20, days_below_critical=2` → `[PROXY_DELTA_WARN]` (critical threshold hit but only 2 days — warn, not action)
- `delta=0.38, mark=Decimal("80"), dte=20, days_below_critical=3` → `[PROXY_DELTA_CRITICAL]` (3 days — action; WARN suppressed)
- `delta=0.38, mark=Decimal("80"), dte=20, days_below_critical=5` → `[PROXY_DELTA_CRITICAL]` (5 days still fires)
- `delta=0.88, mark=Decimal("0.40"), dte=8` → `[PROXY_PREMIUM_DECAY]` (mark below floor, DTE ≥ 5)
- `delta=0.88, mark=Decimal("0.40"), dte=4` → `[]` (DTE < 5 — premium decay not triggered; ride to expiry)
- `delta=0.38, mark=Decimal("0.40"), dte=8, days_below_critical=3` → `[PROXY_DELTA_CRITICAL, PROXY_PREMIUM_DECAY]` (both fire)

**Tests (`tests/unit/strategy/test_nifty_track_comparison_v1.py`):**

- Proxy leg with `delta=0.62`: `get_proxy_delta_breach_count` not called (only called when `leg_role == "base_ditm_call"`); PROXY_DELTA_WARN in events.
- Proxy leg `delta=0.38`, breach count returns 2 → PROXY_DELTA_WARN; `set_proxy_delta_breach_count` called with `count=3`.
- Proxy leg `delta=0.38`, breach count returns 3 → PROXY_DELTA_CRITICAL ACTION; `set_proxy_delta_breach_count` called with `count=4`.
- Proxy leg `delta=0.90` (recovered), breach count was 2 → `set_proxy_delta_breach_count` called with `count=0`.
- `store=None` → no crash; signals still emitted without persistence.

**Commit:** `feat(strategy): evaluate_proxy_delta — consecutive-day critical/warn/premium-decay signals; PaperStore breach counter`

---

## NT-2 `[Claude]` — Futures + standalone CC runtime block in `NiftyTrackComparisonV1`

> **Source:** `docs/strategies/nifty_track_comparison_v1.md` — Approved Overlay Menu,
> Blocked Combinations. "Futures + standalone Covered Call: permanently blocked per council ruling."

**Files:**
- `src/strategy/nifty_track_comparison_v1.py`
- `tests/unit/strategy/test_nifty_track_comparison_v1.py`

**Prerequisite:** CR3 committed.

**Before any code:**
- `get_code_snippet("NiftyTrackComparisonV1.check_signals")` — current position loop structure
- `search_graph("SHORT_CALL_ROLES")` — get the set of short call role strings used elsewhere
- `search_code("paper_nifty_futures")` in `src/strategy/` — confirm strategy namespace constant

**What to implement:**

Add module-level constant:
```python
_FUTURES_BLOCKED_ROLES: frozenset[str] = frozenset({
    "overlay_cc",
    "cc_short_call",
    "collar_short_call",   # collar on futures IS allowed — guard must not fire for collar
})
# Collar short call is present in a collar (paired with overlay_collar_put).
# Block only STANDALONE short calls — a collar call paired without a put is also blocked.
# Guard logic: short call role present AND no paired long put in the same position set.
```

Add a private helper:
```python
def _check_futures_cc_block(
    self,
    positions: list[PaperPosition],
    strategy_name: str,
) -> list[SignalEvent]:
    """Emit BLOCKED_COMBINATION ERROR if a standalone covered call exists on a Futures base.

    Futures + standalone short call = synthetic short put (unlimited downside).
    Collar (short call + long put together) is explicitly permitted.

    A short call is considered standalone if no position in the same strategy_name
    has leg_role in {'overlay_collar_put', 'pp_long_put'}.

    Args:
        positions: All open positions for this strategy track.
        strategy_name: The futures strategy namespace (e.g. 'paper_nifty_futures').

    Returns:
        List containing one BLOCKED_COMBINATION SignalEvent if the block fires, else [].
    """
```

Guard logic:
1. If `strategy_name != "paper_nifty_futures"`: return `[]` immediately (guard only applies to Futures track).
2. Collect all short call positions: `[p for p in positions if p.leg_role in _FUTURES_BLOCKED_ROLES]`.
3. If none: return `[]`.
4. Check for paired long put: `any(p.leg_role in {"overlay_collar_put", "pp_long_put"} for p in positions)`.
5. If a short call exists AND no long put paired: emit:

```python
SignalEvent(
    severity="ERROR",
    signal="BLOCKED_COMBINATION",
    payload={
        "message": "Futures + standalone short call detected — synthetic short put (unlimited downside). Close the short call leg immediately.",
        "violating_roles": [p.leg_role for p in short_call_positions],
        "action_required": "CLOSE_LEG",
    },
)
```

Call `_check_futures_cc_block` at the top of `check_signals()` before any other signal evaluation. If it returns a non-empty list, prepend those events and continue (do not short-circuit — also emit any other signals so the operator sees the full picture).

**Tests (`tests/unit/strategy/test_nifty_track_comparison_v1.py`):**

- Futures base + `overlay_cc` leg, no long put → `BLOCKED_COMBINATION` ERROR in events
- Futures base + `overlay_cc` + `overlay_collar_put` (collar) → no `BLOCKED_COMBINATION` (collar is allowed)
- Futures base + `collar_short_call` + `overlay_collar_put` → no block
- Futures base + `collar_short_call`, no paired put → `BLOCKED_COMBINATION` (degenerate collar — put missing)
- Spot base + `overlay_cc` → no `BLOCKED_COMBINATION` (guard only fires on Futures namespace)
- Proxy base + `overlay_cc` → no `BLOCKED_COMBINATION`
- Futures base, no overlays → no `BLOCKED_COMBINATION`

**Commit:** `feat(strategy): NiftyTrackComparisonV1 — Futures+CC block guard with collar exemption`
