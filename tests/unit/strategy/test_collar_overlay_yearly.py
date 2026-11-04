"""YL-2: CollarOverlayV1 and collar reselection read exit/entry thresholds from the tenor policy."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.constants import STRATEGY_OVERLAY, STRATEGY_OVERLAY_YEARLY_COLLAR
from src.paper.models import PaperPosition
from src.strategy.collar_entry import CollarEntrySelectionError, select_and_build_collar_entry
from src.strategy.collar_overlay_v1 import CollarOverlayV1
from src.strategy.exit_signals import ExitSignalEngine
from src.strategy.overlay_tenor import OVERLAY_TENORS

_YEARLY = OVERLAY_TENORS["yearly"]
_ENTRY = "src.strategy.collar_entry"


def _chain(ltp: str = "100", delta: str = "0.20") -> OptionChain:
    leg = OptionLeg(
        ltp=Decimal(ltp),
        bid=Decimal(ltp),
        ask=Decimal(ltp),
        oi=1000,
        volume=500,
        delta=Decimal(delta),
        gamma=Decimal("0.001"),
        theta=Decimal("-5"),
        vega=Decimal("10"),
        iv=Decimal("15.0"),
        strike=Decimal("23000"),
    )
    return OptionChain(
        underlying_spot=Decimal("22000"),
        expiry=date(2026, 12, 29),
        strikes={Decimal("23000"): OptionChainStrike(ce=leg)},
    )


def _call_pos(strategy: str, dte: int) -> PaperPosition:
    expiry = date.today() + timedelta(days=dte)
    return PaperPosition(
        strategy_name=strategy,
        leg_role="overlay_collar_call",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("100"),
        instrument_key=f"NSE_FO|NIFTY{expiry.strftime('%d%b%Y').upper()}|NIFTY23000CE",
        entry_date=date.today() - timedelta(days=3),
    )


def _types(strategy: CollarOverlayV1, pos: PaperPosition, ltp: str = "100") -> dict[str, str]:
    events = asyncio.run(strategy.check_signals(_chain(ltp), [pos]))
    return {e.event_type: e.severity for e in events}


def test_class_default_is_monthly_policy() -> None:
    s = CollarOverlayV1()
    assert s.strategy_name == STRATEGY_OVERLAY
    assert s.reentry_min_dte == 14


def test_yearly_instance_uses_yearly_namespace() -> None:
    s = CollarOverlayV1(tenor=_YEARLY)
    assert s.strategy_name == STRATEGY_OVERLAY_YEARLY_COLLAR
    assert s.reentry_min_dte == 20
    assert _types(s, _call_pos(STRATEGY_OVERLAY, dte=3)) == {}


def test_yearly_collar_review_uses_policy_dte() -> None:
    s = CollarOverlayV1(tenor=_YEARLY)
    assert "DTE_REVIEW" not in _types(s, _call_pos(STRATEGY_OVERLAY_YEARLY_COLLAR, dte=16))
    assert _types(s, _call_pos(STRATEGY_OVERLAY_YEARLY_COLLAR, dte=15))["DTE_REVIEW"] == "ACTION"
    pos = _call_pos(STRATEGY_OVERLAY_YEARLY_COLLAR, dte=20)
    assert "DTE_REVIEW" not in _types(CollarOverlayV1(tenor=replace(_YEARLY, review_dte=5)), pos)


def test_yearly_collar_premium_stop_alert_only_and_target_75() -> None:
    pos = _call_pos(STRATEGY_OVERLAY_YEARLY_COLLAR, dte=200)
    s = CollarOverlayV1(tenor=_YEARLY)
    assert _types(s, pos, ltp="250")["LOSS_STOP"] == "WARN"
    assert "PROFIT_TARGET" not in _types(s, pos, ltp="30")
    assert _types(s, pos, ltp="25")["PROFIT_TARGET"] == "ACTION"


def test_monthly_collar_golden_signals_unchanged() -> None:
    kwargs = {"entry_price": 80.0, "current_mark": 201.0, "delta": 0.56, "dte": 5, "days_held": 3}
    default = ExitSignalEngine.evaluate_cc(**kwargs)
    explicit = ExitSignalEngine.evaluate_cc(**kwargs, policy=OVERLAY_TENORS["monthly"])
    assert default == explicit
    monthly = _types(CollarOverlayV1(), _call_pos(STRATEGY_OVERLAY, dte=5), ltp="250")
    assert monthly["DTE_REVIEW"] == "ACTION" and monthly["LOSS_STOP"] == "ACTION"


# ── reselection ──────────────────────────────────────────────────────────────


def _row(strike: int, key: str, mid: float) -> dict[str, Any]:
    return {"strike": strike, "instrument_key": key, "mid": mid, "ltp": mid, "delta": 0.2}


def _select(lookup: MagicMock, today: date, **kwargs: Any) -> tuple[Any, MagicMock, MagicMock]:
    broker = MagicMock()
    broker.get_option_chain = AsyncMock(return_value=[{"underlying_spot_price": 24000}])
    with (
        patch(f"{_ENTRY}.InstrumentLookup.from_file", return_value=lookup),
        patch(f"{_ENTRY}.load_vix_series", return_value=pd.Series([15.0] * 260)),
        patch(f"{_ENTRY}._find_candidates_for_ladder") as find,
    ):
        find.side_effect = [[_row(25200, "CE", 45.0)], [_row(23900, "PE", 38.0)]]
        result = asyncio.run(
            select_and_build_collar_entry(broker, MagicMock(), today, "DTE_REVIEW", **kwargs)
        )
    return result, broker, lookup


def _yearly_lookup(expiry: str) -> MagicMock:
    lookup = MagicMock()
    lookup.get_expiry_candidates.return_value = [("yearly", expiry)]
    return lookup


def test_yearly_collar_reselect_resolves_december() -> None:
    today = date(2026, 11, 20)
    (trades, *_), broker, lookup = _select(
        _yearly_lookup("2027-12-28"), today, closing_dte=15, policy=_YEARLY
    )
    assert broker.get_option_chain.call_args[0][1] == "2027-12-28"
    kwargs = lookup.get_expiry_candidates.call_args.kwargs
    assert kwargs["preference"] == ["yearly"]
    assert kwargs["min_expiry"] == (today + timedelta(days=15)).isoformat()
    assert {t.strategy_name for t in trades} == {STRATEGY_OVERLAY_YEARLY_COLLAR}


def test_yearly_collar_reselect_dte_floor_from_policy() -> None:
    today = date(2026, 11, 20)
    near = (today + timedelta(days=19)).isoformat()
    with pytest.raises(CollarEntrySelectionError, match="DTE >= 20"):
        _select(_yearly_lookup(near), today, policy=_YEARLY)
    # Same expiry clears when the policy floor is lowered (monthly's 14 floor would not matter).
    low = replace(_YEARLY, entry_min_dte=16)
    (trades, *_), _, _ = _select(_yearly_lookup(near), today, policy=low)
    assert len(trades) == 2


def test_monthly_collar_reselect_unchanged() -> None:
    lookup = MagicMock()
    lookup.get_expiry_candidates.return_value = [("monthly", "2026-11-24")]
    today = date(2026, 11, 4)
    for policy in (None, OVERLAY_TENORS["monthly"]):
        (trades, *_), broker, lk = _select(lookup, today, closing_dte=20, policy=policy)
        assert broker.get_option_chain.call_args[0][1] == "2026-11-24"
        assert lk.get_expiry_candidates.call_args.kwargs["preference"] == ["monthly"]
        assert {t.strategy_name for t in trades} == {STRATEGY_OVERLAY}


def test_monthly_dte_floor_still_14() -> None:
    lookup = MagicMock()
    lookup.get_expiry_candidates.return_value = [("monthly", "2026-11-14")]
    with pytest.raises(CollarEntrySelectionError, match="dte=10 < 14"):
        _select(lookup, date(2026, 11, 4), policy=OVERLAY_TENORS["monthly"])
