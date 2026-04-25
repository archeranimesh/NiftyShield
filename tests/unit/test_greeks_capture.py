"""Offline tests for Greeks capture: OptionChain model + Upstox parser + extraction.

All tests are fixture-driven — no network calls.  The fixture at
tests/fixtures/responses/option_chain/nifty_chain_2026-04-07.json records
a live Upstox response for 2026-04-07 with 129 strikes and an underlying
spot of 22266.25.

Test table
----------
 1  test_parse_chain_strike_count             129 strikes in fixture → 129 keys
 2  test_parse_chain_underlying_spot          underlying_spot == Decimal("22266.25")
 3  test_parse_chain_expiry                   expiry == date(2026, 4, 7)
 4  test_parse_chain_atm_ce_greeks            22250 CE: delta=0.525, iv=27.4, theta=-28.0612
 5  test_parse_chain_atm_pe_greeks            22250 PE: delta=-0.4755, iv=28.68
 6  test_parse_chain_all_decimal_types        spot, delta, gamma are all Decimal instances
 7  test_parse_chain_null_greek_coerces_to_zero  delta: null → Decimal("0")
 8  test_parse_chain_nonnumeric_greek_coerces_to_zero  delta: "N/A" → Decimal("0")
 9  test_parse_chain_empty_data               [] → empty strikes dict
10  test_extract_greeks_ce_happy_path         Leg(strike=22250, CE) → delta=Decimal("0.525")
11  test_extract_greeks_pe_happy_path         Leg(strike=22250, PE) → delta=Decimal("-0.4755")
12  test_extract_greeks_missing_strike        Leg(strike=99999) → {}
13  test_extract_greeks_equity_leg            Leg(asset_type=EQUITY) → {}
14  test_extract_greeks_none_strike           Leg(strike=None) → {}
15  test_fetch_greeks_no_option_legs          EQUITY-only → {}, market never called
16  test_fetch_greeks_correct_underlying_key  patches market.get_option_chain, asserts key
"""

from __future__ import annotations

import copy
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.client.upstox_market import parse_upstox_option_chain
from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.models.portfolio import AssetType, Direction, Leg, ProductType
from src.portfolio.tracker import PortfolioTracker, _extract_greeks_from_chain

# ── Fixture helpers ──────────────────────────────────────────────────────────

_FIXTURE_PATH = Path("tests/fixtures/responses/option_chain/nifty_chain_2026-04-07.json")


def _load_chain_data() -> list[dict]:
    """Load the raw strikes list from the recorded fixture."""
    with _FIXTURE_PATH.open() as fh:
        return json.load(fh)["response"]["data"]


def _make_leg(
    *,
    strike: float | None = 22250.0,
    asset_type: AssetType = AssetType.CE,
    expiry: date | None = date(2026, 4, 7),
    instrument_key: str = "NSE_FO|FAKE",
) -> Leg:
    """Construct a minimal option Leg for testing."""
    return Leg(
        display_name="TEST",
        instrument_key=instrument_key,
        quantity=50,
        entry_price=Decimal("100"),
        entry_date=date(2026, 1, 1),
        direction=Direction.SELL,
        asset_type=asset_type,
        product_type=ProductType.NRML,
        expiry=expiry,
        strike=strike,
    )


# ── Phase 2: parse_upstox_option_chain ──────────────────────────────────────


def test_parse_chain_strike_count() -> None:
    """Fixture has 129 strikes; parsed chain must have exactly 129 keys."""
    chain = parse_upstox_option_chain(_load_chain_data())
    assert len(chain.strikes) == 129


def test_parse_chain_underlying_spot() -> None:
    """Spot price read from first strike entry."""
    chain = parse_upstox_option_chain(_load_chain_data())
    assert chain.underlying_spot == Decimal("22266.25")


def test_parse_chain_expiry() -> None:
    """Expiry date parsed correctly from ISO string in fixture."""
    chain = parse_upstox_option_chain(_load_chain_data())
    assert chain.expiry == date(2026, 4, 7)


def test_parse_chain_atm_ce_greeks() -> None:
    """ATM CE (22250) Greeks match fixture values exactly."""
    chain = parse_upstox_option_chain(_load_chain_data())
    ce = chain.strikes[Decimal("22250.0")].ce
    assert ce is not None
    assert ce.delta == Decimal("0.525")
    assert ce.iv == Decimal("27.4")
    assert ce.theta == Decimal("-28.0612")
    assert ce.vega == Decimal("10.5313")
    assert ce.gamma == Decimal("0.0005")


def test_parse_chain_atm_pe_greeks() -> None:
    """ATM PE (22250) Greeks match fixture values exactly."""
    chain = parse_upstox_option_chain(_load_chain_data())
    pe = chain.strikes[Decimal("22250.0")].pe
    assert pe is not None
    assert pe.delta == Decimal("-0.4755")
    assert pe.iv == Decimal("28.68")


def test_parse_chain_all_decimal_types() -> None:
    """underlying_spot, CE delta, and CE gamma are all Decimal instances."""
    chain = parse_upstox_option_chain(_load_chain_data())
    assert isinstance(chain.underlying_spot, Decimal)
    ce = chain.strikes[Decimal("22250.0")].ce
    assert ce is not None
    assert isinstance(ce.delta, Decimal)
    assert isinstance(ce.gamma, Decimal)


