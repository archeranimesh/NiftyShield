import asyncio
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import ExitSignal, PaperTrade, TradeAction
from src.paper.store import PaperStore
from src.strategy.executor import PaperFillSimulator
from src.strategy.overlay_closer import OverlayCloser
from src.strategy.protocol import ApprovedAction


class MockNotifier:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    def send(self, msg: str) -> bool:
        self.sent_messages.append(msg)
        return True


def _make_call_leg(
    ltp: str,
    delta: str,
    strike: str = "24500",
) -> OptionLeg:
    return OptionLeg(
        ltp=Decimal(ltp),
        bid=Decimal(ltp),
        ask=Decimal(ltp),
        oi=1000,
        volume=500,
        delta=Decimal(delta),
        gamma=Decimal("0.001"),
        theta=Decimal("-5"),
        vega=Decimal("10"),
        iv=Decimal("15.0"),
        strike=Decimal(strike),
    )


def _make_put_leg(
    ltp: str,
    delta: str,
    bid: str | None = None,
    ask: str | None = None,
    strike: str = "21500",
) -> OptionLeg:
    bid_val = Decimal(bid) if bid is not None else Decimal(ltp)
    ask_val = Decimal(ask) if ask is not None else Decimal(ltp)
    return OptionLeg(
        ltp=Decimal(ltp),
        bid=bid_val,
        ask=ask_val,
        oi=1000,
        volume=500,
        delta=Decimal(delta),
        gamma=Decimal("0.001"),
        theta=Decimal("-5"),
        vega=Decimal("10"),
        iv=Decimal("15.0"),
        strike=Decimal(strike),
    )


def _make_chain(
    call_ltp: str,
    call_delta: str,
    put_ltp: str,
    put_delta: str,
    put_bid: str | None = None,
    put_ask: str | None = None,
    call_strike: str = "24500",
    put_strike: str = "21500",
) -> OptionChain:
    ce = _make_call_leg(ltp=call_ltp, delta=call_delta, strike=call_strike)
    pe = _make_put_leg(ltp=put_ltp, delta=put_delta, bid=put_bid, ask=put_ask, strike=put_strike)
    return OptionChain(
        underlying_spot=Decimal("23000"),
        expiry=date(2026, 6, 26),
        strikes={
            Decimal(call_strike): OptionChainStrike(ce=ce),
            Decimal(put_strike): OptionChainStrike(pe=pe),
        },
    )


@pytest.fixture
def store(tmp_path: Any) -> PaperStore:
    db_file = tmp_path / "test.sqlite"
    return PaperStore(str(db_file))


@pytest.fixture
def simulator() -> PaperFillSimulator:
    return PaperFillSimulator()


@pytest.fixture
def notifier() -> MockNotifier:
    return MockNotifier()


@pytest.fixture
def closer(
    store: PaperStore, simulator: PaperFillSimulator, notifier: MockNotifier
) -> OverlayCloser:
    return OverlayCloser(store, simulator, notifier)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_close_single_leg_happy_path(store: PaperStore, closer: OverlayCloser) -> None:
    # 1. Seed entry trade for CC
    entry = PaperTrade(
        strategy_name="paper_covered_call_v1",
        leg_role="short_call",
        instrument_key="NSE_FO|NIFTY24500CE",
        trade_date=date.today(),
        action=TradeAction.SELL,
        quantity=65,
        price=Decimal("80.0"),
        notes="entry",
        ivr_at_entry=0.30,
        is_paper=True,
    )
    store.record_trade(entry)

    # 2. Create exit event
    event_id = store.create_exit_event(
        strategy_name="paper_covered_call_v1",
        leg_name="short_call",
        trade_id="0",
        event_time=datetime.now(timezone.utc),
        detected_by="INTRADAY",
        exit_signal=ExitSignal.PROFIT_TARGET,
        severity="ACTION",
        entry_price=Decimal("80.0"),
    )

    # 3. Close it
    chain = _make_chain("35", "0.20", "20", "-0.10")
    closer.close_single_leg(
        strategy_name="paper_covered_call_v1",
        leg_role="short_call",
        market=chain,
        event_id=event_id,
        vix=15.0,
        is_loss_stop=False,
    )

    # 4. Verify position is now closed
    pos = store.get_position("paper_covered_call_v1", "short_call")
    assert pos.net_qty == 0

    # 5. Verify exit event is ACTED
    open_events = store.get_open_exit_events("paper_covered_call_v1")
    assert not any(e["id"] == event_id for e in open_events)


