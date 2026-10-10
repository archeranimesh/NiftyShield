"""Tests for src.strategy.payoff_registrations."""

from decimal import Decimal
from typing import Any

import pytest

from src.paper.models import PaperPosition
from src.payoff.core import compute_payoff
from src.payoff.errors import InvalidLegsError
from src.payoff.registry import PayoffContext, PayoffRegistry
from src.strategy import payoff_registrations as pr
from src.strategy.payoff_registrations import (
    BodStrikeResolver,
    ensure_registered,
)

# Single source of truth for strategy names the wired sites (PC-14..18) pass.
WIRED_STRATEGY_NAMES = [
    "paper_ic_nifty_v1_weekly",
    "paper_ic_nifty_v1_monthly",
    "paper_ic_nifty_v1_leaps",
    "paper_ic_nifty_v1_yearly",
    "paper_ic_nifty_v2_monthly",
]

_STRIKES = {"SP": "24000", "LP": "23500", "SC": "25000", "LC": "25500"}


class _FakeResolver:
    def strike_for(self, instrument_key: str) -> Decimal | None:
        return Decimal(_STRIKES[instrument_key]) if instrument_key in _STRIKES else None


def _pos(role: str, key: str, qty: int, sell: str, cost: str, kind: str) -> PaperPosition:
    return PaperPosition(
        strategy_name="s",
        leg_role=role,
        net_qty=qty,
        avg_cost=Decimal(cost),
        avg_sell_price=Decimal(sell),
        instrument_key=key,
        option_type=kind,  # type: ignore[arg-type]
    )


def _ic_positions() -> list[PaperPosition]:
    return [
        _pos("short_put", "SP", -65, "100", "0", "PE"),
        _pos("long_put_hedge", "LP", 65, "0", "20", "PE"),
        _pos("short_call", "SC", -65, "80", "0", "CE"),
        _pos("long_call_hedge", "LC", 65, "0", "10", "CE"),
    ]


@pytest.mark.parametrize("name", WIRED_STRATEGY_NAMES)
def test_every_wired_strategy_name_is_registered(name: str) -> None:
    registry = PayoffRegistry()
    ensure_registered(registry)
    assert registry.get(name) is not None


def test_ensure_registered_is_idempotent() -> None:
    registry = PayoffRegistry()
    ensure_registered(registry)
    ensure_registered(registry)
    assert registry.get("paper_ic_nifty_v2_monthly") is not None


def test_ensure_registered_resolves_ic_v1_and_v2() -> None:
    registry = PayoffRegistry()
    ensure_registered(registry)
    assert registry.get("paper_ic_nifty_v1_monthly") is not None
    assert registry.get("paper_ic_nifty_v2_monthly") is not None
    assert registry.get("paper_csp_nifty_v1") is None


def test_ic_adapter_legs_match_entry_strikes() -> None:
    adapter = pr.IronCondorPayoffAdapter("monthly", _FakeResolver(), "Iron Condor v1")
    ctx = PayoffContext(_ic_positions(), Decimal("24500"), 65, "paper_ic_nifty_v1_monthly")
    legs = adapter.legs(ctx)
    by_role = {leg.role: leg for leg in legs}
    assert len(legs) == 4
    assert by_role["short_put"].qty == -65 and by_role["short_put"].strike == Decimal("24000")
    assert by_role["long_call_hedge"].qty == 65 and by_role["long_call_hedge"].kind == "CE"
    # Entry credit per unit = 100 + 80 - 20 - 10 = 150
    assert compute_payoff(legs).net_premium == Decimal("150") * 65


def test_ic_adapter_aborts_on_unresolved_strike() -> None:
    adapter = pr.IronCondorPayoffAdapter("monthly", _FakeResolver(), "Iron Condor v1")
    pos = _ic_positions()
    pos[0] = _pos("short_put", "UNKNOWN", -65, "100", "0", "PE")
    ctx = PayoffContext(pos, None, 65, "paper_ic_nifty_v1_monthly")
    with pytest.raises(InvalidLegsError):
        adapter.legs(ctx)


def test_ic_adapter_title_and_subtitle() -> None:
    adapter = pr.IronCondorPayoffAdapter("monthly", _FakeResolver(), "Iron Condor v1")
    ctx = PayoffContext([], None, 65, "x")
    assert adapter.title(ctx) == "Iron Condor v1"
    assert adapter.subtitle(ctx) == "Monthly expiry"


def test_ensure_registered_labels_v1_and_v2() -> None:
    registry = PayoffRegistry()
    ensure_registered(registry)
    v1 = registry.get("paper_ic_nifty_v1_monthly")
    v2 = registry.get("paper_ic_nifty_v2_monthly")
    ctx = PayoffContext([], None, 65, "x")
    assert v1.title(ctx) == "Iron Condor v1"
    assert v2.title(ctx) == "Iron Condor v2"


def test_bod_strike_resolver_is_lazy_and_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class _Lookup:
        def get_by_key(self, key: str) -> dict[str, Any] | None:
            return {"strike_price": 24000.0} if key == "K" else None

    def _from_file(path: str) -> _Lookup:
        calls.append(path)
        return _Lookup()

    monkeypatch.setattr(pr.InstrumentLookup, "from_file", staticmethod(_from_file))
    resolver = BodStrikeResolver("/nope")
    assert calls == []
    assert resolver.strike_for("K") == Decimal("24000.0")
    assert resolver.strike_for("missing") is None
    assert calls == ["/nope"]
