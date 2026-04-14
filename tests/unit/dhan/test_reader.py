"""Tests for src/dhan/reader.py — classify, build, enrich, summarise."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.dhan.models import DhanHolding
from src.dhan.reader import (
    build_dhan_holdings,
    build_dhan_summary,
    build_security_id_map,
    classify_holding,
    enrich_with_ltp,
    enrich_with_upstox_prices,
    upstox_keys_for_holdings,
)

FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures" / "responses"


@pytest.fixture
def raw_holdings() -> list[dict]:
    """Load the sample Dhan holdings fixture."""
    with open(FIXTURES / "dhan_holdings.json") as f:
        data = json.load(f)
    return data["response"]


@pytest.fixture
def ltp_response() -> dict:
    """Load the sample Dhan LTP fixture."""
    with open(FIXTURES / "dhan_ltp.json") as f:
        data = json.load(f)
    return data["response"]["data"]


# ── classify_holding ─────────────────────────────────────────────


class TestClassifyHolding:

    def test_equity_default(self):
        assert classify_holding("NIFTYIETF") == "EQUITY"

    def test_bond_liquidcase(self):
        assert classify_holding("LIQUIDCASE") == "BOND"

    def test_bond_liquidbees(self):
        assert classify_holding("LIQUIDBEES") == "BOND"

    def test_bond_case_insensitive(self):
        assert classify_holding("liquidcase") == "BOND"

    def test_unknown_defaults_to_equity(self):
        assert classify_holding("RELIANCE") == "EQUITY"

    def test_whitespace_stripped(self):
        assert classify_holding("  LIQUIDCASE  ") == "BOND"


# ── build_dhan_holdings ──────────────────────────────────────────


class TestBuildDhanHoldings:

    def test_all_holdings_returned_without_filter(self, raw_holdings):
        holdings = build_dhan_holdings(raw_holdings)
        assert len(holdings) == 4
        symbols = {h.trading_symbol for h in holdings}
        assert symbols == {"NIFTYIETF", "LIQUIDCASE", "EBBETF0431", "LIQUIDBEES"}

    def test_excludes_strategy_isins(self, raw_holdings):
        exclude = {"INF754K01LE1", "INF732E01037"}  # EBBETF0431 + LIQUIDBEES
        holdings = build_dhan_holdings(raw_holdings, exclude_isins=exclude)
        assert len(holdings) == 2
        symbols = {h.trading_symbol for h in holdings}
        assert symbols == {"NIFTYIETF", "LIQUIDCASE"}

    def test_classification_applied(self, raw_holdings):
        exclude = {"INF754K01LE1", "INF732E01037"}
        holdings = build_dhan_holdings(raw_holdings, exclude_isins=exclude)
        by_sym = {h.trading_symbol: h for h in holdings}
        assert by_sym["NIFTYIETF"].classification == "EQUITY"
        assert by_sym["LIQUIDCASE"].classification == "BOND"

    def test_decimal_precision(self, raw_holdings):
        exclude = {"INF754K01LE1", "INF732E01037"}
        holdings = build_dhan_holdings(raw_holdings, exclude_isins=exclude)
        nifty = next(h for h in holdings if h.trading_symbol == "NIFTYIETF")
        assert isinstance(nifty.avg_cost_price, Decimal)
        assert nifty.avg_cost_price == Decimal("268.5")

    def test_ltp_initially_none(self, raw_holdings):
        holdings = build_dhan_holdings(raw_holdings)
        for h in holdings:
            assert h.ltp is None

    def test_zero_qty_skipped(self):
        raw = [{"tradingSymbol": "TEST", "isin": "INF000001", "securityId": "99",
                "totalQty": 0, "collateralQty": 0, "avgCostPrice": 100}]
        assert build_dhan_holdings(raw) == []

    def test_missing_isin_skipped(self):
        raw = [{"tradingSymbol": "TEST", "isin": "", "securityId": "99",
                "totalQty": 10, "collateralQty": 0, "avgCostPrice": 100}]
        assert build_dhan_holdings(raw) == []

    def test_malformed_entry_skipped(self):
        raw = [None, {"bad": "data"}, 42]
        # Should not raise — malformed entries are skipped
        result = build_dhan_holdings(raw)
        assert result == []

    def test_security_id_stored(self, raw_holdings):
        holdings = build_dhan_holdings(raw_holdings)
        nifty = next(h for h in holdings if h.trading_symbol == "NIFTYIETF")
        assert nifty.security_id == "13611"


# ── build_security_id_map ────────────────────────────────────────


class TestBuildSecurityIdMap:

    def test_groups_by_exchange(self, raw_holdings):
        exclude = {"INF754K01LE1", "INF732E01037"}
        holdings = build_dhan_holdings(raw_holdings, exclude_isins=exclude)
        sid_map = build_security_id_map(holdings)
        assert "NSE_EQ" in sid_map
        assert set(sid_map["NSE_EQ"]) == {13611, 25780}

    def test_empty_holdings(self):
        assert build_security_id_map([]) == {}

    def test_non_numeric_security_id_skipped(self):
        h = DhanHolding(
            trading_symbol="TEST", isin="INF000", security_id="abc",
            exchange="NSE_EQ", total_qty=10, collateral_qty=0,
            avg_cost_price=Decimal("100"), classification="EQUITY",
        )
        assert build_security_id_map([h]) == {}


# ── enrich_with_ltp ──────────────────────────────────────────────


class TestEnrichWithLtp:

    def test_enriches_matching_holdings(self, raw_holdings, ltp_response):
        exclude = {"INF754K01LE1", "INF732E01037"}
        holdings = build_dhan_holdings(raw_holdings, exclude_isins=exclude)
        enriched = enrich_with_ltp(holdings, ltp_response)

        nifty = next(h for h in enriched if h.trading_symbol == "NIFTYIETF")
        assert nifty.ltp == Decimal("275.40") or nifty.ltp == Decimal("275.4")

        liquid = next(h for h in enriched if h.trading_symbol == "LIQUIDCASE")
        assert liquid.ltp == Decimal("1005.50") or liquid.ltp == Decimal("1005.5")

    def test_missing_ltp_stays_none(self, raw_holdings):
        exclude = {"INF754K01LE1", "INF732E01037"}
        holdings = build_dhan_holdings(raw_holdings, exclude_isins=exclude)
        enriched = enrich_with_ltp(holdings, {})  # empty LTP data
        for h in enriched:
            assert h.ltp is None

    def test_preserves_all_fields(self, raw_holdings, ltp_response):
        exclude = {"INF754K01LE1", "INF732E01037"}
        holdings = build_dhan_holdings(raw_holdings, exclude_isins=exclude)
        enriched = enrich_with_ltp(holdings, ltp_response)
        for orig, enr in zip(holdings, enriched):
            assert enr.trading_symbol == orig.trading_symbol
            assert enr.isin == orig.isin
            assert enr.total_qty == orig.total_qty
            assert enr.avg_cost_price == orig.avg_cost_price
            assert enr.classification == orig.classification


# ── build_dhan_summary ───────────────────────────────────────────


class TestBuildDhanSummary:

    def _make_enriched(self) -> list[DhanHolding]:
        return [
            DhanHolding(
                trading_symbol="NIFTYIETF", isin="INF109K012R6",
                security_id="13611", exchange="NSE_EQ",
                total_qty=500, collateral_qty=500,
                avg_cost_price=Decimal("268.50"), classification="EQUITY",
                ltp=Decimal("275.40"),
            ),
            DhanHolding(
                trading_symbol="LIQUIDCASE", isin="INF0R8F01034",
                security_id="25780", exchange="NSE_EQ",
                total_qty=200, collateral_qty=200,
                avg_cost_price=Decimal("1003.25"), classification="BOND",
                ltp=Decimal("1005.50"),
            ),
        ]

    def test_equity_bond_split(self):
        summary = build_dhan_summary(self._make_enriched(), date(2026, 4, 14))
        assert len(summary.equity_holdings) == 1
        assert len(summary.bond_holdings) == 1
        assert summary.equity_holdings[0].trading_symbol == "NIFTYIETF"
        assert summary.bond_holdings[0].trading_symbol == "LIQUIDCASE"

    def test_equity_values(self):
        summary = build_dhan_summary(self._make_enriched(), date(2026, 4, 14))
        assert summary.equity_value == Decimal("275.40") * 500
        assert summary.equity_basis == Decimal("268.50") * 500
        assert summary.equity_pnl == summary.equity_value - summary.equity_basis

    def test_bond_values(self):
        summary = build_dhan_summary(self._make_enriched(), date(2026, 4, 14))
        assert summary.bond_value == Decimal("1005.50") * 200
        assert summary.bond_basis == Decimal("1003.25") * 200
        assert summary.bond_pnl == summary.bond_value - summary.bond_basis

    def test_no_prev_holdings_no_deltas(self):
        summary = build_dhan_summary(self._make_enriched(), date(2026, 4, 14))
        assert summary.equity_day_delta is None
        assert summary.bond_day_delta is None

    def test_day_delta_computed_with_prev(self):
        prev = {
            "INF109K012R6": DhanHolding(
                trading_symbol="NIFTYIETF", isin="INF109K012R6",
                security_id="13611", exchange="NSE_EQ",
                total_qty=500, collateral_qty=500,
                avg_cost_price=Decimal("268.50"), classification="EQUITY",
                ltp=Decimal("270.00"),
            ),
            "INF0R8F01034": DhanHolding(
                trading_symbol="LIQUIDCASE", isin="INF0R8F01034",
                security_id="25780", exchange="NSE_EQ",
                total_qty=200, collateral_qty=200,
                avg_cost_price=Decimal("1003.25"), classification="BOND",
                ltp=Decimal("1004.00"),
            ),
        }
        summary = build_dhan_summary(self._make_enriched(), date(2026, 4, 14), prev)
        # equity: 275.40*500 - 270.00*500 = 2700
        assert summary.equity_day_delta == Decimal("275.40") * 500 - Decimal("270.00") * 500
        # bond: 1005.50*200 - 1004.00*200 = 300
        assert summary.bond_day_delta == Decimal("1005.50") * 200 - Decimal("1004.00") * 200

    def test_empty_holdings(self):
        summary = build_dhan_summary([], date(2026, 4, 14))
        assert summary.equity_value == Decimal("0")
        assert summary.bond_value == Decimal("0")
        assert len(summary.equity_holdings) == 0
        assert len(summary.bond_holdings) == 0

    def test_pnl_pct_computed(self):
        summary = build_dhan_summary(self._make_enriched(), date(2026, 4, 14))
        assert summary.equity_pnl_pct is not None
        assert summary.equity_pnl_pct > 0
        assert summary.bond_pnl_pct is not None
        assert summary.bond_pnl_pct > 0


# ── enrich_with_upstox_prices ─────────────────────────────────────


def _bare_holding(symbol: str, isin: str, security_id: str, classification: str) -> DhanHolding:
    return DhanHolding(
        trading_symbol=symbol,
        isin=isin,
        security_id=security_id,
        exchange="NSE_EQ",
        total_qty=100,
        collateral_qty=100,
        avg_cost_price=Decimal("200.00"),
        classification=classification,
        ltp=None,
    )


class TestEnrichWithUpstoxPrices:
    def test_enriches_from_nse_eq_key(self):
        h = _bare_holding("NIFTYIETF", "INF109K012R6", "13611", "EQUITY")
        prices = {"NSE_EQ|INF109K012R6": 275.40}
        result = enrich_with_upstox_prices([h], prices)
        assert result[0].ltp == Decimal("275.40")

    def test_missing_key_stays_none(self):
        h = _bare_holding("NIFTYIETF", "INF109K012R6", "13611", "EQUITY")
        result = enrich_with_upstox_prices([h], {})
        assert result[0].ltp is None

    def test_preserves_all_fields(self):
        h = _bare_holding("LIQUIDCASE", "INF0R8F01034", "25780", "BOND")
        prices = {"NSE_EQ|INF0R8F01034": 1005.50}
        result = enrich_with_upstox_prices([h], prices)
        r = result[0]
        assert r.trading_symbol == "LIQUIDCASE"
        assert r.isin == "INF0R8F01034"
        assert r.classification == "BOND"
        assert r.total_qty == 100
        assert r.avg_cost_price == Decimal("200.00")

    def test_multiple_holdings_independent(self):
        eq = _bare_holding("NIFTYIETF", "INF109K012R6", "13611", "EQUITY")
        bd = _bare_holding("LIQUIDCASE", "INF0R8F01034", "25780", "BOND")
        prices = {
            "NSE_EQ|INF109K012R6": 275.40,
            "NSE_EQ|INF0R8F01034": 1005.50,
        }
        result = enrich_with_upstox_prices([eq, bd], prices)
        assert result[0].ltp == Decimal("275.40")
        assert result[1].ltp == Decimal("1005.50")

    def test_partial_match_leaves_missing_as_none(self):
        eq = _bare_holding("NIFTYIETF", "INF109K012R6", "13611", "EQUITY")
        bd = _bare_holding("LIQUIDCASE", "INF0R8F01034", "25780", "BOND")
        prices = {"NSE_EQ|INF109K012R6": 275.40}  # only equity present
        result = enrich_with_upstox_prices([eq, bd], prices)
        assert result[0].ltp == Decimal("275.40")
        assert result[1].ltp is None

    def test_empty_holdings_returns_empty(self):
        assert enrich_with_upstox_prices([], {"NSE_EQ|SOMETHING": 100.0}) == []


# ── upstox_keys_for_holdings ─────────────────────────────────────


class TestUpstoxKeysForHoldings:
    def test_derives_nse_eq_keys(self):
        eq = _bare_holding("NIFTYIETF", "INF109K012R6", "13611", "EQUITY")
        bd = _bare_holding("LIQUIDCASE", "INF0R8F01034", "25780", "BOND")
        keys = upstox_keys_for_holdings([eq, bd])
        assert keys == {"NSE_EQ|INF109K012R6", "NSE_EQ|INF0R8F01034"}

    def test_empty_returns_empty_set(self):
        assert upstox_keys_for_holdings([]) == set()

    def test_single_holding(self):
        h = _bare_holding("NIFTYIETF", "INF109K012R6", "13611", "EQUITY")
        assert upstox_keys_for_holdings([h]) == {"NSE_EQ|INF109K012R6"}
