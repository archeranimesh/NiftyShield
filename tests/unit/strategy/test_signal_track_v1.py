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
        is_actionable=(action is not TradeAction.NO_TRADE),
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


# ---------------------------------------------------------------------------
# SPT-4 — monitor registration (30s) + mark-path logging
# ---------------------------------------------------------------------------

from datetime import datetime as _dt  # noqa: E402
from datetime import timedelta as _timedelta  # noqa: E402
from zoneinfo import ZoneInfo as _ZoneInfo  # noqa: E402

from src.client.upstox_market import parse_upstox_option_chain  # noqa: E402
from src.models.options import OptionChain as _OptionChain  # noqa: E402
from src.models.portfolio import TradeAction as _TradeAction  # noqa: E402
from src.paper.models import PaperTrade as _PaperTrade  # noqa: E402
from src.strategy.signal_track_v1 import SignalTrackV1, _compute_mark  # noqa: E402

_IST = _ZoneInfo("Asia/Kolkata")
_SYM_KEY = "NSE_FO|NIFTY23000PE"


def _chain(bid: str, ask: str, ltp: str) -> _OptionChain:
    raw = [
        {
            "strike_price": _STRIKE,
            "expiry": _EXPIRY.isoformat(),
            "underlying_spot_price": 23041.0,
            "call_options": _leg_dict(ltp, bid, ask),
            "put_options": _leg_dict(ltp, bid, ask),
        }
    ]
    return parse_upstox_option_chain(raw)


def _open_entry(store: PaperStore, *, sl_price: str, tgt_price: str, premium: str = "40") -> int:
    """Persist a real open paper_trades row + SignalPaperEntry, return trade_id."""
    trade = _PaperTrade(
        strategy_name=STRATEGY_SIGNAL_TRACK,
        leg_role="signal_long",
        instrument_key=_SYM_KEY,
        trade_date=_SIGNAL_DATE,
        action=_TradeAction.BUY,
        quantity=LOT_SIZE,
        price=Decimal(premium),
        notes="test entry",
        is_paper=True,
    )
    trade_id = store.record_signal_open_leg(trade)
    entry = _make_entry(
        trade_id=trade_id,
        entry_premium=Decimal(premium),
        sl_price=Decimal(sl_price),
        tgt_price=Decimal(tgt_price),
        instrument_key=_SYM_KEY,
    )
    store.open_signal_entry(entry)
    return trade_id


async def test_due_tick_stop_loss_routes(store: PaperStore) -> None:
    _open_entry(store, sl_price="35", tgt_price="60")
    strategy = SignalTrackV1(store=store, clock=lambda: _dt(2026, 9, 10, 10, 0, tzinfo=_IST))
    chain = _chain(bid="30.00", ask="30.00", ltp="30.00")  # mark=30 <= sl_price=35

    events = await strategy.check_signals(chain, [])

    assert events == []
    assert strategy._exit_fired_trade_ids  # a decision fired
    marks = store.get_marks(next(iter(strategy._exit_fired_trade_ids)))
    assert len(marks) == 1
    assert marks[0].mark == Decimal("30.00")


async def test_dead_band_tick_is_hold_and_writes_mark(store: PaperStore) -> None:
    trade_id = _open_entry(store, sl_price="28", tgt_price="60")
    strategy = SignalTrackV1(store=store, clock=lambda: _dt(2026, 9, 10, 10, 0, tzinfo=_IST))
    chain = _chain(bid="40.00", ask="40.00", ltp="40.00")  # dead band

    events = await strategy.check_signals(chain, [])

    assert events == []
    assert trade_id not in strategy._exit_fired_trade_ids
    marks = store.get_marks(trade_id)
    assert len(marks) == 1
    assert marks[0].gap_event is False


async def test_second_tick_after_exit_does_not_refire(store: PaperStore) -> None:
    trade_id = _open_entry(store, sl_price="35", tgt_price="60")
    strategy = SignalTrackV1(store=store, clock=lambda: _dt(2026, 9, 10, 10, 0, tzinfo=_IST))
    chain = _chain(bid="30.00", ask="30.00", ltp="30.00")

    await strategy.check_signals(chain, [])
    assert len(store.get_marks(trade_id)) == 1

    await strategy.check_signals(chain, [])  # second tick, same open entry
    assert len(store.get_marks(trade_id)) == 1  # no new mark row — dedup short-circuits


