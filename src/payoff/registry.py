"""Opt-in registry mapping a strategy name to a payoff adapter.

How to register a strategy for payoff charts:
    1. Write an adapter with ``legs(ctx) -> list[PayoffLeg]`` (or reuse ``DefaultPositionAdapter``).
    2. Add ``register_payoff("<strategy_name>", adapter)`` inside the explicit registration module.
    3. Optionally give the adapter a ``title(ctx) -> str`` method (``HasTitle``) for a custom heading.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Protocol, TypeVar, overload, runtime_checkable

from src.payoff.core import PayoffLeg
from src.payoff.errors import DuplicateRegistrationError, InvalidLegsError


class PositionLike(Protocol):
    """Structural view of ``src.paper.models.PaperPosition`` fields the payoff layer reads."""

    leg_role: str
    net_qty: int
    avg_cost: Decimal
    avg_sell_price: Decimal
    instrument_key: str
    option_type: Literal["PE", "CE", "FUT", "EQ"] | None


class StrikeResolver(Protocol):
    """Resolves an instrument key to an option strike."""

    def strike_for(self, instrument_key: str) -> Decimal | None:
        """Return the strike for ``instrument_key``, or ``None`` if unresolvable."""
        ...


@dataclass(frozen=True)
class PayoffContext:
    """Inputs handed to a payoff adapter.

    Attributes:
        positions: Position legs of the strategy.
        spot: Current underlying spot, if known.
        lot_size: Contract lot size.
        strategy_name: Registered strategy name.
        extras: Strategy-specific inputs.
    """

    positions: Sequence[PositionLike]
    spot: Decimal | None
    lot_size: int
    strategy_name: str
    extras: Mapping[str, object] = field(default_factory=dict)


@runtime_checkable
class PayoffAdapter(Protocol):
    """Required adapter capability: build payoff legs from a context."""

    def legs(self, ctx: PayoffContext) -> list[PayoffLeg]:
        """Return the payoff legs for ``ctx``."""
        ...


@runtime_checkable
class HasTitle(Protocol):
    """Optional adapter capability: a custom chart title."""

    def title(self, ctx: PayoffContext) -> str:
        """Return the chart title for ``ctx``."""
        ...


class PayoffRegistry:
    """Name -> adapter map. Inject a fresh instance for test isolation."""

    def __init__(self) -> None:
        self._adapters: dict[str, PayoffAdapter] = {}

    def register(self, name: str, adapter: PayoffAdapter) -> None:
        """Register ``adapter`` under ``name``.

        Raises:
            DuplicateRegistrationError: If ``name`` is already registered.
        """
        if name in self._adapters:
            raise DuplicateRegistrationError(f"payoff adapter already registered: {name}")
        self._adapters[name] = adapter

    def get(self, name: str) -> PayoffAdapter | None:
        """Return the adapter for ``name``, or ``None`` if unregistered."""
        return self._adapters.get(name)

    def clear(self) -> None:
        """Remove all registrations."""
        self._adapters.clear()


DEFAULT_REGISTRY = PayoffRegistry()

_T = TypeVar("_T")


@overload
def register_payoff(name: str, adapter: PayoffAdapter) -> PayoffAdapter: ...
@overload
def register_payoff(name: str, adapter: None = None) -> Callable[[type[_T]], type[_T]]: ...
def register_payoff(name, adapter=None):
    """Register an adapter in ``DEFAULT_REGISTRY``, directly or as a class decorator.

    A decorated class is instantiated with no arguments; the class itself is returned.
    """
    if adapter is not None:
        DEFAULT_REGISTRY.register(name, adapter)
        return adapter

    def decorator(cls: type[_T]) -> type[_T]:
        DEFAULT_REGISTRY.register(name, cls())  # type: ignore[arg-type]
        return cls

    return decorator


def get_adapter(name: str) -> PayoffAdapter | None:
    """Return the adapter registered in ``DEFAULT_REGISTRY`` for ``name``."""
    return DEFAULT_REGISTRY.get(name)


class DefaultPositionAdapter:
    """Charts every open position as one structure, using an injected strike resolver."""

    def __init__(self, resolver: StrikeResolver) -> None:
        self._resolver = resolver

    def legs(self, ctx: PayoffContext) -> list[PayoffLeg]:
        """Build one ``PayoffLeg`` per non-flat position.

        Raises:
            InvalidLegsError: If any open position has an unknown instrument type or an
                option without a resolvable strike (a partial payoff would mislead).
        """
        return [self._leg(p) for p in ctx.positions if p.net_qty != 0]

    def _leg(self, pos: PositionLike) -> PayoffLeg:
        kind = pos.option_type
        if kind is None:
            raise InvalidLegsError(f"unresolved instrument type for {pos.instrument_key}")
        strike = None
        if kind in ("CE", "PE"):
            strike = self._resolver.strike_for(pos.instrument_key)
            if strike is None:
                raise InvalidLegsError(f"unresolved strike for {pos.instrument_key}")
        price = pos.avg_sell_price if pos.net_qty < 0 else pos.avg_cost
        return PayoffLeg(
            kind=kind, strike=strike, qty=pos.net_qty, entry_price=price, role=pos.leg_role
        )
