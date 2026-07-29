"""Unit tests for scripts/dev/migrate_3track_close_duplicate_overlays.py (S1r).

Offline — broker LTP is mocked, DB is a temp SQLite file via PaperStore.
No network.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.dev.migrate_3track_close_duplicate_overlays import (
    _CC_BUG_INSTRUMENT_KEY,
    _CC_BUG_LEG_ROLE,
    _CC_BUG_TRADE_DATE,
    _OVERLAY_STRATEGY,
    _SOURCE_STRATEGY,
    migrate,
)
from src.paper.models import PaperTrade, TradeAction, TradeState
from src.paper.store import PaperStore


def _run(coro):  # type: ignore[no-untyped-def]
    import asyncio

    return asyncio.run(coro)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "portfolio.sqlite"


@pytest.fixture()
def store(db_path: Path) -> PaperStore:
    return PaperStore(db_path)


def _trade(
    strategy_name: str,
    leg_role: str,
    instrument_key: str,
    trade_date: str,
    action: TradeAction,
    qty: int,
    price: str,
    state: TradeState = TradeState.OPEN,
) -> PaperTrade:
    return PaperTrade(
        strategy_name=strategy_name,
        leg_role=leg_role,
        instrument_key=instrument_key,
        trade_date=trade_date,
        action=action,
        quantity=qty,
        price=Decimal(price),
        state=state,
    )


def _seed_duplicate_overlays(store: PaperStore) -> None:
    """Seed the live-confirmed duplicate rows from S1's context table."""
    trades = [
        # overlay_collar_call: open on all three tracks
        _trade(
            "paper_nifty_spot",
            "overlay_collar_call",
            "NSE_FO|65900",
            "2026-06-01",
            TradeAction.SELL,
            65,
            "20.00",
        ),
        _trade(
            "paper_nifty_futures",
            "overlay_collar_call",
            "NSE_FO|65900",
            "2026-06-01",
            TradeAction.SELL,
            65,
            "20.00",
        ),
        _trade(
            "paper_nifty_proxy",
            "overlay_collar_call",
            "NSE_FO|65900",
            "2026-06-01",
            TradeAction.SELL,
            65,
            "20.00",
        ),
        # overlay_collar_put: open on all three tracks
        _trade(
            "paper_nifty_spot",
            "overlay_collar_put",
            "NSE_FO|65894",
            "2026-06-01",
            TradeAction.BUY,
            65,
            "15.00",
        ),
        _trade(
            "paper_nifty_futures",
            "overlay_collar_put",
            "NSE_FO|65894",
            "2026-06-01",
            TradeAction.BUY,
            65,
            "15.00",
        ),
        _trade(
            "paper_nifty_proxy",
            "overlay_collar_put",
            "NSE_FO|65894",
            "2026-06-01",
            TradeAction.BUY,
            65,
            "15.00",
        ),
        # overlay_pp on 63848: open on spot + futures (proxy has no leg here)
        _trade(
            "paper_nifty_spot",
            "overlay_pp",
            "NSE_FO|63848",
            "2026-06-05",
            TradeAction.BUY,
            65,
            "10.00",
        ),
        _trade(
            "paper_nifty_futures",
            "overlay_pp",
            "NSE_FO|63848",
            "2026-06-05",
            TradeAction.BUY,
            65,
            "10.00",
        ),
        # overlay_cc 71474: BUY (opener) then closing BUY-back mistagged OPEN (S1b)
        _trade(
            "paper_nifty_spot",
            "overlay_cc",
            "NSE_FO|71474",
            "2026-05-20",
            TradeAction.SELL,
            65,
            "18.00",
        ),
        _trade(
            "paper_nifty_spot",
            "overlay_cc",
            "NSE_FO|71474",
            _CC_BUG_TRADE_DATE,
            TradeAction.BUY,
            65,
            "12.60",
            state=TradeState.OPEN,  # bug: should be CLOSED, net flat
        ),
        _trade(
            "paper_nifty_proxy",
            "overlay_cc",
            "NSE_FO|71474",
            "2026-05-20",
            TradeAction.SELL,
            65,
            "18.00",
        ),
        _trade(
            "paper_nifty_proxy",
            "overlay_cc",
            "NSE_FO|71474",
            _CC_BUG_TRADE_DATE,
            TradeAction.BUY,
            65,
            "12.60",
            state=TradeState.OPEN,  # bug: should be CLOSED, net flat
        ),
    ]
    store.record_trades(trades)


