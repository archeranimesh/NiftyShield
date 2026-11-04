"""YP-2: PP roll window and crash-monetize re-entry floor read the tenor policy."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.strategies.three_track import paper_3track_overlay_entry as oe
from src.models.options import OptionChain, OptionChainStrike
from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_OVERLAY, STRATEGY_OVERLAY_YEARLY_PP
from src.paper.models import PaperPosition, PaperTrade
from src.paper.store import PaperStore
from src.strategy.auto_close import evaluate_pp_reentry_eod
from src.strategy.exit_signals import ExitSignalEngine
from src.strategy.overlay_tenor import OVERLAY_TENORS
from src.strategy.pp_overlay_v1 import PPOverlayV1
from tests.unit.scripts.test_overlay_chain_wiring import BOD, _bod_chain, _vix_patches
from tests.unit.strategy.test_pp_overlay_v1 import _make_put_leg

_YEARLY = OVERLAY_TENORS["yearly"]
_MONTHLY = OVERLAY_TENORS["monthly"]
_DEC_2026_KEY = "NSE_FO|62506"
_DEC_2027_MS = 1830018599000


def _chain(ltp: str = "100", delta: str = "-0.20") -> OptionChain:
    leg = _make_put_leg(ltp=ltp, delta=delta)
    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 12, 29),
        strikes={Decimal("23000"): OptionChainStrike(pe=leg)},
    )


def _pos(strategy: str, dte: int) -> PaperPosition:
    expiry = date.today() + timedelta(days=dte)
    return PaperPosition(
        strategy_name=strategy,
        leg_role="overlay_pp",
        net_qty=65,
        avg_cost=Decimal("100"),
        avg_sell_price=Decimal("0"),
        instrument_key=f"NSE_FO|NIFTY{expiry.strftime('%d%b%Y').upper()}PE",
        entry_date=date.today() - timedelta(days=3),
    )


def _types(strategy: PPOverlayV1, pos: PaperPosition) -> dict[str, str]:
    events = asyncio.run(strategy.check_signals(_chain(), [pos]))
    return {e.event_type: e.severity for e in events}


def test_class_default_is_monthly_policy() -> None:
    s = PPOverlayV1()
    assert s.strategy_name == STRATEGY_OVERLAY
    assert s.reentry_min_dte == 14


def test_yearly_instance_uses_yearly_namespace_and_floor() -> None:
    s = PPOverlayV1(tenor=_YEARLY)
    assert s.strategy_name == STRATEGY_OVERLAY_YEARLY_PP
    assert s.reentry_min_dte == _YEARLY.reentry_min_dte
    assert _types(s, _pos(STRATEGY_OVERLAY, dte=3)) == {}


def test_monthly_roll_threshold_unchanged() -> None:
    """Pinned: monthly rolls at DTE <= 5 and not at 6, with the legacy note text."""
    kwargs = {"entry_price": 100.0, "current_mark": 90.0, "delta": -0.2}
    assert [r.exit_signal for r in ExitSignalEngine.evaluate_pp(**kwargs, dte=5)] == [
        "ROLL_ELIGIBLE"
    ]
    assert ExitSignalEngine.evaluate_pp(**kwargs, dte=6) == []
    explicit = ExitSignalEngine.evaluate_pp(**kwargs, dte=5, policy=_MONTHLY)
    assert explicit == ExitSignalEngine.evaluate_pp(**kwargs, dte=5)
    assert (explicit[0].threshold_value, explicit[0].notes) == (
        5.0,
        "DTE 5 ≤ 5 — roll PP to next expiry",
    )
    s = PPOverlayV1()
    assert _types(s, _pos(STRATEGY_OVERLAY, dte=5)) == {"ROLL_ELIGIBLE": "ACTION"}
    assert _types(s, _pos(STRATEGY_OVERLAY, dte=6)) == {}


def test_yearly_put_rolls_at_15_not_16() -> None:
    s = PPOverlayV1(tenor=_YEARLY)
    assert _types(s, _pos(STRATEGY_OVERLAY_YEARLY_PP, dte=16)) == {}
    assert _types(s, _pos(STRATEGY_OVERLAY_YEARLY_PP, dte=15)) == {"ROLL_ELIGIBLE": "ACTION"}


def test_roll_window_reads_policy_value() -> None:
    pos = _pos(STRATEGY_OVERLAY_YEARLY_PP, dte=20)
    assert _types(PPOverlayV1(tenor=replace(_YEARLY, roll_dte=30)), pos) == {
        "ROLL_ELIGIBLE": "ACTION"
    }
    assert _types(PPOverlayV1(tenor=replace(_YEARLY, roll_dte=10)), pos) == {}


def test_roll_outside_window_noops() -> None:
    s = PPOverlayV1(tenor=_YEARLY)
    assert _types(s, _pos(STRATEGY_OVERLAY_YEARLY_PP, dte=200)) == {}


def test_reentry_blocked_below_policy_floor() -> None:
    store = MagicMock()
    store.get_open_exit_events.return_value = []
    s = PPOverlayV1(store=store, tenor=_YEARLY)
    today = date(2026, 11, 3)
    asyncio.run(s._check_reentry(today + timedelta(days=19), today, "k", 0))
    assert store.create_exit_event.call_args.kwargs["notes"].startswith("DTE=19 < 20")
    assert store.create_exit_event.call_args.kwargs["strategy_name"] == STRATEGY_OVERLAY_YEARLY_PP


def test_reentry_monthly_floor_still_14() -> None:
    store = MagicMock()
    store.get_open_exit_events.return_value = []
    s = PPOverlayV1(store=store)
    today = date(2026, 11, 3)
    asyncio.run(s._check_reentry(today + timedelta(days=13), today, "k", 0))
    assert store.create_exit_event.call_args.kwargs["notes"].startswith("DTE=13 < 14")


def test_monetize_notification_states_policy_floor() -> None:
    notifier = MagicMock()
    notifier.send = AsyncMock()
    s = PPOverlayV1(notifier=notifier, tenor=_YEARLY)
    with patch("src.strategy.pp_overlay_v1.format_exit_message") as fmt:
        fmt.return_value = "msg"
        pos = _pos(STRATEGY_OVERLAY_YEARLY_PP, dte=200)
        action = MagicMock(action_type="MONETIZE_PP", metadata={"mark": "400"})
        asyncio.run(s._send_close_notification(pos, action))
    assert "DTE ≥ 20" in str(fmt.call_args)


def test_eod_reentry_override_names_the_yearly_ledger() -> None:
    """evaluate_pp_reentry_eod's instance override is a real per-book label, not a no-op."""
    store = MagicMock()
    store.get_positions.return_value = []
    seen: list[str] = []
    real = PPOverlayV1._ivr_passes

    def spy(self: PPOverlayV1, ivr: float) -> Any:
        seen.append(self.strategy_name)
        assert self.tenor.expiry_type == "yearly"
        assert self.reentry_min_dte == 20
        return real(self, ivr)

    series = MagicMock()
    series.empty = False
    series.__len__.return_value = 300
    series.iloc = [15.0, 15.0]
    with (
        patch("src.strategy.auto_close.load_vix_series", return_value=series),
        patch("src.strategy.auto_close.compute_ivr", return_value=0.30),
        patch.object(PPOverlayV1, "_ivr_passes", spy),
    ):
        asyncio.run(
            evaluate_pp_reentry_eod(
                store,
                MagicMock(),
                _chain(),
                None,
                None,
                None,
                date(2026, 11, 3),
                strategy_name=STRATEGY_OVERLAY_YEARLY_PP,
            )
        )
    store.get_positions.assert_called_with(STRATEGY_OVERLAY_YEARLY_PP)
    assert seen == [STRATEGY_OVERLAY_YEARLY_PP]


