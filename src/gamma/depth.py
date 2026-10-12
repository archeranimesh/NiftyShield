"""Depth source protocol and null implementation for Phase B gamma scan.

Pure module: does not import concrete broker adapters.
"""

from __future__ import annotations

import dataclasses
import datetime
import typing


@dataclasses.dataclass(frozen=True)
class DepthSnapshot:
    """L2 Market Depth snapshot for an option strike.

    Attributes:
        bid_qty_l1: Quantity available at best bid (Level 1, depth.buy[0].quantity).
        ask_qty_l1: Quantity available at best ask (Level 1, depth.sell[0].quantity).
            Used by Layer 0 hard filter (ask_qty_l1 >= lot_size).
        total_bid_qty: Total pending buy order quantity in the entire order book
            (Dhan buy_quantity). Not the sum of the top 5 levels.
        total_ask_qty: Total pending sell order quantity in the entire order book
            (Dhan sell_quantity). Not the sum of the top 5 levels.
        timestamp: Timezone-aware UTC timestamp of depth capture (optional).
    """

    bid_qty_l1: int
    ask_qty_l1: int
    total_bid_qty: int
    total_ask_qty: int
    timestamp: datetime.datetime | None = None


@typing.runtime_checkable
class DepthSource(typing.Protocol):
    """Protocol for fetching market depth data."""

    async def fetch(
        self, security_id: str, exchange_segment: str = "NSE_FNO"
    ) -> DepthSnapshot | None:
        """Fetch depth snapshot for given security ID and exchange segment.

        Returns None if depth is unavailable, reduced mode is active,
        or the instrument is illiquid.
        """
        ...


class NullDepth:
    """Null depth implementation for reduced mode (e.g. DHAN_DATA_API_KEY unset)."""

    async def fetch(
        self, security_id: str, exchange_segment: str = "NSE_FNO"
    ) -> DepthSnapshot | None:
        """Always returns None to signal reduced mode to the scan."""
        return None
