"""Unit tests for src/strategy/executor.py.

Covers:
- PaperFillSimulator.simulate_fill: VIX-regime slippage bands
- PaperFillSimulator: BUY fills above mid, SELL fills below mid
- PaperFillSimulator: vix=None uses default slippage without error
- PaperExecutor.apply: one leg to open → record_trade called with correct args
- PaperExecutor.apply: one leg to close → closing trade uses opposite action
- PaperExecutor.apply: empty legs → no store calls, returns current positions
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal
from unittest.mock import MagicMock, call, patch

import pytest

from src.models.options import OptionChain, OptionChainStrike
from src.models.portfolio import TradeAction
from src.paper.models import PaperPosition, PaperTrade
from src.strategy.executor import FillResult, PaperExecutor, PaperFillSimulator
from src.strategy.protocol import ApprovedAction, LegSpec


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_chain() -> OptionChain:
    """Minimal OptionChain sufficient for PaperExecutor (no instrument_key lookup)."""
    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={},
    )


def _make_position(
    strategy_name: str,
    leg_role: str,
    net_qty: int,
    instrument_key: str = "NSE_FO|12345",
) -> PaperPosition:
    """Build a PaperPosition dataclass."""
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal("100"),
        avg_sell_price=Decimal("0"),
        instrument_key=instrument_key,
    )


def _make_store(
    positions: list[PaperPosition] | None = None,
) -> MagicMock:
    """Return a MagicMock PaperStore pre-wired with get_positions / get_position."""
    store = MagicMock()
    positions = positions or []
    store.get_positions.return_value = positions
    # get_position: find matching leg_role or return a zero-qty default
    def _get_position(strategy_name: str, leg_role: str) -> PaperPosition:
        for p in positions:
            if p.leg_role == leg_role:
                return p
        return PaperPosition(
            strategy_name=strategy_name,
            leg_role=leg_role,
            net_qty=0,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("0"),
            instrument_key="",
        )

    store.get_position.side_effect = _get_position
    return store


def _make_executor(
    store: MagicMock | None = None,
    simulator: PaperFillSimulator | None = None,
) -> PaperExecutor:
    """Return a PaperExecutor with mock store and real or provided simulator."""
    return PaperExecutor(
        store=store or _make_store(),
        simulator=simulator or PaperFillSimulator(),
        db_path=":memory:",
    )


# ── PaperFillSimulator tests ──────────────────────────────────────────────────


class TestPaperFillSimulator:
    def test_low_vix_uses_1_rupee_slippage(self) -> None:
        """VIX ≤ 20 → slippage = ₹1.0."""
        sim = PaperFillSimulator()
        result = sim.simulate_fill("NSE_FO|1", "SELL", 50, Decimal("100"), vix=15.0)
        assert result.slippage == Decimal("1.0")

    def test_mid_low_vix_uses_1_5_rupee_slippage(self) -> None:
        """20 < VIX ≤ 25 → slippage = ₹1.5."""
        sim = PaperFillSimulator()
        result = sim.simulate_fill("NSE_FO|1", "BUY", 50, Decimal("100"), vix=22.0)
        assert result.slippage == Decimal("1.5")

    def test_mid_high_vix_uses_3_rupee_slippage(self) -> None:
        """25 < VIX ≤ 30 → slippage = ₹3.0."""
        sim = PaperFillSimulator()
        result = sim.simulate_fill("NSE_FO|1", "SELL", 50, Decimal("100"), vix=27.5)
        assert result.slippage == Decimal("3.0")

    def test_high_vix_uses_4_rupee_slippage(self) -> None:
        """VIX > 30 → slippage = ₹4.0."""
        sim = PaperFillSimulator()
        result = sim.simulate_fill("NSE_FO|1", "BUY", 50, Decimal("100"), vix=35.0)
        assert result.slippage == Decimal("4.0")

    def test_vix_none_uses_default_slippage_no_error(self) -> None:
        """vix=None → default slippage (₹1.5); no exception raised."""
        sim = PaperFillSimulator()
        result = sim.simulate_fill("NSE_FO|1", "SELL", 50, Decimal("100"), vix=None)
        assert result.slippage == Decimal("1.5")
        assert result.fill_price == Decimal("98.5")

    def test_buy_fill_price_above_mid(self) -> None:
        """BUY fill_price = mid + slippage > mid."""
        sim = PaperFillSimulator()
        result = sim.simulate_fill("NSE_FO|1", "BUY", 25, Decimal("50"), vix=18.0)
        assert result.fill_price == Decimal("51.0")
        assert result.fill_price > Decimal("50")

    def test_sell_fill_price_below_mid(self) -> None:
        """SELL fill_price = mid − slippage < mid."""
        sim = PaperFillSimulator()
        result = sim.simulate_fill("NSE_FO|1", "SELL", 25, Decimal("50"), vix=18.0)
        assert result.fill_price == Decimal("49.0")
        assert result.fill_price < Decimal("50")

    def test_result_carries_instrument_key_and_quantity(self) -> None:
        """FillResult echoes back instrument_key, action, and quantity."""
        sim = PaperFillSimulator()
        result = sim.simulate_fill("NSE_FO|99", "BUY", 75, Decimal("200"), vix=20.0)
        assert result.instrument_key == "NSE_FO|99"
        assert result.action == "BUY"
        assert result.quantity == 75

    def test_boundary_vix_exactly_20_is_low_band(self) -> None:
        """VIX exactly at 20.0 falls into the ≤20 band (₹1.0)."""
        sim = PaperFillSimulator()
        result = sim.simulate_fill("NSE_FO|1", "BUY", 50, Decimal("100"), vix=20.0)
        assert result.slippage == Decimal("1.0")


# ── PaperExecutor tests ───────────────────────────────────────────────────────


class TestPaperExecutorOpenLeg:
    def test_open_one_leg_calls_record_trade_once(self) -> None:
        """apply() with one leg to open → record_trade called exactly once."""
        store = _make_store()
        executor = _make_executor(store=store)
        chain = _make_chain()

        action = ApprovedAction(
            action_type="ENTER",
            legs_to_close=[],
            legs_to_open=[
                LegSpec(
                    instrument_key="NSE_FO|42",
                    action="SELL",
                    quantity=50,
                    leg_role="short_put",
                )
            ],
            rationale="CSP entry",
            council_rank=1,
        )

        with patch.object(executor, "_resolve_mid_price", return_value=Decimal("50")), \
             patch.object(executor, "_write_audit"):
            executor.apply("paper_csp", action, chain, approval_id=7, vix=18.0)

        store.record_trade.assert_called_once()
        recorded: PaperTrade = store.record_trade.call_args[0][0]
        assert recorded.strategy_name == "paper_csp"
        assert recorded.action == TradeAction.SELL
        assert recorded.instrument_key == "NSE_FO|42"
        assert recorded.leg_role == "short_put"

    def test_open_leg_sell_price_is_below_mid(self) -> None:
        """SELL-to-open: fill_price = mid − slippage (mid=100, VIX=18 → slip=1.0)."""
        store = _make_store()
        executor = _make_executor(store=store)
        chain = _make_chain()

        action = ApprovedAction(
            action_type="ENTER",
            legs_to_close=[],
            legs_to_open=[LegSpec("NSE_FO|1", "SELL", 50, "short_put")],
            rationale="entry",
            council_rank=1,
        )

        # Patch _resolve_mid_price to return a known mid so arithmetic is predictable
        with patch.object(executor, "_resolve_mid_price", return_value=Decimal("100")), \
             patch.object(executor, "_write_audit"):
            executor.apply("paper_csp", action, chain, approval_id=1, vix=18.0)

        recorded: PaperTrade = store.record_trade.call_args[0][0]
        # mid=100, slippage=1.0 → fill = 99.0
        assert recorded.price == Decimal("99.0")


class TestPaperExecutorCloseLeg:
    def test_close_short_leg_records_buy_trade(self) -> None:
        """Closing a short leg (net_qty < 0) records a BUY trade."""
        short_position = _make_position(
            "paper_csp", "short_put", net_qty=-50, instrument_key="NSE_FO|42"
        )
        store = _make_store(positions=[short_position])
        executor = _make_executor(store=store)
        chain = _make_chain()

        action = ApprovedAction(
            action_type="EXIT",
            legs_to_close=["short_put"],
            legs_to_open=[],
            rationale="profit target hit",
            council_rank=1,
        )

        with patch.object(executor, "_resolve_mid_price", return_value=Decimal("100")), \
             patch.object(executor, "_write_audit"):
            executor.apply("paper_csp", action, chain, approval_id=3, vix=18.0)

        store.record_trade.assert_called_once()
        recorded: PaperTrade = store.record_trade.call_args[0][0]
        assert recorded.action == TradeAction.BUY  # BUY to close short
        assert recorded.quantity == 50
        assert recorded.instrument_key == "NSE_FO|42"

    def test_close_long_leg_records_sell_trade(self) -> None:
        """Closing a long leg (net_qty > 0) records a SELL trade."""
        long_position = _make_position(
            "paper_csp", "long_put", net_qty=25, instrument_key="NSE_FO|55"
        )
        store = _make_store(positions=[long_position])
        executor = _make_executor(store=store)
        chain = _make_chain()

        action = ApprovedAction(
            action_type="EXIT",
            legs_to_close=["long_put"],
            legs_to_open=[],
            rationale="hedge exit",
            council_rank=1,
        )

        with patch.object(executor, "_resolve_mid_price", return_value=Decimal("80")), \
             patch.object(executor, "_write_audit"):
            executor.apply("paper_csp", action, chain, approval_id=5, vix=18.0)

        recorded: PaperTrade = store.record_trade.call_args[0][0]
        assert recorded.action == TradeAction.SELL  # SELL to close long

    def test_close_zero_qty_leg_skipped(self) -> None:
        """Legs with net_qty == 0 are skipped — no record_trade call."""
        zero_position = _make_position("paper_csp", "short_put", net_qty=0)
        store = _make_store(positions=[zero_position])
        executor = _make_executor(store=store)
        chain = _make_chain()

        action = ApprovedAction(
            action_type="EXIT",
            legs_to_close=["short_put"],
            legs_to_open=[],
            rationale="nothing open",
            council_rank=1,
        )

        with patch.object(executor, "_write_audit"):
            executor.apply("paper_csp", action, chain, approval_id=9, vix=18.0)

        store.record_trade.assert_not_called()


class TestPaperExecutorEmptyAction:
    def test_empty_action_no_store_calls_returns_positions(self) -> None:
        """Empty legs_to_close and legs_to_open → no record_trade; returns positions."""
        existing = _make_position("paper_csp", "short_put", net_qty=-50)
        store = _make_store(positions=[existing])
        executor = _make_executor(store=store)
        chain = _make_chain()

        action = ApprovedAction(
            action_type="NOOP",
            legs_to_close=[],
            legs_to_open=[],
            rationale="nothing to do",
            council_rank=1,
        )

        with patch.object(executor, "_write_audit"):
            result = executor.apply("paper_csp", action, chain, approval_id=0)

        store.record_trade.assert_not_called()
        assert result == [existing]
