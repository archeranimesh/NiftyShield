import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.signals.models import (
    DailySignal,
    Direction,
    TradeAction,
)
from src.signals.option_resolver import resolve_monthly_option


def _make_bod(entries: list[dict[str, object]]) -> str:
    return json.dumps(
        [
            {
                "instrument_key": e.get("instrument_key", "NSE_FO|12345"),
                "name": e.get("name", "NIFTY 24000 CE"),
                "instrument_type": e.get("instrument_type", "CE"),
                "trading_symbol": e.get("trading_symbol", "NIFTY24APR24000CE"),
                "expiry": e.get("expiry", "2024-04-25"),
                "strike_price": e.get("strike_price", 24000.0),
                "underlying_key": e.get("underlying_key", "NSE_INDEX|Nifty 50"),
                "underlying_symbol": e.get("underlying_symbol", "NIFTY"),
                "lot_size": 50,
                "freeze_quantity": 1800,
                "exchange": "NSE_FO",
                "segment": "NSE_FO",
            }
            for e in entries
        ]
    )


def test_resolve_monthly_option_happy_path(tmp_path: Path) -> None:
    bod_path = tmp_path / "bod.json"
    bod_path.write_text(_make_bod([{"instrument_key": "NSE_FO|12345"}]))

    signal = DailySignal(
        trade_date=date(2024, 4, 1),
        responses=[],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24000,
        entry_premium=None,
        agreeing_models=[],
        dissenting_models=[],
    )

    assert resolve_monthly_option(signal, bod_path) == "NSE_FO|12345"


def test_resolve_monthly_option_missing_bod(tmp_path: Path) -> None:
    signal = DailySignal(
        trade_date=date(2024, 4, 1),
        responses=[],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24000,
        entry_premium=None,
        agreeing_models=[],
        dissenting_models=[],
    )
    assert resolve_monthly_option(signal, tmp_path / "missing.json") is None


def test_resolve_monthly_option_no_monthly_expiry(tmp_path: Path) -> None:
    bod_path = tmp_path / "bod.json"
    bod_path.write_text(_make_bod([]))

    signal = DailySignal(
        trade_date=date(2024, 4, 1),
        responses=[],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24000,
        entry_premium=None,
        agreeing_models=[],
        dissenting_models=[],
    )
    assert resolve_monthly_option(signal, bod_path) is None


def test_resolve_monthly_option_no_strike_match_multiple(tmp_path: Path) -> None:
    bod_path = tmp_path / "bod.json"
    bod_path.write_text(
        _make_bod(
            [
                {"instrument_key": "NSE_FO|11111", "expiry": "2024-04-18"},
                {"instrument_key": "NSE_FO|22222", "expiry": "2024-04-25", "strike_price": 24100.0},
            ]
        )
    )

    signal = DailySignal(
        trade_date=date(2024, 4, 1),
        responses=[],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24000,
        entry_premium=None,
        agreeing_models=[],
        dissenting_models=[],
    )
    assert resolve_monthly_option(signal, bod_path) is None


def test_resolve_monthly_option_no_strike_match_single(tmp_path: Path) -> None:
    bod_path = tmp_path / "bod.json"
    bod_path.write_text(_make_bod([{"instrument_key": "NSE_FO|12345", "strike_price": 24100.0}]))

    signal = DailySignal(
        trade_date=date(2024, 4, 1),
        responses=[],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24000,
        entry_premium=None,
        agreeing_models=[],
        dissenting_models=[],
    )
    assert resolve_monthly_option(signal, bod_path) is None
