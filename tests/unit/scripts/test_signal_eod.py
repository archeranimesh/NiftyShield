"""No-network render tests for the S5.5a outcome Telegram message."""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts import signal_eod
from src.paper.constants import LOT_SIZE
from src.signals.models import (
    DailySignal,
    Direction,
    SignalOutcome,
    SignalResponse,
    TradeAction,
)

_FMT_OUTCOME = signal_eod._format_outcome_notification


def _resp(provider: str, direction: Direction) -> SignalResponse:
    return SignalResponse(
        trade_date=date(2026, 9, 8),
        provider=provider,
        direction=direction,
        confidence=4,
        recommended_strike=24800,
        entry_premium_low=Decimal("58.00"),
        entry_premium_high=Decimal("72.00"),
        key_reason="GIFT Nifty supportive.",
        key_risk="US CPI tonight.",
        raw_response="{}",
    )


_SIGNAL_BUY = DailySignal(
    trade_date=date(2026, 9, 8),
    responses=[_resp("grok", Direction.BULLISH), _resp("gpt4o", Direction.BULLISH)],
    consensus_direction=Direction.BULLISH,
    consensus_confidence=Decimal("3.5"),
    trade_action=TradeAction.BUY_CALL,
    recommended_strike=24800,
    agreeing_models=["grok", "gpt4o"],
    dissenting_models=["gemini"],
)
_SIGNAL_NOTRADE = DailySignal(
    trade_date=date(2026, 9, 8),
    responses=[],
    consensus_direction=Direction.NEUTRAL,
    consensus_confidence=Decimal("0"),
    trade_action=TradeAction.NO_TRADE,
    recommended_strike=None,
    agreeing_models=[],
    dissenting_models=[],
)

_OUT_EXEC = SignalOutcome(
    trade_date=date(2026, 9, 8),
    trade_action=TradeAction.BUY_CALL,
    recommended_strike=24800,
    entry_premium=Decimal("65.50"),
    exit_premium=Decimal("92.00"),
    pnl_per_lot=(Decimal("92.00") - Decimal("65.50")) * LOT_SIZE,
    nifty_close=Decimal("24842.10"),
    executed=True,
)


def test_executed_outcome_renders_realised_pnl() -> None:
    msg = _FMT_OUTCOME(_OUT_EXEC, _SIGNAL_BUY)

    assert msg.startswith("*📊 SIGNAL OUTCOME · 08 Sep*\n\n")
    assert "📈 BULLISH · BUY CALL 24800" in msg
    assert "💰 Entry ₹65\\.50 → Exit ₹92\\.00" in msg
    assert "(would-be)" not in msg
    assert "✅ P&L: \\+₹1,722\\.50 / lot" in msg
    assert "🏁 Nifty close: 24,842" in msg
    assert "🔧 Phase: openrouter\\_only" in msg


def test_not_taken_outcome_derives_would_be_pnl_in_formatter() -> None:
    out_skip = _OUT_EXEC.model_copy(update={"executed": False, "pnl_per_lot": None})
    msg = _FMT_OUTCOME(out_skip, _SIGNAL_BUY)

    assert msg.startswith("*📊 SIGNAL OUTCOME · 08 Sep · NOT TAKEN*\n\n")
    assert "💰 Entry ₹65\\.50 → Exit ₹92\\.00 \\(would\\-be\\)" in msg
    assert "✅ Paper P&L: \\+₹1,722\\.50 / lot" in msg


def test_no_trade_outcome_renders_close_only_line() -> None:
    out = SignalOutcome(
        trade_date=date(2026, 9, 8),
        trade_action=TradeAction.NO_TRADE,
        recommended_strike=None,
        entry_premium=None,
        exit_premium=None,
        pnl_per_lot=None,
        nifty_close=Decimal("24842.10"),
        executed=False,
    )
    msg = _FMT_OUTCOME(out, _SIGNAL_NOTRADE)

    assert msg.startswith("*📊 SIGNAL OUTCOME · 08 Sep · NO TRADE*\n\n")
    assert "➖ No signal issued today" in msg
    assert "🏁 Nifty close: 24,842" in msg
    assert "P&L" not in msg


