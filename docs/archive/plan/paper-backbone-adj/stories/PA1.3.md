# PA1.3 — `src/strategy/nifty_track_comparison_v1.py`: overlay roll ACTION signals + apply_action + tests
> **Assigned to: Claude** — requires reading 3-track strategy spec + absorbing paper_3track_overlay_roll.py logic.

**Files to change:**
- `src/strategy/nifty_track_comparison_v1.py` — upgrade `ROLL_DUE_DTE`/`ROLL_DUE_DECAY` to ACTION, add `_select_overlay_roll_target()`, implement `apply_action` (ROLL_OVERLAY + ROLL_COLLAR)
- `tests/unit/strategy/test_nifty_track_comparison_v1.py` — extend with ACTION signal + apply_action tests

**Before implementing:** Read `docs/strategies/nifty_track_comparison_v1.md` — overlay menu, blocked combinations, leg roles. Also read `scripts/strategies/three_track/paper_3track_overlay_roll.py` for the strike selection and collar atomicity logic being absorbed.

**Prerequisite:** PA0 (`src/strategy/roll_utils.py`) must be committed before this story.

**Multi-expiry requirement (council 2026-06-02):** Overlay roll targets are on the **next expiry**, not the current one. `_select_overlay_roll_target` cannot use the chain already passed to `check_signals` (which is the current expiry). The strategy must fetch the next-expiry chain via a second `get_option_chain()` call inside `check_signals` when constructing an ACTION event. Pass the broker client to `NiftyTrackComparisonV1.__init__` for this purpose.

---

## Context: what currently exists

`NiftyTrackComparisonV1.check_signals` emits only WARN severity events (`ROLL_DUE_DTE`, `ROLL_DUE_DECAY`, `OVERLAY_EXPIRED`). `apply_action` raises `NotImplementedError` — this strategy was intentionally left as WARN-only in PB4.1.

Overlay leg roles handled: `overlay_pp`, `overlay_cc`, `overlay_collar_put`, `overlay_collar_call`.

Blocked combination (hard rule — never open): `paper_nifty_futures` + standalone `overlay_cc`.

---

## What to implement

### 1. Upgrade ROLL_DUE_DTE and ROLL_DUE_DECAY to ACTION severity

Change the severity of `ROLL_DUE_DTE` (DTE ≤ 5) and `ROLL_DUE_DECAY` (remaining premium ≤ 25%) from `"WARN"` to `"ACTION"` when `_select_overlay_roll_target()` returns a valid replacement. If no replacement is available, keep them as `"WARN"` — the council cannot approve a roll without a suggested target.

`OVERLAY_EXPIRED` stays WARN (already past expiry — no point in a council flow).

Upgrade the payload for these signals to include roll target fields alongside the existing fields:
```python
{
    # existing fields
    "leg_role": str,
    "dte": int,
    "strategy_name": str,
    # new fields (when ACTION)
    "suggested_instrument_key": str,
    "suggested_strike": str,
    "suggested_expiry": str,
    "suggested_delta": str,
    "suggested_mid_price": str,
}
```

### 2. `_select_overlay_roll_target(market: OptionChain, leg_role: str, strategy_name: str) -> LegSpec | None`

Absorb from `paper_3track_overlay_roll.py`. Target selection by leg role:

| leg_role | Option type | Delta target | Action |
|---|---|---|---|
| `overlay_pp` | PE | closest to 0.20 (8–10% OTM put) | BUY |
| `overlay_cc` | CE | closest to 0.20 (3–5% OTM call) | SELL |
| `overlay_collar_put` | PE | closest to 0.20 | BUY |
| `overlay_collar_call` | CE | closest to 0.20 | SELL |

**Blocked check:** if `strategy_name == "paper_nifty_futures"` and `leg_role == "overlay_cc"` → return `None` (blocked combination — no standalone CC on futures).

Uses the **next-expiry chain** fetched via broker client (see multi-expiry prerequisite above). Use `roll_utils.find_strike_by_delta(next_chain, option_type, delta_range, target_delta)` — do not re-implement delta filtering inline. Return `None` when no suitable strike found, chain data insufficient, or broker fetch fails.

### 3. `apply_action` — implement ROLL_OVERLAY and ROLL_COLLAR

Replace `NotImplementedError` with:

