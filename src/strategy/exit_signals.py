from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

import structlog

from src.paper.models import TradeState

_log = structlog.get_logger(__name__)

# Shared profit-target retention ratio: fire when LTP ≤ 30% of entry credit (70% captured).
# Used by CSP and CC evaluators.
_PROFIT_TARGET_RETENTION = Decimal("0.30")
_CC_MIN_ENTRY_CREDIT = Decimal("15")  # CC: below this floor, no early exit — ride to DTE_REVIEW

_OVERLAY_SHORT_CALL_ROLES = {"overlay_cc", "overlay_collar_call"}
_OVERLAY_LONG_PUT_ROLES = {"overlay_pp", "overlay_collar_put"}
_OVERLAY_STRIKE_OFFSET = 50  # points
_BASE_DTE_GUARD = 10  # if base DTE <= this, block overlay roll

_PROXY_DELTA_WARN = 0.65  # warning threshold — emit WARN, do not close
_PROXY_DELTA_CRITICAL = 0.40  # critical threshold — close after 3 consecutive days
_PROXY_DELTA_CONSECUTIVE = 3  # consecutive days below critical before ACTION fires
_PROXY_PREMIUM_FLOOR = Decimal("0.50")  # premium decay kill — close if mark < this with DTE >= 5


@dataclass(frozen=True)
class ExitSignalResult:
    """The result of evaluating a single exit signal on a position leg."""

    exit_signal: str
    severity: Literal["INFO", "WARN", "ACTION"]
    threshold_value: float | None = None
    delta_stop_would_fire: bool | None = None
    premium_stop_would_fire: bool | None = None
    actual_rule_used: Literal["DELTA", "PREMIUM", "BOTH", "NEITHER"] | None = None
    notes: str | None = None


