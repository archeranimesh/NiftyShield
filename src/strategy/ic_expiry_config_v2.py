"""Delta-based per-expiry configuration for IronCondorV2.

IronCondorV2ExpiryConfig replaces V1's fixed wing_width_points with
10Δ long-wing placement and adds adjustment/exit thresholds sourced
from the core-design council ruling.

Council ruling: docs/archive/council/strategy/2026-06-26_ic-v2-core-design.md
Stage 3 — Decisions D1 / D2 / D3 / D4.

V2 differences from V1
-----------------------
| Dimension          | V1 (ICExpiryConfig)              | V2 (this file)                     |
|--------------------|----------------------------------|------------------------------------|
| Entry deltas       | 15Δ put / 10Δ call               | 25Δ put / 22Δ call (D1)            |
| Wing construction  | wing_width_points (fixed points) | 10Δ placement + premium/liq floors |
| Adjustment         | ROLL_WING only                   | Full partial vertical roll (D3)    |
| Roll accounting    | Single leg                       | 4-leg atomic, max 1 per side (D3)  |
| DTE hard close     | None                             | DTE≤7 CLOSE_FULL monthly (D4)      |
| Debit guards       | None                             | ≤ 50% of original IC credit (D3)   |

Only the monthly preset is implemented in Phase 1.  Weekly, leaps, and yearly
presets will be added in a later story after backtesting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class ProfitLockConfig:
    """Profit-lock thresholds for IronCondorV2.

    Council ruling: docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md Stage 3.

    Three zones:
      Zone 1 (25% captured): log-only, no structural change.
      Zone 2 (50% captured): roll long wings inward — structural guarantee required.
      Zone 3 (75% captured): CLOSE_FULL — formula too tight for Nifty execution.

    Floor guarantee formula (Zone 2, enforced before execution):
      max(W_put, W_call) + D_cum + D_lock + K <= 0.75 * C0

    If formula cannot be satisfied: CLOSE_FULL (no exceptions).
    """

    # Zone trigger thresholds (fraction of entry credit captured)
    zone1_trigger: Decimal = Decimal("0.25")
    zone2_trigger: Decimal = Decimal("0.50")
    zone3_trigger: Decimal = Decimal("0.75")

    # Zone 2 — wing inward roll config
    zone2_long_wing_delta_target: Decimal = Decimal("0.19")  # target delta for inward wings
    zone2_long_wing_delta_lo: Decimal = Decimal("0.16")  # acceptable range lo
    zone2_long_wing_delta_hi: Decimal = Decimal("0.22")  # acceptable range hi
    zone2_long_wing_min_premium: Decimal = Decimal("15")  # ₹ min mid-price on new longs

    # Floor formula constants
    floor_budget_zone2: Decimal = Decimal("0.75")  # (1 - F) where F=0.25
    cost_buffer_pts: Decimal = Decimal("10")  # K: conservative slippage + STT buffer (points)
    max_debit_fraction: Decimal = Decimal("0.25")  # D_lock <= 25% of C0

    # Minimum restructured width to bother (below this → CLOSE_FULL is cleaner)
    min_viable_width_pts: int = 100  # 100-point minimum on Nifty grid

    # DTE guards (monthly)
    monthly_lock_dte_lo: int = 10  # do not restructure below this DTE
    monthly_lock_dte_hi: int = 22  # prefer restructure window; above this restructure only if cheap

    # IV/VIX guards (secondary — mathematical formula is primary)
    min_vix: Decimal = Decimal("11")
    min_ivr: Decimal = Decimal("0.20")


@dataclass(frozen=True)
class IronCondorV2ExpiryConfig:
    """Delta-based config for IronCondorV2.

    Replaces V1's fixed wing_width_points with 10Δ long-wing placement.
    Council ruling: docs/archive/council/strategy/2026-06-26_ic-v2-core-design.md Stage 3.

    Field groups
    ------------
    Entry — short leg deltas (D1 ruling)
        short_put_delta_target : Decimal
            Target absolute delta for the short put leg at entry.
        short_call_delta_target : Decimal
            Target absolute delta for the short call leg at entry.
            Set 3Δ below put to reflect Nifty put-skew (D1 ruling).
        delta_range : Decimal
            ± tolerance band around each delta target for strike filtering.

    Wing sizing — long leg deltas (D2 ruling)
        long_wing_delta_target : Decimal
            Target absolute delta for both long-wing legs.
        long_wing_delta_floor : Decimal
            Absolute minimum delta for long wing; entry skipped if not met.
        long_wing_min_premium : Decimal
            Minimum mid-price (₹) for long wing; entry skipped if not met.

    SD sanity guard (D2) — warn thresholds, never hard blocks
        sd_width_warn_upper_multiplier : Decimal
            Warn if actual wing width > this multiple of sd_width.
        sd_width_warn_lower_multiplier : Decimal
            Warn if actual wing width < this multiple of sd_width.
        sd_atm_iv_multiplier : Decimal
            Multiplier k in: sd_width = spot × ATM_IV × sqrt(DTE / 365) × k.

    Adjustment (D3 ruling)
        roll_trigger_delta : Decimal
            |short_delta| ≥ this → ROLL_WING (attempt partial roll).
        roll_warn_delta : Decimal
            |short_delta| ≥ this → DELTA_WARN (log only).
        forced_close_delta : Decimal
            |short_delta| ≥ this → FORCED_CLOSE (skip roll guards).
        roll_debit_cap_fraction : Decimal
            Roll debit must be ≤ this fraction of original IC credit.
        max_rolls_per_side_per_cycle : int
            Maximum number of partial rolls on any one side per entry cycle.

    DTE-tiered exit (D4 ruling)
        monthly_close_full_dte : int
            DTE ≤ this value → CLOSE_FULL default for monthly expiry.
            Hard force-close at DTE ≤ 1 is unconditional (see ic_nifty_v2.py).
            Naming note: when weekly config lands (close_full_dte=3 per D4), rename
            to expiry-agnostic ``close_full_dte`` or keep per-expiry fields with
            dispatch on ``expiry_type``. See TODOS.md entry 2026-06-27.

    Omitted fields (Phase 1)
    ------------------------
    profit_target_fraction : deferred to Phase 2 (profit-lock engine story IC-V2-8).
        V1's ICExpiryConfig carries this; V2 replaces it with the three-zone
        profit-lock mechanism (ProfitLockConfig). Not an oversight.
    """

    # Phase 1: monthly only. Expand to Literal["monthly", "weekly", "leaps", "yearly"]
    # as each preset is added.  Keeps mypy honest on cfg.expiry_type dispatch.
    expiry_type: Literal["monthly"]

    @property
    def strategy_name(self) -> str:
        return f"paper_ic_nifty_v2_{self.expiry_type}"

    # Entry — short leg deltas (D1 ruling)
    short_put_delta_target: Decimal = Decimal("0.25")
    short_call_delta_target: Decimal = Decimal("0.22")
    delta_range: Decimal = Decimal("0.03")  # ±tolerance for strike selection

    # Wing sizing — long leg deltas (D2 ruling)
    long_wing_delta_target: Decimal = Decimal("0.10")
    long_wing_delta_floor: Decimal = Decimal("0.05")  # absolute minimum; skip entry if not met
    long_wing_min_premium: Decimal = Decimal("15")  # ₹ per unit

    # SD sanity guard (D2) — warn thresholds, not hard blocks
    sd_width_warn_upper_multiplier: Decimal = Decimal("1.5")
    sd_width_warn_lower_multiplier: Decimal = Decimal("0.4")
    sd_atm_iv_multiplier: Decimal = Decimal("1.25")  # k in sd_width formula

    # Adjustment (D3)
    roll_trigger_delta: Decimal = Decimal("0.35")  # |short_delta| ≥ this → ROLL_WING
    roll_warn_delta: Decimal = Decimal("0.30")  # |short_delta| ≥ this → DELTA_WARN
    forced_close_delta: Decimal = Decimal("0.45")  # |short_delta| ≥ this → FORCED_CLOSE
    roll_debit_cap_fraction: Decimal = Decimal("0.50")  # roll debit ≤ 50% of original IC credit
    max_rolls_per_side_per_cycle: int = 1

    # DTE-tiered exit (D4)
    # Naming decision pending: when weekly preset adds weekly_close_full_dte=3,
    # decide between per-expiry fields vs. a single expiry-agnostic close_full_dte.
    # See TODOS.md entry 2026-06-27 and docstring above.
    monthly_close_full_dte: int = 7  # DTE≤7 → CLOSE_FULL default (refineable during backtest)

    # Profit-lock config
    profit_lock: ProfitLockConfig = field(default_factory=ProfitLockConfig)


# ---------------------------------------------------------------------------
# Canonical preset — monthly only (Phase 1)
# ---------------------------------------------------------------------------

IC_V2_MONTHLY = IronCondorV2ExpiryConfig(
    expiry_type="monthly",
    # Explicit per D2 ruling: ₹15 monthly floor.  When weekly preset is added it will
    # use ₹10, so the kwarg stays here to document the per-expiry divergence clearly.
    long_wing_min_premium=Decimal("15"),
    profit_lock=ProfitLockConfig(
        zone2_long_wing_min_premium=Decimal("15"),
        monthly_lock_dte_lo=10,
        monthly_lock_dte_hi=22,
    ),
)

# ---------------------------------------------------------------------------
# CONFIGS_V2 registry — for daemon and entry script registration
# ---------------------------------------------------------------------------
# Keyed by expiry_type; values are instantiated IronCondorV2ExpiryConfig presets.
# Phase 1: monthly only. Weekly, leaps, yearly will be added after backtesting.

CONFIGS_V2: dict[str, IronCondorV2ExpiryConfig] = {
    "monthly": IC_V2_MONTHLY,
}