def test_stale_set_on_old_quote_timestamp() -> None:
    entry = _make_entry(entry_premium=Decimal("40"))
    leg = SimpleNamespace(ltp=Decimal("40"), bid=Decimal("39"), ask=Decimal("41"))
    now = _dt(2026, 9, 10, 10, 0, tzinfo=_IST)
    old_quote_ts = now - _timedelta(seconds=45)

    mark = _compute_mark(
        entry,
        leg,
        now=now,
        quote_ts=old_quote_ts,
        prev_mark=None,
        prev_mfe_pct=Decimal("0"),
        prev_mae_pct=Decimal("0"),
    )

    assert mark.stale is True


def test_gap_event_on_large_inter_tick_jump() -> None:
    entry = _make_entry(entry_premium=Decimal("40"))
    leg = SimpleNamespace(ltp=Decimal("60"), bid=Decimal("59"), ask=Decimal("61"))
    now = _dt(2026, 9, 10, 10, 0, tzinfo=_IST)

    # prev_mark=40 -> new mark=60: |60-40|/40 = 0.50 > 0.20
    mark = _compute_mark(
        entry,
        leg,
        now=now,
        quote_ts=None,
        prev_mark=Decimal("40"),
        prev_mfe_pct=Decimal("0"),
        prev_mae_pct=Decimal("0"),
    )

    assert mark.gap_event is True


# ---------------------------------------------------------------------------
# SPT-5 — exit engine caller-side wiring
# ---------------------------------------------------------------------------


async def test_stop_loss_tick_closes_and_records_pnl(store: PaperStore) -> None:
    trade_id = _open_entry(store, sl_price="35", tgt_price="60", premium="40")
    notifier = _FakeNotifier()
    strategy = SignalTrackV1(
        store=store, notifier=notifier, clock=lambda: _dt(2026, 9, 10, 10, 0, tzinfo=_IST)
    )
    chain = _chain(bid="30.00", ask="30.00", ltp="30.00")  # mark=30 <= sl_price=35

    await strategy.check_signals(chain, [])

    open_entry = store.get_open_signal_entry()
    assert open_entry is None  # position closed

    trades = store.get_trades(STRATEGY_SIGNAL_TRACK)
    sell_trades = [t for t in trades if t.action.value == "SELL"]
    assert len(sell_trades) == 1
    # SELL fill = mid(30) - slippage(1.0, VIX<=20 band) = 29.0
    assert sell_trades[0].price == Decimal("29.0")

    total, n_closed, wins, losses = store.cumulative_pnl()
    assert n_closed == 1
    assert losses == 1 and wins == 0
    # pnl = (29.0 - 40) * LOT_SIZE
    assert total == (Decimal("29.0") - Decimal("40")) * LOT_SIZE

    assert len(notifier.messages) == 1
    msg = notifier.messages[0]
    assert "SIGNAL EXIT" in msg and "STOP" in msg and "LOSS" in msg
    _ = trade_id


async def test_target_tick_closes_as_win(store: PaperStore) -> None:
    _open_entry(store, sl_price="20", tgt_price="55", premium="40")
    strategy = SignalTrackV1(store=store, clock=lambda: _dt(2026, 9, 10, 10, 0, tzinfo=_IST))
    chain = _chain(bid="60.00", ask="60.00", ltp="60.00")  # mark=60 >= tgt_price=55

    await strategy.check_signals(chain, [])

    total, n_closed, wins, losses = store.cumulative_pnl()
    assert n_closed == 1
    assert wins == 1 and losses == 0
    # SELL fill = mid(60) - slippage(1.0) = 59.0 > entry(40) -> win
    assert total == (Decimal("59.0") - Decimal("40")) * LOT_SIZE


async def test_gap_through_books_actual_mark_not_threshold(store: PaperStore) -> None:
    """A tick that jumps straight past the SL realises the gapped price, not the SL level."""
    _open_entry(store, sl_price="28", tgt_price="60", premium="40")
    strategy = SignalTrackV1(store=store, clock=lambda: _dt(2026, 9, 10, 10, 0, tzinfo=_IST))
    chain = _chain(bid="24.00", ask="24.00", ltp="24.00")  # mark=24, well past sl_price=28

    await strategy.check_signals(chain, [])

    total, n_closed, _, _ = store.cumulative_pnl()
    assert n_closed == 1
    # fill = mid(24) - slippage(1.0) = 23.0, booked as-is (not clamped to sl_price=28)
    assert total == (Decimal("23.0") - Decimal("40")) * LOT_SIZE


