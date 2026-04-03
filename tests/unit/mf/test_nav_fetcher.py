"""Unit tests for src/mf/nav_fetcher.py.

All tests are offline — they read from tests/fixtures/amfi/nav_slice.txt.
No network calls are made at any point.

Fixture layout:
  - 11 valid scheme lines spread across three category sections
  - One N.A. NAV line (code 119293)
  - One malformed line (too few fields, non-digit code)
  - One scheme (code 999999) that is absent from the fixture entirely
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from src.mf.nav_fetcher import _parse, fetch_navs

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "amfi" / "nav_slice.txt"

# All 11 codes present in the fixture with valid NAVs
ALL_VALID_CODES = {
    "104481",  # DSP Midcap
    "146193",  # Edelweiss Small Cap
    "101281",  # HDFC Sensex Index
    "102760",  # HDFC Focused
    "112090",  # Kotak Flexicap
    "142109",  # Mahindra Manulife Mid Cap
    "122640",  # Parag Parikh Flexi Cap
    "100177",  # Quant Small Cap
    "101659",  # Tata Nifty 50 Index
    "101672",  # Tata Value Fund
    "150799",  # WhiteOak Capital Large Cap
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw() -> str:
    return FIXTURE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# _parse — pure unit tests, no I/O at all
# ---------------------------------------------------------------------------


class TestParse:
    def test_returns_all_requested_valid_codes(self) -> None:
        result = _parse(_raw(), ALL_VALID_CODES)
        assert result.keys() == ALL_VALID_CODES

    def test_nav_values_are_decimal(self) -> None:
        result = _parse(_raw(), ALL_VALID_CODES)
        assert all(isinstance(v, Decimal) for v in result.values())

    def test_specific_nav_values(self) -> None:
        result = _parse(_raw(), {"104481", "122640", "150799"})
        assert result["104481"] == Decimal("123.4560")
        assert result["122640"] == Decimal("78.4560")
        assert result["150799"] == Decimal("18.7320")

    def test_code_not_in_file_is_absent_from_result(self) -> None:
        result = _parse(_raw(), {"999999"})
        assert "999999" not in result
        assert result == {}

    def test_partial_match_returns_only_found_codes(self) -> None:
        # Request 3 real codes + 1 missing
        codes = {"104481", "146193", "999999"}
        result = _parse(_raw(), codes)
        assert set(result.keys()) == {"104481", "146193"}

    def test_na_nav_is_skipped(self) -> None:
        # Code 119293 has NAV = "N.A." in the fixture
        result = _parse(_raw(), {"119293"})
        assert "119293" not in result

    def test_malformed_line_is_skipped(self) -> None:
        # "BADLINE;malformed data..." has a non-digit code field — should not raise
        raw = "BADLINE;malformed data without enough fields\n104481;X;Y;DSP;123.00;03-Apr-2026"
        result = _parse(raw, {"104481"})
        assert result == {"104481": Decimal("123.00")}

    def test_line_with_too_few_fields_is_skipped(self) -> None:
        raw = (
            "104481;only_three_fields;name\n146193;INF;INF;Edelweiss;45.67;03-Apr-2026"
        )
        result = _parse(raw, {"104481", "146193"})
        # 104481 line has only 3 fields → skipped; 146193 is valid
        assert "104481" not in result
        assert result["146193"] == Decimal("45.67")

    def test_section_header_lines_are_skipped(self) -> None:
        raw = (
            "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n"
            "Scheme Code;ISIN Div;ISIN Reinvest;Name;NAV;Date\n"
            "104481;INF;INF;DSP;123.00;03-Apr-2026\n"
        )
        result = _parse(raw, {"104481"})
        assert result == {"104481": Decimal("123.00")}

    def test_blank_lines_are_skipped(self) -> None:
        raw = "\n\n104481;INF;INF;DSP;123.00;03-Apr-2026\n\n"
        result = _parse(raw, {"104481"})
        assert result == {"104481": Decimal("123.00")}

    def test_empty_input_returns_empty_dict(self) -> None:
        assert _parse("", ALL_VALID_CODES) == {}

    def test_empty_codes_set_returns_empty_dict(self) -> None:
        assert _parse(_raw(), set()) == {}

    def test_duplicate_code_in_file_last_write_wins(self) -> None:
        # Defensive: if the same code appears twice, later value overwrites
        raw = (
            "104481;INF;INF;DSP First;100.00;03-Apr-2026\n"
            "104481;INF;INF;DSP Second;200.00;03-Apr-2026\n"
        )
        result = _parse(raw, {"104481"})
        assert result["104481"] == Decimal("200.00")

    def test_whitespace_around_fields_is_stripped(self) -> None:
        raw = "  104481 ; INF ; INF ; DSP ;  123.456 ; 03-Apr-2026\n"
        result = _parse(raw, {"104481"})
        assert result["104481"] == Decimal("123.456")


# ---------------------------------------------------------------------------
# fetch_navs — integration over _load_source + _parse, still offline
# ---------------------------------------------------------------------------


class TestFetchNavs:
    def test_reads_from_path_object(self) -> None:
        result = fetch_navs({"104481", "146193"}, source=FIXTURE)
        assert result["104481"] == Decimal("123.4560")
        assert result["146193"] == Decimal("45.6780")

    def test_reads_from_path_string(self) -> None:
        result = fetch_navs({"104481"}, source=str(FIXTURE))
        assert result["104481"] == Decimal("123.4560")

    def test_missing_code_absent_not_raised(self) -> None:
        result = fetch_navs({"999999"}, source=FIXTURE)
        assert result == {}

    def test_all_11_portfolio_schemes_resolved(self) -> None:
        result = fetch_navs(ALL_VALID_CODES, source=FIXTURE)
        assert result.keys() == ALL_VALID_CODES

    def test_missing_codes_logged_as_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        with caplog.at_level(logging.WARNING, logger="src.mf.nav_fetcher"):
            fetch_navs({"104481", "999999"}, source=FIXTURE)
        assert "999999" in caplog.text

    def test_file_not_found_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            fetch_navs({"104481"}, source=Path("/nonexistent/path/navall.txt"))
