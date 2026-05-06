"""Tests for src/dhan/positions.py and the option-related models in src/dhan/models.py.

Phase A: model construction, field types, Decimal precision, frozen enforcement.
Phase B: parser functions, filter, build_options_summary, parse_fund_limit, formatter.
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.dhan.models import DhanFundLimit, DhanOptionPosition, DhanOptionsSummary
from src.dhan.positions import (
    build_options_summary,
    filter_intraday_options,
    format_options_section,
    parse_fund_limit,
    parse_option_positions,
)

_FIXTURES = Path(__file__).parents[2] / "fixtures" / "responses"


# ── Helpers ──────────────────────────────────────────────────────────────────

_TS = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)


def _make_option_position(**overrides) -> DhanOptionPosition:
    """Factory for DhanOptionPosition with sensible defaults."""
    defaults: dict = {
        "security_id": "41234",
        "trading_symbol": "NIFTY2550523500CE",
        "exchange_segment": "NSE_FNO",
        "product_type": "INTRADAY",
        "position_type": "SHORT",
        "buy_qty": 0,
        "sell_qty": 50,
        "net_qty": -50,
        "buy_avg": Decimal("0.00"),
        "sell_avg": Decimal("120.50"),
        "realized_pnl": Decimal("0.00"),
        "unrealized_pnl": Decimal("1250.00"),
    }
    defaults.update(overrides)
    return DhanOptionPosition(**defaults)


def _make_options_summary(**overrides) -> DhanOptionsSummary:
    """Factory for DhanOptionsSummary with sensible defaults."""
    defaults: dict = {
        "realized_pnl": Decimal("3000.00"),
        "unrealized_pnl": Decimal("0.00"),
        "total_pnl": Decimal("3000.00"),
        "position_count": 2,
        "snapshot_ts": _TS,
    }
    defaults.update(overrides)
    return DhanOptionsSummary(**defaults)


def _make_fund_limit(**overrides) -> DhanFundLimit:
    """Factory for DhanFundLimit with sensible defaults."""
    defaults: dict = {
        "available_balance": Decimal("150000.00"),
        "utilized_amount": Decimal("50000.00"),
        "collateral_amount": Decimal("200000.00"),
        "withdrawable_balance": Decimal("100000.00"),
        "snapshot_ts": _TS,
    }
    defaults.update(overrides)
    return DhanFundLimit(**defaults)


# ── DhanOptionPosition ────────────────────────────────────────────────────────


class TestDhanOptionPosition:
    def test_construction_happy(self) -> None:
        pos = _make_option_position()
        assert pos.security_id == "41234"
        assert pos.trading_symbol == "NIFTY2550523500CE"
        assert pos.exchange_segment == "NSE_FNO"
        assert pos.product_type == "INTRADAY"
        assert pos.position_type == "SHORT"
        assert pos.buy_qty == 0
        assert pos.sell_qty == 50
        assert pos.net_qty == -50
        assert pos.buy_avg == Decimal("0.00")
        assert pos.sell_avg == Decimal("120.50")
        assert pos.realized_pnl == Decimal("0.00")
        assert pos.unrealized_pnl == Decimal("1250.00")

    def test_monetary_fields_are_decimal(self) -> None:
        pos = _make_option_position()
        assert isinstance(pos.buy_avg, Decimal)
        assert isinstance(pos.sell_avg, Decimal)
        assert isinstance(pos.realized_pnl, Decimal)
        assert isinstance(pos.unrealized_pnl, Decimal)

    def test_decimal_precision_preserved(self) -> None:
        """Decimal(str(v)) from a Dhan float like 120.5 must not lose precision."""
        pos = _make_option_position(sell_avg=Decimal("120.55"))
        assert pos.sell_avg == Decimal("120.55")

    def test_frozen_raises_on_mutation(self) -> None:
        pos = _make_option_position()
        with pytest.raises((FrozenInstanceError, AttributeError)):
            pos.net_qty = 0  # type: ignore[misc]

    def test_net_qty_zero_means_fully_closed(self) -> None:
        """net_qty=0 is valid — represents a fully squared-off position."""
        pos = _make_option_position(buy_qty=50, sell_qty=50, net_qty=0)
        assert pos.net_qty == 0

    def test_long_position(self) -> None:
        pos = _make_option_position(
            position_type="LONG",
            buy_qty=50,
            sell_qty=0,
            net_qty=50,
            buy_avg=Decimal("95.00"),
            sell_avg=Decimal("0.00"),
        )
        assert pos.position_type == "LONG"
        assert pos.net_qty == 50


# ── DhanOptionsSummary ────────────────────────────────────────────────────────


class TestDhanOptionsSummary:
    def test_construction_happy(self) -> None:
        s = _make_options_summary()
        assert s.realized_pnl == Decimal("3000.00")
        assert s.unrealized_pnl == Decimal("0.00")
        assert s.total_pnl == Decimal("3000.00")
        assert s.position_count == 2
        assert s.snapshot_ts == _TS

    def test_monetary_fields_are_decimal(self) -> None:
        s = _make_options_summary()
        assert isinstance(s.realized_pnl, Decimal)
        assert isinstance(s.unrealized_pnl, Decimal)
        assert isinstance(s.total_pnl, Decimal)

    def test_snapshot_ts_is_datetime(self) -> None:
        s = _make_options_summary()
        assert isinstance(s.snapshot_ts, datetime)

    def test_frozen_raises_on_mutation(self) -> None:
        s = _make_options_summary()
        with pytest.raises((FrozenInstanceError, AttributeError)):
            s.position_count = 0  # type: ignore[misc]

    def test_zero_positions(self) -> None:
        s = _make_options_summary(
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            position_count=0,
        )
        assert s.position_count == 0
        assert s.total_pnl == Decimal("0")

    def test_negative_pnl(self) -> None:
        """Losses are represented as negative Decimals."""
        s = _make_options_summary(
            realized_pnl=Decimal("-2500.00"),
            total_pnl=Decimal("-2500.00"),
        )
        assert s.realized_pnl < Decimal("0")


# ── DhanFundLimit ─────────────────────────────────────────────────────────────


class TestDhanFundLimit:
    def test_construction_happy(self) -> None:
        fl = _make_fund_limit()
        assert fl.available_balance == Decimal("150000.00")
        assert fl.utilized_amount == Decimal("50000.00")
        assert fl.collateral_amount == Decimal("200000.00")
        assert fl.withdrawable_balance == Decimal("100000.00")
        assert fl.snapshot_ts == _TS

    def test_monetary_fields_are_decimal(self) -> None:
        fl = _make_fund_limit()
        assert isinstance(fl.available_balance, Decimal)
        assert isinstance(fl.utilized_amount, Decimal)
        assert isinstance(fl.collateral_amount, Decimal)
        assert isinstance(fl.withdrawable_balance, Decimal)

    def test_frozen_raises_on_mutation(self) -> None:
        fl = _make_fund_limit()
        with pytest.raises((FrozenInstanceError, AttributeError)):
            fl.available_balance = Decimal("0")  # type: ignore[misc]

    def test_snapshot_ts_is_datetime(self) -> None:
        fl = _make_fund_limit()
        assert isinstance(fl.snapshot_ts, datetime)

    def test_zero_utilization(self) -> None:
        """Zero utilized_amount is valid (no open positions consuming margin)."""
        fl = _make_fund_limit(utilized_amount=Decimal("0"))
        assert fl.utilized_amount == Decimal("0")


# ── Phase B: parse_option_positions ──────────────────────────────────────────


class TestParseOptionPositions:
    @pytest.fixture()
    def raw_positions(self) -> list[dict]:
        data = json.loads((_FIXTURES / "dhan_positions.json").read_text())
        return data["response"]

    def test_parse_all_rows(self, raw_positions) -> None:
        """Fixture has 5 rows; all 5 parse correctly (filtering is separate)."""
        result = parse_option_positions(raw_positions)
        assert len(result) == 5

    def test_parse_field_mapping(self, raw_positions) -> None:
        """First row: verify every field maps correctly from camelCase."""
        result = parse_option_positions(raw_positions)
        pos = result[0]
        assert pos.security_id == "41234"
        assert pos.trading_symbol == "NIFTY2550523500CE"
        assert pos.exchange_segment == "NSE_FNO"
        assert pos.product_type == "INTRADAY"
        assert pos.position_type == "SHORT"
        assert pos.buy_qty == 0
        assert pos.sell_qty == 50
        assert pos.net_qty == -50

    def test_parse_monetary_fields_are_decimal_not_float(self, raw_positions) -> None:
        """Dhan returns floats in JSON; parser must convert via Decimal(str(v))."""
        result = parse_option_positions(raw_positions)
        for pos in result:
            assert isinstance(pos.buy_avg, Decimal)
            assert isinstance(pos.sell_avg, Decimal)
            assert isinstance(pos.realized_pnl, Decimal)
            assert isinstance(pos.unrealized_pnl, Decimal)

    def test_parse_decimal_value_accuracy(self, raw_positions) -> None:
        """sell_avg=120.5 must survive as Decimal('120.5'), not float approximation."""
        result = parse_option_positions(raw_positions)
        assert result[0].sell_avg == Decimal("120.5")
        # Second position has buyAvg=85.25 — verify sub-rupee precision
        assert result[1].buy_avg == Decimal("85.25")

    def test_parse_empty_list(self) -> None:
        result = parse_option_positions([])
        assert result == []


# ── Phase B: filter_intraday_options ─────────────────────────────────────────


class TestFilterIntradayOptions:
    @pytest.fixture()
    def all_positions(self) -> list[DhanOptionPosition]:
        raw = json.loads((_FIXTURES / "dhan_positions.json").read_text())["response"]
        return parse_option_positions(raw)

    def test_keeps_nse_fno_intraday_and_margin(self, all_positions) -> None:
        """Fixture: 2 INTRADAY + 1 MARGIN on NSE_FNO → keeps 3. CNC and NSE_EQ excluded."""
        result = filter_intraday_options(all_positions)
        assert len(result) == 3
        for pos in result:
            assert pos.exchange_segment == "NSE_FNO"
            assert pos.product_type in ("INTRADAY", "MARGIN")

    def test_includes_margin_product_type(self, all_positions) -> None:
        """MARGIN (Dhan API name for NRML/Normal UI label) on NSE_FNO is same-day intraday."""
        result = filter_intraday_options(all_positions)
        symbols = {p.trading_symbol for p in result}
        assert "NIFTY2550524200CE" in symbols  # NSE_FNO/MARGIN row

    def test_excludes_equity_cnc(self, all_positions) -> None:
        result = filter_intraday_options(all_positions)
        symbols = {p.trading_symbol for p in result}
        assert "NIFTYIETF" not in symbols  # NSE_EQ/CNC row

    def test_excludes_fno_cnc(self, all_positions) -> None:
        result = filter_intraday_options(all_positions)
        symbols = {p.trading_symbol for p in result}
        assert "BANKNIFTY2550545000CE" not in symbols  # NSE_FNO/CNC row

    def test_empty_input(self) -> None:
        assert filter_intraday_options([]) == []

    def test_no_fno_in_input(self) -> None:
        """All CNC — result is empty."""
        cnc = [_make_option_position(product_type="CNC")]
        assert filter_intraday_options(cnc) == []

    def test_margin_on_non_fno_excluded(self) -> None:
        """MARGIN on NSE_EQ should not be included — segment gate applies first."""
        eq_margin = [_make_option_position(exchange_segment="NSE_EQ", product_type="MARGIN")]
        assert filter_intraday_options(eq_margin) == []


# ── Phase B: build_options_summary ───────────────────────────────────────────


class TestBuildOptionsSummary:
    def test_aggregates_realized_and_unrealized(self) -> None:
        positions = [
            _make_option_position(realized_pnl=Decimal("1000"), unrealized_pnl=Decimal("250")),
            _make_option_position(realized_pnl=Decimal("2000"), unrealized_pnl=Decimal("0")),
        ]
        summary = build_options_summary(positions, _TS)
        assert summary.realized_pnl == Decimal("3000")
        assert summary.unrealized_pnl == Decimal("250")
        assert summary.total_pnl == Decimal("3250")
        assert summary.position_count == 2
        assert summary.snapshot_ts == _TS

    def test_total_pnl_is_sum_of_components(self) -> None:
        positions = [
            _make_option_position(realized_pnl=Decimal("500"), unrealized_pnl=Decimal("-100")),
        ]
        summary = build_options_summary(positions, _TS)
        assert summary.total_pnl == summary.realized_pnl + summary.unrealized_pnl

    def test_empty_positions(self) -> None:
        summary = build_options_summary([], _TS)
        assert summary.realized_pnl == Decimal("0")
        assert summary.unrealized_pnl == Decimal("0")
        assert summary.total_pnl == Decimal("0")
        assert summary.position_count == 0

    def test_negative_pnl(self) -> None:
        positions = [
            _make_option_position(realized_pnl=Decimal("-1500"), unrealized_pnl=Decimal("-300")),
        ]
        summary = build_options_summary(positions, _TS)
        assert summary.total_pnl == Decimal("-1800")

    def test_returns_dhan_options_summary_type(self) -> None:
        summary = build_options_summary([], _TS)
        assert isinstance(summary, DhanOptionsSummary)


# ── Phase B: parse_fund_limit ─────────────────────────────────────────────────


class TestParseFundLimit:
    @pytest.fixture()
    def raw_fund_limit(self) -> dict:
        data = json.loads((_FIXTURES / "dhan_fund_limit.json").read_text())
        return data["response"]

    def test_parse_happy(self, raw_fund_limit) -> None:
        fl = parse_fund_limit(raw_fund_limit, _TS)
        assert fl.available_balance == Decimal("150000.75")
        assert fl.utilized_amount == Decimal("49999.25")
        assert fl.collateral_amount == Decimal("350000.0")
        assert fl.withdrawable_balance == Decimal("100001.5")
        assert fl.snapshot_ts == _TS

    def test_monetary_fields_are_decimal(self, raw_fund_limit) -> None:
        fl = parse_fund_limit(raw_fund_limit, _TS)
        assert isinstance(fl.available_balance, Decimal)
        assert isinstance(fl.utilized_amount, Decimal)
        assert isinstance(fl.collateral_amount, Decimal)
        assert isinstance(fl.withdrawable_balance, Decimal)

    def test_typo_field_availabel_balance(self, raw_fund_limit) -> None:
        """Dhan's API typo: 'availabelBalance' (missing 'l'). Parser must use exact key."""
        assert "availabelBalance" in raw_fund_limit  # fixture uses the real typo
        assert "availableBalance" not in raw_fund_limit  # correct spelling absent
        fl = parse_fund_limit(raw_fund_limit, _TS)
        assert fl.available_balance == Decimal("150000.75")

    def test_missing_typo_key_raises(self) -> None:
        """If Dhan ever fixes the typo, KeyError surfaces immediately — not silent."""
        bad = {"availableBalance": 100.0, "utilizedAmount": 0.0,
               "collateralAmount": 0.0, "withdrawableBalance": 0.0}
        with pytest.raises(KeyError):
            parse_fund_limit(bad, _TS)


