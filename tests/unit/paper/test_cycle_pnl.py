"""Tests for src/paper/cycle_pnl.py and scripts/dev/cycle_pnl_report.py."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from scripts.dev.cycle_pnl_report import _exit_reason, resolve_target
from src.models.portfolio import TradeAction
from src.paper.cycle_pnl import (
    Cycle,
    get_last_cycle_realized_pnl,
    reconstruct_cycles,
)
from src.paper.models import PaperTrade


def _t(
    leg_role: str,
    action: TradeAction,
    price: str,
    trade_date: str,
    *,
    qty: int = 65,
    notes: str = "",
) -> PaperTrade:
    return PaperTrade(
        strategy_name="paper_ic_nifty_v1_weekly",
        leg_role=leg_role,
        instrument_key=f"NSE_FO|{leg_role}",
        trade_date=date.fromisoformat(trade_date),
        action=action,
        quantity=qty,
        price=Decimal(price),
        notes=notes,
    )


def _ic_cycle(
    entry: str, exit_: str, sp_sell: str, sp_buy: str, close_note: str = ""
) -> list[PaperTrade]:
    """One 2-leg IC round trip (short_put + long_put_hedge) for brevity."""
    return [
        _t("short_put", TradeAction.SELL, sp_sell, entry),
        _t("long_put_hedge", TradeAction.BUY, "4.0", entry),
        _t("short_put", TradeAction.BUY, sp_buy, exit_, notes=close_note),
        _t("long_put_hedge", TradeAction.SELL, "4.0", exit_, notes=close_note),
    ]


# ── reconstruct_cycles ───────────────────────────────────────────────────────


def test_reconstruct_two_closed_cycles_and_open_tail() -> None:
    trades = (
        _ic_cycle("2026-07-08", "2026-07-16", "10.0", "3.0")
        + _ic_cycle("2026-07-22", "2026-07-27", "20.0", "5.0")
        + [  # third cycle: opened, not yet flat
            _t("short_put", TradeAction.SELL, "12.0", "2026-07-29"),
            _t("long_put_hedge", TradeAction.BUY, "4.0", "2026-07-29"),
        ]
    )

    cycles = reconstruct_cycles(trades)

    assert [c.index for c in cycles] == [1, 2, 3]
    assert [c.is_open for c in cycles] == [False, False, True]
    assert cycles[0].entry_date == date(2026, 7, 8)
    assert cycles[0].exit_date == date(2026, 7, 16)
    assert cycles[0].days_in_trade == 8
    # short_put: (10 - 3) * 65 = 455 ; hedge: (4 - 4) * 65 = 0
    assert cycles[0].realized_pnl == Decimal("455") * 1
    assert cycles[1].realized_pnl == Decimal("975")  # (20 - 5) * 65
    assert cycles[2].exit_date is None
    assert cycles[2].days_in_trade is None


def test_reconstruct_empty_input_returns_empty() -> None:
    assert reconstruct_cycles([]) == []


def test_single_leg_overlay_cycle() -> None:
    trades = [
        _t("overlay_cc", TradeAction.SELL, "50.0", "2026-08-12"),
        _t("overlay_cc", TradeAction.BUY, "10.0", "2026-08-25"),
    ]

    cycles = reconstruct_cycles(trades)

    assert len(cycles) == 1
    assert not cycles[0].is_open
    assert cycles[0].realized_pnl == Decimal("2600")  # (50 - 10) * 65
    assert cycles[0].days_in_trade == 13


# ── get_last_cycle_realized_pnl ──────────────────────────────────────────────


def test_last_cycle_pnl_ignores_open_tail() -> None:
    trades = _ic_cycle("2026-07-08", "2026-07-16", "10.0", "3.0") + [
        _t("short_put", TradeAction.SELL, "99.0", "2026-07-22"),
        _t("long_put_hedge", TradeAction.BUY, "4.0", "2026-07-22"),
    ]
    assert get_last_cycle_realized_pnl(trades) == Decimal("455")


def test_last_cycle_pnl_none_when_nothing_closed() -> None:
    trades = [
        _t("short_put", TradeAction.SELL, "10.0", "2026-07-08"),
        _t("long_put_hedge", TradeAction.BUY, "4.0", "2026-07-08"),
    ]
    assert get_last_cycle_realized_pnl(trades) is None


# ── report helpers ──────────────────────────────────────────────────────────


def test_resolve_target_aliases_and_exact_name() -> None:
    assert resolve_target("ic-weekly")[0].strategy_name == "paper_ic_nifty_v1_weekly"
    assert len(resolve_target("ic-all")) == 4
    assert resolve_target("collar")[0].leg_roles == ("overlay_collar_put", "overlay_collar_call")
    assert resolve_target("all")[-1].strategy_name == "paper_nifty_overlay"
    assert resolve_target("paper_custom_thing")[0].strategy_name == "paper_custom_thing"


def test_resolve_target_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown target"):
        resolve_target("nonsense")


def _cycle(is_open: bool, note: str) -> Cycle:
    trades = (_t("short_put", TradeAction.BUY, "3.0", "2026-07-16", notes=note),)
    return Cycle(
        index=1,
        entry_date=date(2026, 7, 8),
        exit_date=None if is_open else date(2026, 7, 16),
        days_in_trade=None if is_open else 8,
        realized_pnl=Decimal("0"),
        is_open=is_open,
        trades=trades,
    )


def test_exit_reason_prefers_signal_in_window() -> None:
    signals = [(date(2026, 7, 16), "PROFIT_TARGET")]
    assert _exit_reason(_cycle(False, ""), signals) == "PROFIT_TARGET"


def test_exit_reason_falls_back_to_close_note() -> None:
    cycle = _cycle(False, "ic_nifty_v1 auto-close: CLOSE_FULL")
    assert _exit_reason(cycle, []) == "CLOSE_FULL (auto-close)"


def test_exit_reason_open_cycle_is_dash() -> None:
    assert _exit_reason(_cycle(True, ""), []) == "—"