def test_missing_premium_falls_back_to_close_only() -> None:
    out = _OUT_EXEC.model_copy(update={"exit_premium": None, "pnl_per_lot": None})
    msg = _FMT_OUTCOME(out, _SIGNAL_BUY)

    assert msg.startswith("*📊 SIGNAL OUTCOME · 08 Sep*\n\n")
    assert "➖ Outcome not priced" in msg
    assert "🏁 Nifty close: 24,842" in msg
    assert "Entry" not in msg


def test_resolve_option_key_delegates_and_exits_on_none() -> None:
    signal = DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24800,
        entry_premium=None,
        agreeing_models=[],
        dissenting_models=[],
    )
    with patch("scripts.signal_eod.resolve_monthly_option") as mock_resolve:
        mock_resolve.return_value = "NSE_FO|12345"
        key = signal_eod._resolve_option_key(signal, Path("/fake/bod.json"))
        assert key == "NSE_FO|12345"
        mock_resolve.assert_called_once_with(signal, Path("/fake/bod.json"))

        mock_resolve.return_value = None
        with pytest.raises((SystemExit, ValueError, RuntimeError)) as exc_info:
            signal_eod._resolve_option_key(signal, Path("/fake/bod.json"))
        assert str(exc_info.value) != ""


@patch("scripts.signal_eod.PaperStore")
@patch("scripts.signal_eod.guard_trading_day")
@patch("scripts.signal_eod._parse_args")
@patch("scripts.signal_eod.market_today")
@patch("scripts.signal_eod.SignalStore")
@patch("scripts.signal_eod._resolve_option_key")
@patch("scripts.signal_eod._fetch_ltp")
@patch("scripts.signal_eod.build_notifier")
def test_auto_path_prefers_stored_entry_premium_over_consensus(
    mock_notifier: MagicMock,
    mock_fetch_ltp: MagicMock,
    mock_resolve: MagicMock,
    mock_store_cls: MagicMock,
    mock_market_today: MagicMock,
    mock_parse_args: MagicMock,
    mock_guard: MagicMock,
    mock_paper_store_cls: MagicMock,
) -> None:
    mock_paper_store_cls.return_value.get_entries.return_value = []
    mock_parse_args.return_value = MagicMock(
        auto=True,
        report_only=False,
        from_date=None,
        to_date=None,
        phase=None,
        entry_premium=None,
        exit_premium=None,
        executed=False,
        nifty_close=None,
        bod_path=Path("/fake/bod.json"),
        notes="",
        trade_date="2026-09-08",
    )
    mock_market_today.return_value = date(2026, 9, 8)
    mock_notifier.return_value = None
    mock_guard.return_value = False

    mock_store = MagicMock()
    mock_store_cls.return_value = mock_store

    # signal WITH entry_premium
    signal = DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24800,
        entry_premium=Decimal("120.00"),
        agreeing_models=[],
        dissenting_models=[],
    )
    mock_store.get_signal.return_value = signal

    mock_resolve.return_value = "NSE_FO|12345"
    mock_fetch_ltp.return_value = {
        "NSE_FO|12345": Decimal("150.00"),
        "NSE_INDEX|Nifty 50": Decimal("24850.00"),
    }

    with patch("scripts.signal_eod._consensus_entry_premium") as mock_consensus:
        mock_consensus.return_value = Decimal("99.99")

        signal_eod.main()

        # assert outcome was recorded with 120.00, not 99.99
        outcome = mock_store.record_outcome.call_args[0][0]
        assert outcome.entry_premium == Decimal("120.00")
        mock_consensus.assert_not_called()


