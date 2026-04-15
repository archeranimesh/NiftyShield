"""Tests for scripts/seed_nuvama_positions.py — build_positions and seed_positions."""

from decimal import Decimal

import pytest

from scripts.seed_nuvama_positions import build_positions, seed_positions


_KNOWN_ISINS = {
    "INE532F07FD3",  # EFSL 10% NCD 2034
    "INE532F07EC8",  # EFSL 9.20% NCD 2026
    "INE532F07DK3",  # EFSL 9.67% NCD 2028
    "INE532F07FN2",  # EFSL 9.67% NCD 2029
    "IN0020070069",  # G-Sec 8.28% 2027
    "IN0020230168",  # SGB 2031 2.50%
}


# ---------------------------------------------------------------------------
# build_positions — pure, no I/O
# ---------------------------------------------------------------------------


def test_build_positions_count():
    assert len(build_positions()) == 6


def test_build_positions_isins_match_known_set():
    isins = {p["isin"] for p in build_positions()}
    assert isins == _KNOWN_ISINS


def test_build_positions_all_have_required_keys():
    for p in build_positions():
        assert "isin" in p
        assert "avg_price" in p
        assert "qty" in p
        assert "label" in p


def test_build_positions_avg_prices_are_decimal():
    for p in build_positions():
        assert isinstance(p["avg_price"], Decimal)


def test_build_positions_qty_positive():
    for p in build_positions():
        assert p["qty"] > 0


def test_build_positions_avg_price_positive():
    for p in build_positions():
        assert p["avg_price"] > 0


def test_build_positions_gsec_avg_price():
    gsec = next(p for p in build_positions() if p["isin"] == "IN0020070069")
    assert gsec["avg_price"] == Decimal("109.00")
    assert gsec["qty"] == 2000


def test_build_positions_sgb_avg_price():
    sgb = next(p for p in build_positions() if p["isin"] == "IN0020230168")
    assert sgb["avg_price"] == Decimal("6199.00")
    assert sgb["qty"] == 50


def test_build_positions_efsl_ncd_2028_avg_price():
    """The 9.67% NCD 2028 has a non-round avg price."""
    ncd = next(p for p in build_positions() if p["isin"] == "INE532F07DK3")
    assert ncd["avg_price"] == Decimal("1001.06")


def test_build_positions_total_invested():
    total = sum(p["avg_price"] * p["qty"] for p in build_positions())
    # 700000 + 500000 + 1201272 + 700000 + 218000 + 309950 = 3629222
    assert total == Decimal("3629222.00")


# ---------------------------------------------------------------------------
# seed_positions — I/O, uses tmp_path DB
# ---------------------------------------------------------------------------


def test_seed_positions_returns_count(tmp_path):
    db = str(tmp_path / "test.sqlite")
    inserted = seed_positions(db)
    assert inserted == 6


def test_seed_positions_idempotent(tmp_path):
    db = str(tmp_path / "test.sqlite")
    seed_positions(db)
    inserted2 = seed_positions(db)
    assert inserted2 == 0  # INSERT OR IGNORE


def test_seed_positions_idempotent_three_runs(tmp_path):
    db = str(tmp_path / "test.sqlite")
    seed_positions(db)
    seed_positions(db)
    inserted3 = seed_positions(db)
    assert inserted3 == 0


def test_seed_positions_get_positions_after_seed(tmp_path):
    from src.nuvama.store import NuvamaStore

    db = str(tmp_path / "test.sqlite")
    seed_positions(db)
    store = NuvamaStore(db)
    pos = store.get_positions()
    assert set(pos.keys()) == _KNOWN_ISINS


def test_seed_positions_gsec_avg_price_persisted(tmp_path):
    from src.nuvama.store import NuvamaStore

    db = str(tmp_path / "test.sqlite")
    seed_positions(db)
    store = NuvamaStore(db)
    pos = store.get_positions()
    assert pos["IN0020070069"] == Decimal("109.00")


def test_seed_positions_decimal_precision_efsl_2028(tmp_path):
    from src.nuvama.store import NuvamaStore

    db = str(tmp_path / "test.sqlite")
    seed_positions(db)
    store = NuvamaStore(db)
    pos = store.get_positions()
    assert pos["INE532F07DK3"] == Decimal("1001.06")