def test_close_single_leg_loss_stop_slippage(store: PaperStore, closer: OverlayCloser) -> None:
    # Seed short call
    entry = PaperTrade(
        strategy_name="paper_covered_call_v1",
        leg_role="short_call",
        instrument_key="NSE_FO|NIFTY24500CE",
        trade_date=date.today(),
        action=TradeAction.SELL,
        quantity=65,
        price=Decimal("80.0"),
        notes="entry",
        is_paper=True,
    )
    store.record_trade(entry)

    chain = _make_chain("200", "0.60", "20", "-0.10")  # 200 LTP (loss stop)

    # Close with is_loss_stop=True
    closer.close_single_leg(
        strategy_name="paper_covered_call_v1",
        leg_role="short_call",
        market=chain,
        event_id=None,
        vix=15.0,
        is_loss_stop=True,
    )

    # VIX 15.0 has slippage of 1.0. For loss stop, it should be 1.5x, i.e. 1.5.
    # Mid = 200. Action is BUY back, so fill_price = mid + 1.5 = 201.5.
    trades = store.get_trades("paper_covered_call_v1", "short_call")
    close_trade = next(t for t in trades if t.action == TradeAction.BUY)
    assert close_trade.price == Decimal("201.5")


def test_close_single_leg_with_dual_audit(store: PaperStore, closer: OverlayCloser) -> None:
    entry = PaperTrade(
        strategy_name="paper_covered_call_v1",
        leg_role="short_call",
        instrument_key="NSE_FO|NIFTY24500CE",
        trade_date=date.today(),
        action=TradeAction.SELL,
        quantity=65,
        price=Decimal("80.0"),
        notes="entry",
        is_paper=True,
    )
    store.record_trade(entry)

    event_id = store.create_exit_event(
        strategy_name="paper_covered_call_v1",
        leg_name="short_call",
        trade_id="0",
        event_time=datetime.now(timezone.utc),
        detected_by="INTRADAY",
        exit_signal=ExitSignal.LOSS_STOP,
        severity="ACTION",
        entry_price=Decimal("80.0"),
    )

    chain = _make_chain("200", "0.60", "20", "-0.10")
    audit = {
        "delta_stop_would_fire": True,
        "premium_stop_would_fire": True,
        "actual_rule_used": "BOTH",
    }

    closer.close_single_leg(
        strategy_name="paper_covered_call_v1",
        leg_role="short_call",
        market=chain,
        event_id=event_id,
        vix=15.0,
        is_loss_stop=True,
        dual_signal_audit=audit,
    )

    # Query resolved event from database directly to verify audit fields
    with sqlite3.connect(store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT delta_stop_would_fire, premium_stop_would_fire, actual_rule_used FROM paper_exit_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        assert row["delta_stop_would_fire"] == 1
        assert row["premium_stop_would_fire"] == 1
        assert row["actual_rule_used"] == "BOTH"


def test_close_collar_all_happy_path(store: PaperStore, closer: OverlayCloser) -> None:
    # Seed short call and long put
    t1 = PaperTrade(
        strategy_name="paper_collar_v1",
        leg_role="collar_short_call",
        instrument_key="NSE_FO|NIFTY24500CE",
        trade_date=date.today(),
        action=TradeAction.SELL,
        quantity=65,
        price=Decimal("80"),
        is_paper=True,
    )
    t2 = PaperTrade(
        strategy_name="paper_collar_v1",
        leg_role="collar_long_put",
        instrument_key="NSE_FO|NIFTY21500PE",
        trade_date=date.today(),
        action=TradeAction.BUY,
        quantity=65,
        price=Decimal("50"),
        is_paper=True,
    )
    store.record_trade(t1)
    store.record_trade(t2)

    chain = _make_chain("10", "0.05", "20", "-0.10")
    closer.close_collar_all("paper_collar_v1", chain, None, 15.0)

    # Verify both legs are closed
    assert store.get_position("paper_collar_v1", "collar_short_call").net_qty == 0
    assert store.get_position("paper_collar_v1", "collar_long_put").net_qty == 0


def test_close_collar_all_rollback(
    store: PaperStore, closer: OverlayCloser, notifier: MockNotifier
) -> None:
    # Seed short call and long put
    t1 = PaperTrade(
        strategy_name="paper_collar_v1",
        leg_role="collar_short_call",
        instrument_key="NSE_FO|NIFTY24500CE",
        trade_date=date.today(),
        action=TradeAction.SELL,
        quantity=65,
        price=Decimal("80"),
        is_paper=True,
    )
    t2 = PaperTrade(
        strategy_name="paper_collar_v1",
        leg_role="collar_long_put",
        instrument_key="NSE_FO|NIFTY21500PE",
        trade_date=date.today(),
        action=TradeAction.BUY,
        quantity=65,
        price=Decimal("50"),
        is_paper=True,
    )
    store.record_trade(t1)
    store.record_trade(t2)

    # Mock store to fail on put record_trade
    original_record = store.record_trade

    def mock_record(trade: PaperTrade) -> bool:
        if trade.leg_role == "collar_long_put":
            raise ValueError("Simulated DB error")
        return original_record(trade)

    store.record_trade = mock_record  # type: ignore[method-assign]

    chain = _make_chain("10", "0.05", "20", "-0.10")
    closer.close_collar_all("paper_collar_v1", chain, None, 15.0)

    # Verify call leg was rolled back (is still open)
    pos = store.get_position("paper_collar_v1", "collar_short_call")
    assert pos.net_qty == -65
    assert len(notifier.sent_messages) == 1
    assert "Collar close failed" in notifier.sent_messages[0]


def test_monetize_collar_put(store: PaperStore, closer: OverlayCloser) -> None:
    t1 = PaperTrade(
        strategy_name="paper_collar_v1",
        leg_role="collar_short_call",
        instrument_key="NSE_FO|NIFTY24500CE",
        trade_date=date.today(),
        action=TradeAction.SELL,
        quantity=65,
        price=Decimal("80"),
        is_paper=True,
    )
    t2 = PaperTrade(
        strategy_name="paper_collar_v1",
        leg_role="collar_long_put",
        instrument_key="NSE_FO|NIFTY21500PE",
        trade_date=date.today(),
        action=TradeAction.BUY,
        quantity=65,
        price=Decimal("50"),
        is_paper=True,
    )
    store.record_trade(t1)
    store.record_trade(t2)

    # Case 1: call residual (ltp) = 4.0 (< 5.0) -> call should be closed
    chain = _make_chain("4.0", "0.05", "250", "-0.85")
    closer.monetize_collar_put("paper_collar_v1", chain, None, 15.0)

    assert store.get_position("paper_collar_v1", "collar_short_call").net_qty == 0
    assert store.get_position("paper_collar_v1", "collar_long_put").net_qty == 0


def test_route(store: PaperStore, closer: OverlayCloser) -> None:
    # Test route mapping for CLOSE_CC
    entry = PaperTrade(
        strategy_name="paper_covered_call_v1",
        leg_role="short_call",
        instrument_key="NSE_FO|NIFTY24500CE",
        trade_date=date.today(),
        action=TradeAction.SELL,
        quantity=65,
        price=Decimal("80.0"),
        is_paper=True,
    )
    store.record_trade(entry)

    action = ApprovedAction(
        action_type="CLOSE_CC",
        legs_to_close=["short_call"],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    chain = _make_chain("35", "0.20", "20", "-0.10")
    result = _run(closer.route("paper_covered_call_v1", action, chain, None, 15.0))
    # verify position is closed
    assert all(p.leg_role != "short_call" for p in result if p.net_qty != 0)
