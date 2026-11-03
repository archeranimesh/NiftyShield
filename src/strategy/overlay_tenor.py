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
from datetime import date, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING

from src.config import DEFAULT_DHAN_MIN_INTERVAL_S
from src.paper.constants import (
    STRATEGY_OVERLAY,
    STRATEGY_OVERLAY_YEARLY_CC,
    STRATEGY_OVERLAY_YEARLY_COLLAR,
    STRATEGY_OVERLAY_YEARLY_PP,
)
from src.strategy.ic_expiry_config import ExpiryType

if TYPE_CHECKING:
    from src.instruments.lookup import InstrumentLookup


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
        monitor_cadence_s: Seconds between monitor cycles for this tenor; one routed chain
            call per cycle, through the shared Dhan throttle.
        greeks_freshness_bound_s: Oldest chain snapshot (seconds) still treated as live.
            Must be at least ``min_freshness_bound_s(monitor_cadence_s, <Dhan floor>)``
            so one missed cycle plus a throttled retry does not flip the book to stale.
        greeks_cache_max_age_days: Trading-day age up to which a last-known delta may be
            shown, labelled (consumed by DSN-3).
        greeks_action_max_age_days: Trading-day age up to which a last-known delta may
            serve degraded aggregation (consumed by DSN-3); never above the cache age.
        routed_chain: True to fetch the entry chain through the configured
            ``ChainSource`` routing (Dhan fallback for zero Upstox Greeks);
            False keeps the direct Upstox fetch.
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
    monitor_cadence_s: int
    greeks_freshness_bound_s: int
    greeks_cache_max_age_days: int = 3
    greeks_action_max_age_days: int = 1
    routed_chain: bool = False

    def __post_init__(self) -> None:
        """Reject structurally impossible cadence and age values.

        Raises:
            ValueError: A cadence, bound or age is not positive, or the action age
                exceeds the cache age.
        """
        for name in (
            "monitor_cadence_s",
            "greeks_freshness_bound_s",
            "greeks_cache_max_age_days",
            "greeks_action_max_age_days",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{self.expiry_type}: {name} must be positive")
        if self.greeks_action_max_age_days > self.greeks_cache_max_age_days:
            raise ValueError(
                f"{self.expiry_type}: greeks_action_max_age_days must not exceed "
                "greeks_cache_max_age_days"
            )


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
            monitor_cadence_s=90,  # StrategyMonitor / monitor_daemon --poll-interval default
            greeks_freshness_bound_s=184,  # 2 x 90 + 4; monthly reads Upstox, bound is a floor
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
            monitor_cadence_s=3600,  # hourly, decided 2026-11-03; one Dhan chain call per cycle
            greeks_freshness_bound_s=7204,  # 2 x 3600 + one 4 s throttle slot
            routed_chain=True,  # Upstox returns zero Greeks past ~90 DTE
        ),
    }
)


def min_freshness_bound_s(
    cadence_s: int, dhan_min_interval_s: float = DEFAULT_DHAN_MIN_INTERVAL_S
) -> float:
    """Smallest consistent freshness bound: two cycles plus one throttle slot.

    Args:
        cadence_s: Monitor cadence in seconds.
        dhan_min_interval_s: Dhan chain call floor (``market_data.chain.dhan_min_interval_s``).

    Returns:
        ``2 * cadence_s + dhan_min_interval_s``.
    """
    return 2 * cadence_s + dhan_min_interval_s


def validate_tenor_policy(
    policy: OverlayTenorPolicy, dhan_min_interval_s: float = DEFAULT_DHAN_MIN_INTERVAL_S
) -> None:
    """Check one policy's cadence and freshness bound against the Dhan call floor.

    Args:
        policy: Policy to check.
        dhan_min_interval_s: Dhan chain call floor in seconds.

    Raises:
        ValueError: A routed (Dhan-capable) policy's cadence is shorter than one throttle
            slot, or the freshness bound is below ``min_freshness_bound_s``.
    """
    if policy.routed_chain and policy.monitor_cadence_s < dhan_min_interval_s:
        raise ValueError(
            f"{policy.expiry_type}: monitor_cadence_s {policy.monitor_cadence_s} is below "
            f"the Dhan call floor {dhan_min_interval_s}"
        )
    minimum = min_freshness_bound_s(policy.monitor_cadence_s, dhan_min_interval_s)
    if policy.greeks_freshness_bound_s < minimum:
        raise ValueError(
            f"{policy.expiry_type}: greeks_freshness_bound_s {policy.greeks_freshness_bound_s} "
            f"is below the minimum {minimum} (2 x monitor_cadence_s {policy.monitor_cadence_s} "
            f"+ one {dhan_min_interval_s} s throttle slot)"
        )


def validate_overlay_tenors(dhan_min_interval_s: float = DEFAULT_DHAN_MIN_INTERVAL_S) -> None:
    """Startup check: every registered tenor is consistent with the Dhan call floor.

    Args:
        dhan_min_interval_s: Pass ``settings.market_data.chain.dhan_min_interval_s``.

    Raises:
        ValueError: Any registered policy fails ``validate_tenor_policy``.
    """
    for policy in OVERLAY_TENORS.values():
        validate_tenor_policy(policy, dhan_min_interval_s)


def resolve_overlay_expiry(
    lookup: InstrumentLookup, today: date, policy: OverlayTenorPolicy
) -> str | None:
    """Resolve the contract expiry a new overlay entry should use.

    Wraps one ``get_expiry_candidates`` call: expiries at or within ``roll_dte`` of
    ``today`` are excluded (``min_expiry``), so the yearly book moves to the next December once
    the near one reaches its roll threshold. The first candidate whose label matches
    ``policy.expiry_bucket`` is then checked against ``policy.entry_min_dte``.

    Args:
        lookup: BOD instrument lookup.
        today: Reference date for DTE (callers inject ``market_today()``).
        policy: Tenor policy supplying the bucket, roll window and entry floor.

    Returns:
        Expiry as ``YYYY-MM-DD``, or ``None`` if no candidate exists or its DTE is below
        ``policy.entry_min_dte``. Both are structural failures for the caller.
    """
    candidates = lookup.get_expiry_candidates(
        underlying="NIFTY",
        today=today,
        preference=[policy.expiry_bucket],
        min_expiry=(today + timedelta(days=policy.roll_dte)).isoformat(),
    )
    expiry = next((exp for label, exp in candidates if label == policy.expiry_bucket), None)
    if expiry is None or (date.fromisoformat(expiry) - today).days < policy.entry_min_dte:
        return None
    return expiry