@patch("scripts.signal_eod.PaperStore")
@patch("scripts.signal_eod.guard_trading_day")
@patch("scripts.signal_eod._parse_args")
@patch("scripts.signal_eod.market_today")
@patch("scripts.signal_eod.SignalStore")
@patch("scripts.signal_eod._resolve_option_key")
@patch("scripts.signal_eod._fetch_ltp")
@patch("scripts.signal_eod.build_notifier")
def test_auto_path_falls_back_to_consensus_when_entry_premium_none(
    mock_notifier: MagicMock,
    mock_fetch_ltp: MagicMock,
    mock_resolve: MagicMock,
    mock_store_cls: MagicMock,
    mock_market_today: MagicMock,
    mock_parse_args: MagicMock,
    mock_guard: MagicMock,
    mock_paper_store_cls: MagicMock,
) -> None:
    mock_paper_store_cls.return_value.get_entries.return_value = []
    mock_parse_args.return_value = MagicMock(
        auto=True,
        report_only=False,
        from_date=None,
        to_date=None,
        phase=None,
        entry_premium=None,
        exit_premium=None,
        executed=False,
        nifty_close=None,
        bod_path=Path("/fake/bod.json"),
        notes="",
        trade_date="2026-09-08",
    )
    mock_market_today.return_value = date(2026, 9, 8)
    mock_notifier.return_value = None
    mock_guard.return_value = False

    mock_store = MagicMock()
    mock_store_cls.return_value = mock_store

    # signal WITHOUT entry_premium
    signal = DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24800,
        entry_premium=None,
        agreeing_models=[],
        dissenting_models=[],
    )
    mock_store.get_signal.return_value = signal

    mock_resolve.return_value = "NSE_FO|12345"
    mock_fetch_ltp.return_value = {
        "NSE_FO|12345": Decimal("150.00"),
        "NSE_INDEX|Nifty 50": Decimal("24850.00"),
    }

    with patch("scripts.signal_eod._consensus_entry_premium") as mock_consensus:
        mock_consensus.return_value = Decimal("99.99")

        signal_eod.main()

        # assert outcome was recorded with 99.99
        outcome = mock_store.record_outcome.call_args[0][0]
        assert outcome.entry_premium == Decimal("99.99")
        mock_consensus.assert_called_once()


@patch("scripts.signal_eod.PaperStore")
@patch("scripts.signal_eod.guard_trading_day")
@patch("scripts.signal_eod._parse_args")
@patch("scripts.signal_eod.market_today")
@patch("scripts.signal_eod.SignalStore")
@patch("scripts.signal_eod._resolve_option_key")
@patch("scripts.signal_eod._fetch_ltp")
@patch("scripts.signal_eod.build_notifier")
def test_executed_detected_from_live_paper_entry(
    mock_notifier: MagicMock,
    mock_fetch_ltp: MagicMock,
    mock_resolve: MagicMock,
    mock_store_cls: MagicMock,
    mock_market_today: MagicMock,
    mock_parse_args: MagicMock,
    mock_guard: MagicMock,
    mock_paper_store_cls: MagicMock,
) -> None:
    """A live `paper_signal_entries` row flips `executed=True` even when `--executed` is unset (BUG-048)."""
    mock_parse_args.return_value = MagicMock(
        auto=True,
        report_only=False,
        from_date=None,
        to_date=None,
        phase=None,
        entry_premium=None,
        exit_premium=None,
        executed=False,
        nifty_close=None,
        bod_path=Path("/fake/bod.json"),
        notes="",
        trade_date="2026-09-08",
    )
    mock_market_today.return_value = date(2026, 9, 8)
    mock_notifier.return_value = None
    mock_guard.return_value = False

    mock_store = MagicMock()
    mock_store_cls.return_value = mock_store

    signal = DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24800,
        entry_premium=None,
        agreeing_models=[],
        dissenting_models=[],
    )
    mock_store.get_signal.return_value = signal

    mock_resolve.return_value = "NSE_FO|12345"
    mock_fetch_ltp.return_value = {
        "NSE_FO|12345": Decimal("150.00"),
        "NSE_INDEX|Nifty 50": Decimal("24850.00"),
    }

    live_entry = MagicMock()
    live_entry.entry_premium = Decimal("120.00")
    mock_paper_store_cls.return_value.get_entries.return_value = [live_entry]

    signal_eod.main()

    outcome = mock_store.record_outcome.call_args[0][0]
    assert outcome.executed is True
    assert outcome.entry_premium == Decimal("120.00")
    assert outcome.pnl_per_lot == (Decimal("150.00") - Decimal("120.00")) * LOT_SIZE


