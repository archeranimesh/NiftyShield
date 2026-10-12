"""Phase B signal stack (strategy doc section 6, Layers 0-4).

Pure and zero-I/O. Each layer condition is a small predicate
``(Candidate, SignalConfig) -> ReasonCode | None`` (``None`` = pass).
``SignalStack`` evaluates an ordered list of layers in a loop and stops at
the first failing predicate. All thresholds live in ``SignalConfig``;
predicate bodies hold no threshold literals.

Fail-closed policy: a missing input never passes. VIX, quote age, spread,
gearing, speed and Layer 3/4 inputs fail with distinct ``*_UNAVAILABLE``
codes; OI and the 15m move fail with their regular code. The only
pass-on-None cases are the Dhan L1 ask quantity (reduced mode) and Layer 3
when either condition passes on its own.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Literal

_TWO = Decimal(2)
_DIRECTION = {"CE": Decimal(1), "PE": Decimal(-1)}


class ReasonCode(str, Enum):
    """Why a candidate failed a layer."""

    L0_DTE = "L0_DTE"
    L0_OPTION_TYPE = "L0_OPTION_TYPE"
    L0_PREMIUM = "L0_PREMIUM"
    L0_SPREAD = "L0_SPREAD"
    L0_SPREAD_UNAVAILABLE = "L0_SPREAD_UNAVAILABLE"
    L0_ASK_QTY = "L0_ASK_QTY"
    L0_VIX = "L0_VIX"
    L0_VIX_UNAVAILABLE = "L0_VIX_UNAVAILABLE"
    L0_QUOTE_STALE = "L0_QUOTE_STALE"
    L0_QUOTE_AGE_UNAVAILABLE = "L0_QUOTE_AGE_UNAVAILABLE"
    L0_OI = "L0_OI"
    L1_RETURN_DIRECTION = "L1_RETURN_DIRECTION"
    L1_DISTANCE_NOT_SHRINKING = "L1_DISTANCE_NOT_SHRINKING"
    L1_SIGMA = "L1_SIGMA"
    L1_INPUT_UNAVAILABLE = "L1_INPUT_UNAVAILABLE"
    L2_GEARING = "L2_GEARING"
    L2_GEARING_UNAVAILABLE = "L2_GEARING_UNAVAILABLE"
    L2_SPEED_UNAVAILABLE = "L2_SPEED_UNAVAILABLE"
    L2_SPEED = "L2_SPEED"
    L2_MOVE_TOWARD_STRIKE = "L2_MOVE_TOWARD_STRIKE"
    L3_QUALITY = "L3_QUALITY"
    L3_B_UNAVAILABLE = "L3_B_UNAVAILABLE"
    L4_VOLUME = "L4_VOLUME"
    L4_OI_VELOCITY = "L4_OI_VELOCITY"
    L4_PRICE_NOT_RISING = "L4_PRICE_NOT_RISING"
    L4_INPUT_UNAVAILABLE = "L4_INPUT_UNAVAILABLE"


@dataclass(frozen=True)
class Candidate:
    """Per-strike inputs read by the predicates (money/Greeks as Decimal).

    Fractions, not percents (0.003 = 0.3%). ``ask_qty_l1`` None means
    reduced mode; ``speed_5m`` None means unavailable (first scan of day).
    """

    option_type: Literal["CE", "PE"]
    dte: int
    ask: Decimal
    bid: Decimal | None
    spread: Decimal | None
    ask_qty_l1: int | None
    india_vix: Decimal | None
    quote_age_seconds: int | None
    oi: int | None
    underlying_return_15m: Decimal | None
    distance_pct: Decimal
    distance_pct_15m_ago: Decimal | None
    distance_sigma: Decimal | None
    gamma_gearing: Decimal | None
    speed_5m: Decimal | None
    theoretical_price: Decimal | None
    strike_iv_pctile_20d: Decimal | None
    volume_zscore_5m: Decimal | None
    oi_velocity_15m: Decimal | None
    option_price_rising: bool | None
    watchlist_hit: bool = False


@dataclass(frozen=True)
class SignalConfig:
    """Every threshold of the stack.

    ``min_ask_qty`` is required (one lot, from DateAwareLotSizeResolver).
    ``gearing_threshold`` is injected: Stage 1 bootstrap floor is 5.0;
    Stage 2/3 (Phase A p75 calibration) is chosen by the caller.
    ``iv_pctile_max`` is a 0-1 fraction, matching ``strike_iv_pctile_20d``
    as stored by Phase A (0.30 = 30th percentile).
    """

    min_ask_qty: int
    gearing_threshold: Decimal = Decimal("5.0")
    max_dte: int = 1
    min_premium: Decimal = Decimal(2)
    max_premium: Decimal = Decimal(10)
    max_spread_pct_of_mid: Decimal = Decimal("0.25")
    min_vix: Decimal = Decimal(12)
    max_quote_age_seconds: int = 300
    min_oi: int = 1000
    max_distance_sigma: Decimal = Decimal("1.5")
    min_move_toward_strike: Decimal = Decimal("0.003")
    edge_abs_floor: Decimal = Decimal("0.75")
    edge_spread_multiple: Decimal = Decimal("1.0")
    edge_ask_fraction: Decimal = Decimal("0.35")
    mispricing_max_distance_pct: Decimal = Decimal("0.10")
    iv_pctile_max: Decimal = Decimal("0.30")
    min_volume_zscore: Decimal = Decimal("2.0")
    min_oi_velocity: Decimal = Decimal("0.15")


Predicate = Callable[[Candidate, SignalConfig], "ReasonCode | None"]


@dataclass(frozen=True)
class Layer:
    """Named ordered group of predicates; ``index`` is its f0..f4 slot."""

    index: int
    predicates: tuple[Predicate, ...]


@dataclass(frozen=True)
class StackResult:
    """Outcome of one stack evaluation.

    ``f0..f4`` are tri-state: True passed, False failed, None never reached.
    """

    passed: bool
    failed_layer: int | None
    reason: ReasonCode | None
    f0: bool | None
    f1: bool | None
    f2: bool | None
    f3: bool | None
    f4: bool | None
    quality_method: Literal["A", "B", "both", "none"]
    watchlist_hit: bool


# --- Layer 0 -------------------------------------------------------------


def l0_dte(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    return None if c.dte <= cfg.max_dte else ReasonCode.L0_DTE


def l0_option_type(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    return None if c.option_type in _DIRECTION else ReasonCode.L0_OPTION_TYPE


def l0_premium(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    ok = cfg.min_premium <= c.ask <= cfg.max_premium
    return None if ok else ReasonCode.L0_PREMIUM


def l0_spread(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    if c.bid is None or c.spread is None:
        return ReasonCode.L0_SPREAD_UNAVAILABLE
    mid = (c.bid + c.ask) / _TWO
    if mid <= 0:
        return ReasonCode.L0_SPREAD
    ok = c.spread <= cfg.max_spread_pct_of_mid * mid
    return None if ok else ReasonCode.L0_SPREAD


def l0_ask_qty(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    if c.ask_qty_l1 is None:  # reduced mode: documented pass
        return None
    return None if c.ask_qty_l1 >= cfg.min_ask_qty else ReasonCode.L0_ASK_QTY


def l0_vix(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    if c.india_vix is None:
        return ReasonCode.L0_VIX_UNAVAILABLE
    return None if c.india_vix > cfg.min_vix else ReasonCode.L0_VIX


def l0_quote_fresh(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    if c.quote_age_seconds is None:
        return ReasonCode.L0_QUOTE_AGE_UNAVAILABLE
    ok = c.quote_age_seconds <= cfg.max_quote_age_seconds
    return None if ok else ReasonCode.L0_QUOTE_STALE


def l0_oi(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    ok = c.oi is not None and c.oi >= cfg.min_oi
    return None if ok else ReasonCode.L0_OI


# --- Layer 1 -------------------------------------------------------------


def l1_return_direction(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    if c.underlying_return_15m is None:
        return ReasonCode.L1_INPUT_UNAVAILABLE
    ok = c.underlying_return_15m * _DIRECTION[c.option_type] > 0
    return None if ok else ReasonCode.L1_RETURN_DIRECTION


def l1_distance_shrinking(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    if c.distance_pct_15m_ago is None:
        return ReasonCode.L1_INPUT_UNAVAILABLE
    ok = c.distance_pct < c.distance_pct_15m_ago
    return None if ok else ReasonCode.L1_DISTANCE_NOT_SHRINKING


def l1_sigma(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    if c.distance_sigma is None:
        return ReasonCode.L1_INPUT_UNAVAILABLE
    ok = c.distance_sigma <= cfg.max_distance_sigma
    return None if ok else ReasonCode.L1_SIGMA


# --- Layer 2 -------------------------------------------------------------


def l2_gearing(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    if c.gamma_gearing is None:
        return ReasonCode.L2_GEARING_UNAVAILABLE
    return None if c.gamma_gearing > cfg.gearing_threshold else ReasonCode.L2_GEARING


def l2_speed(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    if c.speed_5m is None:
        return ReasonCode.L2_SPEED_UNAVAILABLE
    return None if c.speed_5m > 0 else ReasonCode.L2_SPEED


def l2_move_toward_strike(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    if c.underlying_return_15m is None:
        return ReasonCode.L2_MOVE_TOWARD_STRIKE
    move = c.underlying_return_15m * _DIRECTION[c.option_type]
    ok = move > cfg.min_move_toward_strike
    return None if ok else ReasonCode.L2_MOVE_TOWARD_STRIKE


# --- Layer 3 -------------------------------------------------------------


def quality_conditions(c: Candidate, cfg: SignalConfig) -> tuple[bool | None, bool | None]:
    """Return tri-state (condition A, condition B); None = unavailable."""
    a: bool | None = None
    if c.theoretical_price is not None and c.spread is not None:
        if c.distance_pct <= cfg.mispricing_max_distance_pct:
            need = max(
                cfg.edge_abs_floor,
                cfg.edge_spread_multiple * c.spread,
                cfg.edge_ask_fraction * c.ask,
            )
            a = c.theoretical_price - c.ask >= need
    b: bool | None = None
    if c.strike_iv_pctile_20d is not None:
        b = c.strike_iv_pctile_20d < cfg.iv_pctile_max
    return a, b


def quality_method(a: bool | None, b: bool | None) -> Literal["A", "B", "both", "none"]:
    """Map the condition flags to the logged ``quality_filter_method``."""
    if a and b:
        return "both"
    if a:
        return "A"
    if b:
        return "B"
    return "none"


def l3_quality(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    a, b = quality_conditions(c, cfg)
    if a or b:
        return None
    return ReasonCode.L3_B_UNAVAILABLE if b is None else ReasonCode.L3_QUALITY


# --- Layer 4 -------------------------------------------------------------


def l4_volume(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    if c.volume_zscore_5m is None:
        return ReasonCode.L4_INPUT_UNAVAILABLE
    ok = c.volume_zscore_5m > cfg.min_volume_zscore
    return None if ok else ReasonCode.L4_VOLUME


def l4_oi_velocity(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    if c.oi_velocity_15m is None:
        return ReasonCode.L4_INPUT_UNAVAILABLE
    ok = c.oi_velocity_15m > cfg.min_oi_velocity
    return None if ok else ReasonCode.L4_OI_VELOCITY


def l4_price_rising(c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    if c.option_price_rising is None:
        return ReasonCode.L4_INPUT_UNAVAILABLE
    return None if c.option_price_rising else ReasonCode.L4_PRICE_NOT_RISING


DEFAULT_LAYERS: tuple[Layer, ...] = (
    Layer(
        0,
        (l0_dte, l0_option_type, l0_premium, l0_spread, l0_ask_qty, l0_vix, l0_quote_fresh, l0_oi),
    ),
    Layer(1, (l1_return_direction, l1_distance_shrinking, l1_sigma)),
    Layer(2, (l2_gearing, l2_speed, l2_move_toward_strike)),
    Layer(3, (l3_quality,)),
    Layer(4, (l4_volume, l4_oi_velocity, l4_price_rising)),
)


@dataclass(frozen=True)
class SignalStack:
    """Ordered layers evaluated first-failure-wins."""

    config: SignalConfig
    layers: tuple[Layer, ...] = field(default=DEFAULT_LAYERS)

    def evaluate(self, c: Candidate) -> StackResult:
        """Evaluate ``c``; stop at the first failing predicate.

        Args:
            c: Candidate inputs.

        Returns:
            Frozen result with tri-state f0..f4 (None = never reached).
        """
        flags: dict[int, bool] = {}
        failed: int | None = None
        reason: ReasonCode | None = None
        for layer in self.layers:
            reason = _first_failure(layer, c, self.config)
            flags[layer.index] = reason is None
            if reason is not None:
                failed = layer.index
                break
        method: Literal["A", "B", "both", "none"] = "none"
        if 3 in flags:
            method = quality_method(*quality_conditions(c, self.config))
        return StackResult(
            passed=failed is None,
            failed_layer=failed,
            reason=reason,
            f0=flags.get(0),
            f1=flags.get(1),
            f2=flags.get(2),
            f3=flags.get(3),
            f4=flags.get(4),
            quality_method=method,
            watchlist_hit=c.watchlist_hit,
        )


def _first_failure(layer: Layer, c: Candidate, cfg: SignalConfig) -> ReasonCode | None:
    for predicate in layer.predicates:
        code = predicate(c, cfg)
        if code is not None:
            return code
    return None
