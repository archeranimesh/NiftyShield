import json
import socket
import sqlite3
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from src.client.chain_source import ChainRouter, DhanChainSource, UpstoxChainSource
from src.client.contract_resolver import MasterContractResolver
from src.client.exceptions import (
    AuthenticationError,
    DataFetchError,
    NotSubscribedError,
    ProviderRateLimitError,
)
from src.client.source_health import SourceHealth
from src.client.upstox_market import parse_upstox_option_chain
from src.models.contract import ChainSnapshot, ContractRef, SourceId
from src.models.options import OptionChain, OptionChainStrike, OptionLeg


class FakeUpstoxClient:
    def __init__(self, raw_data_or_exc):
        self.raw_data_or_exc = raw_data_or_exc
        self.called_with = None

    async def get_option_chain(self, underlying, expiry):
        self.called_with = (underlying, expiry)
        if isinstance(self.raw_data_or_exc, Exception):
            raise self.raw_data_or_exc
        return self.raw_data_or_exc


class FakeDhanClient:
    def __init__(self, parsed_chain_or_exc):
        self.parsed_chain_or_exc = parsed_chain_or_exc
        self.called_with = None

    async def get_option_chain(self, underlying, expiry):
        self.called_with = (underlying, expiry)
        if isinstance(self.parsed_chain_or_exc, Exception):
            raise self.parsed_chain_or_exc
        return self.parsed_chain_or_exc


NOW = datetime(2026, 11, 3, 5, 0, tzinfo=timezone.utc)
NIFTY = "NSE_INDEX|Nifty 50"


def snap(chain: OptionChain, source: SourceId = SourceId.UPSTOX) -> ChainSnapshot:
    return ChainSnapshot(chain=chain, greeks_source=source, fetched_at=NOW, instrument_keys={})


class FakeChainSource:
    """Scripted source: each call pops the next outcome (the last one repeats)."""

    def __init__(self, *outcomes: ChainSnapshot | Exception, source: SourceId = SourceId.UPSTOX):
        self.outcomes = list(outcomes)
        self.source = source
        self.calls = 0

    @property
    def called(self) -> bool:
        return self.calls > 0

    async def get_chain(self, underlying: str, expiry: str) -> ChainSnapshot:
        self.calls += 1
        out = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(out, Exception):
            raise out
        return out


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


class Alerts:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def __call__(self, message: str) -> None:
        self.messages.append(message)


U, D = SourceId.UPSTOX, SourceId.DHAN


def make_router(
    sources: Sequence[tuple[SourceId, Any]],
    clock: FakeClock | None = None,
    alerts: Alerts | None = None,
) -> tuple[ChainRouter, FakeClock, SourceHealth]:
    clock = clock or FakeClock()
    health = SourceHealth(alert=alerts, clock=clock)
    return ChainRouter(sources, health=health, sleep=clock.sleep), clock, health


def create_mock_chain(deltas: list[Decimal | None]) -> OptionChain:
    strikes = {}
    for i, d in enumerate(deltas):
        # We just fill CE to simplify, PE delta defaults to None
        ce_leg = OptionLeg(
            ltp=Decimal("0"),
            bid=Decimal("0"),
            ask=Decimal("0"),
            oi=0,
            volume=0,
            delta=d,
            gamma=None,
            theta=None,
            vega=None,
            iv=None,
            strike=Decimal(1000 + i),
        )
        pe_leg = OptionLeg(
            ltp=Decimal("0"),
            bid=Decimal("0"),
            ask=Decimal("0"),
            oi=0,
            volume=0,
            delta=None,
            gamma=None,
            theta=None,
            vega=None,
            iv=None,
            strike=Decimal(1000 + i),
        )
        strikes[Decimal(1000 + i)] = OptionChainStrike(ce=ce_leg, pe=pe_leg)
    return OptionChain(underlying_spot=Decimal("1000"), expiry=date(2026, 10, 29), strikes=strikes)


GOOD = create_mock_chain([Decimal("0.5")])
ZERO = create_mock_chain([Decimal("0")])


