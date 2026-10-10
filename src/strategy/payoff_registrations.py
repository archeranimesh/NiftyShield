"""The single explicit place where strategies opt in to payoff charts.

Registration is never an import side effect of a strategy module: every wired call site
(entry / EOD / close) calls ``ensure_registered()`` itself.

How to register a new strategy: add one ``registry.register("<strategy_name>", adapter)`` line
inside ``ensure_registered``. The name must equal the ``strategy_name`` the call site passes to
``send_payoff_chart`` (the DB discriminator, e.g. ``paper_ic_nifty_v1_weekly``).
"""

from decimal import Decimal
from pathlib import Path

from src.instruments.lookup import InstrumentLookup
from src.paper.constants import DEFAULT_BOD_PATH
from src.payoff.core import PayoffLeg
from src.payoff.errors import DuplicateRegistrationError
from src.payoff.registry import (
    DEFAULT_REGISTRY,
    DefaultPositionAdapter,
    PayoffContext,
    PayoffRegistry,
    StrikeResolver,
)
from src.strategy.ic_expiry_config import CONFIGS
from src.strategy.ic_expiry_config_v2 import CONFIGS_V2


class BodStrikeResolver:
    """Resolves option strikes from the BOD instrument file, loaded lazily on first use."""

    def __init__(self, bod_path: Path | str = DEFAULT_BOD_PATH) -> None:
        self._bod_path = bod_path
        self._lookup: InstrumentLookup | None = None

    def strike_for(self, instrument_key: str) -> Decimal | None:
        """Return the strike for ``instrument_key``, or ``None`` if unresolvable."""
        if self._lookup is None:
            self._lookup = InstrumentLookup.from_file(self._bod_path)
        inst = self._lookup.get_by_key(instrument_key)
        strike = inst.get("strike_price") if inst else None
        return None if strike is None else Decimal(str(strike))


class IronCondorPayoffAdapter:
    """Default four-leg position adapter plus title and subtitle."""

    def __init__(self, expiry_type: str, resolver: StrikeResolver, label: str) -> None:
        self._expiry_type = expiry_type
        self._label = label
        self._default = DefaultPositionAdapter(resolver)

    def legs(self, ctx: PayoffContext) -> list[PayoffLeg]:
        """Return the open IC legs (delegates to ``DefaultPositionAdapter``)."""
        return self._default.legs(ctx)

    def title(self, ctx: PayoffContext) -> str:
        """Return the chart title."""
        return self._label

    def subtitle(self, ctx: PayoffContext) -> str:
        """Return the chart subtitle."""
        return f"{self._expiry_type.capitalize()} expiry"


def _ic_strategy_names() -> list[tuple[str, str, str]]:
    """Return ``(strategy_name, expiry_type, label)`` for every V1 and V2 IC preset."""
    v1: list[tuple[str, str, str]] = [
        (c.strategy_name, c.expiry_type, "Iron Condor v1") for c in CONFIGS.values()
    ]
    v2: list[tuple[str, str, str]] = [
        (c.strategy_name, c.expiry_type, "Iron Condor v2") for c in CONFIGS_V2.values()
    ]
    return v1 + v2


def ensure_registered(registry: PayoffRegistry = DEFAULT_REGISTRY) -> None:
    """Register every payoff-charted strategy in ``registry``; safe to call repeatedly."""
    resolver = BodStrikeResolver()
    for name, expiry_type, label in _ic_strategy_names():
        try:
            registry.register(name, IronCondorPayoffAdapter(expiry_type, resolver, label))
        except DuplicateRegistrationError:
            continue
