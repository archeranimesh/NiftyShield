"""Upstox V3 Market Data client.

Uses the Market Quote V3 LTP endpoint with an Analytics Token.
Implements the MarketDataProvider protocol expected by PortfolioTracker.

Key mapping: We send pipe-format keys (NSE_EQ|INF754K01LE1) but the
response uses colon-format keys (NSE_EQ:EBBETF0431). The response's
instrument_token field gives back the pipe-format key for mapping.

Error policy:
- A total HTTP failure or empty response raises LTPFetchError — callers
  must not proceed with zero/stale prices.
- Partial failures (some instruments resolve, others don't) are logged at
  WARNING and the partial result is returned. Callers check for missing keys.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date
from decimal import Decimal
from typing import Any

import requests

from src.client.exceptions import DataFetchError, LTPFetchError
from src.config import settings
from src.models.options import OptionChain, OptionChainStrike, OptionLeg

logger = logging.getLogger(__name__)

V3_LTP_URL = "https://api.upstox.com/v3/market-quote/ltp"
V3_OHLC_URL = "https://api.upstox.com/v3/market-quote/ohlc"
V2_OPTION_CHAIN_URL = "https://api.upstox.com/v2/option/chain"

MAX_INSTRUMENTS_PER_REQUEST = 500


def _remap_response(data: dict[str, Any]) -> dict[str, Any]:
    """Remap colon-format response keys to pipe-format using instrument_token."""
    remapped: dict[str, Any] = {}
    for _resp_key, value in data.items():
        pipe_key = value.get("instrument_token", "")
        if pipe_key:
            remapped[pipe_key] = value
    return remapped


class UpstoxMarketClient:
    """Sync client for Upstox Market Quote V3 API.

    Provides both sync methods (get_ltp_sync) and async wrappers
    (get_ltp) that satisfy the MarketDataProvider protocol.
    """

    def __init__(self, token: str | None = None) -> None:
        """Initialize with an Analytics Token.

        Args:
            token: Upstox Analytics Token. Falls back to
                   UPSTOX_ANALYTICS_TOKEN env var if not provided.
        """
        self.token = token or settings.upstox_analytics_token or ""
        if not self.token:
            raise ValueError(
                "No token provided. Set UPSTOX_ANALYTICS_TOKEN in .env "
                "or pass token= to constructor."
            )
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            }
        )

    # ── Sync methods (used directly by CLI scripts) ──────────────

    def get_ltp_sync(self, instruments: list[str]) -> dict[str, Decimal]:
        """Fetch LTP for a list of instrument keys.

        Args:
            instruments: List of pipe-format keys (e.g. 'NSE_EQ|INF754K01LE1').

        Returns:
            Dict mapping instrument_key -> last_price.
            Keys that fail to resolve are omitted silently.
        """
        if not instruments:
            return {}

        results: dict[str, Decimal] = {}

        # Batch into chunks of 500
        for i in range(0, len(instruments), MAX_INSTRUMENTS_PER_REQUEST):
            batch = instruments[i : i + MAX_INSTRUMENTS_PER_REQUEST]
            batch_results = self._fetch_ltp_batch(batch)
            results.update(batch_results)

        return results

    def get_ohlc_sync(
        self, instruments: list[str], interval: str = "1d"
    ) -> dict[str, dict[str, Any]]:
        """Fetch OHLC data for a list of instrument keys.

        Args:
            instruments: List of pipe-format keys.
            interval: Candle interval ('1d', 'I1', 'I30').

        Returns:
            Dict mapping instrument_key -> OHLC data dict.

        Raises:
            DataFetchError: If the HTTP request fails.
        """
        if not instruments:
            return {}

        keys_param = ",".join(instruments)
        try:
            t0 = time.perf_counter()
            resp = self._session.get(
                V3_OHLC_URL,
                params={"instrument_key": keys_param, "interval": interval},
                timeout=10,
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "upstox.api_call endpoint=%s status_code=%s latency_ms=%s",
                V3_OHLC_URL,
                resp.status_code,
                latency_ms,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return _remap_response(data)
        except requests.RequestException as e:
            raise DataFetchError(f"OHLC fetch failed: {e}") from e

    def get_option_chain_sync(self, instrument: str, expiry: str) -> list[dict[str, Any]]:
        """Fetch option chain for an underlying + expiry.

        Args:
            instrument: Underlying instrument key (e.g. 'NSE_INDEX|Nifty 50').
            expiry: Expiry date as YYYY-MM-DD.

        Returns:
            Raw option chain response as a list of strike dicts.

        Raises:
            DataFetchError: If the HTTP request fails.
        """
        try:
            t0 = time.perf_counter()
            resp = self._session.get(
                V2_OPTION_CHAIN_URL,
                params={"instrument_key": instrument, "expiry_date": expiry},
                timeout=10,
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "upstox.api_call endpoint=%s status_code=%s latency_ms=%s",
                V2_OPTION_CHAIN_URL,
                resp.status_code,
                latency_ms,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return data if isinstance(data, list) else []
        except requests.RequestException as e:
            raise DataFetchError(f"Option chain fetch failed: {e}") from e

    # ── Async wrappers (satisfy MarketDataProvider protocol) ─────

    async def get_ltp(self, instruments: list[str]) -> dict[str, Decimal]:
        """Async wrapper around get_ltp_sync."""
        return await asyncio.to_thread(self.get_ltp_sync, instruments)

    async def get_option_chain(self, instrument: str, expiry: str) -> list[dict[str, Any]]:
        """Async wrapper around get_option_chain_sync."""
        return await asyncio.to_thread(self.get_option_chain_sync, instrument, expiry)

    # ── Internal helpers ─────────────────────────────────────────

    def _fetch_ltp_batch(self, instruments: list[str]) -> dict[str, Decimal]:
        """Fetch LTP for a single batch of up to 500 instruments.

        Raises:
            LTPFetchError: If the HTTP request fails or the response contains
                no usable price data. Callers must not proceed with zero prices.
        """
        keys_param = ",".join(instruments)
        try:
            t0 = time.perf_counter()
            resp = self._session.get(
                V3_LTP_URL,
                params={"instrument_key": keys_param},
                timeout=10,
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "upstox.api_call endpoint=%s status_code=%s latency_ms=%s",
                V3_LTP_URL,
                resp.status_code,
                latency_ms,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise LTPFetchError(f"LTP batch request failed: {e}") from e

        data = resp.json().get("data", {})
        if not data:
            raise LTPFetchError(f"LTP batch returned empty data for {len(instruments)} instruments")

        results: dict[str, Decimal] = {}
        for _resp_key, quote in data.items():
            pipe_key = quote.get("instrument_token", "")
            price = quote.get("last_price")
            if pipe_key and price is not None:
                results[pipe_key] = Decimal(str(price))

        if not results:
            raise LTPFetchError(
                "LTP batch response had data but no resolvable instrument_token fields"
            )

        return results

    # ── Response remapping (module-level: _remap_response) ──


# ── Option chain parsers ─────────────────────────────────────────────────────


def _safe_decimal(val: Any) -> Decimal:
    """Coerce a price value to Decimal, returning Decimal("0") on any failure.

    Use for price fields (ltp, bid, ask) where Decimal("0") is a safe sentinel.
    For Greek fields (delta, gamma, theta, vega, iv) use _safe_decimal_greek
    so that missing data is represented as None rather than silently zeroed.

    Args:
        val: Raw value from the broker response (float, str, None, …).

    Returns:
        Decimal representation of val, or Decimal("0") if conversion fails.
    """
    if val is None:
        return Decimal("0")
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal("0")


def _safe_decimal_greek(val: Any) -> Decimal | None:
    """Coerce a Greek value to Decimal | None.

    Returns None when the value is absent or non-numeric so callers can
    distinguish "Greek not available" from a genuine zero (e.g. delta exactly
    0.0 on a far-OTM strike vs. a stale/missing API field).

    Args:
        val: Raw value from the broker response (float, str, None, …).

    Returns:
        Decimal representation of val, or None if conversion fails or val is None.
    """
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except Exception:
        logger.warning("Non-numeric Greek value %r — storing as None", val)
        return None


def _parse_option_leg(options_dict: dict[str, Any], strike: Decimal) -> OptionLeg | None:
    """Parse one side (CE or PE) of a strike entry into an OptionLeg.

    Returns None when either the ``market_data`` or ``option_greeks``
    sub-dicts are missing or empty — callers treat that as an absent leg.

    Args:
        options_dict: The ``call_options`` or ``put_options`` dict from the
            Upstox option chain response.
        strike: Strike price as Decimal (already converted from the parent
            strike entry).

    Returns:
        Populated OptionLeg, or None if data is absent.
    """
    market_data = options_dict.get("market_data") or {}
    option_greeks = options_dict.get("option_greeks") or {}

    if not market_data and not option_greeks:
        return None

    try:
        oi = int(float(market_data.get("oi") or 0))
    except (TypeError, ValueError):
        oi = 0

    try:
        volume = int(float(market_data.get("volume") or 0))
    except (TypeError, ValueError):
        volume = 0

    return OptionLeg(
        ltp=_safe_decimal(market_data.get("ltp")),
        bid=_safe_decimal(market_data.get("bid_price")),
        ask=_safe_decimal(market_data.get("ask_price")),
        oi=oi,
        volume=volume,
        delta=_safe_decimal_greek(option_greeks.get("delta")),
        gamma=_safe_decimal_greek(option_greeks.get("gamma")),
        theta=_safe_decimal_greek(option_greeks.get("theta")),
        vega=_safe_decimal_greek(option_greeks.get("vega")),
        iv=_safe_decimal_greek(option_greeks.get("iv")),
        strike=strike,
    )


def parse_upstox_option_chain(data: list[dict[str, Any]]) -> OptionChain:
    """Parse the Upstox option chain response into a source-agnostic OptionChain.

    Accepts the raw list returned by ``get_option_chain_sync`` (the value of
    ``resp.json()["data"]``).  Returns an empty-strikes OptionChain when data
    is empty or not a list — callers need not guard against None.

    Field mapping (Upstox → OptionLeg):
        market_data.ltp          → ltp
        market_data.bid_price    → bid
        market_data.ask_price    → ask
        market_data.oi           → oi  (int cast via int(float(...)))
        market_data.volume       → volume
        option_greeks.delta      → delta
        option_greeks.gamma      → gamma
        option_greeks.theta      → theta
        option_greeks.vega       → vega
        option_greeks.iv         → iv
        option_greeks.pop        → ignored (not a standard Greek)

    Args:
        data: List of strike dicts from the Upstox V2 option chain endpoint.

    Returns:
        Populated OptionChain.  ``strikes`` may be empty if data is empty or
        every strike entry is malformed.
    """
    _EMPTY_EXPIRY = date(1970, 1, 1)
    _EMPTY = OptionChain(
        underlying_spot=Decimal("0"),
        expiry=_EMPTY_EXPIRY,
        strikes={},
    )

    if not data or not isinstance(data, list):
        return _EMPTY

    first = data[0]
    try:
        underlying_spot = Decimal(str(first.get("underlying_spot_price", 0)))
    except Exception:
        underlying_spot = Decimal("0")

    try:
        expiry = date.fromisoformat(first["expiry"])
    except (KeyError, ValueError, TypeError):
        expiry = _EMPTY_EXPIRY

    strikes: dict[Decimal, OptionChainStrike] = {}
    for entry in data:
        try:
            raw_strike = entry.get("strike_price")
            if raw_strike is None:
                continue
            strike_key = Decimal(str(raw_strike))
        except Exception:
            continue

        ce = _parse_option_leg(entry.get("call_options") or {}, strike_key)
        pe = _parse_option_leg(entry.get("put_options") or {}, strike_key)
        strikes[strike_key] = OptionChainStrike(ce=ce, pe=pe)

    return OptionChain(
        underlying_spot=underlying_spot,
        expiry=expiry,
        strikes=strikes,
    )
