"""Tests for IronCondorV2 entry logic — IC-V2-1.

Covers: _select_short_put, _select_short_call, _select_long_wing (floors),
_sd_sanity_check, and the full enter() happy/skip paths.

No network calls. All chains are constructed in-memory from OptionLeg fixtures.
"""

from __future__ import annotations

import datetime
import re
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

import structlog.testing

from src.market_calendar.holidays import market_today
from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.strategy.ic_expiry_config_v2 import IC_V2_MONTHLY
from src.strategy.ic_nifty_v2 import IronCondorV2, PositionUpdate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _leg(
    strike: str,
    delta: str | None,
    ltp: str = "50",
    oi: int = 100_000,
    bid: str = "49",
    ask: str = "51",
    iv: str | None = "15.0",
) -> OptionLeg:
    """Build a minimal OptionLeg for testing."""
    return OptionLeg(
        ltp=Decimal(ltp),
        bid=Decimal(bid),
        ask=Decimal(ask),
        oi=oi,
        volume=10_000,
        delta=Decimal(delta) if delta is not None else None,
        gamma=None,
        theta=None,
        vega=None,
        iv=Decimal(iv) if iv is not None else None,
        strike=Decimal(strike),
    )


def _chain(
    strikes: dict[str, tuple[OptionLeg | None, OptionLeg | None]],
    spot: str = "24500",
    expiry: datetime.date | None = None,
) -> OptionChain:
    """Build OptionChain from {strike_str: (ce_leg, pe_leg)} mapping."""
    return OptionChain(
        underlying_spot=Decimal(spot),
        expiry=expiry or datetime.date(2026, 7, 31),
        strikes={Decimal(k): OptionChainStrike(ce=ce, pe=pe) for k, (ce, pe) in strikes.items()},
    )


@contextmanager
def _patch_bod():
    """Patch the BOD instrument lookup used by _resolve_instrument_key (BUG-024).

    Resolved keys are numeric-style (``NSE_FO|NIFTY<strike><CE|PE>``, matching
    production shape) and keyed off the strike/option_type passed to
    ``search_options`` so per-leg assertions still work unchanged.
    """
    with patch("src.instruments.lookup.InstrumentLookup.from_file") as mock_from_file:
        lookup = MagicMock()
        lookup.search_options.side_effect = lambda **kwargs: [
            {"instrument_key": f"NSE_FO|NIFTY{int(kwargs['strike'])}{kwargs['option_type']}"}
        ]
        mock_from_file.return_value = lookup
        yield lookup


