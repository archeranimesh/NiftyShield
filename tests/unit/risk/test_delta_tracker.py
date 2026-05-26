# tests/unit/risk/test_delta_tracker.py
"""Unit tests for PortfolioDeltaTracker and check_entry_allowed.

All tests are offline — no network, no DB, no broker calls.
PaperPosition is a frozen dataclass; construct directly from field values.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.paper.constants import LOT_SIZE, NIFTYBEES_KEY
from src.paper.models import PaperPosition
from src.risk.delta_tracker import (
    COMBINED_CAP_LOTS,
    COMBINED_WARNING_LOTS,
    OPTIONS_CAP_LOTS,
    OPTIONS_WARNING_LOTS,
    PortfolioDeltaTracker,
)
from src.risk.entry_gate import check_entry_allowed
from src.risk.models import PortfolioDelta

# ── Helpers ───────────────────────────────────────────────────────────────────

NIFTY_SPOT = Decimal("24000")


def _make_position(
    instrument_key: str,
    net_qty: int,
    avg_cost: Decimal = Decimal("100"),
    strategy_name: str = "paper_csp_nifty_v1",
    leg_role: str = "test_leg",
) -> PaperPosition:
    """Construct a ``PaperPosition`` for testing.

    Fields verified against get_code_snippet("PaperPosition") output (2026-05-26):
    strategy_name, leg_role, net_qty, avg_cost, avg_sell_price, instrument_key.
    """
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=avg_cost,
        avg_sell_price=Decimal("0"),
        instrument_key=instrument_key,
    )


def _tracker() -> PortfolioDeltaTracker:
    return PortfolioDeltaTracker()


# ── Zero-position base case ───────────────────────────────────────────────────


def test_aggregate_delta_empty_positions() -> None:
    """Empty position list → all deltas zero, no breaches."""
    result = _tracker().aggregate_delta([], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots == Decimal(0)
    assert result.niftybees_delta_lots == Decimal(0)
    assert result.total_delta_lots == Decimal(0)
    assert result.warning_breached is False
    assert result.cap_breached is False


# ── Short put (CSP) — positive delta ─────────────────────────────────────────


def test_aggregate_delta_short_put_happy_path() -> None:
    """Short 1 lot of PE → positive delta of 1.0 lot; no breach at this level."""
    pos = _make_position("NSE_FO|NIFTY25JUN23000PE", net_qty=-LOT_SIZE)
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots == Decimal(1)
    assert result.niftybees_delta_lots == Decimal(0)
    assert result.total_delta_lots == Decimal(1)
    # options delta == OPTIONS_CAP (1.0) → cap breached (strict >? No, > not >=)
    # Actually 1.0 == OPTIONS_CAP_LOTS; cap uses strict >, so NOT breached at exactly 1.0
    assert result.cap_breached is False
    assert result.warning_breached is True  # 1.0 > OPTIONS_WARNING (0.75)


def test_aggregate_delta_short_put_cap_breached() -> None:
    """Short > 1 lot of PE → options cap breached."""
    pos = _make_position("NSE_FO|NIFTY25JUN23000PE", net_qty=-(LOT_SIZE + 1))
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots > Decimal(1)
    assert result.cap_breached is True


# ── Warning boundary ──────────────────────────────────────────────────────────


def test_aggregate_delta_exactly_at_options_warning() -> None:
    """Options delta exactly at OPTIONS_WARNING_LOTS: warning set, cap clear."""
    # net_qty that yields exactly 0.75 lots: 0.75 * LOT_SIZE = 48.75 → use 48 (< 0.75)
    # Use 49 lots short put: 49/65 ≈ 0.7538 > 0.75 → warning
    pos = _make_position("NSE_FO|NIFTY25JUN23000PE", net_qty=-49)
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots > OPTIONS_WARNING_LOTS
    assert result.warning_breached is True
    assert result.cap_breached is False


def test_aggregate_delta_below_warning() -> None:
    """Options delta clearly below warning: both flags clear."""
    # 48 / 65 ≈ 0.738 < 0.75
    pos = _make_position("NSE_FO|NIFTY25JUN23000PE", net_qty=-48)
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots < OPTIONS_WARNING_LOTS
    assert result.warning_breached is False
    assert result.cap_breached is False


# ── Long call — positive delta ────────────────────────────────────────────────


def test_aggregate_delta_long_call() -> None:
    """Long 1 lot of CE → positive delta, same sign as short put."""
    pos = _make_position("NSE_FO|NIFTY25JUN24000CE", net_qty=LOT_SIZE)
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots == Decimal(1)


# ── Short call — negative delta ───────────────────────────────────────────────


def test_aggregate_delta_short_call_negative() -> None:
    """Short call reduces directional exposure → negative options delta."""
    pos = _make_position("NSE_FO|NIFTY25JUN25000CE", net_qty=-LOT_SIZE)
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots == Decimal(-1)
    assert result.warning_breached is False
    assert result.cap_breached is False


# ── Long put — negative delta ─────────────────────────────────────────────────


def test_aggregate_delta_long_put_negative() -> None:
    """Long protective put → negative delta (hedges long exposure)."""
    pos = _make_position("NSE_FO|NIFTY25JUN22000PE", net_qty=LOT_SIZE)
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots == Decimal(-1)


# ── NiftyBees ETF ─────────────────────────────────────────────────────────────


def test_aggregate_delta_niftybees_only() -> None:
    """NiftyBees ETF contributes to niftybees_delta_lots, not options bucket."""
    # 65 units at avg_cost 240 → notional = 65 * 240 = 15600
    # niftybees_lots = 15600 / (24000 * 65) = 15600 / 1560000 ≈ 0.01
    pos = _make_position(
        NIFTYBEES_KEY,
        net_qty=65,
        avg_cost=Decimal("240"),
    )
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots == Decimal(0)
    expected = Decimal(65) * Decimal("240") / (NIFTY_SPOT * Decimal(LOT_SIZE))
    assert result.niftybees_delta_lots == expected
    assert result.total_delta_lots == expected


# ── Combined breach (NiftyBees + options) ─────────────────────────────────────


def test_aggregate_delta_combined_cap_breach() -> None:
    """Options below options cap but combined with NiftyBees exceeds combined cap."""
    # 1 lot short put = options_delta = 1.0 (at OPTIONS_CAP, not breached)
    # Large NiftyBees holding → total > COMBINED_CAP (2.0)
    short_put = _make_position("NSE_FO|NIFTY25JUN23000PE", net_qty=-LOT_SIZE)
    # NiftyBees: qty * avg_cost / (24000 * 65) > 1.0 → qty * 240 > 1_560_000 → qty > 6500
    niftybees = _make_position(
        NIFTYBEES_KEY,
        net_qty=7000,  # 7000 * 240 / 1_560_000 ≈ 1.077 lots
        avg_cost=Decimal("240"),
        leg_role="base_etf",
    )
    result = _tracker().aggregate_delta([short_put, niftybees], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots == Decimal(1)
    assert result.niftybees_delta_lots > Decimal(1)
    assert result.total_delta_lots > COMBINED_CAP_LOTS
    assert result.cap_breached is True


# ── Futures delta ─────────────────────────────────────────────────────────────


def test_aggregate_delta_long_futures() -> None:
    """Long Nifty futures (NSE_FO, no CE/PE) → positive delta in options bucket."""
    pos = _make_position("NSE_FO|NIFTY25JUNFUT", net_qty=LOT_SIZE)
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots == Decimal(1)
    assert result.niftybees_delta_lots == Decimal(0)


# ── Unknown instrument ────────────────────────────────────────────────────────


def test_aggregate_delta_unknown_instrument_skipped() -> None:
    """Unrecognised instrument_key logs warning and contributes zero delta."""
    pos = _make_position("NSE_EQ|UNKNOWN_EQUITY", net_qty=100)
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots == Decimal(0)
    assert result.niftybees_delta_lots == Decimal(0)


# ── Input validation ──────────────────────────────────────────────────────────


def test_aggregate_delta_zero_spot_raises() -> None:
    with pytest.raises(ValueError, match="nifty_spot"):
        _tracker().aggregate_delta([], Decimal(0), LOT_SIZE)


def test_aggregate_delta_zero_lot_size_raises() -> None:
    with pytest.raises(ValueError, match="lot_size"):
        _tracker().aggregate_delta([], NIFTY_SPOT, 0)


def test_aggregate_delta_negative_spot_raises() -> None:
    with pytest.raises(ValueError, match="nifty_spot"):
        _tracker().aggregate_delta([], Decimal("-1"), LOT_SIZE)


# ── entry_gate: check_entry_allowed ──────────────────────────────────────────


def _make_delta(
    options: Decimal = Decimal(0),
    niftybees: Decimal = Decimal(0),
    warning: bool = False,
    cap: bool = False,
) -> PortfolioDelta:
    """Construct a PortfolioDelta for gate tests without touching the tracker."""
    from datetime import datetime, timezone

    return PortfolioDelta(
        options_delta_lots=options,
        niftybees_delta_lots=niftybees,
        total_delta_lots=options + niftybees,
        warning_breached=warning,
        cap_breached=cap,
        as_of=datetime.now(tz=timezone.utc),
    )


def test_entry_allowed_no_breach() -> None:
    """No breach → entry allowed, empty reason."""
    delta = _make_delta()
    allowed, reason = check_entry_allowed(delta, Decimal("1"), is_protective=False)

    assert allowed is True
    assert reason == ""


def test_entry_blocked_at_cap() -> None:
    """Cap breached → entry blocked, non-empty reason."""
    delta = _make_delta(options=Decimal("1.1"), warning=True, cap=True)
    allowed, reason = check_entry_allowed(delta, Decimal("1"), is_protective=False)

    assert allowed is False
    assert "hard cap" in reason.lower()


def test_entry_allowed_with_warning() -> None:
    """Warning breached but not cap → entry allowed with WARNING prefix in reason."""
    delta = _make_delta(options=Decimal("0.8"), warning=True, cap=False)
    allowed, reason = check_entry_allowed(delta, Decimal("1"), is_protective=False)

    assert allowed is True
    assert "WARNING" in reason


def test_entry_protective_bypasses_cap() -> None:
    """Protective trade bypasses cap unconditionally."""
    delta = _make_delta(options=Decimal("2"), warning=True, cap=True)
    allowed, reason = check_entry_allowed(delta, Decimal("-1"), is_protective=True)

    assert allowed is True
    assert reason == ""


def test_entry_protective_bypasses_warning() -> None:
    """Protective trade bypasses even warning state."""
    delta = _make_delta(options=Decimal("0.8"), warning=True, cap=False)
    allowed, reason = check_entry_allowed(delta, Decimal("-1"), is_protective=True)

    assert allowed is True
    assert reason == ""


# ── Custom thresholds ─────────────────────────────────────────────────────────


def test_custom_thresholds_respected() -> None:
    """Tracker constructed with tighter thresholds fires earlier."""
    tight_tracker = PortfolioDeltaTracker(
        options_warning=Decimal("0.3"),
        options_cap=Decimal("0.5"),
        combined_warning=Decimal("0.6"),
        combined_cap=Decimal("1.0"),
    )
    # 0.4 lots short put — above tight warning (0.3), below tight cap (0.5)
    pos = _make_position("NSE_FO|NIFTY25JUN23000PE", net_qty=-26)  # 26/65 ≈ 0.4 lots
    result = tight_tracker.aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.warning_breached is True
    assert result.cap_breached is False
