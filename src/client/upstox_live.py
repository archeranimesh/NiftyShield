"""Production BrokerClient implementation backed by Upstox V3 APIs.

Delegates all market data to UpstoxMarketClient (Analytics Token).
Order execution and portfolio read methods raise NotImplementedError
with a reason tied to the current constraint that blocks them.

Known gaps (by design — not bugs)
----------------------------------
Order execution (place/modify/cancel):
    Blocked until a static IP is provisioned. The Upstox API rejects
    order requests from dynamic IPs. All order logic is developed and
    tested against MockBrokerClient; this class is the drop-in replacement
    when the constraint is lifted. See CONTEXT.md → Current Constraints.

Portfolio read (positions/holdings/margins):
    These endpoints use the Daily OAuth token (Algo Trading app), not the
    Analytics Token that powers market data. UpstoxLiveClient currently
    holds only an Analytics Token. A future refactor will accept both tokens
    and wire up the portfolio read methods. Until then they raise
    NotImplementedError. See CONTEXT.md → Tokens & Auth.

Expired instruments:
    The Expired Instruments API requires a paid Upstox subscription
    (not yet active). Raises NotImplementedError until the subscription
    is enabled. See CONTEXT.md → Current Constraints.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import requests
import structlog

from src.client.exceptions import AuthenticationError, DataFetchError
from src.client.protocol import (
    CandleRequest,
    Holding,
    MarginInstrument,
    MarginResponse,
    OrderModify,
    OrderMarginResponse,
    OrderRequest,
    OrderResponse,
    Position,
)
from src.client.upstox_market import UpstoxMarketClient
from src.config import settings

logger = structlog.stdlib.get_logger(__name__)

V2_MARGIN_URL = "https://api.upstox.com/v2/charges/margin"
MAX_MARGIN_INSTRUMENTS_PER_REQUEST = 20


class UpstoxLiveClient:
    """Production BrokerClient implementation backed by Upstox V3 APIs.

    Wraps UpstoxMarketClient for all market data methods. Order execution,
    portfolio read, and expired instruments methods raise NotImplementedError
    until their respective constraints are resolved (see module docstring).

    Args:
        token: Analytics Token. Falls back to UPSTOX_ANALYTICS_TOKEN env var.

    Example::

        client = UpstoxLiveClient()
        prices = await client.get_ltp(["NSE_EQ|INF754K01LE1"])
    """

    def __init__(self, token: str | None = None) -> None:
        """Initialise with an Analytics Token.

        Args:
            token: Upstox Analytics Token. Falls back to the
                   UPSTOX_ANALYTICS_TOKEN env var when omitted.
        """
        self._market = UpstoxMarketClient(token=token)

    # ── MarketDataProvider surface (working today) ───────────────

    async def get_ltp(self, instruments: list[str]) -> dict[str, Decimal]:
        """Fetch last-traded prices for the given instrument keys.

        Delegates to UpstoxMarketClient. Raises LTPFetchError on total
        failure; partial results are returned with a WARNING log (see
        UpstoxMarketClient for the detailed error policy).

        Args:
            instruments: Pipe-format instrument keys
                         (e.g. ``["NSE_EQ|INF754K01LE1"]``).

        Returns:
            Dict mapping instrument_key -> last_price (Decimal).

        Raises:
            LTPFetchError: If the API request fails or returns no data.
        """
        return await self._market.get_ltp(instruments)

    async def get_option_chain(self, instrument: str, expiry: str) -> dict:
        """Fetch option chain for an underlying + expiry date.

        Delegates to UpstoxMarketClient.

        Args:
            instrument: Underlying key (e.g. ``"NSE_INDEX|Nifty 50"``).
            expiry: Expiry date as ``YYYY-MM-DD``.

        Returns:
            Raw option chain response dict (Upstox V2 schema).

        Raises:
            DataFetchError: If the API request fails.
        """
        return await self._market.get_option_chain(instrument, expiry)

    # ── Not yet implemented (constraints documented above) ────────

    async def get_historical_candles(self, params: CandleRequest) -> list:
        """Not yet implemented.

        Raises:
            NotImplementedError: Always — historical candles via Upstox API
                are not yet wired up in UpstoxMarketClient. Add a sync
                fetcher there first, then delegate here.
        """
        raise NotImplementedError(
            "get_historical_candles: not yet implemented in UpstoxLiveClient. "
            "Add a sync fetcher to UpstoxMarketClient first."
        )

    async def get_expired_option_contracts(self, instrument: str, expiry: str) -> list:
        """Not available — requires a paid Upstox subscription.

        Raises:
            NotImplementedError: Always — Expired Instruments API requires
                a paid subscription. See CONTEXT.md → Current Constraints.
        """
        raise NotImplementedError(
            "Expired Instruments API requires paid subscription — see CONTEXT.md"
        )

    # ── Order execution (blocked — static IP required) ────────────

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """Not available — order execution blocked by static IP constraint.

        Raises:
            NotImplementedError: Always. See CONTEXT.md → Current Constraints.
        """
        self._raise_order_blocked()

    async def modify_order(self, order_id: str, changes: OrderModify) -> OrderResponse:
        """Not available — order execution blocked by static IP constraint.

        Raises:
            NotImplementedError: Always. See CONTEXT.md → Current Constraints.
        """
        self._raise_order_blocked()

    async def cancel_order(self, order_id: str) -> OrderResponse:
        """Not available — order execution blocked by static IP constraint.

        Raises:
            NotImplementedError: Always. See CONTEXT.md → Current Constraints.
        """
        self._raise_order_blocked()

    # ── Portfolio read (blocked — Daily OAuth token required) ─────

    async def get_positions(self) -> list[Position]:
        """Not available — requires Daily OAuth token.

        Raises:
            NotImplementedError: Always. See CONTEXT.md → Tokens & Auth.
        """
        raise NotImplementedError("Requires Daily OAuth token — see CONTEXT.md")

    async def get_holdings(self) -> list[Holding]:
        """Not available — requires Daily OAuth token.

        Raises:
            NotImplementedError: Always. See CONTEXT.md → Tokens & Auth.
        """
        raise NotImplementedError("Requires Daily OAuth token — see CONTEXT.md")

    async def get_margins(self) -> MarginResponse:
        """Not available — requires Daily OAuth token.

        Raises:
            NotImplementedError: Always. See CONTEXT.md → Tokens & Auth.
        """
        raise NotImplementedError("Requires Daily OAuth token — see CONTEXT.md")

    # ── Order margin calculator (Daily OAuth token — reads settings directly) ──
    #
    # Unlike the other Daily-OAuth-gated methods above, this one is wired: the
    # margin-calculator endpoint (POST /v2/charges/margin) doesn't touch the
    # positions/holdings surface that's still pending a constructor refactor
    # (see module docstring), so it reads UPSTOX_ACCESS_TOKEN from settings
    # directly rather than waiting on that broader change. Scope: IC margin
    # capture at paper-trade entry only — see DECISIONS.md.

    async def get_order_margin(
        self, instruments: list[MarginInstrument]
    ) -> OrderMarginResponse:
        """Compute required/final margin for a basket of not-yet-placed orders.

        Args:
            instruments: List of ``{instrument_key, quantity, transaction_type,
                product}`` dicts. Max 20 per call (Upstox limit) — callers must
                pre-batch larger baskets.

        Returns:
            Parsed ``data`` object from the Upstox response, e.g.
            ``{"required_margin": ..., "final_margin": ..., "margins": [...]}``.

        Raises:
            ValueError: If ``instruments`` is empty or exceeds the 20-instrument
                limit.
            AuthenticationError: If UPSTOX_ACCESS_TOKEN is missing or the API
                rejects it (401/403).
            DataFetchError: If the request fails for any other reason, or the
                response is missing the expected ``data`` object.
        """
        if not instruments:
            raise ValueError("get_order_margin: instruments must not be empty")
        if len(instruments) > MAX_MARGIN_INSTRUMENTS_PER_REQUEST:
            raise ValueError(
                f"get_order_margin: max {MAX_MARGIN_INSTRUMENTS_PER_REQUEST} "
                f"instruments per call, got {len(instruments)}"
            )
        return await asyncio.to_thread(self._get_order_margin_sync, instruments)

    def _get_order_margin_sync(
        self, instruments: list[MarginInstrument]
    ) -> OrderMarginResponse:
        """Sync implementation of get_order_margin — see that method for contract."""
        token = settings.upstox_access_token
        if not token:
            raise AuthenticationError(
                "get_order_margin: UPSTOX_ACCESS_TOKEN not set — "
                "run: python -m src.auth.login"
            )

        try:
            resp = requests.post(
                V2_MARGIN_URL,
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"instruments": instruments},
                timeout=15,
            )
        except requests.RequestException as exc:
            raise DataFetchError(f"get_order_margin: request failed: {exc}") from exc

        if resp.status_code in (401, 403):
            raise AuthenticationError(
                f"get_order_margin: auth rejected (status={resp.status_code}) — "
                "token likely expired, run: python -m src.auth.login"
            )
        if not resp.ok:
            raise DataFetchError(
                f"get_order_margin: HTTP {resp.status_code}: {resp.text[:500]}"
            )

        body: dict[str, Any] = resp.json()
        data = body.get("data")
        if not isinstance(data, dict):
            raise DataFetchError(f"get_order_margin: unexpected response shape: {body!r}")
        return data

    # ── Private helpers ───────────────────────────────────────────

    def _raise_order_blocked(self) -> None:
        """Raise NotImplementedError for all order execution methods.

        Centralises the error message so the three order methods stay
        thin and the constraint reason is updated in one place.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "Order execution requires a static IP — see CONTEXT.md → Current Constraints"
        )
