"""YP-1: ``--expiry-type`` on ``--auto-pp`` (monthly default pinned, yearly opens December)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts.strategies.three_track import paper_3track_overlay_entry as oe
from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_OVERLAY, STRATEGY_OVERLAY_YEARLY_PP
from src.paper.models import PaperTrade
from src.paper.store import PaperStore
from tests.unit.scripts.test_overlay_chain_wiring import (
    BOD,
    DEC_2026_MS,
    TODAY,
    _bod_chain,
    _vix_patches,
)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Patch every external seam of ``main`` and expose the tmp store + gate spy."""
    raw = _bod_chain(DEC_2026_MS, "2026-12-29")
    db = tmp_path / "p.sqlite"
    gate = MagicMock()
    patches = [
        *_vix_patches(),
        patch.object(oe, "market_today", return_value=TODAY),
        patch.object(oe, "UpstoxMarketClient"),
        patch.object(oe, "create_overlay_chain_fetch", return_value=lambda u, e: raw),
        patch.object(oe, "setup_logging"),
        patch.object(oe, "build_notifier", return_value=None),
        patch.object(oe, "_check_overlay_collateral_capacity", gate),
    ]
    for p in patches:
        p.start()
    oe.UpstoxMarketClient.return_value.get_option_chain_sync.return_value = raw
    try:
        yield {"db": db, "gate": gate, "store": PaperStore(db)}
    finally:
        for p in patches:
            p.stop()


def _main(env: dict[str, Any], *flags: str) -> None:
    argv = ["x.py", "--auto-pp", "--bod-path", str(BOD), "--db-path", str(env["db"]), *flags]
    with patch("sys.argv", argv):
        oe.main()


def _pp_legs(env: dict[str, Any], strategy: str) -> list[Any]:
    return [p for p in env["store"].get_positions(strategy) if p.leg_role == "overlay_pp"]


def _open_put(env: dict[str, Any], strategy: str, key: str) -> None:
    """Record an open ``overlay_pp`` put (Dec 2026 BOD key) under *strategy*."""
    env["store"].record_trade(
        PaperTrade(
            strategy_name=strategy,
            leg_role="overlay_pp",
            instrument_key=key,
            trade_date=date(2026, 10, 1),
            action=TradeAction.BUY,
            quantity=75,
            price=Decimal("100"),
        )
    )


def test_monthly_default_records_under_monthly_namespace(env: dict[str, Any]) -> None:
    _main(env)
    assert len(_pp_legs(env, STRATEGY_OVERLAY)) == 1
    assert _pp_legs(env, STRATEGY_OVERLAY_YEARLY_PP) == []
    assert env["gate"].call_args.args[1] == STRATEGY_OVERLAY


def test_yearly_pp_bootstrap_opens_december_put(env: dict[str, Any]) -> None:
    _main(env, "--expiry-type", "yearly")
    legs = _pp_legs(env, STRATEGY_OVERLAY_YEARLY_PP)
    assert len(legs) == 1
    assert legs[0].instrument_key == "NSE_FO|62506"
    assert _pp_legs(env, STRATEGY_OVERLAY) == []
    assert env["gate"].call_args.args[1] == STRATEGY_OVERLAY_YEARLY_PP


def test_yearly_pp_dry_run_writes_nothing(env: dict[str, Any]) -> None:
    _main(env, "--expiry-type", "yearly", "--dry-run")
    assert _pp_legs(env, STRATEGY_OVERLAY_YEARLY_PP) == []
    assert _pp_legs(env, STRATEGY_OVERLAY) == []


def test_monthly_put_open_does_not_noop_yearly_bootstrap(env: dict[str, Any]) -> None:
    _open_put(env, STRATEGY_OVERLAY, "NSE_FO|62506")  # fresh monthly put, DTE 56
    _main(env, "--expiry-type", "yearly")
    assert len(_pp_legs(env, STRATEGY_OVERLAY_YEARLY_PP)) == 1


def test_yearly_put_open_does_not_noop_monthly_bootstrap(env: dict[str, Any]) -> None:
    _open_put(env, STRATEGY_OVERLAY_YEARLY_PP, "NSE_FO|62506")
    _main(env)
    assert len(_pp_legs(env, STRATEGY_OVERLAY)) == 1


def test_yearly_fresh_put_open_is_noop(env: dict[str, Any]) -> None:
    _open_put(env, STRATEGY_OVERLAY_YEARLY_PP, "NSE_FO|62506")
    with pytest.raises(SystemExit) as exc:
        _main(env, "--expiry-type", "yearly")
    assert exc.value.code == 0
    assert env["store"].get_positions(STRATEGY_OVERLAY_YEARLY_PP)[0].net_qty == 75


def test_open_pp_dte_measures_only_the_given_namespace(env: dict[str, Any]) -> None:
    _open_put(env, STRATEGY_OVERLAY, "NSE_FO|62506")
    args = (env["db"], BOD, TODAY)
    assert oe._open_pp_dte(*args) == 56
    assert oe._open_pp_dte(*args, strategy_name=STRATEGY_OVERLAY_YEARLY_PP) is None


def test_yearly_with_collar_flag_still_rejected(env: dict[str, Any]) -> None:
    argv = ["x.py", "--auto-collar", "--expiry-type", "yearly", "--db-path", str(env["db"])]
    with patch("sys.argv", argv), pytest.raises(SystemExit) as exc:
        oe.main()
    assert exc.value.code != 0
