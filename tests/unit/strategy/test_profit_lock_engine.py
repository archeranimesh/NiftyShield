"""Tests for IC V2 ProfitLockEngine."""

from datetime import date
from decimal import Decimal

import pytest

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.strategy.ic_expiry_config_v2 import ProfitLockConfig
from src.strategy.profit_lock_engine import ProfitLockEngine, ProfitLockState


@pytest.fixture
def config():
    return ProfitLockConfig()


@pytest.fixture
def state():
    return ProfitLockState(
        profit_lock_zone=0,
        zone2_lock_executed=False,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal("0"),
        active_put_width_pts=500,
        active_call_width_pts=500,
        cycle_id="test",
    )


@pytest.fixture
def chain():
    # 24500 spot, let's create a chain with some strikes.
    strikes = {
        Decimal("24000"): OptionChainStrike(
            pe=OptionLeg(
                ltp=Decimal("10"),
                bid=Decimal("9"),
                ask=Decimal("11"),
                oi=1000,
                volume=1000,
                delta=Decimal("-0.10"),
                gamma=Decimal("0.001"),
                theta=Decimal("-1"),
                vega=Decimal("10"),
                iv=Decimal("15"),
                strike=Decimal("24000"),
            )
        ),
        Decimal("25000"): OptionChainStrike(
            ce=OptionLeg(
                ltp=Decimal("10"),
                bid=Decimal("9"),
                ask=Decimal("11"),
                oi=1000,
                volume=1000,
                delta=Decimal("0.10"),
                gamma=Decimal("0.001"),
                theta=Decimal("-1"),
                vega=Decimal("10"),
                iv=Decimal("15"),
                strike=Decimal("25000"),
            )
        ),
        Decimal("24200"): OptionChainStrike(
            pe=OptionLeg(
                ltp=Decimal("40"),
                bid=Decimal("39.5"),
                ask=Decimal("40.5"),
                oi=60000,
                volume=10000,
                delta=Decimal("-0.19"),
                gamma=Decimal("0.002"),
                theta=Decimal("-2"),
                vega=Decimal("12"),
                iv=Decimal("15"),
                strike=Decimal("24200"),
            )
        ),
        Decimal("24800"): OptionChainStrike(
            ce=OptionLeg(
                ltp=Decimal("40"),
                bid=Decimal("39.5"),
                ask=Decimal("40.5"),
                oi=60000,
                volume=10000,
                delta=Decimal("0.19"),
                gamma=Decimal("0.002"),
                theta=Decimal("-2"),
                vega=Decimal("12"),
                iv=Decimal("15"),
                strike=Decimal("24800"),
            )
        ),
    }
    return OptionChain(underlying_spot=Decimal("24500"), expiry=date(2026, 7, 30), strikes=strikes)


def test_zone_detection_none_below_25pct(config, state, chain):
    engine = ProfitLockEngine()
    decision = engine.evaluate(
        captured_fraction=Decimal("0.20"),
        entry_credit_pts=Decimal("200"),
        current_mark_pts=Decimal("160"),
        dte=15,
        expiry_type="monthly",
        vix=Decimal("12"),
        ivr=Decimal("0.30"),
        state=state,
        chain=chain,
        config=config,
        short_put_strike=Decimal("24300"),
        short_call_strike=Decimal("24700"),
    )
    assert decision.action == "NONE"
    assert decision.zone == 0


def test_zone1_log_only(config, state, chain):
    engine = ProfitLockEngine()
    decision = engine.evaluate(
        captured_fraction=Decimal("0.30"),
        entry_credit_pts=Decimal("200"),
        current_mark_pts=Decimal("140"),
        dte=15,
        expiry_type="monthly",
        vix=Decimal("12"),
        ivr=Decimal("0.30"),
        state=state,
        chain=chain,
        config=config,
        short_put_strike=Decimal("24300"),
        short_call_strike=Decimal("24700"),
    )
    assert decision.action == "ZONE1_LOG"
    assert decision.zone == 1


