"""YC-1: ``--expiry-type`` on ``--auto-cc`` (monthly default pinned, yearly opens December)."""

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
from src.paper.constants import STRATEGY_OVERLAY, STRATEGY_OVERLAY_YEARLY_CC, STRATEGY_SPOT
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
    argv = ["x.py", "--auto-cc", "--bod-path", str(BOD), "--db-path", str(env["db"]), *flags]
    with patch("sys.argv", argv):
        oe.main()


def _cc_legs(env: dict[str, Any], strategy: str) -> list[Any]:
    return [p for p in env["store"].get_positions(strategy) if p.leg_role == "overlay_cc"]


def test_monthly_default_records_under_monthly_namespace(env: dict[str, Any]) -> None:
    _main(env)
    assert len(_cc_legs(env, STRATEGY_OVERLAY)) == 1
    assert _cc_legs(env, STRATEGY_OVERLAY_YEARLY_CC) == []
    assert env["gate"].call_args.args[1] == STRATEGY_OVERLAY


def test_yearly_flag_opens_december_call_under_yearly_namespace(env: dict[str, Any]) -> None:
    _main(env, "--expiry-type", "yearly")
    legs = _cc_legs(env, STRATEGY_OVERLAY_YEARLY_CC)
    assert len(legs) == 1
    assert _cc_legs(env, STRATEGY_OVERLAY) == []
    assert env["store"].get_positions(STRATEGY_OVERLAY_YEARLY_CC)[0].instrument_key
    assert env["gate"].call_args.args[1] == STRATEGY_OVERLAY_YEARLY_CC


def test_yearly_dry_run_writes_nothing(env: dict[str, Any]) -> None:
    _main(env, "--expiry-type", "yearly", "--dry-run")
    assert _cc_legs(env, STRATEGY_OVERLAY_YEARLY_CC) == []
    assert _cc_legs(env, STRATEGY_OVERLAY) == []


def test_monthly_open_leg_does_not_block_yearly_entry(env: dict[str, Any]) -> None:
    _main(env)
    _main(env, "--expiry-type", "yearly")
    assert len(_cc_legs(env, STRATEGY_OVERLAY_YEARLY_CC)) == 1


def test_yearly_open_leg_does_not_block_monthly_entry(env: dict[str, Any]) -> None:
    _main(env, "--expiry-type", "yearly")
    _main(env)
    assert len(_cc_legs(env, STRATEGY_OVERLAY)) == 1


def test_yearly_rerun_is_noop(env: dict[str, Any]) -> None:
    _main(env, "--expiry-type", "yearly")
    qty = env["store"].get_positions(STRATEGY_OVERLAY_YEARLY_CC)[0].net_qty
    _main(env, "--expiry-type", "yearly")
    assert env["store"].get_positions(STRATEGY_OVERLAY_YEARLY_CC)[0].net_qty == qty


def test_yearly_with_collar_flag_rejected(env: dict[str, Any]) -> None:
    argv = ["x.py", "--auto-collar", "--expiry-type", "yearly", "--db-path", str(env["db"])]
    with patch("sys.argv", argv), pytest.raises(SystemExit) as exc:
        oe.main()
    assert exc.value.code != 0


def test_yearly_without_auto_cc_rejected(env: dict[str, Any]) -> None:
    with patch("sys.argv", ["x.py", "--expiry-type", "yearly"]), pytest.raises(SystemExit) as e:
        oe.main()
    assert e.value.code != 0


def _open_legacy_spot_cc(env: dict[str, Any]) -> None:
    """Open an ``overlay_cc`` short call under the legacy ``STRATEGY_SPOT`` ledger."""
    env["store"].record_trade(
        PaperTrade(
            strategy_name=STRATEGY_SPOT,
            leg_role="overlay_cc",
            instrument_key="NSE_FO|legacy",
            trade_date=date(2026, 9, 1),
            action=TradeAction.SELL,
            quantity=75,
            price=Decimal("100"),
        )
    )


def test_legacy_spot_overlay_cc_still_blocks_monthly_entry(env: dict[str, Any]) -> None:
    _open_legacy_spot_cc(env)
    with pytest.raises(SystemExit) as exc:
        _main(env)
    assert exc.value.code == 0
    assert _cc_legs(env, STRATEGY_OVERLAY) == []


def test_legacy_spot_overlay_cc_does_not_block_yearly_entry(env: dict[str, Any]) -> None:
    _open_legacy_spot_cc(env)
    _main(env, "--expiry-type", "yearly")
    assert len(_cc_legs(env, STRATEGY_OVERLAY_YEARLY_CC)) == 1
