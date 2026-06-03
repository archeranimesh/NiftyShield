"""Unit tests for the liquidity gate and fallback logic in find_strike_by_delta.py."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.lookup.find_strike_by_delta import _apply_liquidity_gate, main


def test_apply_liquidity_gate_empty() -> None:
    assert _apply_liquidity_gate([]) == []


def test_apply_liquidity_gate_filtering() -> None:
    # 5% of mid is the threshold: spread / mid <= 0.05
    rows = [
        # mid = 100, spread = 4, spread_pct = 4% (passes)
        {"strike": 22000.0, "bid": 98.0, "ask": 102.0, "mid": 100.0},
        # mid = 100, spread = 6, spread_pct = 6% (fails)
        {"strike": 22100.0, "bid": 97.0, "ask": 103.0, "mid": 100.0},
        # mid = 50, spread = 2.5, spread_pct = 5% (passes)
        {"strike": 22200.0, "bid": 48.75, "ask": 51.25, "mid": 50.0},
        # mid = 0 (fails)
        {"strike": 22300.0, "bid": 0.0, "ask": 0.0, "mid": 0.0},
        # mid = 50, but bid/ask are 0 (fails) — liquidity ghost
        {"strike": 22400.0, "bid": 0.0, "ask": 0.0, "mid": 50.0},
    ]
    filtered = _apply_liquidity_gate(rows)
    assert len(filtered) == 2
    assert filtered[0]["strike"] == 22000.0
    assert filtered[1]["strike"] == 22200.0


def make_mock_chain(strikes_config: list[dict]) -> list[dict]:
    """Helper to generate a mock option chain based on delta and bid/ask spreads."""
    chain = []
    for cfg in strikes_config:
        delta = cfg["delta"]
        bid = cfg["bid"]
        ask = cfg["ask"]
        mid = (bid + ask) / 2.0
        chain.append(
            {
                "strike_price": cfg["strike"],
                "underlying_spot_price": 22000.0,
                "put_options": {
                    "instrument_key": f"NSE_FO|PUT_{cfg['strike']}",
                    "option_greeks": {"delta": delta, "iv": 15.0},
                    "market_data": {
                        "ltp": mid,
                        "bid_price": bid,
                        "ask_price": ask,
                        "oi": cfg.get("oi", 1000),
                    },
                },
            }
        )
    return chain


def test_main_selection_primary_passes(capsys) -> None:
    # 0.22 delta passes liquidity (spread 4 / mid 100 = 4% <= 5%)
    mock_data = make_mock_chain(
        [
            {"strike": 21800, "delta": -0.22, "bid": 98.0, "ask": 102.0},
            {"strike": 21700, "delta": -0.25, "bid": 98.0, "ask": 102.0},
            {"strike": 21900, "delta": -0.20, "bid": 98.0, "ask": 102.0},
        ]
    )

    argv = [
        "scripts/lookup/find_strike_by_delta.py",
        "--expiry",
        "2026-06-30",
        "--no-dry-run",
    ]

    with (
        patch("sys.argv", argv),
        patch("scripts.lookup.find_strike_by_delta.UpstoxMarketClient") as mock_client_cls,
    ):
        mock_client = mock_client_cls.return_value
        mock_client.get_option_chain_sync.return_value = mock_data

        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert "WARNING: Fallback used" not in captured.err
    assert "GATE FAIL" not in captured.err
    # Selected key should be the primary candidate (21800)
    assert "NSE_FO|PUT_21800" in captured.out


def test_main_selection_fallback_used(capsys) -> None:
    # 0.22 delta fails liquidity (spread 10 / mid 100 = 10%)
    # 0.25 delta passes (spread 2 / mid 100 = 2%)
    mock_data = make_mock_chain(
        [
            {"strike": 21800, "delta": -0.22, "bid": 95.0, "ask": 105.0},
            {"strike": 21700, "delta": -0.25, "bid": 99.0, "ask": 101.0},
            {"strike": 21900, "delta": -0.20, "bid": 95.0, "ask": 105.0},
        ]
    )

    argv = [
        "scripts/lookup/find_strike_by_delta.py",
        "--expiry",
        "2026-06-30",
        "--no-dry-run",
    ]

    with (
        patch("sys.argv", argv),
        patch("scripts.lookup.find_strike_by_delta.UpstoxMarketClient") as mock_client_cls,
    ):
        mock_client = mock_client_cls.return_value
        mock_client.get_option_chain_sync.return_value = mock_data

        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    # Warning about fallback should be printed to stderr
    assert "WARNING: Fallback used" in captured.err
    assert "Selected delta 0.2500 vs requested delta 0.2200" in captured.err
    # Selected key should be the fallback (21700)
    assert "NSE_FO|PUT_21700" in captured.out


def test_main_selection_all_fail(capsys) -> None:
    # All candidates fail liquidity
    mock_data = make_mock_chain(
        [
            {"strike": 21800, "delta": -0.22, "bid": 90.0, "ask": 110.0},
            {"strike": 21700, "delta": -0.25, "bid": 90.0, "ask": 110.0},
            {"strike": 21900, "delta": -0.20, "bid": 90.0, "ask": 110.0},
        ]
    )

    argv = [
        "scripts/lookup/find_strike_by_delta.py",
        "--expiry",
        "2026-06-30",
        "--no-dry-run",
    ]

    with (
        patch("sys.argv", argv),
        patch("scripts.lookup.find_strike_by_delta.UpstoxMarketClient") as mock_client_cls,
    ):
        mock_client = mock_client_cls.return_value
        mock_client.get_option_chain_sync.return_value = mock_data

        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert "ERROR: GATE FAIL" in captured.err