class StubMaster:
    """Master listing only the listed (strike, side) pairs, as Upstox-style keys."""

    def __init__(self, listed: dict[tuple[int, str], str]) -> None:
        self.listed = listed

    def to_native(self, ref: ContractRef) -> str | None:
        return self.listed.get((int(ref.strike), ref.side))

    def from_native(self, native_key: str) -> ContractRef | None:
        return None


# --- sources return ChainSnapshot ------------------------------------------


@pytest.mark.asyncio
async def test_upstox_only_reproduces_parsed_chain_exactly():
    """Regression pin: bare Upstox path (today's Upstox-only) yields parse_upstox_option_chain's chain.

    The fixture has all-zero deltas, and the bare source still returns it (no usability
    gate). DSC-4 must wire the Upstox-only default as the bare source, not a one-entry
    ChainRouter, which would raise on such a chain.
    """
    path = Path("tests/fixtures/responses/option_chain/nifty_chain_2026-04-07.json")
    raw = json.loads(path.read_text())

    res = await UpstoxChainSource(FakeUpstoxClient(raw)).get_chain(NIFTY, "2026-04-07")

    assert res.chain == parse_upstox_option_chain(raw)
    assert res.greeks_source is U


@pytest.mark.asyncio
async def test_upstox_wrapper_tags_utc_and_partial_ledger_keys():
    chain = create_mock_chain([Decimal("0.5"), Decimal("0.4")])  # strikes 1000, 1001
    resolver = MasterContractResolver(
        {U: StubMaster({(1000, "CE"): "NSE_FO|1", (1001, "PE"): "NSE_FO|2"})}
    )
    source = UpstoxChainSource(FakeUpstoxClient([]), resolver)
    import src.client.chain_source as cs

    cs.parse_upstox_option_chain, orig = (lambda _: chain), cs.parse_upstox_option_chain
    try:
        res = await source.get_chain(NIFTY, "2026-10-29")
    finally:
        cs.parse_upstox_option_chain = orig

    assert res.chain is chain
    assert res.fetched_at.utcoffset() == timedelta(0)
    ref = ContractRef(
        underlying="NIFTY", expiry=date(2026, 10, 29), strike=Decimal("1000.0"), side="CE"
    )
    assert res.instrument_keys == {
        ref: "NSE_FO|1",
        ref.model_copy(update={"strike": Decimal("1001"), "side": "PE"}): "NSE_FO|2",
    }


@pytest.mark.asyncio
async def test_dhan_wrapper_tags_dhan_with_upstox_ledger_keys():
    chain = create_mock_chain([Decimal("0.5")])
    fake_client = FakeDhanClient(chain)
    resolver = MasterContractResolver({U: StubMaster({(1000, "CE"): "NSE_FO|1"})})
    source = DhanChainSource(fake_client, resolver)

    res = await source.get_chain(NIFTY, "2026-10-29")

    assert res.chain is chain and res.greeks_source is D
    assert list(res.instrument_keys.values()) == ["NSE_FO|1"]
    assert fake_client.called_with == (NIFTY, date(2026, 10, 29))


@pytest.mark.asyncio
async def test_unknown_underlying_or_no_resolver_gives_empty_keys():
    source = DhanChainSource(FakeDhanClient(GOOD))
    assert (await source.get_chain(NIFTY, "2026-10-29")).instrument_keys == {}


@pytest.mark.asyncio
async def test_upstox_exception_propagates_from_wrapper():
    source = UpstoxChainSource(FakeUpstoxClient(DataFetchError("Upstox down")))
    with pytest.raises(DataFetchError, match="Upstox down"):
        await source.get_chain(NIFTY, "2026-10-29")


# --- routing taxonomy -------------------------------------------------------


@pytest.mark.asyncio
async def test_monthly_selects_upstox_without_dhan_call():
    up, dh = FakeChainSource(snap(GOOD)), FakeChainSource(snap(GOOD, D))
    router, _, _ = make_router([(U, up), (D, dh)])

    res = await router.get_chain(NIFTY, "2026-10-29")

    assert res.greeks_source is U
    assert up.calls == 1 and not dh.called


