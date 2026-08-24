# tests/unit/strategy/test_price_utils.py
"""Unit tests for src/strategy/_price_utils."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from structlog.testing import capture_logs

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.strategy._price_utils import find_option_leg, resolve_price

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_leg(
    ltp: str = "100",
    bid: str = "99",
    ask: str = "101",
    strike: str = "23000",
) -> OptionLeg:
    return OptionLeg(
        ltp=Decimal(ltp),
        bid=Decimal(bid),
        ask=Decimal(ask),
        oi=500,
        volume=200,
        delta=Decimal("-0.30"),
        gamma=Decimal("0.001"),
        theta=Decimal("-5"),
        vega=Decimal("10"),
        iv=Decimal("15.0"),
        strike=Decimal(strike),
    )


def _make_chain(pe_strike: str = "23000", ce_strike: str = "24000") -> OptionChain:
    pe = _make_leg(ltp="100", bid="99", ask="101", strike=pe_strike)
    ce = _make_leg(ltp="200", bid="198", ask="202", strike=ce_strike)
    return OptionChain(
        underlying_spot=Decimal("23500"),
        expiry=date(2026, 6, 26),
        strikes={
            Decimal(pe_strike): OptionChainStrike(pe=pe),
            Decimal(ce_strike): OptionChainStrike(ce=ce),
        },
    )


# ── resolve_price ─────────────────────────────────────────────────────────────


def test_resolve_price_uses_mid_when_bid_ask_positive() -> None:
    leg = _make_leg(bid="99", ask="101", ltp="95")
    assert resolve_price(leg) == Decimal("100")  # (99+101)/2


def test_resolve_price_falls_back_to_ltp_when_bid_zero() -> None:
    leg = _make_leg(bid="0", ask="101", ltp="95")
    assert resolve_price(leg) == Decimal("95")


def test_resolve_price_falls_back_to_ltp_when_ask_zero() -> None:
    leg = _make_leg(bid="99", ask="0", ltp="95")
    assert resolve_price(leg) == Decimal("95")


def test_resolve_price_raises_when_all_prices_zero() -> None:
    leg = _make_leg(bid="0", ask="0", ltp="0")
    with pytest.raises(ValueError, match="No valid price"):
        resolve_price(leg)


def test_resolve_price_raises_when_ltp_zero_and_no_spread() -> None:
    leg = _make_leg(bid="0", ask="0", ltp="0")
    with pytest.raises(ValueError):
        resolve_price(leg)


# ── find_option_leg ───────────────────────────────────────────────────────────


def test_find_option_leg_returns_pe_for_put_key() -> None:
    market = _make_chain(pe_strike="23000")
    leg = find_option_leg("NSE_FO|NIFTY23000PE29MAY2026", market)
    assert leg is not None
    assert leg.strike == Decimal("23000")


def test_find_option_leg_returns_ce_for_call_key() -> None:
    market = _make_chain(ce_strike="24000")
    leg = find_option_leg("NSE_FO|NIFTY24000CE29MAY2026", market)
    assert leg is not None
    assert leg.strike == Decimal("24000")


def test_find_option_leg_returns_none_for_absent_strike() -> None:
    market = _make_chain(pe_strike="23000")
    # 22000 is not in the chain
    leg = find_option_leg("NSE_FO|NIFTY22000PE29MAY2026", market)
    assert leg is None


def test_find_option_leg_returns_none_and_logs_warning_for_unparseable_key() -> None:
    market = _make_chain()
    with capture_logs() as cap:
        leg = find_option_leg("NSE_EQ|RELIANCE", market)
    assert leg is None
    assert any("key_not_parseable" in e.get("event", "") for e in cap)


def test_find_option_leg_case_insensitive() -> None:
    """Key with lowercase 'pe' should still resolve."""
    market = _make_chain(pe_strike="23000")
    leg = find_option_leg("NSE_FO|nifty23000pe29MAY2026", market)
    assert leg is not None


# ── find_option_leg — real numeric Upstox keys via BOD lookup fallback ────────


class _FakeLookup:
    """Minimal stand-in for InstrumentLookup.get_by_key()."""

    def __init__(self, instruments: dict[str, dict[str, object]]) -> None:
        self._instruments = instruments

    def get_by_key(self, instrument_key: str) -> dict[str, object] | None:
        return self._instruments.get(instrument_key)


def test_find_option_leg_resolves_real_numeric_key_via_bod_lookup() -> None:
    """Real Upstox keys (e.g. NSE_FO|65900) carry no strike/type in the key
    string and must fall back to BOD JSON resolution — this is the case that
    broke AUTO-CLOSE for overlay_collar_call in production."""
    market = _make_chain(ce_strike="24000")
    lookup = _FakeLookup({"NSE_FO|65900": {"instrument_type": "CE", "strike_price": 24000.0}})
    leg = find_option_leg("NSE_FO|65900", market, lookup=lookup)
    assert leg is not None
    assert leg.strike == Decimal("24000")


def test_find_option_leg_numeric_key_without_lookup_returns_none() -> None:
    """No lookup injected → numeric key can never resolve (matches pre-fix
    behaviour for callers that don't pass a lookup)."""
    market = _make_chain(ce_strike="24000")
    with capture_logs() as cap:
        leg = find_option_leg("NSE_FO|65900", market)
    assert leg is None
    assert any("key_not_parseable" in e.get("event", "") for e in cap)


def test_find_option_leg_bod_lookup_key_not_found() -> None:
    market = _make_chain(ce_strike="24000")
    lookup = _FakeLookup({})  # instrument_key absent from BOD JSON
    with capture_logs() as cap:
        leg = find_option_leg("NSE_FO|99999", market, lookup=lookup)
    assert leg is None
    assert any("bod_lookup_failed" in e.get("event", "") for e in cap)


def test_find_option_leg_bod_lookup_strike_absent_from_chain() -> None:
    market = _make_chain(ce_strike="24000")
    lookup = _FakeLookup({"NSE_FO|65900": {"instrument_type": "CE", "strike_price": 25000.0}})
    leg = find_option_leg("NSE_FO|65900", market, lookup=lookup)
    assert leg is None


def test_find_option_leg_bod_lookup_non_option_instrument_type() -> None:
    """FUT/EQ instrument types are not option legs — must not resolve."""
    market = _make_chain(ce_strike="24000")
    lookup = _FakeLookup({"NSE_FO|48100": {"instrument_type": "FUT", "strike_price": None}})
    with capture_logs() as cap:
        leg = find_option_leg("NSE_FO|48100", market, lookup=lookup)
    assert leg is None
    assert any("bod_not_an_option" in e.get("event", "") for e in cap)


# ── resolve_option_expiry (BUG-033) ───────────────────────────────────────────
# CCOverlayV1/PPOverlayV1/CollarOverlayV1._parse_expiry all delegate to this
# helper. Real Upstox instrument keys are numeric-only and never match the
# symbolic-key regex — resolution must fall back to BOD JSON lookup.


def test_resolve_option_expiry_symbolic_key_via_regex() -> None:
    from datetime import date as _date

    from src.strategy._price_utils import resolve_option_expiry

    assert resolve_option_expiry("NSE_FO|NIFTY29MAY2026PE") == _date(2026, 5, 29)


def test_resolve_option_expiry_resolves_real_numeric_key_via_bod_lookup() -> None:
    from src.strategy._price_utils import resolve_option_expiry

    lookup = _FakeLookup({"NSE_FO|61604": {"expiry": "2026-08-25"}})
    assert resolve_option_expiry("NSE_FO|61604", lookup=lookup) == date(2026, 8, 25)


def test_resolve_option_expiry_resolves_epoch_ms_expiry_via_bod_lookup() -> None:
    from datetime import datetime, timezone

    from src.strategy._price_utils import resolve_option_expiry

    expiry_dt = datetime(2026, 8, 25, tzinfo=timezone.utc)
    epoch_ms = int(expiry_dt.timestamp() * 1000)
    lookup = _FakeLookup({"NSE_FO|61604": {"expiry": epoch_ms}})
    assert resolve_option_expiry("NSE_FO|61604", lookup=lookup) == date(2026, 8, 25)


def test_resolve_option_expiry_numeric_key_without_lookup_returns_none() -> None:
    from src.strategy._price_utils import resolve_option_expiry

    with capture_logs() as cap:
        result = resolve_option_expiry("NSE_FO|61604")
    assert result is None
    assert any("key_not_parseable" in e.get("event", "") for e in cap)


def test_resolve_option_expiry_numeric_key_not_in_bod_returns_none() -> None:
    from src.strategy._price_utils import resolve_option_expiry

    lookup = _FakeLookup({})
    with capture_logs() as cap:
        result = resolve_option_expiry("NSE_FO|61604", lookup=lookup)
    assert result is None
    assert any("bod_lookup_failed" in e.get("event", "") for e in cap)


def test_resolve_option_expiry_regex_wins_over_bod_when_both_resolvable() -> None:
    """Symbolic key still resolves via regex even when a (deliberately wrong)
    BOD entry is also present — no behavior change for existing text-format
    fixtures once the fallback was added."""
    from datetime import date as _date

    from src.strategy._price_utils import resolve_option_expiry

    lookup = _FakeLookup({"NSE_FO|NIFTY29MAY2026PE": {"expiry": "2099-01-01"}})
    assert resolve_option_expiry("NSE_FO|NIFTY29MAY2026PE", lookup=lookup) == _date(2026, 5, 29)


def test_resolve_option_expiry_bod_entry_missing_expiry_field_returns_none() -> None:
    """BOD record found but has no usable `expiry` field (None/unparseable) —
    must degrade to None, not raise."""
    from src.strategy._price_utils import resolve_option_expiry

    lookup = _FakeLookup({"NSE_FO|61604": {"expiry": None}})
    with capture_logs() as cap:
        result = resolve_option_expiry("NSE_FO|61604", lookup=lookup)
    assert result is None
    assert any("bod_no_expiry_field" in e.get("event", "") for e in cap)


def test_resolve_option_expiry_bod_bad_expiry_string_returns_none() -> None:
    """A malformed (non-ISO) expiry string from BOD must degrade to None,
    not raise ValueError out of the tick loop."""
    from src.strategy._price_utils import resolve_option_expiry

    lookup = _FakeLookup({"NSE_FO|61604": {"expiry": "not-a-date"}})
    with capture_logs() as cap:
        result = resolve_option_expiry("NSE_FO|61604", lookup=lookup)
    assert result is None
    assert any("bod_bad_expiry" in e.get("event", "") for e in cap)
