"""Unit tests for the signals-paper-track entry executor (SPT-3).

No network, no real DB (file-based SQLite under tmp_path), no real orders.
``resolve_monthly_option`` is monkeypatched; the option chain comes from a fake
broker returning a raw Upstox-shaped payload that the real parser consumes.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.paper.constants import LOT_SIZE, STRATEGY_SIGNAL_TRACK
from src.paper.store import PaperStore
from src.signals.models import TradeAction
from src.strategy.signal_track_v1 import build_signal_entry_message, open_signal_paper_entry

_KEY = "NSE_FO|99999"
_STRIKE = 23000
_EXPIRY = date(2026, 9, 29)
_SIGNAL_DATE = date(2026, 9, 10)


def _leg_dict(ltp: str, bid: str, ask: str) -> dict:
    return {
        "market_data": {"ltp": ltp, "bid_price": bid, "ask_price": ask, "oi": 1000, "volume": 500},
        "option_greeks": {"delta": "0.5", "gamma": "0.01", "theta": "-5", "vega": "10", "iv": "12"},
    }


class _FakeBroker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def get_option_chain(self, instrument: str, expiry: str) -> list[dict]:
        self.calls.append((instrument, expiry))
        return [
            {
                "strike_price": _STRIKE,
                "expiry": expiry,
                "underlying_spot_price": 23041.0,
                "call_options": _leg_dict("40.10", "39.00", "41.00"),
                "put_options": _leg_dict("39.90", "39.00", "41.00"),
            }
        ]


class _FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> bool:
        self.messages.append(text)
        return True


@pytest.fixture
def store(tmp_path) -> PaperStore:
    return PaperStore(tmp_path / "signal_track.db")


def _signal(action: TradeAction) -> SimpleNamespace:
    return SimpleNamespace(
        trade_action=action,
        trade_date=_SIGNAL_DATE,
        recommended_strike=_STRIKE,
        consensus_confidence=Decimal("4"),
    )


def _snapshot() -> SimpleNamespace:
    return SimpleNamespace(
        monthly_expiry=_EXPIRY,
        india_vix=Decimal("12.34"),
        nifty_spot=Decimal("23041.55"),
    )


@pytest.fixture(autouse=True)
def _patch_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.signals.option_resolver.resolve_monthly_option",
        lambda signal, bod_path: _KEY,
    )


@pytest.mark.parametrize(
    ("action", "expected_type", "expected_action"),
    [(TradeAction.BUY_CALL, "CE", "BUY_CALL"), (TradeAction.BUY_PUT, "PE", "BUY_PUT")],
)
async def test_entry_opens_one_row_and_frozen_entry(
    store: PaperStore, action: TradeAction, expected_type: str, expected_action: str
) -> None:
    entry = await open_signal_paper_entry(_signal(action), _snapshot(), _FakeBroker(), store)

    assert entry is not None
    # mid = (39 + 41) / 2 = 40; BUY fill at mid + 1.0 (VIX <= 20 band)
    assert entry.entry_premium == Decimal("41.0")
    assert entry.sl_price == Decimal("41.0") * Decimal("0.70")
    assert entry.tgt_price == Decimal("41.0") * Decimal("1.50")
    assert entry.trade_action == expected_action
    assert entry.instrument_key == _KEY
    assert entry.expiry == _EXPIRY
    assert entry.entry_dte == (_EXPIRY - _SIGNAL_DATE).days
    assert entry.ruleset_version == "v1"

    open_entry = store.get_open_signal_entry()
    assert open_entry is not None and open_entry.trade_id == entry.trade_id

    trades = store.get_trades(STRATEGY_SIGNAL_TRACK)
    assert len(trades) == 1
    assert trades[0].quantity == LOT_SIZE
    assert trades[0].instrument_key == _KEY
    assert expected_type  # option side asserted via entry.trade_action above


async def test_no_trade_is_logged_noop(store: PaperStore) -> None:
    out = await open_signal_paper_entry(
        _signal(TradeAction.NO_TRADE), _snapshot(), _FakeBroker(), store
    )
    assert out is None
    assert store.get_trades(STRATEGY_SIGNAL_TRACK) == []


async def test_already_open_is_noop(store: PaperStore) -> None:
    broker = _FakeBroker()
    first = await open_signal_paper_entry(_signal(TradeAction.BUY_CALL), _snapshot(), broker, store)
    assert first is not None

    second = await open_signal_paper_entry(_signal(TradeAction.BUY_PUT), _snapshot(), broker, store)
    assert second is None
    assert len(store.get_trades(STRATEGY_SIGNAL_TRACK)) == 1


async def test_resolve_failure_is_noop(store: PaperStore, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.signals.option_resolver.resolve_monthly_option", lambda s, p: None)
    out = await open_signal_paper_entry(
        _signal(TradeAction.BUY_CALL), _snapshot(), _FakeBroker(), store
    )
    assert out is None
    assert store.get_trades(STRATEGY_SIGNAL_TRACK) == []


async def test_missing_strike_in_chain_is_noop(store: PaperStore) -> None:
    class _EmptyChainBroker(_FakeBroker):
        async def get_option_chain(self, instrument: str, expiry: str) -> list[dict]:
            return []

    out = await open_signal_paper_entry(
        _signal(TradeAction.BUY_CALL), _snapshot(), _EmptyChainBroker(), store
    )
    assert out is None
    assert store.get_trades(STRATEGY_SIGNAL_TRACK) == []


@pytest.mark.parametrize(
    ("action", "side"), [(TradeAction.BUY_CALL, "CE"), (TradeAction.BUY_PUT, "PE")]
)
async def test_entry_message_sent_for_both_directions(
    store: PaperStore, action: TradeAction, side: str
) -> None:
    notifier = _FakeNotifier()
    await open_signal_paper_entry(
        _signal(action), _snapshot(), _FakeBroker(), store, notifier=notifier
    )

    assert len(notifier.messages) == 1
    msg = notifier.messages[0]
    assert "SIGNAL ENTRY" in msg
    assert "NIFTY 23000" in msg and f" {side}" in msg
    assert "SL" in msg and "Target" in msg
    assert "Inception" in msg


def _make_entry(**over):
    from src.paper.models import SignalPaperEntry

    defaults = dict(
        trade_id=1,
        signal_date=_SIGNAL_DATE,
        trade_action="BUY_PUT",
        instrument_key=_KEY,
        expiry=_EXPIRY,
        entry_dte=19,
        entry_ts=__import__("datetime").datetime(2026, 9, 10, 9, 32),
        entry_premium=Decimal("39.52"),
        entry_bid=Decimal("39.00"),
        entry_ask=Decimal("40.04"),
        entry_slippage=Decimal("1.0"),
        entry_vix=Decimal("12.34"),
        entry_underlying=Decimal("23041.55"),
        signal_confidence=4,
        sl_pct=Decimal("0.30"),
        tgt_pct=Decimal("0.50"),
        sl_price=Decimal("27.664"),
        tgt_price=Decimal("59.28"),
    )
    defaults.update(over)
    return SignalPaperEntry(**defaults)


def test_entry_message_footer_at_zero_prior_trades() -> None:
    msg = build_signal_entry_message(
        _make_entry(), "NIFTY 23000 29 SEP 26 PE", (Decimal("0"), 0, 0, 0)
    )
    # footer is escape_markdown'd outside the fence
    assert "Inception  \\+0\\.00  ·  0 trades  ·  0W / 0L" in msg
    assert msg.startswith("*")
    assert "```" in msg


def test_entry_message_footer_at_n_prior_trades() -> None:
    msg = build_signal_entry_message(
        _make_entry(), "NIFTY 23000 29 SEP 26 PE", (Decimal("12480.50"), 37, 24, 13)
    )
    assert "\\+12,480\\.50" in msg and "37 trades" in msg and "24W / 13L" in msg
    # SL / target rendered 2dp, no rupee sign
    assert "SL 27\\.66" in msg and "Target 59\\.28" in msg
