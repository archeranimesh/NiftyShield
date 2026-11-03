"""YF-5: namespace read-paths recognise the yearly overlay book (and keep the monthly book apart)."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.strategies.three_track.paper_3track_overlay_entry import _has_open_overlay_leg
from src.models.portfolio import TradeAction
from src.notifications.formatting import strategy_label
from src.paper.constants import (
    STRATEGY_OVERLAY,
    STRATEGY_OVERLAY_YEARLY_CC,
    STRATEGY_OVERLAY_YEARLY_COLLAR,
    STRATEGY_OVERLAY_YEARLY_PP,
    STRATEGY_SPOT,
    YEARLY_OVERLAY_STRATEGIES,
    is_yearly_overlay_strategy,
)
from src.paper.cycle_pnl import resolve_target
from src.paper.models import GateViolation, PaperTrade
from src.paper.store import PaperStore
from src.portfolio.overlay_coverage import (
    compute_overlay_coverage,
    compute_overlay_coverage_by_namespace,
)
from src.reporting import eod_pt_summary as eod
from src.risk.collateral_gate import check_collateral_capacity
from src.strategy.auto_close import evaluate_pp_reentry_eod
from src.strategy.executor import PaperFillSimulator
from src.strategy.reentry_mixin import _reentry_headline_label

_LOT = 65
_D = date(2026, 11, 3)


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "yearly_ns.db")


def _open(
    store: PaperStore,
    strategy: str,
    role: str,
    key: str,
    action: TradeAction = TradeAction.SELL,
    qty: int = _LOT,
    price: str = "100.00",
) -> None:
    store.record_trade(
        PaperTrade(
            strategy_name=strategy,
            leg_role=role,
            instrument_key=key,
            trade_date=_D,
            action=action,
            quantity=qty,
            price=Decimal(price),
        )
    )


# --- single source of truth ----------------------------------------------------------


def test_yearly_set_is_the_three_names_and_monthly_is_not_in_it() -> None:
    assert set(YEARLY_OVERLAY_STRATEGIES) == {
        STRATEGY_OVERLAY_YEARLY_CC,
        STRATEGY_OVERLAY_YEARLY_PP,
        STRATEGY_OVERLAY_YEARLY_COLLAR,
    }
    assert all(is_yearly_overlay_strategy(n) for n in YEARLY_OVERLAY_STRATEGIES)
    assert not is_yearly_overlay_strategy(STRATEGY_OVERLAY)
    assert not is_yearly_overlay_strategy("paper_csp_nifty_v1")


# --- _has_open_overlay_leg -----------------------------------------------------------


def test_monthly_leg_does_not_block_yearly_entry(store: PaperStore) -> None:
    _open(store, STRATEGY_OVERLAY, "overlay_cc", "NSE_FO|M1")
    assert _has_open_overlay_leg(store, "overlay_cc") is True
    assert _has_open_overlay_leg(store, "overlay_cc", STRATEGY_OVERLAY_YEARLY_CC) is False


def test_yearly_leg_does_not_block_monthly_entry(store: PaperStore) -> None:
    _open(store, STRATEGY_OVERLAY_YEARLY_CC, "overlay_cc", "NSE_FO|Y1")
    assert _has_open_overlay_leg(store, "overlay_cc", STRATEGY_OVERLAY_YEARLY_CC) is True
    assert _has_open_overlay_leg(store, "overlay_cc") is False


# --- collateral gate -----------------------------------------------------------------


def _gate(store: PaperStore, name: str, lots: int = 1) -> GateViolation | None:
    return check_collateral_capacity(
        store, name, lots, Decimal("24500"), Decimal("280"), lot_size=_LOT
    )


def test_collateral_gate_counts_yearly_namespace_separately(store: PaperStore) -> None:
    # 5725 units supports exactly 1 monthly lot; monthly pool already holds 1 lot.
    _open(store, STRATEGY_SPOT, "base_etf", "NSE_EQ|NB", TradeAction.BUY, 5725, "260.00")
    _open(store, STRATEGY_OVERLAY, "overlay_cc", "NSE_FO|M1")
    # A yearly lot must not push the monthly pool over capacity ...
    _open(store, STRATEGY_OVERLAY_YEARLY_CC, "overlay_cc", "NSE_FO|Y1")
    monthly = _gate(store, STRATEGY_OVERLAY)
    assert monthly is not None and monthly.actual == "2" and monthly.threshold == "1"
    # ... and the yearly pool counts only yearly lots against its own (zero) allocation.
    yearly = _gate(store, STRATEGY_OVERLAY_YEARLY_CC)
    assert yearly is not None and yearly.actual == "2" and yearly.threshold == "0"


def test_collateral_gate_yearly_lots_never_enter_monthly_pool(store: PaperStore) -> None:
    _open(store, STRATEGY_SPOT, "base_etf", "NSE_EQ|NB", TradeAction.BUY, 5725, "260.00")
    _open(store, STRATEGY_OVERLAY_YEARLY_CC, "overlay_cc", "NSE_FO|Y1")
    _open(store, STRATEGY_OVERLAY_YEARLY_PP, "overlay_pp", "NSE_FO|Y2", TradeAction.BUY)
    assert _gate(store, STRATEGY_OVERLAY) is None  # monthly pool empty, 1 lot fits


# --- coverage ------------------------------------------------------------------------


class _Lookup:
    def get_by_key(self, key: str) -> None:
        return None


def test_coverage_reports_each_namespace_separately(store: PaperStore) -> None:
    # Futures base: 65 units, delta 1.0. Monthly overlay holds 65 units of a leg whose
    # delta can't be resolved (no chain) -> 0 delta; the point is the namespaces differ
    # in which legs they see. Use fetched deltas via patch.
    _open(store, STRATEGY_OVERLAY, "overlay_pp", "NSE_FO|M1", TradeAction.BUY)
    _open(store, STRATEGY_OVERLAY_YEARLY_PP, "overlay_pp", "NSE_FO|Y1", TradeAction.BUY, 130)
    _open(store, "paper_nifty_futures", "base_futures", "NSE_FO|FUT", TradeAction.BUY)

    async def fake_delta(pos, lookup, broker, cache):
        return Decimal("-0.5"), Decimal("0"), Decimal("0")

    with patch("src.portfolio.overlay_coverage.resolve_leg_delta", side_effect=fake_delta):
        rows = asyncio.run(
            compute_overlay_coverage_by_namespace(
                store, AsyncMock(), _Lookup(), "paper_nifty_futures", _D
            )
        )
        monthly_only = asyncio.run(
            compute_overlay_coverage(store, AsyncMock(), _Lookup(), "paper_nifty_futures", _D)
        )

    assert set(rows) == {STRATEGY_OVERLAY, *YEARLY_OVERLAY_STRATEGIES}
    assert rows[STRATEGY_OVERLAY].overlay_effective_units == Decimal("-32.5")
    assert rows[STRATEGY_OVERLAY_YEARLY_PP].overlay_effective_units == Decimal("-65")
    assert rows[STRATEGY_OVERLAY_YEARLY_CC].overlay_effective_units == Decimal("0")
    # Default call is the monthly book alone, unchanged.
    assert monthly_only.overlay_effective_units == Decimal("-32.5")


# --- eod_pt_summary ------------------------------------------------------------------


class _EodLookup:
    def get_by_key(self, key: str) -> dict[str, str | int]:
        return {
            "instrument_type": "CE",
            "underlying_symbol": "NIFTY",
            "strike_price": 26000,
            "expiry": "2026-12-29",
        }


class _Broker:
    async def get_ltp(self, keys: list[str]) -> dict[str, Decimal]:
        return {k: Decimal("90") for k in keys}


def test_eod_rows_label_yearly_book_and_count_niftybees_once(store: PaperStore) -> None:
    _open(store, STRATEGY_SPOT, "base_etf", "NSE_EQ|NB", TradeAction.BUY, 100, "260.00")
    _open(store, STRATEGY_OVERLAY, "overlay_cc", "NSE_FO|M1")
    _open(store, STRATEGY_OVERLAY_YEARLY_CC, "overlay_cc", "NSE_FO|Y1")
    _open(store, STRATEGY_OVERLAY_YEARLY_COLLAR, "overlay_collar_put", "NSE_FO|Y2", TradeAction.BUY)

    rows, total, _missing, meta = asyncio.run(eod._collect_rows(store, _Broker(), _EodLookup()))

    labels = [r[0] for r in rows]
    assert labels.count("Nifty Spot") == 1  # NiftyBees counted once across both books
    assert labels.count("CC") == 1 and labels.count("Yearly CC") == 1
    assert labels.count("Yearly Collar") == 1
    assert meta["Yearly CC"][1] == STRATEGY_OVERLAY_YEARLY_CC
    assert total == sum(r[7] for r in rows)


def test_eod_closed_legs_include_yearly_book(store: PaperStore) -> None:
    _open(store, STRATEGY_OVERLAY_YEARLY_PP, "overlay_pp", "NSE_FO|Y1", TradeAction.BUY, price="50")
    _open(
        store, STRATEGY_OVERLAY_YEARLY_PP, "overlay_pp", "NSE_FO|Y1", TradeAction.SELL, price="80"
    )
    rows, total = eod._collect_closed_rows(store, _EodLookup(), _D)
    assert [r[0] for r in rows] == ["Yearly PP"]
    assert total == Decimal("1950")


# --- labels / reentry headline / cycle_pnl -------------------------------------------


def test_yearly_names_have_labels_and_headline() -> None:
    assert strategy_label(STRATEGY_OVERLAY_YEARLY_CC) == "Yearly Covered Call"
    assert _reentry_headline_label(STRATEGY_OVERLAY_YEARLY_PP, "protective_put") == (
        "Yearly Protective Put"
    )
    assert _reentry_headline_label(STRATEGY_OVERLAY, "protective_put") == "Protective Put V1"


def test_unmapped_overlay_name_still_raises() -> None:
    with pytest.raises(ValueError):
        _reentry_headline_label("paper_nifty_overlay_yearly_bogus", "overlay_pp")


def test_cycle_pnl_overlay_groups_use_the_shared_constant() -> None:
    assert resolve_target("cc")[0].strategy_name == STRATEGY_OVERLAY
    assert resolve_target(STRATEGY_OVERLAY_YEARLY_CC)[0].strategy_name == (
        STRATEGY_OVERLAY_YEARLY_CC
    )


# --- auto_close PP re-entry ----------------------------------------------------------


def _vix() -> MagicMock:
    s = MagicMock()
    s.empty = False
    s.__len__ = MagicMock(return_value=300)
    s.iloc = ["15.0"] * 300
    return s


def _run_pp_reentry(store: PaperStore, **kw) -> AsyncMock:
    notifier = AsyncMock()
    with (
        patch("src.strategy.auto_close.load_vix_series", return_value=_vix()),
        patch("src.strategy.auto_close.compute_ivr", return_value=0.45),
    ):
        asyncio.run(
            evaluate_pp_reentry_eod(
                store=store,
                simulator=PaperFillSimulator(),
                chain=MagicMock(),
                lookup=None,
                notifier=notifier,
                vix_data_dir=None,
                today=_D,
                **kw,
            )
        )
    return notifier


def test_pp_reentry_monthly_pp_does_not_suppress_yearly_notice(store: PaperStore) -> None:
    _open(store, STRATEGY_OVERLAY, "overlay_pp", "NSE_FO|M1", TradeAction.BUY)
    assert _run_pp_reentry(store).send.call_count == 0
    assert _run_pp_reentry(store, strategy_name=STRATEGY_OVERLAY_YEARLY_PP).send.call_count == 1


def test_pp_reentry_yearly_pp_does_not_suppress_monthly_notice(store: PaperStore) -> None:
    _open(store, STRATEGY_OVERLAY_YEARLY_PP, "overlay_pp", "NSE_FO|Y1", TradeAction.BUY)
    assert _run_pp_reentry(store, strategy_name=STRATEGY_OVERLAY_YEARLY_PP).send.call_count == 0
    assert _run_pp_reentry(store).send.call_count == 1
