"""Unit tests for scripts/seed_mf_holdings.py.

All tests use a file-based SQLite DB under pytest's tmp_path.
No network, no live DB — fully offline.

Coverage:
- build_transactions: correct count, types, AMFI codes, amounts, date.
- seed_holdings: all 11 schemes inserted, units/amounts match spot-checks.
- seed_holdings: idempotent — running twice leaves exactly 11 rows.
- get_holdings round-trip: units and invested amounts survive the store cycle.
- AMFI codes: seeded codes match the verified set from nav_slice.txt.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.seed_mf_holdings import (
    ENTRY_DATE,
    _HOLDINGS,
    build_transactions,
    seed_holdings,
)
from src.mf.models import MFHolding, TransactionType
from src.mf.store import MFStore


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> MFStore:
    return MFStore(tmp_path / "test.sqlite")


# ── build_transactions ────────────────────────────────────────────


def test_build_transactions_count() -> None:
    """Exactly 11 transactions — one per scheme."""
    assert len(build_transactions()) == 11


def test_build_transactions_all_initial() -> None:
    """Every transaction must be type INITIAL."""
    for tx in build_transactions():
        assert tx.transaction_type == TransactionType.INITIAL


def test_build_transactions_entry_date_default() -> None:
    """Default entry date is 2026-04-01 (portfolio baseline)."""
    for tx in build_transactions():
        assert tx.transaction_date == ENTRY_DATE


def test_build_transactions_entry_date_override() -> None:
    """entry_date argument is forwarded to all transactions."""
    custom_date = date(2025, 1, 1)
    for tx in build_transactions(entry_date=custom_date):
        assert tx.transaction_date == custom_date


def test_build_transactions_amfi_codes_match_holdings_table() -> None:
    """AMFI codes in built transactions match the _HOLDINGS constant exactly."""
    expected_codes = {row[0] for row in _HOLDINGS}
    built_codes = {tx.amfi_code for tx in build_transactions()}
    assert built_codes == expected_codes


def test_build_transactions_amfi_codes_are_verified_set() -> None:
    """All 11 AMFI codes must be present — matches nav_slice.txt fixture."""
    # Codes verified against AMFI flat file and nav_slice.txt on 2026-04-01
    expected = {
        "104481",  # DSP Midcap Fund
        "146193",  # Edelweiss Small Cap Fund
        "101281",  # HDFC BSE Sensex Index Fund
        "102760",  # HDFC Focused Fund
        "112090",  # Kotak Flexicap Fund
        "142109",  # Mahindra Manulife Mid Cap Fund
        "122640",  # Parag Parikh Flexi Cap Fund
        "100177",  # Quant Small Cap Fund
        "101659",  # Tata Nifty 50 Index Fund
        "101672",  # Tata Value Fund
        "150799",  # WhiteOak Capital Large Cap Fund
    }
    assert {tx.amfi_code for tx in build_transactions()} == expected


def test_build_transactions_units_positive() -> None:
    """All unit values must be positive (Pydantic gt=0 enforced at model level)."""
    for tx in build_transactions():
        assert tx.units > 0


def test_build_transactions_amounts_positive() -> None:
    for tx in build_transactions():
        assert tx.amount > 0


# ── seed_holdings ────────────────────────────────────────────────


def test_seed_holdings_inserts_all_schemes(store: MFStore) -> None:
    """After seeding, all 11 schemes must appear in mf_transactions."""
    seed_holdings(store)
    txs = store.get_transactions()
    assert len(txs) == 11


def test_seed_holdings_returns_count(store: MFStore) -> None:
    """Return value is the number of transactions attempted (always 11)."""
    assert seed_holdings(store) == 11


def test_seed_holdings_idempotent(store: MFStore) -> None:
    """Running twice must not create duplicate rows — ON CONFLICT DO NOTHING."""
    seed_holdings(store)
    seed_holdings(store)
    assert len(store.get_transactions()) == 11


def test_seed_holdings_idempotent_three_runs(store: MFStore) -> None:
    """Idempotency holds for any number of re-runs."""
    for _ in range(3):
        seed_holdings(store)
    assert len(store.get_transactions()) == 11


# ── get_holdings round-trip ───────────────────────────────────────


def test_get_holdings_after_seed_count(store: MFStore) -> None:
    """All 11 schemes must appear in holdings after seed."""
    seed_holdings(store)
    holdings = store.get_holdings()
    assert len(holdings) == 11


def test_get_holdings_after_seed_returns_mfholding(store: MFStore) -> None:
    """Each value in get_holdings() must be an MFHolding instance."""
    seed_holdings(store)
    for h in store.get_holdings().values():
        assert isinstance(h, MFHolding)


def test_get_holdings_parag_parikh_units(store: MFStore) -> None:
    """Spot-check: Parag Parikh units must match the seeded value."""
    seed_holdings(store)
    holdings = store.get_holdings()
    h = holdings["122640"]
    assert h.total_units == Decimal("32424.322")
    assert h.scheme_name == "Parag Parikh Flexi Cap Fund - Regular Growth"


def test_get_holdings_parag_parikh_invested(store: MFStore) -> None:
    """Spot-check: Parag Parikh invested amount must match the seeded value."""
    seed_holdings(store)
    assert store.get_holdings()["122640"].total_invested == Decimal("1719925.75")


def test_get_holdings_whiteoak_units(store: MFStore) -> None:
    """Spot-check: WhiteOak units match (largest unit count in portfolio)."""
    seed_holdings(store)
    h = store.get_holdings()["150799"]
    assert h.total_units == Decimal("20681.514")
    assert h.total_invested == Decimal("299985.00")


def test_get_holdings_hdfc_sensex_precision(store: MFStore) -> None:
    """Decimal precision must survive the TEXT round-trip for fractional units."""
    seed_holdings(store)
    h = store.get_holdings()["101281"]
    assert h.total_units == Decimal("291.628")
    assert h.total_invested == Decimal("187371.53")


def test_get_holdings_total_invested_sum(store: MFStore) -> None:
    """Sum of all invested amounts must equal the known portfolio total."""
    seed_holdings(store)
    holdings = store.get_holdings()
    total = sum(h.total_invested for h in holdings.values())
    # Sum of all 11 invested amounts from _HOLDINGS
    expected = sum(Decimal(row[3]) for row in _HOLDINGS)
    assert total == expected


def test_get_holdings_amfi_codes_match_seed(store: MFStore) -> None:
    """Holdings keys must exactly match the seeded AMFI codes."""
    seed_holdings(store)
    seeded_codes = {row[0] for row in _HOLDINGS}
    assert set(store.get_holdings().keys()) == seeded_codes
