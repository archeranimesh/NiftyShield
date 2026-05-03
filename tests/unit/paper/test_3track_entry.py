"""Unit tests for scripts/paper_3track_entry.py (live-fetch auto mode)."""

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from scripts.paper_3track_entry import (
    LivePrices,
    auto_select_proxy,
    build_trades,
    compute_gate_results,
    compute_proxy_entry_price,
    derive_expiry,
    filter_proxy_candidates,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_row(strike: float, delta: float, bid: float = 10.0, ask: float = 12.0,
              oi: int = 10_000) -> dict:
    mid = (bid + ask) / 2.0
    return {
        "strike": strike, "delta": delta, "iv": 15.0,
        "ltp": mid, "mid": mid, "bid": bid, "ask": ask,
        "oi": oi, "instrument_key": f"NSE_FO|NIFTY_{int(strike)}CE",
    }


def _make_chain_entry(strike: float, delta: float, spot: float = 24000.0,
                      bid: float = 10.0, ask: float = 12.0, oi: int = 10_000) -> dict:
    """Build a minimal raw Upstox option chain entry."""
    return {
        "strike_price": strike,
        "underlying_spot_price": spot,
        "call_options": {
            "instrument_key": f"NSE_FO|NIFTY_{int(strike)}CE",
            "option_greeks": {"delta": delta, "iv": 15.0},
            "market_data": {
                "ltp": (bid + ask) / 2,
                "bid_price": bid, "ask_price": ask, "oi": oi,
            },
        },
        "put_options": {},
    }


def _make_prices(**kwargs) -> LivePrices:
    defaults = dict(
        entry_date=date(2026, 5, 7), expiry="2026-05-29",
        nifty_spot=Decimal("24000"), lot_size=65, cycle=1,
        niftybees_ltp=Decimal("384.50"), niftybees_qty=4055,
        futures_key="NSE_FO|NIFTY29MAY2026FUT",
        futures_price=Decimal("24100"),
        proxy_strike=21500.0, proxy_price=Decimal("2720.25"),
        proxy_actual_delta=Decimal("0.9050"),
        proxy_instrument_key="NSE_FO|NIFTY21500CE",
        proxy_oi=12_000, proxy_bid=2715.0, proxy_ask=2723.0,
    )
    defaults.update(kwargs)
    return LivePrices(**defaults)


# ── filter_proxy_candidates ───────────────────────────────────────────────────

class TestFilterProxyCandidates:
    def test_filters_to_delta_band(self):
        chain = [
            _make_chain_entry(21000, 0.95),   # edge of band
            _make_chain_entry(22000, 0.90),   # in band
            _make_chain_entry(23000, 0.70),   # out of band
            _make_chain_entry(24000, 0.50),   # out of band
        ]
        rows = filter_proxy_candidates(chain)
        strikes = {r["strike"] for r in rows}
        assert 22000.0 in strikes
        assert 21000.0 in strikes
        assert 23000.0 not in strikes

    def test_excludes_entry_with_no_instrument_key(self):
        entry = _make_chain_entry(22000, 0.90)
        entry["call_options"]["instrument_key"] = ""
        rows = filter_proxy_candidates([entry])
        assert rows == []

    def test_sorted_by_delta_descending(self):
        chain = [
            _make_chain_entry(22500, 0.86),
            _make_chain_entry(22000, 0.91),
            _make_chain_entry(21500, 0.93),
        ]
        rows = filter_proxy_candidates(chain)
        deltas = [r["delta"] for r in rows]
        assert deltas == sorted(deltas, reverse=True)

    def test_empty_chain_returns_empty(self):
        assert filter_proxy_candidates([]) == []


# ── auto_select_proxy ─────────────────────────────────────────────────────────

class TestAutoSelectProxy:
    def test_picks_nearest_to_0_90(self):
        rows = [
            _make_row(21500, 0.93),  # 0.03 away
            _make_row(22000, 0.88),  # 0.02 away  ← winner
            _make_row(22500, 0.86),  # 0.04 away
        ]
        best = auto_select_proxy(rows)
        assert best["strike"] == 22000.0

    def test_tie_takes_higher_delta(self):
        # Both 0.02 away from 0.90
        rows = [
            _make_row(22000, 0.88),  # 0.02 away, delta=0.88
            _make_row(21500, 0.92),  # 0.02 away, delta=0.92 ← deeper ITM, wins
        ]
        best = auto_select_proxy(rows)
        assert best["strike"] == 21500.0
        assert best["delta"] == 0.92

    def test_exact_target_wins(self):
        rows = [
            _make_row(22000, 0.90),  # exact
            _make_row(21500, 0.93),
            _make_row(22500, 0.87),
        ]
        best = auto_select_proxy(rows)
        assert best["strike"] == 22000.0
        assert best["delta"] == 0.90

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="No CE strikes found"):
            auto_select_proxy([])


# ── compute_proxy_entry_price ─────────────────────────────────────────────────