@pytest.mark.asyncio
async def test_far_expiry_all_zero_falls_through_to_dhan_without_changing_next_near_expiry_call():
    up = FakeChainSource(snap(ZERO), snap(GOOD))
    dh = FakeChainSource(snap(GOOD, D))
    router, _, health = make_router([(U, up), (D, dh)])

    far = await router.get_chain(NIFTY, "2027-12-28")
    near = await router.get_chain(NIFTY, "2026-11-24")

    assert far.greeks_source is D and dh.calls == 1
    assert near.greeks_source is U and dh.calls == 1
    assert not health.is_unhealthy(U, "chain")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first", [snap(create_mock_chain([])), snap(create_mock_chain([None, None]))]
)
async def test_empty_or_all_none_chain_falls_back(first):
    router, _, _ = make_router([(U, FakeChainSource(first)), (D, FakeChainSource(snap(GOOD, D)))])
    assert (await router.get_chain(NIFTY, "2027-12-28")).greeks_source is D


@pytest.mark.asyncio
async def test_all_sources_unusable_raises():
    router, _, _ = make_router(
        [(U, FakeChainSource(snap(ZERO))), (D, FakeChainSource(snap(ZERO, D)))]
    )
    with pytest.raises(DataFetchError, match="No usable chain"):
        await router.get_chain(NIFTY, "2027-12-28")


@pytest.mark.asyncio
async def test_805_does_not_flip_source():
    dh = FakeChainSource(ProviderRateLimitError("805"), source=D)
    up = FakeChainSource(snap(GOOD))
    router, clock, health = make_router([(D, dh), (U, up)])

    with pytest.raises(ProviderRateLimitError):
        await router.get_chain(NIFTY, "2027-12-28")
    with pytest.raises(ProviderRateLimitError):
        await router.get_chain(NIFTY, "2027-12-28")

    assert not up.called
    assert dh.calls == 2  # no in-router retry, and Dhan stays healthy
    assert clock.sleeps == [4.0, 4.0]
    assert not health.is_unhealthy(D, "chain")


@pytest.mark.asyncio
async def test_805_backoff_floor_comes_from_constructor():
    clock = FakeClock()
    router = ChainRouter(
        [(D, FakeChainSource(ProviderRateLimitError("805")))],
        dhan_min_interval_s=7.5,
        sleep=clock.sleep,
    )
    with pytest.raises(ProviderRateLimitError):
        await router.get_chain(NIFTY, "2027-12-28")
    assert clock.sleeps == [7.5]


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [NotSubscribedError("806"), AuthenticationError("stale token")])
async def test_806_and_stale_token_issue_no_dhan_call_and_alert(exc):
    dh = FakeChainSource(exc, source=D)
    up = FakeChainSource(snap(GOOD))
    alerts = Alerts()
    router, clock, health = make_router([(D, dh), (U, up)], alerts=alerts)

    first = await router.get_chain(NIFTY, "2027-12-28")
    second = await router.get_chain(NIFTY, "2027-12-28")

    assert first.greeks_source is U and second.greeks_source is U
    assert dh.calls == 1  # no Dhan call once unhealthy
    assert len(alerts.messages) == 1 and "dhan" in alerts.messages[0]
    assert health.is_unhealthy(D, "chain") and not health.is_unhealthy(U, "chain")

    clock.now += 61  # bounded probe is due; a still-failing probe does not re-alert
    await router.get_chain(NIFTY, "2027-12-28")
    assert dh.calls == 2 and len(alerts.messages) == 1


@pytest.mark.asyncio
async def test_successful_probe_restores_source():
    dh = FakeChainSource(NotSubscribedError("806"), snap(GOOD, D), source=D)
    router, clock, health = make_router([(D, dh), (U, FakeChainSource(snap(GOOD)))])
    await router.get_chain(NIFTY, "2027-12-28")
    clock.now += 61

    res = await router.get_chain(NIFTY, "2027-12-28")

    assert res.greeks_source is D and not health.is_unhealthy(D, "chain")


