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
    option_type: str | None = None,
) -> PaperPosition:
    """Construct a ``PaperPosition`` for testing.

    Fields verified against get_code_snippet("PaperPosition") output (2026-07-02):
    strategy_name, leg_role, net_qty, avg_cost, avg_sell_price, instrument_key,
    option_type. As of B002.4, ``_position_delta`` classifies by ``option_type``
    (not by substring-matching ``instrument_key``), so callers must pass it
    explicitly — it is never inferred from ``instrument_key`` here, matching
    production behaviour where ``PaperStore`` resolves it via the BOD lookup.
    """
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=avg_cost,
        avg_sell_price=Decimal("0"),
        instrument_key=instrument_key,
        option_type=option_type,  # type: ignore[arg-type]
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
    pos = _make_position("NSE_FO|NIFTY25JUN23000PE", net_qty=-LOT_SIZE, option_type="PE")
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
    pos = _make_position("NSE_FO|NIFTY25JUN23000PE", net_qty=-(LOT_SIZE + 1), option_type="PE")
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots > Decimal(1)
    assert result.cap_breached is True


# ── Warning boundary ──────────────────────────────────────────────────────────


def test_aggregate_delta_exactly_at_options_warning() -> None:
    """Options delta exactly at OPTIONS_WARNING_LOTS: warning set, cap clear."""
    # net_qty that yields exactly 0.75 lots: 0.75 * LOT_SIZE = 48.75 → use 48 (< 0.75)
    # Use 49 lots short put: 49/65 ≈ 0.7538 > 0.75 → warning
    pos = _make_position("NSE_FO|NIFTY25JUN23000PE", net_qty=-49, option_type="PE")
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots > OPTIONS_WARNING_LOTS
    assert result.warning_breached is True
    assert result.cap_breached is False


def test_aggregate_delta_below_warning() -> None:
    """Options delta clearly below warning: both flags clear."""
    # 48 / 65 ≈ 0.738 < 0.75
    pos = _make_position("NSE_FO|NIFTY25JUN23000PE", net_qty=-48, option_type="PE")
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots < OPTIONS_WARNING_LOTS
    assert result.warning_breached is False
    assert result.cap_breached is False


# ── Long call — positive delta ────────────────────────────────────────────────


def test_aggregate_delta_long_call() -> None:
    """Long 1 lot of CE → positive delta, same sign as short put."""
    pos = _make_position("NSE_FO|NIFTY25JUN24000CE", net_qty=LOT_SIZE, option_type="CE")
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots == Decimal(1)


# ── Short call — negative delta ───────────────────────────────────────────────


def test_aggregate_delta_short_call_negative() -> None:
    """Short call reduces directional exposure → negative options delta."""
    pos = _make_position("NSE_FO|NIFTY25JUN25000CE", net_qty=-LOT_SIZE, option_type="CE")
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots == Decimal(-1)
    assert result.warning_breached is False
    assert result.cap_breached is False


# ── Long put — negative delta ─────────────────────────────────────────────────


def test_aggregate_delta_long_put_negative() -> None:
    """Long protective put → negative delta (hedges long exposure)."""
    pos = _make_position("NSE_FO|NIFTY25JUN22000PE", net_qty=LOT_SIZE, option_type="PE")
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
    short_put = _make_position("NSE_FO|NIFTY25JUN23000PE", net_qty=-LOT_SIZE, option_type="PE")
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
    """Long Nifty futures (option_type=FUT) → positive delta in options
    bucket."""
    pos = _make_position("NSE_FO|NIFTY25JUNFUT", net_qty=LOT_SIZE, option_type="FUT")
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots == Decimal(1)
    assert result.niftybees_delta_lots == Decimal(0)


# ── Chain-derived delta (B002.4) ─────────────────────────────────────────────


def test_aggregate_delta_uses_chain_derived_value_when_available() -> None:
    """position_deltas supplies the real (non ±1.0) delta; used as-is.

    A short 1-lot put with real delta ≈ +0.28 lots (not the ±1.0 approximation)
    is exactly BUG-002's original failure mode — this is the happy-path fix.
    """
    pos = _make_position("NSE_FO|NIFTY25JUN23000PE", net_qty=-LOT_SIZE, option_type="PE")
    chain_delta = Decimal("0.28")
    result = _tracker().aggregate_delta(
        [pos],
        NIFTY_SPOT,
        LOT_SIZE,
        position_deltas={"NSE_FO|NIFTY25JUN23000PE": chain_delta},
    )

    assert result.options_delta_lots == chain_delta
    assert result.total_delta_lots == chain_delta
    # 0.28 is well below both warning (0.75) and cap (1.0) — the ±1.0
    # approximation would have wrongly flagged a warning here.
    assert result.warning_breached is False
    assert result.cap_breached is False


def test_aggregate_delta_missing_from_chain_map_falls_back_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """instrument_key absent from position_deltas → WARNING + ±1.0 fallback.

    Edge case (B002.5): unrecognised/stale/missing chain coverage for an
    otherwise-classified option position must never silently misclassify —
    it degrades to the pre-B002.4 approximation with a logged WARNING, per
    council ruling 2026-07-02 (paper-phase fallback policy).
    """
    pos = _make_position("NSE_FO|NIFTY25JUN23000PE", net_qty=-LOT_SIZE, option_type="PE")

    with caplog.at_level("WARNING"):
        result = _tracker().aggregate_delta(
            [pos],
            NIFTY_SPOT,
            LOT_SIZE,
            position_deltas={"NSE_FO|SOME_OTHER_KEY": Decimal("0.3")},
        )

    # Falls back to the ±1.0 approximation (same as no map supplied at all).
    assert result.options_delta_lots == Decimal(1)
    assert result.warning_breached is True
    assert any("no chain-derived delta" in record.message for record in caplog.records)


def test_aggregate_delta_no_position_deltas_arg_behaves_as_before() -> None:
    """Omitting position_deltas keeps the pre-B002.4 approximation behavior."""
    pos = _make_position("NSE_FO|NIFTY25JUN24000CE", net_qty=LOT_SIZE, option_type="CE")
    result = _tracker().aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.options_delta_lots == Decimal(1)


# ── Unknown instrument ────────────────────────────────────────────────────────


def test_aggregate_delta_unknown_instrument_skipped() -> None:
    """Unresolved option_type (None) logs warning and contributes zero delta.

    Mirrors production: PaperStore leaves option_type=None when instrument_key
    can't be resolved via InstrumentLookup (unrecognised/legacy key). Must not
    be silently misclassified as a full-delta future (B002.5 edge case).
    """
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
    pos = _make_position(
        "NSE_FO|NIFTY25JUN23000PE", net_qty=-26, option_type="PE"
    )  # 26/65 ≈ 0.4 lots
    result = tight_tracker.aggregate_delta([pos], NIFTY_SPOT, LOT_SIZE)

    assert result.warning_breached is True
    assert result.cap_breached is False
