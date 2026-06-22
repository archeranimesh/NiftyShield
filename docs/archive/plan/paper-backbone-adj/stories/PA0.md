# PA0 — `src/strategy/roll_utils.py`: shared strike selection utility + tests
> **Assigned to: Claude** — prerequisite for all three strategy roll stories (PA1.1, PA1.2, PA1.3).

**Files to change:**
- `src/strategy/roll_utils.py` — new file: `find_strike_by_delta()`
- `src/strategy/__init__.py` — no change needed (existing file)
- `tests/unit/strategy/test_roll_utils.py` — new test file

**Council mandate:** `docs/council/2026-06-02_strategy-monitor-watchlist-design.md` — Implementation Guidance.
All strategy `_select_*_roll_target()` helpers in PA1.1–PA1.3 must call this function.
Do not duplicate delta-range filtering logic across strategy files.

---

## What to implement

```python
# src/strategy/roll_utils.py

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from src.models.options import OptionChain, OptionLeg


def find_strike_by_delta(
    chain: OptionChain,
    option_type: Literal["CE", "PE"],
    delta_range: tuple[Decimal, Decimal],
    target_delta: Decimal,
) -> OptionLeg | None:
    """Filter chain strikes by absolute delta band and return the leg closest to target.

    Scans all strikes in the chain for the given option type, filters to those whose
    absolute delta falls within [delta_range[0], delta_range[1]], then returns the
    leg whose absolute delta is closest to target_delta. Returns None when no
    candidates exist or the chain has no strikes.

    Args:
        chain: Current Nifty 50 option chain snapshot.
        option_type: "CE" for call legs, "PE" for put legs.
        delta_range: Inclusive (min, max) absolute delta filter band.
                     E.g. (Decimal("0.18"), Decimal("0.28")) for CSP target zone.
        target_delta: Ideal absolute delta to rank candidates against.
                      E.g. Decimal("0.22") for CSP 22-delta target.

    Returns:
        OptionLeg with absolute delta closest to target_delta within the band,
        or None when no candidates found.
    """
```

**Implementation notes:**
- Use `abs(leg.delta)` for all comparisons — delta on PE legs is negative in the chain.
- Only include legs with `ltp > Decimal("0")` — zero LTP means illiquid / no market.
- `delta_range` is inclusive on both ends.
- When two candidates are equidistant from `target_delta`, prefer the one with higher OI if available; otherwise return the first (lower strike for PE, higher strike for CE).
- This function is pure — no I/O, no async, no side effects.

---

## Tests (`tests/unit/strategy/test_roll_utils.py`)

Build a minimal `OptionChain` fixture with 5–6 strikes covering the target band and outside it.

**Happy-path tests:**
- PE chain with 3 strikes in band → returns leg closest to target delta
- CE chain with 3 strikes in band → returns leg closest to target delta
- Single strike exactly at target delta → returns it
- Two equidistant candidates → returns one deterministically (document which)

**Edge/error tests:**
- No strikes with ltp > 0 in band → returns None
- Empty chain (no strikes) → returns None
- All strikes outside delta range → returns None
- delta_range min == max (exact match only) → returns matching leg or None

---

## Commit

```
feat(strategy): add roll_utils.find_strike_by_delta shared helper

Why: All three adjustment stories (PA1.1–PA1.3) need delta-band strike
selection; council mandated a single shared utility to avoid duplication.
What:
- src/strategy/roll_utils.py: find_strike_by_delta()
- tests/unit/strategy/test_roll_utils.py: 8 tests
Ref: paper-backbone-adj PA0; council 2026-06-02
```

---

## Pre-baked Context

**`OptionChain`** — `src/models/options.py`. Fields: `underlying_spot: Decimal`, `expiry: date`, `strikes: dict[Decimal, OptionChainStrike]`. Key is the strike price as `Decimal`.

**`OptionChainStrike`** — `src/models/options.py`. Fields: `.ce: OptionLeg | None`, `.pe: OptionLeg | None`.

**`OptionLeg`** — `src/models/options.py`. Fields: `ltp: Decimal`, `delta: Decimal`, `iv: Decimal`, `strike: Decimal`, `instrument_key: str`. Delta is signed: CE legs positive, PE legs negative. Use `abs(leg.delta)` for range checks.
