"""Tests for paper_3track_overlay_entry and find_overlay_strikes pure functions."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from scripts.paper_3track_overlay_entry import (
    OverlayConfig,
    build_overlay_trades,
    load_overlay_config,
)
from scripts.find_overlay_strikes import (
    compute_target_strike,
    find_chain_entry,
    evaluate_expiry,
)
from src.models.portfolio import TradeAction


# ── helpers ────────────────────────────────────────────────────────────────────

def _write_yaml(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "overlay_entry.yaml"
    p.write_text(yaml.dump(data))
    return p


def _valid_pp_raw() -> dict:
    return {
        "overlay": {
            "type": "pp",
            "date": "2026-05-07",
            "cycle": 1,
            "lot_size": 65,
            "expiry": "2026-06-26",
            "expiry_type": "quarterly",
            "dte_at_entry": 50,
            "put_strike": 21800.0,
            "put_instrument_key": "NSE_FO|NIFTY21800PE26JUN2026",
            "put_price": 285.50,
            "put_spread_pct": 1.8,
            "put_oi": 12500,
            "call_strike": 0,
            "call_instrument_key": "",
            "call_price": 0.0,
            "call_spread_pct": None,
            "call_oi": 0,
        }
    }


def _valid_cc_raw() -> dict:
    raw = _valid_pp_raw()
    raw["overlay"]["type"] = "cc"
    raw["overlay"]["call_strike"] = 25000.0
    raw["overlay"]["call_instrument_key"] = "NSE_FO|NIFTY25000CE26JUN2026"
    raw["overlay"]["call_price"] = 210.00
    raw["overlay"]["call_spread_pct"] = 2.1
    raw["overlay"]["call_oi"] = 8900
    return raw


def _valid_collar_raw() -> dict:
    raw = _valid_cc_raw()
    raw["overlay"]["type"] = "collar"
    raw["overlay"]["put_strike"] = 21800.0
    raw["overlay"]["put_instrument_key"] = "NSE_FO|NIFTY21800PE26JUN2026"
    raw["overlay"]["put_price"] = 285.50
    raw["overlay"]["put_spread_pct"] = 1.8
    raw["overlay"]["put_oi"] = 12500
    return raw


def _make_overlay_config(**overrides) -> OverlayConfig:
    base = dict(
        overlay_type="pp",
        entry_date=date(2026, 5, 7),
        cycle=1,
        lot_size=65,
        expiry="2026-06-26",
        expiry_type="quarterly",
        dte_at_entry=50,
        put_strike=21800.0,
        put_instrument_key="NSE_FO|NIFTY21800PE26JUN2026",
        put_price=Decimal("285.50"),
        put_spread_pct=1.8,
        put_oi=12500,
        call_strike=25000.0,
        call_instrument_key="NSE_FO|NIFTY25000CE26JUN2026",
        call_price=Decimal("210.00"),
        call_spread_pct=2.1,
        call_oi=8900,
    )
    base.update(overrides)
    return OverlayConfig(**base)


# ── compute_target_strike ──────────────────────────────────────────────────────

def test_compute_target_strike_put_rounds_to_nearest_50():
    # 24000 × (1 - 0.09) = 21840 → nearest 50 = 21850
    result = compute_target_strike(24000.0, 9.0, "PE")
    assert result == 21850.0


def test_compute_target_strike_call_rounds_to_nearest_50():
    # 24000 × (1 + 0.04) = 24960 → nearest 50 = 24950
    result = compute_target_strike(24000.0, 4.0, "CE")
    assert result == 24950.0


def test_compute_target_strike_put_exact():
    # 20000 × 0.90 = 18000 → exactly 18000
    result = compute_target_strike(20000.0, 10.0, "PE")
    assert result == 18000.0


# ── find_chain_entry ──────────────────────────────────────────────────────────

def _make_chain(strike: float, side: str, bid: float, ask: float, oi: int = 1000) -> list[dict]:
    raw_key = "call_options" if side == "CE" else "put_options"
    return [{
        "strike_price": strike,
        raw_key: {
            "instrument_key": f"NSE_FO|TEST{strike:.0f}{side}",
            "market_data": {"ltp": (bid + ask) / 2, "bid_price": bid, "ask_price": ask, "oi": oi},
            "option_greeks": {"delta": 0.3, "iv": 15.0},
        }
    }]


def test_find_chain_entry_returns_closest_strike():
    chain = (
        _make_chain(21800.0, "PE", 280.0, 290.0) +
        _make_chain(22000.0, "PE", 200.0, 210.0)
    )
    result = find_chain_entry(chain, "PE", 21850.0)  # closer to 21800
    assert result is not None
    assert result["strike"] == 21800.0
    assert result["instrument_key"] == "NSE_FO|TEST21800PE"


def test_find_chain_entry_computes_spread_pct():
    chain = _make_chain(21800.0, "PE", 285.0, 290.0)  # spread=5, mid=287.5
    result = find_chain_entry(chain, "PE", 21800.0)
    assert result is not None
    expected_spread = round(5.0 / 287.5 * 100, 2)
    assert result["spread_pct"] == pytest.approx(expected_spread, rel=1e-3)


def test_find_chain_entry_no_instrument_key_skipped():
    chain = [{"strike_price": 21800.0, "put_options": {"market_data": {}, "option_greeks": {}}}]
    result = find_chain_entry(chain, "PE", 21800.0)
    assert result is None


def test_find_chain_entry_computes_mid():
    chain = _make_chain(25000.0, "CE", 200.0, 220.0)
    result = find_chain_entry(chain, "CE", 25000.0)
    assert result["mid"] == pytest.approx(210.0)


# ── evaluate_expiry ───────────────────────────────────────────────────────────

def test_evaluate_expiry_passes_gate():
    chain = _make_chain(21800.0, "PE", 285.0, 287.0)  # spread~0.7% → passes
    ev = evaluate_expiry(chain, "2026-06-26", "pp", 21800.0, 25000.0, date(2026, 5, 7))
    assert ev.passes_gate is True
    assert ev.dte == (date(2026, 6, 26) - date(2026, 5, 7)).days


def test_evaluate_expiry_fails_gate():
    chain = _make_chain(21800.0, "PE", 270.0, 300.0)  # spread~10.5% → fails
    ev = evaluate_expiry(chain, "2026-05-29", "pp", 21800.0, 25000.0, date(2026, 5, 7))
    assert ev.passes_gate is False


def test_evaluate_expiry_collar_uses_max_spread():
    # Put spread=1%, Call spread=4% → max=4% → fails gate
    put_chain = _make_chain(21800.0, "PE", 286.0, 289.0)   # spread~1%
    call_chain = _make_chain(25000.0, "CE", 200.0, 209.0)  # spread~4.4%
    chain = put_chain + call_chain
    ev = evaluate_expiry(chain, "2026-06-26", "collar", 21800.0, 25000.0, date(2026, 5, 7))
    assert ev.passes_gate is False
    assert ev.gate_spread == pytest.approx(max(ev.put["spread_pct"], ev.call["spread_pct"]))


def test_evaluate_expiry_collar_passes_when_both_legs_tight():
    put_chain = _make_chain(21800.0, "PE", 286.0, 289.0)   # spread~1%
    call_chain = _make_chain(25000.0, "CE", 205.0, 208.0)  # spread~1.5%
    chain = put_chain + call_chain
    ev = evaluate_expiry(chain, "2026-06-26", "collar", 21800.0, 25000.0, date(2026, 5, 7))
    assert ev.passes_gate is True


# ── load_overlay_config ───────────────────────────────────────────────────────

def test_load_overlay_config_pp_happy_path(tmp_path):
    path = _write_yaml(tmp_path, _valid_pp_raw())
    cfg = load_overlay_config(path)
    assert cfg.overlay_type == "pp"
    assert cfg.entry_date == date(2026, 5, 7)
    assert cfg.put_price == Decimal("285.5")
    assert cfg.put_instrument_key == "NSE_FO|NIFTY21800PE26JUN2026"
    assert cfg.cycle == 1


def test_load_overlay_config_collar_happy_path(tmp_path):
    path = _write_yaml(tmp_path, _valid_collar_raw())
    cfg = load_overlay_config(path)
    assert cfg.overlay_type == "collar"
    assert cfg.call_price == Decimal("210.0")
    assert cfg.call_instrument_key == "NSE_FO|NIFTY25000CE26JUN2026"


def test_load_overlay_config_invalid_type_raises(tmp_path):
    raw = _valid_pp_raw()
    raw["overlay"]["type"] = "straddle"
    path = _write_yaml(tmp_path, raw)
    with pytest.raises(ValueError, match="pp.*cc.*collar"):
        load_overlay_config(path)


def test_load_overlay_config_pp_zero_put_price_raises(tmp_path):
    raw = _valid_pp_raw()
    raw["overlay"]["put_price"] = 0.0
    path = _write_yaml(tmp_path, raw)
    with pytest.raises(ValueError, match="put_price"):
        load_overlay_config(path)


def test_load_overlay_config_cc_bad_call_key_raises(tmp_path):
    raw = _valid_cc_raw()
    raw["overlay"]["call_instrument_key"] = "INVALID|KEY"
    path = _write_yaml(tmp_path, raw)
    with pytest.raises(ValueError, match="NSE_FO"):
        load_overlay_config(path)


# ── build_overlay_trades ──────────────────────────────────────────────────────

def test_build_overlay_trades_pp_records_all_three_tracks():
    cfg = _make_overlay_config(overlay_type="pp")
    trades, warnings = build_overlay_trades(cfg)
    strategies = {ot.strategy for ot in trades}
    assert strategies == {"paper_nifty_spot", "paper_nifty_futures", "paper_nifty_proxy"}
    assert len(warnings) == 0


def test_build_overlay_trades_pp_all_buy():
    cfg = _make_overlay_config(overlay_type="pp")
    trades, _ = build_overlay_trades(cfg)
    assert all(ot.trade.action == TradeAction.BUY for ot in trades)


def test_build_overlay_trades_pp_leg_role():
    cfg = _make_overlay_config(overlay_type="pp")
    trades, _ = build_overlay_trades(cfg)
    assert all(ot.leg_role == "overlay_pp" for ot in trades)


def test_build_overlay_trades_cc_blocks_futures():
    cfg = _make_overlay_config(overlay_type="cc")
    trades, warnings = build_overlay_trades(cfg)
    strategies = {ot.strategy for ot in trades}
    # Futures must be absent
    assert "paper_nifty_futures" not in strategies
    assert "paper_nifty_spot" in strategies
    assert "paper_nifty_proxy" in strategies
    assert len(warnings) == 1
    assert "BLOCKED" in warnings[0]


def test_build_overlay_trades_cc_is_sell():
    cfg = _make_overlay_config(overlay_type="cc")
    trades, _ = build_overlay_trades(cfg)
    assert all(ot.trade.action == TradeAction.SELL for ot in trades)


def test_build_overlay_trades_collar_records_six_legs():
    cfg = _make_overlay_config(overlay_type="collar")
    trades, warnings = build_overlay_trades(cfg)
    # 3 tracks × 2 legs (put + call) = 6
    assert len(trades) == 6
    assert len(warnings) == 0


def test_build_overlay_trades_collar_includes_futures():
    cfg = _make_overlay_config(overlay_type="collar")
    trades, _ = build_overlay_trades(cfg)
    strategies = {ot.strategy for ot in trades}
    assert "paper_nifty_futures" in strategies


def test_build_overlay_trades_collar_leg_roles():
    cfg = _make_overlay_config(overlay_type="collar")
    trades, _ = build_overlay_trades(cfg)
    roles = {ot.leg_role for ot in trades}
    assert roles == {"overlay_collar_put", "overlay_collar_call"}


def test_build_overlay_trades_collar_put_is_buy_call_is_sell():
    cfg = _make_overlay_config(overlay_type="collar")
    trades, _ = build_overlay_trades(cfg)
    for ot in trades:
        if ot.leg_role == "overlay_collar_put":
            assert ot.trade.action == TradeAction.BUY
        elif ot.leg_role == "overlay_collar_call":
            assert ot.trade.action == TradeAction.SELL


def test_build_overlay_trades_notes_contain_cycle_and_expiry():
    cfg = _make_overlay_config(overlay_type="pp", cycle=2, expiry="2026-09-25")
    trades, _ = build_overlay_trades(cfg)
    for ot in trades:
        assert "Cycle 2" in ot.trade.notes
        assert "2026-09-25" in ot.trade.notes
