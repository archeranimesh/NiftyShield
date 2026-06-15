from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from src.paper.models import TradeState

_log = logging.getLogger(__name__)

# Shared profit-target retention ratio: fire when LTP ≤ 30% of entry credit (70% captured).
# Used by CSP and CC evaluators.
_PROFIT_TARGET_RETENTION = Decimal("0.30")
_CC_MIN_ENTRY_CREDIT = Decimal("15")  # CC: below this floor, no early exit — ride to DTE_REVIEW


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
    ) -> list[ExitSignalResult]:
        """Fire when days_held ≥ 21 calendar days since entry.

        Args:
            days_held: Number of calendar days since the trade was opened.

        Returns:
            Single-element list when signal fires; empty list otherwise.
        """
        if days_held >= 21:
            return [
                ExitSignalResult(
                    exit_signal="TIME_STOP",
                    severity="ACTION",
                    threshold_value=21.0,
                    notes=f"Days held {days_held} ≥ 21",
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
