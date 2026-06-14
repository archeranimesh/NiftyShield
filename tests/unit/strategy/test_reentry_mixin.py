import asyncio
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.backtest.vix_ingest import load_vix_series

import numpy as np
import pandas as pd

from src.paper.models import PaperTrade, TradeAction
from src.paper.store import PaperStore
from src.strategy.reentry_mixin import ReEntryMixin


class DummyStrategy(ReEntryMixin):
    strategy_name = "paper_dummy_strategy"
    reentry_leg_role = "dummy_role"
    reentry_script_hint = "dummy_script.py"

    def __init__(self, store=None, notifier=None, vix_data_dir=None):
        self._store = store
        self._notifier = notifier
        self._vix_data_dir = vix_data_dir or Path("/tmp")


def _run(coro):
    return asyncio.run(coro)


def _make_vix_series(ivr: float, length: int = 252) -> pd.Series:
    vix_today = 10.0 + ivr * 20.0
    values = np.linspace(10.0, 30.0, length - 1).tolist() + [vix_today]
    return pd.Series(values, dtype="float64")


def test_reentry_skipped_when_no_store():
    # If self._store is None, reentry check is skipped.
    strategy = DummyStrategy(store=None)
    _run(
        strategy._check_reentry(
            expiry=date.today(),
            today=date.today(),
            instrument_key="TEST",
            trade_id=123,
        )
    )


