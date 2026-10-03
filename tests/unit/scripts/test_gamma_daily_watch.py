"""Unit tests for scripts/gamma_daily_watch.py."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from structlog.testing import capture_logs

from scripts.pipeline.gamma_daily_watch import (
    _fetch_and_snapshot,
    _fetch_chain,
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
        patch("scripts.pipeline.gamma_daily_watch._runtime", _fake_runtime),
    ):
        with patch(
            "scripts.pipeline.gamma_daily_watch._fetch_and_snapshot", return_value=[]
        ) as mock_fetch:
            with patch("scripts.pipeline.gamma_daily_watch._update_watchlist") as mock_update:
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
        patch("scripts.pipeline.gamma_daily_watch._runtime", _fake_runtime),
    ):
        with patch(
            "scripts.pipeline.gamma_daily_watch.resolve_expiries",
            return_value=(date(2026, 5, 21), date(2026, 5, 28)),
        ) as mock_resolve:
            with patch(
                "scripts.pipeline.gamma_daily_watch._fetch_and_snapshot", return_value=[]
            ) as mock_fetch:
                with patch("scripts.pipeline.gamma_daily_watch._update_watchlist"):
                    main()
                    mock_resolve.assert_called_once_with(date(2026, 5, 15))
                    mock_fetch.assert_called_once()
                    assert mock_fetch.call_args[1]["today"] == date(2026, 5, 15)


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
