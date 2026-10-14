"""Variant registry and cycle-policy handoff for the Nifty calendar factory."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from src.nifty_calendar.config import BIWEEKLY, MONTHLY
from src.nifty_calendar.cycle import BiweeklyCyclePolicy, MonthlyCyclePolicy
from src.nifty_calendar.exit_rules import BiweeklyExitRule, MonthlyExitRule
from src.strategy.nifty_calendar_factory import REGISTRY, build_calendar_shell, build_cycle_policies
from tests.unit.strategy.test_nifty_calendar_v1 import _lookup


def test_registry_lookup_both_variants() -> None:
    assert set(REGISTRY) == {"monthly", "biweekly"}
    assert REGISTRY["monthly"].config is MONTHLY and REGISTRY["monthly"].rule_cls is MonthlyExitRule
    assert REGISTRY["biweekly"].config is BIWEEKLY
    assert REGISTRY["biweekly"].rule_cls is BiweeklyExitRule
    policies = build_cycle_policies(_lookup(), date(2026, 9, 30))
    assert isinstance(policies["monthly"], MonthlyCyclePolicy)
    assert isinstance(policies["biweekly"], BiweeklyCyclePolicy)


def test_unknown_variant_rejected() -> None:
    bad = MONTHLY.__class__(**{**MONTHLY.__dict__, "name": "weekly"})
    with pytest.raises(KeyError):
        build_calendar_shell(
            broker=MagicMock(), store=MagicMock(), notifier=None, lookup=_lookup(), config=bad
        )
