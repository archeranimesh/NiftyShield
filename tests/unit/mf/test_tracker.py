"""Unit tests for src/mf/tracker.py.

Three test classes:

  TestSchemePnL   — pure math, no mocking
  TestAggregate   — pure aggregation math, no mocking
  TestMFTracker   — integration of store + fetcher; store and fetcher are mocked

No network.  No DB.  No file I/O.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, call

import pytest

from src.mf.models import MFNavSnapshot
from src.mf.tracker import (
    MFHolding,
    MFTracker,
    PortfolioPnL,
    SchemePnL,
    _aggregate,
    _scheme_pnl,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

TODAY = date(2026, 4, 3)

# Two schemes with known numbers for deterministic P&L assertions
HOLDING_A = MFHolding(
    amfi_code="104481",
    scheme_name="DSP Midcap Fund - Regular Plan - Growth",
    total_units=Decimal("4020.602"),
    total_invested=Decimal("439978.00"),
)
HOLDING_B = MFHolding(
    amfi_code="146193",
    scheme_name="Edelweiss Small Cap Fund - Regular Plan - Growth",
    total_units=Decimal("8962.544"),
    total_invested=Decimal("379981.00"),
)

NAV_A = Decimal("123.4560")
NAV_B = Decimal("45.6780")

# current_value = units × nav, quantized to 2 dp
CURRENT_VALUE_A = (HOLDING_A.total_units * NAV_A).quantize(Decimal("0.01"))
CURRENT_VALUE_B = (HOLDING_B.total_units * NAV_B).quantize(Decimal("0.01"))


def _mock_store(holdings: dict) -> MagicMock:
    store = MagicMock()
    store.get_holdings.return_value = holdings
    return store


def _mock_fetcher(navs: dict[str, Decimal]):
    return lambda codes: {k: navs[k] for k in codes if k in navs}


# ---------------------------------------------------------------------------
# TestSchemePnL — pure computation, no mocking
# ---------------------------------------------------------------------------


class TestSchemePnL:
    def test_current_value_is_units_times_nav(self) -> None:
        result = _scheme_pnl(HOLDING_A, NAV_A)
        assert result.current_value == CURRENT_VALUE_A

    def test_pnl_is_current_value_minus_invested(self) -> None:
        result = _scheme_pnl(HOLDING_A, NAV_A)
        assert result.pnl == CURRENT_VALUE_A - HOLDING_A.total_invested

    def test_pnl_pct_calculation(self) -> None:
        result = _scheme_pnl(HOLDING_A, NAV_A)
        expected = (result.pnl / HOLDING_A.total_invested * Decimal("100")).quantize(
            Decimal("0.01")
        )
        assert result.pnl_pct == expected

    def test_current_value_quantized_to_two_dp(self) -> None:
        result = _scheme_pnl(HOLDING_A, NAV_A)
        assert result.current_value == result.current_value.quantize(Decimal("0.01"))

    def test_pnl_pct_quantized_to_two_dp(self) -> None:
        result = _scheme_pnl(HOLDING_A, NAV_A)
        assert result.pnl_pct == result.pnl_pct.quantize(Decimal("0.01"))

    def test_fields_passed_through_unchanged(self) -> None:
        result = _scheme_pnl(HOLDING_A, NAV_A)
        assert result.amfi_code == HOLDING_A.amfi_code
        assert result.current_nav == NAV_A
        assert result.total_units == HOLDING_A.total_units
        assert result.total_invested == HOLDING_A.total_invested

    def test_zero_invested_gives_zero_pnl_pct(self) -> None:
        holding = MFHolding("000000", "Test Scheme", Decimal("100"), Decimal("0"))
        result = _scheme_pnl(holding, Decimal("50.00"))
        assert result.pnl_pct == Decimal("0.00")

    def test_loss_scenario_pnl_is_negative(self) -> None:
        # NAV well below cost
        holding = MFHolding(
            "000001", "Test Scheme", Decimal("100"), Decimal("10000.00")
        )
        result = _scheme_pnl(holding, Decimal("50.00"))
        assert result.pnl < Decimal("0")
        assert result.pnl_pct < Decimal("0")


# ---------------------------------------------------------------------------
# TestAggregate — pure aggregation, no mocking
# ---------------------------------------------------------------------------


class TestAggregate:
    def _two_schemes(self) -> list[SchemePnL]:
        return [_scheme_pnl(HOLDING_A, NAV_A), _scheme_pnl(HOLDING_B, NAV_B)]

    def test_total_invested_is_sum_of_schemes(self) -> None:
        result = _aggregate(TODAY, self._two_schemes())
        expected = HOLDING_A.total_invested + HOLDING_B.total_invested
        assert result.total_invested == expected

    def test_total_current_value_is_sum_of_scheme_values(self) -> None:
        result = _aggregate(TODAY, self._two_schemes())
        expected = CURRENT_VALUE_A + CURRENT_VALUE_B
        assert result.total_current_value == expected

    def test_total_pnl_equals_value_minus_invested(self) -> None:
        result = _aggregate(TODAY, self._two_schemes())
        assert result.total_pnl == result.total_current_value - result.total_invested

    def test_snapshot_date_preserved(self) -> None:
        result = _aggregate(TODAY, self._two_schemes())
        assert result.snapshot_date == TODAY

    def test_schemes_list_preserved(self) -> None:
        schemes = self._two_schemes()
        result = _aggregate(TODAY, schemes)
        assert result.schemes == schemes

    def test_empty_schemes_returns_zero_portfolio(self) -> None:
        result = _aggregate(TODAY, [])
        assert result.total_invested == Decimal("0")
        assert result.total_current_value == Decimal("0")
        assert result.total_pnl == Decimal("0")
        assert result.total_pnl_pct == Decimal("0")


# ---------------------------------------------------------------------------
# TestMFTracker — orchestration tests; store and fetcher are mocked
# ---------------------------------------------------------------------------


class TestMFTracker:
    def test_calls_get_holdings_once(self) -> None:
        store = _mock_store({HOLDING_A.amfi_code: HOLDING_A})
        fetcher = _mock_fetcher({HOLDING_A.amfi_code: NAV_A})
        MFTracker(store, fetcher).record_snapshot(TODAY)
        store.get_holdings.assert_called_once()

    def test_fetches_navs_for_all_held_codes(self) -> None:
        holdings = {HOLDING_A.amfi_code: HOLDING_A, HOLDING_B.amfi_code: HOLDING_B}
        nav_fetcher = MagicMock(
            return_value={HOLDING_A.amfi_code: NAV_A, HOLDING_B.amfi_code: NAV_B}
        )
        store = _mock_store(holdings)
        MFTracker(store, nav_fetcher).record_snapshot(TODAY)
        nav_fetcher.assert_called_once_with({HOLDING_A.amfi_code, HOLDING_B.amfi_code})

    def test_upserts_nav_snapshot_per_scheme(self) -> None:
        holdings = {HOLDING_A.amfi_code: HOLDING_A, HOLDING_B.amfi_code: HOLDING_B}
        store = _mock_store(holdings)
        fetcher = _mock_fetcher(
            {HOLDING_A.amfi_code: NAV_A, HOLDING_B.amfi_code: NAV_B}
        )
        MFTracker(store, fetcher).record_snapshot(TODAY)
        assert store.upsert_nav_snapshot.call_count == 2

    def test_upserts_correct_snapshot_values(self) -> None:
        store = _mock_store({HOLDING_A.amfi_code: HOLDING_A})
        fetcher = _mock_fetcher({HOLDING_A.amfi_code: NAV_A})
        MFTracker(store, fetcher).record_snapshot(TODAY)
        expected = MFNavSnapshot(
            amfi_code=HOLDING_A.amfi_code,
            scheme_name=HOLDING_A.scheme_name,
            snapshot_date=TODAY,
            nav=NAV_A,
        )
        store.upsert_nav_snapshot.assert_called_once_with(expected)

    def test_returns_portfolio_pnl_type(self) -> None:
        store = _mock_store({HOLDING_A.amfi_code: HOLDING_A})
        fetcher = _mock_fetcher({HOLDING_A.amfi_code: NAV_A})
        result = MFTracker(store, fetcher).record_snapshot(TODAY)
        assert isinstance(result, PortfolioPnL)

    def test_pnl_math_matches_manual_calculation(self) -> None:
        store = _mock_store({HOLDING_A.amfi_code: HOLDING_A})
        fetcher = _mock_fetcher({HOLDING_A.amfi_code: NAV_A})
        result = MFTracker(store, fetcher).record_snapshot(TODAY)
        assert result.schemes[0].current_value == CURRENT_VALUE_A
        assert result.schemes[0].pnl == CURRENT_VALUE_A - HOLDING_A.total_invested

    def test_snapshot_date_defaults_to_today(self) -> None:
        store = _mock_store({HOLDING_A.amfi_code: HOLDING_A})
        fetcher = _mock_fetcher({HOLDING_A.amfi_code: NAV_A})
        result = MFTracker(store, fetcher).record_snapshot()
        assert result.snapshot_date == date.today()

    def test_explicit_snapshot_date_is_used(self) -> None:
        store = _mock_store({HOLDING_A.amfi_code: HOLDING_A})
        fetcher = _mock_fetcher({HOLDING_A.amfi_code: NAV_A})
        result = MFTracker(store, fetcher).record_snapshot(TODAY)
        assert result.snapshot_date == TODAY

    def test_empty_holdings_returns_empty_portfolio(self) -> None:
        store = _mock_store({})
        fetcher = MagicMock()
        result = MFTracker(store, fetcher).record_snapshot(TODAY)
        assert result.schemes == []
        assert result.total_invested == Decimal("0")
        fetcher.assert_not_called()

    def test_missing_nav_scheme_is_skipped(self) -> None:
        # HOLDING_B's code is not returned by the fetcher
        holdings = {HOLDING_A.amfi_code: HOLDING_A, HOLDING_B.amfi_code: HOLDING_B}
        store = _mock_store(holdings)
        fetcher = _mock_fetcher({HOLDING_A.amfi_code: NAV_A})  # B is missing
        result = MFTracker(store, fetcher).record_snapshot(TODAY)
        scheme_codes = [s.amfi_code for s in result.schemes]
        assert HOLDING_A.amfi_code in scheme_codes
        assert HOLDING_B.amfi_code not in scheme_codes

    def test_missing_nav_scheme_does_not_upsert(self) -> None:
        holdings = {HOLDING_A.amfi_code: HOLDING_A, HOLDING_B.amfi_code: HOLDING_B}
        store = _mock_store(holdings)
        fetcher = _mock_fetcher({HOLDING_A.amfi_code: NAV_A})  # B is missing
        MFTracker(store, fetcher).record_snapshot(TODAY)
        # Only one upsert — for A
        assert store.upsert_nav_snapshot.call_count == 1

    def test_missing_nav_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        holdings = {HOLDING_B.amfi_code: HOLDING_B}
        store = _mock_store(holdings)
        fetcher = _mock_fetcher({})  # nothing returned
        with caplog.at_level(logging.WARNING, logger="src.mf.tracker"):
            MFTracker(store, fetcher).record_snapshot(TODAY)
        assert HOLDING_B.amfi_code in caplog.text

    def test_two_schemes_total_invested_is_summed(self) -> None:
        holdings = {HOLDING_A.amfi_code: HOLDING_A, HOLDING_B.amfi_code: HOLDING_B}
        store = _mock_store(holdings)
        fetcher = _mock_fetcher(
            {HOLDING_A.amfi_code: NAV_A, HOLDING_B.amfi_code: NAV_B}
        )
        result = MFTracker(store, fetcher).record_snapshot(TODAY)
        expected = HOLDING_A.total_invested + HOLDING_B.total_invested
        assert result.total_invested == expected
