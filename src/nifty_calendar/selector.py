"""Wing structure selector and pure quote helpers for Nifty positional calendar."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, TypeAlias

from src.models.options import OptionChain, OptionLeg
from src.models.portfolio import AssetType, Direction
from src.nifty_calendar.config import CalendarVariantConfig
from src.nifty_calendar.errors import InvalidStructureError
from src.nifty_calendar.models import CalendarLeg, CalendarStructure
from src.nifty_calendar.payoff import compute_metrics, derive_far_carry_from_atm


def mid(leg: OptionLeg) -> Decimal:
    """Return the mid price for an OptionLeg.

    Requires positive bid and ask prices. Never falls back to LTP because
    far-dated option LTP can lag quotes significantly.

    Args:
        leg: The OptionLeg snapshot.

    Returns:
        Mid price as Decimal: (bid + ask) / 2.

    Raises:
        ValueError: If bid <= 0 or ask <= 0.
    """
    if leg.bid <= Decimal("0") or leg.ask <= Decimal("0"):
        raise ValueError("OptionLeg has missing or non-positive quote")
    return (leg.bid + leg.ask) / Decimal("2")


def spread_points(leg: OptionLeg) -> Decimal:
    """Return the bid-ask spread in points.

    Requires positive bid and ask prices.

    Args:
        leg: The OptionLeg snapshot.

    Returns:
        Spread in points: ask - bid.

    Raises:
        ValueError: If bid <= 0 or ask <= 0.
    """
    if leg.bid <= Decimal("0") or leg.ask <= Decimal("0"):
        raise ValueError("OptionLeg has missing or non-positive quote")
    return leg.ask - leg.bid


@dataclass(frozen=True)
class NoEntry:
    """Represents a skipped entry when no structure satisfies all filters.

    Attributes:
        reason: Human-readable explanation of why entry was skipped.
        failed_filter: Name of the primary filter that caused rejection.
    """

    reason: str
    failed_filter: str | None = None


SelectionResult: TypeAlias = CalendarStructure | NoEntry


class StructureSelector(Protocol):
    """Protocol for selecting calendar structures from market data chains."""

    def select(
        self,
        chain_near: OptionChain,
        chain_far: OptionChain,
        spot: Decimal,
        config: CalendarVariantConfig,
        exclude_short_strikes: frozenset[Decimal] = frozenset(),
    ) -> SelectionResult:
        """Select a valid calendar structure or return NoEntry."""
        ...


@dataclass
class _CandidateEvaluation:
    """Internal evaluation record for a wing grid candidate."""

    put_offset: int
    call_offset: int
    structure: CalendarStructure | None
    failed_filters: list[str]
    total_violation: Decimal
    dist_from_start: int

    @property
    def first_failed_filter(self) -> str | None:
        return self.failed_filters[0] if self.failed_filters else None


class WingStructureSelector:
    """Selects calendar wing strikes using deterministic full-grid enumeration."""

    def select(
        self,
        chain_near: OptionChain,
        chain_far: OptionChain,
        spot: Decimal,
        config: CalendarVariantConfig,
        exclude_short_strikes: frozenset[Decimal] = frozenset(),
    ) -> SelectionResult:
        """Select an optimal calendar structure across the wing search grid.

        Enumerates wing offsets in 100-point multiples from min_wing_points (300)
        up to start + max_steps * step (900), evaluating spreads, Greeks, and
        the strategy filters (delta cap, vega cap, vega floor >= 0, risk-reward floor,
        symmetry, and net credit). Ranks candidates deterministically.

        Args:
            chain_near: Near-expiry OptionChain snapshot.
            chain_far: Far-expiry OptionChain snapshot.
            spot: Underlying spot price.
            config: CalendarVariantConfig parameters.
            exclude_short_strikes: Strikes the short straddle must not use (a same-day
                re-entry whose original strike would collide in the ledger). The nearest
                remaining strike to spot is used; a tie goes to the lower strike.

        Returns:
            CalendarStructure if a candidate passes all filters, else NoEntry.
        """
        if not chain_near.strikes:
            return NoEntry(reason="Near chain has no strikes", failed_filter="missing_quote")

        # 1. Determine near ATM strike (closest to spot, multiples of 50 allowed)
        eligible = [k for k in chain_near.strikes if k not in exclude_short_strikes]
        if not eligible:
            return NoEntry(reason="No eligible near strike", failed_filter="missing_quote")
        atm_strike = min(eligible, key=lambda k: (abs(k - spot), k))
        near_strike_data = chain_near.strikes[atm_strike]
        near_ce = near_strike_data.ce
        near_pe = near_strike_data.pe

        if near_ce is None or near_pe is None:
            return NoEntry(reason="Near ATM strike missing CE or PE", failed_filter="missing_quote")

        # Quote checks on near ATM
        if (
            near_ce.bid <= Decimal("0")
            or near_ce.ask <= Decimal("0")
            or near_pe.bid <= Decimal("0")
            or near_pe.ask <= Decimal("0")
        ):
            return NoEntry(
                reason="Near ATM leg missing two-sided quote", failed_filter="missing_quote"
            )

        # Greek checks on near ATM
        if (
            near_ce.delta is None
            or near_ce.vega is None
            or near_ce.iv is None
            or near_pe.delta is None
            or near_pe.vega is None
            or near_pe.iv is None
        ):
            return NoEntry(reason="Near ATM leg missing Greeks", failed_filter="missing_greeks")

        # Spread check on near ATM
        near_ce_spread = spread_points(near_ce)
        near_pe_spread = spread_points(near_pe)
        if near_ce_spread > config.spread_tolerance or near_pe_spread > config.spread_tolerance:
            return NoEntry(
                reason="Near ATM leg spread exceeds tolerance", failed_filter="spread_tolerance"
            )

        near_ce_mid = mid(near_ce)
        near_pe_mid = mid(near_pe)

        # 2. Determine far carry using far ATM quotes (no fallback to near parity)
        if atm_strike not in chain_far.strikes:
            return NoEntry(
                reason="Far ATM quote missing or non-positive",
                failed_filter="missing_quote",
            )
        far_atm = chain_far.strikes[atm_strike]
        if (
            far_atm.ce is None
            or far_atm.pe is None
            or far_atm.ce.bid <= Decimal("0")
            or far_atm.ce.ask <= Decimal("0")
            or far_atm.pe.bid <= Decimal("0")
            or far_atm.pe.ask <= Decimal("0")
        ):
            return NoEntry(
                reason="Far ATM quote missing or non-positive",
                failed_filter="missing_quote",
            )
        far_carry = derive_far_carry_from_atm(
            far_atm_strike=atm_strike,
            far_atm_ce_mid=mid(far_atm.ce),
            far_atm_pe_mid=mid(far_atm.pe),
            spot=spot,
        )

        # Build near CalendarLegs
        short_ce = CalendarLeg(
            instrument_key=f"NIFTY_{chain_near.expiry}_{int(atm_strike)}_CE",
            strike=atm_strike,
            option_type=AssetType.CE,
            expiry=chain_near.expiry,
            side=Direction.SELL,
            qty_lots=config.lots,
            entry_price=near_ce_mid,
            delta=near_ce.delta,
            vega=near_ce.vega,
            iv=near_ce.iv,
        )
        short_pe = CalendarLeg(
            instrument_key=f"NIFTY_{chain_near.expiry}_{int(atm_strike)}_PE",
            strike=atm_strike,
            option_type=AssetType.PE,
            expiry=chain_near.expiry,
            side=Direction.SELL,
            qty_lots=config.lots,
            entry_price=near_pe_mid,
            delta=near_pe.delta,
            vega=near_pe.vega,
            iv=near_pe.iv,
        )

        # 3. Enumerate wing grid
        max_put_offset = (
            config.put_wing_start_points + config.max_wing_search_steps * config.wing_step_points
        )
        max_call_offset = (
            config.call_wing_start_points + config.max_wing_search_steps * config.wing_step_points
        )

        put_offsets = list(
            range(config.min_wing_points, max_put_offset + 1, config.wing_step_points)
        )
        call_offsets = list(
            range(config.min_wing_points, max_call_offset + 1, config.wing_step_points)
        )

        evaluations: list[_CandidateEvaluation] = []
        any_quotable_combination = False

        for p_off in put_offsets:
            k_put = atm_strike - Decimal(p_off)
            if k_put not in chain_far.strikes or chain_far.strikes[k_put].pe is None:
                continue
            far_pe = chain_far.strikes[k_put].pe
            if far_pe is None:
                continue

            for c_off in call_offsets:
                k_call = atm_strike + Decimal(c_off)
                if k_call not in chain_far.strikes or chain_far.strikes[k_call].ce is None:
                    continue
                far_ce = chain_far.strikes[k_call].ce
                if far_ce is None:
                    continue

                dist = abs(p_off - config.put_wing_start_points) + abs(
                    c_off - config.call_wing_start_points
                )
                failed_filters: list[str] = []
                total_violation = Decimal("0")

                # Pre-check quotes on far wings
                if (
                    far_pe.bid <= Decimal("0")
                    or far_pe.ask <= Decimal("0")
                    or far_ce.bid <= Decimal("0")
                    or far_ce.ask <= Decimal("0")
                ):
                    failed_filters.append("missing_quote")
                    total_violation += Decimal("10.0")
                    evaluations.append(
                        _CandidateEvaluation(
                            p_off, c_off, None, failed_filters, total_violation, dist
                        )
                    )
                    continue

                any_quotable_combination = True

                # Pre-check Greeks on far wings
                if (
                    far_pe.delta is None
                    or far_pe.vega is None
                    or far_pe.iv is None
                    or far_ce.delta is None
                    or far_ce.vega is None
                    or far_ce.iv is None
                ):
                    failed_filters.append("missing_greeks")
                    total_violation += Decimal("10.0")
                    evaluations.append(
                        _CandidateEvaluation(
                            p_off, c_off, None, failed_filters, total_violation, dist
                        )
                    )
                    continue

                # Spread tolerance check on far wings
                pe_spread = spread_points(far_pe)
                ce_spread = spread_points(far_ce)
                max_wing_spread = max(pe_spread, ce_spread)
                if max_wing_spread > config.spread_tolerance:
                    failed_filters.append("spread_tolerance")
                    v_spread = (max_wing_spread - config.spread_tolerance) / config.spread_tolerance
                    total_violation += v_spread

                # Construct candidate structure
                long_pe = CalendarLeg(
                    instrument_key=f"NIFTY_{chain_far.expiry}_{int(k_put)}_PE",
                    strike=k_put,
                    option_type=AssetType.PE,
                    expiry=chain_far.expiry,
                    side=Direction.BUY,
                    qty_lots=config.lots,
                    entry_price=mid(far_pe),
                    delta=far_pe.delta,
                    vega=far_pe.vega,
                    iv=far_pe.iv,
                )
                long_ce = CalendarLeg(
                    instrument_key=f"NIFTY_{chain_far.expiry}_{int(k_call)}_CE",
                    strike=k_call,
                    option_type=AssetType.CE,
                    expiry=chain_far.expiry,
                    side=Direction.BUY,
                    qty_lots=config.lots,
                    entry_price=mid(far_ce),
                    delta=far_ce.delta,
                    vega=far_ce.vega,
                    iv=far_ce.iv,
                )

                try:
                    structure = CalendarStructure(
                        short_ce=short_ce,
                        short_pe=short_pe,
                        long_ce_wing=long_ce,
                        long_pe_wing=long_pe,
                    )
                    metrics = compute_metrics(
                        structure=structure,
                        spot=spot,
                        far_carry=far_carry,
                        lot_size=config.lot_size,
                    )
                except InvalidStructureError:
                    failed_filters.append("no_breakeven")
                    total_violation += Decimal("10.0")
                    evaluations.append(
                        _CandidateEvaluation(
                            p_off, c_off, None, failed_filters, total_violation, dist
                        )
                    )
                    continue

                # Filter 1: Net Delta
                if abs(metrics.net_delta) > config.delta_cap:
                    failed_filters.append("delta_cap")
                    total_violation += (
                        abs(metrics.net_delta) - config.delta_cap
                    ) / config.delta_cap

                # Filter 2: Net Vega Cap
                if metrics.net_vega > config.vega_cap:
                    failed_filters.append("vega_cap")
                    total_violation += (metrics.net_vega - config.vega_cap) / config.vega_cap

                # Filter 2b: Vega Floor (net vega must be >= 0; calendar should not be net short vega)
                if metrics.net_vega < Decimal("0"):
                    failed_filters.append("vega_floor")
                    total_violation += (-metrics.net_vega) / Decimal("1.0")

                # Filter 3: Risk-Reward
                if metrics.risk_reward < config.risk_reward_floor:
                    failed_filters.append("risk_reward")
                    total_violation += (
                        config.risk_reward_floor - metrics.risk_reward
                    ) / config.risk_reward_floor

                # Filter 4: Breakeven % Symmetry
                be_diff = abs(metrics.breakeven_high_pct - metrics.breakeven_low_pct)
                if be_diff > config.breakeven_symmetry_tolerance_pct:
                    failed_filters.append("breakeven_symmetry")
                    total_violation += (
                        be_diff - config.breakeven_symmetry_tolerance_pct
                    ) / config.breakeven_symmetry_tolerance_pct

                # Filter 5: Loss Symmetry at Breakevens
                l_high = abs(metrics.loss_at_breakeven_high_per_lot)
                l_low = abs(metrics.loss_at_breakeven_low_per_lot)
                max_loss_val = max(l_high, l_low, Decimal("1.0"))
                loss_ratio = abs(l_high - l_low) / max_loss_val
                if loss_ratio > config.breakeven_loss_symmetry_tolerance:
                    failed_filters.append("loss_symmetry")
                    total_violation += (
                        loss_ratio - config.breakeven_loss_symmetry_tolerance
                    ) / config.breakeven_loss_symmetry_tolerance

                # Filter 6: Net Credit
                if metrics.net_credit_per_unit <= Decimal("0"):
                    failed_filters.append("net_credit")
                    # Floor denominator at 1.0 to prevent division by zero
                    denom = Decimal("1.0")
                    total_violation += (-metrics.net_credit_per_unit) / denom

                evaluations.append(
                    _CandidateEvaluation(
                        put_offset=p_off,
                        call_offset=c_off,
                        structure=structure,
                        failed_filters=failed_filters,
                        total_violation=total_violation,
                        dist_from_start=dist,
                    )
                )

        if not evaluations or not any_quotable_combination:
            return NoEntry(reason="No quotable wing strikes found", failed_filter="missing_quote")

        # Rank candidates:
        # 1. Fewest failed filters
        # 2. Smallest total violation
        # 3. Distance from start wings (prefers wings closest to start)
        # 4. Lexicographical put_offset, call_offset
        evaluations.sort(
            key=lambda e: (
                len(e.failed_filters),
                e.total_violation,
                e.dist_from_start,
                e.put_offset,
                e.call_offset,
            )
        )

        best = evaluations[0]
        if len(best.failed_filters) == 0 and best.structure is not None:
            return best.structure

        return NoEntry(
            reason=f"Best candidate ({best.put_offset}/{best.call_offset}) failed filter: {best.first_failed_filter}",
            failed_filter=best.first_failed_filter,
        )