def test_zone2_formula_passes(config, state, chain):
    engine = ProfitLockEngine()
    state = ProfitLockState(
        profit_lock_zone=1,
        zone2_lock_executed=False,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal("0"),
        active_put_width_pts=300,  # old put wing = 24000
        active_call_width_pts=300,  # old call wing = 25000
        cycle_id="test",
    )
    decision = engine.evaluate(
        captured_fraction=Decimal("0.55"),
        entry_credit_pts=Decimal("260"),
        current_mark_pts=Decimal("117"),
        dte=15,
        expiry_type="monthly",
        vix=Decimal("12"),
        ivr=Decimal("0.30"),
        state=state,
        chain=chain,
        config=config,
        short_put_strike=Decimal("24300"),
        short_call_strike=Decimal("24700"),
    )
    assert decision.action == "ZONE2_LOCK"
    assert decision.zone == 2
    assert decision.formula_passes is True
    # new put ask = 40.5, new call ask = 40.5 -> total = 81
    # old put bid = 9, old call bid = 9 -> total = 18
    # D_lock = 81 - 18 = 63
    # W = 100
    # W + D_lock + K = 100 + 63 + 10 = 173
    # Wait! 173 <= 0.75 * 200 (which is 150) ? NO.
    # Ah, the formula in this test would fail because W+D_lock+K is 173 which is > 150.
    # Let's adjust entry_credit_pts to make it pass.
    # We need 173 <= 0.75 * C0 -> C0 >= 230.6


def test_zone2_formula_passes_correct_numbers(config, chain):
    engine = ProfitLockEngine()
    state = ProfitLockState(
        profit_lock_zone=1,
        zone2_lock_executed=False,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal("0"),
        active_put_width_pts=300,  # 24300 - 300 = 24000 (bid=9)
        active_call_width_pts=300,  # 24700 + 300 = 25000 (bid=9)
        cycle_id="test",
    )
    decision = engine.evaluate(
        captured_fraction=Decimal("0.55"),
        entry_credit_pts=Decimal("260"),  # 0.25 * 260 = 65, D_lock=63. 0.75 * 260 = 195
        current_mark_pts=Decimal("117"),
        dte=15,
        expiry_type="monthly",
        vix=Decimal("12"),
        ivr=Decimal("0.30"),
        state=state,
        chain=chain,
        config=config,
        short_put_strike=Decimal("24300"),  # new wing 24200 (ask=40.5) -> W=100
        short_call_strike=Decimal("24700"),  # new wing 24800 (ask=40.5) -> W=100
    )
    assert decision.action == "ZONE2_LOCK"
    assert decision.formula_passes is True
    assert decision.net_debit_pts == Decimal("63")  # 81 - 18


def test_zone2_formula_fails_close_full(config, chain):
    engine = ProfitLockEngine()
    state = ProfitLockState(
        profit_lock_zone=1,
        zone2_lock_executed=False,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal("0"),
        active_put_width_pts=300,
        active_call_width_pts=300,
        cycle_id="test",
    )
    # To avoid debit cap (63 <= 0.25 * C0 => C0 >= 252), we set C0=260.
    # To fail formula W + D_lock + K <= 0.75 * 260 = 195, W=100, D_lock=63, K=10 -> 173 <= 195 passes.
    # So we increase K or decrease C0 while keeping D_lock <= 25% of C0.
    # Max D_lock is 63. Let C0 = 252. Max D_lock = 63. 0.75 * 252 = 189.
    # W + D_lock + K = 100 + 63 + 10 = 173 <= 189 (passes).
    # Wait, we can just make W=120 by changing short_put_strike, but find_strike finds 24200.
    # Or just use an entry credit where formula fails but debit cap passes.
    # 100 + 63 + 10 = 173 > 0.75 * C0 => C0 < 230.6.
    # But debit cap needs C0 >= 252 (because D_lock is 63).
    # Since we can't easily fail the formula with these fixed legs without failing debit cap,
    # let's just mock config.floor_budget_zone2 = 0.50.
    # 0.50 * 260 = 130. 173 > 130 (fails). 63 <= 65 (debit cap passes).
    decision = engine.evaluate(
        captured_fraction=Decimal("0.55"),
        entry_credit_pts=Decimal("260"),
        current_mark_pts=Decimal("117"),
        dte=15,
        expiry_type="monthly",
        vix=Decimal("12"),
        ivr=Decimal("0.30"),
        state=state,
        chain=chain,
        config=ProfitLockConfig(floor_budget_zone2=Decimal("0.50")),
        short_put_strike=Decimal("24300"),
        short_call_strike=Decimal("24700"),
    )
    assert decision.action == "CLOSE_FULL"
    assert decision.skip_reason == "formula_failed"


