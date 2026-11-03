"""ChainSnapshot -> raw Upstox row adapter for the overlay bootstraps.

The overlay bootstraps select strikes from the raw Upstox row shape
(``filter_strikes_by_delta`` and friends) because ``OverlayConfig`` needs each
contract's ``instrument_key``. ``ChainSource`` returns a canonical
``ChainSnapshot`` whose ``instrument_keys`` map holds the **Upstox ledger key**
for every contract the BOD lists, whichever broker supplied the Greeks. This
module is the one place that turns the former back into the latter; CC, PP and
Collar all share it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any, Literal

import structlog

from src.models.contract import ChainSnapshot
from src.models.options import OptionLeg

logger = structlog.get_logger(__name__)

# (underlying instrument key, expiry YYYY-MM-DD) -> raw Upstox rows. Sync, as
# the bootstraps are.
ChainFetch = Callable[[str, str], list[dict[str, Any]]]

DEFAULT_FETCH_TIMEOUT_S = 90.0


def _num(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _side_dict(leg: OptionLeg, instrument_key: str) -> dict[str, Any]:
    return {
        "instrument_key": instrument_key,
        "market_data": {
            "ltp": float(leg.ltp),
            "bid_price": float(leg.bid),
            "ask_price": float(leg.ask),
            "oi": leg.oi,
            "volume": leg.volume,
        },
        "option_greeks": {
            "delta": _num(leg.delta),
            "gamma": _num(leg.gamma),
            "theta": _num(leg.theta),
            "vega": _num(leg.vega),
            "iv": _num(leg.iv),
        },
    }


def chain_to_rows(snapshot: ChainSnapshot) -> list[dict[str, Any]]:
    """Convert a snapshot to raw Upstox strike rows carrying ledger keys.

    A leg whose Upstox ledger key is absent from ``snapshot.instrument_keys``
    is dropped (never given another broker's key) and the drop count is logged.
    A strike with no resolvable leg is omitted.

    Args:
        snapshot: Chain plus its Upstox ledger key map.

    Returns:
        Rows sorted by strike; empty if no leg could be resolved.
    """
    chain = snapshot.chain
    keys = {
        (ref.strike, ref.side): key
        for ref, key in snapshot.instrument_keys.items()
        if ref.expiry == chain.expiry
    }
    rows: list[dict[str, Any]] = []
    dropped = 0
    for strike, row in sorted(chain.strikes.items()):
        out: dict[str, Any] = {
            "expiry": chain.expiry.isoformat(),
            "strike_price": float(strike),
            "underlying_spot_price": float(chain.underlying_spot),
        }
        sides: tuple[tuple[Literal["CE", "PE"], str, OptionLeg | None], ...] = (
            ("CE", "call_options", row.ce),
            ("PE", "put_options", row.pe),
        )
        for side, field, leg in sides:
            if leg is None:
                continue
            key = keys.get((strike, side))
            if key is None:
                dropped += 1
            else:
                out[field] = _side_dict(leg, key)
        if "call_options" in out or "put_options" in out:
            rows.append(out)
    if dropped:
        logger.warning("chain_rows.unresolved_key_dropped", count=dropped, kept=len(rows))
    logger.info(
        "chain_rows.converted",
        greeks_source=snapshot.greeks_source.value,
        expiry=chain.expiry.isoformat(),
        rows=len(rows),
    )
    return rows


def rows_fetch(
    get_chain: Callable[[str, str], Awaitable[ChainSnapshot]],
    timeout_s: float = DEFAULT_FETCH_TIMEOUT_S,
) -> ChainFetch:
    """Wrap an async ``ChainSource.get_chain`` as a sync raw-row fetch.

    Uses ``asyncio.run``, so it must be called from synchronous code (the
    bootstraps are), never from inside a running event loop.

    Args:
        get_chain: ``ChainSource.get_chain`` (or any equivalent coroutine function).
        timeout_s: Whole-call timeout, covering fallback and rate-limit sleeps.

    Returns:
        A :data:`ChainFetch`. It raises ``TimeoutError`` or the source's own
        exception on failure; the bootstraps treat both as a structural abort.
    """

    def fetch(underlying: str, expiry: str) -> list[dict[str, Any]]:
        async def run() -> ChainSnapshot:
            return await asyncio.wait_for(get_chain(underlying, expiry), timeout_s)

        return chain_to_rows(asyncio.run(run()))

    return fetch