class ExitSignalEngine:
    """Rule engine for evaluating exit and warning signals on paper trading positions."""

    @staticmethod
    def _sort_results(results: list[ExitSignalResult]) -> list[ExitSignalResult]:
        """Helper to sort results with ACTION first, then WARN, then INFO."""
        severity_order = {"ACTION": 0, "WARN": 1, "INFO": 2}
        return sorted(results, key=lambda x: severity_order.get(x.severity, 3))

    @staticmethod
    def _get_sell_audit_fields(
        delta: float | None,
        current_mark: Decimal,
        entry_price: Decimal,
        delta_threshold: float,
        premium_threshold_mult: Decimal,
    ) -> tuple[bool, bool, Literal["DELTA", "PREMIUM", "BOTH", "NEITHER"]]:
        """Compute the dual-signal audit fields for sell-leg evaluations."""
        # For call options, delta is positive, so we compare delta >= delta_threshold.
        # For put options, delta is negative, so we compare abs(delta) >= delta_threshold.
        # We assume call if delta_threshold > 0, else put if delta_threshold < 0,
        # but to be generic we use the absolute value comparison for puts,
        # and direct comparison for calls.
        if delta is not None:
            if delta_threshold > 0:
                delta_stop_would_fire = delta >= delta_threshold
            else:
                delta_stop_would_fire = abs(delta) >= abs(delta_threshold)
        else:
            delta_stop_would_fire = False

        premium_stop_would_fire = False
        if entry_price > 0:
            premium_stop_would_fire = current_mark >= premium_threshold_mult * entry_price

        actual_rule_used: Literal["DELTA", "PREMIUM", "BOTH", "NEITHER"]
        if delta_stop_would_fire and premium_stop_would_fire:
            actual_rule_used = "BOTH"
        elif delta_stop_would_fire:
            actual_rule_used = "DELTA"
        elif premium_stop_would_fire:
            actual_rule_used = "PREMIUM"
        else:
            actual_rule_used = "NEITHER"

        return delta_stop_would_fire, premium_stop_would_fire, actual_rule_used

    @classmethod
    def evaluate_profit_target_csp(
        cls,
        *,
        ltp: Decimal,
        entry_credit: Decimal,
    ) -> list[ExitSignalResult]:
        """Fire when 70% of entry credit has been captured (LTP ≤ 30% of entry credit).

        Args:
            ltp: Current last-traded price of the short put.
            entry_credit: Premium received at entry (positive Decimal).

        Returns:
            Single-element list when signal fires; empty list otherwise.
        """
        threshold = entry_credit * _PROFIT_TARGET_RETENTION
        if ltp <= threshold:
            return [
                ExitSignalResult(
                    exit_signal="PROFIT_TARGET",
                    severity="ACTION",
                    threshold_value=float(threshold),
                    notes=f"LTP {ltp} ≤ 30% of entry credit {entry_credit} (70% captured)",
                )
            ]
        return []

    @classmethod
    def evaluate_hard_stop_csp(
        cls,
        *,
        ltp: Decimal,
        entry_credit: Decimal,
    ) -> list[ExitSignalResult]:
        """Fire when LTP ≥ 2× entry credit (position doubled against us).

        Args:
            ltp: Current last-traded price of the short put.
            entry_credit: Premium received at entry (positive Decimal).

        Returns:
            Single-element list when signal fires; empty list otherwise.
        """
        threshold = entry_credit * Decimal("2.0")
        if ltp >= threshold:
            return [
                ExitSignalResult(
                    exit_signal="HARD_STOP",
                    severity="ACTION",
                    threshold_value=float(threshold),
                    notes=f"LTP {ltp} ≥ 2× entry credit {entry_credit}",
                )
            ]
        return []

    @classmethod
    def evaluate_delta_breach_csp(
        cls,
        *,
        delta: float | None,
        state: TradeState,
    ) -> list[ExitSignalResult]:
        """Fire when |delta| ≥ 0.40.

        OPEN state → DELTA_BREACH (roll down and out).
        DEFENDED state → DELTA_BREACH_FINAL (close and wait — second breach).
        None delta → DELTA_MISSING WARN (Greek absent or stale; cannot evaluate).

        Args:
            delta: Current delta of the short put (negative float), or None when
                the broker did not return a Greek value for this strike.
            state: Current lifecycle state of the trade.

        Returns:
            Single-element list when signal fires; empty list otherwise.

        Raises:
            ValueError: If state is RE_ENTRY_PENDING (no open leg to evaluate).
        """
        if state == TradeState.RE_ENTRY_PENDING:
            raise ValueError(
                "evaluate_delta_breach_csp called on RE_ENTRY_PENDING state — no open leg"
            )
        if delta is None:
            return [
                ExitSignalResult(
                    exit_signal="DELTA_MISSING",
                    severity="WARN",
                    notes="delta is None — Greek missing or stale; delta breach cannot be evaluated",
                )
            ]
        if abs(delta) >= 0.40:
            if state == TradeState.OPEN:
                return [
                    ExitSignalResult(
                        exit_signal="DELTA_BREACH",
                        severity="ACTION",
                        threshold_value=0.40,
                        notes=f"delta {delta:.4f}: |δ| ≥ 0.40 — roll down and out",
                    )
                ]
            else:  # DEFENDED
                return [
                    ExitSignalResult(
                        exit_signal="DELTA_BREACH_FINAL",
                        severity="ACTION",
                        threshold_value=0.40,
                        notes=f"delta {delta:.4f}: second breach in DEFENDED state — close and wait",
                    )
                ]
        return []

    @classmethod
    def evaluate_time_stop_csp(
        cls,
        *,
        days_held: int,
        dte: int | None = None,
    ) -> list[ExitSignalResult]:
        """Fire the days-held backstop, gated on DTE-remaining (EC-4).

        ``days_held >= 21`` alone is not a valid close trigger for a position
        that was rolled onto a longer-dated (quarterly/leaps) contract — event
        68 (2026-06-30) reproduced this: a leg with 91 DTE remaining hit
        ``days_held == 21`` and fired TIME_STOP with no expiry pressure behind
        it. When DTE is resolvable, it is used as a corroborating guard: the
        backstop only fires if the position also still has ≤ 21 DTE left —
        the same threshold ``ReEntryMixin`` uses as its re-entry floor
        (DTE ≥ 14), so a position past that floor is already "close to
        expiry" territory and the days-held counter is meaningful again.
        When DTE cannot be resolved (e.g. a strike-embedded instrument key
        with no parseable expiry), ``days_held`` alone remains the only
        available signal and the original backstop behavior is preserved.

        Args:
            days_held: Number of calendar days since the trade was opened.
            dte: Days to expiry of the current short put leg, or ``None``
                when the instrument key's expiry could not be resolved.

        Returns:
            Single-element list when signal fires; empty list otherwise.
        """
        if days_held >= 21 and (dte is None or dte <= 21):
            return [
                ExitSignalResult(
                    exit_signal="TIME_STOP",
                    severity="ACTION",
                    threshold_value=21.0,
                    notes=f"Days held {days_held} ≥ 21 (dte={dte})",
                )
            ]
        return []

    @classmethod
    def evaluate_roll_eligible_csp(
        cls,
        *,
        dte: int,
    ) -> list[ExitSignalResult]:
        """Fire when DTE ≤ 7 — position approaching expiry and should be rolled.

        Args:
            dte: Days to expiry of the current short put leg.

        Returns:
            Single-element list when signal fires; empty list otherwise.
        """
        if dte <= 7:
            return [
                ExitSignalResult(
                    exit_signal="ROLL_ELIGIBLE",
                    severity="ACTION",
                    threshold_value=7.0,
                    notes=f"DTE {dte} ≤ 7 — close and reopen via strike_selector",
                )
            ]
        return []

    @classmethod
    def evaluate_cc(
        cls,
        *,
        entry_price: float,
        current_mark: float,
        delta: float | None,
        dte: int,
        days_held: int,
    ) -> list[ExitSignalResult]:
        """Evaluate exit signals for a Covered Call (CC) short call leg.

        Signal set mirrors CSP structure — same signal names, same severity pattern.
        Thresholds differ where direction or covered nature requires it.
        """
        entry_dec = Decimal(str(entry_price))
        mark_dec = Decimal(str(current_mark))

        delta_stop, premium_stop, rule_used = cls._get_sell_audit_fields(
            delta=delta,
            current_mark=mark_dec,
            entry_price=entry_dec,
            delta_threshold=0.55,
            premium_threshold_mult=Decimal("2.5"),
        )

        results: list[ExitSignalResult] = []

        # 1. BELOW_FLOOR: entry credit < 12
        if entry_dec < Decimal("12"):
            results.append(
                ExitSignalResult(
                    exit_signal="BELOW_FLOOR",
                    severity="INFO",
                    threshold_value=12.0,
                    delta_stop_would_fire=delta_stop,
                    premium_stop_would_fire=premium_stop,
                    actual_rule_used=rule_used,
                    notes=f"Entry credit {entry_price} < 12/unit",
                )
            )
        # 2. PROFIT_TARGET: mark <= 30% of entry credit AND entry credit >= 15
        elif entry_dec >= _CC_MIN_ENTRY_CREDIT and mark_dec <= entry_dec * _PROFIT_TARGET_RETENTION:
            results.append(
                ExitSignalResult(
                    exit_signal="PROFIT_TARGET",
                    severity="ACTION",
                    threshold_value=float(_PROFIT_TARGET_RETENTION),
                    delta_stop_would_fire=delta_stop,
                    premium_stop_would_fire=premium_stop,
                    actual_rule_used=rule_used,
                    notes=f"Mark {current_mark} <= 30% of entry credit {entry_price}",
                )
            )

        # 3. LOSS_STOP: mark >= 2.5x entry credit
        if premium_stop:
            results.append(
                ExitSignalResult(
                    exit_signal="LOSS_STOP",
                    severity="ACTION",
                    threshold_value=2.5,
                    delta_stop_would_fire=delta_stop,
                    premium_stop_would_fire=premium_stop,
                    actual_rule_used=rule_used,
                    notes=f"Mark {current_mark} >= 2.5x entry credit {entry_price}",
                )
            )

        # 4. DELTA_STOP: delta >= 0.55
        if delta is not None and delta >= 0.55:
            results.append(
                ExitSignalResult(
                    exit_signal="DELTA_STOP",
                    severity="ACTION",
                    threshold_value=0.55,
                    delta_stop_would_fire=delta_stop,
                    premium_stop_would_fire=premium_stop,
                    actual_rule_used=rule_used,
                    notes=f"Short call delta {delta} >= 0.55",
                )
            )
        # 5. DELTA_WARN: delta >= 0.45 (only if DELTA_STOP did not fire)
        elif delta is not None and delta >= 0.45:
            results.append(
                ExitSignalResult(
                    exit_signal="DELTA_WARN",
                    severity="WARN",
                    threshold_value=0.45,
                    delta_stop_would_fire=delta_stop,
                    premium_stop_would_fire=premium_stop,
                    actual_rule_used=rule_used,
                    notes=f"Short call delta {delta} >= 0.45",
                )
            )

        # 6. TIME_STOP: days_held >= 21
        if days_held >= 21:
            results.append(
                ExitSignalResult(
                    exit_signal="TIME_STOP",
                    severity="ACTION",
                    threshold_value=21.0,
                    delta_stop_would_fire=delta_stop,
                    premium_stop_would_fire=premium_stop,
                    actual_rule_used=rule_used,
                    notes=f"Days held {days_held} >= 21",
                )
            )

        # 7. DTE_REVIEW: DTE <= 5 (always fires at DTE <= 5, replacing DTE_FORCED)
        if dte <= 5:
            results.append(
                ExitSignalResult(
                    exit_signal="DTE_REVIEW",
                    severity="WARN",
                    threshold_value=5.0,
                    delta_stop_would_fire=delta_stop,
                    premium_stop_would_fire=premium_stop,
                    actual_rule_used=rule_used,
                    notes=f"DTE {dte} <= 5",
                )
            )

        return cls._sort_results(results)

    @classmethod
    def evaluate_pp(
        cls,
        *,
        entry_price: float,
        current_mark: float,
        delta: float | None,
        dte: int,
    ) -> list[ExitSignalResult]:
        """Evaluate exit signals for a Protective Put (PP) long put leg.

        Signal priority (both may fire; caller takes first only):
          1. CRASH_MONETIZE — delta ≤ -0.80 OR value ≥ 5× entry debit
          2. ROLL_ELIGIBLE  — DTE ≤ 5 (auto-roll to next expiry)

        No spread guard: paper mode slippage is handled by PaperFillSimulator.

        Args:
            entry_price: Debit paid at entry (positive value).
            current_mark: Current LTP / mark of the long put.
            delta: Current delta of the long put (negative, e.g. -0.85).
            dte: Days to expiry.

        Returns:
            List of ExitSignalResult, sorted ACTION-first. Empty list if no signal.
        """
        entry_dec = Decimal(str(entry_price))
        mark_dec = Decimal(str(current_mark))
        results: list[ExitSignalResult] = []

        # Guard: entry_price == 0 makes value_breached always True (0 >= 0*0).
        if entry_dec <= 0:
            _log.warning(
                "evaluate_pp.zero_entry_price — skipping evaluation",
                extra={"entry_price": entry_price, "current_mark": current_mark},
            )
            return []

        # 1. CRASH_MONETIZE: put delta <= -0.80 OR value >= 5x entry debit
        delta_breached = delta <= -0.80 if delta is not None else False
        value_breached = mark_dec >= Decimal("5.0") * entry_dec
        if delta_breached or value_breached:
            threshold_5x = Decimal("5.0") * entry_dec
            results.append(
                ExitSignalResult(
                    exit_signal="CRASH_MONETIZE",
                    severity="ACTION",
                    threshold_value=5.0,
                    notes=f"Crash monetise: delta={delta}, value={mark_dec:.2f}, 5x_threshold={threshold_5x:.2f}",
                )
            )

        # 2. ROLL_ELIGIBLE: DTE <= 5 (auto-roll to next expiry)
        if dte <= 5:
            results.append(
                ExitSignalResult(
                    exit_signal="ROLL_ELIGIBLE",
                    severity="ACTION",
                    threshold_value=5.0,
                    notes=f"DTE {dte} ≤ 5 — roll PP to next expiry",
                )
            )

        return cls._sort_results(results)

    @classmethod
    def evaluate_roll_overlay(
        cls,
        *,
        leg_role: str,
        dte: int,
        base_dte: int,
        atm_strike: int,
    ) -> list[ExitSignalResult]:
        """Evaluate whether an overlay leg is eligible to roll.

        Triggers when dte <= 5.
        If base_dte <= 10: returns ROLL_BASE_FIRST WARN.
        Otherwise: returns ROLL_ELIGIBLE ACTION with suggested strike in notes.

        Strike suggestion (advisory — actual selection via strike_selector):
          short call roles: ATM + 50
          long put roles:   ATM - 50

        Raises:
            ValueError: When leg_role is not a known overlay role.
        """
        if leg_role not in (_OVERLAY_SHORT_CALL_ROLES | _OVERLAY_LONG_PUT_ROLES):
            raise ValueError(f"Unknown leg_role: {leg_role}")

        if dte > 5:
            return []

        if base_dte <= _BASE_DTE_GUARD:
            return [
                ExitSignalResult(
                    exit_signal="ROLL_BASE_FIRST",
                    severity="WARN",
                    threshold_value=float(_BASE_DTE_GUARD),
                    notes=f"Base DTE {base_dte} ≤ {_BASE_DTE_GUARD} — roll base first",
                )
            ]

        if leg_role in _OVERLAY_SHORT_CALL_ROLES:
            suggested_strike = atm_strike + _OVERLAY_STRIKE_OFFSET
        else:
            suggested_strike = atm_strike - _OVERLAY_STRIKE_OFFSET

        return [
            ExitSignalResult(
                exit_signal="ROLL_ELIGIBLE",
                severity="ACTION",
                threshold_value=5.0,
                notes=f"DTE {dte} ≤ 5 — suggested strike {suggested_strike}",
            )
        ]

    @classmethod
    def evaluate_proxy_delta(
        cls,
        *,
        current_delta: float,
        current_mark: Decimal,
        dte: int,
        days_below_critical: int = 0,
    ) -> list[ExitSignalResult]:
        """Evaluate exit signals for the Proxy deep ITM call leg.

        Three independent signals in priority order:

        1. PROXY_DELTA_CRITICAL (ACTION): delta < 0.40 AND days_below_critical >= 3.
           Close immediately and re-enter at delta ≈ 0.90.
        2. PROXY_PREMIUM_DECAY (ACTION): current_mark < 0.50 AND dte >= 5.
           Deep ITM call has lost virtually all optionality — carry risk is too high.
        3. PROXY_DELTA_WARN (WARN): delta < 0.65. Flag for monitoring; no close.

        PROXY_DELTA_CRITICAL and PROXY_PREMIUM_DECAY are independent — both can fire
        simultaneously. PROXY_DELTA_WARN is suppressed if PROXY_DELTA_CRITICAL fires
        (CRITICAL subsumes WARN).

        Args:
            current_delta: Current delta of the deep ITM call (positive float, 0–1).
            current_mark: Current mark-to-market price of the call (positive Decimal).
            dte: Calendar days to expiry.
            days_below_critical: Consecutive trading days delta has been < 0.40.
                Caller is responsible for maintaining this count across sessions.

        Returns:
            List of ExitSignalResult ordered ACTION before WARN.
        """
        results: list[ExitSignalResult] = []
        critical_fired = False

        # 1. PROXY_DELTA_CRITICAL: delta < 0.40 AND days_below_critical >= 3
        if (
            current_delta < _PROXY_DELTA_CRITICAL
            and days_below_critical >= _PROXY_DELTA_CONSECUTIVE
        ):
            results.append(
                ExitSignalResult(
                    exit_signal="PROXY_DELTA_CRITICAL",
                    severity="ACTION",
                    threshold_value=_PROXY_DELTA_CRITICAL,
                    notes=f"delta {current_delta:.3f} < {_PROXY_DELTA_CRITICAL} for {days_below_critical} consecutive days — close and re-enter at δ≈0.90",
                )
            )
            critical_fired = True

        # 2. PROXY_PREMIUM_DECAY: current_mark < 0.50 AND dte >= 5
        if current_mark < _PROXY_PREMIUM_FLOOR and dte >= 5:
            results.append(
                ExitSignalResult(
                    exit_signal="PROXY_PREMIUM_DECAY",
                    severity="ACTION",
                    threshold_value=float(_PROXY_PREMIUM_FLOOR),
                    notes=f"mark ₹{current_mark} < ₹{_PROXY_PREMIUM_FLOOR} with DTE {dte} — optionality exhausted",
                )
            )

        # 3. PROXY_DELTA_WARN: delta < 0.65 (suppressed if PROXY_DELTA_CRITICAL fires)
        if current_delta < _PROXY_DELTA_WARN and not critical_fired:
            days_remaining = max(0, _PROXY_DELTA_CONSECUTIVE - days_below_critical)
            day_word = "day" if days_remaining == 1 else "days"
            results.append(
                ExitSignalResult(
                    exit_signal="PROXY_DELTA_WARN",
                    severity="WARN",
                    threshold_value=_PROXY_DELTA_WARN,
                    notes=f"delta {current_delta:.3f} < {_PROXY_DELTA_WARN} — monitor; {days_remaining} more {day_word} below {_PROXY_DELTA_CRITICAL} triggers close",
                )
            )

        return cls._sort_results(results)
