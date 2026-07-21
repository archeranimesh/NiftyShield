"""Tests for IC-V2-4: check_signals() signal hierarchy and apply_action().

Verifies PaperStrategy protocol compliance and the full signal evaluation
order: DTE hard stops → delta signals → DTE CLOSE_FULL → profit target → hold.

No network calls. All chains and positions are constructed in-memory.
greeks-analyst gate: mandatory before code-reviewer (IC-V2-4 spec).

Test list (from stories.md IC-V2-4):
  test_no_signal_on_healthy_position
  test_full_pipeline_delta_warn
  test_full_pipeline_roll_wing
  test_full_pipeline_forced_close_delta
  test_full_pipeline_forced_close_dte
  test_full_pipeline_profit_target
  test_protocol_compliance
  test_apply_action_close_full
  test_apply_action_rejects_unknown
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from structlog.testing import capture_logs

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import PaperPosition
from src.strategy.ic_expiry_config_v2 import IC_V2_MONTHLY
from src.strategy.ic_nifty_v2 import IronCondorV2
from src.strategy.protocol import ApprovedAction, PaperStrategy

# ── Fixtures ─────────────────────────────────────────────────────────────────

_STRATEGY_NAME = "paper_ic_nifty_v2_monthly"
_EXPIRY = datetime.date(2026, 7, 31)  # used with frozen today = 2026-07-15 (DTE=16)
_FROZEN_TODAY = datetime.date(2026, 7, 15)
# Expiry embedded in instrument key (dd-MON-YYYY prefix after NIFTY)
_EXPIRY_TAG = "31JUL2026"


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
        expiry=expiry or _EXPIRY,
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
        strategy_name=_STRATEGY_NAME,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal(avg_cost),
        avg_sell_price=Decimal(avg_sell_price),
        instrument_key=instrument_key,
    )


def _key(strike: str, option_type: str) -> str:
    """Build compound instrument key with both expiry and strike embedded.

    The format NSE_FO|NIFTY<date>NIFTY<strike><PE|CE> satisfies both regexes:
      - _EXPIRY_RE extracts the dd-MON-YYYY portion from the first NIFTY<date> segment
      - _STRIKE_RE finds NIFTY<strike><PE|CE> as the second NIFTY segment
    This allows check_signals tests to exercise DTE calculation AND chain lookup
    in a single position list, unlike adjustment-only tests which pass DTE directly.
    """
    return f"NSE_FO|NIFTY{_EXPIRY_TAG}NIFTY{strike}{option_type}"


def _strike_key(strike: str, option_type: str) -> str:
    """Plain strike key (no expiry). For non-check_signals test positions."""
    return f"NSE_FO|NIFTY{strike}{option_type}"


def _standard_ic_positions() -> list[PaperPosition]:
    """Standard 4-leg IC: short_put@23900, lp_hedge@23200, short_call@25100, lc_hedge@25800.

    All keys embed the expiry date so _parse_expiry works for DTE calc, and
    also embed the strike so _find_leg chain lookup works for delta evaluation.

    Entry credit per short leg = 100 pts.  Wings cost = 50 pts each.
    Net IC credit = (100 + 100) - (50 + 50) = 100 pts total.
    """
    return [
        _pos("short_put", _key("23900", "PE"), avg_sell_price="100"),
        _pos("long_put_hedge", _key("23200", "PE"), avg_cost="50", net_qty=1),
        _pos("short_call", _key("25100", "CE"), avg_sell_price="100"),
        _pos("long_call_hedge", _key("25800", "CE"), avg_cost="50", net_qty=1),
    ]


def _healthy_chain() -> OptionChain:
    """Chain with short deltas well inside safe zone (|delta| < 0.30)."""
    return _chain(
        {
            "23900": (None, _leg("23900", "-0.20", ltp="80", bid="79", ask="81")),
            "25100": (_leg("25100", "0.18", ltp="70", bid="69", ask="71"), None),
            "23200": (None, _leg("23200", "-0.10", ltp="30", bid="29", ask="31")),
            "25800": (_leg("25800", "0.10", ltp="30", bid="29", ask="31"), None),
        }
    )


def _delta_warn_chain() -> OptionChain:
    """Short put |delta|=0.31 (≥0.30 warn, <0.35 roll) → DELTA_WARN expected."""
    return _chain(
        {
            "23900": (None, _leg("23900", "-0.31", ltp="90", bid="89", ask="91")),
            "25100": (_leg("25100", "0.18", ltp="70", bid="69", ask="71"), None),
            "23200": (None, _leg("23200", "-0.10", ltp="30", bid="29", ask="31")),
            "25800": (_leg("25800", "0.10", ltp="30", bid="29", ask="31"), None),
        }
    )


def _roll_wing_chain() -> OptionChain:
    """Short put |delta|=0.36, valid replacement at 25Δ and 10Δ wing.

    All roll guards pass:
    - replacement short at 23500 (delta=-0.25, within ±0.03 of 0.25Δ target)
    - replacement long at 22800 (delta=-0.10, premium=30, spread_pct=1.5/30=0.05)
    - original spread width = |23900-23200| = 700; new = |23500-22800| = 700 (no expansion)
    - debit cap: assumes original IC credit injected via set_original_credit
    - inverted condor: new put short 23500 < call short 25100 ✓
    """
    return _chain(
        {
            "23900": (None, _leg("23900", "-0.36", ltp="160", bid="159", ask="161")),
            "23500": (None, _leg("23500", "-0.25", ltp="100", bid="97.5", ask="102.5")),
            "22800": (None, _leg("22800", "-0.10", ltp="30", bid="29.25", ask="30.75")),
            "23200": (None, _leg("23200", "-0.04", ltp="30", bid="29.25", ask="30.75")),
            "25100": (_leg("25100", "0.18", ltp="70", bid="69", ask="71"), None),
            "25800": (_leg("25800", "0.10", ltp="30", bid="29", ask="31"), None),
        }
    )


def _forced_close_delta_chain() -> OptionChain:
    """Short put |delta|=0.46 → immediate FORCED_CLOSE (≥ 0.45 threshold)."""
    return _chain(
        {
            "23900": (None, _leg("23900", "-0.46", ltp="200", bid="199", ask="201")),
            "25100": (_leg("25100", "0.18", ltp="70", bid="69", ask="71"), None),
            "23200": (None, _leg("23200", "-0.10", ltp="30", bid="29", ask="31")),
            "25800": (_leg("25800", "0.10", ltp="30", bid="29", ask="31"), None),
        }
    )


def _profit_target_chain() -> OptionChain:
    """Both spreads have decayed; combined mark = 30 (≤ 30% of 100 credit → profit target).

    Entry: shorts collected 100+100=200, wings cost 50+50=100 → net_credit=100 pts.
    Current: shorts ltp=10+10=20, wings ltp=5+5=10 → combined_mark=20-10=10 pts.
    captured = (100-10)/100 = 90% ≥ 70% → profit target fires.
    """
    return _chain(
        {
            "23900": (None, _leg("23900", "-0.08", ltp="10", bid="9.5", ask="10.5")),
            "25100": (_leg("25100", "0.07", ltp="10", bid="9.5", ask="10.5"), None),
            "23200": (None, _leg("23200", "-0.03", ltp="5", bid="4.75", ask="5.25")),
            "25800": (_leg("25800", "0.03", ltp="5", bid="4.75", ask="5.25"), None),
        }
    )


def _make_strategy(original_credit: str = "100") -> IronCondorV2:
    """Return an IronCondorV2 with no external dependencies and preset credit."""
    s = IronCondorV2(config=IC_V2_MONTHLY)
    s.set_original_credit(Decimal(original_credit))
    return s


# ── Tests: check_signals pipeline ────────────────────────────────────────────


def test_no_signal_on_healthy_position() -> None:
    """Short deltas well below 0.30 warn threshold → [] returned.

    Happy-path hold: no action needed, strategy is in a healthy state.
    """
    strategy = _make_strategy()
    with patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY):
        import asyncio

        result = asyncio.run(strategy.check_signals(_healthy_chain(), _standard_ic_positions()))
    assert result == []


def test_mark_unavailable_logged_and_pnl_gate_skipped_on_empty_chain() -> None:
    """BUG-2 follow-up (2026-07-20): a chain missing all legs (e.g. daemon
    fetched the wrong expiry) must log ic_nifty_v2.mark_unavailable per leg
    and ic_nifty_v2.pnl_gate_skipped once, instead of silently returning []
    with no trace of why priorities 4-6 (profit target / profit-lock) never
    evaluated.
    """
    strategy = _make_strategy()
    empty_chain = _chain({}, expiry=_EXPIRY)
    with (
        patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY),
        capture_logs() as logs,
    ):
        import asyncio

        result = asyncio.run(strategy.check_signals(empty_chain, _standard_ic_positions()))

    assert result == []
    unavailable = [e for e in logs if e["event"] == "ic_nifty_v2.mark_unavailable"]
    assert len(unavailable) == 4
    assert {e["leg_role"] for e in unavailable} == {
        "short_put",
        "long_put_hedge",
        "short_call",
        "long_call_hedge",
    }
    skipped = [e for e in logs if e["event"] == "ic_nifty_v2.pnl_gate_skipped"]
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "mark_unavailable"
    assert skipped[0]["strategy"] == _STRATEGY_NAME


def test_mark_unavailable_not_logged_on_healthy_chain() -> None:
    """Happy path — all legs resolve, no warning noise."""
    strategy = _make_strategy()
    with (
        patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY),
        capture_logs() as logs,
    ):
        import asyncio

        asyncio.run(strategy.check_signals(_healthy_chain(), _standard_ic_positions()))

    assert not [e for e in logs if e["event"] == "ic_nifty_v2.mark_unavailable"]
    assert not [e for e in logs if e["event"] == "ic_nifty_v2.pnl_gate_skipped"]


def test_flat_legs_produce_no_signals_and_no_bod_warnings() -> None:
    """2026-07-21: a fully-closed V2 IC (net_qty == 0 on all four legs) must
    be filtered out entirely, not re-resolved against the chain every tick.

    ``PaperStore.get_positions`` still returns one ``PaperPosition`` per
    ``leg_role`` after a leg closes (BUG-014), carrying the now-settled,
    delisted ``instrument_key`` of the closed contract. Without the
    ``net_qty != 0`` filter, ``check_signals`` would call ``_find_leg``/
    ``_compute_combined_pnl`` on that dead key every tick, which can never
    resolve via BOD again — producing permanent ``strike_parse_failed``/
    ``mark_unavailable`` warning noise. Same defect class as the
    ``ic_nifty_v1.py`` fix — see DECISIONS.md 2026-07-21.
    """
    strategy = _make_strategy()
    positions = [
        _pos("short_put", "NSE_FO|51348", net_qty=0),
        _pos("long_put_hedge", "NSE_FO|51340", net_qty=0),
        _pos("short_call", "NSE_FO|51405", net_qty=0),
        _pos("long_call_hedge", "NSE_FO|51417", net_qty=0),
    ]
    with (
        patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY),
        capture_logs() as logs,
    ):
        import asyncio

        result = asyncio.run(strategy.check_signals(_chain({}, expiry=_EXPIRY), positions))

    assert result == []
    assert not [e for e in logs if e["event"] == "ic_nifty_v2.strike_parse_failed"]
    assert not [e for e in logs if e["event"] == "ic_nifty_v2.mark_unavailable"]


def test_flat_legs_excluded_but_open_legs_still_evaluated() -> None:
    """A mix of flat and open legs: only the open legs (net_qty != 0) reach
    the chain-resolution path; the flat leg's dead instrument_key is dropped
    before it can ever trigger a BOD warning, and the still-open legs are
    evaluated normally (healthy chain → no signals).
    """
    strategy = _make_strategy()
    positions = _standard_ic_positions()
    # short_put's cycle already closed and rolled to a dead numeric key —
    # everything else in the IC is still open.
    positions[0] = _pos("short_put", "NSE_FO|51348", net_qty=0)
    with (
        patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY),
        capture_logs() as logs,
    ):
        import asyncio

        result = asyncio.run(strategy.check_signals(_healthy_chain(), positions))

    unavailable = [e for e in logs if e["event"] == "ic_nifty_v2.mark_unavailable"]
    assert not [e for e in unavailable if e.get("leg_role") == "short_put"]
    assert result == []


def test_full_pipeline_delta_warn() -> None:
    """|short_delta| = 0.31 → DELTA_WARN WARN signal, no action needed."""
    strategy = _make_strategy()
    with patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY):
        import asyncio

        result = asyncio.run(strategy.check_signals(_delta_warn_chain(), _standard_ic_positions()))
    assert len(result) == 1
    assert result[0].event_type == "DELTA_WARN"
    assert result[0].severity == "WARN"


def test_full_pipeline_roll_wing() -> None:
    """|short_delta| = 0.36 with all roll guards passing → ROLL_WING ACTION.

    Original IC credit set to 200 pts so the debit cap (50% = 100 pts) passes
    against the 60-pt roll debit computed from the chain prices.
    """
    strategy = _make_strategy(original_credit="200")
    with patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY):
        import asyncio

        result = asyncio.run(strategy.check_signals(_roll_wing_chain(), _standard_ic_positions()))
    assert len(result) == 1
    assert result[0].event_type == "ROLL_WING"
    assert result[0].severity == "ACTION"
    assert result[0].payload.get("auto_execute") is True


def test_full_pipeline_forced_close_delta() -> None:
    """|short_delta| = 0.46 → FORCED_CLOSE ACTION (≥ 0.45, extreme delta)."""
    strategy = _make_strategy()
    with patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY):
        import asyncio

        result = asyncio.run(
            strategy.check_signals(_forced_close_delta_chain(), _standard_ic_positions())
        )
    assert len(result) == 1
    assert result[0].event_type == "FORCED_CLOSE"
    assert result[0].severity == "ACTION"
    assert result[0].payload.get("auto_execute") is True


def test_full_pipeline_forced_close_dte() -> None:
    """DTE=1 → FORCED_CLOSE regardless of delta levels (check_signals returns early).

    Positions are healthy on delta (|delta| < 0.30), but expiry on 2026-07-31
    with today=2026-07-30 gives DTE=1 → FORCE_CLOSE unconditionally.
    """
    strategy = _make_strategy()
    # today = 2026-07-30, _EXPIRY = 2026-07-31 → DTE=1
    frozen_today = datetime.date(2026, 7, 30)
    with patch("src.strategy.ic_nifty_v2.market_today", return_value=frozen_today):
        import asyncio

        result = asyncio.run(strategy.check_signals(_healthy_chain(), _standard_ic_positions()))
    assert len(result) == 1
    assert result[0].event_type == "FORCED_CLOSE"
    assert result[0].payload.get("reason") == "dte_force_close"


def test_full_pipeline_profit_target() -> None:
    """Both spreads decayed to ~10% of original credit → CLOSE_FULL (profit target)."""
    strategy = _make_strategy(original_credit="100")
    with patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY):
        import asyncio

        result = asyncio.run(
            strategy.check_signals(_profit_target_chain(), _standard_ic_positions())
        )
    assert len(result) == 1
    assert result[0].event_type == "CLOSE_FULL"
    assert result[0].severity == "ACTION"
    payload = result[0].payload
    assert "captured_fraction" in payload
    captured = Decimal(payload["captured_fraction"])
    assert captured >= Decimal("0.70"), f"expected ≥70% captured, got {captured}"


def test_protocol_compliance() -> None:
    """IronCondorV2 satisfies the PaperStrategy structural subtype check."""
    assert isinstance(IronCondorV2(), PaperStrategy)


def test_no_positions_returns_empty() -> None:
    """No IC V2 positions in the list → check_signals returns [].

    Edge case: other strategies' positions must not be evaluated.
    """
    strategy = _make_strategy()
    other_pos = PaperPosition(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        net_qty=-1,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("100"),
        instrument_key=_key("23900", "PE"),
    )
    with patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY):
        import asyncio

        result = asyncio.run(strategy.check_signals(_healthy_chain(), [other_pos]))
    assert result == []


# ── Tests: apply_action ───────────────────────────────────────────────────────


def test_apply_action_close_full() -> None:
    """CLOSE_FULL auto-execute removes all 4 IC legs from positions."""
    strategy = _make_strategy()
    positions = _standard_ic_positions()
    action = ApprovedAction(
        action_type="CLOSE_FULL",
        legs_to_close=[],
        legs_to_open=[],
        rationale="auto-execute",
        council_rank=1,
    )
    import asyncio

    result = asyncio.run(strategy.apply_action(positions, action))
    assert result == []


def test_apply_action_close_put_spread() -> None:
    """CLOSE_PUT_SPREAD auto-execute removes short_put + long_put_hedge; keeps call legs."""
    strategy = _make_strategy()
    positions = _standard_ic_positions()
    action = ApprovedAction(
        action_type="CLOSE_PUT_SPREAD",
        legs_to_close=[],
        legs_to_open=[],
        rationale="auto-execute",
        council_rank=1,
    )
    import asyncio

    result = asyncio.run(strategy.apply_action(positions, action))
    remaining_roles = {p.leg_role for p in result}
    assert remaining_roles == {"short_call", "long_call_hedge"}


def test_apply_action_rejects_unknown() -> None:
    """Unsupported action_type raises ValueError immediately."""
    strategy = _make_strategy()
    action = ApprovedAction(
        action_type="OPEN_NEW_IC",
        legs_to_close=[],
        legs_to_open=[],
        rationale="manual",
        council_rank=1,
    )
    import asyncio

    with pytest.raises(ValueError, match="OPEN_NEW_IC"):
        asyncio.run(strategy.apply_action(_standard_ic_positions(), action))


# ── Auto-close persistence (fix for silent no-op — same gap as IronCondorV1:
#    closing fills were never written to paper_trades, so the same exit
#    signal re-fired every tick with no visible error) ─────────────────────


def test_apply_action_close_full_auto_execute_persists_all_legs() -> None:
    """Auto-execute CLOSE_FULL with broker+store injected writes 4 closing trades."""
    import asyncio

    from src.client.protocol import BrokerClient
    from src.paper.store import PaperStore

    broker = MagicMock(spec=BrokerClient)
    from unittest.mock import AsyncMock

    broker.get_ltp = AsyncMock(
        return_value={
            _key("23900", "PE"): Decimal("30.00"),
            _key("23200", "PE"): Decimal("2.00"),
            _key("25100", "CE"): Decimal("28.00"),
            _key("25800", "CE"): Decimal("2.50"),
        }
    )
    store = MagicMock(spec=PaperStore)
    store.record_trades = MagicMock(side_effect=lambda trades: (trades, []))

    strategy = IronCondorV2(config=IC_V2_MONTHLY, broker=broker, store=store)
    strategy.set_original_credit(Decimal("100"))
    positions = _standard_ic_positions()
    action = ApprovedAction(
        action_type="CLOSE_FULL",
        legs_to_close=[],
        legs_to_open=[],
        rationale="auto-execute",
        council_rank=1,
        metadata={"auto_selected": True, "event_type": "LOSS_STOP"},
    )

    result = asyncio.run(strategy.apply_action(positions, action))

    store.record_trades.assert_called_once()
    (written,), _ = store.record_trades.call_args
    assert {t.leg_role for t in written} == {
        "short_put",
        "long_put_hedge",
        "short_call",
        "long_call_hedge",
    }
    assert result == []


def test_apply_action_close_full_auto_execute_sends_close_notification() -> None:
    """BUG-013 (2026-07-20): CLOSE_FULL must confirm via Telegram.

    Previously only PROFIT_LOCK_ZONE2 (a rare partial roll) sent a
    notification — the far more common full-close path was silent. See
    docs/bugs/bugs.md BUG-013.
    """
    import asyncio

    from src.client.protocol import BrokerClient
    from src.paper.store import PaperStore

    broker = MagicMock(spec=BrokerClient)
    from unittest.mock import AsyncMock

    broker.get_ltp = AsyncMock(
        return_value={
            _key("23900", "PE"): Decimal("30.00"),
            _key("23200", "PE"): Decimal("2.00"),
            _key("25100", "CE"): Decimal("28.00"),
            _key("25800", "CE"): Decimal("2.50"),
        }
    )
    store = MagicMock(spec=PaperStore)
    store.record_trades = MagicMock(side_effect=lambda trades: (trades, []))
    notifier = MagicMock()
    notifier.send_notification = AsyncMock()

    strategy = IronCondorV2(config=IC_V2_MONTHLY, broker=broker, store=store, notifier=notifier)
    strategy.set_original_credit(Decimal("100"))
    positions = _standard_ic_positions()
    action = ApprovedAction(
        action_type="CLOSE_FULL",
        legs_to_close=[],
        legs_to_open=[],
        rationale="auto-execute",
        council_rank=1,
        metadata={"auto_selected": True, "event_type": "LOSS_STOP"},
    )

    asyncio.run(strategy.apply_action(positions, action))

    notifier.send_notification.assert_called_once()
    (message,), _ = notifier.send_notification.call_args
    assert "LOSS_STOP" in message
    assert _STRATEGY_NAME in message


def test_apply_action_close_full_auto_execute_without_broker_skips_persist_no_raise() -> None:
    """No broker/store injected → logs and skips persistence, does not raise."""
    import asyncio

    strategy = _make_strategy()  # broker=None, store=None
    positions = _standard_ic_positions()
    action = ApprovedAction(
        action_type="CLOSE_FULL",
        legs_to_close=[],
        legs_to_open=[],
        rationale="auto-execute",
        council_rank=1,
        metadata={"auto_selected": True, "event_type": "LOSS_STOP"},
    )

    result = asyncio.run(strategy.apply_action(positions, action))

    assert result == []


# ── BUG-012: numeric instrument key BOD fallback ─────────────────────────────


def test_find_leg_resolves_numeric_key_via_bod() -> None:
    """Numeric key (no NIFTY<strike><PE|CE> substring) resolves via BOD lookup."""
    strategy = _make_strategy()
    chain = _chain({"23900": (None, _leg("23900", "-0.20"))})

    with patch("src.instruments.lookup.InstrumentLookup.from_file") as mock_from_file:
        lookup = MagicMock()
        lookup.get_by_key.return_value = {
            "strike_price": Decimal("23900"),
            "instrument_type": "PE",
        }
        mock_from_file.return_value = lookup

        leg = strategy._find_leg(chain, "NSE_FO|63930")

    assert leg is not None
    assert leg.strike == Decimal("23900")


def test_find_leg_numeric_key_not_in_bod_returns_none() -> None:
    """Numeric key absent from the BOD master returns None, never raises."""
    strategy = _make_strategy()
    chain = _chain({"23900": (None, _leg("23900", "-0.20"))})

    with patch("src.instruments.lookup.InstrumentLookup.from_file") as mock_from_file:
        lookup = MagicMock()
        lookup.get_by_key.return_value = None
        mock_from_file.return_value = lookup

        leg = strategy._find_leg(chain, "NSE_FO|99999999")

    assert leg is None


def test_position_strike_resolves_numeric_key_via_bod() -> None:
    """_position_strike (used by Zone 2 profit-lock) resolves numeric keys too."""
    strategy = _make_strategy()
    pos = _pos("short_put", "NSE_FO|63930")

    with patch("src.instruments.lookup.InstrumentLookup.from_file") as mock_from_file:
        lookup = MagicMock()
        lookup.get_by_key.return_value = {
            "strike_price": Decimal("23900"),
            "instrument_type": "PE",
        }
        mock_from_file.return_value = lookup

        strike = strategy._position_strike(pos)

    assert strike == Decimal("23900")


def test_position_strike_bod_lookup_raises_returns_none() -> None:
    """A BOD file/lookup failure is caught and degrades to None, never raises."""
    strategy = _make_strategy()
    pos = _pos("short_put", "NSE_FO|63930")

    with patch(
        "src.instruments.lookup.InstrumentLookup.from_file",
        side_effect=OSError("BOD file missing"),
    ):
        strike = strategy._position_strike(pos)

    assert strike is None
