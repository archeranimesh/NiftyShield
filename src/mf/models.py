"""Pydantic models for the mutual fund tracking domain.

Two models:
- MFTransaction: a single purchase/SIP installment/redemption event.
- MFNavSnapshot: the NAV recorded for a scheme on a given date.

Current holdings and P&L are derived at query time from these records —
nothing is pre-computed or stored redundantly.
"""

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class TransactionType(str, Enum):
    """Classification for entries in mf_transactions."""

    INITIAL = "INITIAL"      # Lump-sum entry at the start of tracking
    SIP = "SIP"              # Monthly systematic instalment
    REDEMPTION = "REDEMPTION"  # Partial or full exit


class MFTransaction(BaseModel):
    """A single mutual fund transaction — one row in mf_transactions.

    Attributes:
        scheme_name: Human-readable fund name (e.g. 'Parag Parikh Flexi Cap Fund - Reg Gr').
        amfi_code: Numeric AMFI scheme code (e.g. '122639'). Used as the stable join key.
        transaction_date: Date on which units were allotted.
        units: Units purchased or redeemed. Always positive; direction is in transaction_type.
        amount: Rupee value of this transaction. Always positive.
        transaction_type: INITIAL | SIP | REDEMPTION.
    """

    scheme_name: str = Field(..., min_length=1)
    amfi_code: str = Field(..., pattern=r"^\d+$")
    transaction_date: date
    units: Decimal = Field(..., gt=0)
    amount: Decimal = Field(..., gt=0)
    transaction_type: TransactionType

    model_config = {"frozen": True}


class MFNavSnapshot(BaseModel):
    """NAV recorded for a scheme on a single date — one row in mf_nav_snapshots.

    Attributes:
        snapshot_date: The business date this NAV applies to.
        amfi_code: AMFI scheme code — foreign key to mf_transactions.
        scheme_name: Denormalised for readability in queries and reports.
        nav: Net Asset Value per unit on snapshot_date.
    """

    snapshot_date: date
    amfi_code: str = Field(..., pattern=r"^\d+$")
    scheme_name: str = Field(..., min_length=1)
    nav: Decimal = Field(..., gt=0)

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def nav_is_finite(self) -> "MFNavSnapshot":
        """Guard against non-finite values slipping through as Decimal."""
        if not self.nav.is_finite():
            raise ValueError(f"nav must be a finite number, got {self.nav}")
        return self