# ── Phase B: format_options_section ──────────────────────────────────────────


class TestFormatOptionsSection:
    def test_zero_unrealized_omits_warning_line(self) -> None:
        summary = _make_options_summary(
            realized_pnl=Decimal("3000"),
            unrealized_pnl=Decimal("0"),
            total_pnl=Decimal("3000"),
        )
        text = format_options_section(summary, month_pnl=Decimal("12000"))
        assert "Unrealized" not in text
        assert "⚠️" not in text

    def test_nonzero_unrealized_shows_warning_line(self) -> None:
        summary = _make_options_summary(
            realized_pnl=Decimal("3000"),
            unrealized_pnl=Decimal("-500"),
            total_pnl=Decimal("2500"),
        )
        text = format_options_section(summary, month_pnl=Decimal("12000"))
        assert "⚠️" in text
        assert "Unrealized" in text
        assert "-500" in text

    def test_month_pnl_renders(self) -> None:
        summary = _make_options_summary(realized_pnl=Decimal("3000"), unrealized_pnl=Decimal("0"))
        text = format_options_section(summary, month_pnl=Decimal("45000"))
        assert "Month" in text
        assert "45,000" in text

    def test_today_pnl_renders_with_sign(self) -> None:
        summary = _make_options_summary(realized_pnl=Decimal("-1500"), unrealized_pnl=Decimal("0"))
        text = format_options_section(summary, month_pnl=Decimal("0"))
        assert "-1,500" in text

    def test_html_header_present(self) -> None:
        summary = _make_options_summary()
        text = format_options_section(summary, month_pnl=Decimal("0"))
        assert "<b>Dhan Options (Intraday)</b>" in text

    def test_position_count_rendered(self) -> None:
        summary = _make_options_summary(position_count=3)
        text = format_options_section(summary, month_pnl=Decimal("0"))
        assert "3" in text