class TestComputeProxyEntryPrice:
    def test_min_slippage_applied(self):
        # spread=1.0 → slippage=max(0.50, 0.50)=0.50; mid=100.50
        row = _make_row(22000, 0.90, bid=100.0, ask=101.0)
        price = compute_proxy_entry_price(row)
        assert price == Decimal("101.00")  # mid=100.50 + 0.50

    def test_wide_spread_slippage(self):
        # spread=10.0 → slippage=max(0.50, 5.0)=5.0; mid=105.0
        row = _make_row(22000, 0.90, bid=100.0, ask=110.0)
        price = compute_proxy_entry_price(row)
        assert price == Decimal("110.00")  # mid=105.0 + 5.0

    def test_returns_decimal(self):
        row = _make_row(22000, 0.90, bid=2715.0, ask=2723.0)
        price = compute_proxy_entry_price(row)
        assert isinstance(price, Decimal)


# ── build_trades ──────────────────────────────────────────────────────────────

class TestBuildTrades:
    def test_returns_three_trades(self):
        trades = build_trades(_make_prices())
        assert len(trades) == 3

    def test_strategy_names(self):
        trades = build_trades(_make_prices())
        names = {t.strategy_name for t in trades}
        assert names == {"paper_nifty_spot", "paper_nifty_futures", "paper_nifty_proxy"}

    def test_leg_roles(self):
        trades = build_trades(_make_prices())
        roles = {t.leg_role for t in trades}
        assert roles == {"base_etf", "base_futures", "base_ditm_call"}

    def test_spot_uses_niftybees_key(self):
        trades = build_trades(_make_prices())
        spot = next(t for t in trades if t.leg_role == "base_etf")
        assert spot.instrument_key == "NSE_EQ|INF204KB14I2"

    def test_spot_qty_from_prices(self):
        p = _make_prices(niftybees_qty=4055)
        trades = build_trades(p)
        spot = next(t for t in trades if t.leg_role == "base_etf")
        assert spot.quantity == 4055

    def test_proxy_price_from_prices(self):
        p = _make_prices(proxy_price=Decimal("2720.25"))
        trades = build_trades(p)
        proxy = next(t for t in trades if t.leg_role == "base_ditm_call")
        assert proxy.price == Decimal("2720.25")

    def test_cycle_tag_in_notes(self):
        p = _make_prices(cycle=3)
        trades = build_trades(p)
        for trade in trades:
            assert "Cycle 3" in trade.notes


# ── compute_gate_results ──────────────────────────────────────────────────────

class TestComputeGateResults:
    def test_both_pass(self):
        p = _make_prices(proxy_oi=10_000, proxy_bid=2715.0, proxy_ask=2718.0)
        gates = compute_gate_results(p)
        assert "PASS" in gates["oi"]
        assert "PASS" in gates["spread"]

    def test_oi_warn(self):
        p = _make_prices(proxy_oi=3_000, proxy_bid=2715.0, proxy_ask=2718.0)
        gates = compute_gate_results(p)
        assert "WARN" in gates["oi"]

    def test_spread_warn(self):
        p = _make_prices(proxy_oi=10_000, proxy_bid=2715.0, proxy_ask=2725.0)
        gates = compute_gate_results(p)
        assert "WARN" in gates["spread"]

    def test_gate_values_displayed(self):
        p = _make_prices(proxy_oi=7_500, proxy_bid=100.0, proxy_ask=102.0)
        gates = compute_gate_results(p)
        assert "7,500" in gates["oi"]
        assert "2.00" in gates["spread"]


# ── derive_expiry ─────────────────────────────────────────────────────────────

class TestDeriveExpiry:
    def _make_lookup(self, expiry_dates: list[str]) -> object:
        """Stub InstrumentLookup that returns futures for given expiry dates."""
        from unittest.mock import MagicMock
        lookup = MagicMock()
        lookup.search_futures.return_value = [
            {"instrument_key": f"NSE_FO|NIFTY{d.replace('-','')}FUT", "expiry": d}
            for d in expiry_dates
        ]
        return lookup

    def test_prefers_30_to_45_dte(self):
        from datetime import timedelta
        today = date(2026, 5, 7)
        target = (today + timedelta(days=35)).isoformat()
        far = (today + timedelta(days=70)).isoformat()
        lookup = self._make_lookup([far, target])
        result = derive_expiry(lookup, today)
        assert result == target

    def test_fallback_to_nearest_future_when_no_30_45(self):
        from datetime import timedelta
        today = date(2026, 5, 7)
        near = (today + timedelta(days=10)).isoformat()
        far = (today + timedelta(days=60)).isoformat()
        lookup = self._make_lookup([near, far])
        result = derive_expiry(lookup, today)
        assert result == near

    def test_raises_when_no_futures_in_bod(self):
        from unittest.mock import MagicMock
        lookup = MagicMock()
        lookup.search_futures.return_value = []
        with pytest.raises(ValueError, match="No NIFTY futures found in BOD"):
            derive_expiry(lookup, date.today())

    def test_raises_when_all_expiries_are_past(self):
        from unittest.mock import MagicMock
        lookup = MagicMock()
        lookup.search_futures.return_value = [
            {"instrument_key": "NSE_FO|NIFTY2020FUT", "expiry": "2020-01-01"}
        ]
        with pytest.raises(ValueError, match="No future NIFTY expiry"):
            derive_expiry(lookup, date.today())
