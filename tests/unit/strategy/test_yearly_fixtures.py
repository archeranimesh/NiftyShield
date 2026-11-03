"""YF-2: yearly-overlay fixtures (Dec 2026/2027 BOD, Dhan chains) and the frozen clock."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.client.dhan_market import parse_dhan_option_chain
from src.client.upstox_market import parse_upstox_option_chain
from src.instruments.lookup import InstrumentLookup

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
BOD = FIXTURES / "contract_resolver" / "upstox_bod_nifty_dec.json"
DHAN_DEC2026 = FIXTURES / "dhan_chain" / "dec2026.json"
ZERO_GREEKS = FIXTURES / "yearly_overlays" / "chain_dec2027_zero_greeks.json"


def test_fixture_bod_resolves_yearly_dec2026():
    lookup = InstrumentLookup.from_file(BOD)
    cands = dict(lookup.get_expiry_candidates("NIFTY", date(2026, 10, 6), preference=["yearly"]))
    assert cands["yearly"] == "2026-12-29"


def test_fixture_bod_resolves_yearly_dec2027_once_dec2026_gone():
    # Dec 2026 settled and dropped from the live feed: only Dec 2027 remains.
    data = json.loads(BOD.read_text())
    live = [i for i in data if "26" not in i["trading_symbol"].split()[-1]]
    lookup = InstrumentLookup(live)
    cands = dict(lookup.get_expiry_candidates("NIFTY", date(2026, 12, 30), preference=["yearly"]))
    assert cands["yearly"] == "2027-12-28"


def test_zero_greeks_fixture_parses_all_deltas_zero():
    chain = parse_upstox_option_chain(json.loads(ZERO_GREEKS.read_text()))
    assert chain.expiry == date(2027, 12, 28)
    legs = [leg for s in chain.strikes.values() for leg in (s.ce, s.pe) if leg]
    assert legs and all(leg.delta == Decimal("0") for leg in legs)


def test_populated_chain_fixture_has_nonzero_delta():
    chain = parse_dhan_option_chain(json.loads(DHAN_DEC2026.read_text()), date(2026, 12, 29))
    legs = [leg for s in chain.strikes.values() for leg in (s.ce, s.pe) if leg]
    assert any(leg.delta not in (None, Decimal("0")) for leg in legs)


def test_frozen_today_pins_overlay_clock(frozen_today):
    frozen_today(date(2026, 10, 6), "src.strategy.cc_overlay_v1")
    from src.strategy import cc_overlay_v1

    assert cc_overlay_v1.market_today() == date(2026, 10, 6)