def test_zone2_skips_if_already_executed(config, chain):
    engine = ProfitLockEngine()
    state = ProfitLockState(
        profit_lock_zone=2,
        zone2_lock_executed=True,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal("0"),
        active_put_width_pts=100,
        active_call_width_pts=100,
        cycle_id="test",
    )
    decision = engine.evaluate(
        captured_fraction=Decimal("0.60"),
        entry_credit_pts=Decimal("250"),
        current_mark_pts=Decimal("100"),
        dte=15,
        expiry_type="monthly",
        vix=Decimal("12"),
        ivr=Decimal("0.30"),
        state=state,
        chain=chain,
        config=config,
        short_put_strike=Decimal("24300"),
        short_call_strike=Decimal("24700"),
    )
    assert decision.action == "NONE"
    assert decision.skip_reason == "already_executed"


def test_zone2_dte_guard_blocks(config, chain):
    engine = ProfitLockEngine()
    state = ProfitLockState(
        profit_lock_zone=1,
        zone2_lock_executed=False,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal("0"),
        active_put_width_pts=300,
        active_call_width_pts=300,
        cycle_id="test",
    )
    decision = engine.evaluate(
        captured_fraction=Decimal("0.55"),
        entry_credit_pts=Decimal("250"),
        current_mark_pts=Decimal("112.5"),
        dte=6,  # monthly DTE=6 (<10)
        expiry_type="monthly",
        vix=Decimal("12"),
        ivr=Decimal("0.30"),
        state=state,
        chain=chain,
        config=config,
        short_put_strike=Decimal("24300"),
        short_call_strike=Decimal("24700"),
    )
    assert decision.action == "NONE"
    assert decision.skip_reason == "dte_guard"


def test_zone2_iv_guard_bypass_when_formula_has_buffer(config, chain):
    engine = ProfitLockEngine()
    state = ProfitLockState(
        profit_lock_zone=1,
        zone2_lock_executed=False,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal("0"),
        active_put_width_pts=300,
        active_call_width_pts=300,
        cycle_id="test",
    )
    decision = engine.evaluate(
        captured_fraction=Decimal("0.55"),
        entry_credit_pts=Decimal("300"),  # 0.75 * 300 = 225
        current_mark_pts=Decimal("135"),
        dte=15,
        expiry_type="monthly",
        vix=Decimal("9"),  # low VIX
        ivr=Decimal("0.10"),  # low IVR
        state=state,
        chain=chain,
        config=config,
        short_put_strike=Decimal("24300"),
        short_call_strike=Decimal("24700"),
    )
    # W + D_lock + K = 100 + 63 + max(10, 15) = 178
    # 178 <= 225, so passes buffered!
    assert decision.action == "ZONE2_LOCK"
    assert decision.formula_passes is True


def test_zone2_debit_cap_blocks(config, chain):
    engine = ProfitLockEngine()
    state = ProfitLockState(
        profit_lock_zone=1,
        zone2_lock_executed=False,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal("0"),
        active_put_width_pts=300,
        active_call_width_pts=300,
        cycle_id="test",
    )
    # We need D_lock > 25% of C0. D_lock is 63. So C0 < 252 (250).
    decision = engine.evaluate(
        captured_fraction=Decimal("0.55"),
        entry_credit_pts=Decimal("200"),  # 25% of 200 = 50. D_lock = 63.
        current_mark_pts=Decimal("90"),
        dte=15,
        expiry_type="monthly",
        vix=Decimal("12"),
        ivr=Decimal("0.30"),
        state=state,
        chain=chain,
        config=config,
        short_put_strike=Decimal("24300"),
        short_call_strike=Decimal("24700"),
    )
    assert decision.action == "CLOSE_FULL"
    assert decision.skip_reason == "debit_cap"


