"""S6 — one-time bootstrap entry trigger + Telegram notify for paper_3track_entry.py.

See docs/plan/3track-consolidation/stories.md S6 for the confirmed decision log
(bootstrap-only, never a recurring re-entry; Telegram as the sole visibility layer).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.strategies.three_track import paper_3track_entry
from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_FUTURES, STRATEGY_PROXY, STRATEGY_SPOT
from src.paper.models import PaperTrade
from src.paper.store import PaperStore


def _make_store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "test.db")


# ── _has_open_base_positions ────────────────────────────────────────────────


def test_bootstrap_fires_when_no_open_position(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    assert paper_3track_entry._has_open_base_positions(store) is False


def test_bootstrap_does_not_refire_once_any_track_open(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.record_trade(
        PaperTrade(
            strategy_name=STRATEGY_FUTURES,
            leg_role="base_futures",
            instrument_key="NSE_FO|NIFTY26JULFUT",
            trade_date=date(2026, 6, 25),
            action=TradeAction.BUY,
            quantity=50,
            price=Decimal("23000.0"),
        )
    )
    assert paper_3track_entry._has_open_base_positions(store) is True


def test_bootstrap_checks_all_three_tracks(tmp_path: Path) -> None:
    """A single open track (any of Spot/Futures/Proxy) is enough to block re-entry —
    the three base legs are always entered together in one bootstrap cycle."""
    store = _make_store(tmp_path)
    store.record_trade(
        PaperTrade(
            strategy_name=STRATEGY_SPOT,
            leg_role="base_etf",
            instrument_key="NSE_EQ|NIFTYBEES",
            trade_date=date(2026, 6, 25),
            action=TradeAction.BUY,
            quantity=5735,
            price=Decimal("250.0"),
        )
    )
    # Futures/Proxy still flat, but Spot alone is enough to report "already open".
    assert paper_3track_entry._has_open_base_positions(store) is True


# ── _open_tracks (per-track gate) ───────────────────────────────────────────


def test_open_tracks_empty_when_no_positions(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    assert paper_3track_entry._open_tracks(store) == set()


def test_open_tracks_reports_only_the_open_track(tmp_path: Path) -> None:
    """Spot open, Futures/Proxy flat — only Spot should report as open, unlike
    the old all-or-nothing _has_open_base_positions gate."""
    store = _make_store(tmp_path)
    store.record_trade(
        PaperTrade(
            strategy_name=STRATEGY_SPOT,
            leg_role="base_etf",
            instrument_key="NSE_EQ|NIFTYBEES",
            trade_date=date(2026, 6, 25),
            action=TradeAction.BUY,
            quantity=5735,
            price=Decimal("250.0"),
        )
    )
    assert paper_3track_entry._open_tracks(store) == {STRATEGY_SPOT}


# ── main() bootstrap + notify wiring ────────────────────────────────────────


def _fake_prices() -> MagicMock:
    prices = MagicMock()
    prices.entry_date = date(2026, 7, 30)
    prices.cycle = 1
    prices.niftybees_qty = 5735
    prices.niftybees_ltp = Decimal("250.0")
    prices.futures_key = "NSE_FO|NIFTY26JULFUT"
    prices.futures_price = Decimal("23100.0")
    prices.proxy_instrument_key = "NSE_FO|NIFTY23000CE26JUL"
    prices.proxy_price = Decimal("1200.0")
    prices.proxy_actual_delta = Decimal("0.90")
    prices.proxy_strike = Decimal("23000")
    prices.expiry = "2026-07-30"
    prices.lot_size = 75
    return prices


def _fake_trade(n: int) -> MagicMock:
    trade = MagicMock()
    trade.strategy_name = f"paper_nifty_track{n}"
    trade.leg_role = "base_etf"
    trade.quantity = 1
    trade.price = Decimal("1.0")
    return trade


def _run_main(
    mock_store: MagicMock,
    mock_notifier,
    extra_argv: list[str] | None = None,
    build_trades_mock: MagicMock | None = None,
    include_confirm: bool = True,
    prices_override: MagicMock | None = None,
) -> MagicMock:
    bt_mock = build_trades_mock or MagicMock(return_value=[_fake_trade(n) for n in range(3)])
    sys_argv = ["paper_3track_entry.py"]
    if include_confirm:
        sys_argv.append("--confirm")
    if extra_argv:
        sys_argv.extend(extra_argv)
    with (
        patch("scripts.strategies.three_track.paper_3track_entry.UpstoxMarketClient"),
        patch("scripts.strategies.three_track.paper_3track_entry.InstrumentLookup"),
        patch(
            "scripts.strategies.three_track.paper_3track_entry.derive_expiry",
            return_value="2026-08-27",
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_entry.fetch_live_prices",
            return_value=prices_override if prices_override is not None else _fake_prices(),
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_entry.compute_gate_results",
            return_value={"oi": "PASS", "spread": "PASS"},
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_entry.build_trades",
            bt_mock,
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_entry.PaperStore",
            return_value=mock_store,
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_entry.build_notifier",
            return_value=mock_notifier,
        ),
        patch("scripts.strategies.three_track.paper_3track_entry.print_preview"),
        patch("sys.argv", sys_argv),
    ):
        paper_3track_entry.main()
    return bt_mock


def test_entry_trigger_fires_when_no_open_position() -> None:
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []  # all three tracks flat
    mock_store.record_trade.return_value = True

    _run_main(mock_store, mock_notifier=None)

    assert mock_store.record_trade.call_count == 3


def test_entry_trigger_does_not_refire_once_position_open() -> None:
    mock_store = MagicMock()
    # Any non-empty get_positions() result (regardless of which strategy_name is
    # queried) simulates an already-bootstrapped track.
    mock_store.get_positions.return_value = [MagicMock()]

    _run_main(mock_store, mock_notifier=None)

    mock_store.record_trade.assert_not_called()


@pytest.mark.parametrize(
    "tracks_arg, expected_lines",
    [
        (
            [],  # all three
            [
                "📥 Base Entry — 3\\-Track Bootstrap",
                "📥 Spot: Long 5735x NIFTYBEES @ ₹250\\.00",
                "📥 Futures: Long 75x NIFTY AUG FUT @ ₹23,100\\.00",
                "📥 Proxy: Long 75x NIFTY JUL 23000 CE @ ₹1,200\\.00 \\(Δ\\=\\+0\\.90\\)",
            ],
        ),
        (
            ["--tracks", "futures"],
            [
                "📥 Base Entry — 3\\-Track Bootstrap",
                "📥 Futures: Long 75x NIFTY AUG FUT @ ₹23,100\\.00",
            ],
        ),
        (
            ["--tracks", "proxy"],
            [
                "📥 Base Entry — 3\\-Track Bootstrap",
                "📥 Proxy: Long 75x NIFTY JUL 23000 CE @ ₹1,200\\.00 \\(Δ\\=\\+0\\.90\\)",
            ],
        ),
    ],
)
def test_entry_notifies_telegram_on_success_layout(
    tracks_arg: list[str], expected_lines: list[str]
) -> None:
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)

    _run_main(mock_store, mock_notifier=mock_notifier, extra_argv=tracks_arg)

    mock_notifier.send.assert_awaited_once()
    msg = mock_notifier.send.await_args[0][0]

    assert msg == "\n".join(expected_lines)


def test_base_entry_all_reserved_chars_escaped() -> None:
    from src.notifications.markdown import MARKDOWNV2_RESERVED

    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)

    prices = _fake_prices()
    # inject worst-case values to force reserved chars
    prices.niftybees_ltp = Decimal("-250.0")  # minus
    prices.proxy_actual_delta = Decimal("-0.90")
    prices.proxy_strike = Decimal("23000.5")  # point

    _run_main(mock_store, mock_notifier=mock_notifier, prices_override=prices)

    msg = mock_notifier.send.await_args[0][0]

    # Assert every reserved char outside code span is escaped, and every backslash precedes a reserved char
    i = 0
    while i < len(msg):
        ch = msg[i]
        if ch == "\\":
            assert i + 1 < len(msg), "Trailing backslash"
            next_ch = msg[i + 1]
            assert next_ch in MARKDOWNV2_RESERVED, f"Backslash escapes non-reserved char: {next_ch}"
            i += 2
        else:
            assert ch not in MARKDOWNV2_RESERVED, (
                f"Unescaped reserved char: {ch} at {msg[i - 10 : i + 10]}"
            )
            i += 1


def test_base_entry_month_label_derivation() -> None:
    from scripts.strategies.three_track.paper_3track_entry import _month_label

    assert _month_label("2026-07-30") == "JUL"
    assert _month_label("2026-12-31") == "DEC"
    assert _month_label("2027-01-01") == "JAN"


def test_base_entry_lot_size_shown_on_futures_and_proxy() -> None:
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)

    prices = _fake_prices()
    prices.lot_size = 123

    _run_main(mock_store, mock_notifier=mock_notifier, prices_override=prices)

    msg = mock_notifier.send.await_args[0][0]
    assert "Futures: Long 123x" in msg
    assert "Proxy: Long 123x" in msg


def test_notification_failure_does_not_block_trade() -> None:
    """Non-fatal contract: a Telegram failure must never roll back or fail an
    already-executed bootstrap entry."""
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(side_effect=RuntimeError("network down"))

    _run_main(mock_store, mock_notifier=mock_notifier)  # must not raise

    assert mock_store.record_trade.call_count == 3


def test_entry_enters_only_still_flat_tracks_when_one_already_open() -> None:
    """Spot already open, Futures/Proxy flat — Spot must be skipped while
    Futures/Proxy still enter (the per-track gate this story adds; the old
    all-or-nothing gate would have skipped the whole bootstrap)."""
    mock_store = MagicMock()
    mock_store.get_positions.side_effect = lambda strategy_name: (
        [MagicMock()] if strategy_name == STRATEGY_SPOT else []
    )
    mock_store.record_trade.return_value = True
    bt_mock = MagicMock(return_value=[_fake_trade(n) for n in range(2)])

    _run_main(mock_store, mock_notifier=None, build_trades_mock=bt_mock)

    called_tracks = bt_mock.call_args.kwargs["tracks"]
    assert called_tracks == {STRATEGY_FUTURES, STRATEGY_PROXY}
    assert mock_store.record_trade.call_count == 2


def test_entry_tracks_flag_restricts_to_requested_tracks() -> None:
    """--tracks futures proxy must never touch Spot, even when Spot is flat."""
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []  # all three flat
    mock_store.record_trade.return_value = True
    bt_mock = MagicMock(return_value=[_fake_trade(n) for n in range(2)])

    _run_main(
        mock_store,
        mock_notifier=None,
        extra_argv=["--tracks", "futures", "proxy"],
        build_trades_mock=bt_mock,
    )

    called_tracks = bt_mock.call_args.kwargs["tracks"]
    assert called_tracks == {STRATEGY_FUTURES, STRATEGY_PROXY}


def test_auto_futures_exits_early_when_track_open() -> None:
    mock_store = MagicMock()
    mock_store.get_positions.side_effect = lambda strategy_name: (
        [MagicMock()] if strategy_name == STRATEGY_FUTURES else []
    )
    with pytest.raises(SystemExit) as exc:
        _run_main(
            mock_store, mock_notifier=None, extra_argv=["--auto-futures"], include_confirm=False
        )
    assert exc.value.code == 0


def test_auto_ditm_exits_early_when_track_open() -> None:
    mock_store = MagicMock()
    mock_store.get_positions.side_effect = lambda strategy_name: (
        [MagicMock()] if strategy_name == STRATEGY_PROXY else []
    )
    with pytest.raises(SystemExit) as exc:
        _run_main(mock_store, mock_notifier=None, extra_argv=["--auto-ditm"], include_confirm=False)
    assert exc.value.code == 0


def test_auto_futures_confirm_writes_trade_when_track_flat() -> None:
    """EC-5 landed and was verified (DECISIONS.md 2026-08-02 CC3 unblock precedent) —
    --auto-futures --confirm must actually write, not just avoid the old sys.exit(1).
    Asserting only "no error" here would repeat the exact coverage gap CC3's own
    review caught and fixed (test_auto_cc_no_dry_run_writes_trade_on_bootstrap_success)."""
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []  # futures flat
    mock_store.record_trade.return_value = True
    bt_mock = MagicMock(return_value=[_fake_trade(0)])

    _run_main(
        mock_store,
        mock_notifier=None,
        extra_argv=["--auto-futures"],
        include_confirm=True,
        build_trades_mock=bt_mock,
    )

    called_tracks = bt_mock.call_args.kwargs["tracks"]
    assert called_tracks == {STRATEGY_FUTURES}
    assert mock_store.record_trade.call_count == 1


def test_auto_ditm_confirm_writes_trade_when_track_flat() -> None:
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []  # proxy flat
    mock_store.record_trade.return_value = True
    bt_mock = MagicMock(return_value=[_fake_trade(0)])

    _run_main(
        mock_store,
        mock_notifier=None,
        extra_argv=["--auto-ditm"],
        include_confirm=True,
        build_trades_mock=bt_mock,
    )

    called_tracks = bt_mock.call_args.kwargs["tracks"]
    assert called_tracks == {STRATEGY_PROXY}
    assert mock_store.record_trade.call_count == 1
