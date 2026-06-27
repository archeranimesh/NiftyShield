"""Tests for IronCondorV2 strategy registration and naming.

IC-V2-5 story: Register paper_ic_nifty_v2_monthly in daemon and factory.
"""

from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from src.strategy.ic_expiry_config_v2 import IC_V2_MONTHLY, CONFIGS_V2, IronCondorV2ExpiryConfig
from src.strategy.ic_nifty_v2 import IronCondorV2


class TestIronCondorV2RegistrationName(unittest.TestCase):
    """Verify strategy name generation and uniqueness."""

    def test_v2_monthly_strategy_name(self) -> None:
        """Assert IronCondorV2 with monthly config produces correct strategy name."""
        # Arrange
        broker = MagicMock()
        store = MagicMock()
        notifier = MagicMock()
        config = IC_V2_MONTHLY

        # Act
        strategy = IronCondorV2(
            broker=broker,
            store=store,
            notifier=notifier,
            config=config,
        )

        # Assert
        self.assertEqual(strategy.strategy_name, "paper_ic_nifty_v2_monthly")

    def test_v2_not_same_as_v1_name(self) -> None:
        """Verify V2 strategy name does not collide with V1."""
        # V1 would be "paper_ic_nifty_v1_monthly"
        # V2 is "paper_ic_nifty_v2_monthly"
        broker = MagicMock()
        store = MagicMock()
        notifier = MagicMock()

        strategy_v2 = IronCondorV2(
            broker=broker,
            store=store,
            notifier=notifier,
            config=IC_V2_MONTHLY,
        )

        # Assert no V1 collision
        self.assertNotEqual(strategy_v2.strategy_name, "paper_ic_nifty_v1_monthly")
        self.assertTrue(strategy_v2.strategy_name.startswith("paper_ic_nifty_v2_"))

    def test_configs_v2_has_monthly(self) -> None:
        """Verify CONFIGS_V2 registry includes 'monthly' key."""
        self.assertIn("monthly", CONFIGS_V2)

    def test_configs_v2_monthly_equals_ic_v2_monthly(self) -> None:
        """Verify CONFIGS_V2['monthly'] is the IC_V2_MONTHLY preset."""
        self.assertIs(CONFIGS_V2["monthly"], IC_V2_MONTHLY)

    def test_ic_v2_monthly_is_frozen(self) -> None:
        """Verify IC_V2_MONTHLY config is immutable (frozen dataclass)."""
        # Attempt to mutate should raise FrozenInstanceError
        with self.assertRaises(Exception):
            # type: ignore
            IC_V2_MONTHLY.expiry_type = "weekly"

    def test_ic_v2_config_fields_present(self) -> None:
        """Verify IC_V2_MONTHLY has all required fields."""
        self.assertEqual(IC_V2_MONTHLY.expiry_type, "monthly")
        self.assertEqual(IC_V2_MONTHLY.short_put_delta_target, Decimal("0.25"))
        self.assertEqual(IC_V2_MONTHLY.short_call_delta_target, Decimal("0.22"))
        self.assertEqual(IC_V2_MONTHLY.long_wing_delta_target, Decimal("0.10"))
        self.assertEqual(IC_V2_MONTHLY.long_wing_delta_floor, Decimal("0.05"))
        self.assertEqual(IC_V2_MONTHLY.long_wing_min_premium, Decimal("15"))
        self.assertEqual(IC_V2_MONTHLY.roll_trigger_delta, Decimal("0.35"))
        self.assertEqual(IC_V2_MONTHLY.roll_warn_delta, Decimal("0.30"))
        self.assertEqual(IC_V2_MONTHLY.forced_close_delta, Decimal("0.45"))
        self.assertEqual(IC_V2_MONTHLY.roll_debit_cap_fraction, Decimal("0.50"))
        self.assertEqual(IC_V2_MONTHLY.max_rolls_per_side_per_cycle, 1)
        self.assertEqual(IC_V2_MONTHLY.monthly_close_full_dte, 7)


if __name__ == "__main__":
    unittest.main()
