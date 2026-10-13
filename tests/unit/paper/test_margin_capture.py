"""capture_entry_margin lives in src/paper/margin_capture.py; the IC gates module re-exports it."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.strategies.ic import ic_entry_gates
from src.paper import margin_capture


def test_ic_gates_reexports_the_shared_function() -> None:
    assert ic_entry_gates.capture_entry_margin is margin_capture.capture_entry_margin


@pytest.mark.asyncio
async def test_persists_snapshot_for_a_calendar_basket() -> None:
    broker = MagicMock()
    broker.get_order_margin = AsyncMock(
        return_value={"required_margin": 238593.0, "final_margin": 90767.0}
    )
    store = MagicMock()
    snap = await margin_capture.capture_entry_margin(
        broker, store, "paper_nifty_calendar_monthly", date(2026, 10, 28),
        [("NSE_FO|1", "SELL", 65), ("NSE_FO|2", "BUY", 65)],
    )  # fmt: skip
    assert snap is not None and snap.final_margin == Decimal("90767.0")
    store.record_margin_snapshot.assert_called_once_with(snap)


@pytest.mark.asyncio
async def test_broker_failure_returns_none_without_raising() -> None:
    broker = MagicMock()
    broker.get_order_margin = AsyncMock(side_effect=RuntimeError("token expired"))
    store = MagicMock()
    assert (
        await margin_capture.capture_entry_margin(
            broker, store, "paper_x", date(2026, 10, 28), [("NSE_FO|1", "SELL", 65)]
        )
        is None
    )
    store.record_margin_snapshot.assert_not_called()
