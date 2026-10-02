"""Tests for src/strategy/expiry_settlement.py (BUG-060, B060.2). Offline — fake broker."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.client.exceptions import DataFetchError
from src.instruments.lookup import InstrumentLookup
from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade, TradeState
from src.paper.store import PaperStore
from src.strategy.expiry_settlement import (
    SETTLEMENT_PRICE_FLOOR,
    ContractSpec,
    ExpiredLeg,
    build_settlement_trade,
    fetch_index_close,
    intrinsic_value,
    settle_expired_legs,
)

STRAT = "paper_nifty_overlay"
EXPIRED = date(2026, 9, 29)  # monthly Tuesday expiry
TODAY = date(2026, 10, 2)
NEXT_TUE = date(2026, 10, 6)

PUT_KEY = "NSE_FO|1001"  # 25000 PE, expired
CALL_KEY = "NSE_FO|1002"  # 24000 CE, expired
LIVE_PUT_KEY = "NSE_FO|1003"  # 25000 PE, expires NEXT_TUE
FUT_KEY = "NSE_FO|2001"
GONE_KEY = "NSE_FO|9999"  # absent from BOD


def _inst(key: str, itype: str, strike: float, expiry: date) -> dict:
    return {
        "instrument_key": key,
        "segment": "NSE_FO",
        "instrument_type": itype,
        "strike_price": strike,
        "expiry": expiry.isoformat(),
        "underlying_symbol": "NIFTY",
    }


@pytest.fixture
def lookup() -> InstrumentLookup:
    return InstrumentLookup(
        [
            _inst(PUT_KEY, "PE", 25000.0, EXPIRED),
            _inst(CALL_KEY, "CE", 24000.0, EXPIRED),
            _inst(LIVE_PUT_KEY, "PE", 25000.0, NEXT_TUE),
            _inst(FUT_KEY, "FUT", 0.0, EXPIRED),
        ]
    )


@pytest.fixture
def store(tmp_path, lookup) -> PaperStore:
    return PaperStore(tmp_path / "paper.sqlite", instrument_lookup=lookup)


class _Broker:
    """Fake BrokerClient: daily NIFTY 50 candles from a {date: close} map."""

    def __init__(self, closes: dict[date, float] | None = None, exc: Exception | None = None):
        self.closes = closes or {}
        self.exc = exc
        self.calls: list[dict] = []

    async def get_historical_candles(self, params: dict) -> list[list]:
        self.calls.append(params)
        if self.exc is not None:
            raise self.exc
        rows = sorted(self.closes.items(), reverse=True)
        return [[f"{d.isoformat()}T00:00:00+05:30", 1, 1, 1, c, 0, 0] for d, c in rows]


def _open(store: PaperStore, role: str, key: str, action: TradeAction, price: str = "100") -> None:
    store.record_trade(
        PaperTrade(
            strategy_name=STRAT,
            leg_role=role,
            instrument_key=key,
            trade_date=date(2026, 8, 12),
            action=action,
            quantity=65,
            price=Decimal(price),
        )
    )


def _states(store: PaperStore, role: str) -> set[TradeState]:
    return {t.state for t in store.get_trades(STRAT, role)}


def _net(store: PaperStore, role: str) -> int:
    return sum(p.net_qty for p in store.get_positions(STRAT) if p.leg_role == role)


# ── Pure ─────────────────────────────────────────────────────────────────


def test_intrinsic_put_itm_otm_and_call_itm():
    assert intrinsic_value("PE", Decimal("25000"), Decimal("24215.35")) == Decimal("784.65")
    assert intrinsic_value("PE", Decimal("25000"), Decimal("25100")) == Decimal("0")
    assert intrinsic_value("CE", Decimal("24000"), Decimal("24215.35")) == Decimal("215.35")
    assert intrinsic_value("CE", Decimal("24500"), Decimal("24215.35")) == Decimal("0")


def test_intrinsic_rejects_bad_option_type():
    with pytest.raises(ValueError):
        intrinsic_value("FUT", Decimal("1"), Decimal("1"))  # type: ignore[arg-type]


def _leg(net_qty: int, opt: str = "PE", strike: str = "25000") -> ExpiredLeg:
    return ExpiredLeg(STRAT, "r", PUT_KEY, net_qty, ContractSpec(Decimal(strike), opt, EXPIRED))


def test_build_settlement_trade_long_sells_short_buys():
    long_close = build_settlement_trade(_leg(65), Decimal("24200"))
    assert (long_close.action, long_close.quantity, long_close.price) == (
        TradeAction.SELL,
        65,
        Decimal("800"),
    )
    assert long_close.trade_date == EXPIRED
    short_close = build_settlement_trade(_leg(-65, "CE", "24000"), Decimal("24200"))
    assert (short_close.action, short_close.price) == (TradeAction.BUY, Decimal("200"))


def test_build_settlement_trade_otm_floors_and_flat_raises():
    assert build_settlement_trade(_leg(65), Decimal("26000")).price == SETTLEMENT_PRICE_FLOOR
    with pytest.raises(ValueError):
        build_settlement_trade(_leg(0), Decimal("24200"))


# ── fetch_index_close ────────────────────────────────────────────────────


async def test_fetch_index_close_picks_exact_date():
    broker = _Broker({date(2026, 9, 28): 24300.1, EXPIRED: 24215.35})
    assert await fetch_index_close(broker, EXPIRED) == Decimal("24215.35")
    assert broker.calls[0]["instrument_key"] == "NSE_INDEX|Nifty 50"


async def test_fetch_index_close_missing_date_or_error_returns_none():
    assert await fetch_index_close(_Broker({date(2026, 9, 28): 24300.0}), EXPIRED) is None
    assert await fetch_index_close(_Broker(exc=DataFetchError("down")), EXPIRED) is None


# ── settle_expired_legs ──────────────────────────────────────────────────


async def test_expired_put_itm_ends_flat_and_closed(store, lookup):
    _open(store, "overlay_collar_put", PUT_KEY, TradeAction.BUY)
    report = await settle_expired_legs(
        store, _Broker({EXPIRED: 24215.35}), lookup, TODAY, dry_run=False
    )
    assert [s.trade.price for s in report.settled] == [Decimal("784.65")]
    assert report.failures == []
    assert _net(store, "overlay_collar_put") == 0
    assert _states(store, "overlay_collar_put") == {TradeState.CLOSED}


async def test_expired_put_otm_settles_at_floor(store, lookup):
    _open(store, "overlay_pp", PUT_KEY, TradeAction.BUY)
    report = await settle_expired_legs(
        store, _Broker({EXPIRED: 25300.0}), lookup, TODAY, dry_run=False
    )
    assert report.settled[0].trade.price == SETTLEMENT_PRICE_FLOOR
    assert _net(store, "overlay_pp") == 0
    assert _states(store, "overlay_pp") == {TradeState.CLOSED}


async def test_expired_short_call_itm_bought_back_at_intrinsic(store, lookup):
    _open(store, "overlay_cc", CALL_KEY, TradeAction.SELL)
    report = await settle_expired_legs(
        store, _Broker({EXPIRED: 24215.35}), lookup, TODAY, dry_run=False
    )
    trade = report.settled[0].trade
    assert (trade.action, trade.price) == (TradeAction.BUY, Decimal("215.35"))
    assert _net(store, "overlay_cc") == 0


async def test_leg_expiring_today_or_later_untouched(store, lookup):
    _open(store, "overlay_pp", LIVE_PUT_KEY, TradeAction.BUY)
    broker = _Broker({NEXT_TUE: 24000.0})
    for run_date in (TODAY, NEXT_TUE):
        report = await settle_expired_legs(store, broker, lookup, run_date, dry_run=False)
        assert report.settled == [] and report.failures == []
    assert broker.calls == []
    assert _net(store, "overlay_pp") == 65
    assert _states(store, "overlay_pp") == {TradeState.OPEN}


async def test_price_source_failure_leaves_leg_open(store, lookup):
    _open(store, "overlay_collar_put", PUT_KEY, TradeAction.BUY)
    report = await settle_expired_legs(
        store, _Broker(exc=DataFetchError("503")), lookup, TODAY, dry_run=False
    )
    assert report.settled == []
    assert [(f.instrument_key, f.reason) for f in report.failures] == [
        (PUT_KEY, "no NIFTY 50 close for 2026-09-29")
    ]
    assert _net(store, "overlay_collar_put") == 65
    assert _states(store, "overlay_collar_put") == {TradeState.OPEN}


async def test_rerun_is_noop(store, lookup):
    _open(store, "overlay_collar_put", PUT_KEY, TradeAction.BUY)
    broker = _Broker({EXPIRED: 24215.35})
    await settle_expired_legs(store, broker, lookup, TODAY, dry_run=False)
    second = await settle_expired_legs(store, broker, lookup, TODAY, dry_run=False)
    assert second.settled == [] and second.failures == []
    assert len(store.get_trades(STRAT)) == 2


async def test_defended_leg_is_settled(store, lookup):
    _open(store, "short_put", PUT_KEY, TradeAction.SELL)
    store.mark_trade_defended(STRAT, "short_put", PUT_KEY)
    assert _states(store, "short_put") == {TradeState.DEFENDED}
    report = await settle_expired_legs(
        store, _Broker({EXPIRED: 24215.35}), lookup, TODAY, dry_run=False
    )
    assert report.settled[0].trade.action == TradeAction.BUY
    assert _net(store, "short_put") == 0
    assert _states(store, "short_put") == {TradeState.CLOSED}


async def test_dry_run_writes_nothing(store, lookup):
    _open(store, "overlay_collar_put", PUT_KEY, TradeAction.BUY)
    report = await settle_expired_legs(store, _Broker({EXPIRED: 24215.35}), lookup, TODAY)
    assert len(report.settled) == 1
    assert len(store.get_trades(STRAT)) == 1
    assert _states(store, "overlay_collar_put") == {TradeState.OPEN}


async def test_contract_missing_from_bod_fails_closed_unless_overridden(store, lookup):
    _open(store, "overlay_collar_put", GONE_KEY, TradeAction.BUY)
    broker = _Broker({EXPIRED: 24215.35})
    report = await settle_expired_legs(store, broker, lookup, TODAY, dry_run=False)
    assert [f.reason for f in report.failures] == ["contract not resolvable"]
    assert _net(store, "overlay_collar_put") == 65

    override = {GONE_KEY: ContractSpec(Decimal("25000"), "PE", EXPIRED)}
    report = await settle_expired_legs(
        store, broker, lookup, TODAY, dry_run=False, overrides=override
    )
    assert report.settled[0].trade.price == Decimal("784.65")
    assert _net(store, "overlay_collar_put") == 0


async def test_non_option_legs_skipped(store, lookup):
    _open(store, "base_futures", FUT_KEY, TradeAction.BUY)
    report = await settle_expired_legs(store, _Broker(), lookup, TODAY, dry_run=False)
    assert report.settled == [] and report.failures == []
    assert _net(store, "base_futures") == 65


async def test_duplicate_guard_blocks_close_without_marking(store, lookup):
    _open(store, "overlay_pp", PUT_KEY, TradeAction.BUY)
    _open(store, "overlay_pp", PUT_KEY, TradeAction.BUY)  # dup → ignored; net stays 65
    store.record_trade(  # a partial SELL already dated on expiry day
        PaperTrade(
            strategy_name=STRAT,
            leg_role="overlay_pp",
            instrument_key=PUT_KEY,
            trade_date=EXPIRED,
            action=TradeAction.SELL,
            quantity=15,
            price=Decimal("700"),
        )
    )
    report = await settle_expired_legs(
        store, _Broker({EXPIRED: 24215.35}), lookup, TODAY, dry_run=False
    )
    assert [f.reason for f in report.failures] == ["closing trade blocked by duplicate guard"]
    assert _net(store, "overlay_pp") == 50
    assert TradeState.CLOSED not in _states(store, "overlay_pp")
