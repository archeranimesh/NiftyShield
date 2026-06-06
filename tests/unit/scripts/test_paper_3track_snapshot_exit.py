"""Unit tests for compute_and_record_exit_signals in paper_3track_snapshot.py.

Coverage:
- CSP short put breaching profit target → PROFIT_TARGET written with detected_by=EOD.
- CC overlay breaching delta stop → DELTA_STOP written.
- PP overlay breaching crash-monetise conditions → CRASH_MONETIZE written.
- Healthy position (no breach) → create_exit_event NOT called.
- Same signal evaluated twice same day → no duplicate (dedup).
- INFO signals → NOT written to DB.
- Multiple positions; only one breaches → only breaching leg creates event.
- Notifier called once per ACTION; once per batched WARN strategy.
- Notifier raises → event still written to DB (non-fatal).
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import scripts.strategies.three_track.paper_3track_snapshot as snap_mod
from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import PaperPosition
from src.paper.store import PaperStore
from src.strategy.exit_signals import ExitSignalEngine

# ── Helpers ───────────────────────────────────────────────────────────────────

_TODAY = date(2026, 6, 3)
_STRATEGY_CSP = "paper_csp_nifty_v1"
_STRATEGY_SPOT = "paper_nifty_spot"

_STRIKE = Decimal("23000")
_SPOT = Decimal("24000")


def _make_store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "test.db")


def _make_leg(
    ltp: float = 10.0,
    bid: float = 9.5,
    ask: float = 10.5,
    delta: float = -0.20,
    strike: float = 23000.0,
) -> OptionLeg:
    return OptionLeg(
        ltp=Decimal(str(ltp)),
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
        oi=1000,
        volume=500,
        delta=Decimal(str(delta)),
        gamma=Decimal("0.001"),
        theta=Decimal("-5.0"),
        vega=Decimal("10.0"),
        iv=Decimal("15.0"),
        strike=Decimal(str(strike)),
    )


def _make_chain(
    ce_leg: OptionLeg | None = None,
    pe_leg: OptionLeg | None = None,
    spot: float = 24000.0,
    strike: float = 23000.0,
) -> OptionChain:
    """Build a minimal OptionChain with one strike."""
    strike_dec = Decimal(str(strike))
    return OptionChain(
        underlying_spot=Decimal(str(spot)),
        expiry=_TODAY,
        strikes={strike_dec: OptionChainStrike(ce=ce_leg, pe=pe_leg)},
    )


def _make_csp_position(
    avg_sell_price: float = 100.0,
    entry_date: date | None = None,
    instrument_key: str = "NSE_FO|NIFTY23000PE",
) -> PaperPosition:
    return PaperPosition(
        strategy_name=_STRATEGY_CSP,
        leg_role="short_put",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal(str(avg_sell_price)),
        instrument_key=instrument_key,
        entry_date=entry_date or _TODAY,
    )


def _make_overlay_position(
    leg_role: str,
    net_qty: int,
    avg_sell_price: float = 20.0,
    avg_cost: float = 0.0,
    instrument_key: str = "NSE_FO|NIFTY23000CE",
) -> PaperPosition:
    return PaperPosition(
        strategy_name=_STRATEGY_SPOT,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal(str(avg_cost)),
        avg_sell_price=Decimal(str(avg_sell_price)),
        instrument_key=instrument_key,
    )


async def _run_eval(
    store: PaperStore,
    positions: list[PaperPosition],
    chain: OptionChain,
    notifier=None,
    save: bool = True,
) -> None:
    await snap_mod.compute_and_record_exit_signals(
        store=store,
        positions=positions,
        chain=chain,
        snapshot_id=None,
        engine=ExitSignalEngine,
        today=_TODAY,
        notifier=notifier,
        save=save,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_csp_profit_target_written(tmp_path: Path) -> None:
    """CSP LTP ≤ 30% of entry credit → PROFIT_TARGET written with detected_by=EOD."""
    store = _make_store(tmp_path)
    # Entry credit=100, LTP=29 → 29% of credit (≤ 30%) → PROFIT_TARGET fires
    pe_leg = _make_leg(ltp=29.0, delta=-0.20)
    chain = _make_chain(pe_leg=pe_leg)
    pos = _make_csp_position(avg_sell_price=100.0)

    await _run_eval(store, [pos], chain)

    events = store.get_open_exit_events()
    assert len(events) == 1
    assert events[0]["exit_signal"] == "PROFIT_TARGET"
    assert events[0]["detected_by"] == "EOD"
    assert events[0]["strategy_name"] == _STRATEGY_CSP


@pytest.mark.asyncio
async def test_cc_delta_stop_written(tmp_path: Path) -> None:
    """CC overlay delta ≥ 0.56 → DELTA_STOP event written."""
    store = _make_store(tmp_path)
    ce_leg = _make_leg(ltp=25.0, delta=0.57, bid=24.5, ask=25.5)
    chain = _make_chain(ce_leg=ce_leg)
    pos = _make_overlay_position(
        leg_role="overlay_cc",
        net_qty=-1,
        avg_sell_price=20.0,
        instrument_key="NSE_FO|NIFTY23000CE",
    )

    await _run_eval(store, [pos], chain)

    events = store.get_open_exit_events()
    assert len(events) == 1
    assert events[0]["exit_signal"] == "DELTA_STOP"
    assert events[0]["detected_by"] == "EOD"


@pytest.mark.asyncio
async def test_pp_crash_monetize_written(tmp_path: Path) -> None:
    """PP delta ≤ −0.81, spread ≤ 10% of mid → CRASH_MONETIZE written."""
    store = _make_store(tmp_path)
    # Entry debit=10, current_mark=52 (≥ 5×); delta=-0.82; spread=0.5/26=~2%
    pe_leg = _make_leg(ltp=52.0, delta=-0.82, bid=51.75, ask=52.25)
    chain = _make_chain(pe_leg=pe_leg)
    pos = _make_overlay_position(
        leg_role="overlay_pp",
        net_qty=1,
        avg_cost=10.0,
        instrument_key="NSE_FO|NIFTY23000PE",
    )

    await _run_eval(store, [pos], chain)

    events = store.get_open_exit_events()
    assert len(events) == 1
    assert events[0]["exit_signal"] == "CRASH_MONETIZE"


@pytest.mark.asyncio
async def test_healthy_position_no_event(tmp_path: Path) -> None:
    """Healthy position (no breach) → create_exit_event NOT called."""
    store = _make_store(tmp_path)
    # Mark=60% of entry (100) → no signal
    pe_leg = _make_leg(ltp=60.0, delta=-0.20)
    chain = _make_chain(pe_leg=pe_leg)
    pos = _make_csp_position(avg_sell_price=100.0)

    await _run_eval(store, [pos], chain)

    assert store.get_open_exit_events() == []


@pytest.mark.asyncio
async def test_deduplication_no_duplicate(tmp_path: Path) -> None:
    """Same signal evaluated twice on the same day → only one DB row."""
    store = _make_store(tmp_path)
    pe_leg = _make_leg(ltp=29.0, delta=-0.20)
    chain = _make_chain(pe_leg=pe_leg)
    pos = _make_csp_position(avg_sell_price=100.0)

    await _run_eval(store, [pos], chain)
    await _run_eval(store, [pos], chain)  # second run — must be deduped

    events = store.get_open_exit_events()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_info_signals_not_written(tmp_path: Path) -> None:
    """INFO signals (e.g. DTE_REVIEW) are not written to DB."""
    store = _make_store(tmp_path)
    # CC entry < ₹12 → BELOW_FLOOR (INFO); mark=60% → no PROFIT_TARGET
    ce_leg = _make_leg(ltp=7.0, delta=0.15)
    chain = _make_chain(ce_leg=ce_leg)
    pos = _make_overlay_position(
        leg_role="overlay_cc",
        net_qty=-1,
        avg_sell_price=10.0,  # below ₹12 floor → BELOW_FLOOR INFO
        instrument_key="NSE_FO|NIFTY23000CE",
    )

    await _run_eval(store, [pos], chain)

    # BELOW_FLOOR is INFO — must not appear in DB
    assert store.get_open_exit_events() == []


@pytest.mark.asyncio
async def test_only_breaching_position_creates_event(tmp_path: Path) -> None:
    """Multiple positions; only the breaching one creates an event."""
    store = _make_store(tmp_path)
    # Healthy CSP (mark=60%)
    pe_healthy = _make_leg(ltp=60.0, delta=-0.20)
    # Breaching CC (delta=0.57 → DELTA_STOP)
    ce_breach = _make_leg(ltp=25.0, delta=0.57)
    chain = OptionChain(
        underlying_spot=_SPOT,
        expiry=_TODAY,
        strikes={
            _STRIKE: OptionChainStrike(ce=ce_breach, pe=pe_healthy),
        },
    )

    pos_healthy = _make_csp_position(avg_sell_price=100.0)
    pos_breach = _make_overlay_position(
        leg_role="overlay_cc",
        net_qty=-1,
        avg_sell_price=20.0,
        instrument_key="NSE_FO|NIFTY23000CE",
    )

    await _run_eval(store, [pos_healthy, pos_breach], chain)

    events = store.get_open_exit_events()
    assert len(events) == 1
    assert events[0]["exit_signal"] == "DELTA_STOP"


@pytest.mark.asyncio
async def test_notifier_called_for_action_and_warn(tmp_path: Path) -> None:
    """ACTION → one Telegram per signal; WARN → batched per strategy."""
    store = _make_store(tmp_path)
    # ACTION: CSP profit target (LTP=29 ≤ 30% of entry credit 100)
    pe_action = _make_leg(ltp=29.0, delta=-0.20)
    # WARN: CC delta=0.47 → DELTA_WARN
    ce_warn = _make_leg(ltp=22.0, delta=0.47)

    chain = OptionChain(
        underlying_spot=_SPOT,
        expiry=_TODAY,
        strikes={_STRIKE: OptionChainStrike(ce=ce_warn, pe=pe_action)},
    )

    csp_pos = _make_csp_position(avg_sell_price=100.0, instrument_key="NSE_FO|NIFTY23000PE")
    cc_pos = _make_overlay_position(
        leg_role="overlay_cc",
        net_qty=-1,
        avg_sell_price=20.0,
        instrument_key="NSE_FO|NIFTY23000CE",
    )

    notifier = MagicMock()
    notifier.send = AsyncMock()

    await _run_eval(store, [csp_pos, cc_pos], chain, notifier=notifier)

    # One ACTION send (PROFIT_TARGET) + one WARN batch send (DELTA_WARN)
    assert notifier.send.call_count == 2
    action_calls = [c for c in notifier.send.call_args_list if "EXIT SIGNAL [ACTION]" in c.args[0]]
    warn_calls = [c for c in notifier.send.call_args_list if "EXIT WARN" in c.args[0]]
    assert len(action_calls) == 1
    assert len(warn_calls) == 1


@pytest.mark.asyncio
async def test_notifier_raises_event_still_written(tmp_path: Path) -> None:
    """Notifier failure is non-fatal — exit event still persisted to DB."""
    store = _make_store(tmp_path)
    pe_leg = _make_leg(ltp=29.0, delta=-0.20)
    chain = _make_chain(pe_leg=pe_leg)
    pos = _make_csp_position(avg_sell_price=100.0)

    notifier = MagicMock()
    notifier.send = AsyncMock(side_effect=RuntimeError("Telegram down"))

    await _run_eval(store, [pos], chain, notifier=notifier)

    events = store.get_open_exit_events()
    assert len(events) == 1
    assert events[0]["exit_signal"] == "PROFIT_TARGET"


@pytest.mark.asyncio
async def test_dry_run_no_events_written(tmp_path: Path) -> None:
    """save=False (dry-run) → no DB writes and no Telegram sent."""
    store = _make_store(tmp_path)
    pe_leg = _make_leg(ltp=49.0, delta=-0.20)
    chain = _make_chain(pe_leg=pe_leg)
    pos = _make_csp_position(avg_sell_price=100.0)

    notifier = MagicMock()
    notifier.send = AsyncMock()

    await _run_eval(store, [pos], chain, notifier=notifier, save=False)

    assert store.get_open_exit_events() == []
    notifier.send.assert_not_called()
