"""Dhan Market Data client."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

import aiohttp
import structlog

from src.client.exceptions import AuthenticationError, DataFetchError, NotSubscribedError
from src.models.options import OptionChain, OptionChainStrike, OptionLeg

logger = structlog.stdlib.get_logger(__name__)


class Clock(Protocol):
    def time(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...


class RateLimiter(Protocol):
    async def acquire(self) -> None: ...


class SpacingRateLimiter:
    """Enforces a minimum time spacing between requests."""

    def __init__(self, spacing: float, clock: Clock) -> None:
        self._spacing = spacing
        self._clock = clock
        self._last_req = -float("inf")
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = self._clock.time()
            elapsed = now - self._last_req
            if elapsed < self._spacing:
                await self._clock.sleep(self._spacing - elapsed)
            self._last_req = self._clock.time()


def _parse_greek(greeks_dict: dict[str, Any], key: str) -> Decimal | None:
    if key not in greeks_dict:
        return None
    val = greeks_dict[key]
    if val is None:
        return None
    return Decimal(str(val))


def _parse_leg(leg_data: dict[str, Any] | None, strike: Decimal) -> OptionLeg | None:
    if not leg_data:
        return None

    greeks = leg_data.get("greeks", {})
    delta = _parse_greek(greeks, "delta")
    gamma = _parse_greek(greeks, "gamma")
    theta = _parse_greek(greeks, "theta")
    vega = _parse_greek(greeks, "vega")

    # A real zero delta on a deep-OTM strike is a legitimate value.
    # However, Dhan encodes entirely missing/uncomputable Greeks by returning 0 for all four Greeks.
    # If delta, gamma, theta, and vega are ALL exactly 0, we normalise them all to None.
    # This rule is keyed only on Greeks, preserving valid ltp/oi/volume data.
    d0 = Decimal("0")
    if delta == d0 and gamma == d0 and theta == d0 and vega == d0:
        delta = gamma = theta = vega = None

    if "implied_volatility" not in leg_data:
        iv = None
    else:
        iv_raw = leg_data["implied_volatility"]
        iv = None if iv_raw is None else Decimal(str(iv_raw))

    return OptionLeg(
        ltp=Decimal(str(leg_data.get("last_price", 0))),
        bid=Decimal(str(leg_data.get("top_bid_price", 0))),
        ask=Decimal(str(leg_data.get("top_ask_price", 0))),
        oi=int(leg_data.get("oi", 0)),
        volume=int(leg_data.get("volume", 0)),
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        iv=iv,
        strike=strike,
    )


def parse_dhan_option_chain(data: dict[str, Any], expiry: date) -> OptionChain:
    """Parse Dhan option chain response into an OptionChain.

    Data should be the top-level dict containing 'data' key.
    """
    inner = data.get("data", {})
    if not inner:
        return OptionChain(underlying_spot=Decimal("0"), expiry=expiry, strikes={})

    underlying_spot = Decimal(str(inner.get("last_price", 0)))
    oc = inner.get("oc", {})

    strikes = {}
    for strike_str, strike_data in oc.items():
        strike_val = Decimal(strike_str)
        ce_data = strike_data.get("ce")
        pe_data = strike_data.get("pe")

        ce_leg = _parse_leg(ce_data, strike_val) if ce_data else None
        pe_leg = _parse_leg(pe_data, strike_val) if pe_data else None

        strikes[strike_val] = OptionChainStrike(ce=ce_leg, pe=pe_leg)

    return OptionChain(underlying_spot=underlying_spot, expiry=expiry, strikes=strikes)


_DHAN_UNDERLYING_MAP = {"NSE_INDEX|Nifty 50": (13, "IDX_I")}


class DhanMarketClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        rate_limiter: RateLimiter,
        clock: Clock,
        max_retries: int = 3,
    ) -> None:
        self._session = session
        self._rate_limiter = rate_limiter
        self._clock = clock
        self.max_retries = 3

    async def _fetch_with_backoff(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        retries = 0
        while retries <= self.max_retries:
            await self._rate_limiter.acquire()
            try:
                # Explicit timeout on every call
                async with self._session.post(
                    url, json=params, timeout=aiohttp.ClientTimeout(total=10.0)
                ) as resp:
                    if resp.status in (401, 403):
                        raise AuthenticationError("Authentication failed")

                    data = await resp.json()

                    # Dhan custom error codes in JSON
                    err_code = str(data.get("errorCode", data.get("error_code", "")))
                    if err_code == "806":
                        raise NotSubscribedError("Not subscribed to this segment (806)")
                    if err_code == "805":
                        if retries < self.max_retries:
                            retries += 1
                            await self._clock.sleep(1.0 * (2**retries))
                            continue
                        raise DataFetchError("Error 805 after max retries")

                    resp.raise_for_status()
                    return data  # type: ignore
            except asyncio.TimeoutError as e:
                raise DataFetchError("Request timed out") from e
            except aiohttp.ClientResponseError as e:
                if e.status in (401, 403):
                    raise AuthenticationError("Authentication failed") from e
                raise DataFetchError(f"HTTP error {e.status}") from e
            except aiohttp.ClientError as e:
                raise DataFetchError(f"Request failed: {e}") from e

        raise DataFetchError("Max retries exceeded")

    async def get_option_chain(self, underlying: str, expiry: date) -> OptionChain:
        if underlying not in _DHAN_UNDERLYING_MAP:
            raise DataFetchError(f"Unknown underlying for Dhan: {underlying}")
        security_id, segment = _DHAN_UNDERLYING_MAP[underlying]

        url = "https://api.dhan.co/v2/optionchain"
        params = {
            "UnderlyingScrip": security_id,
            "UnderlyingSeg": segment,
            "Expiry": expiry.isoformat(),
        }
        data = await self._fetch_with_backoff(url, params)
        return parse_dhan_option_chain(data, expiry)
