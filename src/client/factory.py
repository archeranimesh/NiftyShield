"""Composition root for broker client instantiation.

This is the **only** module in ``src/`` that imports concrete broker client
implementations (``UpstoxLiveClient``, ``MockBrokerClient``).  All other
modules receive a ``BrokerClient`` via constructor injection — they must
never import concrete client classes directly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import aiohttp

from src.client.chain_rows import DEFAULT_FETCH_TIMEOUT_S, ChainFetch, rows_fetch
from src.client.chain_source import ChainRouter, ChainSource, DhanChainSource, UpstoxChainSource
from src.client.contract_resolver import MasterContractResolver, UpstoxContractMaster
from src.client.dhan_market import Clock, DhanMarketClient, RateLimiter, SpacingRateLimiter
from src.client.mock_client import MockBrokerClient
from src.client.protocol import BrokerClient
from src.client.shared_rate_limiter import SharedRateLimiter
from src.client.source_health import SourceHealth
from src.client.upstox_live import UpstoxLiveClient
from src.client.upstox_market import UpstoxMarketClient
from src.config import settings
from src.instruments.lookup import InstrumentLookup
from src.models.contract import ChainSnapshot, ContractResolver, SourceId

VALID_ENVS: Final = ("prod", "sandbox", "test")


def create_client(env: str, **kwargs: Any) -> BrokerClient:
    """Instantiate the correct broker client for the target environment.

    This is the single composition root — the only place that knows which
    concrete implementation to wire.  Call it at application startup (or in
    test ``conftest.py``) and inject the returned instance everywhere else.

    Args:
        env: Target environment.  Must be one of ``VALID_ENVS``:

            * ``"prod"``    — :class:`UpstoxLiveClient` reading
              ``UPSTOX_ANALYTICS_TOKEN`` from env (or pass ``token=``).
            * ``"sandbox"`` — :class:`UpstoxLiveClient` reading
              ``UPSTOX_SANDBOX_TOKEN`` from env (or pass ``token=``).
            * ``"test"``    — :class:`MockBrokerClient` (offline, no token).

        **kwargs: Forwarded to the chosen client constructor.

            * ``prod`` / ``sandbox``: ``token`` (``str | None``)
            * ``test``:  ``fixtures_dir`` (``Path | None``),
              ``initial_margin`` (``float``, default ``500_000.0``)

    Returns:
        A :class:`BrokerClient` instance.

    Raises:
        ValueError: If *env* is not one of ``VALID_ENVS``.
    """
    if env == "prod":
        return UpstoxLiveClient(token=kwargs.get("token"))

    if env == "sandbox":
        token = kwargs.get("token") or settings.upstox_sandbox_token
        return UpstoxLiveClient(token=token)

    if env == "test":
        return MockBrokerClient(
            fixtures_dir=kwargs.get("fixtures_dir"),
            initial_margin=kwargs.get("initial_margin", 500_000.0),
        )

    raise ValueError(f"Unknown env '{env}'. Valid values: {VALID_ENVS}")


def create_dhan_rate_limiter(
    clock: Clock,
    state_dir: Path | None = None,
    spacing: float | None = None,
) -> RateLimiter:
    """Build the Dhan call throttle.

    Without ``state_dir`` this is the in-process :class:`SpacingRateLimiter`
    (today's behaviour). With it, a :class:`SharedRateLimiter` coordinates the
    capture cron and the monitor daemon through files under ``state_dir``.

    Args:
        clock: Injected time source.
        state_dir: Shared state directory; ``None`` keeps the limiter in-process.
        spacing: Floor in seconds; defaults to ``market_data.chain.dhan_min_interval_s``.

    Returns:
        A :class:`RateLimiter`.
    """
    floor = settings.market_data.chain.dhan_min_interval_s if spacing is None else spacing
    if state_dir is None:
        return SpacingRateLimiter(spacing=floor, clock=clock)
    return SharedRateLimiter(state_dir=state_dir, spacing=floor, clock=clock)


@dataclass(frozen=True)
class _ChainDeps:
    """Collaborators a chain-source builder may draw on."""

    upstox: UpstoxMarketClient | None
    dhan: DhanMarketClient | None
    resolver: ContractResolver | None


def _build_upstox_chain(deps: _ChainDeps) -> ChainSource:
    if deps.upstox is None:
        raise ValueError("chain source 'upstox' is configured but no Upstox client was supplied")
    return UpstoxChainSource(deps.upstox, deps.resolver)


def _build_dhan_chain(deps: _ChainDeps) -> ChainSource:
    if deps.dhan is None:
        raise ValueError("chain source 'dhan' is configured but no Dhan client was supplied")
    return DhanChainSource(deps.dhan, deps.resolver)


# A new source is one entry here (plus its SourceId member); nothing else edits.
_CHAIN_BUILDERS: Final[dict[SourceId, Callable[[_ChainDeps], ChainSource]]] = {
    SourceId.UPSTOX: _build_upstox_chain,
    SourceId.DHAN: _build_dhan_chain,
}


def create_chain_source(
    upstox: UpstoxMarketClient | None = None,
    dhan: DhanMarketClient | None = None,
    resolver: ContractResolver | None = None,
    sources: Sequence[SourceId] | None = None,
    dhan_min_interval_s: float | None = None,
    health: SourceHealth | None = None,
) -> ChainSource:
    """Build the chain source from ``market_data.chain`` routing config.

    One configured source yields that bare source (so the Upstox-only default
    behaves exactly as before, including returning an all-zero chain); more
    than one yields a :class:`ChainRouter` in the configured order.

    Args:
        upstox: Upstox market client, required if ``upstox`` is configured.
        dhan: Dhan market client, required if ``dhan`` is configured.
        resolver: Optional contract resolver used to fill native keys.
        sources: Ordered sources; defaults to ``settings.market_data.chain.sources``.
        dhan_min_interval_s: Dhan floor; defaults to the configured value.
        health: Shared health tracker for the router.

    Returns:
        A :class:`ChainSource`.

    Raises:
        ValueError: ``sources`` is empty, a source has no registered builder, or
            its client was not supplied (fails at startup, not at first call).
    """
    cfg = settings.market_data.chain
    order = list(cfg.sources if sources is None else sources)
    if not order:
        raise ValueError("chain sources must not be empty")
    floor = cfg.dhan_min_interval_s if dhan_min_interval_s is None else dhan_min_interval_s
    deps = _ChainDeps(upstox, dhan, resolver)
    built: list[tuple[SourceId, ChainSource]] = []
    for source_id in order:
        builder = _CHAIN_BUILDERS.get(source_id)
        if builder is None:
            raise ValueError(f"no chain source registered for '{source_id.value}'")
        built.append((source_id, builder(deps)))
    if len(built) == 1:
        return built[0][1]
    return ChainRouter(built, health=health, dhan_min_interval_s=floor)


class _SystemClock:
    """Wall-clock ``Clock`` for the Dhan client."""

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def time(self) -> float:
        return asyncio.get_running_loop().time()


def create_overlay_chain_fetch(
    lookup: InstrumentLookup, timeout_s: float = DEFAULT_FETCH_TIMEOUT_S
) -> ChainFetch:
    """Build the routed, sync raw-row chain fetch for the overlay bootstraps.

    The chain source order comes from ``market_data.chain.sources`` (the
    Upstox-only default behaves as a bare Upstox fetch). Contract keys are the
    Upstox ledger keys from the BOD ``lookup``. The Dhan throttle here is
    in-process; the cross-process limiter is wired by the monitor work.

    Args:
        lookup: Loaded BOD lookup, the source of ledger keys.
        timeout_s: Whole-fetch timeout.

    Returns:
        A :data:`ChainFetch` yielding raw Upstox rows.

    Raises:
        AmbiguousContractError: The BOD maps one contract or key twice.
        ValueError: Chain routing config names an unbuildable source.
    """
    resolver = MasterContractResolver({SourceId.UPSTOX: UpstoxContractMaster(lookup, ["NIFTY"])})

    async def get_chain(underlying: str, expiry: str) -> ChainSnapshot:
        async with aiohttp.ClientSession() as session:
            clock = _SystemClock()
            dhan = DhanMarketClient(
                session=session,
                rate_limiter=create_dhan_rate_limiter(clock),
                clock=clock,
                access_token=settings.dhan_access_token or "",
                client_id=settings.dhan_client_id or "",
            )
            source = create_chain_source(
                upstox=UpstoxMarketClient(settings.upstox_analytics_token),
                dhan=dhan,
                resolver=resolver,
            )
            return await source.get_chain(underlying, expiry)

    return rows_fetch(get_chain, timeout_s)
