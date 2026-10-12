"""Dhan L2 Market Depth adapter."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiohttp
import structlog

from src.client.dhan_market import Clock, RateLimiter
from src.client.exceptions import AuthenticationError, DataFetchError, RateLimitError
from src.gamma.depth import DepthSnapshot

logger = structlog.stdlib.get_logger(__name__)


def parse_dhan_depth_quote(
    data: dict[str, Any], security_id: str, exchange_segment: str = "NSE_FNO"
) -> DepthSnapshot | None:
    """Parse Dhan Market Quote response for a security ID into DepthSnapshot.

    Expected JSON shape per Dhan docs:
      data.<SEGMENT>.<security_id>.depth...
      buy_quantity: total buy order book quantity
      sell_quantity: total sell order book quantity
      depth.buy[0].quantity: Level 1 best bid quantity
      depth.sell[0].quantity: Level 1 best ask quantity

    Returns None if:
      - response status != "success"
      - segment or security_id is not in data
      - depth is missing, empty, or all-zero quantities (illiquid/no usable depth)
    """
    if data.get("status") != "success":
        return None

    data_section = data.get("data")
    if not isinstance(data_section, dict):
        return None

    segment_section = data_section.get(exchange_segment)
    if not isinstance(segment_section, dict):
        return None

    instrument_data = segment_section.get(str(security_id))
    if not isinstance(instrument_data, dict):
        return None

    depth_data = instrument_data.get("depth")
    if not isinstance(depth_data, dict):
        return None

    buy_levels = depth_data.get("buy")
    sell_levels = depth_data.get("sell")
    if not isinstance(buy_levels, list) or not isinstance(sell_levels, list):
        return None

    if not buy_levels or not sell_levels:
        return None

    bid_qty_l1 = int(buy_levels[0].get("quantity", 0))
    ask_qty_l1 = int(sell_levels[0].get("quantity", 0))
    total_bid_qty = int(instrument_data.get("buy_quantity", 0))
    total_ask_qty = int(instrument_data.get("sell_quantity", 0))

    # All-zero depth indicates no usable liquidity/depth
    if bid_qty_l1 == 0 and ask_qty_l1 == 0 and total_bid_qty == 0 and total_ask_qty == 0:
        return None

    return DepthSnapshot(
        bid_qty_l1=bid_qty_l1,
        ask_qty_l1=ask_qty_l1,
        total_bid_qty=total_bid_qty,
        total_ask_qty=total_ask_qty,
        timestamp=datetime.now(timezone.utc),
    )


class DhanDepthAdapter:
    """Adapter fetching L2 depth quotes from Dhan Market Quote API.

    Satisfies the DepthSource Protocol structurally.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        rate_limiter: RateLimiter,
        clock: Clock,
        access_token: str,
        client_id: str,
        base_url: str = "https://api.dhan.co",
        max_retries: int = 3,
    ) -> None:
        self._session = session
        self._rate_limiter = rate_limiter
        self._clock = clock
        self._access_token = access_token
        self._client_id = client_id
        self._base_url = base_url.rstrip("/")
        self.max_retries = max_retries

    async def _fetch_with_backoff(self, url: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Fetch quote with retry and error mapping.

        Error precedence:
          1. 401 / 403 -> AuthenticationError
          2. 429 -> RateLimitError
          3. Timeout / connection / client errors -> DataFetchError
          4. Other non-200 responses -> None
        """
        retries = 0
        while retries <= self.max_retries:
            await self._rate_limiter.acquire()
            try:
                headers = {
                    "access-token": self._access_token,
                    "client-id": self._client_id,
                    "Content-Type": "application/json",
                }
                async with self._session.post(
                    url,
                    json=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5.0),
                ) as resp:
                    if resp.status in (401, 403):
                        raise AuthenticationError(f"Authentication failed: HTTP {resp.status}")
                    if resp.status == 429:
                        raise RateLimitError("Rate limit exceeded: HTTP 429")
                    if resp.status != 200:
                        logger.warning("dhan_depth_non_200", status=resp.status, url=url)
                        return None

                    data = await resp.json()
                    return data  # type: ignore[no-any-return]

            except asyncio.TimeoutError as e:
                if retries < self.max_retries:
                    retries += 1
                    await self._clock.sleep(1.0 * (2**retries))
                    continue
                raise DataFetchError("Request timed out") from e
            except aiohttp.ClientResponseError as e:
                if e.status in (401, 403):
                    raise AuthenticationError(f"Authentication failed: HTTP {e.status}") from e
                if e.status == 429:
                    raise RateLimitError("Rate limit exceeded: HTTP 429") from e
                logger.warning("dhan_depth_http_error", status=e.status)
                return None
            except aiohttp.ClientError as e:
                if retries < self.max_retries:
                    retries += 1
                    await self._clock.sleep(1.0 * (2**retries))
                    continue
                raise DataFetchError(f"Request failed: {e}") from e

        raise DataFetchError("Max retries exceeded")

    async def fetch(
        self, security_id: str, exchange_segment: str = "NSE_FNO"
    ) -> DepthSnapshot | None:
        """Fetch market depth snapshot for given security ID.

        Returns None if security_id is non-numeric, or if depth data is empty/absent.
        """
        try:
            sec_id_int = int(security_id)
        except (ValueError, TypeError):
            logger.warning("dhan_depth_invalid_security_id", security_id=security_id)
            return None

        url = f"{self._base_url}/v2/marketfeed/quote"
        payload = {exchange_segment: [sec_id_int]}

        data = await self._fetch_with_backoff(url, payload)
        if not data or not isinstance(data, dict):
            return None

        return parse_dhan_depth_quote(data, str(sec_id_int), exchange_segment)
