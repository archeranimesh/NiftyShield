# IC-F2 — `ICExpiryConfig` with entry + exit thresholds per expiry type

> **Assigned to: Claude** — new file; pure data model; no logic changes anywhere.

**Prerequisite:** None — independent.

**Files to create/change:**
- `src/strategy/ic_expiry_config.py` — new file
- `src/paper/constants.py` — four new `STRATEGY_IC_*` constants
- `tests/unit/strategy/test_ic_expiry_config.py` — new test file

---

## Context

All IC thresholds (exit rules, entry delta targets, wing widths) are currently hardcoded
in `ic_nifty_v1.py` and `paper_ic_entry.py` as module-level constants calibrated for
monthly only. This story creates the single config object that both files will consume
after IC-F3 and IC-F6 land.

Entry delta targets and wing widths are **research starting points** — they will be
tuned from paper data after 6+ cycles per expiry type. The config design makes
per-field adjustment a one-line edit with no logic changes.

---

## Entry parameter rationale (document in docstring)

| Expiry | Short put Δ | Short call Δ | Wing pts | Reasoning |
|---|---|---|---|---|
| Weekly | 0.10 | 0.08 | 200 | Thin premium; tighter strikes risk assignment; narrow wing keeps cost:credit ratio acceptable |
| Monthly | 0.15 | 0.10 | 500 | Council ruling 2026-05-02; asymmetry reflects put skew |
| Leaps | 0.15 | 0.10 | 1000 | Same delta as monthly; wider wing for 90-day range |
| Yearly | 0.12 | 0.08 | 1500 | Conservative on both sides for 200+ day exposure |

IVR gate thresholds differ for weekly vs longer-dated:
- Weekly: 0.15 (thin premium makes low-IVR entry less punishing)
- Monthly / Leaps / Yearly: 0.25

DTE entry windows (warn if outside; entry script does not block on DTE):
- Weekly: 5–8 (Wednesday entry → next Tuesday ≈ DTE 6)
- Monthly: 30–45
- Leaps: 60–90
- Yearly: 180–270

---

## What to implement

### `src/strategy/ic_expiry_config.py`

```python
"""Per-expiry configuration for IronCondorV1 and paper_ic_entry.

ICExpiryConfig is the single source of truth for all thresholds — both
entry parameters (delta targets, wing width, IVR gate) and exit parameters
(profit target, loss stop, delta stop, time stop).

CONFIGS is the canonical registry. Import it by key — do not construct
ICExpiryConfig instances inline in scripts or tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

ExpiryType = Literal["weekly", "monthly", "leaps", "yearly"]


@dataclass(frozen=True)
class ICExpiryConfig:
    """All thresholds for one IC expiry type.

    Entry parameters
    ----------------
    expiry_bucket : str
        Label passed to get_expiry_candidates() preference list.
        Values: "weekly" | "monthly" | "quarterly" | "yearly".
    short_put_delta : Decimal
        Target absolute delta for the short put leg at entry.
    short_call_delta : Decimal
        Target absolute delta for the short call leg at entry.
    delta_range : Decimal
        ± band around each delta target for strike filtering.
    wing_width_points : int
        Distance in index points from short strike to long hedge strike.
    ivr_gate : Decimal
        Minimum IVR required for entry. Entry blocked below this unless --force-entry.
    dte_warn_lo : int
        Warn (not block) if DTE at entry is below this value.
    dte_warn_hi : int
        Warn (not block) if DTE at entry is above this value.

    Exit parameters
    ---------------
    strategy_name : str
        DB discriminator; must match STRATEGY_IC_* in src/paper/constants.py.
    time_stop_dte : int
        DTE at or below which TIME_STOP ACTION fires.
    dte_warn : int
        DTE at or below which DTE_WARN INFO fires (monitoring, not entry).
    profit_target_pct : Decimal
        Combined mark as fraction of entry credit at which PROFIT_TARGET fires.
    loss_stop_pct : Decimal
        Combined mark as multiple of entry credit at which LOSS_STOP fires.
    delta_stop : Decimal
        |delta| on either short leg at which DELTA_STOP ACTION fires.
    delta_warn : Decimal
        |delta| on either short leg at which DELTA_WARN WARN fires.
    roll_wing_delta_lo : Decimal
        Lower bound of delta range when searching for roll replacement.
    roll_wing_delta_hi : Decimal
        Upper bound of delta range when searching for roll replacement.
    roll_wing_target_delta : Decimal
        Preferred delta for roll replacement strike.
    """

    # Identity
    expiry_type: ExpiryType
    strategy_name: str

    # Entry
    expiry_bucket: str
    short_put_delta: Decimal
    short_call_delta: Decimal
    delta_range: Decimal
    wing_width_points: int
    ivr_gate: Decimal
    dte_warn_lo: int
    dte_warn_hi: int

    # Exit
    time_stop_dte: int
    dte_warn: int
    profit_target_pct: Decimal
    loss_stop_pct: Decimal
    delta_stop: Decimal
    delta_warn: Decimal
    roll_wing_delta_lo: Decimal
    roll_wing_delta_hi: Decimal
    roll_wing_target_delta: Decimal


CONFIGS: dict[str, ICExpiryConfig] = {
    "weekly": ICExpiryConfig(
        expiry_type="weekly",
        strategy_name="paper_ic_nifty_v1_weekly",
        expiry_bucket="weekly",
        short_put_delta=Decimal("0.10"),
        short_call_delta=Decimal("0.08"),
        delta_range=Decimal("0.04"),
        wing_width_points=200,
        ivr_gate=Decimal("0.15"),
        dte_warn_lo=5,
        dte_warn_hi=8,
        time_stop_dte=2,
        dte_warn=4,
        profit_target_pct=Decimal("0.40"),
        loss_stop_pct=Decimal("2.0"),
        delta_stop=Decimal("0.35"),
        delta_warn=Decimal("0.25"),
        roll_wing_delta_lo=Decimal("0.05"),
        roll_wing_delta_hi=Decimal("0.12"),
        roll_wing_target_delta=Decimal("0.08"),
    ),
    "monthly": ICExpiryConfig(
        expiry_type="monthly",
        strategy_name="paper_ic_nifty_v1_monthly",
        expiry_bucket="monthly",
        short_put_delta=Decimal("0.15"),
        short_call_delta=Decimal("0.10"),
        delta_range=Decimal("0.06"),
        wing_width_points=500,
        ivr_gate=Decimal("0.25"),
        dte_warn_lo=30,
        dte_warn_hi=45,
        time_stop_dte=14,
        dte_warn=21,
        profit_target_pct=Decimal("0.50"),
        loss_stop_pct=Decimal("2.0"),
        delta_stop=Decimal("0.35"),
        delta_warn=Decimal("0.25"),
        roll_wing_delta_lo=Decimal("0.10"),
        roll_wing_delta_hi=Decimal("0.20"),
        roll_wing_target_delta=Decimal("0.15"),
    ),
    "leaps": ICExpiryConfig(
        expiry_type="leaps",
        strategy_name="paper_ic_nifty_v1_leaps",
        expiry_bucket="quarterly",
        short_put_delta=Decimal("0.15"),
        short_call_delta=Decimal("0.10"),
        delta_range=Decimal("0.06"),
        wing_width_points=1000,
        ivr_gate=Decimal("0.25"),
        dte_warn_lo=60,
        dte_warn_hi=90,
        time_stop_dte=45,
        dte_warn=60,
        profit_target_pct=Decimal("0.50"),
        loss_stop_pct=Decimal("2.0"),
        delta_stop=Decimal("0.35"),
        delta_warn=Decimal("0.25"),
        roll_wing_delta_lo=Decimal("0.10"),
        roll_wing_delta_hi=Decimal("0.20"),
        roll_wing_target_delta=Decimal("0.15"),
    ),
    "yearly": ICExpiryConfig(
        expiry_type="yearly",
        strategy_name="paper_ic_nifty_v1_yearly",
        expiry_bucket="yearly",
        short_put_delta=Decimal("0.12"),
        short_call_delta=Decimal("0.08"),
        delta_range=Decimal("0.05"),
        wing_width_points=1500,
        ivr_gate=Decimal("0.25"),
        dte_warn_lo=180,
        dte_warn_hi=270,
        time_stop_dte=60,
        dte_warn=90,
        profit_target_pct=Decimal("0.50"),
        loss_stop_pct=Decimal("2.0"),
        delta_stop=Decimal("0.35"),
        delta_warn=Decimal("0.25"),
        roll_wing_delta_lo=Decimal("0.10"),
        roll_wing_delta_hi=Decimal("0.20"),
        roll_wing_target_delta=Decimal("0.15"),
    ),
}
```

