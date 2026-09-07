import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.signals.models import (
    DailySignal,
    Direction,
    FIIData,
    MarketSnapshot,
    OILevel,
    OptionChainSummary,
    SignalOutcome,
    SignalResponse,
    TradeAction,
)
from src.signals.store import SignalStore

TRADE_DATE = date(2026, 9, 7)
ATM = 24000


@pytest.fixture
def store(tmp_path: Path) -> SignalStore:
    s = SignalStore(str(tmp_path / "test.sqlite"))
    s.init_db()
    return s


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        trade_date=TRADE_DATE,
        nifty_spot=Decimal("24000.50"),
        prev_close=Decimal("23900.00"),
        prev_high=Decimal("24050.00"),
        prev_low=Decimal("23850.00"),
        gift_nifty=Decimal("24100.00"),
        india_vix=Decimal("15.5"),
        vix_5d_trend="rising",
        usd_inr=Decimal("83.50"),
        monthly_expiry=date(2026, 9, 24),
        option_chain=OptionChainSummary(
            atm_strike=ATM,
            atm_iv=Decimal("16.0"),
            iv_skew=Decimal("-0.5"),
            pcr_total=Decimal("0.85"),
            pcr_atm=Decimal("0.90"),
            top_call_oi=[OILevel(strike=24100, oi=100000, oi_change=5000)],
            top_put_oi=[OILevel(strike=23900, oi=150000, oi_change=-2000)],
        ),
        fii=FIIData(
            fii_cash_net_cr=Decimal("1500.5"),
            dii_cash_net_cr=Decimal("-500.0"),
        ),
    )


def _response(provider: str = "grok") -> SignalResponse:
    return SignalResponse(
        trade_date=TRADE_DATE,
        provider=provider,
        direction=Direction.BULLISH,
        confidence=4,
        recommended_strike=ATM,
        entry_premium_low=Decimal("80"),
        entry_premium_high=Decimal("100"),
        key_reason="reason",
        key_risk="risk",
        raw_response="{}",
    )


def _signal(recommended_strike: int | None = ATM) -> DailySignal:
    action = TradeAction.BUY_CALL if recommended_strike is not None else TradeAction.NO_TRADE
    return DailySignal(
        trade_date=TRADE_DATE,
        responses=[_response()],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4.0"),
        trade_action=action,
        recommended_strike=recommended_strike,
        agreeing_models=["grok", "gemini"],
        dissenting_models=["gpt4o"],
    )


def _outcome(executed: bool = True, pnl_per_lot: Decimal | None = Decimal("1200")) -> SignalOutcome:
    return SignalOutcome(
        trade_date=TRADE_DATE,
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=ATM,
        entry_premium=Decimal("90"),
        exit_premium=Decimal("110"),
        pnl_per_lot=pnl_per_lot,
        nifty_close=Decimal("24120.00"),
        executed=executed,
        phase="openrouter_only",
        notes="",
    )


