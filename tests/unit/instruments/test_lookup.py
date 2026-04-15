"""Tests for InstrumentLookup search ranking.

All tests are offline — no network, no filesystem beyond in-memory fixtures.
Covers:
  - _score_query: exact / prefix / fuzzy tiers
  - _best_score: field selection across multiple fields
  - InstrumentLookup.search: ranking order, segment/instrument_type filters,
    min_score cutoff, empty/blank query, max_results cap
"""

from __future__ import annotations

import pytest

from src.instruments.lookup import (
    InstrumentLookup,
    _best_score,
    _score_query,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _inst(
    trading_symbol: str = "",
    name: str = "",
    underlying_symbol: str = "",
    short_name: str = "",
    segment: str = "NSE_EQ",
    instrument_type: str = "EQ",
    instrument_key: str = "",
) -> dict:
    return {
        "trading_symbol": trading_symbol,
        "name": name,
        "underlying_symbol": underlying_symbol,
        "short_name": short_name,
        "segment": segment,
        "instrument_type": instrument_type,
        "instrument_key": instrument_key or f"NSE_EQ|{trading_symbol}",
    }


RELIANCE = _inst("RELIANCE", "Reliance Industries Ltd", instrument_key="NSE_EQ|RELIANCE")
HDFCBANK = _inst("HDFCBANK", "HDFC Bank Limited", instrument_key="NSE_EQ|HDFCBANK")
EBBETF = _inst("EBBETF0431", "EDELWEISS BHARAT BOND ETF - APRIL 2031", instrument_key="NSE_EQ|EBBETF0431")
NIFTY_PE = _inst(
    "NIFTY2562523000PE", "NIFTY 23000 PE", underlying_symbol="NIFTY",
    segment="NSE_FO", instrument_type="PE", instrument_key="NSE_FO|NIFTY25JUN23000PE"
)
NIFTY_CE = _inst(
    "NIFTY2562523000CE", "NIFTY 23000 CE", underlying_symbol="NIFTY",
    segment="NSE_FO", instrument_type="CE", instrument_key="NSE_FO|NIFTY25JUN23000CE"
)
NIFTY_FUT = _inst(
    "NIFTYJUN2025FUT", "NIFTY FUT JUN", underlying_symbol="NIFTY",
    segment="NSE_FO", instrument_type="FUT",
)

ALL_INSTRUMENTS = [RELIANCE, HDFCBANK, EBBETF, NIFTY_PE, NIFTY_CE, NIFTY_FUT]


# ── _score_query tests ────────────────────────────────────────────────────────

class TestScoreQuery:
    def test_exact_match_returns_one(self):
        score, reason = _score_query("reliance", "reliance")
        assert score == 1.0
        assert reason == "exact"

    def test_exact_is_case_insensitive(self):
        score, reason = _score_query("reliance", "RELIANCE")
        assert score == 1.0
        assert reason == "exact"

    def test_prefix_match_returns_point_92(self):
        score, reason = _score_query("reli", "reliance")
        assert score == 0.92
        assert reason == "prefix"

    def test_prefix_requires_start_not_substring(self):
        # "liance" is a substring but not a prefix → should NOT be prefix tier
        score, reason = _score_query("liance", "reliance")
        assert reason == "fuzzy"
        assert score < 0.92

    def test_fuzzy_returns_positive_for_close_match(self):
        score, reason = _score_query("reliancee", "reliance")  # one extra char
        assert reason == "fuzzy"
        assert score > 0.65

    def test_empty_candidate_returns_zero(self):
        score, reason = _score_query("nifty", "")
        assert score == 0.0
        assert reason == "none"

    def test_exact_beats_prefix(self):
        exact_score, _ = _score_query("hdfc", "hdfc")
        prefix_score, _ = _score_query("hdfc", "hdfcbank")
        assert exact_score > prefix_score

    def test_prefix_beats_fuzzy(self):
        prefix_score, _ = _score_query("nifty", "nifty25jun")
        fuzzy_score, _ = _score_query("nifty", "infy")  # similar length, fuzzy
        assert prefix_score > fuzzy_score


# ── _best_score tests ─────────────────────────────────────────────────────────

class TestBestScore:
    def test_exact_on_trading_symbol(self):
        score, reason = _best_score("reliance", RELIANCE)
        assert score == 1.0
        assert reason == "exact"

    def test_prefix_on_name_field(self):
        # "hdfc bank" is a prefix of "hdfc bank limited"
        score, reason = _best_score("hdfc bank", HDFCBANK)
        assert score == 0.92
        assert reason == "prefix"

    def test_picks_best_across_fields(self):
        # "nifty" is an exact match on underlying_symbol field of NIFTY_PE
        score, reason = _best_score("nifty", NIFTY_PE)
        assert score == 1.0
        assert reason == "exact"

    def test_unknown_query_returns_low_score(self):
        score, _ = _best_score("xyzgarbage999", RELIANCE)
        assert score < 0.65


# ── InstrumentLookup.search tests ─────────────────────────────────────────────

class TestInstrumentLookupSearch:
    @pytest.fixture
    def lookup(self) -> InstrumentLookup:
        return InstrumentLookup(ALL_INSTRUMENTS)

    # Happy-path: exact match is first

    def test_exact_match_is_first_result(self, lookup):
        results = lookup.search("RELIANCE")
        assert results[0]["trading_symbol"] == "RELIANCE"

    def test_prefix_match_returned(self, lookup):
        results = lookup.search("HDFC")
        symbols = [r["trading_symbol"] for r in results]
        assert "HDFCBANK" in symbols

    def test_results_sorted_by_score_descending(self, lookup):
        # "NIFTY" exact-matches underlying_symbol on NIFTY_PE and NIFTY_CE;
        # all NIFTY instruments should appear before RELIANCE or HDFCBANK
        results = lookup.search("NIFTY", segment="NSE_FO")
        assert len(results) > 0
        # First result must be a NIFTY instrument
        assert "NIFTY" in results[0]["underlying_symbol"].upper()

    def test_max_results_caps_output(self, lookup):
        results = lookup.search("NIFTY", max_results=2)
        assert len(results) <= 2

    # Segment and instrument_type filtering

    def test_segment_filter_excludes_non_matching(self, lookup):
        results = lookup.search("NIFTY", segment="NSE_FO")
        for r in results:
            assert r["segment"] == "NSE_FO"

    def test_instrument_type_filter(self, lookup):
        results = lookup.search("NIFTY", segment="NSE_FO", instrument_type="PE")
        for r in results:
            assert r["instrument_type"] == "PE"

    def test_equity_segment_excludes_options(self, lookup):
        results = lookup.search("NIFTY", segment="NSE_EQ")
        # No NSE_FO instruments in NSE_EQ results
        for r in results:
            assert r["segment"] == "NSE_EQ"

    # min_score cutoff

    def test_min_score_filters_low_confidence(self, lookup):
        # High min_score should exclude fuzzy-only matches
        results = lookup.search("EBBE", min_score=0.95)
        # prefix score is 0.92, so EBBETF should be excluded at 0.95 cutoff
        symbols = [r["trading_symbol"] for r in results]
        assert "EBBETF0431" not in symbols

    def test_min_score_zero_includes_all_positive(self, lookup):
        results = lookup.search("RELIANCE", min_score=0.0)
        assert len(results) > 0

    def test_exact_match_survives_high_min_score(self, lookup):
        results = lookup.search("RELIANCE", min_score=0.99)
        assert results[0]["trading_symbol"] == "RELIANCE"

    # Edge cases

    def test_empty_query_returns_empty(self, lookup):
        assert lookup.search("") == []

    def test_blank_query_returns_empty(self, lookup):
        assert lookup.search("   ") == []

    def test_no_match_returns_empty(self, lookup):
        results = lookup.search("ZZZZNOTASTOCK999", min_score=0.9)
        assert results == []

    def test_empty_instrument_list_returns_empty(self):
        lookup = InstrumentLookup([])
        assert lookup.search("RELIANCE") == []

    def test_case_insensitive_query(self, lookup):
        lower = lookup.search("reliance")
        upper = lookup.search("RELIANCE")
        assert [r["trading_symbol"] for r in lower] == [r["trading_symbol"] for r in upper]
