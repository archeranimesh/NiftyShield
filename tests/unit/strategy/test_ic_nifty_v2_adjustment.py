"""Tests for IronCondorV2 adjustment logic — IC-V2-2.

Covers: _evaluate_adjustment, _execute_partial_roll, and all 7 roll guards.
Signal hierarchy: DELTA_WARN / ROLL_WING / DELTA_STOP / FORCED_CLOSE.

No network calls. All chains and positions constructed in-memory.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import structlog.testing

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import PaperPosition
from src.strategy.ic_expiry_config_v2 import IC_V2_MONTHLY
from src.strategy.ic_nifty_v2 import IronCondorV2

# ---------------------------------------------------------------------------
# Fixtures — chain and position builders
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
    """Minimal OptionLeg for testing."""
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


def _pos(
    leg_role: str,
    instrument_key: str,
    avg_cost: str = "0",
    avg_sell_price: str = "100",
    net_qty: int = -1,
) -> PaperPosition:
    """Build a minimal PaperPosition for testing."""
    return PaperPosition(
        strategy_name="paper_ic_nifty_v2_monthly",
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal(avg_cost),
        avg_sell_price=Decimal(avg_sell_price),
        instrument_key=instrument_key,
    )


def _standard_ic_positions() -> list[PaperPosition]:
    """Represent a standard IC position:
    short_put @ 23900, long_put_hedge @ 23200
    short_call @ 25100, long_call_hedge @ 25800
    """
    return [
        _pos("short_put", "NSE_FO|NIFTY23900PE", avg_sell_price="120"),
        _pos("long_put_hedge", "NSE_FO|NIFTY23200PE", avg_cost="50", net_qty=1),
        _pos("short_call", "NSE_FO|NIFTY25100CE", avg_sell_price="100"),
        _pos("long_call_hedge", "NSE_FO|NIFTY25800CE", avg_cost="50", net_qty=1),
    ]


def _healthy_chain() -> OptionChain:
    """Chain where short deltas are well within safe zone (|delta| < 0.30).

    Used for the 'no signal' baseline.
    """
    return _chain(
        {
            # Current short put at 23900 with benign delta 0.20
            "23900": (None, _leg("23900", "-0.20", ltp="80", bid="79", ask="81")),
            # Current short call at 25100 with benign delta 0.18
            "25100": (_leg("25100", "0.18", ltp="70", bid="69", ask="71"), None),
            # Long wings — untouched in this chain context
            "23200": (None, _leg("23200", "-0.10", ltp="30", bid="29", ask="31")),
            "25800": (_leg("25800", "0.10", ltp="30", bid="29", ask="31"), None),
        }
    )


def _challenged_put_chain(put_delta: str = "-0.36") -> OptionChain:
    """Chain where short put is challenged (|delta| = 0.36, above 0.35 trigger).

    Also includes a replacement short put at 25Δ and a valid 10Δ long wing
    so all guards (except those we explicitly break in specific tests) pass.

    Note: bid/ask must satisfy spread ≤ 5% of mid (liquidity gate).
    For ltp=30: bid=29.25, ask=30.75 → spread=1.5/30=0.05 exactly (passes).
    For ltp=100: bid=97.5, ask=102.5 → spread=5/100=0.05 (passes).
    """
    return _chain(
        {
            # Challenged short put position
            "23900": (None, _leg("23900", put_delta, ltp="160", bid="159", ask="161")),
            # Replacement short put at 25Δ (farther OTM) — tight spread
            "23500": (None, _leg("23500", "-0.25", ltp="100", bid="97.5", ask="102.5")),
            # Replacement long put wing at 10Δ — tight spread, passes all floors
            # spread_pct = 1.5/30 = 0.05 exactly — passes the gate
            "22800": (None, _leg("22800", "-0.10", ltp="30", bid="29.25", ask="30.75")),
            # Existing long put hedge position (at 23200 per _standard_ic_positions)
            # Must appear in chain so _find_leg can resolve it for guard 5 (debit cap)
            "23200": (None, _leg("23200", "-0.04", ltp="30", bid="29.25", ask="30.75")),
            # Short call and long call (profitable side — untouched)
            "25100": (_leg("25100", "0.18", ltp="70", bid="69", ask="71"), None),
            "25800": (_leg("25800", "0.10", ltp="30", bid="29.25", ask="30.75"), None),
        }
    )


# ---------------------------------------------------------------------------
# Tests — DELTA_WARN
# ---------------------------------------------------------------------------


class TestDeltaWarn:
    def test_delta_warn_fires_at_0_30(self) -> None:
        """Short put |delta| = 0.31 → DELTA_WARN, no roll attempted."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        chain = _chain(
            {
                "23900": (None, _leg("23900", "-0.31", ltp="130", bid="129", ask="131")),
                "25100": (_leg("25100", "0.18", ltp="70", bid="69", ask="71"), None),
                "23200": (None, _leg("23200", "-0.10", ltp="30", bid="29", ask="31")),
                "25800": (_leg("25800", "0.10", ltp="30", bid="29", ask="31"), None),
            }
        )
        positions = _standard_ic_positions()

        with structlog.testing.capture_logs() as cap:
            result = strategy._evaluate_adjustment(positions, chain, dte=20, expiry="2026-07-31")

        assert result is not None
        assert result.signal_type == "DELTA_WARN"
        assert result.side == "put"
        assert result.roll_update is None
        # Log event fired
        events = [e["event"] for e in cap]
        assert "ic_nifty_v2.delta_warn" in events

    def test_no_signal_when_deltas_healthy(self) -> None:
        """All short deltas < 0.30 → no signal (returns None)."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        positions = _standard_ic_positions()

        result = strategy._evaluate_adjustment(
            positions, _healthy_chain(), dte=20, expiry="2026-07-31"
        )

        assert result is None


# ---------------------------------------------------------------------------
# Tests — ROLL_WING (all guards pass)
# ---------------------------------------------------------------------------


class TestRollWing:
    def test_roll_wing_fires_at_0_35_all_guards_pass(self) -> None:
        """Short put |delta| = 0.36, all 7 guards pass → ROLL_WING with 4-leg update."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        strategy.set_original_credit(Decimal("150"))  # generous credit → debit cap easy to pass
        positions = _standard_ic_positions()
        chain = _challenged_put_chain(put_delta="-0.36")

        with structlog.testing.capture_logs() as cap:
            result = strategy._evaluate_adjustment(positions, chain, dte=20, expiry="2026-07-31")

        assert result is not None
        assert result.signal_type == "ROLL_WING"
        assert result.side == "put"
        assert result.roll_update is not None

        # Exactly 4 legs in the roll update
        legs = result.roll_update.legs
        assert len(legs) == 4

        # Verify leg roles: 2 closes (BUY short, SELL long) + 2 opens (SELL short, BUY long)
        roles = {leg.leg_role for leg in legs}
        assert roles == {"short_put", "long_put_hedge"}

        actions = [leg.action for leg in legs]
        assert actions.count("BUY") == 2
        assert actions.count("SELL") == 2

        # Profitable call side must NOT appear in the roll legs
        for leg in legs:
            assert "call" not in leg.leg_role

        # Roll executed event logged
        events = [e["event"] for e in cap]
        assert "ic_nifty_v2.roll_wing_executed" in events

    def test_profitable_side_untouched(self) -> None:
        """Only challenged vertical legs appear in roll update — call side NOT touched."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        strategy.set_original_credit(Decimal("150"))
        positions = _standard_ic_positions()
        chain = _challenged_put_chain(put_delta="-0.36")

        result = strategy._evaluate_adjustment(positions, chain, dte=20, expiry="2026-07-31")

        assert result is not None and result.roll_update is not None
        for leg in result.roll_update.legs:
            assert leg.leg_role in {"short_put", "long_put_hedge"}, (
                f"Unexpected leg_role in roll update: {leg.leg_role}"
            )


# ---------------------------------------------------------------------------
# Tests — DELTA_STOP (roll attempted but blocked → escalation)
# ---------------------------------------------------------------------------


class TestDeltaStop:
    def test_roll_blocked_by_wing_floor_miss_escalates_to_delta_stop(self) -> None:
        """Wing floor miss → roll blocked → DELTA_STOP returned."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        strategy.set_original_credit(Decimal("150"))
        positions = _standard_ic_positions()
        # Chain: short put at 0.36 (trigger), replacement short at 0.25,
        # but replacement long wing has premium BELOW the ₹15 floor → wing_floor_miss
        chain = _chain(
            {
                "23900": (None, _leg("23900", "-0.36", ltp="160", bid="159", ask="161")),
                "23500": (None, _leg("23500", "-0.25", ltp="100", bid="99", ask="101")),
                "22800": (None, _leg("22800", "-0.10", ltp="5", bid="4", ask="6")),  # cheap → fails
                "25100": (_leg("25100", "0.18", ltp="70", bid="69", ask="71"), None),
                "25800": (_leg("25800", "0.10", ltp="30", bid="29", ask="31"), None),
            }
        )

        with structlog.testing.capture_logs() as cap:
            result = strategy._evaluate_adjustment(positions, chain, dte=20, expiry="2026-07-31")

        assert result is not None
        assert result.signal_type == "DELTA_STOP"
        assert result.roll_update is None
        events = [e["event"] for e in cap]
        assert "ic_nifty_v2.delta_stop" in events
        guard_fails = [e for e in cap if e.get("event") == "ic_nifty_v2.roll_guard_failed"]
        assert any(e.get("guard") == "wing_floor_miss" for e in guard_fails)

    def test_roll_debit_cap_blocks_roll_escalates_to_delta_stop(self) -> None:
        """Roll debit > 50% of original credit → debit_cap guard fires → DELTA_STOP."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        # Set tiny original credit so the roll debit easily exceeds the 50% cap.
        # old_short ltp=160, old_long (at 23200) ltp=30 → close debit = 130
        # new_short ltp=100, new_long ltp=30 → open credit = 70
        # roll_debit = 130 - 70 = 60 >> 50% of 10 = 5 → blocked
        strategy.set_original_credit(Decimal("10"))  # tiny → 50% cap = 5 pts
        positions = _standard_ic_positions()  # old put spread: 23900 - 23200 = 700 pts
        # Use a chain where all other guards (wing floor, width) pass:
        # new spread: 23500 - 22800 = 700 pts (same as original → passes width_expansion)
        # wing at 22800: ltp=30, bid=29.25 ask=30.75 → spread_pct=0.05 → passes liquidity
        chain = _challenged_put_chain(put_delta="-0.36")

        with structlog.testing.capture_logs() as cap:
            result = strategy._evaluate_adjustment(positions, chain, dte=20, expiry="2026-07-31")

        assert result is not None
        assert result.signal_type == "DELTA_STOP"
        guard_fails = [e for e in cap if e.get("event") == "ic_nifty_v2.roll_guard_failed"]
        assert any(e.get("guard") == "debit_cap" for e in guard_fails)

    def test_inverted_condor_guard_blocks_roll(self) -> None:
        """New put short would cross existing call short strike → inverted_condor guard → DELTA_STOP."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        strategy.set_original_credit(Decimal("150"))
        positions = _standard_ic_positions()
        # Replacement put short at 23500: but call short is at 25100 (fine normally).
        # Force inverted by setting replacement short to 25200 (> existing call short 25100).
        # Build a chain where the "replacement" 25Δ put is at 25200 (ITM, crosses call)
        chain = _chain(
            {
                "23900": (None, _leg("23900", "-0.36", ltp="160", bid="159", ask="161")),
                # Replacement put SHORT at 25200 — above existing call short (25100) → inverted
                "25200": (None, _leg("25200", "-0.25", ltp="200", bid="199", ask="201")),
                # Long put wing (passes floors: ltp=50, spread=2/50=4% < 5%)
                "24900": (None, _leg("24900", "-0.10", ltp="50", bid="48.75", ask="51.25")),
                # Old long put hedge — MUST be present so guard 5 can price the roll.
                # ltp=30 → close_debit=160-30=130; open_credit=200-50=150; roll_debit=-20 (net credit)
                # → roll_debit well within 50% cap → guard 5 passes → guard 7 fires.
                "23200": (None, _leg("23200", "-0.04", ltp="30", bid="29.25", ask="30.75")),
                # Call short and long — both OTM
                "25100": (_leg("25100", "0.18", ltp="70", bid="69", ask="71"), None),
                "25800": (_leg("25800", "0.10", ltp="30", bid="29.25", ask="30.75"), None),
            }
        )

        with structlog.testing.capture_logs() as cap:
            result = strategy._evaluate_adjustment(positions, chain, dte=20, expiry="2026-07-31")

        assert result is not None
        assert result.signal_type == "DELTA_STOP"
        guard_fails = [e for e in cap if e.get("event") == "ic_nifty_v2.roll_guard_failed"]
        assert any(e.get("guard") == "inverted_condor" for e in guard_fails)

    def test_width_expansion_guard_blocks_roll(self) -> None:
        """New spread width > original spread width → width_expansion guard → DELTA_STOP."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        strategy.set_original_credit(Decimal("150"))
        positions = _standard_ic_positions()  # old put spread: 23900 - 23200 = 700 pts

        # New spread: short at 23500, long at 22000 → width = 1500 pts > 700 → blocked
        # IMPORTANT: long wing at 22000 must pass the liquidity gate (spread ≤ 5%)
        # and premium floor (≥ ₹15). ltp=30 bid=29.25 ask=30.75 → passes.
        chain = _chain(
            {
                "23900": (None, _leg("23900", "-0.36", ltp="160", bid="159", ask="161")),
                "23500": (None, _leg("23500", "-0.25", ltp="100", bid="97.5", ask="102.5")),
                # Long wing very far OTM → new width = 1500 pts >> original 700 → blocked
                # Must pass premium + liquidity floors so only width guard fires
                "22000": (None, _leg("22000", "-0.10", ltp="30", bid="29.25", ask="30.75")),
                # Old long put hedge at 23200 (needed so _find_leg resolves for debit-cap check)
                "23200": (None, _leg("23200", "-0.04", ltp="30", bid="29.25", ask="30.75")),
                "25100": (_leg("25100", "0.18", ltp="70", bid="69", ask="71"), None),
                "25800": (_leg("25800", "0.10", ltp="30", bid="29.25", ask="30.75"), None),
            }
        )

        with structlog.testing.capture_logs() as cap:
            result = strategy._evaluate_adjustment(positions, chain, dte=20, expiry="2026-07-31")

        assert result is not None
        assert result.signal_type == "DELTA_STOP"
        guard_fails = [e for e in cap if e.get("event") == "ic_nifty_v2.roll_guard_failed"]
        assert any(e.get("guard") == "width_expansion" for e in guard_fails)


# ---------------------------------------------------------------------------
# Tests — FORCED_CLOSE
# ---------------------------------------------------------------------------


class TestForcedClose:
    def test_forced_close_at_0_45(self) -> None:
        """|short_delta| ≥ 0.45 → FORCED_CLOSE regardless of all other guards."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        positions = _standard_ic_positions()
        chain = _chain(
            {
                "23900": (None, _leg("23900", "-0.46", ltp="250", bid="249", ask="251")),
                "25100": (_leg("25100", "0.18", ltp="70", bid="69", ask="71"), None),
                "23200": (None, _leg("23200", "-0.10", ltp="30", bid="29", ask="31")),
                "25800": (_leg("25800", "0.10", ltp="30", bid="29", ask="31"), None),
            }
        )

        with structlog.testing.capture_logs() as cap:
            result = strategy._evaluate_adjustment(positions, chain, dte=20, expiry="2026-07-31")

        assert result is not None
        assert result.signal_type == "FORCED_CLOSE"
        assert result.roll_update is None
        events = [e["event"] for e in cap]
        assert "ic_nifty_v2.forced_close_delta" in events

    def test_max_rolls_exhausted_forces_close(self) -> None:
        """Second roll attempt (after max_rolls=1 exhausted) → FORCED_CLOSE."""
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        strategy.set_original_credit(Decimal("150"))
        # Simulate: one roll already executed on the put side
        strategy._rolls_executed["put"] = 1  # IC_V2_MONTHLY max_rolls_per_side_per_cycle = 1
        positions = _standard_ic_positions()
        chain = _challenged_put_chain(put_delta="-0.36")  # |delta| in roll zone

        with structlog.testing.capture_logs() as cap:
            result = strategy._evaluate_adjustment(positions, chain, dte=20, expiry="2026-07-31")

        assert result is not None
        assert result.signal_type == "FORCED_CLOSE"
        events = [e["event"] for e in cap]
        assert "ic_nifty_v2.forced_close_rolls_exhausted" in events

    def test_dte_cutoff_blocks_roll_when_roll_not_allowed(self) -> None:
        """roll_allowed_by_dte=False (DTE cutoff) → roll blocked → DELTA_STOP.

        FORCED_CLOSE is NOT returned here: the DTE guard in _execute_partial_roll
        escalates only to DELTA_STOP (caller IC-V2-4 decides whether to close full
        based on DTE tier; the adjustment logic itself only escalates to DELTA_STOP
        when a guard blocks the roll).
        """
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        strategy.set_original_credit(Decimal("150"))
        positions = _standard_ic_positions()
        chain = _challenged_put_chain(put_delta="-0.36")

        with structlog.testing.capture_logs() as cap:
            result = strategy._evaluate_adjustment(
                positions,
                chain,
                dte=5,  # ≤ monthly_close_full_dte; roll_allowed_by_dte=False
                expiry="2026-07-31",
                roll_allowed_by_dte=False,
            )

        assert result is not None
        assert result.signal_type == "DELTA_STOP"
        guard_fails = [e for e in cap if e.get("event") == "ic_nifty_v2.roll_guard_failed"]
        assert any(e.get("guard") == "dte_cutoff" for e in guard_fails)