```python
_ALLOWED_ACTIONS = {"ROLL_OVERLAY", "ROLL_COLLAR"}

async def apply_action(self, positions, action):
    if action.action_type not in _ALLOWED_ACTIONS:
        raise ValueError(
            f"NiftyTrackComparisonV1 does not permit {action.action_type!r} — "
            f"allowed: {_ALLOWED_ACTIONS}"
        )
    if not action.legs_to_open:
        raise ValueError(f"{action.action_type} requires at least one leg in legs_to_open")
    closed: set[str] = set(action.legs_to_close)
    return [p for p in positions if p.leg_role not in closed]
```

**ROLL_OVERLAY**: single leg close + open (PP roll, CC roll). `legs_to_close` has 1 entry, `legs_to_open` has 1 `LegSpec`.

**ROLL_COLLAR**: atomic close + open of both collar legs. `legs_to_close` has 2 entries (`overlay_collar_put` + `overlay_collar_call`), `legs_to_open` has 2 `LegSpec` entries. The executor already handles multi-leg `legs_to_open` in sequence — no special atomic logic needed here; the executor's write sequence is close-then-open per the existing implementation.

The executor handles all DB writes. `apply_action` only does optimistic in-memory position update.

---

## Tests (`tests/unit/strategy/test_nifty_track_comparison_v1.py`)

**New happy-path tests:**
- Overlay leg with DTE=4 and chain has valid replacement → `ROLL_DUE_DTE` fires as ACTION (not WARN)
- Overlay leg with DTE=4 but no replacement in chain → `ROLL_DUE_DTE` fires as WARN
- Overlay leg with mark=20% of entry and chain has replacement → `ROLL_DUE_DECAY` fires as ACTION
- `apply_action` with `ROLL_OVERLAY` + one `LegSpec` → closed leg removed from positions, no error
- `apply_action` with `ROLL_COLLAR` + two `LegSpec` entries → both collar legs removed, no error

**New edge/error tests:**
- `paper_nifty_futures` strategy + `overlay_cc` leg → `_select_overlay_roll_target` returns `None` → signal stays WARN
- `apply_action` with `ROLL_OVERLAY` + empty `legs_to_open` → raises `ValueError`
- `apply_action` with unknown `action_type` `"CLOSE_FULL"` → raises `ValueError`

**Existing tests must still pass:** `OVERLAY_EXPIRED` still WARN, no regression on existing WARN signal tests.

---

## Commit

```
feat(strategy): add NiftyTrackComparisonV1 overlay roll ACTION signals

Why: 3-track overlay rolls were WARN-only and had no apply_action;
backbone can now drive overlay rolls with council approval.
What:
- src/strategy/nifty_track_comparison_v1.py: ROLL_DUE_DTE/DECAY upgraded
  to ACTION when target available; _select_overlay_roll_target(); apply_action
  ROLL_OVERLAY + ROLL_COLLAR branches
- tests/unit/strategy/test_nifty_track_comparison_v1.py: 8 new tests
Ref: paper-backbone-adj PA1.3
```

---

## Pre-baked Context

**`NiftyTrackComparisonV1`** — `src/strategy/nifty_track_comparison_v1.py`. Currently WARN-only. `apply_action` raises `NotImplementedError`. Overlay leg roles: `overlay_pp`, `overlay_cc`, `overlay_collar_put`, `overlay_collar_call`. Roll DTE threshold: `_ROLL_DTE = 5`. Decay threshold: `_DECAY_WARN_PCT = Decimal("0.25")`.

**Blocked combination** — `paper_nifty_futures` + `overlay_cc`: hard rule, never open. Documented in `DECISIONS.md` and strategy spec. `_select_overlay_roll_target` must enforce this by returning `None`.

**`PaperPosition.strategy_name`** — available on the position object passed to `check_signals`. Use it in `_select_overlay_roll_target` to enforce the futures+CC block.

**`OptionChain`** — `src/models/options.py`. `strikes: dict[Decimal, OptionChainStrike]`. Each strike has `.ce` and `.pe` (`OptionLeg | None`). `OptionLeg` fields: `ltp`, `delta`, `iv`, `strike`, `instrument_key`.

**`LegSpec`** — `src/strategy/protocol.py`. Fields: `instrument_key: str`, `action: Literal["BUY", "SELL"]`, `quantity: int`, `leg_role: str`, `notes: str = ""`.

**Executor handles multi-leg `legs_to_open`** — `src/strategy/executor.py` iterates `action.legs_to_open` in sequence. For collar (2 legs), it closes both then opens both. No special handling needed in `apply_action`.

**`paper_3track_overlay_roll.py` reference** — `_find_expiring_overlay` tracks `last_trade` regardless of direction (Phase B lesson: open SELL positions need last_trade direction for correct net_qty detection). This is store logic — no impact on strategy layer. The strategy only needs to select the replacement target from the chain.