def test_reentry_eligible_when_all_gates_pass(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = MagicMock()
    notifier.send_plain_message = AsyncMock(return_value=True)
    strategy = DummyStrategy(store=store, notifier=notifier, vix_data_dir=tmp_path)

    vix_series = _make_vix_series(ivr=0.30)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        _run(
            strategy._check_reentry(
                expiry=date.today() + timedelta(days=15),
                today=date.today(),
                instrument_key="TEST",
                trade_id=123,
            )
        )

    events = store.get_open_exit_events(strategy_name="paper_dummy_strategy")
    signals = [e["exit_signal"] for e in events]
    assert "R5_REENTRY_ELIGIBLE" in signals
    assert events[0]["dte"] == 15
    assert events[0]["trade_id"] == "123"
    notifier.send_plain_message.assert_awaited_once()


def test_reentry_blocked_when_dte_less_than_14(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = DummyStrategy(store=store, vix_data_dir=tmp_path)

    vix_series = _make_vix_series(ivr=0.30)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        _run(
            strategy._check_reentry(
                expiry=date.today() + timedelta(days=13),
                today=date.today(),
                instrument_key="TEST",
                trade_id=123,
            )
        )

    events = store.get_open_exit_events(strategy_name="paper_dummy_strategy")
    blocked = [e for e in events if e["exit_signal"] == "R5_REENTRY_BLOCKED"]
    assert blocked
    assert "DTE" in blocked[0]["notes"]
    assert blocked[0]["dte"] == 13


def test_reentry_blocked_when_ivr_below_floor(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = DummyStrategy(store=store, vix_data_dir=tmp_path)

    vix_series = _make_vix_series(ivr=0.22)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        _run(
            strategy._check_reentry(
                expiry=date.today() + timedelta(days=20),
                today=date.today(),
                instrument_key="TEST",
                trade_id=123,
            )
        )

    events = store.get_open_exit_events(strategy_name="paper_dummy_strategy")
    blocked = [e for e in events if e["exit_signal"] == "R5_REENTRY_BLOCKED"]
    assert blocked
    assert "IVR" in blocked[0]["notes"]


def test_reentry_blocked_when_ivr_history_insufficient(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = DummyStrategy(store=store, vix_data_dir=tmp_path)

    short_series = pd.Series([15.0, 18.0, 20.0], dtype="float64")
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=short_series):
        _run(
            strategy._check_reentry(
                expiry=date.today() + timedelta(days=20),
                today=date.today(),
                instrument_key="TEST",
                trade_id=123,
            )
        )

    events = store.get_open_exit_events(strategy_name="paper_dummy_strategy")
    blocked = [e for e in events if e["exit_signal"] == "R5_REENTRY_BLOCKED"]
    assert blocked
    assert "IVR history" in blocked[0]["notes"]


def test_reentry_blocked_when_position_already_open(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = DummyStrategy(store=store, vix_data_dir=tmp_path)

    store.record_trade(
        PaperTrade(
            strategy_name="paper_dummy_strategy",
            leg_role="dummy_role",
            action=TradeAction.SELL,
            quantity=65,
            price="100",
            instrument_key="NSE_FO|NIFTY23000PE",
            trade_date=date.today(),
        )
    )

    vix_series = _make_vix_series(ivr=0.30)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        _run(
            strategy._check_reentry(
                expiry=date.today() + timedelta(days=20),
                today=date.today(),
                instrument_key="TEST",
                trade_id=123,
            )
        )

    events = store.get_open_exit_events(strategy_name="paper_dummy_strategy")
    blocked = [e for e in events if e["exit_signal"] == "R5_REENTRY_BLOCKED"]
    assert blocked
    assert "open position" in blocked[0]["notes"]


def test_reentry_event_written_even_when_notifier_raises(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = MagicMock()
    notifier.send_plain_message = AsyncMock(side_effect=RuntimeError("telegram down"))
    strategy = DummyStrategy(store=store, notifier=notifier, vix_data_dir=tmp_path)

    vix_series = _make_vix_series(ivr=0.30)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        _run(
            strategy._check_reentry(
                expiry=date.today() + timedelta(days=20),
                today=date.today(),
                instrument_key="TEST",
                trade_id=123,
            )
        )

    events = store.get_open_exit_events(strategy_name="paper_dummy_strategy")
    assert any(e["exit_signal"] in ("R5_REENTRY_ELIGIBLE", "R5_REENTRY_BLOCKED") for e in events)


class CustomPPStrategy(ReEntryMixin):
    strategy_name = "paper_custom_pp"
    reentry_leg_role = "protective_put"
    reentry_script_hint = "hint.py"
    reentry_ivr_threshold = 0.60

    def __init__(self, store, vix_data_dir):
        self._store = store
        self._vix_data_dir = vix_data_dir
        self._notifier = None

    def _ivr_passes(self, ivr: float) -> tuple[bool, str]:
        if ivr > self.reentry_ivr_threshold:
            return False, f"IVR={ivr:.2f} > {self.reentry_ivr_threshold:.2f} — high vol"
        return True, ""

    def _reentry_position_active(self, p):
        return p.leg_role == self.reentry_leg_role and p.net_qty > 0


def test_custom_ivr_passes_override(tmp_path: Path):
    """PP strategy blocks when IVR is high and allows when IVR is low.

    Two separate days are used so the dedup guard does not suppress the second
    call — each day is an independent eligibility evaluation.
    """
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = CustomPPStrategy(store=store, vix_data_dir=tmp_path)

    day1 = date(2025, 1, 10)
    day2 = date(2025, 1, 11)
    expiry = date(2025, 2, 5)  # DTE >= 14 from both days

    # IVR=0.70 should fail the check for CustomPPStrategy (which wants <= 0.60)
    vix_series_high = _make_vix_series(ivr=0.70)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series_high):
        _run(
            strategy._check_reentry(
                expiry=expiry,
                today=day1,
                instrument_key="TEST",
                trade_id=123,
            )
        )

    events = store.get_open_exit_events(strategy_name="paper_custom_pp")
    assert events[0]["exit_signal"] == "R5_REENTRY_BLOCKED"
    assert "IVR" in events[0]["notes"]

    # IVR=0.50 should pass the check (different day — dedup does not block)
    vix_series_low = _make_vix_series(ivr=0.50)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series_low):
        _run(
            strategy._check_reentry(
                expiry=expiry,
                today=day2,
                instrument_key="TEST",
                trade_id=124,
            )
        )

    events2 = store.get_open_exit_events(strategy_name="paper_custom_pp")
    assert any(e["exit_signal"] == "R5_REENTRY_ELIGIBLE" for e in events2)


def test_custom_reentry_position_active_long_position_match(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = CustomPPStrategy(store=store, vix_data_dir=tmp_path)

    # Store a long put position (net_qty > 0)
    store.record_trade(
        PaperTrade(
            strategy_name="paper_custom_pp",
            leg_role="protective_put",
            action=TradeAction.BUY,
            quantity=65,
            price="100",
            instrument_key="NSE_FO|NIFTY23000PE",
            trade_date=date.today(),
        )
    )

    vix_series = _make_vix_series(ivr=0.50)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        _run(
            strategy._check_reentry(
                expiry=date.today() + timedelta(days=20),
                today=date.today(),
                instrument_key="TEST",
                trade_id=125,
            )
        )

    events = store.get_open_exit_events(strategy_name="paper_custom_pp")
    blocked = [e for e in events if e["exit_signal"] == "R5_REENTRY_BLOCKED"]
    assert blocked
    assert "open position" in blocked[0]["notes"]


def test_reentry_dedup_same_day_writes_once(tmp_path: Path):
    """Calling _check_reentry twice on the same day → 1 DB row, 1 Telegram message."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = MagicMock()
    notifier.send_plain_message = AsyncMock(return_value=True)
    strategy = DummyStrategy(store=store, notifier=notifier, vix_data_dir=tmp_path)

    today = date.today()
    expiry = today + timedelta(days=20)
    vix_series = _make_vix_series(ivr=0.40)

    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        _run(
            strategy._check_reentry(
                expiry=expiry,
                today=today,
                instrument_key="TEST",
                trade_id=1,
            )
        )
        # Second call same day — must be deduped
        _run(
            strategy._check_reentry(
                expiry=expiry,
                today=today,
                instrument_key="TEST",
                trade_id=1,
            )
        )

    events = store.get_open_exit_events(strategy_name="paper_dummy_strategy")
    assert len(events) == 1, f"Expected 1 event, got {len(events)}"
    notifier.send_plain_message.assert_awaited_once()


def test_vix_series_load_uses_asyncio_to_thread(tmp_path: Path):
    """load_vix_series must be dispatched via asyncio.to_thread, not called directly."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = DummyStrategy(store=store, vix_data_dir=tmp_path)
    vix_series = _make_vix_series(ivr=0.30)

    with patch("src.strategy.reentry_mixin.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = AsyncMock(return_value=vix_series)
        _run(
            strategy._check_reentry(
                expiry=date.today() + timedelta(days=20),
                today=date.today(),
                instrument_key="TEST",
                trade_id=1,
            )
        )

    mock_asyncio.to_thread.assert_awaited_once()
    load_fn, vix_dir = mock_asyncio.to_thread.call_args[0]
    assert load_fn is load_vix_series
    assert vix_dir == tmp_path


def test_vix_to_thread_exception_results_in_blocked(tmp_path: Path):
    """asyncio.to_thread raising must produce R5_REENTRY_BLOCKED, not propagate."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = DummyStrategy(store=store, vix_data_dir=tmp_path)

    with patch("src.strategy.reentry_mixin.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = AsyncMock(side_effect=RuntimeError("disk read failed"))
        _run(
            strategy._check_reentry(
                expiry=date.today() + timedelta(days=20),
                today=date.today(),
                instrument_key="TEST",
                trade_id=1,
            )
        )

    events = store.get_open_exit_events(strategy_name="paper_dummy_strategy")
    blocked = [e for e in events if e["exit_signal"] == "R5_REENTRY_BLOCKED"]
    assert blocked, "Expected BLOCKED event when to_thread raises"
    assert "IVR history" in blocked[0]["notes"]


def test_reentry_dedup_different_days_writes_twice(tmp_path: Path):
    """Calling _check_reentry on two different days → 2 DB rows, 2 Telegram messages."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = MagicMock()
    notifier.send_plain_message = AsyncMock(return_value=True)
    strategy = DummyStrategy(store=store, notifier=notifier, vix_data_dir=tmp_path)

    day1 = date(2025, 1, 10)
    day2 = date(2025, 1, 11)
    expiry = date(2025, 2, 1)
    vix_series = _make_vix_series(ivr=0.40)

    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        _run(
            strategy._check_reentry(
                expiry=expiry,
                today=day1,
                instrument_key="TEST",
                trade_id=1,
            )
        )
        _run(
            strategy._check_reentry(
                expiry=expiry,
                today=day2,
                instrument_key="TEST",
                trade_id=2,
            )
        )

    events = store.get_open_exit_events(strategy_name="paper_dummy_strategy")
    assert len(events) == 2, f"Expected 2 events, got {len(events)}"
    assert notifier.send_plain_message.await_count == 2
