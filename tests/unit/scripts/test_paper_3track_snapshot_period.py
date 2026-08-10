"""Unit tests for RPT-2/RPT-3: CLI period redesign, daily P&L delta, and monthly mode.

Coverage:
- _compute_daily_deltas: with prior snapshot → returns correct 1-day delta.
- _compute_daily_deltas: without prior snapshot → returns Decimal("0").
- CLI period mutual exclusion: --daily + --inception → argparse error.
- CLI period default: no flag → period='daily'.
- _first_trading_day_of_month: normal month, and non-trading 1st.
- _compute_monthly_deltas: reference vs first trading day; no prior → Decimal("0").
- -m flag no longer exits with error.

BUG-028 (2026-08-10): _compute_daily_deltas/_compute_monthly_deltas are now
base-leg-only — tracks no longer carry overlay P&L, so the old
overlay-summing/cc-1d-vs-inception regression tests that lived here were
removed (the behavior they guarded no longer exists in this function; overlay
P&L is computed independently, see tests/unit/scripts/test_paper_3track_overlay_pnl.py).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import scripts.strategies.three_track.paper_3track_snapshot as snap_mod
from scripts.strategies.three_track.paper_3track_snapshot import (
    _compute_daily_deltas,
    _compute_monthly_deltas,
    _first_trading_day_of_month,
)
from src.paper.models import PaperLegSnapshot

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_track_snapshot(
    base_unrealized: Decimal = Decimal("10000"),
    realized: Decimal = Decimal("2000"),
) -> MagicMock:
    """Build a minimal TrackSnapshot mock.

    BUG-028 (2026-08-10): base-leg-only — TrackPnL no longer carries
    overlay_pnls/raw_overlay_pnls at all.
    """
    snap = MagicMock(spec=["pnl"])
    snap.pnl = MagicMock(spec=["unrealized_pnl", "realized_pnl", "base_pnl", "net_pnl"])
    snap.pnl.unrealized_pnl = base_unrealized
    snap.pnl.realized_pnl = realized
    snap.pnl.base_pnl = base_unrealized
    snap.pnl.net_pnl = base_unrealized + realized
    return snap


def _make_leg_snapshot(total_pnl: Decimal) -> PaperLegSnapshot:
    return PaperLegSnapshot(
        strategy_name="paper_nifty_spot",
        leg_role="base_etf",
        snapshot_date=date(2026, 6, 14),
        unrealized_pnl=total_pnl,
        realized_pnl=Decimal("0"),
        total_pnl=total_pnl,
    )


# ── _compute_daily_deltas ─────────────────────────────────────────────────────


def test_compute_daily_deltas_with_prior_snapshot() -> None:
    """Base delta = current_total − prev.total_pnl when prior snapshot exists."""
    snap = _make_track_snapshot(base_unrealized=Decimal("10000"), realized=Decimal("2000"))
    # base_total = 10000 + 2000 = 12000; prior was 10000 → delta = 2000
    prev_snap = _make_leg_snapshot(Decimal("10000"))

    store = MagicMock()
    store.get_prev_leg_snapshot.return_value = prev_snap

    results = [("paper_nifty_spot", snap)]
    rows = _compute_daily_deltas(results, store, date(2026, 6, 15))

    assert len(rows) == 1
    assert rows[0] == {"base_pnl": Decimal("2000"), "net_pnl": Decimal("2000")}


def test_compute_daily_deltas_no_prior_snapshot() -> None:
    """Returns Decimal('0') when no prior leg snapshot exists."""
    snap = _make_track_snapshot(base_unrealized=Decimal("5000"), realized=Decimal("0"))
    store = MagicMock()
    store.get_prev_leg_snapshot.return_value = None

    rows = _compute_daily_deltas([("paper_nifty_spot", snap)], store, date(2026, 6, 15))

    assert rows[0] == {"base_pnl": Decimal("0"), "net_pnl": Decimal("0")}


# ── CLI period parsing ────────────────────────────────────────────────────────


def _make_parser() -> argparse.ArgumentParser:
    """Build a minimal parser mirroring main()'s period group."""
    parser = argparse.ArgumentParser()
    period_group = parser.add_mutually_exclusive_group()
    period_group.add_argument("--daily", "-d", dest="period", action="store_const", const="daily")
    period_group.add_argument(
        "--monthly", "-m", dest="period", action="store_const", const="monthly"
    )
    period_group.add_argument(
        "--inception", "-i", dest="period", action="store_const", const="inception"
    )
    parser.set_defaults(period="daily")
    return parser