@pytest.fixture()
def mock_broker() -> MagicMock:
    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|65900": Decimal("25.00"),
            "NSE_FO|65894": Decimal("12.00"),
            "NSE_FO|63848": Decimal("8.00"),
        }
    )
    return broker


def _rows(db_path: Path, query: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


# ── Dry-run ──────────────────────────────────────────────────────────────


def test_dry_run_reports_rows_without_writing(
    db_path: Path, store: PaperStore, mock_broker: MagicMock
) -> None:
    """Dry-run mode touches zero rows — no closes, no state fix, no rehome."""
    _seed_duplicate_overlays(store)
    before = _rows(db_path, "SELECT * FROM paper_trades ORDER BY id")

    with patch(
        "scripts.dev.migrate_3track_close_duplicate_overlays.create_client",
        return_value=mock_broker,
    ):
        _run(migrate(db_path, apply=False))

    after = _rows(db_path, "SELECT * FROM paper_trades ORDER BY id")
    assert before == after
    mock_broker.get_ltp.assert_not_called()


# ── Apply: duplicate closes ─────────────────────────────────────────────


def test_apply_closes_futures_and_proxy_overlay_legs(
    db_path: Path, store: PaperStore, mock_broker: MagicMock
) -> None:
    """After --apply, all Futures/Proxy overlay duplicate rows are net-flat (closed)."""
    _seed_duplicate_overlays(store)

    with patch(
        "scripts.dev.migrate_3track_close_duplicate_overlays.create_client",
        return_value=mock_broker,
    ):
        _run(migrate(db_path, apply=True))

    for strategy_name in ("paper_nifty_futures", "paper_nifty_proxy"):
        positions = store.get_positions(strategy_name)
        overlay_positions = [
            p
            for p in positions
            if p.leg_role in {"overlay_collar_call", "overlay_collar_put", "overlay_pp"}
        ]
        assert overlay_positions == []


def test_spot_overlay_rows_untouched_by_close_step(
    db_path: Path, store: PaperStore, mock_broker: MagicMock
) -> None:
    """Spot's overlay legs are not closed — they get re-homed instead (S1r), not closed."""
    _seed_duplicate_overlays(store)

    with patch(
        "scripts.dev.migrate_3track_close_duplicate_overlays.create_client",
        return_value=mock_broker,
    ):
        _run(migrate(db_path, apply=True))

    positions = store.get_positions(_OVERLAY_STRATEGY)
    roles = {p.leg_role for p in positions}
    assert "overlay_collar_call" in roles
    assert "overlay_collar_put" in roles
    assert "overlay_pp" in roles


# ── Apply: S1b state bug ────────────────────────────────────────────────


def test_cc_state_bug_fixed(db_path: Path, store: PaperStore, mock_broker: MagicMock) -> None:
    """overlay_cc 71474 BUY row for spot/proxy is now CLOSED, not OPEN."""
    _seed_duplicate_overlays(store)

    with patch(
        "scripts.dev.migrate_3track_close_duplicate_overlays.create_client",
        return_value=mock_broker,
    ):
        _run(migrate(db_path, apply=True))

    rows = _rows(
        db_path,
        "SELECT strategy_name, state FROM paper_trades"
        " WHERE leg_role = ? AND instrument_key = ? AND trade_date = ? AND action = 'BUY'",
        (_CC_BUG_LEG_ROLE, _CC_BUG_INSTRUMENT_KEY, _CC_BUG_TRADE_DATE),
    )
    # Spot row was re-homed to paper_nifty_overlay by the same run; proxy stays put.
    assert len(rows) == 2
    for row in rows:
        assert row["state"] == "CLOSED"


# ── Apply: re-home to paper_nifty_overlay ───────────────────────────────


def test_surviving_overlay_rewritten_to_overlay_namespace(
    db_path: Path, store: PaperStore, mock_broker: MagicMock
) -> None:
    """Post-migration, spot's overlay_* rows carry strategy_name='paper_nifty_overlay'."""
    _seed_duplicate_overlays(store)

    with patch(
        "scripts.dev.migrate_3track_close_duplicate_overlays.create_client",
        return_value=mock_broker,
    ):
        _run(migrate(db_path, apply=True))

    remaining_spot_overlay = _rows(
        db_path,
        f"SELECT * FROM paper_trades WHERE strategy_name = '{_SOURCE_STRATEGY}'"
        " AND leg_role LIKE 'overlay_%'",
    )
    assert remaining_spot_overlay == []

    rehomed = _rows(
        db_path,
        f"SELECT * FROM paper_trades WHERE strategy_name = '{_OVERLAY_STRATEGY}'"
        " AND leg_role LIKE 'overlay_%'",
    )
    assert len(rehomed) > 0


def test_no_new_trade_rows_created_by_rehoming(
    db_path: Path, store: PaperStore, mock_broker: MagicMock
) -> None:
    """Row count for spot's overlay legs is unchanged, only strategy_name differs."""
    _seed_duplicate_overlays(store)
    spot_overlay_count_before = len(
        _rows(
            db_path,
            f"SELECT * FROM paper_trades WHERE strategy_name = '{_SOURCE_STRATEGY}'"
            " AND leg_role LIKE 'overlay_%'",
        )
    )

    with patch(
        "scripts.dev.migrate_3track_close_duplicate_overlays.create_client",
        return_value=mock_broker,
    ):
        _run(migrate(db_path, apply=True))

    overlay_count_after = len(
        _rows(
            db_path,
            f"SELECT * FROM paper_trades WHERE strategy_name = '{_OVERLAY_STRATEGY}'"
            " AND leg_role LIKE 'overlay_%'",
        )
    )
    assert overlay_count_after == spot_overlay_count_before


# ── Apply: expired-leg intrinsic fallback (reused close_ic_legs logic) ──


def test_expired_leg_uses_intrinsic_fallback(db_path: Path, store: PaperStore) -> None:
    """A closing leg with no live LTP (expired) prices via intrinsic value, not raw LTP."""
    trades = [
        _trade(
            "paper_nifty_futures",
            "overlay_pp",
            "NSE_FO|58627",
            "2026-05-01",
            TradeAction.BUY,
            65,
            "9.00",
        ),
    ]
    store.record_trades(trades)

    broker = MagicMock()
    broker.get_ltp = AsyncMock(return_value={"NSE_FO|58627": None})

    fake_bod_lookup = MagicMock()
    fake_bod_lookup.get_by_key.return_value = {
        "expiry": "2026-05-01",
        "instrument_type": "CE",
        "strike_price": "24000",
    }

    with (
        patch(
            "scripts.dev.migrate_3track_close_duplicate_overlays.create_client",
            return_value=broker,
        ),
        patch(
            "src.strategy.ic_close_executor.InstrumentLookup.from_file",
            return_value=fake_bod_lookup,
        ),
    ):
        broker.get_ltp = AsyncMock(
            side_effect=[{"NSE_FO|58627": None}, {"NSE_INDEX|Nifty 50": Decimal("24500")}]
        )
        _run(migrate(db_path, apply=True))

    positions = store.get_positions("paper_nifty_futures")
    assert all(p.leg_role != "overlay_pp" for p in positions)
