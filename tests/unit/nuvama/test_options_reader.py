"""Tests for src/nuvama/options_reader.py.

Covers parse_options_positions() and build_options_summary().
All tests are fully offline — no network calls, no SDK dependency.
"""

import json
from datetime import date
from decimal import Decimal

import pytest

from src.nuvama.models import NuvamaOptionPosition
from src.nuvama.options_reader import build_options_summary, parse_options_positions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wrap(pos_list: list) -> str:
    """Wrap a position list in the NetPosition() response envelope."""
    return json.dumps({"resp": {"data": {"pos": pos_list}}})


def _rec(
    trd_sym: str = "NIFTY2642123000PE",
    as_typ: str = "OPTIDX",
    nt_qty: int = -50,
    cf_avg_sl_prc: str = "120.00",
    cf_avg_by_prc: str = "0",
    avg_sl_prc: str = "0",
    avg_by_prc: str = "0",
    ltp: str = "90.00",
    urlz_pl: str = "1500.00",
    rlz_pl: str = "200.00",
    dp_name: str = "NIFTY",
    dp_exp_dt: str = "21 APR",
    op_typ: str = "PE",
    stk_prc: str = "23000",
) -> dict:
    """Return a minimal realistic NetPosition record dict."""
    return {
        "trdSym": trd_sym,
        "asTyp": as_typ,
        "ntQty": str(nt_qty),
        "cfAvgSlPrc": cf_avg_sl_prc,
        "cfAvgByPrc": cf_avg_by_prc,
        "avgSlPrc": avg_sl_prc,
        "avgByPrc": avg_by_prc,
        "ltp": ltp,
        "urlzPL": urlz_pl,
        "rlzPL": rlz_pl,
        "dpName": dp_name,
        "dpExpDt": dp_exp_dt,
        "opTyp": op_typ,
        "stkPrc": stk_prc,
    }


def _pos(
    symbol: str = "A",
    unrealized: str = "1000",
    realized: str = "200",
) -> NuvamaOptionPosition:
    """Minimal NuvamaOptionPosition for build_options_summary tests."""
    return NuvamaOptionPosition(
        trade_symbol=symbol,
        instrument_name="Inst",
        net_qty=-10,
        avg_price=Decimal("100"),
        ltp=Decimal("80"),
        unrealized_pnl=Decimal(unrealized),
        realized_pnl_today=Decimal(realized),
    )


# ---------------------------------------------------------------------------
# parse_options_positions — happy path
# ---------------------------------------------------------------------------


class TestParseOptionsPositions:
    def test_happy_path_optidx(self):
        positions = parse_options_positions(_wrap([_rec()]))
        assert len(positions) == 1
        p = positions[0]
        assert p.trade_symbol == "NIFTY2642123000PE"
        assert p.net_qty == -50
        assert p.avg_price == Decimal("120.00")
        assert p.ltp == Decimal("90.00")
        assert p.unrealized_pnl == Decimal("1500.00")
        assert p.realized_pnl_today == Decimal("200.00")

    def test_happy_path_optstk(self):
        positions = parse_options_positions(
            _wrap([_rec(as_typ="OPTSTK", trd_sym="RELIANCE24APR3000CE")])
        )
        assert len(positions) == 1
        assert positions[0].trade_symbol == "RELIANCE24APR3000CE"

    def test_skips_eq_rows(self):
        raw = _wrap([_rec(as_typ="EQ", trd_sym="REL"), _rec(trd_sym="NIFTY2642123000PE")])
        positions = parse_options_positions(raw)
        assert len(positions) == 1
        assert positions[0].trade_symbol == "NIFTY2642123000PE"

    def test_skips_fut_rows(self):
        raw = _wrap([_rec(as_typ="FUTIDX", trd_sym="NIFTY_FUT"), _rec()])
        positions = parse_options_positions(raw)
        assert len(positions) == 1

    def test_flat_position_captured_for_realized_pnl(self):
        """net_qty=0 (squared-off) must still be captured — realized PnL matters."""
        positions = parse_options_positions(_wrap([_rec(nt_qty=0, rlz_pl="500.00")]))
        assert len(positions) == 1
        p = positions[0]
        assert p.net_qty == 0
        assert p.realized_pnl_today == Decimal("500.00")
        assert p.avg_price == Decimal("0")  # flat → avg_price is always 0

    # ------------------------------------------------------------------
    # Average price selection
    # ------------------------------------------------------------------

    def test_short_uses_cf_avg_sl_prc(self):
        positions = parse_options_positions(
            _wrap([_rec(nt_qty=-50, cf_avg_sl_prc="120.00", cf_avg_by_prc="999")])
        )
        assert positions[0].avg_price == Decimal("120.00")

    def test_long_uses_cf_avg_by_prc(self):
        positions = parse_options_positions(
            _wrap([_rec(nt_qty=50, cf_avg_by_prc="85.00", cf_avg_sl_prc="999")])
        )
        assert positions[0].avg_price == Decimal("85.00")

    def test_short_fallback_to_avg_sl_prc(self):
        """cfAvgSlPrc=0 → fall back to avgSlPrc."""
        positions = parse_options_positions(
            _wrap([_rec(nt_qty=-50, cf_avg_sl_prc="0", avg_sl_prc="115.00")])
        )
        assert positions[0].avg_price == Decimal("115.00")

    def test_long_fallback_to_avg_by_prc(self):
        """cfAvgByPrc=0 → fall back to avgByPrc."""
        positions = parse_options_positions(
            _wrap([_rec(nt_qty=50, cf_avg_by_prc="0", avg_by_prc="88.00")])
        )
        assert positions[0].avg_price == Decimal("88.00")

    # ------------------------------------------------------------------
    # Instrument name construction
    # ------------------------------------------------------------------

    def test_instrument_name_combines_fields(self):
        positions = parse_options_positions(
            _wrap([_rec(dp_name="NIFTY", dp_exp_dt="21 APR", op_typ="PE", stk_prc="23000")])
        )
        name = positions[0].instrument_name
        assert "NIFTY" in name
        assert "21 APR" in name
        assert "PE" in name
        assert "23000" in name

    def test_instrument_name_strips_quotes(self):
        """Apostrophes in source fields (e.g. stk_prc="23'000") are removed."""
        positions = parse_options_positions(
            _wrap([_rec(stk_prc="23'000")])
        )
        assert "'" not in positions[0].instrument_name

    # ------------------------------------------------------------------
    # Missing / malformed input
    # ------------------------------------------------------------------

    def test_missing_pos_key_returns_empty(self):
        raw = json.dumps({"resp": {"data": {}}})
        assert parse_options_positions(raw) == []

    def test_missing_trd_sym_skips_record(self):
        bad = _rec()
        del bad["trdSym"]
        assert parse_options_positions(_wrap([bad])) == []

    def test_invalid_decimal_in_ltp_skips_record(self):
        assert parse_options_positions(_wrap([_rec(ltp="not-a-number")])) == []

    def test_invalid_decimal_in_pnl_skips_record(self):
        assert parse_options_positions(_wrap([_rec(urlz_pl="abc")])) == []

    def test_mixed_valid_and_malformed_keeps_valid(self):
        good = _rec(trd_sym="GOOD")
        bad = _rec(trd_sym="BAD", ltp="not-a-number")
        positions = parse_options_positions(_wrap([bad, good]))
        assert len(positions) == 1
        assert positions[0].trade_symbol == "GOOD"

    def test_empty_pos_list(self):
        assert parse_options_positions(_wrap([])) == []


