"""Broker and streaming protocol definitions.

Purpose
-------
Single source of truth for all interface contracts in NiftyShield. Every module
that talks to a broker depends on these protocols — never on a concrete class.
This keeps the live Upstox client, the sandbox client, and the offline
MockBrokerClient interchangeable at the composition root (src/client/factory.py).

Sub-protocol rationale (ISP)
-----------------------------
Three narrow sub-protocols model exactly what each consumer needs:

  MarketDataProvider — portfolio tracker, signal generation
  OrderExecutor      — execution module
  PortfolioReader    — position monitoring and margin checks

A class that implements every method in BrokerClient automatically satisfies all
three sub-protocols via Python's structural (duck-type) checking. BrokerClient is
kept flat — no Protocol inheritance — so the full method list is readable in one
place.

Stub type aliases
-----------------
src/models/ does not exist yet. Until it is built, each model name is aliased to
Any so that protocol.py has zero import-time dependency on models/ at runtime.
All method signatures use forward references (strings) for the same reason.
When src/models/ is created, replace each ``X = Any`` line with the concrete
import and remove its TODO comment.

Do not import concrete client implementations here. Only factory.py (the
composition root) knows which implementation to wire.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Stub type aliases — replace with Pydantic model imports when src/models/ exists
# ---------------------------------------------------------------------------

OrderRequest = Any      # TODO: replace with Pydantic model from src.models
OrderResponse = Any     # TODO: replace with Pydantic model from src.models
OrderModify = Any       # TODO: replace with Pydantic model from src.models
Position = Any          # TODO: replace with Pydantic model from src.models
Holding = Any           # TODO: replace with Pydantic model from src.models
MarginResponse = Any    # TODO: replace with Pydantic model from src.models
OptionChain = Any       # TODO: replace with Pydantic model from src.models
Candle = Any            # TODO: replace with Pydantic model from src.models
CandleRequest = Any     # TODO: replace with Pydantic model from src.models
Contract = Any          # TODO: replace with Pydantic model from src.models
Tick = Any              # TODO: replace with Pydantic model from src.models


# ---------------------------------------------------------------------------
# Narrow sub-protocols (Interface Segregation)
# ---------------------------------------------------------------------------


@runtime_checkable
class MarketDataProvider(Protocol):
    """Subset of BrokerClient used by the portfolio tracker and signal generation.

    Any class that provides ``get_ltp`` and ``get_option_chain`` satisfies this
    protocol without any inheritance.
    """

    async def get_ltp(self, instruments: list[str]) -> dict[str, float]: ...

    async def get_option_chain(
        self, instrument: str, expiry: str
    ) -> dict: ...


@runtime_checkable
class OrderExecutor(Protocol):
    """Subset of BrokerClient used by the execution module.

    Note: order placement is currently blocked pending static IP provisioning.
    All callers go through MockBrokerClient until that constraint is resolved.
    """

    async def place_order(self, order: "OrderRequest") -> "OrderResponse": ...

    async def modify_order(
        self, order_id: str, changes: "OrderModify"
    ) -> "OrderResponse": ...

    async def cancel_order(self, order_id: str) -> "OrderResponse": ...


@runtime_checkable
class PortfolioReader(Protocol):
    """Subset of BrokerClient used by position monitoring."""

    async def get_positions(self) -> list["Position"]: ...

    async def get_holdings(self) -> list["Holding"]: ...

    async def get_margins(self) -> "MarginResponse": ...


# ---------------------------------------------------------------------------
# Full BrokerClient protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class BrokerClient(Protocol):
    """Full broker interface — all feature modules depend on this abstraction.

    BrokerClient is kept flat (not inheriting from the sub-protocols) for
    readability. Python's structural typing means any class that satisfies
    BrokerClient automatically satisfies MarketDataProvider, OrderExecutor,
    and PortfolioReader.

    Intended concrete implementations (see src/client/):
      UpstoxLiveClient   — production, hits live Upstox APIs
      UpstoxSandboxClient — integration testing, hits Upstox sandbox
      MockBrokerClient   — offline unit tests and CI (no network required)
    """

    # ── MarketDataProvider surface ───────────────────────────────

    async def get_ltp(self, instruments: list[str]) -> dict[str, float]: ...

    async def get_option_chain(
        self, instrument: str, expiry: str
    ) -> dict: ...

    # ── OrderExecutor surface ────────────────────────────────────

    async def place_order(self, order: "OrderRequest") -> "OrderResponse": ...

    async def modify_order(
        self, order_id: str, changes: "OrderModify"
    ) -> "OrderResponse": ...

    async def cancel_order(self, order_id: str) -> "OrderResponse": ...

    # ── PortfolioReader surface ──────────────────────────────────

    async def get_positions(self) -> list["Position"]: ...

    async def get_holdings(self) -> list["Holding"]: ...

    async def get_margins(self) -> "MarginResponse": ...

    # ── Additional methods not covered by sub-protocols ──────────

    async def get_historical_candles(
        self, params: "CandleRequest"
    ) -> list["Candle"]: ...

    async def get_expired_option_contracts(
        self, instrument: str, expiry: str
    ) -> list["Contract"]: ...


# ---------------------------------------------------------------------------
# MarketStream protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class MarketStream(Protocol):
    """Real-time websocket stream interface.

    Intended concrete implementations:
      UpstoxLiveStream   — production websocket feed from Upstox
      ReplayMarketStream — replays recorded tick Parquet files (offline)
    """

    async def subscribe(self, instruments: list[str], mode: str) -> None: ...

    async def unsubscribe(self, instruments: list[str]) -> None: ...

    def on_tick(self, callback: Callable[["Tick"], None]) -> None: ...

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...
