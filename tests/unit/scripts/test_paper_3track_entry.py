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
            return_value=_fake_prices(),
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


def test_entry_notifies_telegram_on_success() -> None:
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)

    _run_main(mock_store, mock_notifier=mock_notifier)

    mock_notifier.send.assert_awaited_once()
    msg = mock_notifier.send.await_args[0][0]
    assert "BASE ENTRY" in msg
    assert "*" not in msg  # no leftover markdown that TelegramNotifier.send() won't render


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
    mock_store.get_positions.side_effect = (
        lambda strategy_name: [MagicMock()] if strategy_name == STRATEGY_SPOT else []
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
    mock_store.get_positions.side_effect = (
        lambda strategy_name: [MagicMock()] if strategy_name == STRATEGY_FUTURES else []
    )
    with pytest.raises(SystemExit) as exc:
        _run_main(mock_store, mock_notifier=None, extra_argv=["--auto-futures"], include_confirm=False)
    assert exc.value.code == 0


def test_auto_ditm_exits_early_when_track_open() -> None:
    mock_store = MagicMock()
    mock_store.get_positions.side_effect = (
        lambda strategy_name: [MagicMock()] if strategy_name == STRATEGY_PROXY else []
    )
    with pytest.raises(SystemExit) as exc:
        _run_main(mock_store, mock_notifier=None, extra_argv=["--auto-ditm"], include_confirm=False)
    assert exc.value.code == 0


def test_auto_flags_block_confirm_flag() -> None:
    mock_store = MagicMock()
    with pytest.raises(SystemExit) as exc:
        _run_main(mock_store, mock_notifier=None, extra_argv=["--auto-futures"], include_confirm=True)
    assert exc.value.code == 1
