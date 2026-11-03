"""Tests for the contract resolver over the Upstox BOD and Dhan master (offline)."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.client.contract_resolver import (
    DhanContractMaster,
    MasterContractResolver,
    UpstoxContractMaster,
)
from src.client.exceptions import AmbiguousContractError, UnknownSourceError
from src.instruments.lookup import InstrumentLookup
from src.models.contract import ContractRef, SourceId

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "contract_resolver"


@pytest.fixture(scope="module")
def upstox() -> UpstoxContractMaster:
    data = json.loads((FIX / "upstox_bod_nifty_dec.json").read_text())
    return UpstoxContractMaster(InstrumentLookup(data), ["NIFTY"])


@pytest.fixture(scope="module")
def dhan() -> DhanContractMaster:
    return DhanContractMaster.from_csv(FIX / "dhan_scrip_master_nifty_dec.csv", ["NIFTY"])


@pytest.fixture(scope="module")
def resolver(upstox, dhan) -> MasterContractResolver:
    return MasterContractResolver({SourceId.UPSTOX: upstox, SourceId.DHAN: dhan})


def _refs(master) -> list[ContractRef]:
    return list(master._fwd)


def test_round_trip_both_brokers(resolver, upstox, dhan):
    refs = _refs(upstox)
    assert len(refs) == 265 and len(_refs(dhan)) == 598
    for ref in refs:
        for source in (SourceId.UPSTOX, SourceId.DHAN):
            key = resolver.to_native(ref, source)
            assert key is not None
            assert resolver.from_native(source, key) == ref
    for ref in _refs(dhan):
        key = resolver.to_native(ref, SourceId.DHAN)
        assert resolver.from_native(SourceId.DHAN, key) == ref


def test_native_key_forms(resolver):
    ref = ContractRef(
        underlying="NIFTY", expiry=date(2026, 12, 29), strike=Decimal("17350"), side="CE"
    )
    assert resolver.to_native(ref, SourceId.DHAN) == "NSE_FNO:35068"
    assert resolver.to_native(ref, SourceId.UPSTOX) is None


def test_unlisted_strike_returns_none(resolver, upstox, dhan):
    only_dhan = next(r for r in _refs(dhan) if upstox.to_native(r) is None)
    assert resolver.to_native(only_dhan, SourceId.UPSTOX) is None
    assert resolver.to_native(only_dhan, SourceId.DHAN) is not None
    assert resolver.from_native(SourceId.UPSTOX, "NSE_FO|0") is None


def test_unregistered_source_raises(upstox):
    only_upstox = MasterContractResolver({SourceId.UPSTOX: upstox})
    ref = _refs(upstox)[0]
    with pytest.raises(UnknownSourceError):
        only_upstox.to_native(ref, SourceId.DHAN)
    with pytest.raises(UnknownSourceError):
        only_upstox.from_native(SourceId.DHAN, "NSE_FNO:1")


def test_duplicate_mapping_raises():
    rows = [
        {
            "EXCH_ID": "NSE",
            "SEGMENT": "D",
            "SECURITY_ID": sid,
            "UNDERLYING_SYMBOL": "NIFTY",
            "SM_EXPIRY_DATE": "2026-12-29",
            "STRIKE_PRICE": "17350.00000",
            "OPTION_TYPE": "CE",
        }
        for sid in ("1", "2")
    ]
    with pytest.raises(AmbiguousContractError):
        DhanContractMaster(rows, ["NIFTY"])
    inst = {
        "segment": "NSE_FO",
        "instrument_type": "CE",
        "underlying_symbol": "NIFTY",
        "expiry": 1798568999000,
        "strike_price": 17350.0,
    }
    data = [{**inst, "instrument_key": "NSE_FO|1"}, {**inst, "instrument_key": "NSE_FO|2"}]
    with pytest.raises(AmbiguousContractError):
        UpstoxContractMaster(InstrumentLookup(data), ["NIFTY"])


def test_other_underlying_and_segment_ignored():
    row = {
        "EXCH_ID": "NSE",
        "SEGMENT": "E",
        "SECURITY_ID": "9",
        "UNDERLYING_SYMBOL": "NIFTY",
        "SM_EXPIRY_DATE": "2026-12-29",
        "STRIKE_PRICE": "1.0",
        "OPTION_TYPE": "CE",
    }
    assert (
        DhanContractMaster([row], ["NIFTY"]).to_native(
            ContractRef(
                underlying="NIFTY", expiry=date(2026, 12, 29), strike=Decimal("1"), side="CE"
            )
        )
        is None
    )