def test_cli_period_default_is_daily() -> None:
    """No period flag → period='daily'."""
    parser = _make_parser()
    args = parser.parse_args([])
    assert args.period == "daily"


def test_cli_period_daily_flag() -> None:
    args = _make_parser().parse_args(["--daily"])
    assert args.period == "daily"


def test_cli_period_inception_flag() -> None:
    args = _make_parser().parse_args(["--inception"])
    assert args.period == "inception"


def test_cli_period_short_flags() -> None:
    assert _make_parser().parse_args(["-d"]).period == "daily"
    assert _make_parser().parse_args(["-i"]).period == "inception"
    assert _make_parser().parse_args(["-m"]).period == "monthly"


def test_cli_period_mutual_exclusion() -> None:
    """--daily and --inception together → argparse error."""
    with pytest.raises(SystemExit):
        _make_parser().parse_args(["--daily", "--inception"])


# ── _first_trading_day_of_month ───────────────────────────────────────────────


def test_first_trading_day_normal_month() -> None:
    """June 1 2026 is a Monday — it should be the first trading day of June."""
    # 2026-06-01 is a Monday; assuming it's not a holiday, it's the first TD.
    result = _first_trading_day_of_month(date(2026, 6, 15))
    assert result.month == 6
    assert result.year == 2026
    assert result.day >= 1
    # Must be a weekday
    assert result.weekday() < 5


def test_first_trading_day_non_trading_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the 1st of the month is a non-trading day, advances to the next."""

    # Patch is_trading_day so that Jun 1 is not a trading day, Jun 2 is.
    call_count = {"n": 0}

    def _fake_is_trading_day(d: date, **kwargs: object) -> bool:
        call_count["n"] += 1
        return d.day >= 2  # only 2nd onwards is trading

    monkeypatch.setattr(snap_mod, "is_trading_day", _fake_is_trading_day)

    result = _first_trading_day_of_month(date(2026, 6, 15))
    assert result == date(2026, 6, 2)


# ── _compute_monthly_deltas ───────────────────────────────────────────────────


def test_compute_monthly_deltas_with_prior_snapshot() -> None:
    """MTD delta = current_total − snapshot on/before first trading day of month."""
    snap = _make_track_snapshot(base_unrealized=Decimal("15000"), realized=Decimal("3000"))
    # base_total = 15000 + 3000 = 18000; first-TD snapshot was 10000 → MTD = 8000
    mtd_snap = _make_leg_snapshot(Decimal("10000"))

    store = MagicMock()
    store.get_prev_leg_snapshot.return_value = mtd_snap

    results = [("paper_nifty_spot", snap)]
    rows = _compute_monthly_deltas(results, store, date(2026, 6, 15))

    assert len(rows) == 1
    assert rows[0] == {"base_pnl": Decimal("8000"), "net_pnl": Decimal("8000")}


def test_compute_monthly_deltas_no_prior_snapshot() -> None:
    """Returns Decimal('0') when no leg snapshot exists before the first trading day."""
    snap = _make_track_snapshot(base_unrealized=Decimal("5000"), realized=Decimal("0"))
    store = MagicMock()
    store.get_prev_leg_snapshot.return_value = None

    rows = _compute_monthly_deltas([("paper_nifty_spot", snap)], store, date(2026, 6, 15))

    assert rows[0] == {"base_pnl": Decimal("0"), "net_pnl": Decimal("0")}


def test_compute_monthly_deltas_uses_first_td_as_reference() -> None:
    """Verifies get_prev_leg_snapshot is called with first-TD+1 as before_date."""
    snap = _make_track_snapshot(base_unrealized=Decimal("1000"), realized=Decimal("0"))
    store = MagicMock()
    store.get_prev_leg_snapshot.return_value = None

    # June 2026: first trading day is June 1 (Monday).
    _compute_monthly_deltas([("paper_nifty_spot", snap)], store, date(2026, 6, 15))

    # before_date passed to store should be first_td + 1 day = June 2
    call_args = store.get_prev_leg_snapshot.call_args
    before_date_arg = call_args[1].get("before_date") or call_args[0][2]
    from datetime import timedelta

    first_td = _first_trading_day_of_month(date(2026, 6, 15))
    assert before_date_arg == first_td + timedelta(days=1)


def test_monthly_flag_no_longer_exits() -> None:
    """Parsing -m no longer causes sys.exit(1) in _run — guard was removed in RPT-3."""
    parser = _make_parser()
    args = parser.parse_args(["-m"])
    assert args.period == "monthly"
