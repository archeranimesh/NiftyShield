"""Tests for src/nuvama/reader.py — parse_bond_holdings, build_nuvama_summary,
_extract_rms_hdg, and fetch_nuvama_portfolio."""

import json
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.nuvama.reader import (
    _extract_rms_hdg,
    build_nuvama_summary,
    fetch_nuvama_portfolio,
    parse_bond_holdings,
)


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

_EFSL_10_ISIN = "INE532F07FD3"
_GSEC_ISIN = "IN0020070069"
_SGB_ISIN = "IN0020230168"
_LIQUIDBEES_ISIN = "INF732E01037"

_DEFAULT_POSITIONS: dict[str, Decimal] = {
    _EFSL_10_ISIN: Decimal("1000.00"),
    _GSEC_ISIN: Decimal("109.00"),
    _SGB_ISIN: Decimal("6199.00"),
}


def _make_record(
    isin: str = _EFSL_10_ISIN,
    cp_name: str = " Efsl-10%-29-4-34-ncd ",
    dp_name: str = "10EFSL34A",
    exc: str = "BSE",
    total_qty: str = "700",
    ltp: str = "1014.00",
    chg_p: str = "-1.28",
    hair_cut: str = "25.00",
) -> dict:
    return {
        "isin": isin,
        "cpName": cp_name,
        "dpName": dp_name,
        "exc": exc,
        "totalQty": total_qty,
        "ltp": ltp,
        "chgP": chg_p,
        "hairCut": hair_cut,
        "asTyp": "EQUITY",
        "totalVal": str(float(ltp) * float(total_qty)),
    }


def _wrap_resp(records: list[dict]) -> str:
    return json.dumps({"resp": {"data": {"rmsHdg": records}}})


def _wrap_eq(records: list[dict]) -> str:
    return json.dumps({"eq": {"data": {"rmsHdg": records}}})


# ---------------------------------------------------------------------------
# _extract_rms_hdg
# ---------------------------------------------------------------------------


class TestExtractRmsHdg:
    def test_primary_path(self):
        data = {"resp": {"data": {"rmsHdg": [{"a": 1}]}}}
        assert _extract_rms_hdg(data) == [{"a": 1}]

    def test_fallback_eq_path(self):
        data = {"eq": {"data": {"rmsHdg": [{"b": 2}]}}}
        assert _extract_rms_hdg(data) == [{"b": 2}]

    def test_primary_takes_precedence(self):
        data = {
            "resp": {"data": {"rmsHdg": [{"primary": True}]}},
            "eq": {"data": {"rmsHdg": [{"fallback": True}]}},
        }
        result = _extract_rms_hdg(data)
        assert result == [{"primary": True}]

    def test_raises_when_neither_path_found(self):
        with pytest.raises(KeyError, match="rmsHdg"):
            _extract_rms_hdg({"other": "data"})

    def test_empty_list_accepted(self):
        data = {"resp": {"data": {"rmsHdg": []}}}
        assert _extract_rms_hdg(data) == []


# ---------------------------------------------------------------------------
# parse_bond_holdings — happy path
# ---------------------------------------------------------------------------


