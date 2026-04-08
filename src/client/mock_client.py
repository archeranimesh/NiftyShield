"""Stateful offline broker client for unit tests and CI.

Purpose
-------
MockBrokerClient implements the full BrokerClient protocol without any network
dependency. It is the *only* implementation to use for order-execution tests
until the static IP constraint is resolved (see CONTEXT.md → Current Constraints).

Design principles
-----------------
- Internal state (orders, positions, margin) is mutable so that full workflows
  can be tested end-to-end offline — place an order, check positions, cancel.
- ``simulate_error`` is one-shot: the injected exception fires once on the next
  call to the named method, then the queue is cleared. The second call succeeds.
- Fixture loading is graceful: a missing file logs a WARNING and returns an
  appropriate empty value. The test never crashes due to a missing fixture.
- All BrokerClient methods are async to match the protocol. Tests that call them
  should use ``await`` inside an ``asyncio.run()`` or with ``pytest-asyncio``.

Usage in tests
--------------
::

    from pathlib import Path
    from src.client.mock_client import MockBrokerClient

    FIXTURES = Path(__file__).parent.parent / "fixtures" / "responses"

    client = MockBrokerClient(fixtures_dir=FIXTURES)
    client.set_price("NSE_FO|12345", 150.0)
    client.set_margin(1_000_000.0)

    order = {"instrument_key": "NSE_FO|12345", "quantity": 50,
             "price": 150.0, "direction": "SELL"}
    result = asyncio.run(client.place_order(order))
    assert result["status"] == "complete"
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.client.exceptions import InsufficientMarginError, OrderRejectedError

logger = logging.getLogger(__name__)

# Sentinel used to distinguish "not set" from None
_MISSING = object()


class MockBrokerClient:
    """Offline stateful broker client for unit tests and CI.

    Args:
        fixtures_dir: Root directory for JSON fixtures (``tests/fixtures/responses``).
            May be ``None`` — methods that load fixtures will log a WARNING and
            return empty values instead.
        initial_margin: Starting available margin in rupees. Defaults to 500 000.
    """

    def __init__(
        self,
        fixtures_dir: Path | None = None,
        initial_margin: float = 500_000.0,
    ) -> None:
        self._fixtures_dir: Path | None = fixtures_dir
        self._margin_available: Decimal = Decimal(str(initial_margin))
        self._orders: list[dict] = []
        self._positions: list[dict] = []
        self._price_map: dict[str, float] = {}
        self._error_queue: dict[str, Exception] = {}

    # ------------------------------------------------------------------
    # Test-setup helpers — called by test code before ``act``
    # ------------------------------------------------------------------

    def set_price(self, instrument_key: str, price: float) -> None:
        """Populate ``_price_map`` with a known price for an instrument.

        Args:
            instrument_key: Upstox instrument key (e.g. ``"NSE_FO|37810"``).
            price: Last traded price to return from ``get_ltp``.
        """
        self._price_map[instrument_key] = price

    def set_margin(self, amount: float) -> None:
        """Override available margin.

        Args:
            amount: New available margin in rupees.
        """
        self._margin_available = Decimal(str(amount))

    def simulate_error(self, method_name: str, exc: Exception) -> None:
        """Queue a one-shot exception for the named method.

        The exception fires on the very next call to ``method_name``, after
        which it is removed from the queue. All subsequent calls succeed normally.

        Args:
            method_name: Name of a BrokerClient method (e.g. ``"place_order"``).
            exc: Exception instance to raise.
        """
        self._error_queue[method_name] = exc

    def reset(self) -> None:
        """Clear all orders, positions, and error queues; restore initial state.

        Margin is reset to 500 000 unless ``set_margin`` is called again after
        ``reset``.  Fixtures directory and price map are preserved.
        """
        self._margin_available = Decimal("500000.0")
        self._orders = []
        self._positions = []
        self._error_queue = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _raise_if_queued(self, method_name: str) -> None:
        """Raise and clear the queued error for ``method_name``, if any."""
        exc = self._error_queue.pop(method_name, None)
        if exc is not None:
            raise exc

    def _load_fixture(self, relative_path: str) -> Any:
        """Load a JSON fixture file relative to ``fixtures_dir``.

        Args:
            relative_path: Path under ``fixtures_dir``, e.g.
                ``"option_chain/nifty_chain_2026-04-07.json"``.

        Returns:
            Parsed JSON as a Python object, or ``None`` if the file is missing
            or ``fixtures_dir`` was not provided.
        """
        if self._fixtures_dir is None:
            logger.warning(
                "MockBrokerClient: fixtures_dir not set; cannot load '%s'",
                relative_path,
            )
            return None
        path = self._fixtures_dir / relative_path
        if not path.exists():
            logger.warning(
                "MockBrokerClient: fixture not found: %s",
                path,
            )
            return None
        with path.open() as fh:
            return json.load(fh)

    # ------------------------------------------------------------------
    # BrokerClient — MarketDataProvider surface
    # ------------------------------------------------------------------

    async def get_ltp(self, instruments: list[str]) -> dict[str, float]:
        """Return LTPs from the internal price map.

        Unknown instrument keys are silently omitted from the result dict,
        matching the live client contract.

        Args:
            instruments: List of Upstox instrument keys.

        Returns:
            Dict of ``{instrument_key: price}`` for keys present in
            ``_price_map``.
        """
        self._raise_if_queued("get_ltp")
        return {k: self._price_map[k] for k in instruments if k in self._price_map}

    async def get_option_chain(self, instrument: str, expiry: str) -> dict:
        """Load an option chain fixture from disk.

        Fixture path: ``option_chain/{instrument}_{expiry}.json`` where
        ``instrument`` has the pipe (``|``) replaced with ``_`` to produce a
        safe filename (e.g. ``NSE_INDEX_Nifty 50_2026-04-07.json``).

        Args:
            instrument: Upstox instrument key (e.g. ``"NSE_INDEX|Nifty 50"``).
            expiry: Expiry date string (e.g. ``"2026-04-07"``).

        Returns:
            Full fixture dict on success; empty dict if fixture is missing.
        """
        self._raise_if_queued("get_option_chain")
        safe_instrument = instrument.replace("|", "_").replace(" ", "_")
        path = f"option_chain/{safe_instrument}_{expiry}.json"
        data = self._load_fixture(path)
        if data is None:
            return {}
        return data

    # ------------------------------------------------------------------
    # BrokerClient — OrderExecutor surface
    # ------------------------------------------------------------------

    async def place_order(self, order: dict) -> dict:
        """Place an order, update internal state, return a completion response.

        Validates:
          - ``price * quantity > _margin_available`` → raises
            ``InsufficientMarginError``.
          - Otherwise deducts ``price * quantity * 0.1`` as a simple NRML
            margin proxy.

        Args:
            order: Dict with keys ``instrument_key``, ``quantity``, ``price``,
                ``direction`` (``"BUY"`` or ``"SELL"``).

        Returns:
            Dict with ``order_id`` (UUID4 str) and ``status`` (``"complete"``).

        Raises:
            InsufficientMarginError: When the notional value exceeds available margin.
        """
        self._raise_if_queued("place_order")
        price = Decimal(str(order.get("price", 0)))
        quantity = Decimal(str(order.get("quantity", 0)))
        notional = price * quantity
        if notional > self._margin_available:
            raise InsufficientMarginError(
                f"Mock: insufficient margin. Required ≥{notional}, "
                f"available {self._margin_available}"
            )
        margin_blocked = notional * Decimal("0.1")
        self._margin_available -= margin_blocked
        order_id = str(uuid4())
        response = {"order_id": order_id, "status": "complete"}
        self._orders.append({**order, "order_id": order_id, "status": "complete"})
        self._positions.append(
            {
                "instrument_key": order.get("instrument_key"),
                "quantity": int(quantity),
                "direction": order.get("direction"),
                "entry_price": float(price),
                "order_id": order_id,
            }
        )
        return response

    async def modify_order(self, order_id: str, changes: dict) -> dict:
        """Apply ``changes`` to an existing order in ``_orders``.

        Args:
            order_id: UUID string returned by ``place_order``.
            changes: Dict of fields to update (e.g. ``{"price": 155.0}``).

        Returns:
            Updated order dict.

        Raises:
            OrderRejectedError: When ``order_id`` is not found.
        """
        self._raise_if_queued("modify_order")
        for order in self._orders:
            if order.get("order_id") == order_id:
                order.update(changes)
                return {**order}
        raise OrderRejectedError(f"Mock: order not found: {order_id}")

    async def cancel_order(self, order_id: str) -> dict:
        """Mark an order as ``cancelled`` in ``_orders``.

        Args:
            order_id: UUID string returned by ``place_order``.

        Returns:
            Dict with ``order_id`` and ``status`` (``"cancelled"``).

        Raises:
            OrderRejectedError: When ``order_id`` is not found.
        """
        self._raise_if_queued("cancel_order")
        for order in self._orders:
            if order.get("order_id") == order_id:
                order["status"] = "cancelled"
                return {"order_id": order_id, "status": "cancelled"}
        raise OrderRejectedError(f"Mock: order not found: {order_id}")

    # ------------------------------------------------------------------
    # BrokerClient — PortfolioReader surface
    # ------------------------------------------------------------------

    async def get_positions(self) -> list[dict]:
        """Return a copy of current positions accumulated from ``place_order`` calls.

        Returns:
            List of position dicts.
        """
        self._raise_if_queued("get_positions")
        return list(self._positions)

    async def get_holdings(self) -> list:
        """Return an empty list — equity leg tracking not yet simulated.

        Returns:
            Empty list.
        """
        self._raise_if_queued("get_holdings")
        return []

    async def get_margins(self) -> dict:
        """Return current available margin.

        Returns:
            Dict with ``available_margin`` as a float.
        """
        self._raise_if_queued("get_margins")
        return {"available_margin": float(self._margin_available)}

    # ------------------------------------------------------------------
    # BrokerClient — additional methods
    # ------------------------------------------------------------------

    async def get_historical_candles(self, params: Any) -> list:
        """Load candle data from a fixture file or return an empty list.

        Fixture path is built from ``params`` if it is a dict with
        ``instrument_key`` and ``interval``; otherwise falls back to
        ``historical_candles/default.json``.

        Args:
            params: Dict (or Any) describing the candle request.

        Returns:
            List of candle dicts, or ``[]`` if no fixture is found.
        """
        self._raise_if_queued("get_historical_candles")
        if isinstance(params, dict):
            key = params.get("instrument_key", "default")
            interval = params.get("interval", "day")
            safe_key = str(key).replace("|", "_").replace(" ", "_")
            fixture_path = f"historical_candles/{safe_key}_{interval}.json"
        else:
            fixture_path = "historical_candles/default.json"
        data = self._load_fixture(fixture_path)
        if data is None:
            return []
        if isinstance(data, list):
            return data
        # Fixtures recorded from the real API wrap candles under a ``data`` key.
        return data.get("data", data.get("candles", []))

    async def get_expired_option_contracts(
        self, instrument: str, expiry: str
    ) -> list:
        """Return an empty list — expired instruments API not yet available.

        Args:
            instrument: Upstox instrument key.
            expiry: Expiry date string.

        Returns:
            Empty list always (paid subscription blocked).
        """
        self._raise_if_queued("get_expired_option_contracts")
        return []
