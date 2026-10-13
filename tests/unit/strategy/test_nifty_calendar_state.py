"""Unit tests for the NiftyCalendarV1 rebuild helpers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.instruments.lookup import InstrumentLookup
from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.nifty_calendar.errors import InvalidStructureError
from src.paper.models import PaperPosition
from src.strategy.nifty_calendar_state import (
    ROLES,
    cycle_entry_date,
    executable_pnl,
    far_carry,
    leg_quotes,
    resolve_open_legs,
)

NEAR, FAR = date(2026, 10, 27), date(2026, 11, 23)


def _opt(bid: str, ask: str) -> OptionLeg:
    return OptionLeg(
        strike=Decimal(22700), ltp=Decimal(bid), bid=Decimal(bid), ask=Decimal(ask), oi=1,
        volume=1, delta=Decimal("0.5"), gamma=None, theta=None, vega=Decimal(20), iv=Decimal(14),
    )  # fmt: skip


def _setup() -> tuple[InstrumentLookup, list[PaperPosition]]:
    specs = [("short_call", "CE", NEAR, -65), ("short_put", "PE", NEAR, -65),
             ("long_call_wing", "CE", FAR, 65), ("long_put_wing", "PE", FAR, 65)]  # fmt: skip
    insts = [
        {"segment": "NSE_FO", "instrument_type": t, "underlying_symbol": "NIFTY",
         "strike_price": 22700.0, "expiry": e.isoformat(), "instrument_key": f"NSE_FO|{i}"}
        for i, (_, t, e, _) in enumerate(specs)
    ]  # fmt: skip
    pos = [
        PaperPosition("paper_x", role, qty, Decimal("100"), Decimal("200"), f"NSE_FO|{i}",
                      date(2026, 9, 30) if qty < 0 else None)
        for i, (role, _, _, qty) in enumerate(specs)
    ]  # fmt: skip
    return InstrumentLookup(insts), pos


def test_resolve_open_legs_and_entry_date_from_shorts() -> None:
    lookup, pos = _setup()
    legs = resolve_open_legs(pos, lookup)
    assert set(legs) == set(ROLES)
    assert legs["long_call_wing"].expiry == FAR and legs["short_put"].strike == Decimal(22700)
    assert cycle_entry_date(legs) == date(2026, 9, 30)


def test_resolve_open_legs_rejects_incomplete_structure() -> None:
    lookup, pos = _setup()
    with pytest.raises(InvalidStructureError, match="missing roles"):
        resolve_open_legs(pos[:3], lookup)
    with pytest.raises(InvalidStructureError, match="cannot resolve"):
        resolve_open_legs(pos, InstrumentLookup([]))


def test_quotes_and_executable_pnl_use_the_executable_side() -> None:
    lookup, pos = _setup()
    legs = resolve_open_legs(pos, lookup)
    near = OptionChain(
        underlying_spot=Decimal(22700), expiry=NEAR,
        strikes={Decimal(22700): OptionChainStrike(ce=_opt("150", "152"), pe=_opt("140", "142"))},
    )  # fmt: skip
    far = OptionChain(
        underlying_spot=Decimal(22700), expiry=FAR,
        strikes={Decimal(22700): OptionChainStrike(ce=_opt("300", "302"), pe=_opt("290", "292"))},
    )  # fmt: skip
    quotes = leg_quotes(legs, {NEAR: near, FAR: far})
    # shorts sold at 200 buy back at ask 152/142; longs bought at 100 sell at bid 300/290
    assert executable_pnl(legs, quotes) == Decimal(65) * (48 + 58 + 200 + 190)
    assert far_carry(far, Decimal(22700)) == Decimal("22700") + Decimal(301) - Decimal(291) - 22700
    with pytest.raises(InvalidStructureError, match="no two-sided quote"):
        leg_quotes(legs, {NEAR: near})


def test_far_carry_requires_both_sides() -> None:
    chain = OptionChain(
        underlying_spot=Decimal(1), expiry=FAR,
        strikes={Decimal(1): OptionChainStrike(ce=_opt("1", "2"), pe=None)},
    )  # fmt: skip
    with pytest.raises(InvalidStructureError):
        far_carry(chain, Decimal(1))
