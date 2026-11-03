from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import date, datetime, timezone
from typing import Literal, Protocol

import structlog

from src.client.capability_router import CapabilityRouter
from src.client.dhan_market import DhanMarketClient
from src.client.source_health import SourceHealth
from src.client.upstox_market import UpstoxMarketClient, parse_upstox_option_chain
from src.config import DEFAULT_DHAN_MIN_INTERVAL_S
from src.models.contract import (
    ChainSnapshot,
    ContractRef,
    ContractResolver,
    SourceId,
    has_usable_delta,
)
from src.models.options import OptionChain, OptionLeg

logger = structlog.get_logger(__name__)

CHAIN_CAPABILITY = "chain"
# Request underlying (Upstox instrument key) -> normalised ContractRef underlying.
_REF_UNDERLYING = {"NSE_INDEX|Nifty 50": "NIFTY"}


class ChainSource(Protocol):
    async def get_chain(self, underlying: str, expiry: str) -> ChainSnapshot: ...


def _instrument_keys(
    chain: OptionChain, underlying: str, resolver: ContractResolver | None
) -> dict[ContractRef, str]:
    """Upstox ledger keys for the chain's contracts; partial map is legal."""
    name = _REF_UNDERLYING.get(underlying)
    if resolver is None:
        return {}
    if name is None:
        logger.warning("chain_source.unknown_underlying", underlying=underlying)
        return {}
    keys: dict[ContractRef, str] = {}
    for strike, row in chain.strikes.items():
        sides: tuple[tuple[Literal["CE", "PE"], OptionLeg | None], ...] = (
            ("CE", row.ce),
            ("PE", row.pe),
        )
        for side, leg in sides:
            if leg is None:
                continue
            ref = ContractRef(underlying=name, expiry=chain.expiry, strike=strike, side=side)
            native = resolver.to_native(ref, SourceId.UPSTOX)
            if native is not None:
                keys[ref] = native
    return keys


def _snapshot(
    chain: OptionChain,
    source: SourceId,
    underlying: str,
    resolver: ContractResolver | None,
) -> ChainSnapshot:
    return ChainSnapshot(
        chain=chain,
        greeks_source=source,
        fetched_at=datetime.now(timezone.utc),
        instrument_keys=_instrument_keys(chain, underlying, resolver),
    )


class UpstoxChainSource:
    def __init__(
        self, client: UpstoxMarketClient, resolver: ContractResolver | None = None
    ) -> None:
        self.client = client
        self.resolver = resolver

    async def get_chain(self, underlying: str, expiry: str) -> ChainSnapshot:
        raw_data = await self.client.get_option_chain(underlying, expiry)
        chain = parse_upstox_option_chain(raw_data)
        return _snapshot(chain, SourceId.UPSTOX, underlying, self.resolver)


class DhanChainSource:
    def __init__(self, client: DhanMarketClient, resolver: ContractResolver | None = None) -> None:
        self.client = client
        self.resolver = resolver

    async def get_chain(self, underlying: str, expiry: str) -> ChainSnapshot:
        expiry_date = date.fromisoformat(expiry)
        chain = await self.client.get_option_chain(underlying, expiry_date)
        return _snapshot(chain, SourceId.DHAN, underlying, self.resolver)


class ChainRouter:
    """Ordered-list chain source with per-expiry fallback and health.

    A third source is one more ``(SourceId, ChainSource)`` entry; nothing here
    names a broker. See ``CapabilityRouter`` for the failure taxonomy.
    """

    def __init__(
        self,
        sources: Sequence[tuple[SourceId, ChainSource]],
        health: SourceHealth | None = None,
        dhan_min_interval_s: float = DEFAULT_DHAN_MIN_INTERVAL_S,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Build a chain router.

        Args:
            sources: Ordered sources; the first usable answer wins.
            health: Shared health tracker (a fresh one if omitted).
            dhan_min_interval_s: Rate-limit (805) backoff floor, from config.
            sleep: Awaitable sleep (injected for tests).
        """
        self._core: CapabilityRouter[ChainSource, ChainSnapshot] = CapabilityRouter(
            CHAIN_CAPABILITY,
            sources,
            lambda snap: has_usable_delta(snap.chain),
            health or SourceHealth(),
            rate_limit_backoff_s=dhan_min_interval_s,
            sleep=sleep,
        )

    async def get_chain(self, underlying: str, expiry: str) -> ChainSnapshot:
        return await self._core.call(
            lambda source: source.get_chain(underlying, expiry),
            underlying=underlying,
            expiry=expiry,
        )
