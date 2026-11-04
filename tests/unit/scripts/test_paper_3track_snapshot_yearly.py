"""YW-2: the 3-track snapshot evaluates and reports the yearly overlay book separately."""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import scripts.strategies.three_track.paper_3track_snapshot as snap_mod  # noqa: E402
from src.models.options import OptionChain, OptionChainStrike, OptionLeg  # noqa: E402
from src.paper.constants import (  # noqa: E402
    STRATEGY_OVERLAY,
    STRATEGY_OVERLAY_YEARLY_CC,
    STRATEGY_OVERLAY_YEARLY_COLLAR,
    STRATEGY_OVERLAY_YEARLY_PP,
)
from src.paper.models import PaperLegSnapshot, PaperPosition  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402
from src.strategy.overlay_tenor import OVERLAY_TENORS  # noqa: E402

_TODAY = date(2026, 11, 4)
_EXPIRY = date(2026, 11, 14)  # DTE 10
_PE_KEY = "NIFTY14NOV2026PE22000"
_CE_KEY = "NIFTY14NOV2026CE26000"


def _leg(ltp: str, delta: str, strike: str) -> OptionLeg:
    return OptionLeg(
        ltp=Decimal(ltp),
        bid=Decimal(ltp),
        ask=Decimal(ltp),
        oi=1000,
        volume=500,
        delta=Decimal(delta),
        gamma=Decimal("0.001"),
        theta=Decimal("-5"),
        vega=Decimal("10"),
        iv=Decimal("15"),
        strike=Decimal(strike),
    )


def _chain() -> dict[date, OptionChain]:
    chain = OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=_EXPIRY,
        strikes={
            Decimal("22000"): OptionChainStrike(ce=None, pe=_leg("100", "-0.30", "22000")),
            Decimal("26000"): OptionChainStrike(ce=_leg("28", "0.10", "26000"), pe=None),
        },
    )
    return {_EXPIRY: chain}


def _pp(strategy_name: str) -> PaperPosition:
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role="overlay_pp",
        net_qty=65,
        avg_cost=Decimal("100"),
        avg_sell_price=Decimal("0"),
        instrument_key=_PE_KEY,
        entry_date=date(2026, 1, 5),
    )


def _cc(strategy_name: str) -> PaperPosition:
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role="overlay_cc",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("100"),
        instrument_key=_CE_KEY,
        entry_date=date(2026, 1, 5),
    )


def _signals(pos: PaperPosition) -> list[str]:
    results = snap_mod._dispatch_evaluate(pos, _chain(), 24000.0, _TODAY)
    return [r.exit_signal for r in results]


@pytest.mark.asyncio
async def test_snapshot_flags_roll_eligible_for_yearly_put_at_dte_10(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "t.db")
    from src.strategy.exit_signals import ExitSignalEngine

    await snap_mod.compute_and_record_exit_signals(
        store=store,
        positions=[_pp(STRATEGY_OVERLAY_YEARLY_PP)],
        chains=_chain(),
        snapshot_id=None,
        engine=ExitSignalEngine,
        today=_TODAY,
        save=True,
    )
    events = store.get_open_exit_events()
    assert [e["exit_signal"] for e in events] == ["ROLL_ELIGIBLE"]


def test_monthly_put_at_dte_10_is_not_roll_eligible() -> None:
    assert "ROLL_ELIGIBLE" not in _signals(_pp(STRATEGY_OVERLAY))


def test_dispatch_evaluate_cc_uses_yearly_policy() -> None:
    # mark 28 on entry 100: 72% decayed. Monthly target 70% fires; yearly target 75% does not.
    assert "PROFIT_TARGET" in _signals(_cc(STRATEGY_OVERLAY))
    assert "PROFIT_TARGET" not in _signals(_cc(STRATEGY_OVERLAY_YEARLY_CC))


def test_yearly_position_without_registry_policy_fails_loud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(snap_mod, "OVERLAY_TENORS", {"monthly": OVERLAY_TENORS["monthly"]})
    with pytest.raises(ValueError, match="no tenor policy"):
        snap_mod._dispatch_evaluate(_cc(STRATEGY_OVERLAY_YEARLY_CC), _chain(), 24000.0, _TODAY)
    with pytest.raises(ValueError, match="no tenor policy"):
        snap_mod._overlay_policy_for(STRATEGY_OVERLAY_YEARLY_COLLAR)


def test_overlay_pnl_keys_on_yearly_strategy_name(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "t.db")
    store.record_leg_snapshot(
        PaperLegSnapshot(
            strategy_name=STRATEGY_OVERLAY_YEARLY_CC,
            leg_role="overlay_cc",
            snapshot_date=_TODAY,
            unrealized_pnl=Decimal("500"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("500"),
            ltp=Decimal("90"),
            net_qty=-65,
        )
    )
    yearly = snap_mod._compute_overlay_pnl_snapshots(store, _TODAY, STRATEGY_OVERLAY_YEARLY_CC)
    assert [(s.strategy_name, s.overlay_type) for s in yearly] == [
        (STRATEGY_OVERLAY_YEARLY_CC, "cc")
    ]
    assert snap_mod._compute_overlay_pnl_snapshots(store, _TODAY) == []