@patch("scripts.signal_eod.PaperStore")
@patch("scripts.signal_eod.guard_trading_day")
@patch("scripts.signal_eod._parse_args")
@patch("scripts.signal_eod.market_today")
@patch("scripts.signal_eod.SignalStore")
@patch("scripts.signal_eod._resolve_option_key")
@patch("scripts.signal_eod._fetch_ltp")
@patch("scripts.signal_eod.build_notifier")
def test_executed_stays_false_when_no_live_paper_entry(
    mock_notifier: MagicMock,
    mock_fetch_ltp: MagicMock,
    mock_resolve: MagicMock,
    mock_store_cls: MagicMock,
    mock_market_today: MagicMock,
    mock_parse_args: MagicMock,
    mock_guard: MagicMock,
    mock_paper_store_cls: MagicMock,
) -> None:
    """No matching `paper_signal_entries` row leaves `executed` at the `--executed` flag's value."""
    mock_parse_args.return_value = MagicMock(
        auto=True,
        report_only=False,
        from_date=None,
        to_date=None,
        phase=None,
        entry_premium=None,
        exit_premium=None,
        executed=False,
        nifty_close=None,
        bod_path=Path("/fake/bod.json"),
        notes="",
        trade_date="2026-09-08",
    )
    mock_market_today.return_value = date(2026, 9, 8)
    mock_notifier.return_value = None
    mock_guard.return_value = False

    mock_store = MagicMock()
    mock_store_cls.return_value = mock_store

    signal = DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24800,
        entry_premium=Decimal("120.00"),
        agreeing_models=[],
        dissenting_models=[],
    )
    mock_store.get_signal.return_value = signal

    mock_resolve.return_value = "NSE_FO|12345"
    mock_fetch_ltp.return_value = {
        "NSE_FO|12345": Decimal("150.00"),
        "NSE_INDEX|Nifty 50": Decimal("24850.00"),
    }

    mock_paper_store_cls.return_value.get_entries.return_value = []

    signal_eod.main()

    outcome = mock_store.record_outcome.call_args[0][0]
    assert outcome.executed is False
    assert outcome.entry_premium == Decimal("120.00")
    assert outcome.pnl_per_lot is None


@patch("scripts.signal_eod.SignalStore")
@patch("scripts.signal_eod._parse_args")
@patch("scripts.signal_eod.guard_trading_day")
def test_exits_on_guard_trading_day(
    mock_guard: MagicMock,
    mock_parse_args: MagicMock,
    mock_store: MagicMock,
) -> None:
    mock_parse_args.return_value = MagicMock(
        trade_date="2026-09-08",
    )
    mock_guard.return_value = True

    from scripts.signal_eod import main

    main()

    # Guard returned True -> main() exits before any DB work
    mock_guard.assert_called_once()
    mock_store.assert_not_called()


_FMT_REPORT = signal_eod._format_report_message


def test_format_report_message_wraps_in_fenced_block() -> None:
    msg = _FMT_REPORT("Signal Pipeline Performance Report\nOVERALL: 5 trades")
    assert msg.startswith("```\n")
    assert msg.endswith("\n```")
    assert "OVERALL: 5 trades" in msg


def test_format_report_message_escapes_fence_reserved_chars() -> None:
    msg = _FMT_REPORT("path C:\\x and `code`")
    assert "\\\\x" in msg
    assert "\\`code\\`" in msg


def test_notify_no_notifier_configured_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(signal_eod, "build_notifier", lambda: None)
    # Must not raise when no notifier is configured.
    signal_eod._notify_report("some report body")


def test_notify_send_failure_is_non_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Boom:
        async def send(self, _msg: str) -> None:
            raise RuntimeError("telegram down")

    monkeypatch.setattr(signal_eod, "build_notifier", lambda: _Boom())
    # Logged and swallowed — no exception past the caller.
    signal_eod._notify_report("some report body")


@patch("scripts.signal_eod._parse_args")
@patch("scripts.signal_eod.run_record_phase")
@patch("scripts.signal_eod.run_report_phase")
@patch("scripts.signal_eod.guard_trading_day")
def test_record_exception_allows_report_phase_to_run(
    mock_guard: MagicMock,
    mock_report: MagicMock,
    mock_record: MagicMock,
    mock_parse_args: MagicMock,
) -> None:
    mock_parse_args.return_value = MagicMock(
        auto=False,
        report_only=False,
        from_date=None,
        to_date=None,
        phase=None,
        trade_date="2026-09-08",
    )
    mock_guard.return_value = False

    mock_record.side_effect = RuntimeError("DB locked")

    signal_eod.main()

    mock_record.assert_called_once()
    mock_report.assert_called_once()
