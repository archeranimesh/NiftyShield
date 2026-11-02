"""Tests for the liquidity gate: OI floor, quote rule, reasons, fallback ladder."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from src.instruments.liquidity_gate import (
    GATE_CONFIGS,
    GateConfig,
    GateFailure,
    LadderStep,
    evaluate_ladder,
    order_by_target_delta,
)
from src.instruments.strike_selector import _apply_liquidity_gate, gate_failure_reason


def _row(key: str, bid: str, ask: str, oi: int, delta: float = 0.15) -> dict[str, Any]:
    b, a = Decimal(bid), Decimal(ask)
    return {
        "instrument_key": key,
        "bid": b,
        "ask": a,
        "mid": (a + b) / 2,
        "oi": oi,
        "delta": delta,
    }


GOOD = _row("GOOD", "100", "102", 100_000)
THIN = _row("THIN", "100", "102", 100)
WIDE = _row("WIDE", "100", "130", 100_000)
ONE_SIDED = _row("ONE", "0", "102", 100_000)


def test_defaults_match_previous_behaviour() -> None:
    rows = [GOOD, THIN, WIDE, ONE_SIDED, {"bid": 1, "ask": 1.02, "mid": 1.01}]
    # Original semantics: two-sided, spread <= 5% of mid, no OI check, missing oi ok.
    assert [r.get("instrument_key") for r in _apply_liquidity_gate(rows)] == [
        "GOOD",
        "THIN",
        None,
    ]
    assert _apply_liquidity_gate([]) == []


def test_oi_floor_blocks_thin_strike() -> None:
    out = _apply_liquidity_gate([GOOD, THIN], gate_pct=0.10, min_oi=10_000)
    assert [r["instrument_key"] for r in out] == ["GOOD"]
    assert gate_failure_reason(THIN, Decimal("0.10"), 10_000) is GateFailure.OI


def test_one_sided_quote_blocks() -> None:
    assert gate_failure_reason(ONE_SIDED, Decimal("0.10")) is GateFailure.ONE_SIDED
    assert _apply_liquidity_gate([ONE_SIDED], require_two_sided=True) == []
    # Relaxed rule lets a one-sided quote through (no spread to evaluate).
    assert _apply_liquidity_gate([ONE_SIDED], require_two_sided=False) == [ONE_SIDED]


def test_spread_reason() -> None:
    assert gate_failure_reason(WIDE, Decimal("0.10")) is GateFailure.SPREAD
    assert gate_failure_reason(GOOD, Decimal("0.10")) is None


def test_ladder_passes_target_strike_first() -> None:
    cfg = GATE_CONFIGS["yearly"]
    res = evaluate_ladder([LadderStep("target", [GOOD], cfg), LadderStep("next", [WIDE], cfg)])
    assert res.selected is GOOD
    assert res.step == "target"
    assert res.failures == ()


def test_ladder_falls_to_next_strike() -> None:
    cfg = GATE_CONFIGS["yearly"]
    res = evaluate_ladder([LadderStep("same_expiry", [THIN, WIDE, GOOD], cfg)])
    assert res.selected is GOOD
    assert res.failures == (
        ("same_expiry", "THIN", GateFailure.OI),
        ("same_expiry", "WIDE", GateFailure.SPREAD),
    )


def test_ladder_falls_to_next_expiry() -> None:
    yearly, near = GATE_CONFIGS["yearly"], GATE_CONFIGS["near_far"]
    other = _row("NEAR", "50", "51", 20_000)  # fails yearly OI floor, passes near_far
    res = evaluate_ladder(
        [LadderStep("yearly", [THIN, other], yearly), LadderStep("near_far", [other], near)]
    )
    assert res.selected is other
    assert res.step == "near_far"
    assert res.failures[-1] == ("yearly", "NEAR", GateFailure.OI)


def test_all_steps_fail_returns_reasons() -> None:
    cfg = GATE_CONFIGS["near_far"]
    res = evaluate_ladder([LadderStep("a", [ONE_SIDED, WIDE], cfg), LadderStep("b", [THIN], cfg)])
    assert res.selected is None and res.step is None
    assert [f[2] for f in res.failures] == [
        GateFailure.ONE_SIDED,
        GateFailure.SPREAD,
        GateFailure.OI,
    ]


def test_empty_ladder_fails_closed() -> None:
    res = evaluate_ladder([])
    assert res.selected is None and res.failures == ()


def test_config_rejects_spread_cap_above_ceiling() -> None:
    with pytest.raises(ValueError):
        GateConfig(spread_cap=Decimal("0.11"))
    with pytest.raises(ValueError):
        GateConfig(spread_cap=Decimal("0.05"), min_oi=-1)
    assert GATE_CONFIGS["yearly"].spread_cap == Decimal("0.10")
    assert GATE_CONFIGS["yearly"].min_oi == 50_000
    assert GATE_CONFIGS["near_far"].min_oi == 10_000


def test_order_by_target_delta_band_and_order() -> None:
    rows = [
        _row("A", "1", "1", 1, delta=-0.18),
        _row("B", "1", "1", 1, delta=-0.14),
        _row("C", "1", "1", 1, delta=-0.30),
        _row("D", "1", "1", 1, delta=-0.05),
    ]
    out = order_by_target_delta(rows, 0.15, 0.10, 0.20)
    assert [r["instrument_key"] for r in out] == ["B", "A"]
    assert order_by_target_delta([], 0.15, 0.10, 0.20) == []
