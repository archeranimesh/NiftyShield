"""YC-2: CCOverlayV1 reads exit thresholds, ledger and re-entry floor from the tenor policy."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.constants import STRATEGY_OVERLAY, STRATEGY_OVERLAY_YEARLY_CC
from src.paper.models import PaperPosition
from src.strategy.cc_overlay_v1 import CCOverlayV1
from src.strategy.exit_signals import ExitSignalEngine
from src.strategy.overlay_tenor import OVERLAY_TENORS

_YEARLY = OVERLAY_TENORS["yearly"]


def _chain(ltp: str, delta: str) -> OptionChain:
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


def _pos(strategy: str, dte: int, entry: str = "100") -> PaperPosition:
    expiry = date.today() + timedelta(days=dte)
    return PaperPosition(
        strategy_name=strategy,
        leg_role="overlay_cc",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal(entry),
        # The expiry and strike regexes each need their own NIFTY<...> token to resolve offline.
        instrument_key=f"NSE_FO|NIFTY{expiry.strftime('%d%b%Y').upper()}|NIFTY23000CE",
        entry_date=date.today() - timedelta(days=3),
    )


def _types(
    strategy: CCOverlayV1, pos: PaperPosition, ltp: str = "100", delta: str = "0.20"
) -> dict[str, str]:
    events = asyncio.run(strategy.check_signals(_chain(ltp, delta), [pos]))
    return {e.event_type: e.severity for e in events}


def test_class_default_is_monthly_policy() -> None:
    s = CCOverlayV1()
    assert s.strategy_name == STRATEGY_OVERLAY
    assert s.reentry_min_dte == 14


def test_yearly_instance_uses_yearly_namespace_and_floor() -> None:
    s = CCOverlayV1(tenor=_YEARLY)
    assert s.strategy_name == STRATEGY_OVERLAY_YEARLY_CC
    assert s.reentry_min_dte == _YEARLY.reentry_min_dte
    # Monthly-ledger positions are invisible to the yearly instance.
    assert _types(s, _pos(STRATEGY_OVERLAY, dte=3)) == {}


def test_yearly_cc_review_dte_uses_policy() -> None:
    pos = _pos(STRATEGY_OVERLAY_YEARLY_CC, dte=20)
    five = CCOverlayV1(tenor=replace(_YEARLY, review_dte=5))
    thirty = CCOverlayV1(tenor=replace(_YEARLY, review_dte=30))
    assert "DTE_REVIEW" not in _types(five, pos)
    assert _types(thirty, pos)["DTE_REVIEW"] == "ACTION"


def test_yearly_real_policy_reviews_at_15_not_16() -> None:
    s = CCOverlayV1(tenor=_YEARLY)
    assert "DTE_REVIEW" not in _types(s, _pos(STRATEGY_OVERLAY_YEARLY_CC, dte=16))
    assert _types(s, _pos(STRATEGY_OVERLAY_YEARLY_CC, dte=15))["DTE_REVIEW"] == "ACTION"


def test_yearly_profit_target_at_75_percent_decay() -> None:
    s = CCOverlayV1(tenor=_YEARLY)
    pos = _pos(STRATEGY_OVERLAY_YEARLY_CC, dte=200)
    assert "PROFIT_TARGET" not in _types(
        s, pos, ltp="30"
    )  # 70% captured: monthly fires, yearly not
    assert _types(s, pos, ltp="25")["PROFIT_TARGET"] == "ACTION"
    assert _types(CCOverlayV1(), _pos(STRATEGY_OVERLAY, dte=200), ltp="30")["PROFIT_TARGET"]


def test_yearly_premium_stop_is_alert_only() -> None:
    pos = _pos(STRATEGY_OVERLAY_YEARLY_CC, dte=200)
    assert _types(CCOverlayV1(tenor=_YEARLY), pos, ltp="250")["LOSS_STOP"] == "WARN"
    monthly = _types(CCOverlayV1(), _pos(STRATEGY_OVERLAY, dte=200), ltp="250")
    assert monthly["LOSS_STOP"] == "ACTION"


def test_yearly_delta_stop_uses_policy_value() -> None:
    pos = _pos(STRATEGY_OVERLAY_YEARLY_CC, dte=200)
    s = CCOverlayV1(tenor=replace(_YEARLY, delta_stop=Decimal("0.65")))
    assert "DELTA_STOP" not in _types(s, pos, delta="0.60")
    assert _types(s, pos, delta="0.66")["DELTA_STOP"] == "ACTION"


def test_monthly_cc_unchanged_by_policy_injection() -> None:
    """Golden signals for a fixed leg: explicit monthly policy equals the default."""
    kwargs = {"entry_price": 80.0, "current_mark": 201.0, "delta": 0.56, "dte": 5, "days_held": 3}
    default = ExitSignalEngine.evaluate_cc(**kwargs)
    explicit = ExitSignalEngine.evaluate_cc(**kwargs, policy=OVERLAY_TENORS["monthly"])
    assert default == explicit
    assert [(r.exit_signal, r.severity, r.threshold_value) for r in default] == [
        ("LOSS_STOP", "ACTION", 2.5),
        ("DELTA_STOP", "ACTION", 0.55),
        ("DTE_REVIEW", "ACTION", 5.0),
    ]
    assert default[0].notes == "Mark 201.0 >= 2.5x entry credit 80.0"


def test_reentry_blocked_below_policy_floor() -> None:
    store = MagicMock()
    store.get_open_exit_events.return_value = []
    s = CCOverlayV1(store=store, tenor=_YEARLY)
    today = date(2026, 11, 3)
    asyncio.run(s._check_reentry(today + timedelta(days=19), today, "k", 0))
    assert store.create_exit_event.call_args.kwargs["notes"].startswith("DTE=19 < 20")
    assert store.create_exit_event.call_args.kwargs["strategy_name"] == STRATEGY_OVERLAY_YEARLY_CC


def test_reentry_monthly_floor_still_14() -> None:
    store = MagicMock()
    store.get_open_exit_events.return_value = []
    s = CCOverlayV1(store=store)
    today = date(2026, 11, 3)
    asyncio.run(s._check_reentry(today + timedelta(days=13), today, "k", 0))
    assert store.create_exit_event.call_args.kwargs["notes"].startswith("DTE=13 < 14")