# ---------------------------------------------------------------------------
# build_options_summary — aggregation math
# ---------------------------------------------------------------------------


class TestBuildOptionsSummary:
    def test_aggregates_unrealized_pnl(self):
        positions = [
            _pos("A", unrealized="1000", realized="0"),
            _pos("B", unrealized="500", realized="0"),
        ]
        summary = build_options_summary(positions, date(2026, 4, 21), {})
        assert summary.total_unrealized_pnl == Decimal("1500")

    def test_aggregates_realized_pnl_today(self):
        positions = [
            _pos("A", unrealized="0", realized="200"),
            _pos("B", unrealized="0", realized="350"),
        ]
        summary = build_options_summary(positions, date(2026, 4, 21), {})
        assert summary.total_realized_pnl_today == Decimal("550")

    def test_cumulative_pnl_from_map_sum(self):
        pnl_map = {"A": Decimal("1000"), "B": Decimal("2500")}
        summary = build_options_summary([], date(2026, 4, 21), pnl_map)
        assert summary.cumulative_realized_pnl == Decimal("3500")

    def test_empty_positions_all_zero(self):
        summary = build_options_summary([], date(2026, 4, 21), {})
        assert summary.total_unrealized_pnl == Decimal("0")
        assert summary.total_realized_pnl_today == Decimal("0")
        assert summary.cumulative_realized_pnl == Decimal("0")

    def test_positions_stored_as_tuple(self):
        positions = [_pos("A"), _pos("B")]
        summary = build_options_summary(positions, date(2026, 4, 21), {})
        assert isinstance(summary.positions, tuple)
        assert len(summary.positions) == 2

    def test_snapshot_date_propagated(self):
        snap = date(2026, 4, 21)
        summary = build_options_summary([], snap, {})
        assert summary.snapshot_date == snap

    def test_intraday_bounds_propagated(self):
        summary = build_options_summary(
            [],
            date(2026, 4, 21),
            {},
            intraday_high=Decimal("3000"),
            intraday_low=Decimal("-200"),
            nifty_high=23100.5,
            nifty_low=22800.0,
        )
        assert summary.intraday_high == Decimal("3000")
        assert summary.intraday_low == Decimal("-200")
        assert summary.nifty_high == 23100.5
        assert summary.nifty_low == 22800.0

    def test_intraday_bounds_default_none(self):
        summary = build_options_summary([], date(2026, 4, 21), {})
        assert summary.intraday_high is None
        assert summary.intraday_low is None
        assert summary.nifty_high is None
        assert summary.nifty_low is None

    def test_net_pnl_excludes_cumulative(self):
        """net_pnl = unrealized + today's realized only; cumulative must NOT contribute."""
        positions = [_pos("A", unrealized="1000", realized="300")]
        summary = build_options_summary(
            positions, date(2026, 4, 21), {"A": Decimal("5000")}
        )
        # 1000 + 300 = 1300; NOT 1000 + 300 + 5000
        assert summary.net_pnl == Decimal("1300")