# ── main(): roll gap-fill lands on the next yearly expiry ────────────────────────────


@pytest.fixture
def roll_env(tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Patch main()'s seams; ``today`` is set per test through ``env['today']``."""
    raw_2027 = _bod_chain(_DEC_2027_MS, "2027-12-28")
    db = tmp_path / "p.sqlite"
    state: dict[str, Any] = {"today": date(2026, 12, 14), "db": db, "store": PaperStore(db)}
    patches = [
        *_vix_patches(),
        patch.object(oe, "market_today", side_effect=lambda: state["today"]),
        patch.object(oe, "UpstoxMarketClient"),
        patch.object(oe, "create_overlay_chain_fetch", return_value=lambda u, e: raw_2027),
        patch.object(oe, "setup_logging"),
        patch.object(oe, "build_notifier", return_value=None),
        patch.object(oe, "_check_overlay_collateral_capacity", MagicMock()),
    ]
    for p in patches:
        p.start()
    oe.UpstoxMarketClient.return_value.get_option_chain_sync.return_value = raw_2027
    try:
        yield state
    finally:
        for p in patches:
            p.stop()


def _open_dec_2026_put(state: dict[str, Any], strategy: str) -> None:
    state["store"].record_trade(
        PaperTrade(
            strategy_name=strategy,
            leg_role="overlay_pp",
            instrument_key=_DEC_2026_KEY,
            trade_date=date(2026, 10, 1),
            action=TradeAction.BUY,
            quantity=75,
            price=Decimal("100"),
        )
    )


def _run_main(state: dict[str, Any], *flags: str) -> None:
    argv = ["x.py", "--auto-pp", "--bod-path", str(BOD), "--db-path", str(state["db"]), *flags]
    with patch("sys.argv", argv):
        oe.main()


def _keys(state: dict[str, Any], strategy: str) -> set[str]:
    return {
        p.instrument_key
        for p in state["store"].get_positions(strategy)
        if p.leg_role == "overlay_pp" and p.net_qty > 0
    }


def test_yearly_roll_from_dec2026_targets_dec2027(roll_env: dict[str, Any]) -> None:
    """15 DTE on 2026-12-14: gap-fill opens the Dec 2027 put beside the outgoing one."""
    _open_dec_2026_put(roll_env, STRATEGY_OVERLAY_YEARLY_PP)
    _run_main(roll_env, "--expiry-type", "yearly")
    keys = _keys(roll_env, STRATEGY_OVERLAY_YEARLY_PP)
    assert _DEC_2026_KEY in keys
    new = keys - {_DEC_2026_KEY}
    assert len(new) == 1
    lookup = oe.InstrumentLookup.from_file(BOD)
    assert lookup.get_by_key(next(iter(new)))["expiry"] == _DEC_2027_MS


def test_yearly_put_at_dte_6_to_15_rolls_not_noops(roll_env: dict[str, Any]) -> None:
    """Regression: with the old threshold of 5, a yearly put at DTE 10 was a silent no-op."""
    roll_env["today"] = date(2026, 12, 19)  # DTE 10
    _open_dec_2026_put(roll_env, STRATEGY_OVERLAY_YEARLY_PP)
    _run_main(roll_env, "--expiry-type", "yearly")
    assert len(_keys(roll_env, STRATEGY_OVERLAY_YEARLY_PP)) == 2


def test_yearly_roll_outside_window_noops(roll_env: dict[str, Any]) -> None:
    roll_env["today"] = date(2026, 12, 13)  # DTE 16
    _open_dec_2026_put(roll_env, STRATEGY_OVERLAY_YEARLY_PP)
    with pytest.raises(SystemExit) as exc:
        _run_main(roll_env, "--expiry-type", "yearly")
    assert exc.value.code == 0
    assert _keys(roll_env, STRATEGY_OVERLAY_YEARLY_PP) == {_DEC_2026_KEY}


def test_monthly_main_still_noops_at_dte_6(roll_env: dict[str, Any]) -> None:
    roll_env["today"] = date(2026, 12, 23)  # DTE 6: monthly threshold stays 5
    _open_dec_2026_put(roll_env, STRATEGY_OVERLAY)
    with pytest.raises(SystemExit) as exc:
        _run_main(roll_env)
    assert exc.value.code == 0
    assert _keys(roll_env, STRATEGY_OVERLAY) == {_DEC_2026_KEY}
