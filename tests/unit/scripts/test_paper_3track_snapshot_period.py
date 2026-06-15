"""Unit tests for RPT-2: CLI period redesign + daily P&L delta mode.

Coverage:
- _compute_daily_deltas: with prior snapshot → returns correct 1-day delta.
- _compute_daily_deltas: without prior snapshot → returns Decimal("0").
- _compute_daily_deltas: overlay legs summed correctly.
- CLI period mutual exclusion: --daily + --inception → argparse error.
- CLI period default: no flag → period='daily'.
- --monthly guard: exits 1 with message.
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
from scripts.strategies.three_track.paper_3track_snapshot import _compute_daily_deltas
from src.paper.models import PaperLegSnapshot

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_track_snapshot(
    base_unrealized: Decimal = Decimal("10000"),
    realized: Decimal = Decimal("2000"),
    overlay_pnls: dict | None = None,
) -> MagicMock:
    """Build a minimal TrackSnapshot mock."""
    snap = MagicMock()
    overlays = overlay_pnls or {}
    snap.pnl.unrealized_pnl = base_unrealized + sum(overlays.values())
    snap.pnl.realized_pnl = realized
    snap.pnl.base_pnl = base_unrealized
    snap.pnl.overlay_pnls = overlays
    snap.pnl.net_pnl = base_unrealized + realized + sum(overlays.values())
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
    snap = _make_track_snapshot(
        base_unrealized=Decimal("10000"), realized=Decimal("2000"), overlay_pnls={}
    )
    # base_total = 10000 + 2000 = 12000; prior was 10000 → delta = 2000
    prev_snap = _make_leg_snapshot(Decimal("10000"))

    store = MagicMock()
    store.get_prev_leg_snapshot.return_value = prev_snap

    results = [("paper_nifty_spot", snap)]
    rows = _compute_daily_deltas(results, store, date(2026, 6, 15))

    assert len(rows) == 1
    assert rows[0]["base_pnl"] == Decimal("2000")
    assert rows[0]["overlay_pnl"] == Decimal("0")
    assert rows[0]["net_pnl"] == Decimal("2000")


def test_compute_daily_deltas_no_prior_snapshot() -> None:
    """Returns Decimal('0') when no prior leg snapshot exists."""
    snap = _make_track_snapshot(base_unrealized=Decimal("5000"), realized=Decimal("0"))
    store = MagicMock()
    store.get_prev_leg_snapshot.return_value = None

    rows = _compute_daily_deltas([("paper_nifty_spot", snap)], store, date(2026, 6, 15))

    assert rows[0]["base_pnl"] == Decimal("0")
    assert rows[0]["overlay_pnl"] == Decimal("0")
    assert rows[0]["net_pnl"] == Decimal("0")


def test_compute_daily_deltas_overlay_summed() -> None:
    """Overlay day delta sums across multiple overlay legs."""
    overlays = {"overlay_cc": Decimal("-500"), "overlay_pp": Decimal("300")}
    snap = _make_track_snapshot(
        base_unrealized=Decimal("8000"), realized=Decimal("0"), overlay_pnls=overlays
    )

    def _side_effect(strategy, leg_role, before_date):
        mapping = {
            "base_etf": _make_leg_snapshot(Decimal("8000")),  # delta = 0
            "overlay_cc": _make_leg_snapshot(Decimal("-600")),  # delta = +100
            "overlay_pp": _make_leg_snapshot(Decimal("200")),  # delta = +100
        }
        return mapping.get(leg_role)

    store = MagicMock()
    store.get_prev_leg_snapshot.side_effect = _side_effect

    rows = _compute_daily_deltas([("paper_nifty_spot", snap)], store, date(2026, 6, 15))

    assert rows[0]["overlay_pnl"] == Decimal("200")  # 100 + 100
    assert rows[0]["base_pnl"] == Decimal("0")  # 8000 − 8000
    assert rows[0]["net_pnl"] == Decimal("200")


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


def test_monthly_guard_exits(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """--monthly flag causes sys.exit(1) with an explanatory message."""
    # Build args with period='monthly' and minimal required attrs
    args = argparse.Namespace(
        period="monthly",
        date=date(2026, 6, 15),
        dry_run=True,
        spot=None,
        tracks=None,
        db_path=Path("data/portfolio/portfolio.sqlite"),
        bod_path=Path("data/bod/complete_instruments.json"),
        verbose=False,
    )

    import asyncio

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(snap_mod._run(args))

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Monthly mode" in captured.out or "Monthly" in captured.out
