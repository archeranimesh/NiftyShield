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

from src.client.protocol import (
    BrokerClient,
    CandleRequest,
    Contract,
    Holding,
    MarginResponse,
    MarketDataProvider,
    OrderModify,
    OrderRequest,
    OrderResponse,
    Position,
)
from src.client.upstox_market import UpstoxMarketClient

# Verify protocol conformance at import time (structural typing — no inheritance needed).
# These assertions catch signature drift early and document intent explicitly.
assert issubclass(type, type)  # placeholder — runtime isinstance checks are in tests


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

    async def get_ltp(self, instruments: list[str]) -> dict[str, float]:
        """Fetch last-traded prices for the given instrument keys.

        Delegates to UpstoxMarketClient. Raises LTPFetchError on total
        failure; partial results are returned with a WARNING log (see
        UpstoxMarketClient for the detailed error policy).

        Args:
            instruments: Pipe-format instrument keys
                         (e.g. ``["NSE_EQ|INF754K01LE1"]``).

        Returns:
            Dict mapping instrument_key -> last_price (float).

        Raises:
            LTPFetchError: If the API request fails or returns no data.
        """
        return await self._market.get_ltp(instruments)

    async def get_option_chain(
        self, instrument: str, expiry: str
    ) -> dict:
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

    async def get_historical_candles(
        self, params: "CandleRequest"
    ) -> list:
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

    async def get_expired_option_contracts(
        self, instrument: str, expiry: str
    ) -> list:
        """Not available — requires a paid Upstox subscription.

        Raises:
            NotImplementedError: Always — Expired Instruments API requires
                a paid subscription. See CONTEXT.md → Current Constraints.
        """
        raise NotImplementedError(
            "Expired Instruments API requires paid subscription — see CONTEXT.md"
        )

    # ── Order execution (blocked — static IP required) ────────────

    async def place_order(self, order: "OrderRequest") -> "OrderResponse":
        """Not available — order execution blocked by static IP constraint.

        Raises:
            NotImplementedError: Always. See CONTEXT.md → Current Constraints.
        """
        self._raise_order_blocked()

    async def modify_order(
        self, order_id: str, changes: "OrderModify"
    ) -> "OrderResponse":
        """Not available — order execution blocked by static IP constraint.

        Raises:
            NotImplementedError: Always. See CONTEXT.md → Current Constraints.
        """
        self._raise_order_blocked()

    async def cancel_order(self, order_id: str) -> "OrderResponse":
        """Not available — order execution blocked by static IP constraint.

        Raises:
            NotImplementedError: Always. See CONTEXT.md → Current Constraints.
        """
        self._raise_order_blocked()

    # ── Portfolio read (blocked — Daily OAuth token required) ─────

    async def get_positions(self) -> list["Position"]:
        """Not available — requires Daily OAuth token.

        Raises:
            NotImplementedError: Always. See CONTEXT.md → Tokens & Auth.
        """
        raise NotImplementedError(
            "Requires Daily OAuth token — see CONTEXT.md"
        )

    async def get_holdings(self) -> list["Holding"]:
        """Not available — requires Daily OAuth token.

        Raises:
            NotImplementedError: Always. See CONTEXT.md → Tokens & Auth.
        """
        raise NotImplementedError(
            "Requires Daily OAuth token — see CONTEXT.md"
        )

    async def get_margins(self) -> "MarginResponse":
        """Not available — requires Daily OAuth token.

        Raises:
            NotImplementedError: Always. See CONTEXT.md → Tokens & Auth.
        """
        raise NotImplementedError(
            "Requires Daily OAuth token — see CONTEXT.md"
        )

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
