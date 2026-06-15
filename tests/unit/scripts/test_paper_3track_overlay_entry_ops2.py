"""Tests for OPS-2: atomic collar open/close in paper_3track_overlay_entry."""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Import after sys.path fixup
from scripts.strategies.three_track.paper_3track_overlay_entry import (
    _COLLAR_CALL_ROLE,
    _COLLAR_PUT_ROLE,
    OverlayTrade,
    _record_collar_trades,
    _validate_collar_pairs,
)
from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade


def _make_trade(
    strategy: str = "paper_nifty_spot",
    leg: str = "overlay_collar_put",
    action: TradeAction = TradeAction.BUY,
    key: str = "NSE_FO|11111",
) -> PaperTrade:
    return PaperTrade(
        strategy_name=strategy,
        leg_role=leg,
        instrument_key=key,
        trade_date=date(2026, 6, 15),
        action=action,
        quantity=65,
        price=Decimal("50.00"),
    )


def _ot(trade: PaperTrade) -> OverlayTrade:
    return OverlayTrade(trade=trade, strategy=trade.strategy_name, leg_role=trade.leg_role)


class TestValidateCollarPairs:
    """_validate_collar_pairs: guard against partial-collar submissions."""

    def test_both_legs_present_passes(self) -> None:
        put = _make_trade(leg=_COLLAR_PUT_ROLE, key="NSE_FO|11111")
        call_ = _make_trade(leg=_COLLAR_CALL_ROLE, action=TradeAction.SELL, key="NSE_FO|22222")
        # Should not raise
        _validate_collar_pairs([_ot(put), _ot(call_)])

    def test_collar_call_without_put_raises_systemexit(self) -> None:
        call_ = _make_trade(leg=_COLLAR_CALL_ROLE, action=TradeAction.SELL, key="NSE_FO|22222")
        with pytest.raises(SystemExit):
            _validate_collar_pairs([_ot(call_)])

    def test_collar_put_without_call_raises_systemexit(self) -> None:
        put = _make_trade(leg=_COLLAR_PUT_ROLE, key="NSE_FO|11111")
        with pytest.raises(SystemExit):
            _validate_collar_pairs([_ot(put)])

    def test_non_collar_legs_ignored(self) -> None:
        cc = _make_trade(leg="overlay_cc", action=TradeAction.SELL, key="NSE_FO|33333")
        # No collar legs → no pairs to validate → passes
        _validate_collar_pairs([_ot(cc)])

    def test_multiple_strategies_all_complete_passes(self) -> None:
        trades = []
        for strat in ("paper_nifty_spot", "paper_nifty_proxy"):
            trades.append(
                _ot(_make_trade(strategy=strat, leg=_COLLAR_PUT_ROLE, key="NSE_FO|11111"))
            )
            trades.append(
                _ot(
                    _make_trade(
                        strategy=strat,
                        leg=_COLLAR_CALL_ROLE,
                        action=TradeAction.SELL,
                        key="NSE_FO|22222",
                    )
                )
            )
        _validate_collar_pairs(trades)

    def test_one_strategy_missing_call_raises(self) -> None:
        # spot: complete; proxy: put-only
        spot_put = _make_trade(strategy="paper_nifty_spot", leg=_COLLAR_PUT_ROLE)
        spot_call = _make_trade(
            strategy="paper_nifty_spot", leg=_COLLAR_CALL_ROLE, action=TradeAction.SELL
        )
        proxy_put = _make_trade(strategy="paper_nifty_proxy", leg=_COLLAR_PUT_ROLE)
        with pytest.raises(SystemExit):
            _validate_collar_pairs([_ot(spot_put), _ot(spot_call), _ot(proxy_put)])


class TestRecordCollarTrades:
    """_record_collar_trades: collar pairs submitted atomically via record_trades."""

    def _make_pair(self, strategy: str = "paper_nifty_spot") -> list[OverlayTrade]:
        put = _make_trade(strategy=strategy, leg=_COLLAR_PUT_ROLE, key="NSE_FO|11111")
        call_ = _make_trade(
            strategy=strategy, leg=_COLLAR_CALL_ROLE, action=TradeAction.SELL, key="NSE_FO|22222"
        )
        return [_ot(put), _ot(call_)]

    def test_both_inserted_calls_record_trades_once_per_strategy(self) -> None:
        ots = self._make_pair()
        store = MagicMock()
        store.record_trades.return_value = ([ots[0].trade, ots[1].trade], [])
        _record_collar_trades(store, ots)
        store.record_trades.assert_called_once_with([ots[0].trade, ots[1].trade])

    def test_second_leg_conflict_both_skipped(self) -> None:
        """When record_trades returns both in skipped, neither is in the DB."""
        ots = self._make_pair()
        store = MagicMock()
        # Simulates unique-constraint skip for both (atomic — all or nothing)
        store.record_trades.return_value = ([], [ots[0].trade, ots[1].trade])
        _record_collar_trades(store, ots)
        store.record_trades.assert_called_once()

    def test_two_strategies_two_atomic_calls(self) -> None:
        ots = self._make_pair("paper_nifty_spot") + self._make_pair("paper_nifty_proxy")
        store = MagicMock()
        store.record_trades.return_value = ([], [])
        _record_collar_trades(store, ots)
        assert store.record_trades.call_count == 2