class TestParseBondHoldingsHappyPath:
    def test_returns_one_holding(self):
        raw = _wrap_resp([_make_record()])
        result = parse_bond_holdings(raw, _DEFAULT_POSITIONS)
        assert len(result) == 1

    def test_company_name_stripped(self):
        raw = _wrap_resp([_make_record(cp_name="  EFSL 10%  ")])
        result = parse_bond_holdings(raw, _DEFAULT_POSITIONS)
        assert result[0].company_name == "EFSL 10%"

    def test_isin_assigned(self):
        raw = _wrap_resp([_make_record(isin=_EFSL_10_ISIN)])
        result = parse_bond_holdings(raw, _DEFAULT_POSITIONS)
        assert result[0].isin == _EFSL_10_ISIN

    def test_ltp_as_decimal(self):
        raw = _wrap_resp([_make_record(ltp="1014.00")])
        result = parse_bond_holdings(raw, _DEFAULT_POSITIONS)
        assert result[0].ltp == Decimal("1014.00")

    def test_avg_price_from_positions(self):
        raw = _wrap_resp([_make_record(isin=_EFSL_10_ISIN)])
        result = parse_bond_holdings(raw, {_EFSL_10_ISIN: Decimal("1000.00")})
        assert result[0].avg_price == Decimal("1000.00")

    def test_classification_is_bond(self):
        raw = _wrap_resp([_make_record()])
        result = parse_bond_holdings(raw, _DEFAULT_POSITIONS)
        assert result[0].classification == "BOND"

    def test_hair_cut_parsed(self):
        raw = _wrap_resp([_make_record(hair_cut="25.00")])
        result = parse_bond_holdings(raw, _DEFAULT_POSITIONS)
        assert result[0].hair_cut == Decimal("25.00")

    def test_chg_pct_negative(self):
        raw = _wrap_resp([_make_record(chg_p="-1.28")])
        result = parse_bond_holdings(raw, _DEFAULT_POSITIONS)
        assert result[0].chg_pct == Decimal("-1.28")

    def test_multiple_records(self):
        records = [
            _make_record(isin=_EFSL_10_ISIN),
            _make_record(isin=_GSEC_ISIN, cp_name=" Goi 8.28% ", ltp="144.40"),
        ]
        raw = _wrap_resp(records)
        result = parse_bond_holdings(raw, _DEFAULT_POSITIONS)
        assert len(result) == 2

    def test_fallback_eq_response_path(self):
        raw = _wrap_eq([_make_record()])
        result = parse_bond_holdings(raw, _DEFAULT_POSITIONS)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# parse_bond_holdings — filtering and exclusions
# ---------------------------------------------------------------------------


class TestParseBondHoldingsFiltering:
    def test_liquidbees_excluded_by_default(self):
        rec = _make_record(isin=_LIQUIDBEES_ISIN)
        raw = _wrap_resp([rec])
        result = parse_bond_holdings(raw, {_LIQUIDBEES_ISIN: Decimal("120.79")})
        assert result == []

    def test_extra_exclude_isin_skipped(self):
        raw = _wrap_resp([_make_record(isin=_EFSL_10_ISIN)])
        result = parse_bond_holdings(
            raw, _DEFAULT_POSITIONS, exclude_isins=frozenset([_EFSL_10_ISIN])
        )
        assert result == []

    def test_isin_missing_from_positions_skipped(self, caplog):
        import logging

        raw = _wrap_resp([_make_record(isin="UNKNOWN_ISIN")])
        with caplog.at_level(logging.WARNING):
            result = parse_bond_holdings(raw, {})
        assert result == []
        assert "UNKNOWN_ISIN" in caplog.text

    def test_missing_isin_field_skipped(self):
        rec = _make_record()
        rec.pop("isin")
        raw = _wrap_resp([rec])
        result = parse_bond_holdings(raw, _DEFAULT_POSITIONS)
        assert result == []

    def test_empty_isin_field_skipped(self):
        rec = _make_record(isin="   ")
        raw = _wrap_resp([rec])
        result = parse_bond_holdings(raw, _DEFAULT_POSITIONS)
        assert result == []

    def test_empty_response_returns_empty(self):
        raw = _wrap_resp([])
        result = parse_bond_holdings(raw, _DEFAULT_POSITIONS)
        assert result == []

    def test_malformed_ltp_skipped(self):
        rec = _make_record()
        rec["ltp"] = "not_a_number"
        raw = _wrap_resp([rec])
        result = parse_bond_holdings(raw, _DEFAULT_POSITIONS)
        assert result == []

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_bond_holdings("not json", _DEFAULT_POSITIONS)

    def test_missing_rms_hdg_raises(self):
        with pytest.raises(KeyError):
            parse_bond_holdings(json.dumps({"other": "data"}), _DEFAULT_POSITIONS)


