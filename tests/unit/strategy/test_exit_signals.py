from decimal import Decimal

from src.paper.models import TradeState
from src.strategy.exit_signals import ExitSignalEngine

# evaluate_csp was removed in CR1b and replaced with five independent classmethods.
# New CSP evaluator tests are at the bottom of this file (CR1b section).


def test_evaluate_cc_below_floor():
    # entry credit < 12 -> BELOW_FLOOR, PROFIT_TARGET doesn't fire
    results = ExitSignalEngine.evaluate_cc(
        entry_price=10.0,
        current_mark=4.0,
        delta=0.15,
        dte=15,
        days_held=5,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "BELOW_FLOOR"
    assert results[0].severity == "INFO"


def test_evaluate_cc_profit_target():
    # entry=20.0, mark=5.9, days_held=5, dte=20 -> fires (5.9 <= 20 * 0.30 = 6.0)
    results = ExitSignalEngine.evaluate_cc(
        entry_price=20.0,
        current_mark=5.9,
        delta=0.15,
        dte=20,
        days_held=5,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "PROFIT_TARGET"
    assert results[0].severity == "ACTION"

    # entry=20.0, mark=6.1, days_held=5, dte=20 -> [] (6.1 > 6.0)
    results = ExitSignalEngine.evaluate_cc(
        entry_price=20.0,
        current_mark=6.1,
        delta=0.15,
        dte=20,
        days_held=5,
    )
    assert results == []

    # entry=14.0, mark=3.0, days_held=5, dte=20 -> [] (entry < _CC_MIN_ENTRY_CREDIT of 15)
    results = ExitSignalEngine.evaluate_cc(
        entry_price=14.0,
        current_mark=3.0,
        delta=0.15,
        dte=20,
        days_held=5,
    )
    assert results == []

    # entry=15.0, mark=4.5, days_held=5, dte=20 -> fires (boundary inclusive)
    results = ExitSignalEngine.evaluate_cc(
        entry_price=15.0,
        current_mark=4.5,
        delta=0.15,
        dte=20,
        days_held=5,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "PROFIT_TARGET"


def test_evaluate_cc_loss_stop():
    results = ExitSignalEngine.evaluate_cc(
        entry_price=15.0,
        current_mark=38.0,
        delta=0.40,
        dte=15,
        days_held=5,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "LOSS_STOP"
    assert results[0].severity == "ACTION"


def test_evaluate_cc_delta_stop_and_warn():
    # delta >= 0.55 -> DELTA_STOP
    results = ExitSignalEngine.evaluate_cc(
        entry_price=15.0,
        current_mark=20.0,
        delta=0.56,
        dte=15,
        days_held=5,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "DELTA_STOP"
    assert results[0].severity == "ACTION"

    # delta >= 0.45 -> DELTA_WARN
    results = ExitSignalEngine.evaluate_cc(
        entry_price=15.0,
        current_mark=20.0,
        delta=0.46,
        dte=15,
        days_held=5,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "DELTA_WARN"
    assert results[0].severity == "WARN"

    # DELTA_WARN suppressed when DELTA_STOP fires (elif coupling)
    # delta=0.60, entry=20.0, mark=15.0, days_held=5, dte=20 -> [DELTA_STOP] only
    results = ExitSignalEngine.evaluate_cc(
        entry_price=20.0,
        current_mark=15.0,
        delta=0.60,
        dte=20,
        days_held=5,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "DELTA_STOP"

    # delta=0.47, entry=20.0, mark=15.0, days_held=5, dte=20 -> [DELTA_WARN] only
    results = ExitSignalEngine.evaluate_cc(
        entry_price=20.0,
        current_mark=15.0,
        delta=0.47,
        dte=20,
        days_held=5,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "DELTA_WARN"


def test_evaluate_cc_time_stop():
    # entry=20.0, mark=15.0, days_held=21, dte=20 -> TIME_STOP ACTION
    results = ExitSignalEngine.evaluate_cc(
        entry_price=20.0,
        current_mark=15.0,
        delta=0.20,
        dte=20,
        days_held=21,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "TIME_STOP"
    assert results[0].severity == "ACTION"

    # days_held=20 -> []
    results = ExitSignalEngine.evaluate_cc(
        entry_price=20.0,
        current_mark=15.0,
        delta=0.20,
        dte=20,
        days_held=20,
    )
    assert results == []

    # days_held=21, dte=4 -> both TIME_STOP and DTE_REVIEW fire
    results = ExitSignalEngine.evaluate_cc(
        entry_price=20.0,
        current_mark=15.0,
        delta=0.20,
        dte=4,
        days_held=21,
    )
    signals = {r.exit_signal for r in results}
    assert "TIME_STOP" in signals
    assert "DTE_REVIEW" in signals


def test_evaluate_cc_dte_review():
    # dte=5 -> DTE_REVIEW WARN
    results = ExitSignalEngine.evaluate_cc(
        entry_price=20.0,
        current_mark=15.0,
        delta=0.20,
        dte=5,
        days_held=5,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "DTE_REVIEW"
    assert results[0].severity == "WARN"

    # dte=6 -> []
    results = ExitSignalEngine.evaluate_cc(
        entry_price=20.0,
        current_mark=15.0,
        delta=0.20,
        dte=6,
        days_held=5,
    )
    assert results == []

    # dte=4, delta=0.70 -> DTE_REVIEW WARN, DELTA_STOP fires (fires separately)
    results = ExitSignalEngine.evaluate_cc(
        entry_price=20.0,
        current_mark=15.0,
        delta=0.70,
        dte=4,
        days_held=5,
    )
    signals = {r.exit_signal for r in results}
    assert "DTE_REVIEW" in signals
    assert "DELTA_STOP" in signals
    assert "DTE_FORCED" not in signals


def test_evaluate_cc_sort_order():
    # LOSS_STOP + DELTA_STOP both true -> ACTION first, sort order verified
    results = ExitSignalEngine.evaluate_cc(
        entry_price=20.0,
        current_mark=51.0,  # > 2.5x
        delta=0.60,
        dte=15,
        days_held=5,
    )
    signals = [r.exit_signal for r in results]
    assert "LOSS_STOP" in signals
    assert "DELTA_STOP" in signals


def test_evaluate_pp_crash_monetize():
    # delta <= -0.80 and spread <= 10%
    results = ExitSignalEngine.evaluate_pp(
        entry_price=50.0, current_mark=250.0, delta=-0.81, dte=15, bid=245.0, ask=255.0
    )
    assert len(results) == 1
    assert results[0].exit_signal == "CRASH_MONETIZE"
    assert results[0].severity == "ACTION"

    # value >= 5x entry and spread <= 10%
    results = ExitSignalEngine.evaluate_pp(
        entry_price=50.0, current_mark=251.0, delta=-0.75, dte=15, bid=248.0, ask=254.0
    )
    assert len(results) == 1
    assert results[0].exit_signal == "CRASH_MONETIZE"

    # value >= 5x but spread > 10% -> no CRASH_MONETIZE
    results = ExitSignalEngine.evaluate_pp(
        entry_price=50.0, current_mark=251.0, delta=-0.75, dte=15, bid=220.0, ask=280.0
    )
    assert results == []

    # bid/ask unavailable -> no CRASH_MONETIZE
    results = ExitSignalEngine.evaluate_pp(
        entry_price=50.0, current_mark=251.0, delta=-0.81, dte=15, bid=None, ask=None
    )
    assert results == []


def test_evaluate_pp_dte_review():
    results = ExitSignalEngine.evaluate_pp(
        entry_price=50.0, current_mark=40.0, delta=-0.30, dte=4, bid=None, ask=None
    )
    assert len(results) == 1
    assert results[0].exit_signal == "DTE_REVIEW"
    assert results[0].severity == "INFO"


def test_evaluate_pp_healthy():
    results = ExitSignalEngine.evaluate_pp(
        entry_price=50.0, current_mark=60.0, delta=-0.15, dte=20, bid=58.0, ask=62.0
    )
    assert results == []


def test_evaluate_collar_call_decay():
    # mark <= 25% of entry credit and DTE > 7
    results = ExitSignalEngine.evaluate_collar_call(
        entry_price=20.0,
        current_mark=4.8,
        delta=0.10,
        dte=15,
        underlying_price=22000.0,
        strike_price=22500.0,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "COLLAR_CALL_DECAY"
    assert results[0].severity == "ACTION"

    # residual <= 3 and DTE > 7
    results = ExitSignalEngine.evaluate_collar_call(
        entry_price=20.0,
        current_mark=2.9,
        delta=0.08,
        dte=15,
        underlying_price=22000.0,
        strike_price=22500.0,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "COLLAR_CALL_DECAY"

    # mark at 26% -> no decay signal
    results = ExitSignalEngine.evaluate_collar_call(
        entry_price=20.0,
        current_mark=5.2,
        delta=0.10,
        dte=15,
        underlying_price=22000.0,
        strike_price=22500.0,
    )
    assert results == []


def test_evaluate_collar_call_warn():
    # delta >= 0.55 -> COLLAR_CALL_WARN (WARN, not ACTION)
    results = ExitSignalEngine.evaluate_collar_call(
        entry_price=20.0,
        current_mark=25.0,
        delta=0.56,
        dte=15,
        underlying_price=22000.0,
        strike_price=22500.0,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "COLLAR_CALL_WARN"
    assert results[0].severity == "WARN"


def test_evaluate_collar_call_dte_forced():
    # DTE <= 5 and call ITM
    results = ExitSignalEngine.evaluate_collar_call(
        entry_price=20.0,
        current_mark=15.0,
        delta=0.35,
        dte=4,
        underlying_price=22600.0,
        strike_price=22500.0,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "DTE_FORCED"
    assert results[0].severity == "ACTION"


def test_evaluate_collar_call_healthy():
    results = ExitSignalEngine.evaluate_collar_call(
        entry_price=20.0,
        current_mark=12.0,
        delta=0.25,
        dte=20,
        underlying_price=22000.0,
        strike_price=22500.0,
    )
    assert results == []


# ── CR1b: five independent CSP evaluators ─────────────────────────────────────

# evaluate_profit_target_csp


def test_evaluate_profit_target_csp_fires_at_70_percent_captured():
    # 47 < 158.6 * 0.30 = 47.58 → fires
    results = ExitSignalEngine.evaluate_profit_target_csp(
        ltp=Decimal("47"), entry_credit=Decimal("158.6")
    )
    assert len(results) == 1
    assert results[0].exit_signal == "PROFIT_TARGET"
    assert results[0].severity == "ACTION"


def test_evaluate_profit_target_csp_no_fire_above_threshold():
    # 48 > 47.58 → does not fire
    results = ExitSignalEngine.evaluate_profit_target_csp(
        ltp=Decimal("48"), entry_credit=Decimal("158.6")
    )
    assert results == []


def test_evaluate_profit_target_csp_zero_ltp_fires():
    results = ExitSignalEngine.evaluate_profit_target_csp(
        ltp=Decimal("0"), entry_credit=Decimal("100")
    )
    assert len(results) == 1
    assert results[0].exit_signal == "PROFIT_TARGET"


def test_evaluate_profit_target_csp_at_exact_threshold_fires():
    # ltp == entry_credit * 0.30 → boundary inclusive (≤)
    results = ExitSignalEngine.evaluate_profit_target_csp(
        ltp=Decimal("30"), entry_credit=Decimal("100")
    )
    assert len(results) == 1


# evaluate_hard_stop_csp


def test_evaluate_hard_stop_csp_fires_at_2x():
    # 320 >= 158.6 * 2 = 317.2 → fires
    results = ExitSignalEngine.evaluate_hard_stop_csp(
        ltp=Decimal("320"), entry_credit=Decimal("158.6")
    )
    assert len(results) == 1
    assert results[0].exit_signal == "HARD_STOP"
    assert results[0].severity == "ACTION"


def test_evaluate_hard_stop_csp_no_fire_below_2x():
    # 316 < 317.2 → does not fire
    results = ExitSignalEngine.evaluate_hard_stop_csp(
        ltp=Decimal("316"), entry_credit=Decimal("158.6")
    )
    assert results == []


# evaluate_delta_breach_csp


def test_evaluate_delta_breach_csp_open_state_fires_delta_breach():
    results = ExitSignalEngine.evaluate_delta_breach_csp(delta=-0.41, state=TradeState.OPEN)
    assert len(results) == 1
    assert results[0].exit_signal == "DELTA_BREACH"
    assert results[0].severity == "ACTION"


def test_evaluate_delta_breach_csp_defended_state_fires_delta_breach_final():
    results = ExitSignalEngine.evaluate_delta_breach_csp(delta=-0.41, state=TradeState.DEFENDED)
    assert len(results) == 1
    assert results[0].exit_signal == "DELTA_BREACH_FINAL"
    assert results[0].severity == "ACTION"


def test_evaluate_delta_breach_csp_no_fire_below_threshold():
    results = ExitSignalEngine.evaluate_delta_breach_csp(delta=-0.39, state=TradeState.OPEN)
    assert results == []


def test_evaluate_delta_breach_csp_boundary_inclusive():
    # |delta| == 0.40 → fires
    results = ExitSignalEngine.evaluate_delta_breach_csp(delta=-0.40, state=TradeState.OPEN)
    assert len(results) == 1
    assert results[0].exit_signal == "DELTA_BREACH"


def test_evaluate_delta_breach_csp_defended_below_threshold_no_fire():
    # DEFENDED state but |delta| < 0.40 → no signal
    results = ExitSignalEngine.evaluate_delta_breach_csp(delta=-0.39, state=TradeState.DEFENDED)
    assert results == []


def test_evaluate_delta_breach_csp_re_entry_pending_raises():
    import pytest

    with pytest.raises(ValueError, match="RE_ENTRY_PENDING"):
        ExitSignalEngine.evaluate_delta_breach_csp(delta=-0.50, state=TradeState.RE_ENTRY_PENDING)


# evaluate_time_stop_csp


def test_evaluate_time_stop_csp_fires_at_21():
    results = ExitSignalEngine.evaluate_time_stop_csp(days_held=21)
    assert len(results) == 1
    assert results[0].exit_signal == "TIME_STOP"
    assert results[0].severity == "ACTION"


def test_evaluate_time_stop_csp_no_fire_at_20():
    results = ExitSignalEngine.evaluate_time_stop_csp(days_held=20)
    assert results == []


# evaluate_roll_eligible_csp


def test_evaluate_roll_eligible_csp_fires_at_7():
    results = ExitSignalEngine.evaluate_roll_eligible_csp(dte=7)
    assert len(results) == 1
    assert results[0].exit_signal == "ROLL_ELIGIBLE"
    assert results[0].severity == "ACTION"


def test_evaluate_roll_eligible_csp_no_fire_at_8():
    results = ExitSignalEngine.evaluate_roll_eligible_csp(dte=8)
    assert results == []


def test_evaluate_roll_eligible_csp_fires_at_expiry_day():
    results = ExitSignalEngine.evaluate_roll_eligible_csp(dte=0)
    assert len(results) == 1
    assert results[0].exit_signal == "ROLL_ELIGIBLE"
