"""Unit tests for scripts/pre_market_brief.py.

Coverage (RO-2):
- _compute_unrealized_with_fallback: futures leg with no live LTP (missing or
  zero) falls back to the latest paper_leg_snapshots row instead of pricing
  at zero.
- _compute_unrealized_with_fallback: futures leg with a genuine live LTP of 0
  and no prior snapshot logs a warning and reports zero (documented edge
  case, not a crash).
- _compute_unrealized_with_fallback: non-futures (option) legs are priced
  from live LTP as before, unaffected by the futures fallback path.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.pre_market_brief import _compute_unrealized_with_fallback  # noqa: E402
from src.paper.models import PaperLegSnapshot, PaperPosition  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402

_STRATEGY = "paper_nifty_futures"
_FUT_LEG = "base_futures"
_FUT_KEY = "NSE_FO|99999"
_PE_LEG = "short_put"
_PE_KEY = "NSE_FO|12345"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_paper.db"


@pytest.fixture
def store(db_path: Path) -> PaperStore:
    return PaperStore(db_path)


class _StubBroker:
    """Minimal BrokerClient stand-in: returns only the prices it's told to."""

    def __init__(self, prices: dict[str, Decimal]) -> None:
        self._prices = prices

    async def get_ltp(self, instrument_keys: list[str]) -> dict[str, Decimal]:
        return {k: v for k, v in self._prices.items() if k in instrument_keys}


def _fut_position(net_qty: int = 65) -> PaperPosition:
    return PaperPosition(
        strategy_name=_STRATEGY,
        leg_role=_FUT_LEG,
        net_qty=net_qty,
        avg_cost=Decimal("24000"),
        avg_sell_price=Decimal("0"),
        instrument_key=_FUT_KEY,
        option_type="FUT",
    )


def _pe_position(net_qty: int = -75) -> PaperPosition:
    return PaperPosition(
        strategy_name=_STRATEGY,
        leg_role=_PE_LEG,
        net_qty=net_qty,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("120"),
        instrument_key=_PE_KEY,
        option_type="PE",
    )


@pytest.mark.asyncio
async def test_futures_leg_falls_back_to_prior_snapshot_when_ltp_missing(
    store: PaperStore,
) -> None:
    """Futures leg with no pre-open LTP uses yesterday's EOD unrealized P&L."""
    store.record_leg_snapshot(
        PaperLegSnapshot(
            strategy_name=_STRATEGY,
            leg_role=_FUT_LEG,
            snapshot_date=date(2026, 8, 6),
            unrealized_pnl=Decimal("3250.00"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("3250.00"),
            ltp=Decimal("24050"),
        )
    )
    broker = _StubBroker({})  # no pre-open LTP for the future at all
    unrealized = await _compute_unrealized_with_fallback(
        store, broker, _STRATEGY, [_fut_position()]
    )
    assert unrealized == Decimal("3250.00")


@pytest.mark.asyncio
async def test_futures_leg_falls_back_when_ltp_is_zero(store: PaperStore) -> None:
    """A zero LTP (not just a missing key) also triggers the snapshot fallback."""
    store.record_leg_snapshot(
        PaperLegSnapshot(
            strategy_name=_STRATEGY,
            leg_role=_FUT_LEG,
            snapshot_date=date(2026, 8, 6),
            unrealized_pnl=Decimal("-500.00"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("-500.00"),
        )
    )
    broker = _StubBroker({_FUT_KEY: Decimal("0")})
    unrealized = await _compute_unrealized_with_fallback(
        store, broker, _STRATEGY, [_fut_position()]
    )
    assert unrealized == Decimal("-500.00")


@pytest.mark.asyncio
async def test_futures_leg_no_snapshot_and_no_ltp_reports_zero(
    store: PaperStore,
) -> None:
    """Edge case: brand-new futures leg, no EOD snapshot exists yet — zero,
    not a fabricated notional loss, and does not raise."""
    broker = _StubBroker({})
    unrealized = await _compute_unrealized_with_fallback(
        store, broker, _STRATEGY, [_fut_position()]
    )
    assert unrealized == Decimal("0")


@pytest.mark.asyncio
async def test_non_futures_leg_uses_live_ltp_unaffected(store: PaperStore) -> None:
    """A short put with genuine pre-market LTP is priced normally — no fallback."""
    broker = _StubBroker({_PE_KEY: Decimal("80")})
    unrealized = await _compute_unrealized_with_fallback(
        store, broker, _STRATEGY, [_pe_position()]
    )
    # Short leg: (avg_sell_price - ltp) * abs(net_qty) = (120 - 80) * 75
    assert unrealized == Decimal("3000")


@pytest.mark.asyncio
async def test_mixed_futures_and_option_legs_combine_correctly(
    store: PaperStore,
) -> None:
    """Futures leg falls back to snapshot while option leg still prices live,
    and the two sum correctly in one strategy's total."""
    store.record_leg_snapshot(
        PaperLegSnapshot(
            strategy_name=_STRATEGY,
            leg_role=_FUT_LEG,
            snapshot_date=date(2026, 8, 6),
            unrealized_pnl=Decimal("1000.00"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("1000.00"),
        )
    )
    broker = _StubBroker({_PE_KEY: Decimal("80")})  # no futures price pre-market
    unrealized = await _compute_unrealized_with_fallback(
        store, broker, _STRATEGY, [_fut_position(), _pe_position()]
    )
    assert unrealized == Decimal("1000.00") + Decimal("3000")
