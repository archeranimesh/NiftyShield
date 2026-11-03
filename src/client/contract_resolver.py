"""Contract resolver over the Upstox BOD and the Dhan instrument master.

One ``ContractMaster`` per broker; ``ContractResolver`` composes a
``dict[SourceId, ContractMaster]``, so a new broker is a new dict entry and
no edit here. Joins are exact on (underlying, expiry, strike, side).

Native key forms:
    Upstox: the BOD ``instrument_key``, e.g. ``"NSE_FO|50978"``.
    Dhan:   ``"<exchange segment>:<security id>"``, e.g. ``"NSE_FNO:35068"``
            (the API segment name, built from the master's ``EXCH_ID`` +
            ``SEGMENT`` columns; NSE derivatives ``D`` map to ``NSE_FNO``).
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from src.client.exceptions import AmbiguousContractError, UnknownSourceError
from src.instruments.lookup import InstrumentLookup, parse_expiry
from src.models.contract import ContractRef, SourceId

_DHAN_SEGMENTS = {("NSE", "D"): "NSE_FNO", ("BSE", "D"): "BSE_FNO"}


class ContractMaster(Protocol):
    """One broker's contract master: canonical contract <-> native key."""

    def to_native(self, ref: ContractRef) -> str | None:
        """Return the native key for ``ref``, or None if unlisted."""
        ...

    def from_native(self, native_key: str) -> ContractRef | None:
        """Return the contract for a native key, or None if unknown."""
        ...


class _MapMaster:
    """Bidirectional exact-match map built once; duplicates raise."""

    def __init__(self, pairs: Iterable[tuple[ContractRef, str]], label: str) -> None:
        self._fwd: dict[ContractRef, str] = {}
        self._rev: dict[str, ContractRef] = {}
        for ref, key in pairs:
            if ref in self._fwd or key in self._rev:
                raise AmbiguousContractError(f"{label}: duplicate mapping for {ref} / {key}")
            self._fwd[ref] = key
            self._rev[key] = ref

    def to_native(self, ref: ContractRef) -> str | None:
        """Return the native key for ``ref``, or None if unlisted."""
        return self._fwd.get(ref)

    def from_native(self, native_key: str) -> ContractRef | None:
        """Return the contract for a native key, or None if unknown."""
        return self._rev.get(native_key)


class UpstoxContractMaster(_MapMaster):
    """Upstox master built from an ``InstrumentLookup`` over the BOD."""

    def __init__(self, lookup: InstrumentLookup, underlyings: Iterable[str]) -> None:
        """Build the map.

        Args:
            lookup: Loaded BOD lookup (reused, not re-parsed).
            underlyings: Underlying symbols to index, e.g. ``["NIFTY"]``.

        Raises:
            AmbiguousContractError: A contract or key appears twice.
        """
        super().__init__(self._pairs(lookup, underlyings), "upstox")

    @staticmethod
    def _pairs(
        lookup: InstrumentLookup, underlyings: Iterable[str]
    ) -> Iterator[tuple[ContractRef, str]]:
        for name in underlyings:
            for inst in lookup.search_options(name, max_results=max(lookup.count, 1)):
                ref = _upstox_ref(inst)
                if ref is not None:
                    yield ref, inst["instrument_key"]


def _upstox_ref(inst: dict[str, Any]) -> ContractRef | None:
    expiry = parse_expiry(inst.get("expiry"))
    if expiry is None or inst.get("strike_price") is None:
        return None
    return ContractRef(
        underlying=str(inst["underlying_symbol"]).upper(),
        expiry=date.fromisoformat(expiry),
        strike=Decimal(str(inst["strike_price"])),
        side=inst["instrument_type"],
    )


class DhanContractMaster(_MapMaster):
    """Dhan master built from rows of the detailed scrip-master CSV."""

    def __init__(self, rows: Iterable[dict[str, str]], underlyings: Iterable[str]) -> None:
        """Build the map from CSV rows (option rows in a known segment only).

        Args:
            rows: ``csv.DictReader``-style rows of ``api-scrip-master-detailed.csv``.
            underlyings: Underlying symbols to index, e.g. ``["NIFTY"]``.

        Raises:
            AmbiguousContractError: A contract or key appears twice.
        """
        wanted = {u.upper() for u in underlyings}
        super().__init__(self._pairs(rows, wanted), "dhan")

    @classmethod
    def from_csv(cls, path: str | Path, underlyings: Iterable[str]) -> DhanContractMaster:
        """Load the master from a CSV file on disk."""
        with open(path, newline="", encoding="utf-8") as f:
            return cls(csv.DictReader(f), underlyings)

    @staticmethod
    def _pairs(
        rows: Iterable[dict[str, str]], wanted: set[str]
    ) -> Iterator[tuple[ContractRef, str]]:
        for row in rows:
            segment = _DHAN_SEGMENTS.get((row["EXCH_ID"], row["SEGMENT"]))
            name = row["UNDERLYING_SYMBOL"].upper()
            side = row["OPTION_TYPE"]
            if segment is None or name not in wanted or side not in ("CE", "PE"):
                continue
            ref = ContractRef(
                underlying=name,
                expiry=date.fromisoformat(row["SM_EXPIRY_DATE"][:10]),
                strike=Decimal(row["STRIKE_PRICE"]),
                side="CE" if side == "CE" else "PE",
            )
            yield ref, f"{segment}:{row['SECURITY_ID']}"


class MasterContractResolver:
    """``ContractResolver`` composing one ``ContractMaster`` per source."""

    def __init__(self, masters: dict[SourceId, ContractMaster]) -> None:
        self._masters = dict(masters)

    def _master(self, source: SourceId) -> ContractMaster:
        try:
            return self._masters[source]
        except KeyError:
            raise UnknownSourceError(f"no contract master registered for {source.value}") from None

    def to_native(self, ref: ContractRef, source: SourceId) -> str | None:
        """Return the native key for ``ref`` at ``source``, or None if unlisted.

        Raises:
            UnknownSourceError: No master is registered for ``source``.
        """
        return self._master(source).to_native(ref)

    def from_native(self, source: SourceId, native_key: str) -> ContractRef | None:
        """Return the contract for a native key, or None if unknown.

        Raises:
            UnknownSourceError: No master is registered for ``source``.
        """
        return self._master(source).from_native(native_key)