def test_parse_chain_null_greek_coerces_to_zero() -> None:
    """A null Greek value in the response must coerce to Decimal('0')."""
    data = _load_chain_data()
    # Inject null delta into the first strike's CE greeks
    injected = copy.deepcopy(data[:1])
    injected[0]["call_options"]["option_greeks"]["delta"] = None
    chain = parse_upstox_option_chain(injected)
    strike_key = Decimal(str(injected[0]["strike_price"]))
    ce = chain.strikes[strike_key].ce
    assert ce is not None
    assert ce.delta == Decimal("0")


def test_parse_chain_nonnumeric_greek_coerces_to_zero() -> None:
    """A non-numeric Greek string in the response must coerce to Decimal('0')."""
    data = _load_chain_data()
    injected = copy.deepcopy(data[:1])
    injected[0]["call_options"]["option_greeks"]["delta"] = "N/A"
    chain = parse_upstox_option_chain(injected)
    strike_key = Decimal(str(injected[0]["strike_price"]))
    ce = chain.strikes[strike_key].ce
    assert ce is not None
    assert ce.delta == Decimal("0")


def test_parse_chain_empty_data() -> None:
    """Empty list input must return an OptionChain with no strikes."""
    chain = parse_upstox_option_chain([])
    assert isinstance(chain, OptionChain)
    assert chain.strikes == {}


# ── Phase 3: _extract_greeks_from_chain ─────────────────────────────────────


def test_extract_greeks_ce_happy_path() -> None:
    """CE leg at 22250 returns correct delta from chain."""
    chain = parse_upstox_option_chain(_load_chain_data())
    leg = _make_leg(strike=22250.0, asset_type=AssetType.CE)
    greeks = _extract_greeks_from_chain(chain, leg)
    assert greeks["delta"] == Decimal("0.525")
    assert greeks["iv"] == Decimal("27.4")
    assert "oi" in greeks
    assert "volume" in greeks


def test_extract_greeks_pe_happy_path() -> None:
    """PE leg at 22250 returns correct (negative) delta from chain."""
    chain = parse_upstox_option_chain(_load_chain_data())
    leg = _make_leg(strike=22250.0, asset_type=AssetType.PE)
    greeks = _extract_greeks_from_chain(chain, leg)
    assert greeks["delta"] == Decimal("-0.4755")
    assert greeks["iv"] == Decimal("28.68")


def test_extract_greeks_missing_strike() -> None:
    """Strike not present in the chain returns empty dict."""
    chain = parse_upstox_option_chain(_load_chain_data())
    leg = _make_leg(strike=99999.0, asset_type=AssetType.CE)
    assert _extract_greeks_from_chain(chain, leg) == {}


def test_extract_greeks_equity_leg() -> None:
    """Equity leg returns empty dict without touching the chain."""
    chain = parse_upstox_option_chain(_load_chain_data())
    leg = _make_leg(strike=22250.0, asset_type=AssetType.EQUITY)
    assert _extract_greeks_from_chain(chain, leg) == {}


def test_extract_greeks_none_strike() -> None:
    """Leg with strike=None returns empty dict."""
    chain = parse_upstox_option_chain(_load_chain_data())
    leg = _make_leg(strike=None, asset_type=AssetType.CE)
    assert _extract_greeks_from_chain(chain, leg) == {}


# ── Phase 3: _fetch_greeks (async, patched market) ──────────────────────────


@pytest.mark.asyncio
async def test_fetch_greeks_no_option_legs() -> None:
    """When all legs are EQUITY, _fetch_greeks returns {} without calling market."""
    market = MagicMock()
    market.get_option_chain = AsyncMock()
    store = MagicMock()
    tracker = PortfolioTracker(store=store, market=market)

    equity_legs = [
        _make_leg(asset_type=AssetType.EQUITY, strike=None, expiry=None),
        _make_leg(asset_type=AssetType.BOND, strike=None, expiry=None),
    ]
    result = await tracker._fetch_greeks(equity_legs)

    assert result == {}
    market.get_option_chain.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_greeks_correct_underlying_key() -> None:
    """_fetch_greeks calls market.get_option_chain with 'NSE_INDEX|Nifty 50'."""
    market = MagicMock()
    # Return the real fixture data so parsing succeeds
    raw_data = _load_chain_data()
    market.get_option_chain = AsyncMock(return_value=raw_data)
    store = MagicMock()
    tracker = PortfolioTracker(store=store, market=market)

    option_leg = _make_leg(
        strike=22250.0,
        asset_type=AssetType.CE,
        expiry=date(2026, 4, 7),
        instrument_key="NSE_FO|40718",
    )
    result = await tracker._fetch_greeks([option_leg])

    market.get_option_chain.assert_called_once_with(
        "NSE_INDEX|Nifty 50", "2026-04-07"
    )
    assert "NSE_FO|40718" in result
    assert result["NSE_FO|40718"]["delta"] == Decimal("0.525")
