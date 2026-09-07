"""Unit tests for src/reporting/eod_pt_summary.py.

No network: the broker is a stub returning canned LTPs and the InstrumentLookup
is a dict-backed fake. A real PaperStore over a tmp_path SQLite DB is used only
where trade-history replay is under test.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.models.portfolio import TradeAction
from src.paper.models import MarginSnapshot, PaperPosition, PaperTrade
from src.paper.store import PaperStore
from src.reporting import eod_pt_summary as mod

_CSP = "paper_csp_nifty_v1"
_KEY = "NSE_FO|11111"


class _FakeLookup:
    """Minimal InstrumentLookup stand-in — ``get_by_key`` off a dict."""

    def __init__(self, table: dict[str, dict]) -> None:
        self._table = table

    def get_by_key(self, instrument_key: str) -> dict | None:
        return self._table.get(instrument_key)


class _FakeBroker:
    def __init__(self, ltps: dict[str, Decimal]) -> None:
        self._ltps = ltps

    async def get_ltp(self, keys: list[str]) -> dict[str, Decimal]:
        return {k: self._ltps[k] for k in keys if k in self._ltps}


def _pos(
    net_qty: int,
    *,
    avg_cost: str = "0",
    avg_sell: str = "0",
    entry_date: date | None = None,
) -> PaperPosition:
    return PaperPosition(
        strategy_name=_CSP,
        leg_role="short_put",
        net_qty=net_qty,
        avg_cost=Decimal(avg_cost),
        avg_sell_price=Decimal(avg_sell),
        instrument_key=_KEY,
        entry_date=entry_date,
    )


# --- _pnl_rupees ---------------------------------------------------------------------


def test_pnl_rupees_short_no_lot_size_multiplier() -> None:
    """Short 65-unit (1-lot) leg: P&L is price-diff * net_qty, NOT * LOT_SIZE (65x bug)."""
    pos = _pos(-65, avg_sell="100")
    assert mod._pnl_rupees(pos, Decimal("90")) == Decimal("650")  # (100-90)*65, not *65*65


def test_pnl_rupees_long_and_missing_ltp() -> None:
    pos = _pos(65, avg_cost="100")
    assert mod._pnl_rupees(pos, Decimal("110")) == Decimal("650")
    assert mod._pnl_rupees(pos, None) is None


# --- _instrument_label -------------------------------------------------------------


@pytest.mark.parametrize(
    "inst, expected",
    [
        (
            {
                "instrument_type": "CE",
                "underlying_symbol": "NIFTY",
                "strike_price": 24000,
                "expiry": "2026-08-25",
            },
            ("NIFTY 24000 25 AUG 26 CE", ""),
        ),
        (
            {
                "instrument_type": "PE",
                "underlying_symbol": "NIFTY",
                "strike_price": 23500.5,
                "expiry": "2026-08-25",
            },
            ("NIFTY 23500.5 25 AUG 26 PE", ""),
        ),
        (
            {"instrument_type": "FUT", "underlying_symbol": "NIFTY", "expiry": "2026-08-25"},
            ("NIFTY FUT 25 AUG 26", "future"),
        ),
        (
            {"instrument_type": "EQ", "trading_symbol": "NIFTYBEES"},
            ("NIFTYBEES", "equity"),
        ),
    ],
)
def test_instrument_label_shapes(inst: dict, expected: tuple[str, str]) -> None:
    lookup = _FakeLookup({_KEY: inst})
    assert mod._instrument_label(_KEY, lookup) == expected


def test_instrument_label_missing_strike_degrades_to_key() -> None:
    lookup = _FakeLookup({_KEY: {"instrument_type": "CE", "underlying_symbol": "NIFTY"}})
    assert mod._instrument_label(_KEY, lookup) == (_KEY, "")


def test_instrument_label_unknown_key() -> None:
    assert mod._instrument_label("NSE_FO|999", _FakeLookup({})) == ("NSE_FO|999", "")


# --- _fmt_expiry_label -------------------------------------------------------------


def test_fmt_expiry_label_iso_and_passthrough() -> None:
    assert mod._fmt_expiry_label("2026-08-25") == "25 AUG 26"
    assert mod._fmt_expiry_label("WEEKLY") == "WEEKLY"
    assert mod._fmt_expiry_label(None) == ""


# --- _closed_legs_for_strategy ---------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "eod_pt_summary.db")


def _trade(role: str, key: str, action: TradeAction, qty: int, price: str, d: date) -> PaperTrade:
    return PaperTrade(
        strategy_name=_CSP,
        leg_role=role,
        instrument_key=key,
        trade_date=d,
        action=action,
        quantity=qty,
        price=Decimal(price),
    )


def test_closed_legs_full_round_trip_surfaces(store: PaperStore) -> None:
    """A short leg opened earlier and bought back to flat today is reported, though
    get_positions() (open-only) would never return it."""
    opened, closed = date(2026, 9, 1), date(2026, 9, 7)
    store.record_trade(_trade("short_put", _KEY, TradeAction.SELL, 65, "10.00", opened))
    store.record_trade(_trade("short_put", _KEY, TradeAction.BUY, 65, "4.00", closed))

    legs = mod._closed_legs_for_strategy(store, _CSP, closed)
    assert len(legs) == 1
    leg_role, key, qty_signed, entry, exit_price, cycle_start = legs[0]
    assert (leg_role, key, qty_signed) == ("short_put", _KEY, -65)
    assert (entry, exit_price, cycle_start) == (Decimal("10.00"), Decimal("4.00"), opened)


def test_closed_legs_partial_close_not_reported(store: PaperStore) -> None:
    d0, d1 = date(2026, 9, 1), date(2026, 9, 7)
    store.record_trade(_trade("short_put", _KEY, TradeAction.SELL, 65, "10.00", d0))
    store.record_trade(_trade("short_put", _KEY, TradeAction.BUY, 30, "4.00", d1))
    assert mod._closed_legs_for_strategy(store, _CSP, d1) == []


# --- _render_summary -------------------------------------------------------------


def test_render_summary_ann_pct_formula(store: PaperStore) -> None:
    entry_date, snap = date(2026, 8, 8), date(2026, 9, 7)  # 30 days held
    store.record_margin_snapshot(
        MarginSnapshot(
            strategy_name=_CSP,
            entry_date=entry_date,
            required_margin=Decimal("100000"),
            final_margin=Decimal("100000"),
            captured_at=__import__("datetime").datetime(2026, 8, 8, 10, 0),
        )
    )
    meta = {"CSP": (Decimal("5000"), _CSP, entry_date, False)}
    out = mod._render_summary(store, meta, Decimal("5000"), snap)
    # (5000/100000) * (365/30) * 100 = 60.83%
    assert "+60.83%" in out
    assert "100,000.00" in out


def test_render_summary_na_when_no_margin_snapshot(store: PaperStore) -> None:
    meta = {"Nifty Spot": (Decimal("1200"), "paper_nifty_spot", date(2026, 8, 8), False)}
    out = mod._render_summary(store, meta, Decimal("1200"), date(2026, 9, 7))
    assert "Nifty Spot" in out and "N/A" in out
    assert "1,200.00" in out


def test_render_summary_empty_meta_returns_blank() -> None:
    assert mod._render_summary(None, {}, Decimal("0"), date(2026, 9, 7)) == ""


# --- build_summary_parts -------------------------------------------------------------


def test_build_summary_parts_two_parts_when_nothing_closed(store: PaperStore) -> None:
    """One open leg, nothing closed today -> open table + summary, no 'Closed Today'."""
    store.record_trade(_trade("short_put", _KEY, TradeAction.SELL, 65, "100.00", date(2026, 9, 1)))
    lookup = _FakeLookup(
        {
            _KEY: {
                "instrument_type": "PE",
                "underlying_symbol": "NIFTY",
                "strike_price": 24000,
                "expiry": "2026-09-25",
            }
        }
    )
    broker = _FakeBroker({_KEY: Decimal("90.00")})

    parts = asyncio.run(mod.build_summary_parts(store, broker, lookup, date(2026, 9, 7)))
    assert len(parts) == 2
    assert parts[0].startswith("EOD PT Summary — 2026-09-07")
    assert parts[1].startswith("Summary — Strategy P&L")
    assert "650.00" in parts[0]  # (100-90)*65, no LOT_SIZE inflation


def test_build_summary_parts_three_parts_with_close(store: PaperStore) -> None:
    store.record_trade(_trade("short_put", _KEY, TradeAction.SELL, 65, "100.00", date(2026, 9, 1)))
    other = "NSE_FO|22222"
    store.record_trade(_trade("short_call", other, TradeAction.SELL, 65, "8.00", date(2026, 9, 1)))
    store.record_trade(_trade("short_call", other, TradeAction.BUY, 65, "2.00", date(2026, 9, 7)))
    lookup = _FakeLookup(
        {
            _KEY: {
                "instrument_type": "PE",
                "underlying_symbol": "NIFTY",
                "strike_price": 24000,
                "expiry": "2026-09-25",
            },
            other: {
                "instrument_type": "CE",
                "underlying_symbol": "NIFTY",
                "strike_price": 25000,
                "expiry": "2026-09-25",
            },
        }
    )
    broker = _FakeBroker({_KEY: Decimal("90.00")})

    parts = asyncio.run(mod.build_summary_parts(store, broker, lookup, date(2026, 9, 7)))
    assert len(parts) == 3
    assert parts[1].startswith("Closed Today — 2026-09-07")
    assert "390.00" in parts[1]  # (8-2)*65 realized


def test_build_summary_parts_empty_book_single_part(store: PaperStore) -> None:
    parts = asyncio.run(
        mod.build_summary_parts(store, _FakeBroker({}), _FakeLookup({}), date(2026, 9, 7))
    )
    assert len(parts) == 1
    assert "no open positions" in parts[0]