# ---------------------------------------------------------------------------
# build_nuvama_summary
# ---------------------------------------------------------------------------


class TestBuildNuvamaSummary:
    def test_empty_holdings(self):
        s = build_nuvama_summary([], date(2026, 4, 15))
        assert s.total_value == Decimal("0")
        assert s.total_basis == Decimal("0")
        assert s.total_pnl == Decimal("0")
        assert s.total_pnl_pct is None
        assert s.total_day_delta == Decimal("0")

    def test_totals_sum_correctly(self):
        raw = _wrap_resp([
            _make_record(isin=_EFSL_10_ISIN, total_qty="700", ltp="1014.00"),
            _make_record(isin=_GSEC_ISIN, cp_name=" GSec ", total_qty="2000", ltp="144.40", chg_p="-5.00"),
        ])
        holdings = parse_bond_holdings(raw, _DEFAULT_POSITIONS)
        s = build_nuvama_summary(holdings, date(2026, 4, 15))
        assert s.total_value == Decimal("709800.00") + Decimal("288800.00")
        assert s.total_basis == Decimal("700000.00") + Decimal("218000.00")

    def test_pnl_pct_none_when_zero_basis(self):
        from src.nuvama.models import NuvamaBondHolding

        h = NuvamaBondHolding(
            isin="X",
            company_name="X",
            trading_symbol="X",
            exchange="BSE",
            qty=0,
            avg_price=Decimal("0"),
            ltp=Decimal("100"),
            chg_pct=Decimal("0"),
            hair_cut=Decimal("0"),
        )
        s = build_nuvama_summary([h], date(2026, 4, 15))
        assert s.total_pnl_pct is None

    def test_snapshot_date_stored(self):
        snap = date(2026, 4, 15)
        s = build_nuvama_summary([], snap)
        assert s.snapshot_date == snap


# ---------------------------------------------------------------------------
# fetch_nuvama_portfolio
# ---------------------------------------------------------------------------


class TestFetchNuvamaPortfolio:
    def test_calls_holdings_once(self):
        mock_api = MagicMock()
        mock_api.Holdings.return_value = _wrap_resp([_make_record()])
        fetch_nuvama_portfolio(mock_api, _DEFAULT_POSITIONS, date(2026, 4, 15))
        mock_api.Holdings.assert_called_once()

    def test_returns_summary(self):
        mock_api = MagicMock()
        mock_api.Holdings.return_value = _wrap_resp([_make_record()])
        from src.nuvama.models import NuvamaBondSummary

        result = fetch_nuvama_portfolio(mock_api, _DEFAULT_POSITIONS, date(2026, 4, 15))
        assert isinstance(result, NuvamaBondSummary)

    def test_empty_holdings_returns_empty_summary(self):
        mock_api = MagicMock()
        mock_api.Holdings.return_value = _wrap_resp([])
        result = fetch_nuvama_portfolio(mock_api, {}, date(2026, 4, 15))
        assert result.total_value == Decimal("0")

    def test_propagates_api_exception(self):
        mock_api = MagicMock()
        mock_api.Holdings.side_effect = RuntimeError("session expired")
        with pytest.raises(RuntimeError, match="session expired"):
            fetch_nuvama_portfolio(mock_api, _DEFAULT_POSITIONS, date(2026, 4, 15))

    def test_extra_exclude_isins_forwarded(self):
        mock_api = MagicMock()
        mock_api.Holdings.return_value = _wrap_resp([_make_record(isin=_EFSL_10_ISIN)])
        result = fetch_nuvama_portfolio(
            mock_api,
            _DEFAULT_POSITIONS,
            date(2026, 4, 15),
            exclude_isins=frozenset([_EFSL_10_ISIN]),
        )
        assert result.holdings == ()
