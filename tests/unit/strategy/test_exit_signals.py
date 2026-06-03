from src.strategy.exit_signals import ExitSignalEngine


def test_evaluate_csp_profit_target():
    # profit target: mark <= 50% of entry credit
    results = ExitSignalEngine.evaluate_csp(
        entry_price=20.0, current_mark=9.8, delta=-0.20, days_held=10, dte=20
    )
    assert len(results) == 1
    assert results[0].exit_signal == "PROFIT_TARGET"
    assert results[0].severity == "ACTION"

    results = ExitSignalEngine.evaluate_csp(
        entry_price=20.0, current_mark=10.2, delta=-0.20, days_held=10, dte=20
    )
    assert not any(r.exit_signal == "PROFIT_TARGET" for r in results)


def test_evaluate_csp_loss_stop():
    # loss stop: mark >= 1.75x entry credit
    results = ExitSignalEngine.evaluate_csp(
        entry_price=20.0, current_mark=35.2, delta=-0.20, days_held=10, dte=20
    )
    assert len(results) == 1
    assert results[0].exit_signal == "LOSS_STOP"
    assert results[0].severity == "ACTION"
    assert results[0].premium_stop_would_fire is True

    results = ExitSignalEngine.evaluate_csp(
        entry_price=20.0, current_mark=34.8, delta=-0.20, days_held=10, dte=20
    )
    assert not any(r.exit_signal == "LOSS_STOP" for r in results)


def test_evaluate_csp_delta_stop_and_warn():
    # delta stop: |delta| >= 0.45
    results = ExitSignalEngine.evaluate_csp(
        entry_price=20.0, current_mark=22.0, delta=-0.46, days_held=10, dte=20
    )
    assert len(results) == 1
    assert results[0].exit_signal == "DELTA_STOP"
    assert results[0].severity == "ACTION"
    assert results[0].delta_stop_would_fire is True

    # delta warn: |delta| >= 0.35
    results = ExitSignalEngine.evaluate_csp(
        entry_price=20.0, current_mark=22.0, delta=-0.36, days_held=10, dte=20
    )
    assert len(results) == 1
    assert results[0].exit_signal == "DELTA_WARN"
    assert results[0].severity == "WARN"
    assert results[0].delta_stop_would_fire is False


def test_evaluate_csp_time_stop():
    # time stop: days_held >= 21
    results = ExitSignalEngine.evaluate_csp(
        entry_price=20.0, current_mark=15.0, delta=-0.20, days_held=21, dte=20
    )
    assert len(results) == 1
    assert results[0].exit_signal == "TIME_STOP"
    assert results[0].severity == "ACTION"

    results = ExitSignalEngine.evaluate_csp(
        entry_price=20.0, current_mark=15.0, delta=-0.20, days_held=20, dte=20
    )
    assert not any(r.exit_signal == "TIME_STOP" for r in results)


def test_evaluate_csp_dte_review():
    # dte review: dte <= 5
    results = ExitSignalEngine.evaluate_csp(
        entry_price=20.0, current_mark=15.0, delta=-0.20, days_held=10, dte=4
    )
    assert len(results) == 1
    assert results[0].exit_signal == "DTE_REVIEW"
    assert results[0].severity == "INFO"


def test_evaluate_csp_healthy():
    results = ExitSignalEngine.evaluate_csp(
        entry_price=20.0, current_mark=12.0, delta=-0.20, days_held=10, dte=15
    )
    assert results == []


def test_evaluate_csp_dual_signals():
    results = ExitSignalEngine.evaluate_csp(
        entry_price=20.0, current_mark=36.0, delta=-0.46, days_held=10, dte=15
    )
    # both DELTA_STOP and LOSS_STOP should fire, sorted by ACTION first (both are ACTION, so order is ok)
    signals = {r.exit_signal for r in results}
    assert "DELTA_STOP" in signals
    assert "LOSS_STOP" in signals
    for r in results:
        assert r.delta_stop_would_fire is True
        assert r.premium_stop_would_fire is True
        assert r.actual_rule_used == "BOTH"


def test_evaluate_csp_delta_none():
    results = ExitSignalEngine.evaluate_csp(
        entry_price=20.0, current_mark=36.0, delta=None, days_held=10, dte=15
    )
    assert len(results) == 1
    assert results[0].exit_signal == "LOSS_STOP"
    assert results[0].delta_stop_would_fire is False
    assert results[0].premium_stop_would_fire is True
    assert results[0].actual_rule_used == "PREMIUM"


def test_evaluate_cc_below_floor():
    # entry credit < 12 -> BELOW_FLOOR, PROFIT_TARGET doesn't fire
    results = ExitSignalEngine.evaluate_cc(
        entry_price=10.0,
        current_mark=4.0,
        delta=0.15,
        dte=15,
        underlying_price=22000.0,
        strike_price=22500.0,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "BELOW_FLOOR"
    assert results[0].severity == "INFO"


def test_evaluate_cc_profit_target():
    results = ExitSignalEngine.evaluate_cc(
        entry_price=15.0,
        current_mark=7.0,
        delta=0.15,
        dte=15,
        underlying_price=22000.0,
        strike_price=22500.0,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "PROFIT_TARGET"
    assert results[0].severity == "ACTION"


def test_evaluate_cc_loss_stop():
    results = ExitSignalEngine.evaluate_cc(
        entry_price=15.0,
        current_mark=38.0,
        delta=0.40,
        dte=15,
        underlying_price=22000.0,
        strike_price=22500.0,
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
        underlying_price=22000.0,
        strike_price=22500.0,
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
        underlying_price=22000.0,
        strike_price=22500.0,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "DELTA_WARN"
    assert results[0].severity == "WARN"


def test_evaluate_cc_dte_forced():
    # DTE <= 5 and call ITM
    results = ExitSignalEngine.evaluate_cc(
        entry_price=15.0,
        current_mark=8.0,
        delta=0.25,
        dte=4,
        underlying_price=22600.0,
        strike_price=22500.0,
    )
    assert len(results) == 1
    assert results[0].exit_signal == "DTE_FORCED"
    assert results[0].severity == "ACTION"

    # DTE <= 5 and not ITM, delta/residual low -> no DTE_FORCED
    results = ExitSignalEngine.evaluate_cc(
        entry_price=15.0,
        current_mark=3.0,
        delta=0.10,
        dte=4,
        underlying_price=22400.0,
        strike_price=22500.0,
    )
    assert not any(r.exit_signal == "DTE_FORCED" for r in results)


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
