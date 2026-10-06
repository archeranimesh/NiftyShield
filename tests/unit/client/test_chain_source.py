from datetime import date
from decimal import Decimal

import pytest

from src.client.chain_source import CompositeChainSource, DhanChainSource, UpstoxChainSource
from src.client.exceptions import DataFetchError
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


class FakeChainSource:
    def __init__(self, chain: OptionChain | Exception):
        self.chain_or_exc = chain
        self.called = False

    async def get_chain(self, underlying: str, expiry: str) -> OptionChain:
        self.called = True
        if isinstance(self.chain_or_exc, Exception):
            raise self.chain_or_exc
        return self.chain_or_exc


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


@pytest.mark.asyncio
async def test_upstox_greeks_present_dhan_not_called():
    upstox_chain = create_mock_chain([Decimal("0.5")])
    dhan_source = FakeChainSource(create_mock_chain([Decimal("0.5")]))

    composite = CompositeChainSource(FakeChainSource(upstox_chain), dhan_source)
    res = await composite.get_chain("NSE_INDEX|Nifty 50", "2026-10-29")

    assert res is upstox_chain
    assert not dhan_source.called


@pytest.mark.asyncio
async def test_upstox_all_zero_falls_back_to_dhan():
    upstox_chain = create_mock_chain([Decimal("0")])
    dhan_chain = create_mock_chain([Decimal("0.5")])

    dhan_source = FakeChainSource(dhan_chain)
    composite = CompositeChainSource(FakeChainSource(upstox_chain), dhan_source)

    res = await composite.get_chain("NSE_INDEX|Nifty 50", "2026-10-29")
    assert res is dhan_chain
    assert dhan_source.called


@pytest.mark.asyncio
async def test_both_fail_raises():
    upstox_chain = create_mock_chain([Decimal("0")])
    dhan_chain = create_mock_chain([Decimal("0")])

    dhan_source = FakeChainSource(dhan_chain)
    composite = CompositeChainSource(FakeChainSource(upstox_chain), dhan_source)

    with pytest.raises(
        DataFetchError, match="Both Upstox and Dhan returned empty or zero-delta chains"
    ):
        await composite.get_chain("NSE_INDEX|Nifty 50", "2026-10-29")


@pytest.mark.asyncio
async def test_partial_zero_is_not_fallback_trigger():
    upstox_chain = create_mock_chain([Decimal("0"), Decimal("0.5")])
    dhan_source = FakeChainSource(create_mock_chain([Decimal("0.5")]))

    composite = CompositeChainSource(FakeChainSource(upstox_chain), dhan_source)
    res = await composite.get_chain("NSE_INDEX|Nifty 50", "2026-10-29")

    assert res is upstox_chain
    assert not dhan_source.called


@pytest.mark.asyncio
async def test_all_None_treated_as_all_zero():
    upstox_chain = create_mock_chain([None, None])
    dhan_chain = create_mock_chain([Decimal("0.5")])

    dhan_source = FakeChainSource(dhan_chain)
    composite = CompositeChainSource(FakeChainSource(upstox_chain), dhan_source)

    res = await composite.get_chain("NSE_INDEX|Nifty 50", "2026-10-29")
    assert res is dhan_chain
    assert dhan_source.called


@pytest.mark.asyncio
async def test_empty_upstox_chain_triggers_fallback():
    upstox_chain = create_mock_chain([])
    dhan_chain = create_mock_chain([Decimal("0.5")])

    dhan_source = FakeChainSource(dhan_chain)
    composite = CompositeChainSource(FakeChainSource(upstox_chain), dhan_source)

    res = await composite.get_chain("NSE_INDEX|Nifty 50", "2026-10-29")
    assert res is dhan_chain
    assert dhan_source.called


@pytest.mark.asyncio
async def test_dhan_all_zero_raises():
    upstox_chain = create_mock_chain([])
    dhan_chain = create_mock_chain([Decimal("0")])

    dhan_source = FakeChainSource(dhan_chain)
    composite = CompositeChainSource(FakeChainSource(upstox_chain), dhan_source)

    with pytest.raises(DataFetchError):
        await composite.get_chain("NSE_INDEX|Nifty 50", "2026-10-29")


@pytest.mark.asyncio
async def test_upstox_wrapper(monkeypatch):
    fake_client = FakeUpstoxClient({"some": "raw_data"})

    # mock parse_upstox_option_chain to just return a dummy
    dummy_chain = create_mock_chain([Decimal("0.5")])
    import src.client.chain_source

    monkeypatch.setattr(src.client.chain_source, "parse_upstox_option_chain", lambda x: dummy_chain)

    source = UpstoxChainSource(fake_client)
    res = await source.get_chain("NSE_INDEX|Nifty 50", "2026-10-29")

    assert res is dummy_chain
    assert fake_client.called_with == ("NSE_INDEX|Nifty 50", "2026-10-29")


@pytest.mark.asyncio
async def test_dhan_wrapper():
    expected_chain = create_mock_chain([Decimal("0.5")])
    fake_client = FakeDhanClient(expected_chain)
    source = DhanChainSource(fake_client)

    res = await source.get_chain("NSE_INDEX|Nifty 50", "2026-10-29")
    assert res is expected_chain
    assert fake_client.called_with == ("NSE_INDEX|Nifty 50", date(2026, 10, 29))


@pytest.mark.asyncio
async def test_upstox_exception_propagates():
    fake_upstox = FakeChainSource(DataFetchError("Upstox down"))
    fake_dhan = FakeChainSource(create_mock_chain([Decimal("0.5")]))

    composite = CompositeChainSource(fake_upstox, fake_dhan)

    with pytest.raises(DataFetchError, match="Upstox down"):
        await composite.get_chain("NSE_INDEX|Nifty 50", "2026-10-29")

    assert not fake_dhan.called


@pytest.mark.asyncio
async def test_upstox_empty_dhan_all_none_raises():
    upstox = FakeUpstoxClient(empty=True)
    dhan = FakeDhanClient(all_zero=True)
    source = CompositeChainSource(UpstoxChainSource(upstox), DhanChainSource(dhan))
    with pytest.raises(DataFetchError, match="both Upstox and Dhan failed to return usable data"):
        await source.get_chain("NSE_INDEX|Nifty 50", "2026-12-31")
