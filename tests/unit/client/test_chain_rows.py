"""YF-6: ChainSnapshot -> raw Upstox row adapter."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.client.chain_rows import chain_to_rows, rows_fetch
from src.client.chain_source import UpstoxChainSource
from src.client.contract_resolver import MasterContractResolver, UpstoxContractMaster
from src.client.upstox_market import parse_upstox_option_chain
from src.instruments.lookup import InstrumentLookup
from src.instruments.strike_selector import filter_strikes_by_delta
from src.models.contract import ChainSnapshot, ContractRef, SourceId
from src.models.options import OptionChain, OptionChainStrike, OptionLeg

FIX = Path(__file__).resolve().parents[2] / "fixtures"
NOW = datetime(2026, 11, 3, 5, 0, tzinfo=timezone.utc)
EXPIRY = date(2026, 12, 29)
D = Decimal


def _leg(strike: str, delta: str | None, ltp: str = "100") -> OptionLeg:
    return OptionLeg(
        ltp=D(ltp),
        bid=D(ltp) - D("0.5"),
        ask=D(ltp) + D("0.5"),
        oi=1000,
        volume=5,
        delta=None if delta is None else D(delta),
        gamma=D("0.001"),
        theta=D("-1"),
        vega=D("5"),
        iv=D("15"),
        strike=D(strike),
    )


def _snapshot(keys: dict[tuple[str, str], str]) -> ChainSnapshot:
    chain = OptionChain(
        underlying_spot=D("24000"),
        expiry=EXPIRY,
        strikes={
            D("24500"): OptionChainStrike(ce=_leg("24500", "0.30"), pe=_leg("24500", "-0.70")),
            D("25000"): OptionChainStrike(ce=_leg("25000", "0.20"), pe=None),
        },
    )
    return ChainSnapshot(
        chain=chain,
        greeks_source=SourceId.DHAN,
        fetched_at=NOW,
        instrument_keys={
            ContractRef(underlying="NIFTY", expiry=EXPIRY, strike=D(k), side=s): v  # type: ignore[arg-type]
            for (k, s), v in keys.items()
        },
    )


FULL = {("24500", "CE"): "NSE_FO|1", ("24500", "PE"): "NSE_FO|2", ("25000", "CE"): "NSE_FO|3"}


def test_chain_to_rows_roundtrips_filter_strikes_by_delta() -> None:
    rows = chain_to_rows(_snapshot(FULL))
    picked = filter_strikes_by_delta(rows, "CE", 0.18, 0.35)
    assert [(r["strike"], r["instrument_key"], r["delta"]) for r in picked] == [
        (24500.0, "NSE_FO|1", 0.30),
        (25000.0, "NSE_FO|3", 0.20),
    ]
    assert (
        picked[0]["ltp"] == D("100") and picked[0]["bid"] == D("99.5") and picked[0]["oi"] == 1000
    )
    puts = filter_strikes_by_delta(rows, "PE", 0.6, 0.8)
    assert [r["instrument_key"] for r in puts] == ["NSE_FO|2"]
    assert rows[0]["expiry"] == "2026-12-29" and rows[0]["underlying_spot_price"] == 24000.0


def test_roundtrip_matches_parse_upstox_option_chain() -> None:
    rows = chain_to_rows(_snapshot(FULL))
    assert parse_upstox_option_chain(rows) == _snapshot(FULL).chain


def test_unresolved_key_leg_dropped(caplog: pytest.LogCaptureFixture) -> None:
    partial = {k: v for k, v in FULL.items() if k != ("24500", "PE")}
    rows = chain_to_rows(_snapshot(partial))
    assert "put_options" not in rows[0]
    assert rows[0]["call_options"]["instrument_key"] == "NSE_FO|1"
    assert filter_strikes_by_delta(rows, "PE", 0.0, 1.0) == []


def test_all_unresolved_aborts() -> None:
    assert chain_to_rows(_snapshot({})) == []


def test_other_expiry_keys_ignored() -> None:
    snap = _snapshot({})
    other = ContractRef(underlying="NIFTY", expiry=date(2027, 12, 28), strike=D("24500"), side="CE")
    snap = snap.model_copy(update={"instrument_keys": {other: "NSE_FO|9"}})
    assert chain_to_rows(snap) == []


def test_roundtrip_preserves_missing_delta() -> None:
    chain = _snapshot(FULL).chain.model_copy(
        update={"strikes": {D("24500"): OptionChainStrike(ce=_leg("24500", None))}}
    )
    snap = _snapshot(FULL).model_copy(update={"chain": chain})
    assert parse_upstox_option_chain(chain_to_rows(snap)).strikes[D("24500")].ce.delta is None  # type: ignore[union-attr]


def test_missing_delta_emitted_as_none() -> None:
    chain = _snapshot(FULL).chain.model_copy(
        update={"strikes": {D("24500"): OptionChainStrike(ce=_leg("24500", None))}}
    )
    snap = _snapshot(FULL).model_copy(update={"chain": chain})
    assert chain_to_rows(snap)[0]["call_options"]["option_greeks"]["delta"] is None


def test_real_fixture_keys_are_upstox_ledger_keys() -> None:
    """Dec 2027 zero-Greeks fixture + BOD master: every emitted key is a BOD key."""
    bod = FIX / "contract_resolver" / "upstox_bod_nifty_dec.json"
    resolver = MasterContractResolver(
        {SourceId.UPSTOX: UpstoxContractMaster(InstrumentLookup.from_file(bod), ["NIFTY"])}
    )
    raw = json.loads((FIX / "yearly_overlays" / "chain_dec2027_zero_greeks.json").read_text())

    class _Client:
        async def get_option_chain(self, underlying: str, expiry: str) -> list[dict]:
            return raw

    source = UpstoxChainSource(_Client(), resolver)  # type: ignore[arg-type]
    rows = chain_to_rows(asyncio.run(source.get_chain("NSE_INDEX|Nifty 50", "2027-12-28")))
    bod_keys = {i["instrument_key"] for i in json.loads(bod.read_text())}
    keys = [r[f]["instrument_key"] for r in rows for f in ("call_options", "put_options") if f in r]
    assert keys and set(keys) <= bod_keys
    assert not any(k.startswith("NSE_FNO") for k in keys)


def test_rows_fetch_converts_and_times_out() -> None:
    async def ok(underlying: str, expiry: str) -> ChainSnapshot:
        return _snapshot(FULL)

    assert len(rows_fetch(ok)("NSE_INDEX|Nifty 50", "2026-12-29")) == 2

    async def slow(underlying: str, expiry: str) -> ChainSnapshot:
        await asyncio.sleep(5)
        return _snapshot(FULL)

    with pytest.raises(TimeoutError):
        rows_fetch(slow, timeout_s=0.05)("NSE_INDEX|Nifty 50", "2026-12-29")
