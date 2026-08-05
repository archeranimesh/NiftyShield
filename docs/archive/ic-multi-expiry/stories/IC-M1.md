# IC-M1 — `ICExpiryConfig` dataclass + `CONFIGS` presets + strategy name constants

> **Assigned to: Claude** — new file; pure data model, no logic changes to existing code.

**Files to create/change:**
- `src/strategy/ic_expiry_config.py` — new file: `ICExpiryConfig` dataclass + `CONFIGS` dict
- `src/paper/constants.py` — add four new `STRATEGY_IC_*` constants
- `src/strategy/__init__.py` — no change needed (existing package)
- `tests/unit/strategy/test_ic_expiry_config.py` — new test file

---

## Context

`IronCondorV1` currently hardcodes all exit thresholds as module-level constants:

```python
_PROFIT_TARGET_PCT = Decimal("0.50")
_LOSS_STOP_PCT     = Decimal("2.0")
_DELTA_STOP        = Decimal("0.35")
_DELTA_WARN        = Decimal("0.25")
_TIME_STOP_DTE     = 14
_DTE_WARN          = 21
```

These values are calibrated for a monthly IC (DTE 30–45 at entry). Weekly IC has a
completely different theta profile — time stop at DTE 14 would trigger on entry day.
Leaps and yearly ICs need substantially wider time buffers.

This story creates the config model only. `IronCondorV1` is not touched here —
that is IC-M2 (Antigravity, depends on this story + IC-E3).

---

## What to implement

### 1. `src/strategy/ic_expiry_config.py`

```python
"""Per-expiry configuration for IronCondorV1.

Each ICExpiryConfig instance encodes the threshold set for one expiry type.
IronCondorV1 accepts one at construction time; all threshold references inside
the class use config fields rather than module-level constants.

CONFIGS is the canonical source of presets. Import and use it — do not
construct ICExpiryConfig instances inline in scripts or tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

ExpiryType = Literal["weekly", "monthly", "leaps", "yearly"]


@dataclass(frozen=True)
class ICExpiryConfig:
    """Threshold set for one IC expiry type.

    Attributes:
        expiry_type: One of weekly / monthly / leaps / yearly.
        strategy_name: DB discriminator; must match STRATEGY_IC_* constants.
        expiry_bucket: Label passed to get_expiry_candidates() preference list.
        time_stop_dte: DTE at or below which TIME_STOP ACTION fires.
        dte_warn: DTE at or below which DTE_WARN INFO fires.
        profit_target_pct: Combined mark as fraction of entry credit at which
            PROFIT_TARGET fires (e.g. 0.50 = exit when 50% of credit remains).
        loss_stop_pct: Combined mark as multiple of entry credit at which
            LOSS_STOP fires (e.g. 2.0 = exit when position costs 2× entry credit).
        delta_stop: |delta| threshold on either short leg for DELTA_STOP ACTION.
        delta_warn: |delta| threshold on either short leg for DELTA_WARN WARN.
        roll_wing_delta_lo: Lower bound of delta range for wing roll target.
        roll_wing_delta_hi: Upper bound of delta range for wing roll target.
        roll_wing_target_delta: Preferred delta for wing roll replacement strike.
    """

    expiry_type: ExpiryType
    strategy_name: str
    expiry_bucket: str
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
        time_stop_dte=2,
        dte_warn=4,
        profit_target_pct=Decimal("0.40"),   # weekly: tighter — bid-ask drag is proportionally larger
        loss_stop_pct=Decimal("2.0"),
        delta_stop=Decimal("0.35"),
        delta_warn=Decimal("0.25"),
        roll_wing_delta_lo=Decimal("0.10"),
        roll_wing_delta_hi=Decimal("0.20"),
        roll_wing_target_delta=Decimal("0.15"),
    ),
    "monthly": ICExpiryConfig(
        expiry_type="monthly",
        strategy_name="paper_ic_nifty_v1_monthly",
        expiry_bucket="monthly",
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

### 2. `src/paper/constants.py`

Add after the existing `STRATEGY_IC` line:

```python
# Per-expiry IC variants (parameterised IronCondorV1)
STRATEGY_IC_WEEKLY  = "paper_ic_nifty_v1_weekly"
STRATEGY_IC_MONTHLY = "paper_ic_nifty_v1_monthly"
STRATEGY_IC_LEAPS   = "paper_ic_nifty_v1_leaps"
STRATEGY_IC_YEARLY  = "paper_ic_nifty_v1_yearly"
```

Keep `STRATEGY_IC = "paper_ic_nifty_v1"` — it remains valid for the legacy
single-expiry registration (ic-e2e IC-E1 added it; do not remove).

---

## Tests (`tests/unit/strategy/test_ic_expiry_config.py`)

**Happy-path tests:**
1. `CONFIGS` has exactly four keys: `{"weekly", "monthly", "leaps", "yearly"}`.
2. Each config's `strategy_name` matches the corresponding `STRATEGY_IC_*` constant in `src.paper.constants`.
3. `time_stop_dte < dte_warn` holds for all four configs (time stop always fires before the warn DTE would flip to INFO — this is a structural invariant).
4. All `Decimal` fields are `Decimal` instances, not `float` (type safety check).
5. `ICExpiryConfig` is frozen — attempting `config.time_stop_dte = 99` raises `FrozenInstanceError`.

**Edge/error tests:**
6. Constructing `ICExpiryConfig` with `profit_target_pct` as a plain `float` (e.g. `0.5`) stores it without error — document that callers must pass `Decimal`; the dataclass does not coerce. Assert `type(config.profit_target_pct) == float` in this case (this is the failure mode, not the desired state — the test documents the footgun, so the docstring warning is justified).

---

## Commit

```
feat(strategy): add ICExpiryConfig + per-expiry IC strategy name constants

