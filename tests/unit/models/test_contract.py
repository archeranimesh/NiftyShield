"""Tests for src.models.contract (offline)."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

import pytest
from pydantic import ValidationError

from src.models.contract import (
    ChainSnapshot,
    ContractRef,
    SourceId,
    has_usable_delta,
)
from src.models.options import OptionChain, OptionChainStrike, OptionLeg

EXPIRY = date(2027, 12, 28)
UTC_NOW = datetime(2026, 11, 3, 4, 0, tzinfo=timezone.utc)


def _leg(strike: str, delta: str | None) -> OptionLeg:
    return OptionLeg(
        ltp=Decimal("1"),
        bid=Decimal("1"),
        ask=Decimal("1"),
        oi=1,
        volume=1,
        delta=None if delta is None else Decimal(delta),
        gamma=None,
        theta=None,
        vega=None,
        iv=None,
        strike=Decimal(strike),
    )


def _chain(c24: str | None, c25: str | None) -> OptionChain:
    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=EXPIRY,
        strikes={
            Decimal("24000"): OptionChainStrike(ce=_leg("24000", c24)),
            Decimal("25000"): OptionChainStrike(ce=_leg("25000", c25)),
        },
    )


def _ref(strike: str, side: Literal["CE", "PE"] = "CE") -> ContractRef:
    return ContractRef(underlying="NIFTY", expiry=EXPIRY, strike=Decimal(strike), side=side)


def _snap(keys: dict[ContractRef, str], fetched_at: datetime = UTC_NOW) -> ChainSnapshot:
    return ChainSnapshot(
        chain=_chain("0.5", "0"),
        greeks_source=SourceId.DHAN,
        fetched_at=fetched_at,
        instrument_keys=keys,
    )


def test_contract_ref_equality_and_hash() -> None:
    a, b = _ref("24000"), _ref("24000.0")
    assert a == b and hash(a) == hash(b)
    assert {a: "k"}[b] == "k"


def test_contract_ref_rejects_bad_side() -> None:
    with pytest.raises(ValidationError):
        _ref("24000", "XX")  # type: ignore[arg-type]


def test_chain_snapshot_partial_instrument_keys_is_legal() -> None:
    snap = _snap({_ref("24000"): "NSE_FO|1"})
    assert len(snap.instrument_keys) == 1 < len(snap.chain.strikes)


def test_chain_snapshot_rejects_naive_fetched_at() -> None:
    with pytest.raises(ValidationError):
        _snap({}, datetime(2026, 11, 3, 4, 0))


def test_chain_snapshot_rejects_non_utc_offset() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    with pytest.raises(ValidationError):
        _snap({}, datetime(2026, 11, 3, 9, 30, tzinfo=ist))


def test_models_are_frozen() -> None:
    with pytest.raises(ValidationError):
        _ref("24000").strike = Decimal("1")
    with pytest.raises(ValidationError):
        _snap({}).greeks_source = SourceId.UPSTOX


def test_source_id_values_are_the_persisted_strings() -> None:
    assert SourceId.DHAN.value == "dhan" and SourceId.UPSTOX.value == "upstox"
    assert SourceId("dhan") is SourceId.DHAN
    assert SourceId.DHAN == "dhan"


def test_has_usable_delta_whole_chain_and_held_refs() -> None:
    chain = _chain("0", "0.4")
    assert has_usable_delta(chain)
    assert has_usable_delta(chain, [_ref("25000")])
    assert not has_usable_delta(chain, [_ref("24000")])  # zero delta
    assert not has_usable_delta(chain, [_ref("26000")])  # not in chain
    assert not has_usable_delta(chain, [_ref("25000", "PE")])  # missing leg


def test_has_usable_delta_none_zero_and_empty() -> None:
    assert not has_usable_delta(_chain(None, "0"))
    assert not has_usable_delta(_chain("0.5", "0.4"), [])
    empty = OptionChain(underlying_spot=Decimal("1"), expiry=EXPIRY, strikes={})
    assert not has_usable_delta(empty)


def test_has_usable_delta_ignores_other_expiry_ref() -> None:
    other = ContractRef(
        underlying="NIFTY", expiry=date(2026, 12, 29), strike=Decimal("24000"), side="CE"
    )
    assert not has_usable_delta(_chain("0.5", "0.4"), [other])
