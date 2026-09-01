import asyncio
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.backtest.vix_ingest import load_vix_series
from src.paper.constants import STRATEGY_OVERLAY
from src.paper.models import PaperTrade, TradeAction
from src.paper.store import PaperStore
from src.strategy.reentry_mixin import ReEntryMixin


class DummyStrategy(ReEntryMixin):
    # Real CSP identifiers — the re-entry notice (ROLL-7) looks strategy_name /
    # reentry_leg_role up in STRATEGY_LABELS / LEG_ROLE_LABELS and raises on an
    # unmapped value, so the fixture must use a mapped pair.
    strategy_name = "paper_csp_nifty_v1"
    reentry_leg_role = "short_put"
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

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
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

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
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

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
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

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
    blocked = [e for e in events if e["exit_signal"] == "R5_REENTRY_BLOCKED"]
    assert blocked
    assert "IVR history" in blocked[0]["notes"]


def test_reentry_blocked_when_position_already_open(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = DummyStrategy(store=store, vix_data_dir=tmp_path)

    store.record_trade(
        PaperTrade(
            strategy_name="paper_csp_nifty_v1",
            leg_role="short_put",
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

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
    blocked = [e for e in events if e["exit_signal"] == "R5_REENTRY_BLOCKED"]
    assert blocked
    assert blocked[0]["notes"] == "Position already active"


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

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
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

    def _ivr_passes(self, ivr: float) -> tuple[bool, str, str | None]:
        if ivr > self.reentry_ivr_threshold:
            return False, f"IVR={ivr:.2f} > {self.reentry_ivr_threshold:.2f}", "High vol"
        return True, "", None

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
    assert blocked[0]["notes"] == "Position already active"


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

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
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

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
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

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
    assert len(events) == 2, f"Expected 2 events, got {len(events)}"
    assert notifier.send_plain_message.await_count == 2


# ── ROLL-7: MarkdownV2 kv-line re-entry notice ───────────────────────────────
# Reference: scratch/2026-08-08_reentry_notice_format.py; spec:
# docs/plan/telegram-markdown-migration/strategy-rollout/stories.md ROLL-7.


def _make_notifier() -> MagicMock:
    notifier = MagicMock()
    notifier.send_plain_message = AsyncMock(return_value=True)
    return notifier


def _sent_message(notifier: MagicMock) -> str:
    notifier.send_plain_message.assert_awaited_once()
    return notifier.send_plain_message.call_args[0][0]


def _run_reentry(
    strategy: DummyStrategy, *, days_to_expiry: int, ivr: float, tmp_path: Path
) -> None:
    vix_series = _make_vix_series(ivr=ivr)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        _run(
            strategy._check_reentry(
                expiry=date.today() + timedelta(days=days_to_expiry),
                today=date.today(),
                instrument_key="TEST",
                trade_id=1,
            )
        )


def test_reentry_notice_eligible_kv_structure(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = _make_notifier()
    strategy = DummyStrategy(store=store, notifier=notifier, vix_data_dir=tmp_path)

    _run_reentry(strategy, days_to_expiry=20, ivr=0.40, tmp_path=tmp_path)

    assert _sent_message(notifier) == (
        "✅ RE\\-ENTRY ELIGIBLE: CSP V1\n"
        "Leg: Short Put\n"
        "Status: All Gates Passed\n"
        "Execute:\n"
        "`dummy_script.py`"
    )


def test_eligible_execute_line_uses_mdcode(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = _make_notifier()
    strategy = DummyStrategy(store=store, notifier=notifier, vix_data_dir=tmp_path)

    _run_reentry(strategy, days_to_expiry=20, ivr=0.40, tmp_path=tmp_path)

    assert _sent_message(notifier).splitlines()[-1] == "`dummy_script.py`"


def test_reentry_notice_blocked_dte_kv_structure(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = _make_notifier()
    strategy = DummyStrategy(store=store, notifier=notifier, vix_data_dir=tmp_path)

    _run_reentry(strategy, days_to_expiry=13, ivr=0.40, tmp_path=tmp_path)

    assert _sent_message(notifier) == (
        "⛔ RE\\-ENTRY BLOCKED: CSP V1\n"
        "Leg: Short Put\n"
        "Reason: DTE\\=13 < 14 \\(Too close to expiry\\)"
    )


def test_reentry_notice_blocked_ivr_kv_structure(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = _make_notifier()
    strategy = DummyStrategy(store=store, notifier=notifier, vix_data_dir=tmp_path)

    _run_reentry(strategy, days_to_expiry=20, ivr=0.10, tmp_path=tmp_path)

    lines = _sent_message(notifier).splitlines()
    assert lines[0] == "⛔ RE\\-ENTRY BLOCKED: CSP V1"
    assert lines[1] == "Leg: Short Put"
    assert lines[2].startswith("Reason: IVR\\=")
    assert lines[2].endswith("\\(Low vol, skip cycle\\)")
    assert "\\." in lines[2]  # decimal point in "0.25" is escaped
    assert "—" not in lines[2]  # no em-dash prose — the pair was formatted, not split


def test_reentry_notice_blocked_open_position_kv_structure(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = _make_notifier()
    strategy = DummyStrategy(store=store, notifier=notifier, vix_data_dir=tmp_path)

    store.record_trade(
        PaperTrade(
            strategy_name="paper_csp_nifty_v1",
            leg_role="short_put",
            action=TradeAction.SELL,
            quantity=65,
            price="100",
            instrument_key="NSE_FO|NIFTY23000PE",
            trade_date=date.today(),
        )
    )

    _run_reentry(strategy, days_to_expiry=20, ivr=0.40, tmp_path=tmp_path)

    assert _sent_message(notifier) == (
        "⛔ RE\\-ENTRY BLOCKED: CSP V1\nLeg: Short Put\nReason: Position already active"
    )


def test_reentry_notice_escapes_raw_strategy_id(tmp_path: Path):
    """The raw id (paper_csp_nifty_v1, underscores) never leaks into the notice —
    only the mapped label, and it survives the escape_markdown() wrap intact."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = _make_notifier()
    strategy = DummyStrategy(store=store, notifier=notifier, vix_data_dir=tmp_path)

    _run_reentry(strategy, days_to_expiry=13, ivr=0.40, tmp_path=tmp_path)

    msg = _sent_message(notifier)
    assert "paper_csp_nifty_v1" not in msg
    assert "short_put" not in msg
    assert "CSP V1" in msg


def test_ivr_passes_returns_structured_triple():
    strategy = DummyStrategy()
    assert strategy._ivr_passes(0.10) == (False, "IVR=0.10 < 0.25", "Low vol, skip cycle")
    assert strategy._ivr_passes(0.50) == (True, "", None)


def test_reentry_notes_are_flattened_pairs_not_prose(tmp_path: Path):
    """paper_exit_events.notes is the flattened '<short> (<detail>)' pair, never
    the old em-dash prose string (regression for the string-split-is-brittle fix)."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = DummyStrategy(store=store, vix_data_dir=tmp_path)

    _run_reentry(strategy, days_to_expiry=13, ivr=0.40, tmp_path=tmp_path)

    notes = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")[0]["notes"]
    assert notes == "DTE=13 < 14 (Too close to expiry)"
    assert "—" not in notes


class _UnmappedStrategyIdStrategy(DummyStrategy):
    strategy_name = "paper_not_in_labels"


class _UnmappedLegRoleStrategy(DummyStrategy):
    reentry_leg_role = "not_a_real_leg_role"


def test_reentry_notice_unmapped_strategy_raises(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = _make_notifier()
    strategy = _UnmappedStrategyIdStrategy(store=store, notifier=notifier, vix_data_dir=tmp_path)

    with pytest.raises(ValueError, match="paper_not_in_labels"):
        _run_reentry(strategy, days_to_expiry=13, ivr=0.40, tmp_path=tmp_path)


def test_reentry_notice_unmapped_leg_role_raises(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = _make_notifier()
    strategy = _UnmappedLegRoleStrategy(store=store, notifier=notifier, vix_data_dir=tmp_path)

    with pytest.raises(ValueError, match="not_a_real_leg_role"):
        _run_reentry(strategy, days_to_expiry=13, ivr=0.40, tmp_path=tmp_path)


class _OverlayCCStrategy(DummyStrategy):
    # CC/Collar/PP all carry strategy_name == STRATEGY_OVERLAY at runtime — the
    # headline must resolve via leg_role, not blow up on the umbrella id.
    strategy_name = STRATEGY_OVERLAY
    reentry_leg_role = "covered_call"


def test_reentry_notice_overlay_headline_resolves_by_leg_role(tmp_path: Path):
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = _make_notifier()
    strategy = _OverlayCCStrategy(store=store, notifier=notifier, vix_data_dir=tmp_path)

    _run_reentry(strategy, days_to_expiry=13, ivr=0.40, tmp_path=tmp_path)

    assert _sent_message(notifier) == (
        "⛔ RE\\-ENTRY BLOCKED: Covered Call V1\n"
        "Leg: Covered Call\n"
        "Reason: DTE\\=13 < 14 \\(Too close to expiry\\)"
    )


class _OverlayUnmappedLegStrategy(DummyStrategy):
    strategy_name = STRATEGY_OVERLAY
    reentry_leg_role = "short_put"  # valid leg_role, but not an overlay re-entry leg


def test_reentry_notice_overlay_unmapped_leg_role_raises(tmp_path: Path):
    """strategy_name == STRATEGY_OVERLAY with a leg_role absent from
    _OVERLAY_HEADLINE_BY_LEG raises rather than guessing a headline."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = _make_notifier()
    strategy = _OverlayUnmappedLegStrategy(store=store, notifier=notifier, vix_data_dir=tmp_path)

    with pytest.raises(ValueError, match="overlay leg_role"):
        _run_reentry(strategy, days_to_expiry=13, ivr=0.40, tmp_path=tmp_path)
