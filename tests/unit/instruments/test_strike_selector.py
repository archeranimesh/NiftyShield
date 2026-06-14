"""Unit tests for src/instruments/strike_selector.py.

All tests run offline using the nifty_chain_2026-04-07.json fixture.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from structlog.testing import capture_logs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.instruments.strike_selector import (
    _apply_liquidity_gate,
    _safe_float,
    _safe_price,
    _sides_for,
    filter_strikes_by_delta,
    rank_strikes,
)

_FIXTURE_PATH = Path("tests/fixtures/responses/option_chain/nifty_chain_2026-04-07.json")


def _load_chain() -> list[dict]:
    """Load the raw strikes list from the recorded Upstox fixture."""
    with _FIXTURE_PATH.open() as fh:
        return json.load(fh)["response"]["data"]


# ── _safe_float ───────────────────────────────────────────────────────────────


def test_safe_float_none_returns_default() -> None:
    assert _safe_float(None) == 0.0


def test_safe_float_valid_string() -> None:
    assert _safe_float("3.14") == pytest.approx(3.14)


def test_safe_float_invalid_returns_custom_default() -> None:
    assert _safe_float("N/A", default=-1.0) == -1.0


# ── _safe_price ───────────────────────────────────────────────────────────────


def test_safe_price_none_returns_none() -> None:
    assert _safe_price(None) is None


def test_safe_price_garbage_returns_none() -> None:
    assert _safe_price("N/A") is None


def test_safe_price_valid_string_returns_decimal() -> None:
    assert _safe_price("100.50") == Decimal("100.50")


def test_safe_price_valid_float_returns_decimal() -> None:
    result = _safe_price(3.14)
    assert isinstance(result, Decimal)


# ── _sides_for ────────────────────────────────────────────────────────────────


def test_sides_for_ce() -> None:
    assert _sides_for("CE") == ["CE"]


def test_sides_for_pe() -> None:
    assert _sides_for("PE") == ["PE"]


def test_sides_for_both() -> None:
    assert _sides_for("BOTH") == ["CE", "PE"]


# ── filter_strikes_by_delta ───────────────────────────────────────────────────


def test_filter_ce_delta_range_returns_nonempty() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "CE", 0.20, 0.40)
    assert len(rows) > 0


def test_filter_pe_delta_range_returns_nonempty() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "PE", 0.20, 0.40)
    assert len(rows) > 0


def test_filter_ce_all_deltas_within_range() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "CE", 0.20, 0.40)
    for r in rows:
        assert 0.20 <= abs(r["delta"]) <= 0.40


def test_filter_pe_all_deltas_within_range() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "PE", 0.20, 0.40)
    for r in rows:
        assert 0.20 <= abs(r["delta"]) <= 0.40


def test_filter_empty_chain_returns_empty() -> None:
    assert filter_strikes_by_delta([], "BOTH", 0.20, 0.40) == []


def test_filter_no_match_returns_empty() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "BOTH", 1.01, 1.50)
    assert rows == []


def test_filter_garbage_ltp_entry_excluded() -> None:
    """Chain entry with un-coerceable ltp is excluded and a WARN is logged."""
    chain = [
        {
            "strike_price": 22000,
            "put_options": {
                "instrument_key": "NSE_FO|12345",
                "option_greeks": {"delta": -0.30, "iv": 15.0},
                "market_data": {
                    "ltp": "N/A",
                    "bid_price": 100.0,
                    "ask_price": 101.0,
                    "oi": 5000,
                },
            },
        }
    ]
    with capture_logs() as log_entries:
        rows = filter_strikes_by_delta(chain, "PE", 0.20, 0.40)
    assert rows == []
    assert any("ltp_missing" in e.get("event", "") for e in log_entries)


def test_filter_prices_are_decimal() -> None:
    """Price fields in output rows must be Decimal, not float."""
    rows = filter_strikes_by_delta(_load_chain(), "PE", 0.20, 0.40)
    assert len(rows) > 0
    for r in rows:
        assert isinstance(r["ltp"], Decimal), f"ltp is {type(r['ltp'])}"
        assert isinstance(r["mid"], Decimal), f"mid is {type(r['mid'])}"
        assert isinstance(r["bid"], Decimal), f"bid is {type(r['bid'])}"
        assert isinstance(r["ask"], Decimal), f"ask is {type(r['ask'])}"


# ── _apply_liquidity_gate ─────────────────────────────────────────────────────


def test_apply_liquidity_gate_filters_wide_spread() -> None:
    # Spread is (2.0 - 1.0) / 1.5 = 0.66 (> 0.05) -> should filter out
    # Spread is (1.02 - 1.0) / 1.01 = 0.019 (< 0.05) -> should keep
    ranked = [
        {
            "bid": Decimal("1.0"),
            "ask": Decimal("2.0"),
            "mid": Decimal("1.5"),
            "oi": 100,
            "instrument_key": "K1",
        },
        {
            "bid": Decimal("1.0"),
            "ask": Decimal("1.02"),
            "mid": Decimal("1.01"),
            "oi": 500,
            "instrument_key": "K2",
        },
    ]
    filtered = _apply_liquidity_gate(ranked, gate_pct=0.05)
    assert len(filtered) == 1
    assert filtered[0]["instrument_key"] == "K2"


# ── rank_strikes ──────────────────────────────────────────────────────────────


def test_rank_strikes_empty_returns_empty() -> None:
    assert rank_strikes([]) == []


def test_rank_strikes_adds_rank_field_1_based() -> None:
    rows = filter_strikes_by_delta(_load_chain(), "PE", 0.20, 0.40)
    ranked = rank_strikes(rows)
    assert len(ranked) == len(rows)
    assert ranked[0]["rank"] == 1
    assert ranked[1]["rank"] == 2


def test_rank_strikes_prefers_round_100_strikes() -> None:
    rows = [
        {
            "strike": 22250.0,
            "bid": 100.0,
            "ask": 101.0,
            "oi": 1000,
            "instrument_key": "K1",
            "delta": -0.45,
        },
        {
            "strike": 22200.0,
            "bid": 100.0,
            "ask": 101.0,
            "oi": 500,
            "instrument_key": "K2",
            "delta": -0.40,
        },
    ]
    ranked = rank_strikes(rows)
    assert ranked[0]["strike"] == 22200.0
    assert ranked[1]["strike"] == 22250.0
