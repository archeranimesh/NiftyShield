"""Tenor policy registry for the CC / PP / Collar overlays.

Everything that differs between the monthly overlay book and the yearly (December)
book lives in one frozen ``OverlayTenorPolicy`` entry of ``OVERLAY_TENORS``. Consumers
read the policy instead of hardcoding monthly numbers. The monthly entry is pinned to
the values the code hardcodes today (``tests/unit/strategy/test_overlay_tenor.py``).

Profit-target / premium-stop values apply to short-call legs only (CC and the Collar's
call). PP and the Collar's put leg are hedges: no profit target, no premium stop.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from src.paper.constants import (
    STRATEGY_OVERLAY,
    STRATEGY_OVERLAY_YEARLY_CC,
    STRATEGY_OVERLAY_YEARLY_COLLAR,
    STRATEGY_OVERLAY_YEARLY_PP,
)
from src.strategy.ic_expiry_config import ExpiryType


@dataclass(frozen=True)
class OverlayTenorPolicy:
    """Tenor-dependent thresholds and ledger names for one overlay book.

    Attributes:
        expiry_type: Registry key; the shared ``ExpiryType`` vocabulary.
        expiry_bucket: Label passed to ``get_expiry_candidates`` preference lists.
        cc_strategy_name: Ledger name for Covered Call trades.
        pp_strategy_name: Ledger name for Protective Put trades.
        collar_strategy_name: Ledger name for Collar trades.
        entry_min_dte: Minimum DTE at entry (entry blocked below it).
        review_dte: DTE at or below which ``DTE_REVIEW`` auto-close fires.
        reentry_min_dte: Minimum DTE for a re-entry (blocked below it).
        roll_dte: DTE at or below which the PP routine roll is due.
        profit_target_decay: Fraction of sold premium that must decay for PROFIT_TARGET.
        delta_stop: Short-call delta at or above which DELTA_STOP fires.
        premium_stop_multiple: Short-leg mark / entry premium multiple for the premium stop.
        premium_stop_alert_only: True if the premium stop alerts without closing.
    """

    expiry_type: ExpiryType
    expiry_bucket: str
    cc_strategy_name: str
    pp_strategy_name: str
    collar_strategy_name: str
    entry_min_dte: int
    review_dte: int
    reentry_min_dte: int
    roll_dte: int
    profit_target_decay: Decimal
    delta_stop: Decimal
    premium_stop_multiple: Decimal
    premium_stop_alert_only: bool


OVERLAY_TENORS: Mapping[ExpiryType, OverlayTenorPolicy] = MappingProxyType(
    {
        "monthly": OverlayTenorPolicy(
            expiry_type="monthly",
            expiry_bucket="monthly",
            cc_strategy_name=STRATEGY_OVERLAY,
            pp_strategy_name=STRATEGY_OVERLAY,
            collar_strategy_name=STRATEGY_OVERLAY,
            entry_min_dte=14,
            review_dte=5,
            reentry_min_dte=14,
            roll_dte=5,
            profit_target_decay=Decimal("0.70"),  # exit_signals _PROFIT_TARGET_RETENTION 0.30
            delta_stop=Decimal("0.55"),
            premium_stop_multiple=Decimal("2.5"),
            premium_stop_alert_only=False,
        ),
        "yearly": OverlayTenorPolicy(
            expiry_type="yearly",
            expiry_bucket="yearly",
            cc_strategy_name=STRATEGY_OVERLAY_YEARLY_CC,
            pp_strategy_name=STRATEGY_OVERLAY_YEARLY_PP,
            collar_strategy_name=STRATEGY_OVERLAY_YEARLY_COLLAR,
            entry_min_dte=20,  # strictly above review_dte / roll_dte, or entry churns same day
            review_dte=15,
            reentry_min_dte=20,
            roll_dte=15,
            profit_target_decay=Decimal("0.75"),
            delta_stop=Decimal("0.55"),  # copied from monthly; tune from paper-run data
            premium_stop_multiple=Decimal("2.5"),
            premium_stop_alert_only=True,
        ),
    }
)