def _standard_chain() -> OptionChain:
    """A realistic 4-strike chain covering the full IC structure.

    Short put  ~25Δ → 23900PE  (|delta|=0.25)
    Short call ~22Δ → 25100CE  (|delta|=0.22)
    Long put   ~10Δ → 23200PE  (|delta|=0.10)  mid=50 (bid=49,ask=51) → passes premium floor
    Long call  ~10Δ → 25800CE  (|delta|=0.10)  same
    """
    return _chain(
        {
            "23900": (None, _leg("23900", "-0.25", ltp="120", bid="119", ask="121")),
            "25100": (_leg("25100", "0.22", ltp="100", bid="99", ask="101"), None),
            "23200": (None, _leg("23200", "-0.10", ltp="50", bid="49", ask="51")),
            "25800": (_leg("25800", "0.10", ltp="50", bid="49", ask="51"), None),
            # ATM strike for IV reference
            "24500": (
                _leg("24500", "0.50", ltp="200", bid="199", ask="201"),
                _leg("24500", "-0.50", ltp="200", bid="199", ask="201"),
            ),
        }
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEnterHappyPath:
    def test_enter_happy_path(self) -> None:
        """Valid chain → both shorts selected, wings pass all floors → PositionUpdate with 4 legs."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        chain = _standard_chain()

        with _patch_bod():
            result = strategy.enter(chain)

        assert isinstance(result, PositionUpdate)
        assert len(result.legs) == 4

        roles = {leg.leg_role for leg in result.legs}
        assert roles == {"short_put", "short_call", "long_put_hedge", "long_call_hedge"}

    def test_enter_happy_path_logs_entry_recorded(self) -> None:
        """Successful entry emits ic_nifty_v2.entry_recorded at info level."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        chain = _standard_chain()

        with _patch_bod(), structlog.testing.capture_logs() as cap:
            result = strategy.enter(chain)

        assert result is not None
        events = [e["event"] for e in cap]
        assert "ic_nifty_v2.entry_recorded" in events

    def test_enter_returns_positive_credit(self) -> None:
        """Entry credit (shorts - longs) should be positive on a standard chain."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        chain = _standard_chain()

        with _patch_bod():
            result = strategy.enter(chain)

        assert result is not None
        assert result.total_credit_pts > Decimal("0")

    def test_enter_short_put_strike_less_than_short_call_strike(self) -> None:
        """Structural invariant: short put strike < short call strike (put is lower)."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        chain = _standard_chain()

        with _patch_bod():
            result = strategy.enter(chain)

        assert result is not None
        sp_leg = next(lg for lg in result.legs if lg.leg_role == "short_put")
        sc_leg = next(lg for lg in result.legs if lg.leg_role == "short_call")

        # Extract strikes from instrument_key "NSE_FO|NIFTYNNNNPE"
        sp_strike = Decimal(re.search(r"NIFTY(\d+)PE", sp_leg.instrument_key).group(1))  # type: ignore[union-attr]
        sc_strike = Decimal(re.search(r"NIFTY(\d+)CE", sc_leg.instrument_key).group(1))  # type: ignore[union-attr]
        assert sp_strike < sc_strike


class TestEnterSkips:
    def test_enter_skips_when_no_put_in_delta_range(self) -> None:
        """No PE within ±0.03 of 0.25Δ → entry skipped (returns None)."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        # Only puts far outside the 25Δ band
        chain = _chain(
            {
                "24000": (_leg("24000", "0.22", ltp="100", bid="99", ask="101"), None),
                "23900": (
                    None,
                    _leg("23900", "-0.10", ltp="50", bid="49", ask="51"),
                ),  # too far OTM
                "23200": (None, _leg("23200", "-0.08", ltp="30", bid="29", ask="31")),
                "25800": (_leg("25800", "0.10", ltp="50", bid="49", ask="51"), None),
            }
        )
        result = strategy.enter(chain)
        assert result is None

    def test_enter_skips_when_no_call_in_delta_range(self) -> None:
        """No CE within ±0.03 of 0.22Δ → entry skipped (returns None)."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        chain = _chain(
            {
                "23900": (None, _leg("23900", "-0.25", ltp="120", bid="119", ask="121")),
                "25100": (
                    _leg("25100", "0.40", ltp="200", bid="199", ask="201"),
                    None,
                ),  # too close to ATM
                "23200": (None, _leg("23200", "-0.10", ltp="50", bid="49", ask="51")),
                "25800": (_leg("25800", "0.10", ltp="50", bid="49", ask="51"), None),
            }
        )
        result = strategy.enter(chain)
        assert result is None

    def test_enter_skips_when_wing_premium_below_floor(self) -> None:
        """Long put wing mid < ₹15 → entry skipped (premium floor miss)."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        # Long put wing priced at ₹5 (bid=4, ask=6, mid=5) — below ₹15 floor
        chain = _chain(
            {
                "23900": (None, _leg("23900", "-0.25", ltp="120", bid="119", ask="121")),
                "25100": (_leg("25100", "0.22", ltp="100", bid="99", ask="101"), None),
                "23200": (None, _leg("23200", "-0.10", ltp="5", bid="4", ask="6")),  # cheap wing
                "25800": (_leg("25800", "0.10", ltp="50", bid="49", ask="51"), None),
            }
        )
        result = strategy.enter(chain)
        assert result is None

    def test_enter_skips_when_wing_liquidity_gate_fails(self) -> None:
        """Long wing bid/ask spread > 5% of mid → entry skipped (liquidity gate miss)."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        # Put wing: bid=40, ask=60 → mid=50, spread_pct=20/50=0.40 > 0.05
        chain = _chain(
            {
                "23900": (None, _leg("23900", "-0.25", ltp="120", bid="119", ask="121")),
                "25100": (_leg("25100", "0.22", ltp="100", bid="99", ask="101"), None),
                "23200": (
                    None,
                    _leg("23200", "-0.10", ltp="50", bid="40", ask="60"),
                ),  # wide spread
                "25800": (_leg("25800", "0.10", ltp="50", bid="49", ask="51"), None),
            }
        )
        with structlog.testing.capture_logs() as cap:
            result = strategy.enter(chain)

        assert result is None
        skip_events = [e for e in cap if e.get("event") == "ic_nifty_v2.entry_skip_wing_floor_miss"]
        assert any(e.get("reason") == "liquidity" for e in skip_events)

    def test_enter_skips_when_wing_delta_below_floor(self) -> None:
        """Long put wing delta 0.03 < 0.05 floor → entry skipped (delta floor miss)."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        # Only wing candidate has delta far below the 0.05 floor
        chain = _chain(
            {
                "23900": (None, _leg("23900", "-0.25", ltp="120", bid="119", ask="121")),
                "25100": (_leg("25100", "0.22", ltp="100", bid="99", ask="101"), None),
                # No PE candidate with abs(delta) in [0.05, 0.20] — only 0.02
                "22000": (None, _leg("22000", "-0.02", ltp="20", bid="19", ask="21")),
                "25800": (_leg("25800", "0.10", ltp="50", bid="49", ask="51"), None),
            }
        )
        result = strategy.enter(chain)
        assert result is None


class TestSdSanityCheck:
    def test_sd_sanity_check_wide_wing_emits_warn(self) -> None:
        """actual_width > 1.5 × sd_width → ic_nifty_v2.entry_sd_warn_wide emitted; entry NOT skipped."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)

        # sd_width = 24500 × 0.15 × sqrt(30/365) × 1.25 ≈ 1316 pts.
        # Wing width 2900 pts (23900-21000) >> 1.5 × 1316 ≈ 1974 → triggers wide warn.
        # Expiry pinned to today+30 (not an absolute date) so `dte` stays 30 regardless
        # of when this test runs — a fixed calendar date drifts toward dte=0 over time
        # and silently invalidates the sd_width math above (see 2026-07-27 investigation,
        # TODOS.md / DECISIONS.md).
        chain = _chain(
            {
                "23900": (None, _leg("23900", "-0.25", ltp="120", bid="119", ask="121")),
                "25100": (_leg("25100", "0.22", ltp="100", bid="99", ask="101"), None),
                "21000": (None, _leg("21000", "-0.10", ltp="25", bid="24.9", ask="25.1")),
                "27000": (_leg("27000", "0.10", ltp="25", bid="24.9", ask="25.1"), None),
                "24500": (
                    _leg("24500", "0.50", ltp="200", bid="199", ask="201"),
                    _leg("24500", "-0.50", ltp="200", bid="199", ask="201"),
                ),
            },
            expiry=market_today() + datetime.timedelta(days=30),
        )

        with _patch_bod(), structlog.testing.capture_logs() as cap:
            result = strategy.enter(chain)

        # Entry proceeds (warn only — never blocks)
        assert result is not None
        events = [e["event"] for e in cap]
        assert "ic_nifty_v2.entry_sd_warn_wide" in events

    def test_sd_sanity_check_tight_wing_emits_warn(self) -> None:
        """actual_width < 0.4 × sd_width → ic_nifty_v2.entry_sd_warn_tight emitted; entry NOT skipped."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)

        # sd_width ≈ 1316 pts. Wing width 200 pts (24300-24100) < 0.4 × 1316 ≈ 526 → triggers tight warn.
        # Expiry pinned to today+30 (not an absolute date) — see wide-wing test above for why:
        # a fixed calendar date drifts toward dte=0 and silently shrinks sd_width until this
        # threshold stops firing (confirmed root cause of the 2026-07-27 failure).
        chain = _chain(
            {
                "24300": (None, _leg("24300", "-0.25", ltp="120", bid="119", ask="121")),
                "24700": (_leg("24700", "0.22", ltp="100", bid="99", ask="101"), None),
                "24100": (None, _leg("24100", "-0.10", ltp="25", bid="24.9", ask="25.1")),
                "24900": (_leg("24900", "0.10", ltp="25", bid="24.9", ask="25.1"), None),
                "24500": (
                    _leg("24500", "0.50", ltp="200", bid="199", ask="201"),
                    _leg("24500", "-0.50", ltp="200", bid="199", ask="201"),
                ),
            },
            expiry=market_today() + datetime.timedelta(days=30),
        )

        with _patch_bod(), structlog.testing.capture_logs() as cap:
            result = strategy.enter(chain)

        # Entry proceeds (warn only — never blocks)
        assert result is not None
        events = [e["event"] for e in cap]
        assert "ic_nifty_v2.entry_sd_warn_tight" in events


# ---------------------------------------------------------------------------
# BUG-024: entry-side instrument_key resolution
# ---------------------------------------------------------------------------


class TestEnterInstrumentKeyResolution:
    def test_enter_all_four_legs_resolve_via_bod_returns_real_keys(self) -> None:
        """All 4 legs resolve through BOD -> PositionUpdate carries real
        numeric-style instrument_keys (not the old fabricated symbol keys)."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        chain = _standard_chain()

        with _patch_bod():
            result = strategy.enter(chain)

        assert isinstance(result, PositionUpdate)
        assert len(result.legs) == 4
        for leg in result.legs:
            assert leg.instrument_key is not None
            assert leg.instrument_key.startswith("NSE_FO|NIFTY")

    def test_enter_one_leg_missing_from_bod_returns_none(self) -> None:
        """One leg's strike absent from BOD for the resolved expiry -> enter()
        returns None (skip the whole entry), never a partial position."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        chain = _standard_chain()

        with patch("src.instruments.lookup.InstrumentLookup.from_file") as mock_from_file:
            lookup = MagicMock()

            def _search_options(**kwargs):
                # Simulate the short-put leg (23900 PE) missing from BOD;
                # every other leg resolves normally.
                if int(kwargs["strike"]) == 23900 and kwargs["option_type"] == "PE":
                    return []
                return [
                    {
                        "instrument_key": f"NSE_FO|NIFTY{int(kwargs['strike'])}{kwargs['option_type']}"
                    }
                ]

            lookup.search_options.side_effect = _search_options
            mock_from_file.return_value = lookup

            with structlog.testing.capture_logs() as cap:
                result = strategy.enter(chain)

        assert result is None
        events = [e["event"] for e in cap]
        assert "ic_nifty_v2.entry_key_resolution_failed" in events