# ---------------------------------------------------------------------------
# Tests — chain_data_missing guard (stale / partial snapshot)
# ---------------------------------------------------------------------------


class TestChainDataMissingGuard:
    def test_roll_blocked_when_old_short_absent_from_chain(self) -> None:
        """Old short leg not in live chain → chain_data_missing guard fires → DELTA_STOP.

        This covers the stale-snapshot scenario where the position's instrument
        key is valid but the broker snapshot is partial (near-expiry, circuit, etc.).
        """
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        strategy.set_original_credit(Decimal("150"))
        positions = _standard_ic_positions()  # short_put at NSE_FO|NIFTY23900PE
        # Build a full challenged chain (23900 present for delta signal lookup),
        # then drop 23900 to simulate a stale snapshot for the debit-cap guard.
        trigger_chain = _challenged_put_chain(put_delta="-0.36")
        # Omit 23900 from the debit-cap lookup chain (simulate stale snapshot)
        stale_chain = _chain(
            {
                k: (ce, pe)
                for k, ocs in trigger_chain.strikes.items()
                for ce, pe in [(ocs.ce, ocs.pe)]
                if k != Decimal("23900")
            }
        )
        # Call _execute_partial_roll directly with:
        #  - positions that include short_put at 23900
        #  - stale_chain that omits 23900 (so _find_leg returns None)
        update, block = strategy._execute_partial_roll(
            side="put",
            positions=positions,
            market=stale_chain,
            dte=20,
            expiry="2026-07-31",
            roll_allowed_by_dte=True,
            baseline={
                "strategy_name": "test",
                "trade_id": "",
                "expiry": "",
                "dte": 20,
                "roll_count_put": 0,
                "roll_count_call": 0,
                "profit_lock_zone": 0,
            },
        )
        assert update is None
        assert block == "chain_data_missing"


