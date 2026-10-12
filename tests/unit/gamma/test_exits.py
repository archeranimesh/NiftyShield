"""Tests for Phase B exit rules E1/E2/E3."""

from __future__ import annotations

from dataclasses import replace
from datetime import time
from decimal import Decimal as D

from src.gamma.exits import (
    ExitConfig,
    ExitPosition,
    ExitReason,
    ExitTick,
    evaluate_exit,
)

CFG = ExitConfig()
POS = ExitPosition(entry_ask=D("4"))


def tick(**kw: object) -> ExitTick:
    """A quiet DTE-0 mid-session tick (no rule fires); override via kw."""
    base: dict[str, object] = dict(at=time(11, 0), dte=0, bid=D("4"), ask_qty=130)
    base.update(kw)
    return ExitTick(**base)  # type: ignore[arg-type]  # kwargs dict is untyped test input


def reason(pos: ExitPosition = POS, **kw: object) -> ExitReason | None:
    d = evaluate_exit(pos, tick(**kw), CFG)
    return d.reason if d else None


def test_no_exit_returns_none() -> None:
    assert evaluate_exit(POS, tick(), CFG) is None


def test_e1_boundary() -> None:
    assert reason(bid=D("19.99")) is None
    assert reason(bid=D("20")) is ExitReason.E1_PROFIT_TARGET


def test_e2_stop_boundary() -> None:
    assert reason(bid=D("0.26")) is None
    assert reason(bid=D("0.25")) is ExitReason.E2_STOP_LOSS


def test_e2_liquidity_needs_two_consecutive_scans() -> None:
    assert reason(ask_qty=0) is None  # first zero scan
    assert reason(replace(POS, prior_zero_ask_scans=1), ask_qty=0) is ExitReason.E2_LIQUIDITY
    assert reason(replace(POS, prior_zero_ask_scans=1), ask_qty=1) is None
    assert reason(replace(POS, prior_zero_ask_scans=1), ask_qty=None) is None


def test_e3_dte0_boundary() -> None:
    assert reason(at=time(14, 29)) is None
    assert reason(at=time(14, 30)) is ExitReason.E3_TIME_STOP


def test_e3_dte1_boundary_and_carry() -> None:
    assert reason(dte=1, at=time(14, 59)) is None
    assert reason(dte=1, at=time(15, 0)) is ExitReason.E3_TIME_STOP
    assert reason(dte=1, at=time(15, 0), bid=D("5.99")) is ExitReason.E3_TIME_STOP
    assert reason(dte=1, at=time(15, 0), bid=D("6")) is None  # 1.5x carry
    assert reason(dte=1, at=time(15, 0), bid=None) is ExitReason.E3_TIME_STOP


def test_e3_ignores_dte_beyond_one() -> None:
    assert reason(dte=2, at=time(15, 25)) is None


def test_priority_e1_before_e3_and_e2_before_e3() -> None:
    late = time(14, 45)
    assert reason(bid=D("20"), at=late) is ExitReason.E1_PROFIT_TARGET
    assert reason(bid=D("0.1"), at=late) is ExitReason.E2_STOP_LOSS
    both = replace(POS, prior_zero_ask_scans=1)
    assert reason(both, bid=D("20"), ask_qty=0) is ExitReason.E1_PROFIT_TARGET


def test_none_bid_skips_price_rules() -> None:
    assert reason(bid=None) is None


def test_decision_carries_price_and_realised_r() -> None:
    d = evaluate_exit(POS, tick(bid=D("20")), CFG)
    assert d is not None
    assert d.exit_price == D("20")
    assert d.realised_r == D("4")  # (20-4)/4
    d2 = evaluate_exit(POS, tick(bid=None, at=time(14, 30)), CFG)
    assert d2 is not None and d2.exit_price is None and d2.realised_r is None