def test_zone2_width_below_100pts_prefers_close(config, chain):
    engine = ProfitLockEngine()
    state = ProfitLockState(
        profit_lock_zone=1,
        zone2_lock_executed=False,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal("0"),
        active_put_width_pts=250,  # 24250 - 250 = 24000
        active_call_width_pts=250,  # 24750 + 250 = 25000
        cycle_id="test",
    )
    # short strikes 24250 and 24750 would result in W=50 since new wings are 24200 and 24800
    decision = engine.evaluate(
        captured_fraction=Decimal("0.55"),
        entry_credit_pts=Decimal("300"),
        current_mark_pts=Decimal("112.5"),
        dte=15,
        expiry_type="monthly",
        vix=Decimal("12"),
        ivr=Decimal("0.30"),
        state=state,
        chain=chain,
        config=config,
        short_put_strike=Decimal("24250"),
        short_call_strike=Decimal("24750"),
    )
    assert decision.action == "CLOSE_FULL"
    assert decision.skip_reason == "required_width_too_small"


def test_formula_evaluation_exact(config):
    engine = ProfitLockEngine()
    # W=100, D_cum=0, D_lock=34, K=10, W+D_lock+K=144. C0=200, F=0.75 -> 150.
    assert (
        engine._evaluate_floor_formula(
            100,
            Decimal("0"),
            Decimal("34"),
            Decimal("10"),
            Decimal("200"),
            config.floor_budget_zone2,
        )
        is True
    )


def test_formula_evaluation_fails(config):
    engine = ProfitLockEngine()
    # W=120, D_cum=0, D_lock=40, K=10. W+D_lock+K=170. 170 > 150.
    assert (
        engine._evaluate_floor_formula(
            120,
            Decimal("0"),
            Decimal("40"),
            Decimal("10"),
            Decimal("200"),
            config.floor_budget_zone2,
        )
        is False
    )


def test_select_inward_wing_happy(config, chain):
    engine = ProfitLockEngine()
    # The chain has 24200 PE with delta -0.19, bid 39.5, ask 40.5
    leg = engine._select_inward_wing(chain, "put", Decimal("24300"), config)
    assert leg is not None
    assert leg.strike == Decimal("24200")


def test_select_inward_wing_no_candidate(config, chain):
    engine = ProfitLockEngine()
    # We will pass a config that requires delta between 0.30 and 0.40
    # No candidate should be found.
    strict_config = ProfitLockConfig(
        zone2_long_wing_delta_lo=Decimal("0.30"), zone2_long_wing_delta_hi=Decimal("0.40")
    )
    leg = engine._select_inward_wing(chain, "put", Decimal("24300"), strict_config)
    assert leg is None


def test_guaranteed_floor_fraction(config, chain):
    engine = ProfitLockEngine()
    state = ProfitLockState(
        profit_lock_zone=1,
        zone2_lock_executed=False,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal("0"),
        active_put_width_pts=300,
        active_call_width_pts=300,
        cycle_id="test",
    )
    decision = engine.evaluate(
        captured_fraction=Decimal("0.55"),
        entry_credit_pts=Decimal("260"),
        current_mark_pts=Decimal("117"),
        dte=15,
        expiry_type="monthly",
        vix=Decimal("12"),
        ivr=Decimal("0.30"),
        state=state,
        chain=chain,
        config=config,
        short_put_strike=Decimal("24300"),
        short_call_strike=Decimal("24700"),
    )
    # worst_pnl = 260 - 0 - 63 - 10 - 100 = 87
    # floor_fraction = 87 / 260
    assert decision.guaranteed_floor_fraction == Decimal("87") / Decimal("260")
