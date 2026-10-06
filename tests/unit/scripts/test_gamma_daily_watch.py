"""Unit tests for scripts/gamma_daily_watch.py."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from structlog.testing import capture_logs

from scripts.pipeline.gamma_daily_watch import (
    _fetch_and_snapshot,
    _fetch_chain,
    _run_calibration,
    _send_summary,
    _update_watchlist,
    main,
    resolve_expiries,
)
from src.client.exceptions import DataFetchError
from src.gamma.watchlist import WatchlistDecision, WatchlistRemoval
from src.models.options import OptionChain, OptionChainStrike, OptionLeg


@contextmanager
def _fake_runtime(dry_run: bool):
    """Stand-in for _runtime: no client, no DB."""
    yield MagicMock(), MagicMock(), MagicMock()


def test_resolve_expiries_mid_week() -> None:
    """On Monday, resolve_expiries returns this Tuesday and next Tuesday."""
    # 2026-04-20 is Monday; Nifty weekly expiry is Tuesday (SEBI, April 2026)
    # 2026-04-21 is Tuesday
    # 2026-04-28 is Tuesday
    today = date(2026, 4, 20)

    with patch("scripts.pipeline.gamma_daily_watch.is_trading_day", return_value=True):
        curr_exp, next_exp = resolve_expiries(today)
        assert curr_exp == date(2026, 4, 21)
        assert next_exp == date(2026, 4, 28)


def test_resolve_expiries_on_thursday_open() -> None:
    """On Tuesday when market is open, resolve_expiries returns today and next Tuesday."""
    # 2026-04-21 is Tuesday
    # 2026-04-28 is Tuesday
    today = date(2026, 4, 21)

    with patch("scripts.pipeline.gamma_daily_watch.is_trading_day", return_value=True):
        curr_exp, next_exp = resolve_expiries(today)
        assert curr_exp == date(2026, 4, 21)
        assert next_exp == date(2026, 4, 28)


def test_resolve_expiries_on_thursday_holiday() -> None:
    """On Tuesday when market is closed, resolve_expiries returns next Tuesday and the one after."""
    # 2026-04-07 is Tuesday (holiday)
    # 2026-04-14 is Tuesday
    # 2026-04-21 is Tuesday
    today = date(2026, 4, 7)

    def mock_is_trading_day(d: date) -> bool:
        if d == date(2026, 4, 7):
            return False
        return True

    with patch(
        "scripts.pipeline.gamma_daily_watch.is_trading_day", side_effect=mock_is_trading_day
    ):
        curr_exp, next_exp = resolve_expiries(today)
        assert curr_exp == date(2026, 4, 14)
        assert next_exp == date(2026, 4, 21)


def test_resolve_expiries_thursday_is_holiday_adjusted() -> None:
    """If Tuesday is a holiday, the expiry is adjusted to Monday (or preceding trading day)."""
    # 2026-04-07 is Tuesday (holiday)
    # 2026-04-06 is Monday (trading day)
    # today is 2026-04-06 (Monday)
    today = date(2026, 4, 6)

    def mock_is_trading_day(d: date) -> bool:
        if d == date(2026, 4, 7):
            return False
        return True

    with patch(
        "scripts.pipeline.gamma_daily_watch.is_trading_day", side_effect=mock_is_trading_day
    ):
        curr_exp, next_exp = resolve_expiries(today)
        assert curr_exp == date(2026, 4, 6)  # adjusted from Tuesday 7 to Monday 6
        assert next_exp == date(2026, 4, 14)


def test_resolve_expiries_friday_weekend() -> None:
    """On Wednesday or later, resolve_expiries returns next Tuesday and the Tuesday after."""
    # Friday 2026-04-24 -> current-week expiry is next Tuesday 2026-04-28
    # Next-week expiry is Tuesday after next 2026-05-05
    today_fri = date(2026, 4, 24)
    today_sat = date(2026, 4, 25)
    today_sun = date(2026, 4, 26)

    with patch("scripts.pipeline.gamma_daily_watch.is_trading_day", return_value=True):
        for today in [today_fri, today_sat, today_sun]:
            curr_exp, next_exp = resolve_expiries(today)
            assert curr_exp == date(2026, 4, 28)
            assert next_exp == date(2026, 5, 5)


def test_resolve_expiries_multi_day_holiday_rollback() -> None:
    """If Tuesday and Monday are holidays, expiry rolls back to Friday."""
    # Tuesday 2026-03-31 is holiday
    # Monday 2026-03-30 is holiday
    # Friday 2026-03-27 is open
    # today is 2026-03-30 (Monday)
    today = date(2026, 3, 30)

    def mock_is_trading_day(d: date) -> bool:
        if d.weekday() >= 5:  # Saturday / Sunday are never trading days
            return False
        if d in {date(2026, 3, 31), date(2026, 3, 30)}:
            return False
        return True

    with patch(
        "scripts.pipeline.gamma_daily_watch.is_trading_day", side_effect=mock_is_trading_day
    ):
        curr_exp, next_exp = resolve_expiries(today)
        assert curr_exp == date(2026, 3, 27)  # rolled back Tue→Mon(holiday)→Sun→Sat→Fri
        assert next_exp == date(2026, 4, 7)


def test_morning_flag_skips_watchlist() -> None:
    """If --morning is passed, _update_watchlist is not called."""
    test_args = ["gamma_daily_watch.py", "--morning"]

    with (
        patch.object(sys, "argv", test_args),
        patch("scripts.pipeline.gamma_daily_watch.is_trading_day", return_value=True),
        patch("scripts.pipeline.gamma_daily_watch._runtime", _fake_runtime),
    ):
        with patch(
            "scripts.pipeline.gamma_daily_watch._fetch_and_snapshot", return_value=[]
        ) as mock_fetch:
            with patch("scripts.pipeline.gamma_daily_watch._update_watchlist") as mock_update:
                main()
                mock_fetch.assert_called_once()
                mock_update.assert_not_called()


def test_dry_run_flag_propagates() -> None:
    """If --dry-run is passed, dry_run=True flows into _fetch_and_snapshot and _update_watchlist."""
    test_args = ["gamma_daily_watch.py", "--dry-run"]

    with (
        patch.object(sys, "argv", test_args),
        patch("scripts.pipeline.gamma_daily_watch.is_trading_day", return_value=True),
        patch("scripts.pipeline.gamma_daily_watch._runtime", _fake_runtime),
    ):
        with patch(
            "scripts.pipeline.gamma_daily_watch._fetch_and_snapshot", return_value=[]
        ) as mock_fetch:
            with (
                patch("scripts.pipeline.gamma_daily_watch._update_watchlist") as mock_update,
                patch("scripts.pipeline.gamma_daily_watch._run_calibration"),
                patch("scripts.pipeline.gamma_daily_watch._send_summary"),
            ):
                main()
                mock_fetch.assert_called_once()
                # Check dry_run=True was passed in kwargs
                assert mock_fetch.call_args[1]["dry_run"] is True
                mock_update.assert_called_once()
                assert mock_update.call_args[1]["dry_run"] is True


def test_date_override_option() -> None:
    """If --date is passed, it override today reference date."""
    test_args = ["gamma_daily_watch.py", "--date", "2026-05-15"]

    with (
        patch.object(sys, "argv", test_args),
        patch("scripts.pipeline.gamma_daily_watch.is_trading_day", return_value=True),
        patch("scripts.pipeline.gamma_daily_watch._runtime", _fake_runtime),
    ):
        with patch(
            "scripts.pipeline.gamma_daily_watch.resolve_expiries",
            return_value=(date(2026, 5, 21), date(2026, 5, 28)),
        ) as mock_resolve:
            with patch(
                "scripts.pipeline.gamma_daily_watch._fetch_and_snapshot", return_value=[]
            ) as mock_fetch:
                with (
                    patch("scripts.pipeline.gamma_daily_watch._update_watchlist"),
                    patch("scripts.pipeline.gamma_daily_watch._run_calibration"),
                    patch("scripts.pipeline.gamma_daily_watch._send_summary"),
                ):
                    main()
                    mock_resolve.assert_called_once_with(date(2026, 5, 15))
                    mock_fetch.assert_called_once()
                    assert mock_fetch.call_args[1]["today"] == date(2026, 5, 15)


_HOLIDAY = "2026-10-03"  # Saturday


def test_non_trading_day_real_run_exits_before_any_fetch() -> None:
    """BUG-072: a real run on a non-trading day makes no client/store call and returns."""
    with (
        patch.object(sys, "argv", ["gamma_daily_watch.py", "--date", _HOLIDAY]),
        patch("scripts.pipeline.gamma_daily_watch.is_trading_day", return_value=False),
        patch("scripts.pipeline.gamma_daily_watch._runtime") as mock_runtime,
        patch("scripts.pipeline.gamma_daily_watch.resolve_expiries") as mock_resolve,
        capture_logs() as logs,
    ):
        main()
    mock_runtime.assert_not_called()
    mock_resolve.assert_not_called()
    assert [e["log_level"] for e in logs if e["event"] == "gamma_daily_watch.non_trading_day"] == [
        "info"
    ]


def test_trading_day_real_run_is_unchanged() -> None:
    """BUG-072: on a trading day the fetch path runs and no non-trading-day event is logged."""
    with (
        patch.object(sys, "argv", ["gamma_daily_watch.py", "--date", "2026-05-15"]),
        patch("scripts.pipeline.gamma_daily_watch.is_trading_day", return_value=True),
        patch("scripts.pipeline.gamma_daily_watch._runtime", _fake_runtime),
        patch(
            "scripts.pipeline.gamma_daily_watch.resolve_expiries",
            return_value=(date(2026, 5, 19), date(2026, 5, 26)),
        ),
        patch("scripts.pipeline.gamma_daily_watch._fetch_and_snapshot", return_value=[]) as fetch,
        patch("scripts.pipeline.gamma_daily_watch._update_watchlist"),
        patch("scripts.pipeline.gamma_daily_watch._run_calibration"),
        patch("scripts.pipeline.gamma_daily_watch._send_summary"),
        capture_logs() as logs,
    ):
        main()
    fetch.assert_called_once()
    assert not [e for e in logs if e["event"] == "gamma_daily_watch.non_trading_day"]


def test_non_trading_day_dry_run_warns_and_continues() -> None:
    """BUG-072: --dry-run on a non-trading day logs a WARNING but still derives rows."""
    with (
        patch.object(sys, "argv", ["gamma_daily_watch.py", "--date", _HOLIDAY, "--dry-run"]),
        patch("scripts.pipeline.gamma_daily_watch.is_trading_day", return_value=False),
        patch("scripts.pipeline.gamma_daily_watch._runtime", _fake_runtime),
        patch(
            "scripts.pipeline.gamma_daily_watch.resolve_expiries",
            return_value=(date(2026, 10, 6), date(2026, 10, 13)),
        ),
        patch("scripts.pipeline.gamma_daily_watch._fetch_and_snapshot", return_value=[]) as fetch,
        patch("scripts.pipeline.gamma_daily_watch._update_watchlist"),
        patch("scripts.pipeline.gamma_daily_watch._run_calibration"),
        patch("scripts.pipeline.gamma_daily_watch._send_summary"),
        capture_logs() as logs,
    ):
        main()
    fetch.assert_called_once()
    assert [e["log_level"] for e in logs if e["event"] == "gamma_daily_watch.non_trading_day"] == [
        "warning"
    ]


def _chain_with_one_strike() -> OptionChain:
    leg = OptionLeg(
        ltp=Decimal("10"),
        bid=Decimal("9"),
        ask=Decimal("10"),
        oi=100,
        volume=5,
        delta=Decimal("0.5"),
        gamma=Decimal("0.001"),
        theta=None,
        vega=None,
        iv=None,
        strike=Decimal("25000"),
    )
    return OptionChain(
        underlying_spot=Decimal("25000"),
        expiry=date(2026, 4, 21),
        strikes={Decimal("25000"): OptionChainStrike(ce=leg, pe=leg)},
    )


def test_fetch_chain_empty_response() -> None:
    """An empty broker response returns None and logs a warning."""
    client = MagicMock()
    client.get_option_chain_sync.return_value = []

    with capture_logs() as logs:
        assert _fetch_chain(client, date(2026, 4, 21)) is None

    assert any(e["log_level"] == "warning" for e in logs)
    client.get_option_chain_sync.assert_called_once_with("NSE_INDEX|Nifty 50", "2026-04-21")


def test_fetch_and_snapshot_batches_prior_oi() -> None:
    """Prior OI is looked up once per expiry, not once per strike."""
    store = MagicMock()
    store.get_prior_oi.return_value = {(25000, "CE"): 80}
    expiries = (date(2026, 4, 21), date(2026, 4, 28))

    with patch(
        "scripts.pipeline.gamma_daily_watch._fetch_chain", return_value=_chain_with_one_strike()
    ):
        snaps = _fetch_and_snapshot(
            MagicMock(), expiries, date(2026, 4, 20), "09:20", store, MagicMock(), dry_run=False
        )

    assert store.get_prior_oi.call_count == 2
    assert len(snaps) == 4
    assert snaps[0].oi_change_1d == Decimal("0.25")


def test_fetch_and_snapshot_dry_run_skips_store() -> None:
    """dry_run derives rows without touching the store."""
    store = MagicMock()

    with patch(
        "scripts.pipeline.gamma_daily_watch._fetch_chain", return_value=_chain_with_one_strike()
    ):
        snaps = _fetch_and_snapshot(
            MagicMock(),
            (date(2026, 4, 21), date(2026, 4, 28)),
            date(2026, 4, 20),
            "09:20",
            store,
            MagicMock(),
            dry_run=True,
        )

    assert store.method_calls == []
    assert len(snaps) == 4 and snaps[0].oi_change_1d is None


def test_fetch_and_snapshot_skips_expiry_with_no_chain() -> None:
    """An expiry whose chain is None contributes no rows."""
    with patch("scripts.pipeline.gamma_daily_watch._fetch_chain", return_value=None):
        snaps = _fetch_and_snapshot(
            MagicMock(),
            (date(2026, 4, 21), date(2026, 4, 28)),
            date(2026, 4, 20),
            "09:20",
            MagicMock(),
            MagicMock(),
            dry_run=False,
        )

    assert snaps == []


def _three_strike_chain() -> OptionChain:
    chain = _chain_with_one_strike()
    leg = chain.strikes[Decimal("25000")].ce
    strikes = {Decimal(k): OptionChainStrike(ce=leg, pe=leg) for k in (24900, 25000, 25100)}
    return OptionChain(underlying_spot=chain.underlying_spot, expiry=chain.expiry, strikes=strikes)


def test_persistence_called_per_snapshot() -> None:
    """Each derived row is inserted once: 3 strikes x 2 option types = 6 calls."""
    store = MagicMock()
    store.get_prior_oi.return_value = {}
    conn = MagicMock()

    with patch(
        "scripts.pipeline.gamma_daily_watch._fetch_chain", return_value=_three_strike_chain()
    ):
        snaps = _fetch_and_snapshot(
            MagicMock(), (date(2026, 4, 21),), date(2026, 4, 20), "09:20", store, conn, False
        )

    assert len(snaps) == 6
    assert store.insert_chain_snapshot.call_count == 6
    store.insert_chain_snapshot.assert_any_call(conn, snaps[0])


def test_dry_run_skips_persistence() -> None:
    """dry_run never calls insert_chain_snapshot and logs the skipped count."""
    store = MagicMock()
    store.get_prior_oi.return_value = {}

    with patch(
        "scripts.pipeline.gamma_daily_watch._fetch_chain", return_value=_three_strike_chain()
    ):
        with capture_logs() as logs:
            _fetch_and_snapshot(
                MagicMock(),
                (date(2026, 4, 21),),
                date(2026, 4, 20),
                "09:20",
                store,
                MagicMock(),
                True,
            )

    store.insert_chain_snapshot.assert_not_called()
    assert any(e["event"] == "gamma_daily_watch.dry_run_skip" and e["rows"] == 6 for e in logs)


def test_single_expiry_failure_does_not_abort() -> None:
    """A DataFetchError on the first expiry is logged; the second is still processed."""
    store = MagicMock()
    store.get_prior_oi.return_value = {}
    effects = [DataFetchError("boom"), _chain_with_one_strike()]

    with patch("scripts.pipeline.gamma_daily_watch._fetch_chain", side_effect=effects):
        with capture_logs() as logs:
            snaps = _fetch_and_snapshot(
                MagicMock(),
                (date(2026, 4, 21), date(2026, 4, 28)),
                date(2026, 4, 20),
                "09:20",
                store,
                MagicMock(),
                dry_run=False,
            )

    assert len(snaps) == 2
    assert store.insert_chain_snapshot.call_count == 2
    assert any(e["log_level"] == "error" for e in logs)


def test_store_error_propagates() -> None:
    """A store write failure is not swallowed (connect() must roll back)."""
    store = MagicMock()
    store.get_prior_oi.return_value = {}
    store.insert_chain_snapshot.side_effect = sqlite3.OperationalError("disk")

    with patch(
        "scripts.pipeline.gamma_daily_watch._fetch_chain", return_value=_chain_with_one_strike()
    ):
        with pytest.raises(sqlite3.OperationalError):
            _fetch_and_snapshot(
                MagicMock(),
                (date(2026, 4, 21),),
                date(2026, 4, 20),
                "09:20",
                store,
                MagicMock(),
                False,
            )


def _wl_snap(expiry: date, strike: int = 25000) -> Any:
    snap = MagicMock()
    snap.expiry_date = expiry
    snap.strike = strike
    return snap


def _decision(**kwargs: Any) -> Any:
    base: dict[str, Any] = {"add": (), "retain": (), "remove": (), "elevate": ()}
    return WatchlistDecision(**{**base, **kwargs})


def test_update_watchlist_applies_decision_and_returns_stats() -> None:
    expiry, today = date(2026, 5, 26), date(2026, 5, 22)
    store, conn = MagicMock(), MagicMock()
    entry = MagicMock()
    removal = WatchlistRemoval(date(2026, 5, 19), 24900, "CE", "expired")
    decision = _decision(add=(entry,), retain=(entry,), remove=(removal,), elevate=(entry,))
    snaps = [_wl_snap(expiry), _wl_snap(date(2026, 6, 2))]
    with patch(
        "scripts.pipeline.gamma_daily_watch.evaluate_watchlist", return_value=decision
    ) as ev:
        stats = _update_watchlist(snaps, expiry, today, store, conn, dry_run=False)

    assert stats == {"added": 1, "retained": 1, "removed": 1, "elevated": 1}
    assert ev.call_args[0][0] == [snaps[0]]  # current-week expiry only
    assert store.upsert_watchlist.call_count == 2
    store.remove_from_watchlist.assert_called_once_with(
        conn, date(2026, 5, 19), 24900, "CE", "expired", today
    )
    store.get_prior_snapshots.assert_called_once_with(conn, expiry, today, 3)
    store.get_all_active_watchlist.assert_called_once_with(conn)


def test_dry_run_no_store_calls() -> None:
    store, conn = MagicMock(), MagicMock()
    removal = WatchlistRemoval(date(2026, 5, 19), 24900, "CE", "expired")
    decision = _decision(add=(MagicMock(),), remove=(removal,))
    with patch("scripts.pipeline.gamma_daily_watch.evaluate_watchlist", return_value=decision):
        stats = _update_watchlist(
            [], date(2026, 5, 26), date(2026, 5, 22), store, conn, dry_run=True
        )

    assert stats["added"] == 1 and stats["removed"] == 1
    store.upsert_watchlist.assert_not_called()
    store.remove_from_watchlist.assert_not_called()


def test_dry_run_tolerates_missing_tables_but_live_run_raises() -> None:
    store = MagicMock()
    store.get_prior_snapshots.side_effect = sqlite3.OperationalError("no such table")
    args = ([], date(2026, 5, 26), date(2026, 5, 22), store, MagicMock())

    assert _update_watchlist(*args, dry_run=True) == {
        "added": 0,
        "retained": 0,
        "removed": 0,
        "elevated": 0,
    }
    with pytest.raises(sqlite3.OperationalError):
        _update_watchlist(*args, dry_run=False)


# --- B2.5: calibration + Telegram ---

_TODAY = date(2026, 6, 10)
_STATS = {"added": 2, "retained": 3, "removed": 1, "elevated": 1}


def _cal_snap(iv: str | None = "0.15", gearing: str | None = "5", dte: int = 2) -> Any:
    snap = MagicMock()
    snap.strike, snap.option_type, snap.dte_calendar = 25000, "CE", dte
    snap.iv_val = Decimal(iv) if iv else None
    snap.gamma_gearing = Decimal(gearing) if gearing else None
    snap.snapshot_date, snap.snapshot_time, snap.expiry_date = _TODAY, "15:20", date(2026, 6, 16)
    return snap


def _cal_store(iv_days: int = 20, gearing_days: int = 20) -> MagicMock:
    store = MagicMock()
    store.get_iv_history.return_value = [Decimal(n) / 100 for n in range(1, iv_days + 1)]
    store.count_prior_gearing_days.return_value = gearing_days
    store.get_gearing_by_dte.return_value = [Decimal(n) for n in range(1, 11)]
    return store


def test_calibration_skipped_insufficient_history() -> None:
    store = _cal_store(iv_days=15, gearing_days=15)
    with capture_logs() as logs:
        _run_calibration([_cal_snap()], _TODAY, store, MagicMock(), dry_run=False)

    store.update_percentiles.assert_not_called()
    store.get_gearing_by_dte.assert_not_called()
    assert any(e["log_level"] == "warning" and e.get("days") == 15 for e in logs)


def test_calibration_writes_percentile() -> None:
    store = _cal_store()
    conn = MagicMock()
    _run_calibration([_cal_snap(iv="0.15", gearing="5")], _TODAY, store, conn, dry_run=False)

    store.get_iv_history.assert_called_once_with(conn, 25000, "CE", limit_days=20, before=_TODAY)
    kwargs = store.update_percentiles.call_args.kwargs
    assert kwargs["iv_pctile"] == Decimal("0.7500")  # 15 of 20 values <= 0.15
    assert kwargs["gearing_pctile"] == Decimal("0.5000")  # 5 of 10 values <= 5
    assert kwargs["strike"] == 25000 and kwargs["snapshot_time"] == "15:20"


def test_calibration_dry_run() -> None:
    store = _cal_store()
    _run_calibration([_cal_snap()], _TODAY, store, MagicMock(), dry_run=True)

    store.get_iv_history.assert_called_once()  # reads are allowed (D9)
    store.update_percentiles.assert_not_called()


def test_calibration_dry_run_tolerates_missing_tables_but_live_run_raises() -> None:
    store = _cal_store()
    store.get_iv_history.side_effect = sqlite3.OperationalError("no such table")
    _run_calibration([_cal_snap()], _TODAY, store, MagicMock(), dry_run=True)
    with pytest.raises(sqlite3.OperationalError):
        _run_calibration([_cal_snap()], _TODAY, store, MagicMock(), dry_run=False)


def test_calibration_gate_counts_days_not_rows() -> None:
    """25 gearing rows over 10 distinct days must not pass the 20-day gate (D5)."""
    store = _cal_store(iv_days=10, gearing_days=10)
    store.get_gearing_by_dte.return_value = [Decimal(n) for n in range(25)]
    _run_calibration([_cal_snap()], _TODAY, store, MagicMock(), dry_run=False)

    store.get_gearing_by_dte.assert_not_called()
    store.update_percentiles.assert_not_called()


def test_calibration_skips_snapshot_without_values() -> None:
    store = _cal_store()
    _run_calibration([_cal_snap(iv=None, gearing=None)], _TODAY, store, MagicMock(), False)

    store.get_iv_history.assert_not_called()
    store.update_percentiles.assert_not_called()


def test_telegram_summary_sent() -> None:
    notifier = MagicMock()
    notifier.send = AsyncMock(return_value=True)
    with patch("scripts.pipeline.gamma_daily_watch.build_notifier", return_value=notifier):
        _send_summary(120, _STATS)

    notifier.send.assert_awaited_once_with(
        "Gamma watch: 120 strikes captured, 5 on watchlist, 1 elevated, 2 added, 1 removed"
    )


def test_telegram_no_notifier_skips_silently() -> None:
    with patch("scripts.pipeline.gamma_daily_watch.build_notifier", return_value=None):
        _send_summary(1, _STATS)  # must not raise


def test_telegram_failure_non_fatal() -> None:
    notifier = MagicMock()
    notifier.send = AsyncMock(side_effect=RuntimeError("boom"))
    with (
        patch("scripts.pipeline.gamma_daily_watch.build_notifier", return_value=notifier),
        capture_logs() as logs,
    ):
        _send_summary(1, _STATS)

    assert any(e["log_level"] == "warning" and "boom" in e["error"] for e in logs)


def _run_main(argv: list[str], calls: list[str]) -> dict[str, MagicMock]:
    mocks: dict[str, MagicMock] = {}
    names = {
        "_fetch_and_snapshot": [],
        "_update_watchlist": _STATS,
        "_run_calibration": None,
        "_send_summary": None,
    }
    with (
        patch.object(sys, "argv", argv),
        patch("scripts.pipeline.gamma_daily_watch._runtime", _fake_runtime),
        patch("scripts.pipeline.gamma_daily_watch.is_trading_day", return_value=True),
    ):
        patchers = {
            n: patch(f"scripts.pipeline.gamma_daily_watch.{n}", return_value=r)
            for n, r in names.items()
        }
        for n, p in patchers.items():
            mocks[n] = p.start()
            mocks[n].side_effect = lambda *a, _n=n, **k: (calls.append(_n), names[_n])[1]
        try:
            main()
        finally:
            for p in patchers.values():
                p.stop()
    return mocks


def test_morning_flag_skips_calibration_and_telegram() -> None:
    calls: list[str] = []
    mocks = _run_main(["gamma_daily_watch.py", "--morning"], calls)

    assert calls == ["_fetch_and_snapshot"]
    mocks["_run_calibration"].assert_not_called()
    mocks["_send_summary"].assert_not_called()


def test_dry_run_skips_telegram_but_calibrates() -> None:
    calls: list[str] = []
    mocks = _run_main(["gamma_daily_watch.py", "--dry-run"], calls)

    assert mocks["_run_calibration"].call_args[0][-1] is True
    mocks["_send_summary"].assert_not_called()


def test_full_pipeline_integration() -> None:
    calls: list[str] = []
    mocks = _run_main(["gamma_daily_watch.py"], calls)

    assert calls == [
        "_fetch_and_snapshot",
        "_update_watchlist",
        "_run_calibration",
        "_send_summary",
    ]
    assert mocks["_send_summary"].call_args[0] == (0, _STATS)  # captured=len(snaps), D8


def test_import_loads_dotenv_for_cron(tmp_path: Path) -> None:
    """Importing the script pulls .env into the env — cron exports no UPSTOX_ENV."""
    import os
    import subprocess

    token = "dummy-token"  # pragma: allowlist secret
    (tmp_path / ".env").write_text(f"UPSTOX_ENV=prod\nUPSTOX_ANALYTICS_TOKEN={token}\n")
    root = Path(__file__).resolve().parents[3]
    env = {k: v for k, v in os.environ.items() if not k.startswith("UPSTOX_")}
    env["PYTHONPATH"] = str(root)
    code = (
        "import scripts.pipeline.gamma_daily_watch as m; print(m.settings.upstox_analytics_token)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.stdout.strip() == token, out.stderr
