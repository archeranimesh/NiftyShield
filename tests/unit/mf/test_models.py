"""Unit tests for src/mf/models.py.

All tests are fully offline — no DB, no network.
Run with: pytest tests/unit/mf/test_models.py -v
"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.models.mf import MFNavSnapshot, MFTransaction, TransactionType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _transaction(**overrides) -> dict:
    """Return a valid MFTransaction payload, with optional field overrides."""
    base = {
        "scheme_name": "Parag Parikh Flexi Cap Fund - Reg Gr",
        "amfi_code": "122639",
        "transaction_date": date(2026, 4, 1),
        "units": Decimal("32424.322"),
        "amount": Decimal("1719925.75"),
        "transaction_type": TransactionType.INITIAL,
    }
    return {**base, **overrides}


def _nav_snapshot(**overrides) -> dict:
    """Return a valid MFNavSnapshot payload, with optional field overrides."""
    base = {
        "snapshot_date": date(2026, 4, 3),
        "amfi_code": "122639",
        "scheme_name": "Parag Parikh Flexi Cap Fund - Reg Gr",
        "nav": Decimal("83.45"),
    }
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# MFTransaction — valid construction
# ---------------------------------------------------------------------------

class TestMFTransactionValid:
    def test_initial_transaction(self):
        t = MFTransaction(**_transaction())
        assert t.scheme_name == "Parag Parikh Flexi Cap Fund - Reg Gr"
        assert t.amfi_code == "122639"
        assert t.units == Decimal("32424.322")
        assert t.amount == Decimal("1719925.75")
        assert t.transaction_type == TransactionType.INITIAL

    def test_sip_transaction(self):
        t = MFTransaction(**_transaction(transaction_type=TransactionType.SIP))
        assert t.transaction_type == TransactionType.SIP

    def test_redemption_transaction(self):
        t = MFTransaction(**_transaction(transaction_type=TransactionType.REDEMPTION))
        assert t.transaction_type == TransactionType.REDEMPTION

    def test_all_schemes_representative(self):
        """Spot-check that real scheme names and amounts from the portfolio parse cleanly."""
        cases = [
            ("DSP Midcap Fund - Reg Gr", "120505", "4020.602", "439978.00"),
            ("Edelweiss Small Cap Fund - Gr", "145552", "8962.544", "379981.00"),
            ("WhiteOak Capital Large Cap Fund - Gr", "150627", "20681.514", "299985.00"),
        ]
        for name, code, units, amount in cases:
            t = MFTransaction(**_transaction(
                scheme_name=name,
                amfi_code=code,
                units=Decimal(units),
                amount=Decimal(amount),
            ))
            assert t.amfi_code == code

    def test_frozen_model_rejects_mutation(self):
        t = MFTransaction(**_transaction())
        with pytest.raises(ValidationError):
            t.units = Decimal("999")


# ---------------------------------------------------------------------------
# MFTransaction — invalid construction
# ---------------------------------------------------------------------------

class TestMFTransactionInvalid:
    def test_empty_scheme_name_rejected(self):
        with pytest.raises(ValidationError):
            MFTransaction(**_transaction(scheme_name=""))

    def test_non_numeric_amfi_code_rejected(self):
        with pytest.raises(ValidationError):
            MFTransaction(**_transaction(amfi_code="ABC123"))

    def test_amfi_code_with_spaces_rejected(self):
        with pytest.raises(ValidationError):
            MFTransaction(**_transaction(amfi_code="122 639"))

    def test_zero_units_rejected(self):
        with pytest.raises(ValidationError):
            MFTransaction(**_transaction(units=Decimal("0")))

    def test_negative_units_rejected(self):
        with pytest.raises(ValidationError):
            MFTransaction(**_transaction(units=Decimal("-10.5")))

    def test_zero_amount_rejected(self):
        with pytest.raises(ValidationError):
            MFTransaction(**_transaction(amount=Decimal("0")))

    def test_negative_amount_rejected(self):
        with pytest.raises(ValidationError):
            MFTransaction(**_transaction(amount=Decimal("-1000")))

    def test_invalid_transaction_type_rejected(self):
        with pytest.raises(ValidationError):
            MFTransaction(**_transaction(transaction_type="DIVIDEND"))

    def test_missing_required_field_rejected(self):
        payload = _transaction()
        del payload["amfi_code"]
        with pytest.raises(ValidationError):
            MFTransaction(**payload)


# ---------------------------------------------------------------------------
# MFNavSnapshot — valid construction
# ---------------------------------------------------------------------------

class TestMFNavSnapshotValid:
    def test_basic_snapshot(self):
        s = MFNavSnapshot(**_nav_snapshot())
        assert s.nav == Decimal("83.45")
        assert s.snapshot_date == date(2026, 4, 3)

    def test_nav_with_many_decimal_places(self):
        s = MFNavSnapshot(**_nav_snapshot(nav=Decimal("1234.5678")))
        assert s.nav == Decimal("1234.5678")

    def test_frozen_model_rejects_mutation(self):
        s = MFNavSnapshot(**_nav_snapshot())
        with pytest.raises(ValidationError):
            s.nav = Decimal("100")


# ---------------------------------------------------------------------------
# MFNavSnapshot — invalid construction
# ---------------------------------------------------------------------------

class TestMFNavSnapshotInvalid:
    def test_zero_nav_rejected(self):
        with pytest.raises(ValidationError):
            MFNavSnapshot(**_nav_snapshot(nav=Decimal("0")))

    def test_negative_nav_rejected(self):
        with pytest.raises(ValidationError):
            MFNavSnapshot(**_nav_snapshot(nav=Decimal("-5.0")))

    def test_non_finite_nav_rejected(self):
        with pytest.raises(ValidationError):
            MFNavSnapshot(**_nav_snapshot(nav=Decimal("Infinity")))

    def test_non_numeric_amfi_code_rejected(self):
        with pytest.raises(ValidationError):
            MFNavSnapshot(**_nav_snapshot(amfi_code="PPFAS"))

    def test_empty_scheme_name_rejected(self):
        with pytest.raises(ValidationError):
            MFNavSnapshot(**_nav_snapshot(scheme_name=""))

    def test_missing_nav_rejected(self):
        payload = _nav_snapshot()
        del payload["nav"]
        with pytest.raises(ValidationError):
            MFNavSnapshot(**payload)


# ---------------------------------------------------------------------------
# TransactionType enum
# ---------------------------------------------------------------------------

class TestTransactionType:
    def test_string_values(self):
        assert TransactionType.INITIAL == "INITIAL"
        assert TransactionType.SIP == "SIP"
        assert TransactionType.REDEMPTION == "REDEMPTION"

    def test_coercion_from_string(self):
        t = MFTransaction(**_transaction(transaction_type="SIP"))
        assert t.transaction_type == TransactionType.SIP
