"""Tests for yearly overlay registration in the monitor daemon (YW-1)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scripts.monitor_daemon import register_overlays
from src.paper.constants import (
    STRATEGY_OVERLAY,
    STRATEGY_OVERLAY_YEARLY_CC,
    STRATEGY_OVERLAY_YEARLY_COLLAR,
    STRATEGY_OVERLAY_YEARLY_PP,
)
from src.strategy.overlay_tenor import OVERLAY_TENORS


def _register(tmp_path, yearly: bool, chain_source=None) -> list:
    strategies: list = []
    register_overlays(
        strategies,
        store=MagicMock(),
        notifier=MagicMock(),
        vix_data_dir=tmp_path,
        yearly=yearly,
        chain_source=chain_source,
    )
    return strategies


def test_flag_off_registers_monthly_only(tmp_path) -> None:
    strategies = _register(tmp_path, yearly=False)
    assert len(strategies) == 3
    assert {s.strategy_name for s in strategies} == {STRATEGY_OVERLAY}
    assert all(not hasattr(s, "due_interval_s") for s in strategies)


def test_flag_on_registers_yearly_instances_with_yearly_namespace(tmp_path) -> None:
    chain = MagicMock()
    strategies = _register(tmp_path, yearly=True, chain_source=chain)
    assert len(strategies) == 6
    yearly = [s for s in strategies if s.strategy_name != STRATEGY_OVERLAY]
    assert {s.strategy_name for s in yearly} == {
        STRATEGY_OVERLAY_YEARLY_CC,
        STRATEGY_OVERLAY_YEARLY_PP,
        STRATEGY_OVERLAY_YEARLY_COLLAR,
    }
    assert all(s.tenor is OVERLAY_TENORS["yearly"] for s in yearly)
    assert all(s.due_interval_s == 3600 for s in yearly)
    collar = next(s for s in yearly if s.strategy_name == STRATEGY_OVERLAY_YEARLY_COLLAR)
    assert collar._chain_source is chain


def test_yearly_reentry_hint_derived_from_policy(tmp_path) -> None:
    strategies = _register(tmp_path, yearly=True, chain_source=MagicMock())
    hints = {s.strategy_name: s.reentry_script_hint for s in strategies}
    assert hints[STRATEGY_OVERLAY_YEARLY_CC] == (
        "run paper_3track_overlay_entry.py --auto-cc --expiry-type yearly"
    )
    assert hints[STRATEGY_OVERLAY_YEARLY_PP].endswith("--auto-pp --expiry-type yearly")
    assert hints[STRATEGY_OVERLAY_YEARLY_COLLAR].endswith("--auto-collar --expiry-type yearly")
    monthly = [s for s in strategies if s.strategy_name == STRATEGY_OVERLAY]
    assert all("find_overlay_strikes.py" in s.reentry_script_hint for s in monthly)


def test_yearly_without_chain_source_fails_loudly(tmp_path) -> None:
    with pytest.raises(ValueError, match="chain_source"):
        _register(tmp_path, yearly=True, chain_source=None)


def test_one_instance_failure_does_not_block_others(tmp_path, monkeypatch) -> None:
    import scripts.monitor_daemon as daemon

    monkeypatch.setattr(daemon, "PPOverlayV1", MagicMock(side_effect=RuntimeError("boom")))
    strategies = _register(tmp_path, yearly=True, chain_source=MagicMock())
    assert len(strategies) == 4


def test_policy_reentry_hint_monthly_keeps_legacy_flow() -> None:
    assert (
        OVERLAY_TENORS["monthly"].reentry_hint("pp")
        == "run find_overlay_strikes.py --overlay-type pp"
    )