# ---------------------------------------------------------------------------
# Tests — state helpers
# ---------------------------------------------------------------------------


class TestStateHelpers:
    def test_reset_roll_state_clears_counters_and_credit(self) -> None:
        """reset_roll_state() returns _rolls_executed to zero and _original_ic_credit to 0.

        A missed call between entry cycles would carry roll counts forward,
        causing the first ROLL_WING of a new trade to immediately hit FORCED_CLOSE.
        """
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        # Simulate a completed cycle: one roll on each side
        strategy._rolls_executed["put"] = 1
        strategy._rolls_executed["call"] = 1
        strategy.set_original_credit(Decimal("200"))

        strategy.reset_roll_state()

        assert strategy._rolls_executed == {"put": 0, "call": 0}
        assert strategy._original_ic_credit == Decimal("0")

    def test_set_original_credit_zero_skips_debit_cap_guard(self) -> None:
        """set_original_credit(0) causes guard 5 to pass unconditionally (no cap).

        This is the correct behaviour when the original credit was never set
        (e.g. position opened before IC-V2-2 was deployed) — the guard skips
        rather than blocking all rolls for legacy positions.
        """
        strategy = IronCondorV2(config=IC_V2_MONTHLY)
        strategy.set_original_credit(Decimal("0"))  # credit=0 → cap guard skips
        positions = _standard_ic_positions()
        chain = _challenged_put_chain(put_delta="-0.36")

        result = strategy._evaluate_adjustment(positions, chain, dte=20, expiry="2026-07-31")

        # Roll should succeed (ROLL_WING) despite huge potential debit,
        # because the guard condition is `original_ic_credit > 0`.
        assert result is not None
        assert result.signal_type == "ROLL_WING"
        assert result.roll_update is not None
