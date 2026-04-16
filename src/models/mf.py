"""Shared data models for the mutual fund tracking domain.

Canonical home for all MF domain types. Modules in src/mf/ import from here.

Two Pydantic models:
- MFTransaction: a single purchase/SIP installment/redemption event.
- MFNavSnapshot: the NAV recorded for a scheme on a given date.

One computed dataclass:
- MFHolding: net holding derived from the transaction ledger at query time.

Current holdings and P&L are derived at query time from these records —
nothing is pre-computed or stored redundantly.
"""

from dataclasses import dataclass
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


@dataclass(frozen=True)
class MFHolding:
    """Net holding for a single scheme, derived from the transaction ledger.

    Returned by MFStore.get_holdings(). Units and invested amount are already
    aggregated (INITIAL/SIP add, REDEMPTION subtracts). scheme_name is carried
    through so MFTracker can populate MFNavSnapshot without a separate lookup.

    This is a computed type — not persisted. It lives here (rather than
    tracker.py) to break the circular import: store returns it, tracker
    consumes it, both import from models.
    """

    amfi_code: str
    scheme_name: str
    total_units: Decimal
    total_invested: Decimal
