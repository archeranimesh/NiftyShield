"""Liquidity-gate config, failure reasons and fallback ladder (FG-2).

Thresholds are per-expiry-type data calibrated in
``docs/plan/dhan-far-expiry-chain/far-expiry-liquidity-gate/findings.md``.
The ladder is an ordered list of steps (data), evaluated by one pure function.
The per-row check lives in :mod:`src.instruments.strike_selector`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

# Hard ceiling for every expiry type (findings.md, sign-off 2026-11-02).
MAX_SPREAD_CAP = Decimal("0.10")


class GateFailure(str, Enum):
    """Why a strike was rejected by the liquidity gate."""

    ONE_SIDED = "one_sided_quote"
    SPREAD = "spread_too_wide"
    OI = "oi_below_floor"


@dataclass(frozen=True)
class GateConfig:
    """Liquidity thresholds for one expiry type.

    Attributes:
        spread_cap: Max (ask - bid) / mid, as a Decimal fraction.
        min_oi: Minimum open interest.
        require_two_sided: Require bid > 0 and ask > 0.
    """

    spread_cap: Decimal
    min_oi: int = 0
    require_two_sided: bool = True

    def __post_init__(self) -> None:
        if self.spread_cap <= 0 or self.spread_cap > MAX_SPREAD_CAP:
            raise ValueError(f"spread_cap must be in (0, {MAX_SPREAD_CAP}], got {self.spread_cap}")
        if self.min_oi < 0:
            raise ValueError(f"min_oi must be >= 0, got {self.min_oi}")


# Starting points from FG-1 findings; to be tuned with more evidence.
GATE_CONFIGS: dict[str, GateConfig] = {
    "yearly": GateConfig(spread_cap=Decimal("0.10"), min_oi=50_000),
    "near_far": GateConfig(spread_cap=Decimal("0.10"), min_oi=10_000),
}


@dataclass(frozen=True)
class LadderStep:
    """One rung: ordered candidate strikes (best first) and the config to apply."""

    label: str
    candidates: Sequence[dict[str, Any]]
    config: GateConfig


@dataclass(frozen=True)
class LadderResult:
    """Outcome of :func:`evaluate_ladder`.

    Attributes:
        selected: First passing strike, or None (fail closed).
        step: Label of the step that passed, or None.
        failures: (step label, instrument_key, reason) for every rejected candidate tried.
    """

    selected: dict[str, Any] | None
    step: str | None
    failures: tuple[tuple[str, str, GateFailure], ...] = ()


def order_by_target_delta(
    rows: Sequence[dict[str, Any]], target: float, lo: float, hi: float
) -> list[dict[str, Any]]:
    """Restrict to |delta| in [lo, hi] and order by closeness to *target*.

    Args:
        rows: Strike dicts with a ``delta`` field.
        target: Target absolute delta.
        lo: Lower |delta| bound (inclusive).
        hi: Upper |delta| bound (inclusive).

    Returns:
        New list, nearest-to-target first; empty if none in band.
    """
    in_band = [r for r in rows if lo <= abs(float(r["delta"])) <= hi]
    return sorted(in_band, key=lambda r: abs(abs(float(r["delta"])) - target))


def evaluate_ladder(steps: Sequence[LadderStep]) -> LadderResult:
    """Walk the steps in order and return the first strike that passes its gate.

    Args:
        steps: Ordered rungs (target strike, next strikes, next expiry, ...).

    Returns:
        :class:`LadderResult`; ``selected`` is None when every candidate fails.
    """
    from src.instruments.strike_selector import gate_failure_reason

    failures: list[tuple[str, str, GateFailure]] = []
    for step in steps:
        for row in step.candidates:
            reason = gate_failure_reason(
                row, step.config.spread_cap, step.config.min_oi, step.config.require_two_sided
            )
            if reason is None:
                return LadderResult(selected=row, step=step.label, failures=tuple(failures))
            failures.append((step.label, str(row.get("instrument_key", "")), reason))
    return LadderResult(selected=None, step=None, failures=tuple(failures))
