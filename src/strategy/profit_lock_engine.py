"""Stateless evaluator for IC V2 profit-lock decisions.

Council ruling: docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md Stage 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

import structlog

from src.models.options import OptionChain, OptionLeg
from src.strategy import roll_utils
from src.strategy.ic_expiry_config_v2 import ProfitLockConfig

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ProfitLockState:
    """Immutable snapshot of profit-lock state for one IC cycle. Persisted in PaperStore."""

    profit_lock_zone: int
    zone2_lock_executed: bool
    zone3_lock_executed: bool
    cumulative_lock_debit_pts: Decimal
    active_put_width_pts: int
    active_call_width_pts: int
    cycle_id: str


@dataclass(frozen=True)
class ProfitLockDecision:
    """Output of ProfitLockEngine.evaluate(). Consumed by IronCondorV2.check_signals()."""

    action: Literal["NONE", "ZONE1_LOG", "ZONE2_LOCK", "CLOSE_FULL"]
    zone: int
    captured_fraction: Decimal
    formula_passes: bool
    required_max_width_pts: int | None
    new_put_wing: OptionLeg | None
    new_call_wing: OptionLeg | None
    net_debit_pts: Decimal | None
    guaranteed_floor_fraction: Decimal | None
    skip_reason: str | None


class ProfitLockEngine:
    """Stateless evaluator for IC V2 profit-lock decisions."""

    def evaluate(
        self,
        captured_fraction: Decimal,
        entry_credit_pts: Decimal,
        current_mark_pts: Decimal,
        dte: int,
        expiry_type: str,
        vix: Decimal | None,
        ivr: Decimal | None,
        state: ProfitLockState,
        chain: OptionChain,
        config: ProfitLockConfig,
        short_put_strike: Decimal,
        short_call_strike: Decimal,
        old_long_put: OptionLeg | None = None,
        old_long_call: OptionLeg | None = None,
    ) -> ProfitLockDecision:
        zone = self._detect_zone(captured_fraction, config)
        if zone == 0:
            return ProfitLockDecision(
                "NONE", 0, captured_fraction, False, None, None, None, None, None, None
            )

        if zone == 1:
            if state.profit_lock_zone < 1:
                return ProfitLockDecision(
                    "ZONE1_LOG", 1, captured_fraction, False, None, None, None, None, None, None
                )
            return ProfitLockDecision(
                "NONE", 1, captured_fraction, False, None, None, None, None, None, "already_logged"
            )

        if zone == 3:
            return ProfitLockDecision(
                "CLOSE_FULL",
                3,
                captured_fraction,
                False,
                None,
                None,
                None,
                None,
                None,
                "zone3_reached",
            )

        if zone == 2:
            if state.zone2_lock_executed:
                return ProfitLockDecision(
                    "NONE",
                    2,
                    captured_fraction,
                    False,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "already_executed",
                )

            if expiry_type == "monthly":
                if dte <= 7:
                    return ProfitLockDecision(
                        "CLOSE_FULL",
                        2,
                        captured_fraction,
                        False,
                        None,
                        None,
                        None,
                        None,
                        None,
                        "dte_too_low",
                    )

            new_put = self._select_inward_wing(chain, "put", short_put_strike, config)
            new_call = self._select_inward_wing(chain, "call", short_call_strike, config)

            if new_put is None or new_call is None:
                return ProfitLockDecision(
                    "CLOSE_FULL",
                    2,
                    captured_fraction,
                    False,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "wing_not_found",
                )

            # Use passed in legs or attempt to find them via state
            if old_long_put is None:
                old_put_strike = short_put_strike - Decimal(state.active_put_width_pts)
                old_put_data = chain.strikes.get(old_put_strike)
                old_long_put = old_put_data.pe if old_put_data else None

            if old_long_call is None:
                old_call_strike = short_call_strike + Decimal(state.active_call_width_pts)
                old_call_data = chain.strikes.get(old_call_strike)
                old_long_call = old_call_data.ce if old_call_data else None

            if old_long_put is None or old_long_call is None:
                return ProfitLockDecision(
                    "CLOSE_FULL",
                    2,
                    captured_fraction,
                    False,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "old_leg_not_found",
                )

            old_put_bid = old_long_put.bid
            old_call_bid = old_long_call.bid
            new_put_ask = new_put.ask
            new_call_ask = new_call.ask

            if (
                old_put_bid <= Decimal("0")
                or old_call_bid <= Decimal("0")
                or new_put_ask <= Decimal("0")
                or new_call_ask <= Decimal("0")
            ):
                return ProfitLockDecision(
                    "CLOSE_FULL",
                    2,
                    captured_fraction,
                    False,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "invalid_prices",
                )

            d_lock = (new_put_ask + new_call_ask) - (old_put_bid + old_call_bid)

            if not self._check_debit_guard(d_lock, entry_credit_pts, config):
                return ProfitLockDecision(
                    "CLOSE_FULL",
                    2,
                    captured_fraction,
                    False,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "debit_cap",
                )

            if expiry_type == "monthly":
                if dte > 22 and d_lock >= Decimal("20"):
                    return ProfitLockDecision(
                        "NONE",
                        2,
                        captured_fraction,
                        False,
                        None,
                        None,
                        None,
                        None,
                        None,
                        "dte_too_high",
                    )

            new_put_width = short_put_strike - new_put.strike
            new_call_width = new_call.strike - short_call_strike
            max_width = max(new_put_width, new_call_width)

            if max_width < config.min_viable_width_pts:
                return ProfitLockDecision(
                    "CLOSE_FULL",
                    2,
                    captured_fraction,
                    False,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "required_width_too_small",
                )

            passes_formula = self._evaluate_floor_formula(
                int(max_width),
                state.cumulative_lock_debit_pts,
                d_lock,
                config.cost_buffer_pts,
                entry_credit_pts,
                config.floor_budget_zone2,
            )

            iv_guard_passes = self._check_iv_guard(vix, ivr, config)
            if passes_formula and iv_guard_passes:
                final_passes = True
            elif passes_formula and not iv_guard_passes:
                final_passes = self._evaluate_floor_formula(
                    int(max_width),
                    state.cumulative_lock_debit_pts,
                    d_lock,
                    max(config.cost_buffer_pts, Decimal("15")),
                    entry_credit_pts,
                    config.floor_budget_zone2,
                )
                if not final_passes:
                    return ProfitLockDecision(
                        "CLOSE_FULL",
                        2,
                        captured_fraction,
                        False,
                        None,
                        None,
                        None,
                        None,
                        None,
                        "iv_guard",
                    )
            else:
                return ProfitLockDecision(
                    "CLOSE_FULL",
                    2,
                    captured_fraction,
                    False,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "formula_failed",
                )

            required_max_width = int(
                config.floor_budget_zone2 * entry_credit_pts
                - state.cumulative_lock_debit_pts
                - d_lock
                - config.cost_buffer_pts
            )
            worst_pnl = (
                entry_credit_pts
                - state.cumulative_lock_debit_pts
                - d_lock
                - config.cost_buffer_pts
                - Decimal(max_width)
            )
            floor_fraction = worst_pnl / entry_credit_pts

            return ProfitLockDecision(
                "ZONE2_LOCK",
                2,
                captured_fraction,
                True,
                required_max_width,
                new_put,
                new_call,
                d_lock,
                floor_fraction,
                None,
            )

        return ProfitLockDecision(
            "NONE", zone, captured_fraction, False, None, None, None, None, None, None
        )

    def _detect_zone(self, captured_fraction: Decimal, config: ProfitLockConfig) -> int:
        """Return highest un-acted zone: 0 if nothing new to act on."""
        if captured_fraction >= config.zone3_trigger:
            return 3
        if captured_fraction >= config.zone2_trigger:
            return 2
        if captured_fraction >= config.zone1_trigger:
            return 1
        return 0

    def _evaluate_floor_formula(
        self,
        new_width_pts: int,
        d_cum_pts: Decimal,
        d_lock_pts: Decimal,
        k_pts: Decimal,
        entry_credit_pts: Decimal,
        floor_budget: Decimal,
    ) -> bool:
        """max(W_put, W_call) + D_cum + D_lock + K <= floor_budget * C0."""
        return (
            Decimal(new_width_pts) + d_cum_pts + d_lock_pts + k_pts
            <= floor_budget * entry_credit_pts
        )

    def _select_inward_wing(
        self,
        chain: OptionChain,
        side: Literal["put", "call"],
        short_strike: Decimal,
        config: ProfitLockConfig,
    ) -> OptionLeg | None:
        """Find replacement long wing at ~19Δ within 16-22Δ range, satisfying premium/liquidity floors."""
        option_type: Literal["CE", "PE"] = "CE" if side == "call" else "PE"

        # We need to filter candidates satisfying 19Δ and floors.
        # But wait, find_strike_by_delta takes delta_range.
        candidate = roll_utils.find_strike_by_delta(
            chain,
            option_type,
            (config.zone2_long_wing_delta_lo, config.zone2_long_wing_delta_hi),
            config.zone2_long_wing_delta_target,
        )

        if candidate is None:
            return None

        if candidate.delta is None:
            return None

        # Optional: verify delta is within lo/hi explicitly just in case, but find_strike_by_delta already does this.
        # Check premium floor
        mid = (
            (candidate.bid + candidate.ask) / Decimal("2")
            if (candidate.bid > Decimal("0") and candidate.ask > Decimal("0"))
            else candidate.ltp
        )
        if mid < config.zone2_long_wing_min_premium:
            return None

        # Check liquidity gate
        if candidate.bid <= Decimal("0") or candidate.ask <= Decimal("0"):
            return None
        spread = candidate.ask - candidate.bid
        if spread / mid > Decimal("0.05"):
            return None

        return candidate

    def _check_iv_guard(
        self, vix: Decimal | None, ivr: Decimal | None, config: ProfitLockConfig
    ) -> bool:
        if vix is not None and vix >= config.min_vix and ivr is not None and ivr >= config.min_ivr:
            return True
        return False

    def _check_debit_guard(
        self, d_lock_pts: Decimal, entry_credit_pts: Decimal, config: ProfitLockConfig
    ) -> bool:
        return d_lock_pts <= config.max_debit_fraction * entry_credit_pts
