from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol

import structlog

from src.client.dhan_market import DhanMarketClient
from src.client.exceptions import DataFetchError
from src.client.upstox_market import UpstoxMarketClient, parse_upstox_option_chain
from src.models.options import OptionChain

logger = structlog.get_logger(__name__)


class ChainSource(Protocol):
    async def get_chain(self, underlying: str, expiry: str) -> OptionChain: ...


class UpstoxChainSource:
    def __init__(self, client: UpstoxMarketClient) -> None:
        self.client = client

    async def get_chain(self, underlying: str, expiry: str) -> OptionChain:
        raw_data = await self.client.get_option_chain(underlying, expiry)
        return parse_upstox_option_chain(raw_data)


class DhanChainSource:
    def __init__(self, client: DhanMarketClient) -> None:
        self.client = client

    async def get_chain(self, underlying: str, expiry: str) -> OptionChain:
        expiry_date = date.fromisoformat(expiry)
        return await self.client.get_option_chain(underlying, expiry_date)


def _is_chain_empty_or_zero_delta(chain: OptionChain) -> bool:
    if not chain.strikes:
        return True

    for strike in chain.strikes.values():
        for leg in (strike.ce, strike.pe):
            if leg is not None and leg.delta is not None and leg.delta != Decimal("0"):
                return False
    return True

    for strike in chain.strikes.values():
        if (strike.ce and strike.ce.delta) or (strike.pe and strike.pe.delta):
            return False
    return True


class CompositeChainSource:
    def __init__(self, upstox: ChainSource, dhan: ChainSource) -> None:
        self.upstox = upstox
        self.dhan = dhan

    async def get_chain(self, underlying: str, expiry: str) -> OptionChain:
        upstox_chain = await self.upstox.get_chain(underlying, expiry)

        if _is_chain_empty_or_zero_delta(upstox_chain):
            logger.info(
                "Fetched OptionChain",
                source="upstox",
                underlying=underlying,
                expiry=expiry,
                status="empty_or_zero",
            )
            logger.info("Upstox chain empty or has zero deltas, falling back to Dhan")
            dhan_chain = await self.dhan.get_chain(underlying, expiry)

            if _is_chain_empty_or_zero_delta(dhan_chain):
                logger.info(
                    "Fetched OptionChain",
                    source="dhan",
                    underlying=underlying,
                    expiry=expiry,
                    status="empty_or_zero",
                )
                raise DataFetchError("Both Upstox and Dhan returned empty or zero-delta chains")

            logger.info(
                "Fetched OptionChain",
                source="dhan",
                underlying=underlying,
                expiry=expiry,
                status="success",
            )
            return dhan_chain

        logger.info(
            "Fetched OptionChain",
            source="upstox",
            underlying=underlying,
            expiry=expiry,
            status="success",
        )
        return upstox_chain
