"""Unit tests for scripts/dev/backfill_leg_snapshot_net_qty.py (BUG-036).

Offline — no network, no broker. DB is a temp SQLite file via PaperStore.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.dev.backfill_leg_snapshot_net_qty import backfill
from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_OVERLAY
from src.paper.models import PaperLegSnapshot, PaperTrade
from src.paper.store import PaperStore

_TRACK = STRATEGY_OVERLAY


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "portfolio.sqlite"


@pytest.fixture()
def store(db_path: Path) -> PaperStore:
    return PaperStore(db_path)


def _trade(
    role: str,
    trade_date: date,
    qty: int,
    price: Decimal,
    action: TradeAction,
    instrument_key: str = "NSE_FO|99999",
) -> PaperTrade:
    return PaperTrade(
        strategy_name=_TRACK,
        leg_role=role,
        instrument_key=instrument_key,
        trade_date=trade_date,
        action=action,
        quantity=qty,
        price=price,
    )


def test_backfill_reconstructs_net_qty_as_of_snapshot_date(
    store: PaperStore, db_path: Path
) -> None:
    """A partial close between two snapshot dates must backfill each row with
    the quantity that was open AS OF that row's date, not today's live qty.
    """
    day1, day2 = date(2026, 5, 1), date(2026, 5, 2)

    # Day 1: sell 50 to open.
    store.record_trade(_trade("overlay_cc", day1, 50, Decimal("100.00"), TradeAction.SELL))
    store.record_leg_snapshot(
        PaperLegSnapshot(
            strategy_name=_TRACK,
            leg_role="overlay_cc",
            snapshot_date=day1,
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            ltp=Decimal("100.00"),
            # net_qty intentionally omitted -- simulates a pre-fix row.
        )
    )

    # Day 2: buy back 25 (partial close) -- live qty is now -25 (still short).
    store.record_trade(_trade("overlay_cc", day2, 25, Decimal("60.00"), TradeAction.BUY))
    store.record_leg_snapshot(
        PaperLegSnapshot(
            strategy_name=_TRACK,
            leg_role="overlay_cc",
            snapshot_date=day2,
            unrealized_pnl=Decimal("1000"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("1000"),
            ltp=Decimal("60.00"),
        )
    )

    result = backfill(db_path, dry_run=False)
    assert result.backfilled == 2

    row1 = store.get_leg_snapshot(_TRACK, "overlay_cc", day1)
    row2 = store.get_leg_snapshot(_TRACK, "overlay_cc", day2)
    # SELL 50 to open is a short -> net_qty=-50; BUY 25 back (partial close)
    # leaves -25 open, matching get_position's SUM(BUY qty) - SUM(SELL qty).
    assert row1 is not None and row1.net_qty == -50
    assert row2 is not None and row2.net_qty == -25
    # unrealized/realized/total_pnl/ltp must round-trip unchanged.
    assert row1.total_pnl == Decimal("0")
    assert row2.total_pnl == Decimal("1000")
    assert row2.ltp == Decimal("60.00")


def test_backfill_skips_rows_already_populated_without_force(
    store: PaperStore, db_path: Path
) -> None:
    """Idempotent: a row that already carries a non-NULL net_qty is left
    untouched when --force is not passed, even if the ledger would compute
    a different value.
    """
    day1 = date(2026, 5, 1)
    store.record_trade(_trade("overlay_cc", day1, 50, Decimal("100.00"), TradeAction.SELL))
    store.record_leg_snapshot(
        PaperLegSnapshot(
            strategy_name=_TRACK,
            leg_role="overlay_cc",
            snapshot_date=day1,
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            ltp=Decimal("100.00"),
            net_qty=999,  # deliberately "wrong" vs. the ledger, to prove it's untouched
        )
    )

    result = backfill(db_path, dry_run=False)
    assert result.backfilled == 0

    row = store.get_leg_snapshot(_TRACK, "overlay_cc", day1)
    assert row is not None and row.net_qty == 999


def test_backfill_dry_run_writes_nothing(store: PaperStore, db_path: Path) -> None:
    day1 = date(2026, 5, 1)
    store.record_trade(_trade("overlay_cc", day1, 50, Decimal("100.00"), TradeAction.SELL))
    store.record_leg_snapshot(
        PaperLegSnapshot(
            strategy_name=_TRACK,
            leg_role="overlay_cc",
            snapshot_date=day1,
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            ltp=Decimal("100.00"),
        )
    )

    result = backfill(db_path, dry_run=True)
    assert result.backfilled == 0

    row = store.get_leg_snapshot(_TRACK, "overlay_cc", day1)
    assert row is not None and row.net_qty is None
