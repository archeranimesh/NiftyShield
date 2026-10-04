"""Tests for src.payoff.registry."""

from dataclasses import dataclass
from decimal import Decimal

import pytest

from src.payoff.core import PayoffLeg
from src.payoff.errors import DuplicateRegistrationError, InvalidLegsError
from src.payoff.registry import (
    DEFAULT_REGISTRY,
    DefaultPositionAdapter,
    HasTitle,
    PayoffContext,
    PayoffRegistry,
    get_adapter,
    register_payoff,
)


@dataclass
class _Pos:
    leg_role: str
    net_qty: int
    avg_cost: Decimal
    avg_sell_price: Decimal
    instrument_key: str
    option_type: str | None


class _Resolver:
    def __init__(self, strikes: dict[str, str]) -> None:
        self._s = {k: Decimal(v) for k, v in strikes.items()}

    def strike_for(self, instrument_key: str) -> Decimal | None:
        return self._s.get(instrument_key)


class _Adapter:
    def legs(self, ctx: PayoffContext) -> list[PayoffLeg]:
        return []


class _TitledAdapter(_Adapter):
    def title(self, ctx: PayoffContext) -> str:
        return "t"


def _ctx(positions) -> PayoffContext:
    return PayoffContext(positions=positions, spot=None, lot_size=65, strategy_name="s")


def _ic_positions() -> list[_Pos]:
    z = Decimal("0")
    return [
        _Pos("short_put", -65, z, Decimal("100"), "k_sp", "PE"),
        _Pos("short_call", -65, z, Decimal("110"), "k_sc", "CE"),
        _Pos("long_put", 65, Decimal("20"), z, "k_lp", "PE"),
        _Pos("long_call", 65, Decimal("25"), z, "k_lc", "CE"),
    ]


_STRIKES = {"k_sp": "23000", "k_sc": "25000", "k_lp": "22500", "k_lc": "25500"}


def test_register_and_get():
    reg, adapter = PayoffRegistry(), _Adapter()
    reg.register("a", adapter)
    assert reg.get("a") is adapter


def test_get_unregistered_returns_none():
    assert PayoffRegistry().get("nope") is None


def test_duplicate_registration_raises():
    reg = PayoffRegistry()
    reg.register("a", _Adapter())
    with pytest.raises(DuplicateRegistrationError):
        reg.register("a", _Adapter())


def test_injected_registry_is_isolated():
    DEFAULT_REGISTRY.clear()
    try:
        register_payoff("iso", _Adapter())
        assert get_adapter("iso") is not None
        assert PayoffRegistry().get("iso") is None
    finally:
        DEFAULT_REGISTRY.clear()


def test_default_adapter_builds_legs():
    legs = DefaultPositionAdapter(_Resolver(_STRIKES)).legs(_ctx(_ic_positions()))
    by_role = {leg.role: leg for leg in legs}
    assert len(legs) == 4
    assert by_role["short_put"].qty == -65 and by_role["short_put"].entry_price == Decimal("100")
    assert by_role["long_call"].qty == 65 and by_role["long_call"].entry_price == Decimal("25")
    assert by_role["short_call"].strike == Decimal("25000") and by_role["short_call"].kind == "CE"


def test_default_adapter_eq_leg_needs_no_strike():
    pos = [_Pos("eq", 100, Decimal("250"), Decimal("0"), "k_eq", "EQ")]
    (leg,) = DefaultPositionAdapter(_Resolver({})).legs(_ctx(pos))
    assert leg.kind == "EQ" and leg.strike is None


def test_default_adapter_skips_flat():
    pos = _ic_positions()
    pos.append(_Pos("old", 0, Decimal("0"), Decimal("0"), "k_old", None))
    legs = DefaultPositionAdapter(_Resolver(_STRIKES)).legs(_ctx(pos))
    assert len(legs) == 4


def test_default_adapter_partial_resolution_raises():
    strikes = {k: v for k, v in _STRIKES.items() if k != "k_lc"}
    with pytest.raises(InvalidLegsError):
        DefaultPositionAdapter(_Resolver(strikes)).legs(_ctx(_ic_positions()))


def test_default_adapter_unknown_type_raises():
    pos = [_Pos("x", -65, Decimal("0"), Decimal("5"), "k_x", None)]
    with pytest.raises(InvalidLegsError):
        DefaultPositionAdapter(_Resolver({})).legs(_ctx(pos))


def test_title_capability_detected():
    assert isinstance(_TitledAdapter(), HasTitle)
    assert not isinstance(_Adapter(), HasTitle)


def test_decorator_registers_class():
    DEFAULT_REGISTRY.clear()
    try:

        @register_payoff("deco")
        class Mine(_Adapter):
            pass

        assert Mine.__name__ == "Mine"
        assert isinstance(get_adapter("deco"), Mine)
    finally:
        DEFAULT_REGISTRY.clear()
