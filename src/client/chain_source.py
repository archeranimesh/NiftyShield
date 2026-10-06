from typing import Any, Protocol

import structlog

from src.client.upstox_market import UpstoxMarketClient, parse_upstox_option_chain
from src.models.options import OptionChain

logger = structlog.get_logger(__name__)


class ChainSource(Protocol):
    async def get_chain(self, underlying: str, expiry: str) -> OptionChain: ...


class UpstoxChainSource:
    def __init__(self, client: UpstoxMarketClient):
        self.client = client

    async def get_chain(self, underlying: str, expiry: str) -> OptionChain:
        raw_data = await self.client.get_option_chain(underlying, expiry)
        return parse_upstox_option_chain(raw_data)


class DhanMarketClient(Protocol):
    async def get_option_chain(
        self, security_id: int, segment: str, expiry: str
    ) -> list[dict[str, Any]]: ...


def parse_dhan_option_chain(data: list[dict[str, Any]]) -> OptionChain:
    # To be built
    raise NotImplementedError("parse_dhan_option_chain not implemented")


class DhanChainSource:
    def __init__(self, client: DhanMarketClient):
        self.client = client

    async def get_chain(self, underlying: str, expiry: str) -> OptionChain:
        if underlying == "NSE_INDEX|Nifty 50":
            security_id = 13
            segment = "IDX_I"
        else:
            raise ValueError(f"Unknown underlying for Dhan: {underlying}")

        raw_data = await self.client.get_option_chain(security_id, segment, expiry)
        return parse_dhan_option_chain(raw_data)


def _is_chain_empty_or_zero_delta(chain: OptionChain) -> bool:
    if not chain.strikes:
        return True

    for strike in chain.strikes.values():
        if (strike.ce and strike.ce.delta) or (strike.pe and strike.pe.delta):
            return False
    return True


class CompositeChainSource:
    def __init__(self, upstox: ChainSource, dhan: ChainSource):
        self.upstox = upstox
        self.dhan = dhan

    async def get_chain(self, underlying: str, expiry: str) -> OptionChain:
        upstox_chain = await self.upstox.get_chain(underlying, expiry)

        if _is_chain_empty_or_zero_delta(upstox_chain):
            logger.info("Upstox chain empty or has zero deltas, falling back to Dhan")
            dhan_chain = await self.dhan.get_chain(underlying, expiry)

            if _is_chain_empty_or_zero_delta(dhan_chain):
                raise RuntimeError("Both Upstox and Dhan returned empty or zero-delta chains")

            return dhan_chain

        return upstox_chain
