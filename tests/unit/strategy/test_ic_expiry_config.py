# tests/unit/strategy/test_ic_expiry_config.py
"""Structural invariant tests for ICExpiryConfig and CONFIGS registry."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from src.paper import constants
from src.strategy.ic_expiry_config import CONFIGS, ICExpiryConfig


def test_configs_has_four_keys() -> None:
    assert set(CONFIGS.keys()) == {"weekly", "monthly", "leaps", "yearly"}


def test_strategy_names_match_constants() -> None:
    for expiry_type, config in CONFIGS.items():
        expected = getattr(constants, f"STRATEGY_IC_{expiry_type.upper()}")
        assert config.strategy_name == expected, (
            f"{expiry_type}: strategy_name={config.strategy_name!r} != {expected!r}"
        )


def test_time_stop_lt_dte_warn() -> None:
    for expiry_type, config in CONFIGS.items():
        assert config.time_stop_dte < config.dte_warn, (
            f"{expiry_type}: time_stop_dte={config.time_stop_dte} >= dte_warn={config.dte_warn}"
        )


def test_dte_warn_lo_lt_dte_warn_hi() -> None:
    for expiry_type, config in CONFIGS.items():
        assert config.dte_warn_lo < config.dte_warn_hi, (
            f"{expiry_type}: dte_warn_lo={config.dte_warn_lo} >= dte_warn_hi={config.dte_warn_hi}"
        )


def test_all_decimal_fields_are_decimal() -> None:
    decimal_fields = [
        "short_put_delta",
        "short_call_delta",
        "delta_range",
        "ivr_gate",
        "profit_target_pct",
        "loss_stop_pct",
        "delta_stop",
        "delta_warn",
        "roll_wing_delta_lo",
        "roll_wing_delta_hi",
        "roll_wing_target_delta",
    ]
    for expiry_type, config in CONFIGS.items():
        for field in decimal_fields:
            value = getattr(config, field)
            assert isinstance(value, Decimal), (
                f"{expiry_type}.{field}={value!r} is not Decimal (got {type(value).__name__})"
            )


def test_frozen_raises_on_assignment() -> None:
    config = CONFIGS["monthly"]
    with pytest.raises((FrozenInstanceError, AttributeError)):
        config.short_put_delta = Decimal("0.99")  # type: ignore[misc]
