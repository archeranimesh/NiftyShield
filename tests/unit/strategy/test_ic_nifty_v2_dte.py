"""Tests for IC-V2-3: DTE-tiered exit logic in IronCondorV2.

Covers _evaluate_dte_action, _should_close_full, and _roll_allowed_by_dte.

All tests are offline (no network, no DB, no chain data required).
Council ruling: docs/archive/council/strategy/2026-06-26_ic-v2-core-design.md
Stage 3 — Decision D4 (DTE-tiered exit, monthly).

Test list (from stories.md IC-V2-3):
  test_monthly_dte_gt_7_normal
  test_monthly_dte_7_close_full
  test_monthly_dte_1_force_close
  test_roll_allowed_by_dte_monthly
  test_dte_0_is_force_close
"""

from __future__ import annotations

from src.strategy.ic_expiry_config_v2 import IronCondorV2ExpiryConfig
from src.strategy.ic_nifty_v2 import IronCondorV2

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_strategy(config: IronCondorV2ExpiryConfig | None = None) -> IronCondorV2:
    """Return an IronCondorV2 instance with no dependencies.

    Args:
        config: Config to inject; defaults to IC_V2_MONTHLY.

    Returns:
        IronCondorV2 with broker/store/notifier all None.
    """
    return IronCondorV2(config=config)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_monthly_dte_gt_7_normal() -> None:
    """DTE > 7 on a monthly IC → _evaluate_dte_action returns 'NORMAL'.

    Happy-path: well away from any close threshold; normal roll rules apply.
    council ruling D4: dte > 7 → NORMAL.
    """
    strategy = _make_strategy()
    result = strategy._evaluate_dte_action(dte=8)
    assert result == "NORMAL"


def test_monthly_dte_7_close_full() -> None:
    """DTE exactly 7 (boundary) → _evaluate_dte_action returns 'CLOSE_FULL'.

    Boundary condition: DTE == monthly_close_full_dte (=7) triggers CLOSE_FULL.
    council ruling D4: dte ≤ 7 → CLOSE_FULL (refineable during backtest).
    """
    strategy = _make_strategy()
    result = strategy._evaluate_dte_action(dte=7)
    assert result == "CLOSE_FULL"


def test_monthly_dte_1_force_close() -> None:
    """DTE = 1 → _evaluate_dte_action returns 'FORCE_CLOSE' (supersedes CLOSE_FULL).

    council ruling D4: dte ≤ 1 → FORCE_CLOSE; no discretion.
    FORCE_CLOSE is evaluated before CLOSE_FULL so it always wins.
    """
    strategy = _make_strategy()
    result = strategy._evaluate_dte_action(dte=1)
    assert result == "FORCE_CLOSE"


def test_roll_allowed_by_dte_monthly() -> None:
    """_roll_allowed_by_dte returns False for dte≤7, True for dte>7.

    Parameterised over boundary and interior values on both sides.
    This predicate is injected into _evaluate_adjustment as roll_allowed_by_dte.
    """
    strategy = _make_strategy()

    # Roll BLOCKED at or below the threshold
    assert strategy._roll_allowed_by_dte(dte=7) is False
    assert strategy._roll_allowed_by_dte(dte=5) is False
    assert strategy._roll_allowed_by_dte(dte=1) is False

    # Roll ALLOWED strictly above the threshold
    assert strategy._roll_allowed_by_dte(dte=8) is True
    assert strategy._roll_allowed_by_dte(dte=15) is True
    assert strategy._roll_allowed_by_dte(dte=30) is True


def test_dte_0_is_force_close() -> None:
    """DTE = 0 (expiry day) → FORCE_CLOSE.

    Edge case: day-of-expiry must still trigger FORCE_CLOSE, not CLOSE_FULL.
    DTE=0 satisfies dte ≤ 1, so FORCE_CLOSE takes precedence.
    """
    strategy = _make_strategy()
    result = strategy._evaluate_dte_action(dte=0)
    assert result == "FORCE_CLOSE"


def test_should_close_full_monthly() -> None:
    """_should_close_full returns True for dte≤7, False for dte>7."""
    strategy = _make_strategy()

    # Close full triggered at or below the threshold
    assert strategy._should_close_full(dte=7) is True
    assert strategy._should_close_full(dte=5) is True
    assert strategy._should_close_full(dte=1) is True

    # Close full NOT triggered above the threshold
    assert strategy._should_close_full(dte=8) is False
    assert strategy._should_close_full(dte=15) is False
