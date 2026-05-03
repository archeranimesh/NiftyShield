"""Tests for paper_3track_entry — load_config, build_trades, resolve_proxy_key."""

import textwrap
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from scripts.paper_3track_entry import (
    EntryConfig,
    build_trades,
    compute_niftybees_qty,
    load_config,
    resolve_proxy_key,
)
from src.models.portfolio import TradeAction


# ── helpers ────────────────────────────────────────────────────────────────────

def _write_yaml(tmp_path: Path, data: dict) -> Path:
    """Write a YAML config dict to a temp file and return its path."""
    p = tmp_path / "entry.yaml"
    p.write_text(yaml.dump(data))
    return p


def _valid_raw() -> dict:
    """Return a minimal valid raw config dict."""
    return {
        "entry": {
            "date": "2026-05-07",
            "lot_size": 65,
            "nifty_spot": 24000.0,
            "cycle": 1,
        },
        "spot": {"niftybees_ltp": 265.50},
        "futures": {
            "instrument_key": "NSE_FO|NIFTY29MAY2026FUT",
            "price": 24150.0,
        },
        "proxy": {
            "strike": 21000,
            "expiry": "2026-05-29",
            "price": 3200.0,
            "actual_delta": 0.91,
        },
    }


class MockInstrumentLookup:
    """Minimal stand-in for InstrumentLookup."""

    def __init__(self, results: list[dict]):
        self._results = results

    def search_options(self, **kwargs) -> list[dict]:
        return self._results


# ── load_config ────────────────────────────────────────────────────────────────

def test_load_config_happy_path(tmp_path):
    path = _write_yaml(tmp_path, _valid_raw())
    cfg = load_config(path)

    assert cfg.entry_date == date(2026, 5, 7)
    assert cfg.lot_size == 65
    assert cfg.nifty_spot == Decimal("24000.0")
    assert cfg.cycle == 1
    assert cfg.niftybees_ltp == Decimal("265.5")
    assert cfg.futures_key == "NSE_FO|NIFTY29MAY2026FUT"
    assert cfg.futures_price == Decimal("24150.0")
    assert cfg.proxy_strike == 21000.0
    assert cfg.proxy_expiry == "2026-05-29"
    assert cfg.proxy_price == Decimal("3200.0")
    assert cfg.proxy_actual_delta == Decimal("0.91")


def test_load_config_placeholder_date_raises(tmp_path):
    raw = _valid_raw()
    raw["entry"]["date"] = "YYYY-MM-DD"
    path = _write_yaml(tmp_path, raw)
    with pytest.raises(ValueError, match="placeholder"):
        load_config(path)


def test_load_config_placeholder_expiry_raises(tmp_path):
    raw = _valid_raw()
    raw["proxy"]["expiry"] = "YYYY-MM-DD"
    path = _write_yaml(tmp_path, raw)
    with pytest.raises(ValueError, match="placeholder"):
        load_config(path)


def test_load_config_missing_field_raises(tmp_path):
    raw = _valid_raw()
    del raw["futures"]["price"]
    path = _write_yaml(tmp_path, raw)
    with pytest.raises(ValueError, match=r"\[futures\]\.price"):
        load_config(path)


def test_load_config_delta_below_085_raises(tmp_path):
    raw = _valid_raw()
    raw["proxy"]["actual_delta"] = 0.80
    path = _write_yaml(tmp_path, raw)
    with pytest.raises(ValueError, match="0.85"):
        load_config(path)


def test_load_config_bad_futures_key_raises(tmp_path):
    raw = _valid_raw()
    raw["futures"]["instrument_key"] = "WRONG|KEY"
    path = _write_yaml(tmp_path, raw)
    with pytest.raises(ValueError, match="NSE_FO"):
        load_config(path)


def test_load_config_zero_spot_raises(tmp_path):
    raw = _valid_raw()
    raw["entry"]["nifty_spot"] = 0.0
    path = _write_yaml(tmp_path, raw)
    with pytest.raises(ValueError, match="nifty_spot"):
        load_config(path)


# ── compute_niftybees_qty ──────────────────────────────────────────────────────

