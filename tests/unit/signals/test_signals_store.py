import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.db import connect
from src.signals.models import (
    DailySignal,
    Direction,
    FIIData,
    MarketSnapshot,
    OILevel,
    OptionChainSummary,
    SignalOutcome,
    SignalResponse,
    SignalUsage,
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


def _usage(cost: str = "0.0031") -> SignalUsage:
    return SignalUsage(prompt_tokens=1200, completion_tokens=40, cost_usd=Decimal(cost))


def _signal(
    recommended_strike: int | None = ATM,
    entry_premium: Decimal | None = None,
) -> DailySignal:
    action = TradeAction.BUY_CALL if recommended_strike is not None else TradeAction.NO_TRADE
    return DailySignal(
        trade_date=TRADE_DATE,
        responses=[_response()],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4.0"),
        trade_action=action,
        recommended_strike=recommended_strike,
        entry_premium=entry_premium,
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
    with connect(store.db_path) as conn:
        return conn.execute(sql, params).fetchall()


def test_init_db_is_idempotent(store: SignalStore) -> None:
    store.init_db()  # second call, fixture already ran one


def test_init_db_migration_applies_and_hydrates(tmp_path: Path) -> None:
    db_path = tmp_path / "migration.sqlite"
    s = SignalStore(str(db_path))
    s.db_path.parent.mkdir(parents=True, exist_ok=True)

    with connect(s.db_path) as conn:
        # Create old schema without entry_premium
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS daily_signals (
                trade_date           TEXT PRIMARY KEY,
                consensus_direction  TEXT NOT NULL,
                consensus_confidence TEXT NOT NULL,
                trade_action         TEXT NOT NULL,
                recommended_strike   INTEGER,
                agreeing_models      TEXT NOT NULL,
                dissenting_models    TEXT NOT NULL,
                created_at           TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO daily_signals VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "2026-04-06",
                "BULLISH",
                "4.0",
                "BUY_CALL",
                22500,
                "[]",
                "[]",
                "2026-04-06T15:00:00Z",
            ),
        )

    s.init_db()  # Should run ALTER TABLE successfully

    # Assert column exists and existing row reads back with entry_premium = None
    with connect(s.db_path) as conn:
        row = conn.execute("SELECT entry_premium FROM daily_signals").fetchone()
    assert row["entry_premium"] is None

    # And get_signal should hydrate it as None
    loaded = s.get_signal(date(2026, 4, 6))
    assert loaded is not None
    assert loaded.entry_premium is None


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


def test_record_signal_entry_premium_round_trip(store: SignalStore) -> None:
    store.record_response(_response("grok"))  # for get_signal to hydrate responses
    store.record_signal(_signal(entry_premium=Decimal("150.75")))
    got = store.get_signal(TRADE_DATE)
    assert got is not None
    assert got.entry_premium == Decimal("150.75")

    rows = _rows(store, "SELECT entry_premium FROM daily_signals")
    assert rows[0]["entry_premium"] == "150.75"


def test_record_outcome_bool_and_null_handling(store: SignalStore) -> None:
    store.record_outcome(_outcome(executed=False, pnl_per_lot=None))
    rows = _rows(store, "SELECT executed, pnl_per_lot, nifty_close FROM signal_outcomes")
    assert rows[0]["executed"] == 0
    assert rows[0]["pnl_per_lot"] is None
    assert rows[0]["nifty_close"] == "24120.00"


def test_signal_outcome_high_low_round_trip(store: SignalStore) -> None:
    outcome = _outcome().model_copy(
        update={
            "high_pnl_per_lot": Decimal("1500"),
            "low_pnl_per_lot": Decimal("-300"),
        }
    )
    store.record_outcome(outcome)
    got = store.get_outcome(TRADE_DATE)
    assert got is not None
    assert got.high_pnl_per_lot == Decimal("1500")
    assert got.low_pnl_per_lot == Decimal("-300")


def test_init_db_migration_idempotent_on_existing_columns(store: SignalStore) -> None:
    store.init_db()
    store.record_outcome(_outcome())
    got = store.get_outcome(TRADE_DATE)
    assert got is not None


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


def test_get_recent_snapshots_newest_first(store: SignalStore) -> None:
    base = _snapshot()
    for offset, vix in ((0, "10"), (1, "11"), (2, "12")):
        store.record_snapshot(
            base.model_copy(
                update={
                    "trade_date": date(2026, 9, 1 + offset),
                    "india_vix": Decimal(vix),
                }
            )
        )
    got = store.get_recent_snapshots(2)
    assert [s.trade_date for s in got] == [date(2026, 9, 3), date(2026, 9, 2)]
    assert got[0].india_vix == Decimal("12")


def test_get_recent_snapshots_fewer_rows_than_requested(store: SignalStore) -> None:
    store.record_snapshot(_snapshot())
    got = store.get_recent_snapshots(5)
    assert len(got) == 1


def test_get_recent_snapshots_non_positive_n_returns_empty(store: SignalStore) -> None:
    store.record_snapshot(_snapshot())
    assert store.get_recent_snapshots(0) == []
    assert store.get_recent_snapshots(-3) == []


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


def test_record_response_persists_usage(store: SignalStore) -> None:
    store.record_response(_response("grok").model_copy(update={"usage": _usage()}))
    got = store.get_responses(TRADE_DATE)[0]
    assert got.usage is not None
    assert got.usage.cost_usd == Decimal("0.0031")
    assert got.usage.prompt_tokens == 1200
    assert got.usage.completion_tokens == 40


def test_record_response_null_usage(store: SignalStore) -> None:
    store.record_response(_response("grok"))
    assert store.get_responses(TRADE_DATE)[0].usage is None


def test_get_signal_cost_aggregates(store: SignalStore) -> None:
    store.record_response(_response("grok").model_copy(update={"usage": _usage("0.0010")}))
    store.record_response(_response("gpt4o").model_copy(update={"usage": _usage("0.0020")}))
    store.record_response(
        _response("gemini").model_copy(
            update={"trade_date": date(2026, 9, 8), "usage": _usage("0.0030")}
        )
    )
    cost = store.get_signal_cost()
    assert cost["total_usd"] == Decimal("0.0060")
    assert cost["call_count"] == 3
    assert set(cost["by_provider"]) == {"grok", "gpt4o", "gemini"}


def test_get_signal_cost_date_filter(store: SignalStore) -> None:
    store.record_response(_response("grok").model_copy(update={"usage": _usage("0.0010")}))
    store.record_response(
        _response("gpt4o").model_copy(
            update={"trade_date": date(2026, 9, 1), "usage": _usage("0.0020")}
        )
    )
    cost = store.get_signal_cost(from_date=TRADE_DATE)
    assert cost["call_count"] == 1
    assert cost["total_usd"] == Decimal("0.0010")


def test_get_signal_cost_empty(store: SignalStore) -> None:
    assert store.get_signal_cost() == {
        "total_usd": Decimal("0"),
        "call_count": 0,
        "by_provider": {},
    }


def test_init_db_idempotent_with_cost_columns(store: SignalStore) -> None:
    store.init_db()
    store.init_db()
    store.record_response(_response("grok").model_copy(update={"usage": _usage()}))
    assert store.get_responses(TRADE_DATE)[0].usage is not None