Why: IronCondorV1 hardcodes monthly thresholds; multi-expiry paper research
requires independently calibrated configs per expiry type.
What:
- src/strategy/ic_expiry_config.py: ICExpiryConfig frozen dataclass + CONFIGS presets
- src/paper/constants.py: STRATEGY_IC_WEEKLY/MONTHLY/LEAPS/YEARLY constants
- tests/unit/strategy/test_ic_expiry_config.py: 6 tests
Ref: ic-multi-expiry IC-M1
```

---

## Pre-baked Context

**`src/paper/constants.py`** — existing strategy name block (lines 22–29):
```python
STRATEGY_SPOT = "paper_nifty_spot"
STRATEGY_FUTURES = "paper_nifty_futures"
STRATEGY_PROXY = "paper_nifty_proxy"
STRATEGY_CSP = "paper_csp_nifty_v1"
STRATEGY_CC_OVERLAY = "paper_covered_call_v1"
STRATEGY_PP_OVERLAY = "paper_protective_put_v1"
STRATEGY_COLLAR_OVERLAY = "paper_collar_v1"
STRATEGY_IC = "paper_ic_nifty_v1"
```
Add the four new constants immediately after `STRATEGY_IC`.

**`src/strategy/` package** — `__init__.py` exists (one comment line). No changes needed.

**Existing hardcoded thresholds in `src/strategy/ic_nifty_v1.py`** (lines 54–59):
```python
_PROFIT_TARGET_PCT = Decimal("0.50")
_LOSS_STOP_PCT     = Decimal("2.0")
_DELTA_STOP        = Decimal("0.35")
_DELTA_WARN        = Decimal("0.25")
_TIME_STOP_DTE     = 14
_DTE_WARN          = 21
```
Do NOT touch these in this story — IC-M2 migrates them.

**`dataclasses.FrozenInstanceError`** — raised on any attribute assignment to a `frozen=True`
dataclass instance. Import path: `from dataclasses import FrozenInstanceError` (Python 3.11+)
or catch as `AttributeError` on 3.10. Use `pytest.raises((FrozenInstanceError, AttributeError))`
to cover both minor versions.

---

## 2026-08-05 Correction — Entry-DTE Scaling Superseded

The `time_stop_dte`/`dte_warn` scaling this story introduced (weekly 2/4, monthly 14/21,
leaps 45/60, yearly 60/90) was rejected by council ruling
`docs/council/2026-08-05_ic-time-stop-dte-tiering.md`: no empirical or theoretical basis
existed for entry-DTE-proportional buffers beyond linear intuition. Current values live in
`ic_expiry_config.py` — see `DECISIONS.md` 2026-08-05 for the full account. This file is kept
as the historical record of the original (superseded) design, not the current spec.