async def test_exit_fires_exactly_once_on_repeat_ticks(store: PaperStore) -> None:
    trade_id = _open_entry(store, sl_price="35", tgt_price="60", premium="40")
    strategy = SignalTrackV1(store=store, clock=lambda: _dt(2026, 9, 10, 10, 0, tzinfo=_IST))
    chain = _chain(bid="30.00", ask="30.00", ltp="30.00")

    await strategy.check_signals(chain, [])
    await strategy.check_signals(chain, [])  # stray re-tick after close

    trades = store.get_trades(STRATEGY_SIGNAL_TRACK)
    sell_trades = [t for t in trades if t.action.value == "SELL"]
    assert len(sell_trades) == 1  # no double-close
    _, n_closed, _, _ = store.cumulative_pnl()
    assert n_closed == 1
    _ = trade_id


def test_exit_message_renders_for_win_and_loss() -> None:
    entry = _make_entry(
        entry_premium=Decimal("40"), sl_price=Decimal("28"), tgt_price=Decimal("60")
    )
    now = _dt(2026, 9, 10, 13, 42, tzinfo=_IST)

    from src.strategy.signal_exit import SignalExitReason
    from src.strategy.signal_track_v1 import build_signal_exit_message

    win_msg = build_signal_exit_message(
        entry,
        "NIFTY 23000 29 SEP 26 PE",
        SignalExitReason.TARGET,
        Decimal("59.0"),
        Decimal("1235.00"),
        now,
        Decimal("23088"),
        (Decimal("1235.00"), 1, 1, 0),
    )
    assert "SIGNAL EXIT" in win_msg and "TARGET" in win_msg
    assert "1,235\\.00" in win_msg or "1,235.00" in win_msg

    loss_msg = build_signal_exit_message(
        entry,
        "NIFTY 23000 29 SEP 26 PE",
        SignalExitReason.STOP_LOSS,
        Decimal("29.0"),
        Decimal("-715.00"),
        now,
        Decimal("22950"),
        (Decimal("-715.00"), 1, 0, 1),
    )
    assert "SIGNAL EXIT" in loss_msg and "STOP" in loss_msg and "LOSS" in loss_msg


def test_mfe_mae_monotonic_across_ticks() -> None:
    entry = _make_entry(entry_premium=Decimal("40"))
    now = _dt(2026, 9, 10, 10, 0, tzinfo=_IST)

    m1 = _compute_mark(
        entry,
        SimpleNamespace(ltp=Decimal("44"), bid=Decimal("43"), ask=Decimal("45")),
        now=now,
        quote_ts=None,
        prev_mark=None,
        prev_mfe_pct=Decimal("0"),
        prev_mae_pct=Decimal("0"),
    )
    assert m1.mfe_pct == Decimal("0.1")  # (44/40)-1
    assert m1.mae_pct == Decimal("0")

    m2 = _compute_mark(
        entry,
        SimpleNamespace(ltp=Decimal("36"), bid=Decimal("35"), ask=Decimal("37")),
        now=now,
        quote_ts=None,
        prev_mark=m1.mark,
        prev_mfe_pct=m1.mfe_pct,
        prev_mae_pct=m1.mae_pct,
    )
    assert m2.mfe_pct == Decimal("0.1")  # unchanged — never regresses
    assert m2.mae_pct == Decimal("-0.1")  # (36/40)-1

    m3 = _compute_mark(
        entry,
        SimpleNamespace(ltp=Decimal("42"), bid=Decimal("41"), ask=Decimal("43")),
        now=now,
        quote_ts=None,
        prev_mark=m2.mark,
        prev_mfe_pct=m2.mfe_pct,
        prev_mae_pct=m2.mae_pct,
    )
    assert m3.mfe_pct == Decimal("0.1")  # still the m1 high-water mark
    assert m3.mae_pct == Decimal("-0.1")  # still the m2 low-water mark