### `src/paper/constants.py`

Add after `STRATEGY_IC = "paper_ic_nifty_v1"`:

```python
# Per-expiry IC variants
STRATEGY_IC_WEEKLY  = "paper_ic_nifty_v1_weekly"
STRATEGY_IC_MONTHLY = "paper_ic_nifty_v1_monthly"
STRATEGY_IC_LEAPS   = "paper_ic_nifty_v1_leaps"
STRATEGY_IC_YEARLY  = "paper_ic_nifty_v1_yearly"
```

Keep `STRATEGY_IC` — backward-compatible with IC-E1 commit.

---

## Tests (`tests/unit/strategy/test_ic_expiry_config.py`)

1. `test_configs_has_four_keys` — assert `set(CONFIGS.keys()) == {"weekly","monthly","leaps","yearly"}`.
2. `test_strategy_names_match_constants` — for each config, assert `config.strategy_name == getattr(constants, f"STRATEGY_IC_{config.expiry_type.upper()}")`.
3. `test_time_stop_lt_dte_warn` — assert `config.time_stop_dte < config.dte_warn` for all four (structural invariant).
4. `test_dte_warn_lo_lt_dte_warn_hi` — assert `config.dte_warn_lo < config.dte_warn_hi` for all four.
5. `test_all_decimal_fields_are_decimal` — assert `isinstance(f, Decimal)` for every `Decimal`-typed field across all four configs.
6. `test_frozen_raises_on_assignment` — assert `pytest.raises((FrozenInstanceError, AttributeError))` when setting any field on a config instance.

---

## Commit

```
feat(strategy): ICExpiryConfig with entry + exit thresholds; STRATEGY_IC_* constants

Why: All IC thresholds hardcoded for monthly only; multi-expiry research
needs per-type calibrated config as single source of truth.
What:
- src/strategy/ic_expiry_config.py: ICExpiryConfig dataclass + CONFIGS presets
- src/paper/constants.py: STRATEGY_IC_WEEKLY/MONTHLY/LEAPS/YEARLY
- tests/unit/strategy/test_ic_expiry_config.py: 6 structural invariant tests
Ref: ic-full IC-F2
```

---

## Pre-baked Context

**`src/paper/constants.py`** STRATEGY block ends at line ~29 with `STRATEGY_IC = "paper_ic_nifty_v1"`. Add four new constants immediately after.

**`FrozenInstanceError`** — `from dataclasses import FrozenInstanceError` (Python 3.11+). Use `pytest.raises((FrozenInstanceError, AttributeError))` to cover Python 3.10.

**`src/strategy/__init__.py`** — exists (one comment line). No changes needed.