def test_compute_niftybees_qty_floors_correctly():
    # floor((65 × 24000) / 265.50) = floor(5875.70…) = 5875
    assert compute_niftybees_qty(Decimal("24000"), 65, Decimal("265.50")) == 5875


def test_compute_niftybees_qty_exact_division():
    # floor((10 × 100) / 50) = 20
    assert compute_niftybees_qty(Decimal("100"), 10, Decimal("50")) == 20


# ── resolve_proxy_key ──────────────────────────────────────────────────────────

def test_resolve_proxy_key_returns_key():
    lookup = MockInstrumentLookup([{"instrument_key": "NSE_FO|99999"}])
    key = resolve_proxy_key(lookup, strike=21000.0, expiry="2026-05-29")
    assert key == "NSE_FO|99999"


def test_resolve_proxy_key_no_results_raises():
    lookup = MockInstrumentLookup([])
    with pytest.raises(ValueError, match="No CE instrument found"):
        resolve_proxy_key(lookup, strike=21000.0, expiry="2026-05-29")


def test_resolve_proxy_key_missing_key_field_raises():
    lookup = MockInstrumentLookup([{"strike_price": 21000}])  # no instrument_key
    with pytest.raises(ValueError, match="no instrument_key"):
        resolve_proxy_key(lookup, strike=21000.0, expiry="2026-05-29")


# ── build_trades ───────────────────────────────────────────────────────────────

def _make_cfg(**overrides) -> EntryConfig:
    base = dict(
        entry_date=date(2026, 5, 7),
        lot_size=65,
        nifty_spot=Decimal("24000"),
        cycle=1,
        niftybees_ltp=Decimal("265.50"),
        futures_key="NSE_FO|NIFTY29MAY2026FUT",
        futures_price=Decimal("24150"),
        proxy_strike=21000.0,
        proxy_expiry="2026-05-29",
        proxy_price=Decimal("3200"),
        proxy_actual_delta=Decimal("0.91"),
    )
    base.update(overrides)
    return EntryConfig(**base)


def test_build_trades_returns_three_legs():
    cfg = _make_cfg()
    trades = build_trades(cfg, proxy_key="NSE_FO|99999", niftybees_qty=5877)
    assert len(trades) == 3


def test_build_trades_strategy_names():
    cfg = _make_cfg()
    trades = build_trades(cfg, proxy_key="NSE_FO|99999", niftybees_qty=5877)
    strategies = {t.strategy_name for t in trades}
    assert strategies == {"paper_nifty_spot", "paper_nifty_futures", "paper_nifty_proxy"}


def test_build_trades_leg_roles():
    cfg = _make_cfg()
    trades = build_trades(cfg, proxy_key="NSE_FO|99999", niftybees_qty=5877)
    roles = {t.leg_role for t in trades}
    assert roles == {"base_etf", "base_futures", "base_ditm_call"}


def test_build_trades_all_buy_actions():
    cfg = _make_cfg()
    trades = build_trades(cfg, proxy_key="NSE_FO|99999", niftybees_qty=5877)
    assert all(t.action == TradeAction.BUY for t in trades)


def test_build_trades_spot_qty_matches_computed():
    cfg = _make_cfg()
    trades = build_trades(cfg, proxy_key="NSE_FO|99999", niftybees_qty=5877)
    spot = next(t for t in trades if t.leg_role == "base_etf")
    assert spot.quantity == 5877


def test_build_trades_futures_proxy_qty_is_lot_size():
    cfg = _make_cfg()
    trades = build_trades(cfg, proxy_key="NSE_FO|99999", niftybees_qty=5877)
    for role in ("base_futures", "base_ditm_call"):
        t = next(t for t in trades if t.leg_role == role)
        assert t.quantity == 65


def test_build_trades_notes_contain_cycle_tag():
    cfg = _make_cfg(cycle=3)
    trades = build_trades(cfg, proxy_key="NSE_FO|99999", niftybees_qty=5877)
    assert all("Cycle 3" in t.notes for t in trades)


def test_build_trades_proxy_key_recorded():
    cfg = _make_cfg()
    trades = build_trades(cfg, proxy_key="NSE_FO|99999", niftybees_qty=5877)
    proxy = next(t for t in trades if t.leg_role == "base_ditm_call")
    assert proxy.instrument_key == "NSE_FO|99999"
