"""YL-1: ``--expiry-type`` on ``--auto-collar`` (one shared December expiry, pair validated)."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts.strategies.three_track import paper_3track_overlay_entry as oe
from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_OVERLAY, STRATEGY_OVERLAY_YEARLY_COLLAR
from src.paper.models import PaperTrade
from src.paper.store import PaperStore
from tests.unit.scripts.test_overlay_chain_wiring import (
    BOD,
    DEC_2026_MS,
    TODAY,
    _bod_chain,
    _vix_patches,
)

_DEC = "2026-12-29"


@pytest.fixture
def env(tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Patch every external seam of ``main`` and expose the tmp store + gate spy."""
    raw = _bod_chain(DEC_2026_MS, _DEC)
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
    argv = ["x.py", "--auto-collar", "--bod-path", str(BOD), "--db-path", str(env["db"]), *flags]
    with patch("sys.argv", argv):
        oe.main()


def _collar_roles(env: dict[str, Any], strategy: str) -> set[str]:
    return {p.leg_role for p in env["store"].get_positions(strategy)}


def _ot(role: str, key: str) -> oe.OverlayTrade:
    action = TradeAction.BUY if role.endswith("put") else TradeAction.SELL
    trade = PaperTrade(
        strategy_name=STRATEGY_OVERLAY_YEARLY_COLLAR,
        leg_role=role,
        instrument_key=key,
        trade_date=TODAY,
        action=action,
        quantity=75,
        price=Decimal("100"),
    )
    return oe.OverlayTrade(trade=trade, strategy=trade.strategy_name, leg_role=role)


def test_yearly_collar_pair_on_same_december_expiry(env: dict[str, Any]) -> None:
    _main(env, "--expiry-type", "yearly")
    positions = env["store"].get_positions(STRATEGY_OVERLAY_YEARLY_COLLAR)
    assert _collar_roles(env, STRATEGY_OVERLAY_YEARLY_COLLAR) == {
        "overlay_collar_put",
        "overlay_collar_call",
    }
    expiry_of = oe._bod_expiry_resolver(BOD)
    assert {expiry_of(p.instrument_key) for p in positions} == {_DEC}
    assert _collar_roles(env, STRATEGY_OVERLAY) == set()
    assert env["gate"].call_args.args[1] == STRATEGY_OVERLAY_YEARLY_COLLAR


def test_pair_with_different_expiries_rejected() -> None:
    expiry_of = {"NSE_FO|62506": _DEC, "NSE_FO|OTHER": "2026-11-24"}.get
    pair = [_ot("overlay_collar_put", "NSE_FO|62506"), _ot("overlay_collar_call", "NSE_FO|OTHER")]
    with pytest.raises(SystemExit) as exc:
        oe._validate_collar_pairs(pair, expected_expiry=_DEC, expiry_of=expiry_of)
    assert exc.value.code == 1


def test_pair_with_unresolvable_leg_rejected() -> None:
    pair = [_ot("overlay_collar_put", "NSE_FO|62506"), _ot("overlay_collar_call", "NSE_FO|71505")]
    with pytest.raises(SystemExit) as exc:
        oe._validate_collar_pairs(pair, expected_expiry=_DEC, expiry_of=lambda _k: None)
    assert exc.value.code == 1


def test_expected_expiry_without_resolver_raises() -> None:
    pair = [_ot("overlay_collar_put", "NSE_FO|62506"), _ot("overlay_collar_call", "NSE_FO|71505")]
    with pytest.raises(ValueError):
        oe._validate_collar_pairs(pair, expected_expiry=_DEC)


def test_pair_on_expected_expiry_accepted() -> None:
    pair = [_ot("overlay_collar_put", "NSE_FO|62506"), _ot("overlay_collar_call", "NSE_FO|71505")]
    oe._validate_collar_pairs(pair, expected_expiry=_DEC, expiry_of=lambda _k: _DEC)


def test_monthly_collar_unchanged(env: dict[str, Any]) -> None:
    _main(env)
    assert _collar_roles(env, STRATEGY_OVERLAY) == {"overlay_collar_put", "overlay_collar_call"}
    assert _collar_roles(env, STRATEGY_OVERLAY_YEARLY_COLLAR) == set()
    assert env["gate"].call_args.args[1] == STRATEGY_OVERLAY


def test_pair_validation_without_expected_expiry_ignores_expiry() -> None:
    pair = [_ot("overlay_collar_put", "NSE_FO|62506"), _ot("overlay_collar_call", "NSE_FO|71505")]
    oe._validate_collar_pairs(pair)


def test_yearly_expiry_type_rejected_without_overlay_flag(env: dict[str, Any]) -> None:
    argv = ["x.py", "--expiry-type", "yearly", "--db-path", str(env["db"])]
    with patch("sys.argv", argv), pytest.raises(SystemExit) as exc:
        oe.main()
    assert exc.value.code != 0
