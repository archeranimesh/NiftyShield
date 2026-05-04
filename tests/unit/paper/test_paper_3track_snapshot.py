"""Unit tests for scripts/paper_3track_snapshot.py.

Coverage:
- _fmt: positive, negative, zero formatting.
- _delta_arrow: positive (▲), negative (▼), zero (±0), None (no prior).
- _hedge_verdict: all four verdict paths.
- _leg_delta: returns None when no prior snapshot; returns correct delta when prior exists.
- _base_leg_role: correct mapping for all three tracks.
- _save_nav_snapshot: roundtrips through store.get_nav_snapshots.
- _save_leg_snapshots: writes base + overlay leg snapshots; total_pnl invariant satisfied.
- _save_leg_snapshots: written snap retrievable via get_leg_snapshot.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import scripts.paper_3track_snapshot as snap_mod
from src.models.portfolio import TradeAction
from src.paper.models import PaperLegSnapshot, PaperNavSnapshot, PaperTrade
from src.paper.store import PaperStore
from src.paper.track_snapshot import TrackGreeks, TrackPnL, TrackSnapshot


# ── Helpers ───────────────────────────────────────────────────────────────────

_STRATEGY = "paper_nifty_spot"
_DATE = date(2026, 5, 7)
_PREV_DATE = date(2026, 5, 6)


def _make_store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "test.db")


def _make_snapshot(
    base_pnl: Decimal = Decimal("1000"),
    overlay_pnls: dict | None = None,
    unrealized: Decimal = Decimal("800"),
    realized: Decimal = Decimal("200"),
) -> TrackSnapshot:
    overlay_pnls = overlay_pnls or {}
    net = base_pnl + sum(overlay_pnls.values())
    return TrackSnapshot(
        track_name=_STRATEGY,
        pnl=TrackPnL(
            base_pnl=base_pnl,
            overlay_pnls=overlay_pnls,
            net_pnl=net,
            unrealized_pnl=unrealized,
            realized_pnl=realized,
        ),
        greeks=TrackGreeks(Decimal("0.92"), Decimal("-5"), Decimal("10")),
        max_drawdown_abs=Decimal("-500"),
        max_drawdown_pct=Decimal("-2.5"),
        return_on_nee=Decimal("1.05"),
    )


def _make_trade(
    strategy: str = _STRATEGY,
    leg_role: str = "base_etf",
    action: TradeAction = TradeAction.BUY,
    trade_date: date = _DATE,
) -> PaperTrade:
    return PaperTrade(
        strategy_name=strategy,
        leg_role=leg_role,
        instrument_key="NSE_EQ|NIFTYBEES",
        trade_date=trade_date,
        action=action,
        quantity=65,
        price=Decimal("240.00"),
    )


def _leg_snap(
    strategy: str = _STRATEGY,
    leg_role: str = "base_etf",
    snap_date: date = _PREV_DATE,
    total_pnl: Decimal = Decimal("500"),
) -> PaperLegSnapshot:
    unrealized = total_pnl - Decimal("100")
    realized   = Decimal("100")
    return PaperLegSnapshot(
        strategy_name=strategy,
        leg_role=leg_role,
        snapshot_date=snap_date,
        unrealized_pnl=unrealized,
        realized_pnl=realized,
        total_pnl=total_pnl,
        ltp=Decimal("245.00"),
    )


# ── _fmt ─────────────────────────────────────────────────────────────────────


def test_fmt_positive() -> None:
    assert snap_mod._fmt(Decimal("1234")) == "+1,234"


def test_fmt_negative() -> None:
    assert snap_mod._fmt(Decimal("-5678")) == "-5,678"


def test_fmt_zero() -> None:
    assert snap_mod._fmt(Decimal("0")) == "+0"


# ── _delta_arrow ──────────────────────────────────────────────────────────────


def test_delta_arrow_positive() -> None:
    result = snap_mod._delta_arrow(Decimal("300"))
    assert "▲" in result
    assert "+300" in result


def test_delta_arrow_negative() -> None:
    result = snap_mod._delta_arrow(Decimal("-200"))
    assert "▼" in result
    assert "-200" in result


def test_delta_arrow_zero() -> None:
    result = snap_mod._delta_arrow(Decimal("0"))
    assert "±0" in result


def test_delta_arrow_none() -> None:
    result = snap_mod._delta_arrow(None)
    assert "no prior" in result


# ── _hedge_verdict ────────────────────────────────────────────────────────────


def test_hedge_verdict_fully_protected() -> None:
    # base loss, overlay gain that reduces net loss
    verdict = snap_mod._hedge_verdict(Decimal("-1000"), Decimal("600"))
    assert "Protected" in verdict
    assert "60%" in verdict


def test_hedge_verdict_partial() -> None:
    # overlay gain > abs(base loss) — absorbed > 100%? Actually this means net positive
    # Real partial: overlay < base loss, but some help
    verdict = snap_mod._hedge_verdict(Decimal("-1000"), Decimal("300"))
    assert "Protected" in verdict or "Partial" in verdict


def test_hedge_verdict_no_protection() -> None:
    verdict = snap_mod._hedge_verdict(Decimal("-1000"), Decimal("-200"))
    assert "No protection" in verdict


def test_hedge_verdict_overlay_drag_on_up_move() -> None:
    verdict = snap_mod._hedge_verdict(Decimal("1000"), Decimal("-150"))
    assert "drag" in verdict or "Overlay" in verdict


# ── _leg_delta ────────────────────────────────────────────────────────────────


def test_leg_delta_no_prior_returns_none(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    result = snap_mod._leg_delta(store, _STRATEGY, "base_etf", Decimal("1000"), _DATE)
    assert result is None


def test_leg_delta_with_prior_returns_diff(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    # Record a prior snapshot on _PREV_DATE
    store.record_leg_snapshot(_leg_snap(total_pnl=Decimal("500")))
    result = snap_mod._leg_delta(store, _STRATEGY, "base_etf", Decimal("700"), _DATE)
    assert result == Decimal("200")


def test_leg_delta_negative_movement(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.record_leg_snapshot(_leg_snap(total_pnl=Decimal("800")))
    result = snap_mod._leg_delta(store, _STRATEGY, "base_etf", Decimal("600"), _DATE)
    assert result == Decimal("-200")


# ── _base_leg_role ────────────────────────────────────────────────────────────


def test_base_leg_role_spot() -> None:
    assert snap_mod._base_leg_role("paper_nifty_spot") == "base_etf"


def test_base_leg_role_futures() -> None:
    assert snap_mod._base_leg_role("paper_nifty_futures") == "base_futures"


def test_base_leg_role_proxy() -> None:
    assert snap_mod._base_leg_role("paper_nifty_proxy") == "base_ditm_call"


# ── _save_nav_snapshot ────────────────────────────────────────────────────────


def test_save_nav_snapshot_roundtrip(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    snapshot = _make_snapshot(
        base_pnl=Decimal("1000"),
        unrealized=Decimal("800"),
        realized=Decimal("200"),
    )
    snap_mod._save_nav_snapshot(store, _STRATEGY, snapshot, _DATE, Decimal("24000"))

    snaps = store.get_nav_snapshots(_STRATEGY)
    assert len(snaps) == 1
    s = snaps[0]
    assert s.strategy_name == _STRATEGY
    assert s.snapshot_date == _DATE
    assert s.total_pnl == Decimal("1000")
    assert s.unrealized_pnl == Decimal("800")
    assert s.realized_pnl == Decimal("200")
    assert s.underlying_price == Decimal("24000")


def test_save_nav_snapshot_upsert(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    snap_mod._save_nav_snapshot(
        store, _STRATEGY,
        _make_snapshot(base_pnl=Decimal("100"), unrealized=Decimal("100"), realized=Decimal("0")),
        _DATE, Decimal("24000"),
    )
    snap_mod._save_nav_snapshot(
        store, _STRATEGY,
        _make_snapshot(base_pnl=Decimal("999"), unrealized=Decimal("999"), realized=Decimal("0")),
        _DATE, Decimal("24000"),
    )
    snaps = store.get_nav_snapshots(_STRATEGY)
    assert len(snaps) == 1
    assert snaps[0].total_pnl == Decimal("999")


# ── _save_leg_snapshots ───────────────────────────────────────────────────────


def test_save_leg_snapshots_base_only(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    trade = _make_trade()
    store.record_trade(trade)

    snapshot = _make_snapshot(
        base_pnl=Decimal("1000"),
        overlay_pnls={},
        unrealized=Decimal("800"),
        realized=Decimal("200"),
    )
    snap_mod._save_leg_snapshots(store, _STRATEGY, snapshot, _DATE, ltp_map={})

    result = store.get_leg_snapshot(_STRATEGY, "base_etf", _DATE)
    assert result is not None
    assert result.total_pnl == result.unrealized_pnl + result.realized_pnl


def test_save_leg_snapshots_with_overlay(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.record_trade(_make_trade(leg_role="base_etf"))
    store.record_trade(PaperTrade(
        strategy_name=_STRATEGY,
        leg_role="overlay_pp",
        instrument_key="NSE_FO|NIFTY22000PE",
        trade_date=_DATE,
        action=TradeAction.BUY,
        quantity=65,
        price=Decimal("300.00"),
    ))

    snapshot = _make_snapshot(
        base_pnl=Decimal("1000"),
        overlay_pnls={"overlay_pp": Decimal("-200")},
        unrealized=Decimal("1000"),
        realized=Decimal("0"),
    )
    snap_mod._save_leg_snapshots(
        store, _STRATEGY, snapshot, _DATE,
        ltp_map={"NSE_FO|NIFTY22000PE": Decimal("280.00")},
    )

    # Overlay leg snapshot must exist and satisfy total_pnl invariant
    overlay_snap = store.get_leg_snapshot(_STRATEGY, "overlay_pp", _DATE)
    assert overlay_snap is not None
    assert overlay_snap.total_pnl == overlay_snap.unrealized_pnl + overlay_snap.realized_pnl
    assert overlay_snap.total_pnl == Decimal("-200")


def test_save_leg_snapshots_total_pnl_invariant_holds(tmp_path: Path) -> None:
    """All saved leg snapshots must satisfy total_pnl == unrealized + realized.

    This is enforced by store.record_leg_snapshot, but we verify it end-to-end
    from the _save_leg_snapshots path to confirm the values we compute are consistent.
    """
    store = _make_store(tmp_path)
    store.record_trade(_make_trade(leg_role="base_etf"))
    snapshot = _make_snapshot(
        base_pnl=Decimal("750"),
        unrealized=Decimal("500"),
        realized=Decimal("250"),
    )
    # Must not raise — if our arithmetic is wrong, the store's assertion would fire
    snap_mod._save_leg_snapshots(store, _STRATEGY, snapshot, _DATE, ltp_map={})
    result = store.get_leg_snapshot(_STRATEGY, "base_etf", _DATE)
    assert result is not None
    assert result.total_pnl == result.unrealized_pnl + result.realized_pnl
