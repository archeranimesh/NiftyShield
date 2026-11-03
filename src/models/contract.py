"""Broker-neutral contract identity and the chain-snapshot seam.

No concrete broker is imported here: a broker is a ``SourceId`` member plus a
master registered elsewhere, so adding one never edits these types.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Literal, Protocol

from pydantic import BaseModel, field_validator

from src.models.options import OptionChain, OptionLeg


class SourceId(str, Enum):
    """The one vocabulary for market-data sources.

    Values are the strings persisted in ``delta_source`` / ``chain_source``
    TEXT columns and used in routing config.
    """

    UPSTOX = "upstox"
    DHAN = "dhan"


class ContractRef(BaseModel, frozen=True):
    """Broker-neutral identity of one option contract.

    Attributes:
        underlying: Normalised underlying name, e.g. ``"NIFTY"``.
        expiry: Option expiry date.
        strike: Strike price (Decimal; ``24000`` and ``24000.0`` are equal).
        side: ``"CE"`` or ``"PE"``.
    """

    underlying: str
    expiry: date
    strike: Decimal
    side: Literal["CE", "PE"]


class ChainSnapshot(BaseModel, frozen=True):
    """An option chain tagged with provenance and ledger instrument keys.

    Attributes:
        chain: The canonical option chain.
        greeks_source: Source that supplied the Greeks.
        fetched_at: UTC-aware fetch time.
        instrument_keys: Contract to **Upstox ledger key**, whichever source
            supplied the Greeks (the name is fixed by the council ruling).
            Never put another broker's native keys here. A partial map is
            legal: a strike one broker does not list has no entry.
    """

    chain: OptionChain
    greeks_source: SourceId
    fetched_at: datetime
    instrument_keys: Mapping[ContractRef, str]

    @field_validator("fetched_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("fetched_at must be timezone-aware UTC")
        return value


class ContractResolver(Protocol):
    """Maps canonical contracts to a source's native key and back."""

    def to_native(self, ref: ContractRef, source: SourceId) -> str | None:
        """Return the native key for ``ref`` at ``source``, or None if unlisted."""
        ...

    def from_native(self, source: SourceId, native_key: str) -> ContractRef | None:
        """Return the contract for a native key, or None if unknown."""
        ...


def _leg_for(chain: OptionChain, ref: ContractRef) -> OptionLeg | None:
    if ref.expiry != chain.expiry or ref.strike not in chain.strikes:
        return None
    strike = chain.strikes[ref.strike]
    return strike.ce if ref.side == "CE" else strike.pe


def _has_delta(leg: OptionLeg | None) -> bool:
    return leg is not None and leg.delta is not None and leg.delta != Decimal("0")


def has_usable_delta(chain: OptionChain, refs: Collection[ContractRef] | None = None) -> bool:
    """Whether the chain carries non-zero deltas.

    Args:
        chain: Chain to inspect.
        refs: If given, only these held contracts count; a ref missing from
            the chain, or with a None or zero delta, is not usable. If None,
            any non-zero delta anywhere in the chain counts.

    Returns:
        True if at least one inspected leg has a non-zero delta (an empty
        chain or empty ``refs`` is False).
    """
    if refs is not None:
        return any(_has_delta(_leg_for(chain, r)) for r in refs)
    return any(
        _has_delta(leg) for strike in chain.strikes.values() for leg in (strike.ce, strike.pe)
    )
