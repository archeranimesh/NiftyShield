# PA1.2 — `src/strategy/ic_nifty_v1.py`: IC wing-roll adjustment signals + apply_action ROLL branch
> **Assigned to: Claude** — requires reading IC strategy spec for wing-roll rules.

**Files to change:**
- `src/strategy/ic_nifty_v1.py` — add `ROLL_WING` signal, `_select_wing_roll_target()` helper, ROLL_WING in `_ALLOWED_ACTIONS`, ROLL_WING branch in `apply_action`
- `tests/unit/strategy/test_ic_nifty_v1.py` — extend with ROLL_WING signal + apply_action tests

**Before implementing:** Read `docs/strategies/ic_nifty_v1.md` for wing-roll entry rules and delta targets.

**Prerequisite:** PA0 (`src/strategy/roll_utils.py`) must be committed before this story.

---

## What to implement

### 1. New signal: `ROLL_WING` (ACTION severity)

`check_signals` should emit a `ROLL_WING` ACTION event when a **short leg's |delta| ≥ 0.35** (`DELTA_STOP` threshold) AND a replacement wing can be selected from the live chain. The intent: instead of closing the whole condor, roll only the threatened wing to a further OTM strike.

`ROLL_WING` payload:
```python
{
    "leg_role": str,                   # e.g. "short_call" or "short_put"
    "current_instrument_key": str,
    "current_delta": str,              # Decimal as string
    "suggested_instrument_key": str,   # selected by _select_wing_roll_target()
    "suggested_strike": str,           # Decimal as string
    "suggested_delta": str,            # target delta of the suggested replacement
    "suggested_mid_price": str,        # Decimal as string — LTP of suggested leg
}
```

`DELTA_STOP` (close full wing) still fires unchanged alongside `ROLL_WING`. The council decides which action to approve.

### 2. `_select_wing_roll_target(market: OptionChain, leg_role: str, current_strike: Decimal) -> LegSpec | None`

- For `leg_role == "short_call"`: find the nearest CE strike **above** `current_strike` with |delta| between 0.10–0.20, ranked by proximity to target delta 0.15.
- For `leg_role == "short_put"`: find the nearest PE strike **below** `current_strike` with |delta| between 0.10–0.20, ranked by proximity to target delta 0.15.
- Return `None` when no suitable strike found or chain data insufficient.
- Works purely from the passed `OptionChain` — no additional fetches.
- Use `roll_utils.find_strike_by_delta(chain, option_type, (Decimal("0.10"), Decimal("0.20")), Decimal("0.15"))` — do not re-implement delta filtering inline.
- Return a `LegSpec` with `action="SELL"`, `quantity=1`, `leg_role=leg_role`, `notes="roll_wing delta={delta}"`.

### 3. `apply_action` ROLL_WING branch

Add `"ROLL_WING"` to `_ALLOWED_ACTIONS`. Add branch:

```python
elif action.action_type == "ROLL_WING":
    if not action.legs_to_open:
        raise ValueError("ROLL_WING action requires at least one leg in legs_to_open")
    closed: set[str] = set(action.legs_to_close)
    return [p for p in positions if p.leg_role not in closed]
```

The executor already handles DB writes for both close and open.

---

## Tests (`tests/unit/strategy/test_ic_nifty_v1.py`)

**New happy-path tests:**
- Short call with |delta|=0.36 and chain has valid OTM CE replacement → `ROLL_WING` ACTION fires alongside `DELTA_STOP`
- Short put with |delta|=0.37 and chain has valid OTM PE replacement → `ROLL_WING` ACTION fires alongside `DELTA_STOP`
- `apply_action` with `ROLL_WING` + one `LegSpec` in `legs_to_open` → no error, closed leg removed from positions

**New edge/error tests:**
- Short call with |delta|=0.36 but chain has no CE in target delta range → `ROLL_WING` does NOT fire (only `DELTA_STOP` fires)
- `apply_action` with `ROLL_WING` + empty `legs_to_open` → raises `ValueError`
- Existing `apply_action` tests for `CLOSE_FULL`, `CLOSE_CALL_SPREAD`, `CLOSE_PUT_SPREAD` must still pass

---

## Commit

```
feat(strategy): add IronCondorV1 ROLL_WING signal with wing selection

Why: IC adjustment requires per-wing roll rather than full close;
executor already handles legs_to_open (PB1.3).
What:
- src/strategy/ic_nifty_v1.py: ROLL_WING signal, _select_wing_roll_target(), apply_action branch
- tests/unit/strategy/test_ic_nifty_v1.py: 5 new tests for ROLL_WING path
Ref: paper-backbone-adj PA1.2
```

---

## Pre-baked Context

**`IronCondorV1`** — `src/strategy/ic_nifty_v1.py`. Current `_ALLOWED_ACTIONS = {"CLOSE_FULL", "CLOSE_CALL_SPREAD", "CLOSE_PUT_SPREAD"}`. `apply_action` raises `ValueError` for anything outside that set. `check_signals` emits `TIME_STOP`, `DTE_WARN`, `DELTA_STOP` (per short leg), `DELTA_WARN`, `PROFIT_TARGET`, `LOSS_STOP`. Delta stop threshold: `_DELTA_STOP = Decimal("0.35")`.

**`OptionChainStrike`** — `src/models/options.py`. Has `.ce: OptionLeg | None` and `.pe: OptionLeg | None`. `OptionLeg.delta` is signed: CE legs have positive delta, PE legs have negative delta. Use `abs(leg.delta)` for threshold comparisons.

**`LegSpec`** — `src/strategy/protocol.py`. Frozen dataclass: `instrument_key: str`, `action: Literal["BUY", "SELL"]`, `quantity: int`, `leg_role: str`, `notes: str = ""`.

**`PaperExecutor.dispatch`** — already iterates `action.legs_to_open`. No executor changes needed.
