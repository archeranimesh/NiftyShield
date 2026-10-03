"""Unit tests for src/gamma/derive.py — pure, no mocks."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from structlog.testing import capture_logs

from src.gamma.derive import derive_snapshots
from src.models.options import OptionChain, OptionChainStrike, OptionLeg

TODAY = date(2026, 4, 20)
EXPIRY = date(2026, 4, 21)


def _leg(strike: int, *, bid: str = "9.50", ask: str = "10", oi: int = 1200) -> OptionLeg:
    return OptionLeg(
        ltp=Decimal("9.8"),
        bid=Decimal(bid),
        ask=Decimal(ask),
        oi=oi,
        volume=500,
        delta=Decimal("0.5"),
        gamma=Decimal("0.001"),
        theta=Decimal("-5"),
        vega=Decimal("3"),
        iv=Decimal("14"),
        strike=Decimal(strike),
    )


def _chain(strikes: dict[int, OptionChainStrike], spot: str = "25000") -> OptionChain:
    return OptionChain(
        underlying_spot=Decimal(spot),
        expiry=EXPIRY,
        strikes={Decimal(k): v for k, v in strikes.items()},
    )


def test_derive_snapshots_normal() -> None:
    chain = _chain(
        {
            25000: OptionChainStrike(ce=_leg(25000), pe=_leg(25000, oi=800)),
            25100: OptionChainStrike(ce=_leg(25100), pe=None),
        }
    )
    prior = {(25000, "CE"): 1000, (25000, "PE"): 1000}

    rows = derive_snapshots(chain, EXPIRY, TODAY, "09:20", prior)

    assert [(r.strike, r.option_type) for r in rows] == [
        (25000, "CE"),
        (25000, "PE"),
        (25100, "CE"),
    ]
    ce, pe, far = rows
    assert ce.gamma_gearing == Decimal("0.001") * Decimal(25000) ** 2 / Decimal("10")
    assert ce.distance_pct == Decimal("0")
    assert ce.oi_change_1d == Decimal("0.2")
    assert pe.oi_change_1d == Decimal("-0.2")
    assert ce.bid_ask_spread == Decimal("0.50")
    assert far.distance_pct == Decimal("100") / Decimal("25000")
    assert ce.dte_calendar == 1


def test_derive_snapshots_ask_guard() -> None:
    chain = _chain({25000: OptionChainStrike(ce=_leg(25000, ask="0.10"))})

    with capture_logs() as logs:
        rows = derive_snapshots(chain, EXPIRY, TODAY, "09:20", {})

    assert len(rows) == 1
    assert rows[0].gamma_gearing is None
    assert any(e["event"] == "gamma.derive.ask_too_low_for_gearing" for e in logs)


def test_derive_snapshots_missing_bid_gives_no_spread() -> None:
    chain = _chain({25000: OptionChainStrike(ce=_leg(25000, bid="0", ask="10"))})

    rows = derive_snapshots(chain, EXPIRY, TODAY, "09:20", {})

    assert rows[0].bid_ask_spread is None


def test_derive_snapshots_no_prior_oi() -> None:
    chain = _chain({25000: OptionChainStrike(ce=_leg(25000), pe=_leg(25000))})

    rows = derive_snapshots(chain, EXPIRY, TODAY, "09:20", {(25000, "PE"): 0})

    assert [r.oi_change_1d for r in rows] == [None, None]


def test_derive_snapshots_excludes_strikes_beyond_ten_percent() -> None:
    chain = _chain(
        {
            25000: OptionChainStrike(ce=_leg(25000)),
            27600: OptionChainStrike(ce=_leg(27600)),
        }
    )

    rows = derive_snapshots(chain, EXPIRY, TODAY, "09:20", {})

    assert [r.strike for r in rows] == [25000]


def test_derive_snapshots_zero_spot_returns_empty() -> None:
    chain = _chain({25000: OptionChainStrike(ce=_leg(25000))}, spot="0")

    assert derive_snapshots(chain, EXPIRY, TODAY, "09:20", {}) == []