@pytest.mark.asyncio
async def test_transport_failure_retries_once_then_opens_circuit():
    dh = FakeChainSource(DataFetchError("net down"), source=D)
    up = FakeChainSource(snap(GOOD))
    alerts = Alerts()
    router, clock, health = make_router([(D, dh), (U, up)], alerts=alerts)

    first = await router.get_chain(NIFTY, "2027-12-28")
    assert dh.calls == 2 and first.greeks_source is U  # one retry, then fall back

    await router.get_chain(NIFTY, "2027-12-28")
    assert dh.calls == 2  # circuit open: no Dhan call
    assert alerts.messages == []  # a transport circuit is logged, not alerted

    clock.now += 61
    await router.get_chain(NIFTY, "2027-12-28")
    assert dh.calls == 4  # one bounded probe (itself retried once)


@pytest.mark.asyncio
async def test_transport_retry_success_keeps_source():
    dh = FakeChainSource(DataFetchError("blip"), snap(GOOD, D), source=D)
    router, _, health = make_router([(D, dh), (U, FakeChainSource(snap(GOOD)))])
    res = await router.get_chain(NIFTY, "2027-12-28")
    assert res.greeks_source is D and dh.calls == 2
    assert not health.is_unhealthy(D, "chain")


@pytest.mark.asyncio
async def test_single_source_transport_failure_raises_data_fetch_error():
    router, _, _ = make_router([(U, FakeChainSource(DataFetchError("Upstox down")))])
    with pytest.raises(DataFetchError, match="Upstox down"):
        await router.get_chain(NIFTY, "2026-10-29")


@pytest.mark.asyncio
async def test_alert_failure_is_non_fatal():
    async def boom(message: str) -> None:
        raise RuntimeError("telegram down")

    clock = FakeClock()
    router = ChainRouter(
        [(D, FakeChainSource(NotSubscribedError("806"))), (U, FakeChainSource(snap(GOOD)))],
        health=SourceHealth(alert=boom, clock=clock),
        sleep=clock.sleep,
    )
    assert (await router.get_chain(NIFTY, "2027-12-28")).greeks_source is U


def test_probe_interval_doubles_and_is_capped():
    clock = FakeClock()
    health = SourceHealth(clock=clock, probe_interval_s=10, max_probe_interval_s=30)
    import asyncio

    asyncio.run(health.mark_unhealthy(D, "chain", "x", alert=False))
    gaps = []
    for _ in range(4):
        clock.now = max(clock.now, health._unhealthy[(D, "chain")].next_probe_at)
        before = clock.now
        assert health.allow(D, "chain")
        gaps.append(health._unhealthy[(D, "chain")].next_probe_at - before)
        assert not health.allow(D, "chain")  # only one probe per window
    assert gaps == [20, 30, 30, 30]


# --- extensibility and hermeticity -----------------------------------------


@pytest.mark.asyncio
async def test_third_source_routes_without_editing_router():
    """A new SourceId member plus stub source and master routes, falls back and tags provenance."""
    kite = str.__new__(SourceId, "kite")
    kite._name_, kite._value_ = "KITE", "kite"  # stand-in for a future enum member
    resolver = MasterContractResolver(
        {kite: StubMaster({(1000, "CE"): "KITE|1"}), U: StubMaster({})}
    )
    ref = ContractRef(
        underlying="NIFTY", expiry=date(2026, 10, 29), strike=Decimal("1000"), side="CE"
    )
    assert resolver.to_native(ref, kite) == "KITE|1"

    third = FakeChainSource(snap(GOOD, kite), source=kite)
    router, _, _ = make_router(
        [
            (U, FakeChainSource(snap(ZERO))),
            (D, FakeChainSource(DataFetchError("x"), source=D)),
            (kite, third),
        ]
    )
    res = await router.get_chain(NIFTY, "2027-12-28")

    assert res.greeks_source is kite and third.calls == 1


@pytest.mark.asyncio
async def test_default_pytest_has_no_network_token_or_db(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("network or DB touched")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    router, _, _ = make_router(
        [(U, FakeChainSource(snap(ZERO))), (D, FakeChainSource(snap(GOOD, D)))]
    )

    assert (await router.get_chain(NIFTY, "2027-12-28")).greeks_source is D