def _rows(store: SignalStore, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    from src.db import connect

    with connect(store.db_path) as conn:
        return conn.execute(sql, params).fetchall()


def test_init_db_is_idempotent(store: SignalStore) -> None:
    store.init_db()  # second call, fixture already ran one


def test_record_snapshot_writes_row(store: SignalStore) -> None:
    store.record_snapshot(_snapshot())
    rows = _rows(store, "SELECT trade_date, snapshot_json FROM signal_inputs")
    assert len(rows) == 1
    assert rows[0]["trade_date"] == "2026-09-07"
    assert '"nifty_spot"' in rows[0]["snapshot_json"]


def test_record_snapshot_replaces_on_same_date(store: SignalStore) -> None:
    store.record_snapshot(_snapshot())
    store.record_snapshot(_snapshot())
    assert len(_rows(store, "SELECT 1 FROM signal_inputs")) == 1


def test_record_response_maps_columns(store: SignalStore) -> None:
    store.record_response(_response())
    rows = _rows(store, "SELECT * FROM signal_responses")
    assert len(rows) == 1
    assert rows[0]["strike"] == ATM
    assert rows[0]["premium_low"] == "80"
    assert rows[0]["direction"] == "BULLISH"
    assert rows[0]["created_at"]


def test_record_response_is_insert_or_ignore(store: SignalStore) -> None:
    store.record_response(_response())
    store.record_response(_response())
    assert len(_rows(store, "SELECT 1 FROM signal_responses")) == 1


def test_record_signal_stores_none_strike_as_null(store: SignalStore) -> None:
    store.record_signal(_signal(recommended_strike=None))
    rows = _rows(store, "SELECT recommended_strike, agreeing_models FROM daily_signals")
    assert rows[0]["recommended_strike"] is None
    assert rows[0]["agreeing_models"] == '["grok", "gemini"]'


def test_record_signal_replaces_on_same_date(store: SignalStore) -> None:
    store.record_signal(_signal())
    store.record_signal(_signal(recommended_strike=None))
    rows = _rows(store, "SELECT recommended_strike FROM daily_signals")
    assert len(rows) == 1
    assert rows[0]["recommended_strike"] is None


def test_record_outcome_bool_and_null_handling(store: SignalStore) -> None:
    store.record_outcome(_outcome(executed=False, pnl_per_lot=None))
    rows = _rows(store, "SELECT executed, pnl_per_lot, nifty_close FROM signal_outcomes")
    assert rows[0]["executed"] == 0
    assert rows[0]["pnl_per_lot"] is None
    assert rows[0]["nifty_close"] == "24120.00"


def test_record_outcome_replaces_on_same_date(store: SignalStore) -> None:
    store.record_outcome(_outcome(pnl_per_lot=Decimal("1200")))
    store.record_outcome(_outcome(pnl_per_lot=Decimal("-300")))
    rows = _rows(store, "SELECT pnl_per_lot FROM signal_outcomes")
    assert len(rows) == 1
    assert rows[0]["pnl_per_lot"] == "-300"


def test_get_snapshot_round_trip_preserves_decimals(store: SignalStore) -> None:
    store.record_snapshot(_snapshot())
    got = store.get_snapshot(TRADE_DATE)
    assert got == _snapshot()
    assert got.nifty_spot == Decimal("24000.50")
    assert got.option_chain.pcr_atm == Decimal("0.90")


def test_get_snapshot_missing_date_returns_none(store: SignalStore) -> None:
    assert store.get_snapshot(TRADE_DATE) is None


def test_get_responses_count_and_provider(store: SignalStore) -> None:
    store.record_response(_response("grok"))
    store.record_response(_response("gpt4o"))
    got = store.get_responses(TRADE_DATE)
    assert [r.provider for r in got] == ["gpt4o", "grok"]
    assert got[1].entry_premium_low == Decimal("80")


def test_get_signal_populates_responses(store: SignalStore) -> None:
    store.record_response(_response("grok"))
    store.record_signal(_signal())
    got = store.get_signal(TRADE_DATE)
    assert got is not None
    assert [r.provider for r in got.responses] == ["grok"]
    assert got.consensus_confidence == Decimal("4.0")
    assert got.agreeing_models == ["grok", "gemini"]


def test_get_signal_missing_date_returns_none(store: SignalStore) -> None:
    assert store.get_signal(TRADE_DATE) is None


def test_get_outcome_deserialises_executed_bool(store: SignalStore) -> None:
    store.record_outcome(_outcome(executed=False, pnl_per_lot=None))
    got = store.get_outcome(TRADE_DATE)
    assert got is not None
    assert got.executed is False
    assert got.pnl_per_lot is None
    assert got.nifty_close == Decimal("24120.00")


def test_get_all_outcomes_phase_filter(store: SignalStore) -> None:
    store.record_outcome(_outcome())
    other = _outcome().model_copy(
        update={"trade_date": date(2026, 9, 8), "phase": "search_enabled"}
    )
    store.record_outcome(other)
    got = store.get_all_outcomes(phase="openrouter_only")
    assert [o.trade_date for o in got] == [TRADE_DATE]


def test_get_all_outcomes_date_range_excludes_out_of_range(store: SignalStore) -> None:
    for d in (date(2026, 9, 5), date(2026, 9, 7), date(2026, 9, 9)):
        store.record_outcome(_outcome().model_copy(update={"trade_date": d}))
    got = store.get_all_outcomes(from_date=date(2026, 9, 6), to_date=date(2026, 9, 8))
    assert [o.trade_date for o in got] == [date(2026, 9, 7)]
