# PA1.1 — `src/strategy/csp_nifty_v1.py`: CSP ROLL signal + strike selection + apply_action ROLL branch
> **Assigned to: Claude** — requires reading strategy spec + absorbing paper_csp_roll.py logic.

**Files to change:**
- `src/strategy/csp_nifty_v1.py` — add `ROLL` signal emission, `_select_roll_target()` helper, ROLL branch in `apply_action`
- `tests/unit/strategy/test_csp_nifty_v1.py` — extend with ROLL signal + apply_action ROLL tests

**Before implementing:** Read `docs/strategies/csp_nifty_v1.md` for roll target rules.
Also read `scripts/strategies/csp/paper_csp_roll.py` — the strike selection logic (`_open_new_csp_leg`) moves here.

**Prerequisite:** PA0 (`src/strategy/roll_utils.py`) must be committed before this story.

---

## What to implement

### 1. New signal: `ROLL` (ACTION severity)

`check_signals` should emit a `ROLL` ACTION event when **any** of these trigger:
- DTE ≤ 21 (`TIME_STOP` condition — same threshold, different event when a replacement strike is available)
- |delta| ≥ 0.35 (`DELTA_STOP` condition — same threshold)
- Mark ≤ 50% of entry credit (`PROFIT_TARGET` condition)

The existing individual signals (`TIME_STOP`, `DELTA_STOP`, `PROFIT_TARGET`, `LOSS_STOP`) still fire unchanged. `ROLL` is emitted **in addition** when the chain has enough data to select a replacement strike. If `_select_roll_target()` returns `None` (chain data unavailable), skip the ROLL event — the existing close-only signals still fire.

`ROLL` payload:
```python
{
    "leg_role": str,                  # e.g. "short_put"
    "current_instrument_key": str,
    "current_dte": int,
    "suggested_instrument_key": str,  # selected by _select_roll_target()
    "suggested_strike": str,          # Decimal as string
    "suggested_expiry": str,          # ISO date string
    "suggested_delta": str,           # Decimal as string — delta of the suggested leg
    "suggested_mid_price": str,       # Decimal as string — LTP of suggested leg
}
```

### 2. `_select_roll_target(market: OptionChain, expiry_preference: list[str]) -> LegSpec | None`

Absorb the core logic from `scripts/strategies/csp/paper_csp_roll.py → _open_new_csp_leg`.

Target: closest available PE strike to **22-delta** (|delta| between 0.18–0.28, ranked by proximity to 0.22) on the next monthly expiry. Use `InstrumentLookup.get_expiry_candidates()` to find the expiry — pass `preference=["monthly", "quarterly"]`.

Return a `LegSpec` with:
- `instrument_key`: the selected PE key
- `action`: `"SELL"`
- `quantity`: 1 (caller scales if needed)
- `leg_role`: `"short_put"`
- `notes`: `"roll_target delta={delta}"`

Return `None` when no suitable strike is found or chain data is insufficient.

**Important:** `_select_roll_target` must NOT make async network calls. It works purely from the `OptionChain` already passed to `check_signals` — same chain object, no additional fetches. Use `roll_utils.find_strike_by_delta(chain, "PE", (Decimal("0.18"), Decimal("0.28")), Decimal("0.22"))` — do not re-implement the filtering logic inline.

### 3. `apply_action` ROLL branch

Current code raises `ValueError` for non-`CLOSE_FULL` actions. Add:

```python
elif action.action_type == "ROLL":
    if not action.legs_to_open:
        raise ValueError("ROLL action requires at least one leg in legs_to_open")
    closed: set[str] = set(action.legs_to_close)
    return [p for p in positions if p.leg_role not in closed]
```

The executor (`PaperExecutor.dispatch`) already handles the actual DB writes for both close and open. `apply_action` only does the optimistic in-memory position update.

---

## Tests (`tests/unit/strategy/test_csp_nifty_v1.py`)

**New happy-path tests:**
- Short put with DTE=20 and chain has a valid 22-delta replacement → `ROLL` ACTION event fires alongside `TIME_STOP`
- Short put with |delta|=0.36 and chain has replacement → `ROLL` fires alongside `DELTA_STOP`
- Short put with mark=48% of entry and chain has replacement → `ROLL` fires alongside `PROFIT_TARGET`
- `apply_action` with `ROLL` + one `LegSpec` in `legs_to_open` → no error, closed leg removed from positions

**New edge/error tests:**
- Short put with DTE=20 but chain has no PE legs with delta in range → `ROLL` does NOT fire (only `TIME_STOP` fires)
- `apply_action` with `ROLL` + empty `legs_to_open` → raises `ValueError`
- `apply_action` with unknown action type `"ADJUST"` → raises `ValueError` (existing test, ensure still passes)

---

## Commit

```
feat(strategy): add CSPNiftyV1 ROLL signal with strike selection

Why: Backbone previously only emitted CLOSE_FULL signals; ROLL unblocks
full adjustment mode — executor already handles legs_to_open (PB1.3).
What:
- src/strategy/csp_nifty_v1.py: ROLL signal, _select_roll_target(), apply_action ROLL branch
- tests/unit/strategy/test_csp_nifty_v1.py: 6 new tests for ROLL path
Ref: paper-backbone-adj PA1.1
```

---

## Pre-baked Context

**`CSPNiftyV1`** — `src/strategy/csp_nifty_v1.py`. Current `apply_action` raises `ValueError` for anything other than `CLOSE_FULL`. `check_signals` emits `TIME_STOP`, `DELTA_STOP`, `PROFIT_TARGET`, `LOSS_STOP`, `ROLL_DUE_DTE`, `ROLL_DUE_DECAY`, `DELTA_WARN`. All thresholds defined as module-level `Decimal` constants.

**`LegSpec`** — `src/strategy/protocol.py`. Frozen dataclass.
Fields: `instrument_key: str`, `action: Literal["BUY", "SELL"]`, `quantity: int`, `leg_role: str`, `notes: str = ""`.

**`ApprovedAction`** — `src/strategy/protocol.py`. Frozen dataclass.
Fields: `action_type: str`, `legs_to_close: list[str]`, `legs_to_open: list[LegSpec]`, `rationale: str`, `council_rank: int`.

**`OptionChain`** — `src/models/options.py`. Fields: `underlying_spot: Decimal`, `expiry: date`, `strikes: dict[Decimal, OptionChainStrike]`. Each `OptionChainStrike` has `.pe: OptionLeg | None` and `.ce: OptionLeg | None`. `OptionLeg` fields: `ltp: Decimal`, `delta: Decimal`, `iv: Decimal`, `strike: Decimal`, `instrument_key: str`.

**`PaperExecutor.dispatch`** — `src/strategy/executor.py`. Already iterates `action.legs_to_open` and calls `store.record_trade()` for each `LegSpec`. No changes needed to executor.

**`roll_utils`** — `src/strategy/roll_utils.py` (PA0). Import: `from src.strategy.roll_utils import find_strike_by_delta`. Call: `find_strike_by_delta(chain, "PE", (Decimal("0.18"), Decimal("0.28")), Decimal("0.22"))`. Do not import from `scripts.lookup.find_strike_by_delta` — that is the standalone script path being retired.
