"""Per-expiry configuration for IronCondorV1 and paper_ic_entry.

ICExpiryConfig is the single source of truth for all thresholds — both
entry parameters (delta targets, wing width, IVR gate) and exit parameters
(profit target, loss stop, delta stop, time stop).

CONFIGS is the canonical registry. Import it by key — do not construct
ICExpiryConfig instances inline in scripts or tests.

Entry parameter rationale
--------------------------
| Expiry  | Short put Δ | Short call Δ | Wing pts | Reasoning                                               |
|---------|-------------|--------------|----------|---------------------------------------------------------|
| Weekly  | 0.10        | 0.08         | 200      | Thin premium; tighter strikes risk assignment;          |
|         |             |              |          | narrow wing keeps cost:credit ratio acceptable          |
| Monthly | 0.15        | 0.10         | 500      | Council ruling 2026-05-02; asymmetry reflects put skew  |
| Leaps   | 0.15        | 0.10         | 1000     | Same delta as monthly; wider wing for 90-day range      |
| Yearly  | 0.12        | 0.08         | 1500     | Conservative on both sides for 200+ day exposure        |

IVR gate: weekly=0.15 (thin premium makes low-IVR entry less punishing);
monthly/leaps/yearly=0.25.

DTE entry windows (warn if outside; entry script does not block on DTE):
- Weekly: 5–8 (Wednesday entry → next Tuesday ≈ DTE 6)
- Monthly: 30–45
- Leaps: 60–90
- Yearly: 180–270
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
        time_stop_dte=7,
        dte_warn=14,
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
        time_stop_dte=7,
        dte_warn=14,
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
        time_stop_dte=7,
        dte_warn=14,
        profit_target_pct=Decimal("0.50"),
        loss_stop_pct=Decimal("2.0"),
        delta_stop=Decimal("0.35"),
        delta_warn=Decimal("0.25"),
        roll_wing_delta_lo=Decimal("0.10"),
        roll_wing_delta_hi=Decimal("0.20"),
        roll_wing_target_delta=Decimal("0.15"),
    ),
}
